"""
风控管理器 (Phase 1D)

核心职责:
1. 拦截 StrategySignal，校验后放行、修改或拒绝
2. 规则: 单策略最大持仓 30%、全局最大回撤 -15%、单日亏损上限
3. 熔断机制: 触发阈值 -> 冷却期 (默认 24h)
4. 所有拒绝/修改事件写入 risk_events 表
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, Any, Optional, List

from strategies.base import StrategySignal, SignalType
from risk.position_sizer import PositionSizer, FixedPercentSizer
from risk.stop_loss import StopLossEngine

logger = logging.getLogger(__name__)


class RiskAction(str, Enum):
    """风控动作"""
    PASS = "pass"           # 放行
    MODIFY = "modify"       # 修改 (如缩减仓位)
    REJECT = "reject"       # 拒绝


@dataclass
class RiskDecision:
    """风控决策结果"""
    action: RiskAction
    original_signal: StrategySignal
    modified_signal: Optional[StrategySignal] = None
    reason: str = ""
    risk_events: List[Dict[str, Any]] = field(default_factory=list)
    
    @property
    def final_signal(self) -> Optional[StrategySignal]:
        """返回最终信号 (修改后或原始)"""
        if self.action == RiskAction.REJECT:
            return None
        return self.modified_signal or self.original_signal


class RiskManager:
    """
    风控管理器
    
    使用方式:
        decision = risk_manager.evaluate(signal, portfolio_state)
        if decision.final_signal:
            await engine.execute_signal(db, sid, decision.final_signal)
        # 记录 risk_events 到数据库
    """
    
    def __init__(
        self,
        # 仓位限制
        max_position_pct: float = 0.30,       # 单策略最大持仓 30%
        max_total_exposure_pct: float = 0.80,  # 全局最大暴露 80%
        
        # 回撤控制
        max_drawdown_pct: float = 0.15,        # 最大回撤 15%
        daily_loss_limit_pct: float = 0.05,    # 单日亏损上限 5%
        
        # 熔断
        circuit_breaker_enabled: bool = True,
        cooldown_hours: int = 24,
        
        # 组件
        position_sizer: Optional[PositionSizer] = None,
        stop_loss_engine: Optional[StopLossEngine] = None,
    ):
        self.max_position_pct = max_position_pct
        self.max_total_exposure_pct = max_total_exposure_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.daily_loss_limit_pct = daily_loss_limit_pct
        
        # 熔断状态
        self.circuit_breaker_enabled = circuit_breaker_enabled
        self.cooldown_hours = cooldown_hours
        self._circuit_breaker_active = False
        self._circuit_breaker_until: Optional[datetime] = None
        self._circuit_breaker_reason: str = ""
        
        # 组件
        self.position_sizer = position_sizer or FixedPercentSizer()
        self.stop_loss_engine = stop_loss_engine or StopLossEngine()
        
        # 日内追踪
        self._daily_pnl: float = 0.0
        self._daily_reset_date: Optional[datetime] = None
        
        # 事件记录 (内存缓存, 由 scheduler 定期写入 DB)
        self._pending_events: List[Dict[str, Any]] = []
    
    def evaluate(
        self,
        signal: StrategySignal,
        portfolio_state: Optional[Dict[str, Any]] = None,
        current_price: Optional[float] = None,
        atr: Optional[float] = None,
    ) -> RiskDecision:
        """
        评估交易信号, 决定放行/修改/拒绝
        
        Args:
            signal: 策略信号
            portfolio_state: 当前组合状态 {
                "total_value": float,
                "positions": {strategy_id: {"value": float, "pnl_pct": float}},
                "total_pnl_pct": float,  # 从最高点的回撤
                "daily_pnl": float,
            }
            current_price: 当前价格
            atr: ATR 值
            
        Returns:
            RiskDecision
        """
        events = []
        
        # HOLD 信号直接放行
        if signal.signal == SignalType.HOLD:
            return RiskDecision(
                action=RiskAction.PASS,
                original_signal=signal,
            )
        
        # === 1. 熔断检查 ===
        if self._check_circuit_breaker():
            event = {
                "event_type": "circuit_breaker_reject",
                "details": f"熔断生效中, 恢复时间: {self._circuit_breaker_until}",
                "timestamp": datetime.utcnow(),
            }
            events.append(event)
            self._pending_events.append(event)
            
            logger.warning(f"[Risk] 熔断拒绝信号: {signal.signal.value} {signal.symbol}")
            return RiskDecision(
                action=RiskAction.REJECT,
                original_signal=signal,
                reason=f"熔断生效中, 恢复时间: {self._circuit_breaker_until}",
                risk_events=events,
            )
        
        portfolio = portfolio_state or {}
        total_value = portfolio.get("total_value", 100000)  # 默认 10w
        
        # === 2. 回撤检查 ===
        total_pnl_pct = portfolio.get("total_pnl_pct", 0)
        if total_pnl_pct < -self.max_drawdown_pct * 100:
            self._trigger_circuit_breaker(
                f"全局回撤 {total_pnl_pct:.1f}% 超过阈值 -{self.max_drawdown_pct*100:.0f}%"
            )
            event = {
                "event_type": "max_drawdown_breach",
                "details": f"回撤 {total_pnl_pct:.1f}%, 触发熔断",
                "timestamp": datetime.utcnow(),
            }
            events.append(event)
            self._pending_events.append(event)
            
            return RiskDecision(
                action=RiskAction.REJECT,
                original_signal=signal,
                reason=f"触发熔断: 回撤 {total_pnl_pct:.1f}%",
                risk_events=events,
            )
        
        # === 3. 单日亏损检查 ===
        self._reset_daily_if_needed()
        daily_pnl = portfolio.get("daily_pnl", self._daily_pnl)
        daily_loss_limit = total_value * self.daily_loss_limit_pct
        
        if daily_pnl < -daily_loss_limit:
            event = {
                "event_type": "daily_loss_limit",
                "details": f"日亏损 {daily_pnl:.2f} 超过限额 {daily_loss_limit:.2f}",
                "timestamp": datetime.utcnow(),
            }
            events.append(event)
            self._pending_events.append(event)
            
            logger.warning(f"[Risk] 单日亏损限额拒绝: 亏损 {daily_pnl:.2f}")
            return RiskDecision(
                action=RiskAction.REJECT,
                original_signal=signal,
                reason=f"单日亏损 {daily_pnl:.2f} 超过限额",
                risk_events=events,
            )
        
        # === 4. 持仓比例检查 (买入时) ===
        modified_signal = None
        if signal.signal == SignalType.BUY:
            positions = portfolio.get("positions", {})
            total_exposure = sum(
                p.get("value", 0) for p in positions.values()
            )
            exposure_pct = total_exposure / total_value if total_value > 0 else 0
            
            if exposure_pct >= self.max_total_exposure_pct:
                event = {
                    "event_type": "max_exposure_reject",
                    "details": f"总暴露 {exposure_pct:.1%} >= {self.max_total_exposure_pct:.0%}",
                    "timestamp": datetime.utcnow(),
                }
                events.append(event)
                self._pending_events.append(event)
                
                return RiskDecision(
                    action=RiskAction.REJECT,
                    original_signal=signal,
                    reason=f"总暴露 {exposure_pct:.1%} 超过上限",
                    risk_events=events,
                )
        
        # === 5. 自动补充止损/止盈 ===
        price = current_price or signal.entry_price or 0
        if price > 0:
            signal = self.stop_loss_engine.attach_stop_loss(
                signal, entry_price=price, atr=atr
            )
        
        # === 放行 ===
        action = RiskAction.MODIFY if modified_signal else RiskAction.PASS
        
        if events:
            logger.info(f"[Risk] 信号通过 (events={len(events)}): {signal.signal.value} {signal.symbol}")
        
        return RiskDecision(
            action=action,
            original_signal=signal,
            modified_signal=modified_signal,
            risk_events=events,
        )
    
    # ========== 熔断机制 ==========
    
    def _check_circuit_breaker(self) -> bool:
        """检查熔断是否生效"""
        if not self.circuit_breaker_enabled or not self._circuit_breaker_active:
            return False
        
        if self._circuit_breaker_until and datetime.utcnow() >= self._circuit_breaker_until:
            self._release_circuit_breaker()
            return False
        
        return True
    
    def _trigger_circuit_breaker(self, reason: str):
        """触发熔断"""
        self._circuit_breaker_active = True
        self._circuit_breaker_until = datetime.utcnow() + timedelta(hours=self.cooldown_hours)
        self._circuit_breaker_reason = reason
        
        event = {
            "event_type": "circuit_breaker_triggered",
            "details": f"{reason} | 冷却至 {self._circuit_breaker_until}",
            "timestamp": datetime.utcnow(),
        }
        self._pending_events.append(event)
        
        logger.critical(
            f"[Risk] 熔断触发: {reason}. "
            f"冷却至 {self._circuit_breaker_until}"
        )
    
    def _release_circuit_breaker(self):
        """解除熔断"""
        logger.info(f"[Risk] 熔断自动解除 (冷却期到期)")
        
        event = {
            "event_type": "circuit_breaker_released",
            "details": "冷却期到期, 自动解除",
            "timestamp": datetime.utcnow(),
        }
        self._pending_events.append(event)
        
        self._circuit_breaker_active = False
        self._circuit_breaker_until = None
        self._circuit_breaker_reason = ""
    
    def manual_release_circuit_breaker(self) -> bool:
        """手动解除熔断 (Web UI 调用)"""
        if not self._circuit_breaker_active:
            return False
        
        logger.info("[Risk] 熔断手动解除")
        
        event = {
            "event_type": "circuit_breaker_released",
            "details": "手动解除",
            "timestamp": datetime.utcnow(),
        }
        self._pending_events.append(event)
        
        self._circuit_breaker_active = False
        self._circuit_breaker_until = None
        self._circuit_breaker_reason = ""
        return True
    
    @property
    def circuit_breaker_status(self) -> Dict[str, Any]:
        """获取熔断状态 (Web UI 展示)"""
        return {
            "active": self._circuit_breaker_active,
            "until": self._circuit_breaker_until.isoformat() if self._circuit_breaker_until else None,
            "reason": self._circuit_breaker_reason,
        }
    
    # ========== 日内追踪 ==========
    
    def _reset_daily_if_needed(self):
        """日内 PnL 重置"""
        today = datetime.utcnow().date()
        if self._daily_reset_date != today:
            self._daily_pnl = 0.0
            self._daily_reset_date = today
    
    def update_daily_pnl(self, pnl_change: float):
        """更新日内 PnL (由执行引擎回调)"""
        self._reset_daily_if_needed()
        self._daily_pnl += pnl_change
    
    # ========== 事件管理 ==========
    
    def flush_events(self) -> List[Dict[str, Any]]:
        """获取并清空待写入的风控事件"""
        events = self._pending_events.copy()
        self._pending_events.clear()
        return events
    
    def get_status(self) -> Dict[str, Any]:
        """获取风控状态摘要 (Web UI)"""
        return {
            "circuit_breaker": self.circuit_breaker_status,
            "daily_pnl": self._daily_pnl,
            "pending_events_count": len(self._pending_events),
            "config": {
                "max_position_pct": self.max_position_pct,
                "max_total_exposure_pct": self.max_total_exposure_pct,
                "max_drawdown_pct": self.max_drawdown_pct,
                "daily_loss_limit_pct": self.daily_loss_limit_pct,
                "cooldown_hours": self.cooldown_hours,
            }
        }


# 全局实例
risk_manager = RiskManager()
