"""
网格交易策略 (Grid Strategy)

在价格区间内设置网格，低买高卖
"""
import logging
from decimal import Decimal
from typing import Dict, Any, List, Optional

from .base import BaseStrategy, StrategySignal, SignalType
from data_collectors import binance_collector

logger = logging.getLogger(__name__)


class GridStrategy(BaseStrategy):
    """
    网格交易策略
    
    原理:
    1. 在指定价格区间内设置等间距网格
    2. 当价格下跌穿过网格线时买入
    3. 当价格上涨穿过网格线时卖出
    
    适用场景:
    - 震荡市场
    - 无需预测方向
    """
    
    strategy_type = "grid"
    
    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        return {
            "symbol": "BTC",
            "grid_type": "arithmetic",   # arithmetic (等差) / geometric (等比)
            "upper_price": 50000,        # 上边界
            "lower_price": 40000,        # 下边界
            "grid_count": 10,            # 网格数量
            "total_investment": 10000,   # 总投资额 (USDT)
            "trigger_mode": "cross",     # cross (穿越触发) / touch (碰触触发)
        }
    
    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config)
        self._grid_lines: List[float] = []
        self._last_price: Optional[float] = None
        self._generate_grid_lines()
    
    def _generate_grid_lines(self):
        """生成网格线"""
        upper = self.config["upper_price"]
        lower = self.config["lower_price"]
        count = self.config["grid_count"]
        
        if self.config["grid_type"] == "arithmetic":
            # 等差网格
            step = (upper - lower) / count
            self._grid_lines = [lower + step * i for i in range(count + 1)]
        else:
            # 等比网格
            ratio = (upper / lower) ** (1 / count)
            self._grid_lines = [lower * (ratio ** i) for i in range(count + 1)]
        
        logger.info(f"Grid lines: {[f'{p:.2f}' for p in self._grid_lines]}")
    
    @property
    def grid_lines(self) -> List[float]:
        """获取网格线列表"""
        return self._grid_lines
    
    @property
    def investment_per_grid(self) -> float:
        """每格投资额"""
        return self.config["total_investment"] / self.config["grid_count"]
    
    async def analyze(self, market_data: Dict[str, Any] = None) -> StrategySignal:
        """
        检查是否触发网格交易
        
        Returns:
            StrategySignal: 
                - BUY: 价格向下穿过某网格线
                - SELL: 价格向上穿过某网格线
                - HOLD: 价格在同一网格区间内
        """
        symbol = self.config["symbol"]
        pair = f"{symbol}USDT"
        
        # 获取当前价格
        if market_data and "price" in market_data:
            current_price = market_data["price"]
        else:
            price_data = await binance_collector.get_price(pair)
            if not price_data:
                return StrategySignal(
                    signal=SignalType.HOLD,
                    conviction_score=50,
                    position_size=0,
                    reason="无法获取价格"
                )
            current_price = price_data["price"]
        
        # 第一次调用，记录价格
        if self._last_price is None:
            self._last_price = current_price
            return StrategySignal(
                signal=SignalType.HOLD,
                conviction_score=50,
                position_size=0,
                reason="初始化完成"
            )
        
        # 检查价格穿越
        signal, grid_level, reason = self._check_grid_cross(
            self._last_price, 
            current_price
        )
        
        # 更新最后价格
        self._last_price = current_price
        
        # 计算仓位
        if signal != SignalType.HOLD:
            position_size = self.investment_per_grid / current_price
        else:
            position_size = 0
        
        result = StrategySignal(
            signal=signal,
            conviction_score=80 if signal != SignalType.HOLD else 50,
            position_size=position_size,
            reason=reason
        )
        
        self._last_signal = result
        
        if signal != SignalType.HOLD:
            logger.info(f"Grid Strategy: {signal.value} @ Level {grid_level} - {reason}")
        
        return result
    
    def _check_grid_cross(
        self, 
        old_price: float, 
        new_price: float
    ) -> tuple[SignalType, int, str]:
        """
        检查价格是否穿越网格线
        
        Returns:
            (signal, grid_level, reason)
        """
        # 找到旧价格所在的网格层级
        old_level = self._find_grid_level(old_price)
        new_level = self._find_grid_level(new_price)
        
        if old_level == new_level:
            return SignalType.HOLD, -1, "价格在同一网格区间"
        
        # 价格下跌穿越网格线 -> 买入
        if new_level < old_level:
            crossed_line = self._grid_lines[new_level + 1]
            return (
                SignalType.BUY,
                new_level,
                f"价格下穿 {crossed_line:.2f}"
            )
        
        # 价格上涨穿越网格线 -> 卖出
        else:
            crossed_line = self._grid_lines[new_level]
            return (
                SignalType.SELL,
                new_level,
                f"价格上穿 {crossed_line:.2f}"
            )
    
    def _find_grid_level(self, price: float) -> int:
        """
        找到价格所在的网格层级
        
        层级 0: lower_price 以下
        层级 N: 在 grid_lines[N] 和 grid_lines[N+1] 之间
        层级 grid_count: upper_price 以上
        """
        if price <= self._grid_lines[0]:
            return -1  # 低于最低网格
        
        for i in range(len(self._grid_lines) - 1):
            if self._grid_lines[i] < price <= self._grid_lines[i + 1]:
                return i
        
        return len(self._grid_lines) - 1  # 高于最高网格
    
    def get_grid_status(self, current_price: float) -> Dict[str, Any]:
        """
        获取网格状态信息
        
        Returns:
            {
                "current_level": int,
                "grids": [
                    {"level": 0, "buy_price": 40000, "sell_price": 41000, "status": "filled"},
                    ...
                ]
            }
        """
        current_level = self._find_grid_level(current_price)
        
        grids = []
        for i in range(len(self._grid_lines) - 1):
            grids.append({
                "level": i,
                "buy_price": self._grid_lines[i],
                "sell_price": self._grid_lines[i + 1],
                "status": "active" if i == current_level else "pending"
            })
        
        return {
            "current_price": current_price,
            "current_level": current_level,
            "total_grids": len(self._grid_lines) - 1,
            "grids": grids,
            "investment_per_grid": self.investment_per_grid,
        }
