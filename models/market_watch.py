"""
Market Watch Model - 行情监控
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MarketWatch(Base):
    """行情监控表"""
    __tablename__ = "market_watch"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    display_order: Mapped[int] = mapped_column(Integer, default=0)
    is_starred: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<MarketWatch {self.symbol}>"
