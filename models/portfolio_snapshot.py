"""
组合净值快照表 (Phase 1E)

由 scheduler 每小时写入一次，记录组合状态用于：
1. 前端净值曲线展示
2. 回撤计算
3. 历史绩效分析
"""
from datetime import datetime
from decimal import Decimal
from sqlalchemy import String, DateTime, Integer, Numeric, JSON
from sqlalchemy.orm import Mapped, mapped_column
from typing import Optional

from .base import Base


class PortfolioSnapshot(Base):
    """组合净值快照表"""
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # 总价值
    total_value: Mapped[Decimal] = mapped_column(Numeric(20, 2), nullable=False)
    
    # 盈亏
    total_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 2), default=Decimal("0"))
    total_pnl_percent: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    
    # 各策略持仓快照 (JSON)
    # 格式: {"strategy_1": {"symbol": "BTC", "value": 5000, "pnl": 200}, ...}
    positions_json: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    
    # 风控状态
    drawdown_from_peak: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=Decimal("0"))
    circuit_breaker_active: Mapped[bool] = mapped_column(default=False)
    
    # 时间戳
    snapshot_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    def __repr__(self) -> str:
        return f"<PortfolioSnapshot ${self.total_value} @ {self.snapshot_at}>"
