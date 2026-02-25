"""
技术指标计算器 (v2 — TA Strategy 强化版)

变更记录:
- v2: 修复 MACD signal_line 计算（完整历史 EMA 序列）
      新增成交量分析 (Volume MA, 量比)
      新增 Stochastic RSI
      新增趋势结构分析 (Higher High / Lower Low)
      新增蜡烛形态识别 (锤头线, 吞没形态)
      ATR 止损/止盈辅助计算
      EMA 序列计算优化（返回全量历史值）
"""
from typing import List, Dict, Any, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class IndicatorCalculator:
    """技术指标计算器 (v2)"""

    # ─────────────────────────────────────────────
    #  基础序列计算（返回历史列表）
    # ─────────────────────────────────────────────

    @staticmethod
    def calculate_ema_series(prices: List[float], period: int) -> List[float]:
        """
        计算 EMA 完整历史序列
        
        Args:
            prices: 价格列表（时间正序，最新在末尾）
            period: EMA 周期
            
        Returns:
            与 prices 等长的 EMA 值列表
        """
        if not prices:
            return []
        if len(prices) < period:
            # 数据不足时用 SMA 填充
            result = []
            for i in range(len(prices)):
                window = prices[:i+1]
                result.append(sum(window) / len(window))
            return result

        multiplier = 2 / (period + 1)
        ema_values = [prices[0]]

        for price in prices[1:]:
            ema_values.append((price - ema_values[-1]) * multiplier + ema_values[-1])

        return ema_values

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> float:
        """
        计算 EMA 当前值（最后一个点）
        
        Args:
            prices: 价格列表（时间正序，最新在末尾）
            period: EMA 周期
            
        Returns:
            EMA 当前值
        """
        if not prices:
            return 0.0
        series = IndicatorCalculator.calculate_ema_series(prices, period)
        return series[-1] if series else 0.0

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> float:
        """
        计算 RSI — 使用 Wilder's smoothing method
        
        Returns:
            RSI 值 (0-100)
        """
        if len(prices) < period + 1:
            return 50.0

        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]

        gains = [max(d, 0) for d in deltas]
        losses = [max(-d, 0) for d in deltas]

        # 初始化：用简单平均
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Wilder's smoothing
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0

        rs = avg_gain / avg_loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def calculate_stoch_rsi(prices: List[float], rsi_period: int = 14, stoch_period: int = 14) -> Dict[str, float]:
        """
        计算 Stochastic RSI
        
        Returns:
            {"k": float(0-100), "d": float(0-100)}
        """
        if len(prices) < rsi_period + stoch_period + 1:
            return {"k": 50.0, "d": 50.0}

        # 先计算全量 RSI 序列
        rsi_series = []
        for i in range(rsi_period + 1, len(prices) + 1):
            rsi_val = IndicatorCalculator.calculate_rsi(prices[:i], rsi_period)
            rsi_series.append(rsi_val)

        if len(rsi_series) < stoch_period:
            return {"k": 50.0, "d": 50.0}

        # Stochastic of RSI
        window = rsi_series[-stoch_period:]
        rsi_min = min(window)
        rsi_max = max(window)
        rsi_range = rsi_max - rsi_min

        k = ((rsi_series[-1] - rsi_min) / rsi_range * 100) if rsi_range > 0 else 50.0

        # D = 3-period SMA of K (简化：用最后3个 stoch_k)
        k_series = []
        for j in range(max(0, len(rsi_series) - 3), len(rsi_series)):
            w = rsi_series[max(0, j - stoch_period + 1):j + 1]
            mn, mx = min(w), max(w)
            r = mx - mn
            k_series.append(((rsi_series[j] - mn) / r * 100) if r > 0 else 50.0)

        d = sum(k_series) / len(k_series) if k_series else 50.0

        return {"k": k, "d": d}

    @staticmethod
    def calculate_macd(
        prices: List[float],
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, float]:
        """
        计算 MACD — 完整实现（不再使用 *0.9 近似）

        Returns:
            {
                "macd_line": float,
                "signal_line": float,
                "histogram": float,
                "trend": "bullish" | "bearish" | "neutral",
                "cross": "golden" | "death" | None
            }
        """
        if len(prices) < slow + signal:
            return {
                "macd_line": 0.0,
                "signal_line": 0.0,
                "histogram": 0.0,
                "trend": "neutral",
                "cross": None,
            }

        # 完整 EMA 序列
        ema_fast_series = IndicatorCalculator.calculate_ema_series(prices, fast)
        ema_slow_series = IndicatorCalculator.calculate_ema_series(prices, slow)

        # MACD 线序列（只有两个序列都有值时才计算）
        min_len = min(len(ema_fast_series), len(ema_slow_series))
        macd_line_series = [
            ema_fast_series[i] - ema_slow_series[i]
            for i in range(min_len)
        ]

        if len(macd_line_series) < signal:
            return {
                "macd_line": macd_line_series[-1] if macd_line_series else 0.0,
                "signal_line": 0.0,
                "histogram": 0.0,
                "trend": "neutral",
                "cross": None,
            }

        # Signal line = EMA of MACD line
        signal_series = IndicatorCalculator.calculate_ema_series(macd_line_series, signal)

        macd_line = macd_line_series[-1]
        signal_line = signal_series[-1]
        histogram = macd_line - signal_line

        # 判断趋势
        trend = "bullish" if macd_line > 0 else "bearish" if macd_line < 0 else "neutral"

        # 判断金叉/死叉（最近两根柱）
        cross = None
        if len(macd_line_series) >= 2 and len(signal_series) >= 2:
            prev_diff = macd_line_series[-2] - signal_series[-2]
            curr_diff = histogram
            if prev_diff <= 0 < curr_diff:
                cross = "golden"
            elif prev_diff >= 0 > curr_diff:
                cross = "death"

        return {
            "macd_line": macd_line,
            "signal_line": signal_line,
            "histogram": histogram,
            "trend": trend,
            "cross": cross,
        }

    @staticmethod
    def calculate_bollinger_bands(
        prices: List[float],
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, float]:
        """
        计算布林带

        Returns:
            {
                "upper": float,
                "middle": float,
                "lower": float,
                "bandwidth": float,
                "percent_b": float,
                "squeeze": bool  # 带宽压缩（可能突破信号）
            }
        """
        if len(prices) < period:
            current = prices[-1] if prices else 0
            return {
                "upper": current,
                "middle": current,
                "lower": current,
                "bandwidth": 0.0,
                "percent_b": 0.5,
                "squeeze": False,
            }

        recent = prices[-period:]
        middle = sum(recent) / period

        variance = sum((p - middle) ** 2 for p in recent) / period
        std = variance ** 0.5

        upper = middle + std_dev * std
        lower = middle - std_dev * std
        band_range = upper - lower

        bandwidth = (band_range / middle) if middle > 0 else 0.0
        current_price = prices[-1]
        percent_b = ((current_price - lower) / band_range) if band_range > 0 else 0.5

        # Squeeze: 带宽 < 过去 20 根最小带宽的 1.2 倍
        # 简化判断：当前带宽 < 0.03 (3%)
        squeeze = bandwidth < 0.03

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower,
            "bandwidth": bandwidth,
            "percent_b": percent_b,
            "squeeze": squeeze,
        }

    @staticmethod
    def calculate_atr(
        highs: List[float],
        lows: List[float],
        closes: List[float],
        period: int = 14
    ) -> float:
        """
        计算 ATR（Wilder's smoothing）
        
        Returns:
            ATR 值
        """
        if len(closes) < 2:
            return 0.0

        true_ranges = []
        for i in range(1, len(closes)):
            hl = highs[i] - lows[i]
            hc = abs(highs[i] - closes[i-1])
            lc = abs(lows[i] - closes[i-1])
            true_ranges.append(max(hl, hc, lc))

        if not true_ranges:
            return 0.0

        if len(true_ranges) < period:
            return sum(true_ranges) / len(true_ranges)

        # Wilder's smoothing
        atr = sum(true_ranges[:period]) / period
        for tr in true_ranges[period:]:
            atr = (atr * (period - 1) + tr) / period

        return atr

    @staticmethod
    def calculate_volume_analysis(volumes: List[float], period: int = 20) -> Dict[str, float]:
        """
        成交量分析
        
        Returns:
            {
                "current_volume": float,
                "volume_ma": float,       # 成交量均值
                "volume_ratio": float,    # 量比 = 当前量 / 均量
                "trend": "surge" | "normal" | "dry"  # 放量/正常/缩量
            }
        """
        if not volumes:
            return {"current_volume": 0, "volume_ma": 0, "volume_ratio": 1.0, "trend": "normal"}

        current = volumes[-1]
        window = volumes[-period:] if len(volumes) >= period else volumes
        vol_ma = sum(window) / len(window) if window else 1.0

        ratio = current / vol_ma if vol_ma > 0 else 1.0

        if ratio > 2.0:
            trend = "surge"      # 明显放量
        elif ratio < 0.5:
            trend = "dry"        # 明显缩量
        else:
            trend = "normal"

        return {
            "current_volume": current,
            "volume_ma": vol_ma,
            "volume_ratio": ratio,
            "trend": trend,
        }

    @staticmethod
    def analyze_trend_structure(closes: List[float], lookback: int = 20) -> Dict[str, Any]:
        """
        趋势结构分析 —— 识别高低点序列

        检测最近 N 根 K 线的局部高低点，判断趋势结构：
        - UPTREND: Higher High + Higher Low
        - DOWNTREND: Lower High + Lower Low
        - CONSOLIDATION: 无明显方向

        Returns:
            {
                "structure": "UPTREND" | "DOWNTREND" | "CONSOLIDATION",
                "strength": float(0-100),  # 趋势强度
                "recent_high": float,
                "recent_low": float,
            }
        """
        if len(closes) < lookback:
            return {
                "structure": "CONSOLIDATION",
                "strength": 50.0,
                "recent_high": closes[-1] if closes else 0,
                "recent_low": closes[-1] if closes else 0,
            }

        window = closes[-lookback:]
        mid = len(window) // 2

        first_half_high = max(window[:mid])
        first_half_low = min(window[:mid])
        second_half_high = max(window[mid:])
        second_half_low = min(window[mid:])

        hh = second_half_high > first_half_high  # Higher High
        hl = second_half_low > first_half_low    # Higher Low
        lh = second_half_high < first_half_high  # Lower High
        ll = second_half_low < first_half_low    # Lower Low

        if hh and hl:
            structure = "UPTREND"
            # 强度：基于涨幅
            strength = min(100, 50 + (second_half_high - first_half_high) / first_half_high * 1000)
        elif lh and ll:
            structure = "DOWNTREND"
            strength = min(100, 50 + (first_half_low - second_half_low) / first_half_low * 1000)
        else:
            structure = "CONSOLIDATION"
            strength = 50.0

        return {
            "structure": structure,
            "strength": min(100.0, max(0.0, strength)),
            "recent_high": max(window),
            "recent_low": min(window),
        }

    @staticmethod
    def identify_candle_patterns(klines: List[Dict[str, Any]]) -> List[str]:
        """
        蜡烛形态识别（最近 2 根 K 线）
        
        识别形态:
        - hammer: 锤头线（反转看涨）
        - shooting_star: 射击之星（反转看跌）
        - bullish_engulfing: 看涨吞没
        - bearish_engulfing: 看跌吞没
        - doji: 十字星（犹豫）

        Returns:
            形态名称列表
        """
        patterns = []
        if len(klines) < 2:
            return patterns

        curr = klines[-1]
        prev = klines[-2]

        curr_open = curr["open"]
        curr_close = curr["close"]
        curr_high = curr["high"]
        curr_low = curr["low"]
        curr_body = abs(curr_close - curr_open)
        curr_range = curr_high - curr_low

        prev_open = prev["open"]
        prev_close = prev["close"]

        if curr_range == 0:
            return patterns

        # 十字星：实体 < 10% 整体范围
        if curr_body / curr_range < 0.1:
            patterns.append("doji")

        # 锤头线：下影线 >= 2x 实体，上影线小
        lower_shadow = min(curr_open, curr_close) - curr_low
        upper_shadow = curr_high - max(curr_open, curr_close)
        if curr_body > 0 and lower_shadow >= 2 * curr_body and upper_shadow <= curr_body * 0.5:
            patterns.append("hammer")

        # 射击之星：上影线 >= 2x 实体，下影线小
        if curr_body > 0 and upper_shadow >= 2 * curr_body and lower_shadow <= curr_body * 0.5:
            patterns.append("shooting_star")

        # 看涨吞没：前一根下跌，当前上涨且包住前根实体
        prev_is_bear = prev_close < prev_open
        curr_is_bull = curr_close > curr_open
        if (prev_is_bear and curr_is_bull
                and curr_open < prev_close
                and curr_close > prev_open):
            patterns.append("bullish_engulfing")

        # 看跌吞没：反向
        prev_is_bull = prev_close > prev_open
        curr_is_bear = curr_close < curr_open
        if (prev_is_bull and curr_is_bear
                and curr_open > prev_close
                and curr_close < prev_open):
            patterns.append("bearish_engulfing")

        return patterns

    @staticmethod
    def calculate_stop_loss_take_profit(
        entry_price: float,
        atr: float,
        signal: str,  # "buy" | "sell"
        atr_stop_mult: float = 2.0,
        atr_target_mult: float = 3.0,
    ) -> Dict[str, Optional[float]]:
        """
        基于 ATR 计算止损/止盈价位

        Returns:
            {"stop_loss": float, "take_profit": float, "risk_reward": float}
        """
        if entry_price <= 0 or atr <= 0:
            return {"stop_loss": None, "take_profit": None, "risk_reward": 0.0}

        if signal == "buy":
            stop_loss = entry_price - atr_stop_mult * atr
            take_profit = entry_price + atr_target_mult * atr
        else:
            stop_loss = entry_price + atr_stop_mult * atr
            take_profit = entry_price - atr_target_mult * atr

        risk = abs(entry_price - stop_loss)
        reward = abs(entry_price - take_profit)
        rr = reward / risk if risk > 0 else 0.0

        return {
            "stop_loss": round(stop_loss, 2),
            "take_profit": round(take_profit, 2),
            "risk_reward": round(rr, 2),
        }

    # ─────────────────────────────────────────────
    #  综合计算入口
    # ─────────────────────────────────────────────

    def calculate_all(
        self,
        klines: List[Dict[str, Any]],
        ema_periods: List[int] = [9, 21, 50, 200],
    ) -> Dict[str, Any]:
        """
        计算所有技术指标

        Args:
            klines: K 线列表（每项含 open/high/low/close/volume）
            ema_periods: 要计算的 EMA 周期列表

        Returns:
            完整指标字典，含:
            - ema_9/21/50/200, current_price
            - rsi, stoch_rsi
            - macd (含 cross, trend)
            - bollinger (含 squeeze)
            - atr
            - volume (volume_ratio, trend)
            - trend_structure
            - candle_patterns
        """
        if not klines:
            return {}

        closes = [float(k["close"]) for k in klines]
        highs  = [float(k["high"])  for k in klines]
        lows   = [float(k["low"])   for k in klines]
        volumes = [float(k.get("volume", 0)) for k in klines]

        result: Dict[str, Any] = {
            "current_price": closes[-1],
        }

        # EMA
        for period in ema_periods:
            result[f"ema_{period}"] = self.calculate_ema(closes, period)

        # RSI
        result["rsi"] = self.calculate_rsi(closes)

        # Stochastic RSI
        result["stoch_rsi"] = self.calculate_stoch_rsi(closes)

        # MACD（完整实现）
        result["macd"] = self.calculate_macd(closes)

        # Bollinger Bands
        result["bollinger"] = self.calculate_bollinger_bands(closes)

        # ATR
        result["atr"] = self.calculate_atr(highs, lows, closes)

        # 成交量分析
        result["volume"] = self.calculate_volume_analysis(volumes)

        # 趋势结构
        result["trend_structure"] = self.analyze_trend_structure(closes)

        # 蜡烛形态
        result["candle_patterns"] = self.identify_candle_patterns(klines)

        return result


# 全局实例
indicator_calculator = IndicatorCalculator()
