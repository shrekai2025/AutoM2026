"""
Strategy Execution History Model - 策略执行记录
"""
from datetime import datetime
from sqlalchemy import String, JSON, DateTime, Integer, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base

class StrategyExecution(Base):
    """策略执行历史记录"""
    __tablename__ = "strategy_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    strategy_id: Mapped[int] = mapped_column(Integer, ForeignKey("strategies.id"), nullable=False)
    
    # 执行时间
    executed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    
    # 输入快照 (市场数据等)
    market_snapshot: Mapped[dict] = mapped_column(JSON, default=dict)
    
    # 过程详情 (关键决策步骤 logs)
    # 例如: [{"step": "Check FRED", "output": "Rate 4.1%"}, {"step": "Score", "output": "-10"}]
    process_logs: Mapped[list] = mapped_column(JSON, default=list)
    
    # 最终结果
    signal: Mapped[str] = mapped_column(String(20)) # BUY, SELL, HOLD
    conviction_score: Mapped[float] = mapped_column(Float, nullable=True)
    reason: Mapped[str] = mapped_column(String(500))
    
    # 关联
    # strategy = relationship("Strategy", back_populates="executions")

    def __repr__(self) -> str:
        return f"<Execution {self.id} - Strat {self.strategy_id} - {self.signal}>"
