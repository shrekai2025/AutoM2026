"""
宏观趋势策略 (Macro Strategy)

基于宏观经济指标和市场情绪进行长期持仓决策
集成 FRED 数据和 LLM 智能分析 ("The Oracle")
"""
import logging
import json
import re
from datetime import datetime
from typing import Dict, Any, List, Optional

from .base import BaseStrategy, StrategySignal, SignalType
from data_collectors import binance_collector, fear_greed_collector
# Conditional import to avoid crash if collector has issues
try:
    from data_collectors.fred_collector import fred_collector
except ImportError:
    fred_collector = None

# LLM Service import
try:
    from core.llm_service import llm_service
except ImportError:
    llm_service = None

logger = logging.getLogger(__name__)


# ============== LLM SYSTEM PROMPT (Ported from Legacy MacroAgent) ==============
SYSTEM_PROMPT = """You are a macroeconomic analysis expert specializing in cryptocurrency markets, particularly Bitcoin.

Your role is to analyze macroeconomic indicators and their impact on Bitcoin price movements.

Key indicators you should analyze:
1. **Federal Funds Rate (DFF)**: Central bank interest rates affect liquidity and risk appetite
2. **M2 Money Supply Growth**: Money supply expansion/contraction impacts asset prices
3. **US Dollar Index (DXY)**: Bitcoin often moves inversely to USD strength
4. **Fear & Greed Index**: Market sentiment indicator
5. **10-Year Treasury Yield (DGS10)**: Risk-free rate benchmark

Analysis guidelines:
- **BULLISH signals**: Low/falling interest rates, increasing M2, weakening dollar, improving sentiment
- **BEARISH signals**: High/rising interest rates, contracting M2, strengthening dollar, extreme fear
- **NEUTRAL signals**: Mixed indicators, transitional periods

⚠️ CRITICAL OUTPUT REQUIREMENTS:

1. ❌ ABSOLUTELY NO MARKDOWN in JSON string values (no **, ##, -, *, etc.)
2. ❌ NO markdown code blocks (no ```json or ```)
3. ❌ NO extra text before or after the JSON
4. ✅ Use plain text in "reasoning" and other string fields
5. ✅ Start response with { and end with }
6. ✅ Use double quotes for all strings

The JSON must match this exact structure:

{
    "signal": "BULLISH",
    "confidence": 0.75,
    "score": 45.0,
    "reasoning": "Detailed explanation of your analysis...",
    "key_factors": [
        "High interest rates reducing liquidity",
        "Strong dollar creating headwinds"
    ],
    "risk_assessment": "High risk environment due to tight monetary policy"
}

CRITICAL REQUIREMENTS:
- "signal" MUST be one of: "BULLISH", "BEARISH", or "NEUTRAL"
- "confidence" MUST be a decimal between 0.0 and 1.0
- "score" MUST be a number between -100.0 and 100.0 representing investment conviction:
  * -100 to -60: Strong bearish (recommend selling)
  * -60 to -20: Moderate bearish (reduce exposure)
  * -20 to +20: Neutral (hold current position)
  * +20 to +60: Moderate bullish (accumulate gradually)
  * +60 to +100: Strong bullish (aggressive buying)

Be objective, data-driven, and consider the interplay between different macroeconomic forces.
"""


class MacroStrategy(BaseStrategy):
    """
    宏观趋势策略 (Enhanced)
    
    分析因素:
    1. Fear & Greed Index (市场情绪)
    2. Macro Indicators (FRED): DFF, M2, DXY, US10Y
    3. Price Trend (Technical)
    
    混合决策机制:
    - 规则评分 (Rule-Based Score)
    - LLM 分析 (High-Level Context)
    """
    
    strategy_type = "macro"
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "symbol": "BTC",
            "rebalance_period_days": 1, 
            "buy_threshold": 60,
            "sell_threshold": 40,
            "position_size": 0.3,
            "use_llm": False,  # Feature flag for LLM
            "weights": {
                "fear_greed": 0.30,
                "macro_score": 0.40,  # Combined FRED score
                "price_trend": 0.30,
            }
        }
    
    async def analyze(self, market_data: Dict[str, Any] = None) -> StrategySignal:
        """
        执行宏观分析
        """
        symbol = self.config["symbol"]
        pair = f"{symbol}USDT"
        logs = []
        
        def _ts():
            """Get current timestamp string"""
            return datetime.now().strftime("%H:%M:%S")
        
        # 1. 获取基础数据 (Price & Trend)
        logs.append({
            "timestamp": _ts(),
            "step": "API: Binance 24h Ticker",
            "type": "api_call",
            "output": "Fetching...",
            "details": f"Pair: {pair}"
        })
        ticker = await binance_collector.get_24h_ticker(pair)
        logs[-1]["timestamp"] = _ts()
        logs[-1]["output"] = f"${ticker['price']:,.2f}" if ticker else "Failed"
        
        if not ticker:
            return StrategySignal(SignalType.HOLD, 50, 0, "No market data", logs)
        
        logs.append({
            "timestamp": _ts(),
            "step": "API: Binance Klines",
            "type": "api_call",
            "output": "Fetching 90d...",
            "details": f"Interval: 1d, Limit: 90"
        })
        klines_daily = await binance_collector.get_klines(pair, "1d", limit=90)
        logs[-1]["timestamp"] = _ts()
        logs[-1]["output"] = f"Got {len(klines_daily)} candles"
        
        # 2. 获取 Fear & Greed
        logs.append({
            "timestamp": _ts(),
            "step": "API: Fear & Greed Index",
            "type": "api_call",
            "output": "Fetching...",
            "details": "alternative.me API"
        })
        fg_data = await fear_greed_collector.get_current()
        fear_greed_value = fg_data["value"] if fg_data else 50
        logs[-1]["timestamp"] = _ts()
        logs[-1]["output"] = f"Value: {fear_greed_value}"
        logs[-1]["details"] = f"Classification: {fg_data.get('classification', 'N/A')}" if fg_data else "No data"
        
        # 3. 获取 Macro Data (FRED)
        macro_indicators = {}
        if fred_collector:
            logs.append({
                "timestamp": _ts(),
                "step": "API: FRED Macro Data",
                "type": "api_call",
                "output": "Fetching...",
                "details": "DFF, DGS10, DEXUSEU"
            })
            macro_indicators = await fred_collector.get_macro_data()
            logs[-1]["timestamp"] = _ts()
            logs[-1]["output"] = f"Got {len(macro_indicators)} indicators"
            logs[-1]["details"] = json.dumps(macro_indicators, default=str)[:200]
            
        # 4. 计算各部分得分 & 记录日志
        # Trend
        trend_score = self._score_price_trend(klines_daily)
        logs.append({
            "timestamp": _ts(),
            "step": "Calculation: Price Trend",
            "type": "calculation",
            "output": f"Score: {trend_score}",
            "details": f"SMA30 comparison, {len(klines_daily)} candles"
        })
        
        # Fear & Greed
        fg_score = self._score_fear_greed(fear_greed_value)
        logs.append({
            "timestamp": _ts(),
            "step": "Calculation: Sentiment Score",
            "type": "calculation",
            "output": f"Score: {fg_score}",
            "details": f"F&G={fear_greed_value} → Contrarian Score"
        })
        
        # Macro (FRED)
        macro_score, macro_reasons, macro_logs = self._score_macro_indicators(macro_indicators)
        # Enhance macro logs with timestamps
        for log in macro_logs:
            log["timestamp"] = _ts()
            log["type"] = "calculation"
        logs.extend(macro_logs)
        
        # 5. 综合加权 (Rule-Based)
        weights = self.config["weights"]
        final_score = (
            trend_score * weights["price_trend"] +
            fg_score * weights["fear_greed"] +
            macro_score * weights["macro_score"]
        )
        
        reasons = []
        if trend_score > 60: reasons.append("上升趋势")
        elif trend_score < 40: reasons.append("下降趋势")
        
        if fg_score > 60: reasons.append(f"极度恐惧({fear_greed_value})") 
        elif fg_score < 40: reasons.append(f"极度贪婪({fear_greed_value})")
        
        reasons.extend(macro_reasons)
        
        logs.append({
            "timestamp": _ts(),
            "step": "Calculation: Final Score (Rule-Based)",
            "type": "calculation",
            "output": f"Score: {final_score:.1f}",
            "details": f"Trend({trend_score}×{weights['price_trend']}) + F&G({fg_score}×{weights['fear_greed']}) + Macro({macro_score}×{weights['macro_score']})"
        })

        # 6. LLM 增强 (Optional)
        llm_result = None
        if self.config.get("use_llm") and llm_service and llm_service.is_enabled():
            try:
                # Build prompt and log it
                user_prompt = self._build_llm_prompt(
                    ticker["price"], ticker["price_change_24h"], 
                    fear_greed_value, macro_indicators
                )
                
                logs.append({
                    "timestamp": _ts(),
                    "step": "LLM: Request",
                    "type": "llm_call",
                    "output": "Sending to OpenRouter...",
                    "details": f"Model: {llm_service.default_model}",
                    "data": {
                        "prompt": user_prompt,
                        "system_prompt_length": len(SYSTEM_PROMPT)
                    }
                })
                
                llm_result = await self._analyze_with_llm(
                    btc_price=ticker["price"],
                    price_change_24h=ticker["price_change_24h"],
                    fear_greed_value=fear_greed_value,
                    macro_indicators=macro_indicators,
                )
                
                if llm_result:
                    # Blend LLM score with rule-based (70% LLM, 30% rules when LLM available)
                    raw_score = llm_result.get("score", 0)
                    llm_score = (raw_score + 100) / 2  # Convert -100~100 to 0~100
                    
                    logs.append({
                        "timestamp": _ts(),
                        "step": "LLM: Response",
                        "type": "llm_call",
                        "output": f"{llm_result.get('signal', 'N/A')} @ {raw_score:.1f}",
                        "details": f"Raw: {raw_score} → Norm: {llm_score:.1f} | Conf: {llm_result.get('confidence', 0):.0%}",
                        "data": {
                            "response": llm_result.get("reasoning", ""),
                            "raw_json": llm_result.get("_raw_json", ""),
                            "key_factors": llm_result.get("key_factors", []),
                            "risk_assessment": llm_result.get("risk_assessment", "")
                        }
                    })

                    final_score = llm_score * 0.7 + final_score * 0.3
                    reasons.append(f"LLM: {llm_result.get('signal', '')}")
                    
                    logs.append({
                        "timestamp": _ts(),
                        "step": "Calculation: Final Score (LLM Blended)",
                        "type": "calculation",
                        "output": f"Score: {final_score:.1f}",
                        "details": f"LLM({llm_score:.1f}×0.7) + Rules({(final_score - llm_score*0.7)/0.3:.1f}×0.3)"
                    })
            except Exception as e:
                logger.error(f"LLM analysis failed: {e}")
                logs.append({
                    "timestamp": _ts(),
                    "step": "LLM: Error",
                    "type": "llm_call",
                    "output": "Failed",
                    "details": str(e)
                })

        # 7. 生成信号
        signal = self._generate_signal(final_score)
        position_size = self._calculate_position_size(final_score, signal)
        
        result = StrategySignal(
            signal=signal,
            conviction_score=final_score,
            position_size=position_size,
            reason="; ".join(reasons),
            logs=logs
        )
        
        self._last_signal = result
        logger.info(f"Macro Strategy: {signal.value} @ {final_score:.1f}% - {result.reason}")
        
        return result

    def _score_macro_indicators(self, data: Dict[str, float]) -> tuple[float, List[str], List[Dict]]:
        """
        基于 Oracle 逻辑的宏观评分
        Returns: (score, reasons, logs)
        """
        logs = []
        if not data:
            logs.append({"step": "Macro Data", "output": "Skipped", "details": "No FRED data available"})
            return 50.0, [], logs
            
        score = 50.0
        reasons = []
        
        # 1. Fed Funds Rate (DFF)
        dff = data.get("fed_funds_rate")
        if dff:
            if dff > 4.0:
                score -= 10
                reasons.append(f"高利率({dff}%)")
                logs.append({"step": "Fed Rate Check", "output": "-10 (Bearish)", "details": f"Rate {dff}% > 4.0%"})
            elif dff < 2.0:
                score += 10
                reasons.append(f"低利率环境({dff}%)")
                logs.append({"step": "Fed Rate Check", "output": "+10 (Bullish)", "details": f"Rate {dff}% < 2.0%"})
            else:
                logs.append({"step": "Fed Rate Check", "output": "Neutral", "details": f"Rate {dff}%"})
                
        # 2. US10Y Yield (DGS10)
        yield_10y = data.get("treasury_10y")
        if yield_10y:
             if yield_10y > 4.0:
                 score -= 5
                 logs.append({"step": "10Y Yield Check", "output": "-5 (Bearish)", "details": f"Yield {yield_10y}% > 4.0%"})
             elif yield_10y < 3.0:
                 score += 5
                 logs.append({"step": "10Y Yield Check", "output": "+5 (Bullish)", "details": f"Yield {yield_10y}% < 3.0%"})
             else:
                 logs.append({"step": "10Y Yield Check", "output": "Neutral", "details": f"Yield {yield_10y}%"})
                 
        # 3. DXY (Dollar Index)
        dxy = data.get("dollar_index")
        if dxy:
            if dxy > 105:
                score -= 10
                reasons.append(f"美元强势({dxy:.1f})")
                logs.append({"step": "DXY Check", "output": "-10 (Bearish)", "details": f"DXY {dxy} > 105"})
            elif dxy < 100:
                score += 10
                reasons.append("美元弱势")
                logs.append({"step": "DXY Check", "output": "+10 (Bullish)", "details": f"DXY {dxy} < 100"})
            else:
                logs.append({"step": "DXY Check", "output": "Neutral", "details": f"DXY {dxy}"})
                
        # 4. M2 (Money Supply) YoY Growth
        m2_growth = data.get("m2_growth_yoy")
        if m2_growth is not None:
            if m2_growth > 5.0:
                score += 10
                reasons.append(f"流动性扩张(M2={m2_growth:.1f}%)")
                logs.append({"step": "M2 Check", "output": "+10 (Bullish)", "details": f"Growth {m2_growth}% > 5.0%"})
            elif m2_growth < 0.0:
                score -= 10
                reasons.append(f"流动性收缩(M2={m2_growth:.1f}%)")
                logs.append({"step": "M2 Check", "output": "-10 (Bearish)", "details": f"Growth {m2_growth}% < 0.0%"})
            else:
                logs.append({"step": "M2 Check", "output": "Neutral", "details": f"Growth {m2_growth}%"})
        else:
            logs.append({"step": "M2 Check", "output": "Skipped", "details": "Data unavailable"})
        
        return max(0, min(100, score)), reasons, logs

    def _score_fear_greed(self, value: int) -> float:
        # Contrarian: Fear (Low Value) -> Buy (High Score)
        # Greed (High Value) -> Sell (Low Score)
        if value <= 20: return 90
        if value <= 40: return 70
        if value >= 80: return 10
        if value >= 60: return 30
        return 50

    def _score_price_trend(self, klines: List[Dict]) -> float:
        if not klines or len(klines) < 30: return 50
        closes = [k["close"] for k in klines]
        sma30 = sum(closes[-30:]) / 30
        current = closes[-1]
        
        if current > sma30 * 1.05: return 80 # Strong uptrend
        if current > sma30: return 60
        if current < sma30 * 0.95: return 20 # Strong downtrend
        if current < sma30: return 40
        return 50

    def _generate_signal(self, score: float) -> SignalType:
        if score >= self.config["buy_threshold"]: return SignalType.BUY
        if score <= self.config["sell_threshold"]: return SignalType.SELL
        return SignalType.HOLD

    def _calculate_position_size(self, score: float, signal: SignalType) -> float:
        if signal == SignalType.HOLD: return 0.0
        base = self.config["position_size"]
        strength = (score - 50) / 50 if signal == SignalType.BUY else (50 - score) / 50
        return base * (0.5 + 0.5 * strength) # Dynamic sizing

    # ============== LLM ANALYSIS METHODS ==============
    
    async def _analyze_with_llm(
        self, 
        btc_price: float, 
        price_change_24h: float, 
        fear_greed_value: int, 
        macro_indicators: Dict
    ) -> Optional[Dict[str, Any]]:
        """
        Call LLM for deep macroeconomic analysis.
        Returns parsed JSON dict or None on failure.
        """
        if not llm_service or not llm_service.is_enabled():
            return None
            
        # Build prompt
        user_prompt = self._build_llm_prompt(btc_price, price_change_24h, fear_greed_value, macro_indicators)
        
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        
        logger.info("Calling LLM for macro analysis...")
        response = await llm_service.chat(messages, temperature=0.7, max_tokens=2048)
        
        # Parse response
        result = self._parse_llm_response(response.content)
        result["_raw_json"] = response.content
        logger.info(f"LLM result: signal={result.get('signal')}, score={result.get('score')}")
        
        return result
    
    def _build_llm_prompt(
        self, 
        btc_price: float, 
        price_change_24h: float, 
        fear_greed_value: int, 
        macro: Dict
    ) -> str:
        """Build the user prompt with current market data."""
        fed_rate = macro.get('fed_funds_rate', 'N/A')
        treasury_10y = macro.get('treasury_10y', 'N/A')
        dxy = macro.get('dollar_index', 'N/A')
        m2_growth = macro.get('m2_growth_yoy', 'N/A')
        m2_str = f"{m2_growth}%" if isinstance(m2_growth, (int, float)) else "N/A"
        
        return f"""Analyze the current macroeconomic environment and its impact on Bitcoin:

**Current Market Data:**
- BTC Price: ${btc_price:,.2f}
- 24h Change: {price_change_24h:+.2f}%

**Macroeconomic Indicators:**
- Federal Funds Rate: {fed_rate}%
- 10-Year Treasury Yield: {treasury_10y}%
- US Dollar Index (DXY): {dxy}
- M2 Money Supply Growth (YoY): {m2_str}

**Market Sentiment:**
- Fear & Greed Index: {fear_greed_value}/100

Provide a comprehensive macroeconomic analysis and generate a trading signal.
Return your analysis in the specified JSON format."""

    def _parse_llm_response(self, content: str) -> Dict[str, Any]:
        """
        Parse LLM response and extract structured analysis.
        Falls back to neutral on parse errors.
        """
        try:
            # Try to extract JSON from response (handle markdown code blocks)
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            elif "```" in content:
                json_start = content.find("```") + 3
                json_end = content.find("```", json_start)
                json_str = content[json_start:json_end].strip()
            else:
                # Try to find JSON object directly
                match = re.search(r'\{[\s\S]*\}', content)
                json_str = match.group(0) if match else content.strip()
            
            analysis = json.loads(json_str)
            
            # Validate required fields
            required = ["signal", "confidence", "score", "reasoning"]
            for field in required:
                if field not in analysis:
                    raise ValueError(f"Missing required field: {field}")
            
            # Validate signal type
            if analysis["signal"] not in ["BULLISH", "BEARISH", "NEUTRAL"]:
                raise ValueError(f"Invalid signal: {analysis['signal']}")
            
            # Validate ranges
            if not 0.0 <= float(analysis["confidence"]) <= 1.0:
                raise ValueError(f"Invalid confidence: {analysis['confidence']}")
            if not -100.0 <= float(analysis["score"]) <= 100.0:
                raise ValueError(f"Invalid score: {analysis['score']}")
            
            return analysis
            
        except (json.JSONDecodeError, ValueError, AttributeError) as e:
            logger.warning(f"LLM response parse error: {e}. Raw: {content[:300]}...")
            return {
                "signal": "NEUTRAL",
                "confidence": 0.3,
                "score": 0.0,
                "reasoning": f"Parse error: {str(e)}",
                "key_factors": ["Analysis parsing error"],
                "risk_assessment": "Unable to assess",
            }
