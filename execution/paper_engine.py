"""
模拟交易引擎 (Paper Trading Engine) — Phase 1C 升级

变更记录:
- v3: 继承 ExecutionEngine 基类, 新增 execute_signal() 接受 StrategySignal
      旧 execute_trade() 保留向后兼容 (标记 deprecated)
"""
import logging
import warnings
from decimal import Decimal
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Trade, Position, Strategy
from strategies.base import StrategySignal, SignalType
from execution.base import ExecutionEngine
from data_collectors import binance_collector

logger = logging.getLogger(__name__)


class PaperTradingEngine(ExecutionEngine):
    """模拟交易引擎 (v3)"""
    
    engine_type = "paper"
    
    # ====================== v3 新接口 ======================
    
    async def execute_signal(
        self,
        db: AsyncSession,
        strategy_id: int,
        signal: StrategySignal,
        current_price: Optional[float] = None,
    ) -> Optional[Trade]:
        """
        从 StrategySignal 执行模拟交易 (v3 推荐接口)
        
        Args:
            db: 数据库会话
            strategy_id: 策略ID
            signal: 策略信号
            current_price: 当前市场价格 (优先级: signal.entry_price > current_price > 实时获取)
        """
        if signal.signal == SignalType.HOLD or signal.position_size <= 0:
            return None
        
        # 确定执行价格
        price = signal.entry_price or current_price
        if price is None:
            pair = f"{signal.symbol}USDT"
            price_data = await binance_collector.get_price(pair)
            if not price_data:
                logger.error(f"Cannot get price for {pair}, trade aborted")
                return None
            price = price_data["price"]
        
        # 执行交易
        return await self.execute_trade(
            db=db,
            strategy_id=strategy_id,
            side=signal.signal.value,
            symbol=signal.symbol,
            amount=signal.position_size,
            price=price,
            reason=signal.reason,
            conviction_score=signal.conviction_score,
            signal_strength=signal.position_size,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
        )
    
    async def get_balance(self) -> Dict[str, Decimal]:
        """
        模拟引擎不追踪余额 (组合管理在 Phase 3 实现)
        返回一个理论上无限的纸上余额
        """
        return {
            "USDT": Decimal("1000000"),
            "BTC": Decimal("0"),
        }
    
    # ====================== 原有接口 (向后兼容) ======================
    
    async def execute_trade(
        self,
        db: AsyncSession,
        strategy_id: int,
        side: str,
        symbol: str,
        amount: float,
        price: float,
        reason: str = "",
        conviction_score: float = None,
        signal_strength: float = None,
        stop_loss: float = None,
        take_profit: float = None,
    ) -> Trade:
        """
        执行模拟交易 (旧接口, 保持兼容)
        
        Args:
            db: 数据库会话
            strategy_id: 策略ID
            side: 买卖方向
            symbol: 交易对 (如 BTC)
            amount: 数量
            price: 价格
            reason: 交易原因
        """
        usdt_value = Decimal(str(amount)) * Decimal(str(price))
        
        # 创建交易记录
        trade = Trade(
            strategy_id=strategy_id,
            side=side,
            symbol=symbol,
            amount=Decimal(str(amount)),
            price=Decimal(str(price)),
            usdt_value=usdt_value,
            is_paper=True,
            conviction_score=conviction_score,
            signal_strength=signal_strength,
            reason=reason,
            executed_at=datetime.utcnow(),
        )
        
        db.add(trade)
        
        # 更新持仓
        await self._update_position(db, strategy_id, symbol, side, amount, price)
        
        # 更新策略统计
        await self._update_strategy_stats(db, strategy_id, side)
        
        await db.commit()
        await db.refresh(trade)
        
        logger.info(
            f"[Paper] {side.upper()} {amount:.6f} {symbol} @ ${price:,.2f} "
            f"(Value: ${usdt_value:,.2f})"
            f"{f' | SL={stop_loss}' if stop_loss else ''}"
            f"{f' | TP={take_profit}' if take_profit else ''}"
        )
        
        return trade
    
    async def _update_position(
        self,
        db: AsyncSession,
        strategy_id: int,
        symbol: str,
        side: str,
        amount: float,
        price: float,
    ):
        """更新持仓"""
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol
            )
        )
        position = result.scalar_one_or_none()
        
        amount_dec = Decimal(str(amount))
        price_dec = Decimal(str(price))
        
        if position is None:
            if side == "buy":
                position = Position(
                    strategy_id=strategy_id,
                    symbol=symbol,
                    amount=amount_dec,
                    avg_cost=price_dec,
                    current_price=price_dec,
                    current_value=amount_dec * price_dec,
                )
                db.add(position)
        else:
            if side == "buy":
                total_cost = position.amount * position.avg_cost + amount_dec * price_dec
                position.amount += amount_dec
                if position.amount > 0:
                    position.avg_cost = total_cost / position.amount
            else:  # sell
                position.amount -= amount_dec
                if position.amount < 0:
                    position.amount = Decimal("0")
            
            position.current_price = price_dec
            position.current_value = position.amount * price_dec
            
            if position.amount > 0 and position.avg_cost > 0:
                position.unrealized_pnl = (price_dec - position.avg_cost) * position.amount
                position.unrealized_pnl_percent = (
                    (price_dec - position.avg_cost) / position.avg_cost * 100
                )
            
            position.updated_at = datetime.utcnow()
    
    async def _update_strategy_stats(
        self,
        db: AsyncSession,
        strategy_id: int,
        signal: str,
    ):
        """更新策略统计"""
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        
        if strategy:
            strategy.total_trades += 1
            strategy.last_executed_at = datetime.utcnow()
            strategy.last_signal = signal
    
    async def get_position(
        self,
        db: AsyncSession,
        strategy_id: int,
        symbol: str = "BTC"
    ) -> Optional[Position]:
        """获取持仓"""
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol
            )
        )
        return result.scalar_one_or_none()
    
    async def update_position_values(
        self,
        db: AsyncSession,
        strategy_id: int = None
    ):
        """更新所有持仓的当前价值"""
        query = select(Position)
        if strategy_id:
            query = query.where(Position.strategy_id == strategy_id)
        
        result = await db.execute(query)
        positions = result.scalars().all()
        
        for position in positions:
            if position.amount <= 0:
                continue
            
            pair = f"{position.symbol}USDT"
            price_data = await binance_collector.get_price(pair)
            
            if price_data:
                current_price = Decimal(str(price_data["price"]))
                position.current_price = current_price
                position.current_value = position.amount * current_price
                
                if position.avg_cost > 0:
                    position.unrealized_pnl = (current_price - position.avg_cost) * position.amount
                    position.unrealized_pnl_percent = (
                        (current_price - position.avg_cost) / position.avg_cost * 100
                    )
                
                position.updated_at = datetime.utcnow()
        
        await db.commit()


# 全局实例
paper_engine = PaperTradingEngine()
