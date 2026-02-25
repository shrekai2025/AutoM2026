"""
Position Model - 持仓信息
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Position(Base):
    """持仓信息表"""
    __tablename__ = "positions"
    __table_args__ = (
        UniqueConstraint('strategy_id', 'symbol', name='uq_strategy_symbol'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # 持仓信息
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    avg_cost: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    
    # 当前价值
    current_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), default=Decimal("0"))
    current_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    unrealized_pnl_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    
    # 时间戳
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Position {self.symbol}: {self.amount} @ avg {self.avg_cost}>"
