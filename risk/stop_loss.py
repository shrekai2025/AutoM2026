"""
止损引擎 (Phase 1D)

功能:
1. 若策略信号未指定 stop_loss，根据配置自动补充
2. 支持: 固定百分比 / ATR 倍数 / 追踪止损
3. 独立检查现有持仓是否触发止损 (由 scheduler 定时调用)
"""
import logging
from enum import Enum
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime

from strategies.base import StrategySignal, SignalType

logger = logging.getLogger(__name__)


class StopLossType(str, Enum):
    """止损类型"""
    FIXED_PERCENT = "fixed_percent"
    ATR_MULTIPLE = "atr_multiple"
    TRAILING = "trailing"


@dataclass
class StopLossCheck:
    """止损检查结果"""
    triggered: bool
    sl_type: StopLossType
    trigger_price: float
    current_price: float
    message: str


class StopLossEngine:
    """止损引擎"""
    
    def __init__(
        self,
        default_sl_type: StopLossType = StopLossType.FIXED_PERCENT,
        fixed_percent: float = 5.0,        # 默认止损比例 5%
        atr_multiplier: float = 2.0,       # ATR 倍数止损
        trailing_percent: float = 3.0,     # 追踪止损回撤比例
        default_tp_percent: float = 10.0,  # 默认止盈比例 10%
    ):
        self.default_sl_type = default_sl_type
        self.fixed_percent = fixed_percent
        self.atr_multiplier = atr_multiplier
        self.trailing_percent = trailing_percent
        self.default_tp_percent = default_tp_percent
        
        # 追踪止损: {strategy_id_symbol: highest_price}
        self._trailing_highs: Dict[str, float] = {}
    
    def attach_stop_loss(
        self,
        signal: StrategySignal,
        entry_price: float,
        atr: Optional[float] = None,
    ) -> StrategySignal:
        """
        若信号未指定 stop_loss / take_profit，自动补充
        
        Args:
            signal: 策略信号
            entry_price: 入场价
            atr: ATR 值 (可选, 用于 ATR 倍数止损)
            
        Returns:
            修改后的信号 (原地修改并返回)
        """
        if signal.signal == SignalType.HOLD:
            return signal
        
        is_buy = signal.signal == SignalType.BUY
        
        # 自动补充 stop_loss
        if signal.stop_loss is None:
            if self.default_sl_type == StopLossType.ATR_MULTIPLE and atr and atr > 0:
                sl_distance = atr * self.atr_multiplier
            else:
                sl_distance = entry_price * (self.fixed_percent / 100)
            
            if is_buy:
                signal.stop_loss = round(entry_price - sl_distance, 2)
            else:
                signal.stop_loss = round(entry_price + sl_distance, 2)
        
        # 自动补充 take_profit
        if signal.take_profit is None:
            tp_distance = entry_price * (self.default_tp_percent / 100)
            if is_buy:
                signal.take_profit = round(entry_price + tp_distance, 2)
            else:
                signal.take_profit = round(entry_price - tp_distance, 2)
        
        return signal
    
    def check_position_stop_loss(
        self,
        strategy_id: int,
        symbol: str,
        side: str,
        entry_price: float,
        current_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[StopLossCheck]:
        """
        检查持仓是否触发止损/止盈
        
        Args:
            strategy_id: 策略ID
            symbol: 标的
            side: "buy" (多头) / "sell" (空头)
            entry_price: 入场价
            current_price: 当前价格
            stop_loss: 止损价 (可选)
            take_profit: 止盈价 (可选)
            
        Returns:
            StopLossCheck 若触发, None 若未触发
        """
        is_long = side == "buy"
        key = f"{strategy_id}_{symbol}"
        
        # === 追踪止损检查 ===
        if self.default_sl_type == StopLossType.TRAILING:
            if key not in self._trailing_highs:
                self._trailing_highs[key] = current_price
            
            if is_long:
                # 多头: 记录最高价
                self._trailing_highs[key] = max(self._trailing_highs[key], current_price)
                trail_sl = self._trailing_highs[key] * (1 - self.trailing_percent / 100)
                if current_price <= trail_sl:
                    return StopLossCheck(
                        triggered=True,
                        sl_type=StopLossType.TRAILING,
                        trigger_price=trail_sl,
                        current_price=current_price,
                        message=f"追踪止损触发: 最高价 {self._trailing_highs[key]:.2f}, "
                                f"回撤 {self.trailing_percent}%, 当前 {current_price:.2f}"
                    )
            else:
                # 空头: 记录最低价
                self._trailing_highs[key] = min(self._trailing_highs[key], current_price)
                trail_sl = self._trailing_highs[key] * (1 + self.trailing_percent / 100)
                if current_price >= trail_sl:
                    return StopLossCheck(
                        triggered=True,
                        sl_type=StopLossType.TRAILING,
                        trigger_price=trail_sl,
                        current_price=current_price,
                        message=f"追踪止损触发(空): 最低价 {self._trailing_highs[key]:.2f}, "
                                f"反弹 {self.trailing_percent}%, 当前 {current_price:.2f}"
                    )
        
        # === 固定止损检查 ===
        if stop_loss is not None:
            if is_long and current_price <= stop_loss:
                return StopLossCheck(
                    triggered=True,
                    sl_type=StopLossType.FIXED_PERCENT,
                    trigger_price=stop_loss,
                    current_price=current_price,
                    message=f"止损触发: 价格 {current_price:.2f} <= SL {stop_loss:.2f}"
                )
            elif not is_long and current_price >= stop_loss:
                return StopLossCheck(
                    triggered=True,
                    sl_type=StopLossType.FIXED_PERCENT,
                    trigger_price=stop_loss,
                    current_price=current_price,
                    message=f"止损触发(空): 价格 {current_price:.2f} >= SL {stop_loss:.2f}"
                )
        
        # === 止盈检查 ===
        if take_profit is not None:
            if is_long and current_price >= take_profit:
                return StopLossCheck(
                    triggered=True,
                    sl_type=StopLossType.FIXED_PERCENT,
                    trigger_price=take_profit,
                    current_price=current_price,
                    message=f"止盈触发: 价格 {current_price:.2f} >= TP {take_profit:.2f}"
                )
            elif not is_long and current_price <= take_profit:
                return StopLossCheck(
                    triggered=True,
                    sl_type=StopLossType.FIXED_PERCENT,
                    trigger_price=take_profit,
                    current_price=current_price,
                    message=f"止盈触发(空): 价格 {current_price:.2f} <= TP {take_profit:.2f}"
                )
        
        return None
    
    def clear_trailing(self, strategy_id: int, symbol: str):
        """清除追踪止损记录 (平仓后调用)"""
        key = f"{strategy_id}_{symbol}"
        self._trailing_highs.pop(key, None)
