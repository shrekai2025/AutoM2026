"""
行情实时缓存表

由 Scheduler 每 1 分钟刷新，供 API 快速返回实时价格，
避免 Agent 调用时实时等待 Binance 响应。
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, Float, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MarketCache(Base):
    """行情缓存表（每个币种一条记录，更新覆盖）"""
    __tablename__ = "market_cache"
    __table_args__ = (
        Index('ix_market_cache_symbol', 'symbol'),
    )

    # 使用 symbol 作为主键，保证每个币种唯一一条记录
    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)   # e.g. "BTC"

    # 价格数据
    price: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    price_change_24h: Mapped[float] = mapped_column(Float, default=0.0)    # 涨跌额
    price_change_pct_24h: Mapped[float] = mapped_column(Float, default=0.0)  # 涨跌幅%
    high_24h: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=True)
    low_24h: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=True)
    volume_24h: Mapped[Decimal] = mapped_column(Numeric(30, 2), nullable=True)

    # 更新时间
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "price": float(self.price),
            "change_24h": self.price_change_24h,
            "change_pct_24h": self.price_change_pct_24h,
            "high_24h": float(self.high_24h) if self.high_24h else None,
            "low_24h": float(self.low_24h) if self.low_24h else None,
            "volume_24h": float(self.volume_24h) if self.volume_24h else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
