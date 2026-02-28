"""
下跌趋势跟随策略 (Downtrend Follow Strategy v1)

基于技术指标的做空策略，适用于明确下跌趋势中捕捉做空机会。

核心逻辑:
1. 趋势判断: 价格 < EMA200 (顺势做空)
2. 入场信号: EMA空头排列 + RSI/MACD确认
3. 止损: Swing High + ATR × 倍数
4. 止盈: 1R 和 2R 目标
5. 离场: 突破EMA20 或 MACD金叉

信号分级:
- ⭐⭐⭐ 强力机会: 多时间框架共振 + 极端超卖反弹风险低
- ⭐⭐ 良好机会: 单时间框架确认
"""
import logging
from typing import Dict, Any, List, Tuple, Optional

from .base import BaseStrategy, StrategySignal, SignalType
from indicators.calculator import indicator_calculator

logger = logging.getLogger(__name__)


class DowntrendFollowStrategy(BaseStrategy):
    """
    下跌趋势跟随策略 (v1)

    专注于下跌趋势中的做空机会，使用严格的风险管理。
    """

    strategy_type = "downtrend_follow"
    strategy_version = "1.0"

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "symbol": "BTC",
            "timeframes": ["15m", "1h", "4h"],  # 多时间框架确认
            "klines_limit": 300,

            # 入场条件
            "ema200_below_required": True,      # 必须在EMA200下方
            "short_threshold": 35,              # conviction <= 35 触发做空
            "min_conviction": 20,               # 最低信念分数

            # 止损/止盈
            "atr_stop_mult": 1.5,               # 止损 = Swing High + ATR × 1.5
            "risk_reward_1r": 1.0,              # 第一目标 1R
            "risk_reward_2r": 2.0,              # 第二目标 2R
            "swing_lookback": 20,               # Swing High 回溯周期

            # 仓位管理
            "base_position_size": 0.20,         # 基础仓位 20%
            "max_position_size": 0.50,          # 最大仓位 50%

            # 指标权重
            "weights": {
                "ema_alignment": 0.25,          # EMA空头排列
                "price_below_ema200": 0.20,     # 价格位置
                "rsi": 0.15,                    # RSI（避免极端超卖）
                "macd": 0.20,                   # MACD死叉/空头
                "trend_structure": 0.15,        # 下降趋势结构
                "volume": 0.05,                 # 成交量确认
            },
        }

    async def analyze(self, market_data: Dict[str, Any] = None) -> StrategySignal:
        """
        执行下跌趋势分析

        Args:
            market_data: 可选，包含多时间框架K线数据
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
            return self._hold_signal(symbol, "无法获取市场数据")

        # ── 2. 各时间框架指标计算 ────────────────────────────────
        indicators_by_tf: Dict[str, Dict[str, Any]] = {}
        for tf, klines in timeframe_data.items():
            if klines and len(klines) >= 30:
                indicators_by_tf[tf] = indicator_calculator.calculate_all(klines)

        if not indicators_by_tf:
            return self._hold_signal(symbol, "K线数据不足")

        # ── 3. 主时间框架分析 ────────────────────────────────────
        main_tf = self._get_main_tf(timeframes, indicators_by_tf)
        main_ind = indicators_by_tf[main_tf]
        current_price = main_ind.get("current_price", 0)
        ema200 = main_ind.get("ema_200", 0)

        # 检查是否在下跌趋势中
        if self.config["ema200_below_required"] and current_price >= ema200:
            return self._hold_signal(
                symbol,
                f"价格 ${current_price:,.0f} 高于 EMA200 ${ema200:,.0f}，不符合做空条件"
            )

        # ── 4. 多时间框架评分 ────────────────────────────────────
        score, reasons, score_details = self._multi_tf_score(indicators_by_tf, timeframes)

        # ── 5. 判断是否触发做空信号 ──────────────────────────────
        if score > self.config["short_threshold"]:
            return self._hold_signal(
                symbol,
                f"信念分数 {score:.1f} 高于做空阈值 {self.config['short_threshold']}"
            )

        if score < self.config["min_conviction"]:
            return self._hold_signal(
                symbol,
                f"信念分数 {score:.1f} 过低，信号不可靠"
            )

        # ── 6. 计算止损/止盈 ─────────────────────────────────────
        klines = timeframe_data[main_tf]
        swing_high = self._calculate_swing_high(klines)
        atr = main_ind.get("atr", 0)

        if atr <= 0:
            return self._hold_signal(symbol, "ATR数据无效")

        stop_loss = swing_high + self.config["atr_stop_mult"] * atr
        risk = stop_loss - current_price

        if risk <= 0:
            return self._hold_signal(symbol, "止损位置不合理")

        take_profit_1r = current_price - risk * self.config["risk_reward_1r"]
        take_profit_2r = current_price - risk * self.config["risk_reward_2r"]

        # ── 7. 信号分级 ──────────────────────────────────────────
        signal_grade = self._grade_signal(score, reasons, indicators_by_tf, timeframes)

        # ── 8. 计算仓位 ──────────────────────────────────────────
        position_size = self._calculate_position_size(score, signal_grade)

        # ── 9. 离场条件 ──────────────────────────────────────────
        ema20 = main_ind.get("ema_20", 0)
        exit_condition = f"突破EMA20(${ema20:,.0f})或MACD金叉"

        # ── 10. 组装信号 ─────────────────────────────────────────
        stars = "⭐⭐⭐" if signal_grade == "strong" else "⭐⭐"
        reason_str = f"{stars} {signal_grade.upper()}机会 | " + "; ".join(reasons[:3])

        result = StrategySignal(
            signal=SignalType.SELL,
            conviction_score=round(score, 1),
            position_size=position_size,
            reason=reason_str,
            symbol=symbol,
            entry_price=current_price,
            stop_loss=round(stop_loss, 2),
            take_profit=round(take_profit_1r, 2),  # 主要目标
            urgency="normal",
            order_type="market",
            metadata={
                "grade": signal_grade,
                "score_by_tf": score_details,
                "atr": round(atr, 2),
                "swing_high": round(swing_high, 2),
                "risk": round(risk, 2),
                "take_profit_1r": round(take_profit_1r, 2),
                "take_profit_2r": round(take_profit_2r, 2),
                "risk_reward_1r": self.config["risk_reward_1r"],
                "risk_reward_2r": self.config["risk_reward_2r"],
                "exit_condition": exit_condition,
                "ema20": round(ema20, 2) if ema20 else None,
                "ema200": round(ema200, 2) if ema200 else None,
            }
        )

        self._last_signal = result
        logger.info(
            f"Downtrend Follow [{signal_grade.upper()}]: SHORT @ {score:.1f}% "
            f"| {symbol} = ${current_price:,.0f} "
            f"| SL=${stop_loss:,.0f} TP1=${take_profit_1r:,.0f} TP2=${take_profit_2r:,.0f}"
        )

        return result

    # ─────────────────────────────────────────────
    #  辅助方法
    # ─────────────────────────────────────────────

    def _hold_signal(self, symbol: str, reason: str) -> StrategySignal:
        """生成持有信号"""
        return StrategySignal(
            signal=SignalType.HOLD,
            conviction_score=50,
            position_size=0,
            reason=reason,
            symbol=symbol,
        )

    async def _fetch_klines(
        self, symbol: str, timeframes: List[str], limit: int
    ) -> Dict[str, List[Dict]]:
        """获取K线数据（优先本地数据库）"""
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
            logger.error(f"KlineSyncService failed: {e}")
            try:
                from data_collectors import binance_collector
                return await binance_collector.get_multi_timeframe_data(
                    symbol=symbol, timeframes=timeframes
                )
            except Exception as e2:
                logger.error(f"Binance fallback failed: {e2}")
                return {}

    def _get_main_tf(self, timeframes: List[str], indicators_by_tf: Dict) -> str:
        """获取主时间框架"""
        for preferred in ["1h", "4h", "15m", "1d"]:
            if preferred in indicators_by_tf:
                return preferred
        return list(indicators_by_tf.keys())[0]

    def _calculate_swing_high(self, klines: List[Dict[str, Any]]) -> float:
        """
        计算 Swing High（最近N根K线的最高点）

        Args:
            klines: K线列表

        Returns:
            Swing High 价格
        """
        lookback = self.config.get("swing_lookback", 20)
        if not klines:
            return 0.0

        recent = klines[-lookback:] if len(klines) >= lookback else klines
        highs = [float(k["high"]) for k in recent]
        return max(highs) if highs else 0.0

    def _multi_tf_score(
        self,
        indicators_by_tf: Dict[str, Dict],
        timeframes: List[str],
    ) -> Tuple[float, List[str], Dict]:
        """
        多时间框架加权评分（做空方向）

        Returns:
            (score_0_to_100, reasons, per_tf_scores)
            注意: 分数越低越适合做空
        """
        # 时间框架权重
        weight_map = {
            "1d": 0.40,
            "4h": 0.35,
            "1h": 0.15,
            "15m": 0.10,
        }

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
        单时间框架评分（做空方向）

        Returns:
            (score_0_to_100, reasons)
            注意: 分数越低越适合做空
        """
        weights = self.config["weights"]
        score = 50.0  # 中性起点
        reasons: List[str] = []
        prefix = f"[{tf_label}]" if tf_label else ""

        # 1. 价格相对 EMA200 位置（核心条件）
        price = ind.get("current_price", 0)
        ema200 = ind.get("ema_200", 0)

        if price and ema200:
            distance_pct = (price - ema200) / ema200 * 100
            if distance_pct < -5:  # 远低于EMA200
                score -= 15
                reasons.append(f"{prefix}顺势<EMA200({distance_pct:.1f}%)")
            elif distance_pct < 0:
                score -= 10
                reasons.append(f"{prefix}顺势<EMA200")
            else:
                score += 20  # 价格高于EMA200，不适合做空

        score_adjustment = 0.0

        # 2. EMA 排列（空头排列 = 低分 = 适合做空）
        ema_score = self._score_ema_bearish(ind)
        score_adjustment += (ema_score - 50) * weights["ema_alignment"]
        if ema_score <= 30:
            reasons.append(f"{prefix}EMA空头排列")

        # 3. RSI（避免极端超卖，可能反弹）
        rsi = ind.get("rsi", 50)
        if rsi < 25:
            score += 15  # 极端超卖，风险高
            reasons.append(f"{prefix}RSI极端超卖({rsi:.0f})⚠️")
        elif rsi < 40:
            score_adjustment -= 10 * weights["rsi"]
            reasons.append(f"{prefix}RSI偏弱({rsi:.0f})")
        elif rsi > 60:
            score_adjustment -= 15 * weights["rsi"]
            reasons.append(f"{prefix}RSI超买({rsi:.0f})")

        # 4. MACD（死叉/空头 = 适合做空）
        macd = ind.get("macd", {})
        cross = macd.get("cross")
        if cross == "death":
            score_adjustment -= 20 * weights["macd"]
            reasons.append(f"{prefix}MACD死叉🔴")
        elif macd.get("trend") == "bearish":
            score_adjustment -= 10 * weights["macd"]
            reasons.append(f"{prefix}MACD空头")
        elif cross == "golden":
            score += 15  # 金叉，不适合做空
            reasons.append(f"{prefix}MACD金叉🟢⚠️")

        # 5. 趋势结构（下降趋势 = 适合做空）
        ts = ind.get("trend_structure", {})
        structure = ts.get("structure", "CONSOLIDATION")
        if structure == "DOWNTREND":
            score_adjustment -= 12 * weights["trend_structure"]
            reasons.append(f"{prefix}下降趋势结构")
        elif structure == "UPTREND":
            score += 12
            reasons.append(f"{prefix}上升趋势⚠️")

        # 6. 成交量（放量下跌 = 确认信号）
        vol = ind.get("volume", {})
        vol_trend = vol.get("trend", "normal")
        if vol_trend == "surge":
            score_adjustment -= 5 * weights["volume"]
            reasons.append(f"{prefix}放量下跌")

        # 7. 蜡烛形态（看跌形态加分）
        patterns = ind.get("candle_patterns", [])
        for p in patterns:
            if p == "bearish_engulfing":
                score -= 5
                reasons.append(f"{prefix}看跌吞没形态")
            elif p == "shooting_star":
                score -= 3
                reasons.append(f"{prefix}射击之星")
            elif p == "bullish_engulfing":
                score += 5
                reasons.append(f"{prefix}看涨吞没⚠️")

        score += score_adjustment
        return min(100.0, max(0.0, score)), reasons

    @staticmethod
    def _score_ema_bearish(ind: Dict[str, Any]) -> float:
        """
        EMA 空头排列评分

        Returns:
            分数越低越空头（0-100）
        """
        ema_9 = ind.get("ema_9", 0)
        ema_21 = ind.get("ema_21", 0)
        ema_50 = ind.get("ema_50", 0)
        ema_200 = ind.get("ema_200", 0)
        price = ind.get("current_price", 0)

        if not price:
            return 50.0

        score = 50.0

        # 价格相对 EMA 位置（低于 = 空头）
        if price < ema_9:   score -= 5
        if price < ema_21:  score -= 5
        if price < ema_50:  score -= 5
        if ema_200 and price < ema_200: score -= 5

        # EMA 空头排列（9 < 21 < 50 < 200）
        if ema_9 and ema_21 and ema_50:
            if ema_9 < ema_21 < ema_50:
                score -= 15  # 完美空头排列
                if ema_200 and ema_50 < ema_200:
                    score -= 5  # 全排列
            elif ema_9 > ema_21 > ema_50:
                score += 15  # 多头排列，不适合做空
            elif ema_9 < ema_21:
                score -= 5   # 短期空头

        return min(100.0, max(0.0, score))

    def _grade_signal(
        self,
        score: float,
        reasons: List[str],
        indicators_by_tf: Dict,
        timeframes: List[str],
    ) -> str:
        """
        信号质量分级

        Returns:
            "strong" (⭐⭐⭐) 或 "good" (⭐⭐)
        """
        # 统计有多少时间框架触发做空
        short_tfs = sum(
            1 for tf, ind in indicators_by_tf.items()
            if self._single_tf_score(ind)[0] <= self.config["short_threshold"]
        )

        # 检测是否有死叉
        has_death_cross = any(
            ind.get("macd", {}).get("cross") == "death"
            for ind in indicators_by_tf.values()
        )

        total_tfs = len(indicators_by_tf)
        if total_tfs == 0:
            return "good"

        same_direction_ratio = short_tfs / total_tfs

        # 强力信号: 极端分数 + 多时间框架共振
        if score <= 25 and same_direction_ratio >= 0.66:
            return "strong"
        elif same_direction_ratio >= 0.5 or has_death_cross:
            return "strong"
        else:
            return "good"

    def _calculate_position_size(self, score: float, grade: str) -> float:
        """
        计算仓位大小

        Args:
            score: 信念分数（越低越适合做空）
            grade: 信号等级

        Returns:
            仓位比例 (0-1)
        """
        base = self.config["base_position_size"]
        max_size = self.config["max_position_size"]

        # 信号等级倍数
        grade_mult = 1.0 if grade == "strong" else 0.7

        # 信念强度（分数越低，强度越高）
        strength = max(0.0, (50 - score) / 50)

        position = base * grade_mult * (1 + strength)
        return round(min(position, max_size), 3)
