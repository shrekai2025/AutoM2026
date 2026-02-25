"""
Strategy Model - 策略配置
"""
from datetime import datetime
from enum import Enum
from typing import Optional
from sqlalchemy import String, Boolean, JSON, DateTime, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class StrategyType(str, Enum):
    """策略类型"""
    TA = "ta"           # 技术指标策略
    MACRO = "macro"     # 宏观趋势策略
    GRID = "grid"       # 网格交易策略
    PAIR = "pair"       # 双币轮动/套利策略


class StrategyStatus(str, Enum):
    """策略状态"""
    ACTIVE = "active"       # 运行中
    PAUSED = "paused"       # 暂停
    STOPPED = "stopped"     # 已停止
    ERROR = "error"         # 错误


class Strategy(Base):
    """策略配置表"""
    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # ta / macro / grid / pair
    symbol: Mapped[str] = mapped_column(String(20), nullable=False, default="BTC")
    status: Mapped[str] = mapped_column(String(20), default=StrategyStatus.PAUSED.value)
    
    # 调度配置
    schedule_minutes: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    
    # 策略配置 (JSON)
    config: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # 执行统计
    total_trades: Mapped[int] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    last_signal: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    last_conviction_score: Mapped[Optional[float]] = mapped_column(nullable=True)
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<Strategy {self.name} ({self.type}) - {self.status}>"
    
    @property
    def is_active(self) -> bool:
        return self.status == StrategyStatus.ACTIVE.value
