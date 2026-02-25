"""
K线本地缓存表 (Phase 1E)

用于存储历史 K 线数据，回测引擎和 DataQuality 消费。
联合唯一索引: symbol + interval + open_time
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, BigInteger, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class KlineCache(Base):
    """K线缓存表"""
    __tablename__ = "kline_cache"
    __table_args__ = (
        UniqueConstraint('symbol', 'interval', 'open_time', name='uq_kline_symbol_interval_time'),
        Index('ix_kline_symbol_interval', 'symbol', 'interval'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 标识
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)       # e.g. "BTCUSDT"
    interval: Mapped[str] = mapped_column(String(10), nullable=False)     # e.g. "1h", "4h", "1d"
    
    # 时间
    open_time: Mapped[int] = mapped_column(BigInteger, nullable=False)    # 毫秒时间戳
    close_time: Mapped[int] = mapped_column(BigInteger, nullable=False)
    
    # OHLCV
    open: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(30, 8), nullable=False)
    
    # 元数据
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Kline {self.symbol} {self.interval} {self.open_time}>"
    
    def to_dict(self):
        return {
            "open_time": self.open_time,
            "close_time": self.close_time,
            "open": float(self.open),
            "high": float(self.high),
            "low": float(self.low),
            "close": float(self.close),
            "volume": float(self.volume),
        }
