"""
仓位计算器 (Phase 1D)

三种仓位计算策略:
1. FixedPercentSizer — 固定比例法 (默认 2% 账户风险/笔)
2. KellySizer — Half Kelly Criterion
3. AtrSizer — ATR 波动率自适应
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class PositionSizer(ABC):
    """仓位计算基类"""
    
    @abstractmethod
    def calculate(
        self,
        account_value: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        signal_conviction: float = 50.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        计算建议仓位大小 (USDT 价值)
        
        Args:
            account_value: 账户总价值 (USDT)
            entry_price: 入场价
            stop_loss: 止损价 (可选)
            signal_conviction: 信号强度 0-100
            extra: 额外参数 (如 ATR 值)
            
        Returns:
            建议投入金额 (USDT)
        """
        pass


class FixedPercentSizer(PositionSizer):
    """
    固定比例法
    
    每笔交易风险 = 账户价值 x risk_per_trade
    仓位 = 风险金额 / (入场价 - 止损价) * 入场价
    若无止损价，直接用 risk_per_trade 比例
    """
    
    def __init__(self, risk_per_trade: float = 0.02):
        """
        Args:
            risk_per_trade: 每笔交易最大风险占比 (默认 2%)
        """
        self.risk_per_trade = risk_per_trade
    
    def calculate(
        self,
        account_value: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        signal_conviction: float = 50.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> float:
        risk_amount = account_value * self.risk_per_trade
        
        if stop_loss and entry_price > 0:
            # 有止损 -> 精确计算: 仓位价值 = 风险金额 / 风险比例
            risk_pct = abs(entry_price - stop_loss) / entry_price
            if risk_pct > 0:
                position_value = risk_amount / risk_pct
            else:
                position_value = risk_amount
        else:
            # 无止损 -> 直接用风险金额作为仓位
            position_value = risk_amount
        
        # 根据信念强度微调 (conviction 50=基础, 100=x1.5, 0=x0.5)
        conviction_factor = 0.5 + (signal_conviction / 100.0)
        position_value *= conviction_factor
        
        # 上限: 不超过账户价值的 30%
        max_position = account_value * 0.30
        position_value = min(position_value, max_position)
        
        logger.debug(
            f"FixedPercent: risk={risk_amount:.2f}, "
            f"position={position_value:.2f}, conviction={signal_conviction:.0f}"
        )
        
        return max(0, position_value)


class KellySizer(PositionSizer):
    """
    Half Kelly Criterion (半凯利公式)
    
    kelly_fraction = (win_rate * avg_win / avg_loss - (1 - win_rate)) / (avg_win / avg_loss)
    实际使用 half kelly 以降低风险
    """
    
    def __init__(
        self,
        win_rate: float = 0.55,
        avg_win_loss_ratio: float = 1.5,
        kelly_fraction: float = 0.5,  # Half Kelly
        max_position_pct: float = 0.25,
    ):
        self.win_rate = win_rate
        self.avg_win_loss_ratio = avg_win_loss_ratio
        self.kelly_fraction = kelly_fraction
        self.max_position_pct = max_position_pct
    
    def calculate(
        self,
        account_value: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        signal_conviction: float = 50.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> float:
        # 可从 extra 中动态获取胜率和盈亏比
        win_rate = (extra or {}).get("win_rate", self.win_rate)
        wl_ratio = (extra or {}).get("avg_win_loss_ratio", self.avg_win_loss_ratio)
        
        # Kelly 公式
        if wl_ratio <= 0:
            return 0
        
        kelly = (win_rate * wl_ratio - (1 - win_rate)) / wl_ratio
        
        # 负值说明没有边际优势，不下单
        if kelly <= 0:
            logger.debug(f"Kelly negative ({kelly:.4f}), no position")
            return 0
        
        # 应用 Half Kelly
        position_pct = kelly * self.kelly_fraction
        position_pct = min(position_pct, self.max_position_pct)
        
        position_value = account_value * position_pct
        
        logger.debug(
            f"Kelly: raw={kelly:.4f}, half={position_pct:.4f}, "
            f"position={position_value:.2f}"
        )
        
        return max(0, position_value)


class AtrSizer(PositionSizer):
    """
    ATR 波动率自适应仓位
    
    仓位 = (账户价值 x risk_per_trade) / (ATR x atr_multiplier)
    波动大 -> ATR 大 -> 仓位小
    波动小 -> ATR 小 -> 仓位大
    """
    
    def __init__(
        self,
        risk_per_trade: float = 0.02,
        atr_multiplier: float = 2.0,
        max_position_pct: float = 0.25,
    ):
        self.risk_per_trade = risk_per_trade
        self.atr_multiplier = atr_multiplier
        self.max_position_pct = max_position_pct
    
    def calculate(
        self,
        account_value: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        signal_conviction: float = 50.0,
        extra: Optional[Dict[str, Any]] = None,
    ) -> float:
        atr = (extra or {}).get("atr")
        
        if not atr or atr <= 0 or entry_price <= 0:
            # 无 ATR 数据时退化为 FixedPercent
            logger.debug("ATR unavailable, fallback to fixed percent")
            fallback = FixedPercentSizer(self.risk_per_trade)
            return fallback.calculate(
                account_value, entry_price, stop_loss, signal_conviction, extra
            )
        
        risk_amount = account_value * self.risk_per_trade
        risk_per_unit = atr * self.atr_multiplier
        
        # 可购买单位数
        units = risk_amount / risk_per_unit
        position_value = units * entry_price
        
        # 上限
        max_position = account_value * self.max_position_pct
        position_value = min(position_value, max_position)
        
        logger.debug(
            f"ATR Sizer: atr={atr:.2f}, risk_per_unit={risk_per_unit:.2f}, "
            f"units={units:.6f}, position={position_value:.2f}"
        )
        
        return max(0, position_value)
