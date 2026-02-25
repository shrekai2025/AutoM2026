"""
ExecutionEngine 抽象基类 (Phase 1C)

所有执行引擎 (PaperEngine / LiveEngine / BacktestEngine) 的公共接口。
"""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from strategies.base import StrategySignal
from models.trade import Trade


class ExecutionEngine(ABC):
    """
    执行引擎抽象基类
    
    子类需实现:
    - execute_signal(): 从 StrategySignal 执行交易
    - get_balance(): 获取账户余额
    """
    
    engine_type: str = "base"
    
    @abstractmethod
    async def execute_signal(
        self,
        db: AsyncSession,
        strategy_id: int,
        signal: StrategySignal,
        current_price: Optional[float] = None,
    ) -> Optional[Trade]:
        """
        执行交易信号
        
        Args:
            db: 数据库会话
            strategy_id: 策略ID
            signal: 策略信号 (v3, 含 stop_loss/take_profit 等)
            current_price: 当前市场价格 (若 signal.entry_price 为 None 则使用此价)
            
        Returns:
            Trade 记录，或 None (如 HOLD 信号)
        """
        pass
    
    @abstractmethod
    async def get_balance(self) -> Dict[str, Decimal]:
        """
        获取账户余额
        
        Returns:
            {"USDT": Decimal("10000"), "BTC": Decimal("0.5"), ...}
        """
        pass
