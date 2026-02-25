"""
风控事件表 (Phase 1E)

记录所有风控拦截/修改/熔断事件，用于审计和前端展示。
"""
from datetime import datetime
from sqlalchemy import String, DateTime, Integer, JSON, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from .base import Base


class RiskEvent(Base):
    """风控事件表"""
    __tablename__ = "risk_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 事件类型
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # 可选值: circuit_breaker_triggered, circuit_breaker_released, 
    #         circuit_breaker_reject, max_drawdown_breach,
    #         daily_loss_limit, max_exposure_reject, 
    #         position_modified, signal_rejected
    
    # 关联策略 (可选，全局事件无策略关联)
    strategy_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("strategies.id"), nullable=True
    )
    
    # 事件详情 (JSON)
    details: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # 简要描述
    message: Mapped[str] = mapped_column(String(500), default="")
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<RiskEvent {self.event_type} @ {self.created_at}>"
