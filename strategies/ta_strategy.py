"""
技术指标策略 (TA Strategy v2)

变更记录:
- v2: 多时间框架加权融合 (4h×50%, 1h×35%, 15m×15%)
      激活成交量评分（真实量比分析）
      激活 ATR 止损/止盈（填充 StrategySignal v3 字段）
      新增信号质量分级 A/B/C（影响 position_size）
      新增趋势结构 + 金叉/死叉信号解释
      宏观不介入（纯 TA，与 macro-strategy 解耦）
      K 线来源支持本地数据库（通过 KlineSyncService）
"""
import logging
from typing import Dict, Any, List, Tuple, Optional

from .base import BaseStrategy, StrategySignal, SignalType
from indicators.calculator import indicator_calculator

logger = logging.getLogger(__name__)

# 多时间框架权重定义
# 越长周期权重越高：定趋势方向，短周期做入场时机
TIMEFRAME_WEIGHTS = {
    "1d":  0.40,   # 日线：宏观趋势定方向（如果使用）
    "4h":  0.35,   # 4h：中期趋势
    "1h":  0.15,   # 1h：执行层面趋势确认
    "15m": 0.10,   # 15m：入场时机
}

# 三时间框架默认权重（标准模式）
DEFAULT_TF_WEIGHTS_3 = {
    "4h":  0.50,
    "1h":  0.35,
    "15m": 0.15,
}

# 四时间框架默认权重（含日线）
DEFAULT_TF_WEIGHTS_4 = {
    "1d":  0.40,
    "4h":  0.30,
    "1h":  0.20,
    "15m": 0.10,
}


class TAStrategy(BaseStrategy):
    """
    技术指标策略 (v2)

    分析逻辑:
    1. 通过 KlineSyncService 从本地数据库获取多时间框架 K 线（含增量同步）
    2. 每个时间框架独立计算全套技术指标
    3. 多时间框架加权融合（长周期权重高）
    4. 生成信号 + 止损/止盈（基于 ATR）+ 信号质量分级 A/B/C
    """

    strategy_type = "ta"
    strategy_version = "2.0"

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "symbol": "BTC",
            "timeframes": ["15m", "1h", "4h"],  # 默认三时间框架
            "klines_limit": 300,                # 每个时间框架拉取的 K 线数
            "buy_threshold": 65,                # conviction >= 65 触发买入
            "sell_threshold": 35,               # conviction <= 35 触发卖出
            "position_size": 0.25,              # 基础仓位 25%
            "atr_stop_mult": 2.0,               # 止损 = entry ± ATR × 2
            "atr_target_mult": 3.0,             # 止盈 = entry ± ATR × 3
            # 指标权重（在单个时间框架内）
            "weights": {
                "ema_alignment":  0.20,
                "rsi":            0.15,
                "stoch_rsi":      0.10,
                "macd":           0.20,
                "bollinger":      0.10,
                "volume":         0.10,
                "trend_structure":0.15,
            },
        }

    async def analyze(self, market_data: Dict[str, Any] = None) -> StrategySignal:
        """
        执行技术分析

        Args:
            market_data: 可选，dict with key "klines" = {tf: [kline_dicts]}
                         如果不提供，将通过 KlineSyncService 自动从数据库获取（含增量同步）
        """
        symbol = self.config["symbol"]
        pair = f"{symbol}USDT"
        timeframes = self.config["timeframes"]
        limit = self.config.get("klines_limit", 300)

        # ── 1. 获取多时间框架 K 线 ──────────────────────────────
        if market_data is not None:
            timeframe_data = market_data.get("klines", {})
        else:
            timeframe_data = await self._fetch_klines(pair, timeframes, limit)

        if not timeframe_data:
            return StrategySignal(
                signal=SignalType.HOLD,
                conviction_score=50,
                position_size=0,
                reason="无法获取市场数据",
                symbol=symbol,
            )

        # ── 2. 各时间框架指标计算 ────────────────────────────────
        indicators_by_tf: Dict[str, Dict[str, Any]] = {}
        for tf, klines in timeframe_data.items():
            if klines and len(klines) >= 30:
                indicators_by_tf[tf] = indicator_calculator.calculate_all(klines)

        if not indicators_by_tf:
            return StrategySignal(
                signal=SignalType.HOLD,
                conviction_score=50,
                position_size=0,
                reason="K 线数据不足，无法计算指标",
                symbol=symbol,
            )

        # ── 3. 多时间框架加权融合 ────────────────────────────────
        score, reasons, score_details = self._multi_tf_score(indicators_by_tf, timeframes)

        # ── 4. 获取主时间框架当前价格和 ATR ─────────────────────
        main_tf = self._get_main_tf(timeframes, indicators_by_tf)
        main_ind = indicators_by_tf[main_tf]
        current_price = main_ind.get("current_price", 0)
        atr = main_ind.get("atr", 0)

        # ── 5. 生成信号 ─────────────────────────────────────────
        signal = self._generate_signal(score)
        signal_grade = self._grade_signal(score, reasons, indicators_by_tf, timeframes)

        # ── 6. 止损/止盈 ─────────────────────────────────────────
        sl_tp = {}
        if current_price > 0 and atr > 0:
            sl_tp = indicator_calculator.calculate_stop_loss_take_profit(
                entry_price=current_price,
                atr=atr,
                signal=signal.value,
                atr_stop_mult=self.config.get("atr_stop_mult", 2.0),
                atr_target_mult=self.config.get("atr_target_mult", 3.0),
            )

        # ── 7. 仓位 ─────────────────────────────────────────────
        position_size = self._calculate_position_size(score, signal, signal_grade)

        # ── 8. 组装 StrategySignal ────────────────────────────────
        reason_str = "; ".join(reasons) if reasons else "无明确信号"
        if signal_grade:
            reason_str = f"[{signal_grade}级信号] " + reason_str

        result = StrategySignal(
            signal=signal,
            conviction_score=round(score, 1),
            position_size=position_size,
            reason=reason_str,
            symbol=symbol,
            entry_price=current_price if current_price > 0 else None,
            stop_loss=sl_tp.get("stop_loss"),
            take_profit=sl_tp.get("take_profit"),
            metadata={
                "grade": signal_grade,
                "score_by_tf": score_details,
                "atr": round(atr, 2) if atr else None,
                "risk_reward": sl_tp.get("risk_reward"),
                "current_price": current_price,
            }
        )

        self._last_signal = result
        logger.info(
            f"TA Strategy [{signal_grade}]: {signal.value} @ {score:.1f}% "
            f"| {symbol} = ${current_price:,.0f} "
            f"| SL={sl_tp.get('stop_loss')} TP={sl_tp.get('take_profit')}"
        )

        return result

    # ─────────────────────────────────────────────
    #  K 线获取（优先本地，首次则回填）
    # ─────────────────────────────────────────────

    async def _fetch_klines(
        self, symbol: str, timeframes: List[str], limit: int
    ) -> Dict[str, List[Dict]]:
        """优先从本地数据库获取（通过 KlineSyncService），含增量同步"""
        try:
            from data_collectors.kline_sync import kline_sync
            from core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as db:
                return await kline_sync.get_multi_timeframe_klines(
                    db=db,
                    symbol=symbol,
                    timeframes=timeframes,
                    limit=limit,
                    sync_first=True,
                )
        except Exception as e:
            logger.error(f"KlineSyncService failed: {e}, falling back to direct Binance fetch")
            # Fallback: 直接从 Binance 拉
            try:
                from data_collectors import binance_collector
                return await binance_collector.get_multi_timeframe_data(
                    symbol=symbol, timeframes=timeframes
                )
            except Exception as e2:
                logger.error(f"Binance fallback also failed: {e2}")
                return {}

    # ─────────────────────────────────────────────
    #  多时间框架加权融合
    # ─────────────────────────────────────────────

    def _multi_tf_score(
        self,
        indicators_by_tf: Dict[str, Dict],
        timeframes: List[str],
    ) -> Tuple[float, List[str], Dict]:
        """
        多时间框架加权信念分数融合

        Returns:
            (total_score_0_to_100, reasons_list, per_tf_scores)
        """
        # 选定权重表
        if "1d" in indicators_by_tf:
            weight_map = DEFAULT_TF_WEIGHTS_4
        else:
            weight_map = DEFAULT_TF_WEIGHTS_3

        total_weight = 0.0
        weighted_score = 0.0
        all_reasons: List[str] = []
        per_tf_scores: Dict[str, float] = {}

        for tf, ind in indicators_by_tf.items():
            w = weight_map.get(tf, 0.1)
            tf_score, tf_reasons = self._single_tf_score(ind, tf)

            weighted_score += tf_score * w
            total_weight += w
            per_tf_scores[tf] = round(tf_score, 1)
            all_reasons.extend(tf_reasons)

        if total_weight == 0:
            return 50.0, ["无有效时间框架数据"], {}

        final_score = weighted_score / total_weight
        return min(100.0, max(0.0, final_score)), all_reasons, per_tf_scores

    def _single_tf_score(
        self, ind: Dict[str, Any], tf_label: str = ""
    ) -> Tuple[float, List[str]]:
        """
        单时间框架信念分计算

        Returns:
            (score_0_to_100, reasons)
        """
        weights = self.config["weights"]
        score = 0.0
        reasons: List[str] = []
        prefix = f"[{tf_label}]" if tf_label else ""

        # 1. EMA 排列 (0-100)
        ema_score = self._score_ema_alignment(ind)
        score += ema_score * weights["ema_alignment"]
        if ema_score >= 75:
            reasons.append(f"{prefix}EMA多头排列")
        elif ema_score <= 25:
            reasons.append(f"{prefix}EMA空头排列")

        # 2. RSI (0-100) — Wilder's smoothed
        rsi = ind.get("rsi", 50)
        rsi_score = self._score_rsi(rsi)
        score += rsi_score * weights["rsi"]
        if rsi < 30:
            reasons.append(f"{prefix}RSI超卖({rsi:.0f})")
        elif rsi > 70:
            reasons.append(f"{prefix}RSI超买({rsi:.0f})")

        # 3. Stochastic RSI
        stoch = ind.get("stoch_rsi", {})
        stoch_score = self._score_stoch_rsi(stoch)
        score += stoch_score * weights.get("stoch_rsi", 0.10)
        stoch_k = stoch.get("k", 50)
        if stoch_k < 20:
            reasons.append(f"{prefix}StochRSI超卖({stoch_k:.0f})")
        elif stoch_k > 80:
            reasons.append(f"{prefix}StochRSI超买({stoch_k:.0f})")

        # 4. MACD（完整实现，含金叉/死叉）
        macd = ind.get("macd", {})
        macd_score = self._score_macd(macd)
        score += macd_score * weights["macd"]
        cross = macd.get("cross")
        if cross == "golden":
            reasons.append(f"{prefix}MACD金叉🟢")
        elif cross == "death":
            reasons.append(f"{prefix}MACD死叉🔴")
        elif macd.get("trend") == "bullish":
            reasons.append(f"{prefix}MACD多头")
        elif macd.get("trend") == "bearish":
            reasons.append(f"{prefix}MACD空头")

        # 5. Bollinger Bands
        bb = ind.get("bollinger", {})
        bb_score = self._score_bollinger(bb)
        score += bb_score * weights["bollinger"]
        if bb.get("squeeze"):
            reasons.append(f"{prefix}布林带压缩（突破待确认）")

        # 6. 成交量（真实量比分析）
        vol = ind.get("volume", {})
        vol_score = self._score_volume(vol)
        score += vol_score * weights["volume"]
        vol_trend = vol.get("trend", "normal")
        if vol_trend == "surge":
            reasons.append(f"{prefix}成交量放量({vol.get('volume_ratio', 1):.1f}x)")
        elif vol_trend == "dry":
            reasons.append(f"{prefix}成交量缩量")

        # 7. 趋势结构
        ts = ind.get("trend_structure", {})
        ts_score = self._score_trend_structure(ts)
        score += ts_score * weights.get("trend_structure", 0.15)
        ts_struct = ts.get("structure", "CONSOLIDATION")
        if ts_struct == "UPTREND":
            reasons.append(f"{prefix}上升趋势结构")
        elif ts_struct == "DOWNTREND":
            reasons.append(f"{prefix}下降趋势结构")

        # 8. 蜡烛形态（额外加减分，不计入权重）
        patterns = ind.get("candle_patterns", [])
        pattern_bonus = 0
        for p in patterns:
            if p == "bullish_engulfing":
                pattern_bonus += 3
                reasons.append(f"{prefix}看涨吞没形态")
            elif p == "hammer":
                pattern_bonus += 2
                reasons.append(f"{prefix}锤头线")
            elif p == "bearish_engulfing":
                pattern_bonus -= 3
                reasons.append(f"{prefix}看跌吞没形态")
            elif p == "shooting_star":
                pattern_bonus -= 2
                reasons.append(f"{prefix}射击之星")
            # doji 不影响分数但值得记录
        score += pattern_bonus

        return min(100.0, max(0.0, score)), reasons

    # ─────────────────────────────────────────────
    #  各指标评分函数
    # ─────────────────────────────────────────────

    @staticmethod
    def _score_ema_alignment(ind: Dict[str, Any]) -> float:
        """EMA 排列评分"""
        ema_9  = ind.get("ema_9", 0)
        ema_21 = ind.get("ema_21", 0)
        ema_50 = ind.get("ema_50", 0)
        ema_200 = ind.get("ema_200", 0)
        price  = ind.get("current_price", 0)

        if not price:
            return 50.0

        score = 50.0

        # 价格相对 EMA 位置
        if price > ema_9:   score += 5
        if price > ema_21:  score += 5
        if price > ema_50:  score += 5
        if ema_200 and price > ema_200: score += 5

        # EMA 多头排列
        if ema_9 and ema_21 and ema_50:
            if ema_9 > ema_21 > ema_50:
                score += 15   # 完美多头排列
                if ema_200 and ema_50 > ema_200:
                    score += 5  # 全排列
            elif ema_9 < ema_21 < ema_50:
                score -= 15   # 完美空头排列
                if ema_200 and ema_50 < ema_200:
                    score -= 5
            elif ema_9 > ema_21:
                score += 5    # 短期多头
            elif ema_9 < ema_21:
                score -= 5

        return min(100.0, max(0.0, score))

    @staticmethod
    def _score_rsi(rsi: float) -> float:
        """RSI 评分（反转逻辑：极端超卖 = 高分，极端超买 = 低分）"""
        if rsi <= 20:   return 90.0
        elif rsi <= 30: return 78.0
        elif rsi <= 40: return 65.0
        elif rsi <= 50: return 55.0
        elif rsi <= 60: return 48.0
        elif rsi <= 70: return 38.0
        elif rsi <= 80: return 25.0
        else:           return 15.0

    @staticmethod
    def _score_stoch_rsi(stoch: Dict[str, float]) -> float:
        """Stochastic RSI 评分"""
        k = stoch.get("k", 50)
        d = stoch.get("d", 50)

        score = 50.0
        if k < 20:  score += 25
        elif k < 30: score += 12
        elif k > 80: score -= 25
        elif k > 70: score -= 12

        # K > D 为多头信号
        if k > d:   score += 5
        elif k < d: score -= 5

        return min(100.0, max(0.0, score))

    @staticmethod
    def _score_macd(macd: Dict[str, float]) -> float:
        """MACD 评分"""
        histogram = macd.get("histogram", 0)
        macd_line = macd.get("macd_line", 0)
        cross = macd.get("cross")

        score = 50.0

        # 金叉/死叉直接重大加减分
        if cross == "golden":
            score += 30
        elif cross == "death":
            score -= 30
        else:
            # 基于直方图大小
            if histogram > 0:
                score += min(20.0, abs(histogram) * 0.01 + 10)
            else:
                score -= min(20.0, abs(histogram) * 0.01 + 10)

        # MACD 线在零轴位置
        if macd_line > 0:
            score += 8
        elif macd_line < 0:
            score -= 8

        return min(100.0, max(0.0, score))

    @staticmethod
    def _score_bollinger(bb: Dict[str, float]) -> float:
        """%B 评分"""
        pct_b = bb.get("percent_b", 0.5)
        if pct_b < 0:    return 82.0   # 下轨下方，超卖
        elif pct_b < 0.2: return 70.0
        elif pct_b < 0.4: return 58.0
        elif pct_b < 0.6: return 48.0
        elif pct_b < 0.8: return 38.0
        elif pct_b < 1.0: return 28.0
        else:             return 18.0   # 上轨上方，超买

    @staticmethod
    def _score_volume(vol: Dict[str, Any]) -> float:
        """成交量评分（需结合价格方向才有意义，这里独立给轻度权重）"""
        ratio = vol.get("volume_ratio", 1.0)
        trend = vol.get("trend", "normal")

        # 放量：方向强化信号（中性偏加，需配合价格判断）
        # 缩量：不确定性高，保守中性
        if trend == "surge":
            return 65.0    # 放量：信号更可靠（轻度加分）
        elif trend == "dry":
            return 42.0    # 缩量：信号更弱（轻度减分）
        else:
            # 量比在 0.8-1.5 之间，线性插值
            score = 50.0 + (ratio - 1.0) * 10
            return min(60.0, max(40.0, score))

    @staticmethod
    def _score_trend_structure(ts: Dict[str, Any]) -> float:
        """趋势结构评分"""
        structure = ts.get("structure", "CONSOLIDATION")
        strength  = ts.get("strength", 50.0)

        if structure == "UPTREND":
            # 越强的上升趋势分越高
            return 55.0 + (strength - 50.0) * 0.5
        elif structure == "DOWNTREND":
            return 45.0 - (strength - 50.0) * 0.5
        else:
            return 50.0

    # ─────────────────────────────────────────────
    #  信号生成 + 质量分级
    # ─────────────────────────────────────────────

    def _get_main_tf(self, timeframes: List[str], indicators_by_tf: Dict) -> str:
        """获取主时间框架（优先 1h，次选列表第一个）"""
        for preferred in ["1h", "4h", "15m", "1d"]:
            if preferred in indicators_by_tf:
                return preferred
        return list(indicators_by_tf.keys())[0]

    def _generate_signal(self, score: float) -> SignalType:
        if score >= self.config["buy_threshold"]:
            return SignalType.BUY
        elif score <= self.config["sell_threshold"]:
            return SignalType.SELL
        else:
            return SignalType.HOLD

    def _grade_signal(
        self,
        score: float,
        reasons: List[str],
        indicators_by_tf: Dict,
        timeframes: List[str],
    ) -> str:
        """
        信号质量分级 A/B/C

        A: 强确认信号（多时间框架共振 + 极端分数）
        B: 正常信号
        C: 弱信号（仅单时间框架触发或分数边缘）
        """
        # 判断有多少时间框架同向
        buy_tfs = sum(
            1 for tf, ind in indicators_by_tf.items()
            if self._single_tf_score(ind)[0] >= self.config["buy_threshold"]
        )
        sell_tfs = sum(
            1 for tf, ind in indicators_by_tf.items()
            if self._single_tf_score(ind)[0] <= self.config["sell_threshold"]
        )

        # 检测是否有金叉/死叉
        has_cross = any(
            ind.get("macd", {}).get("cross") in ("golden", "death")
            for ind in indicators_by_tf.values()
        )

        total_tfs = len(indicators_by_tf)

        if total_tfs == 0:
            return "C"

        same_direction_ratio = max(buy_tfs, sell_tfs) / total_tfs

        if (score >= 78 or score <= 22) and same_direction_ratio >= 0.66:
            return "A"
        elif same_direction_ratio >= 0.5 or has_cross:
            return "B"
        else:
            return "C"

    def _calculate_position_size(
        self, score: float, signal: SignalType, grade: str
    ) -> float:
        """
        仓位计算（基于信念强度 + 信号等级）

        A 级: 最大仓位 100%
        B 级: 最大仓位 70%
        C 级: 最大仓位 40%
        """
        if signal == SignalType.HOLD:
            return 0.0

        base = self.config["position_size"]
        grade_mult = {"A": 1.0, "B": 0.7, "C": 0.4}.get(grade, 0.5)

        if signal == SignalType.BUY:
            strength = max(0.0, (score - 50) / 50)
        else:
            strength = max(0.0, (50 - score) / 50)

        return round(base * grade_mult * strength, 3)
