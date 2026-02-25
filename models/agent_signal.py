"""
Agent 信号记录表

用于记录 OpenClaw Agent 的决策信号，提供完整审计追踪。
数据由外部 Agent 通过 POST /api/v1/data/signals 写入。
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Numeric, Float, Text, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class AgentSignal(Base):
    """Agent 信号记录表"""
    __tablename__ = "agent_signals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # 来源
    agent_id: Mapped[str] = mapped_column(String(64), nullable=True)     # Agent 标识
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=True)  # 策略名称（自由文本）

    # 交易信号
    symbol: Mapped[str] = mapped_column(String(20), nullable=False)       # e.g. "BTC"
    action: Mapped[str] = mapped_column(String(10), nullable=False)       # BUY / SELL / HOLD
    conviction: Mapped[float] = mapped_column(Float, nullable=True)       # 0-100 信心分数
    price_at_signal: Mapped[Decimal] = mapped_column(Numeric(20, 8), nullable=True)  # 信号时价格

    # 分析依据
    reason: Mapped[str] = mapped_column(Text, nullable=True)              # 分析原因（自由文本）
    raw_analysis: Mapped[dict] = mapped_column(JSON, nullable=True)       # 完整分析 JSON

    # 风控参数
    stop_loss: Mapped[float] = mapped_column(Float, nullable=True)
    take_profit: Mapped[float] = mapped_column(Float, nullable=True)

    # 时间
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "action": self.action,
            "conviction": self.conviction,
            "price_at_signal": float(self.price_at_signal) if self.price_at_signal else None,
            "reason": self.reason,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
