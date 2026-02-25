"""
GridOrder Model - 网格订单
"""
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from sqlalchemy import String, DateTime, Integer, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class GridOrderStatus(str, Enum):
    """网格订单状态"""
    PENDING = "pending"       # 等待触发
    BUY_FILLED = "buy_filled" # 买入已成交
    SELL_FILLED = "sell_filled" # 卖出已成交
    CANCELLED = "cancelled"   # 已取消


class GridOrder(Base):
    """网格订单表"""
    __tablename__ = "grid_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # 网格信息
    grid_level: Mapped[int] = mapped_column(Integer, nullable=False)  # 网格层级 (0, 1, 2...)
    buy_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    sell_price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    
    # 状态
    status: Mapped[str] = mapped_column(String(20), default=GridOrderStatus.PENDING.value)
    
    # 成交信息
    buy_filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    sell_filled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    realized_profit: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<GridOrder L{self.grid_level}: buy@{self.buy_price} sell@{self.sell_price} ({self.status})>"
