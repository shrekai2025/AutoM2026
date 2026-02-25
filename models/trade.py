"""
Trade Model - 交易记录
"""
from datetime import datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class Trade(Base):
    """交易记录表"""
    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # 交易信息
    side: Mapped[str] = mapped_column(String(10), nullable=False)  # buy / sell
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    usdt_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    
    # 交易类型
    is_paper: Mapped[bool] = mapped_column(Boolean, default=True)  # 是否模拟交易
    
    # 决策信息
    conviction_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    signal_strength: Mapped[Optional[float]] = mapped_column(nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    
    # 时间戳
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Trade {self.side.upper()} {self.amount} {self.symbol} @ {self.price}>"
