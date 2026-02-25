"""
策略调度器 (v3 — Phase 1 集成)

变更记录:
- v3: 集成完整流程 Strategy -> DataQuality -> RiskManager -> ExecutionEngine -> Notification
      新增 portfolio_snapshot 定时任务
      新增 risk_events 批量写入
      支持 MarketContext 构建
"""
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Dict, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from config import (
    SCHEDULER_TIMEZONE,
    DEFAULT_TA_INTERVAL_MINUTES,
    DEFAULT_MACRO_INTERVAL_HOURS,
    DEFAULT_GRID_CHECK_SECONDS,
    PORTFOLIO_SNAPSHOT_INTERVAL_HOURS,
)
from models import Strategy, StrategyStatus, Position, PortfolioSnapshot, RiskEvent
from models.strategy_execution import StrategyExecution
from strategies import get_strategy_class, SignalType
from execution import paper_engine
from data_collectors import binance_collector
from core.market_context import MarketContext
from core.data_quality import data_quality_checker
from risk.risk_manager import risk_manager, RiskAction
from notifications.telegram import telegram_notifier

# 延迟导入 (可能不存在)
try:
    from crawler.scheduler import check_and_run_crawlers
except ImportError:
    check_and_run_crawlers = None

logger = logging.getLogger(__name__)


class StrategyScheduler:
    """策略调度器 (v3)"""
    
    def __init__(self):
        self.scheduler = AsyncIOScheduler(timezone=SCHEDULER_TIMEZONE)
        self._strategy_cache: Dict[int, object] = {}
        self._peak_value: float = 0  # 历史最高净值 (用于回撤计算)
    
    async def start(self, db_session_factory):
        """启动调度器 (Data Service Mode)"""
        self.db_session_factory = db_session_factory
        
        # [Data Service Mode] 策略自动执行已禁用，由外部 Agent 选择性触发
        # 不再加载活跃策略：_load_active_strategies 尚存但不调用
        
        self.scheduler.start()
        
        # ✅ [数据中台] 行情缓存刷新任务 (每 1 分钟)
        self.scheduler.add_job(
            self._refresh_market_cache,
            trigger=IntervalTrigger(minutes=1),
            id="market_cache_refresh",
            replace_existing=True,
        )
        
        # ✅ [数据中台] 爬虫定时任务 (ETF 流入等)
        if check_and_run_crawlers:
            self.scheduler.add_job(
                check_and_run_crawlers,
                trigger=IntervalTrigger(minutes=5),
                id="crawler_check",
                replace_existing=True,
            )
        
        # ✅ [数据中台] K 线增量同步任务 (每 15 分钟)
        # 对所有 MarketWatch 中的币种进行增量同步，保持本地全量历史数据最新
        # 首次同步某 symbol/timeframe 时会自动触发全量回填（由 KlineSyncService 处理）
        self.scheduler.add_job(
            self._sync_klines_incremental,
            trigger=IntervalTrigger(minutes=15),
            id="klines_incremental_sync",
            replace_existing=True,
        )
        
        # ✅ [数据中台] Portfolio 快照定时任务 (for Web UI 显示)
        self.scheduler.add_job(
            self._save_portfolio_snapshot,
            trigger=IntervalTrigger(hours=PORTFOLIO_SNAPSHOT_INTERVAL_HOURS),
            id="portfolio_snapshot",
            replace_existing=True,
        )
        
        # ✅ [数据中台] 风控事件写入 (for 日志完整性)
        self.scheduler.add_job(
            self._flush_risk_events,
            trigger=IntervalTrigger(minutes=5),
            id="flush_risk_events",
            replace_existing=True,
        )
        
        # ☆ 策略自动执行已禁用 - 牯略由 OpenClaw Agent 統築
        # 如需恢复，取消下方注释：
        # async with db_session_factory() as db:
        #     await self._load_active_strategies(db)
        
        logger.info("Scheduler started (Data Service Mode) - strategy auto-execution DISABLED")
    
    def stop(self):
        """停止调度器"""
        if self.scheduler.running:
            self.scheduler.shutdown()
            logger.info("Strategy Scheduler stopped")
    
    async def _load_active_strategies(self, db: AsyncSession):
        """加载并调度所有活跃策略（Data Service Mode 下不再被调用）"""
        result = await db.execute(
            select(Strategy).where(Strategy.status == StrategyStatus.ACTIVE.value)
        )
        strategies = result.scalars().all()
        
        for strategy in strategies:
            self._add_strategy_job(strategy)
        
        logger.info(f"Loaded {len(strategies)} active strategies")
    
    async def _refresh_market_cache(self):
        """[Data Service] 刷新行情缓存（每 1 分钟）"""
        try:
            from models import MarketWatch
            from models.market_cache import MarketCache
            from data_collectors import binance_collector
            
            async with self.db_session_factory() as db:
                # 获取所有监控中的币种
                result = await db.execute(select(MarketWatch))
                watched = result.scalars().all()
                
                if not watched:
                    return
                
                for item in watched:
                    try:
                        ticker = await binance_collector.get_24h_ticker(f"{item.symbol}USDT")
                        if not ticker:
                            continue
                        
                        # Upsert: 存在则更新，不存在则插入
                        existing = await db.get(MarketCache, item.symbol)
                        if existing:
                            existing.price = ticker["price"]
                            existing.price_change_24h = ticker.get("price_change_24h", 0)
                            existing.high_24h = ticker.get("high_24h")
                            existing.low_24h = ticker.get("low_24h")
                            existing.volume_24h = ticker.get("volume_24h")
                            from datetime import datetime
                            existing.updated_at = datetime.utcnow()
                        else:
                            cache = MarketCache(
                                symbol=item.symbol,
                                price=ticker["price"],
                                price_change_24h=ticker.get("price_change_24h", 0),
                                high_24h=ticker.get("high_24h"),
                                low_24h=ticker.get("low_24h"),
                                volume_24h=ticker.get("volume_24h"),
                            )
                            db.add(cache)
                    except Exception as e:
                        logger.debug(f"Cache refresh failed for {item.symbol}: {e}")
                
                await db.commit()
                logger.debug(f"Market cache refreshed for {len(watched)} symbols")
        except Exception as e:
            logger.error(f"Market cache refresh error: {e}")

    
    def _add_strategy_job(self, strategy: Strategy):
        """为策略添加调度任务"""
        job_id = f"strategy_{strategy.id}"
        
        if hasattr(strategy, 'schedule_minutes') and strategy.schedule_minutes > 0:
            interval_seconds = strategy.schedule_minutes * 60
        elif strategy.type == "grid":
            interval_seconds = DEFAULT_GRID_CHECK_SECONDS
        else:
            interval_seconds = 300
            
        config = strategy.config or {}
        if "interval_seconds" in config:
            interval_seconds = config["interval_seconds"]
        
        self.scheduler.add_job(
            self._execute_strategy,
            trigger=IntervalTrigger(seconds=interval_seconds),
            id=job_id,
            args=[strategy.id],
            replace_existing=True,
            max_instances=1,
        )
        
        logger.info(
            f"Scheduled strategy '{strategy.name}' ({strategy.type}) "
            f"every {interval_seconds}s"
        )
    
    async def _execute_strategy(self, strategy_id: int):
        """
        执行单个策略 (v3 完整流程)
        
        流程: 
        1. 获取策略 -> 2. 策略分析(生成Signal) 
        -> 3. 风控评估 -> 4. 执行引擎 -> 5. 通知
        """
        async with self.db_session_factory() as db:
            try:
                # === 1. 获取策略 ===
                result = await db.execute(
                    select(Strategy).where(Strategy.id == strategy_id)
                )
                strategy = result.scalar_one_or_none()
                
                if not strategy or strategy.status != StrategyStatus.ACTIVE.value:
                    logger.warning(f"Strategy {strategy_id} not active, skipping")
                    return
                
                # 获取策略实例
                strategy_instance = self._get_strategy_instance(strategy)
                
                # === 2. 策略分析 ===
                signal = await strategy_instance.analyze()
                
                # 确保 signal.symbol 与策略一致
                signal.symbol = strategy.symbol
                
                # === 2.5 获取当前价格 (用于风控和执行) ===
                pair = f"{strategy.symbol}USDT"
                price_data = await binance_collector.get_price(pair)
                current_price = price_data["price"] if price_data else None
                
                # === 3. 构建组合状态 (用于风控评估) ===
                portfolio_state = await self._build_portfolio_state(db)
                
                # === 3.5 风控评估 ===
                risk_decision = risk_manager.evaluate(
                    signal=signal,
                    portfolio_state=portfolio_state,
                    current_price=current_price,
                )
                
                # 记录执行日志
                execution_record = StrategyExecution(
                    strategy_id=strategy.id,
                    executed_at=datetime.utcnow(),
                    market_snapshot={
                        "price": current_price,
                        "risk_action": risk_decision.action.value,
                    },
                    process_logs=signal.logs or [],
                    signal=signal.signal.value,
                    conviction_score=signal.conviction_score,
                    reason=signal.reason,
                )
                db.add(execution_record)
                
                # 更新策略执行信息
                strategy.last_executed_at = datetime.utcnow()
                strategy.last_signal = signal.signal.value
                strategy.last_conviction_score = signal.conviction_score
                
                # === 4. 执行交易 (如果风控放行) ===
                final_signal = risk_decision.final_signal
                
                if final_signal and final_signal.signal != SignalType.HOLD and final_signal.position_size > 0:
                    if current_price:
                        trade = await paper_engine.execute_signal(
                            db=db,
                            strategy_id=strategy.id,
                            signal=final_signal,
                            current_price=current_price,
                        )
                        
                        # === 5. 交易通知 ===
                        if trade and telegram_notifier.is_enabled:
                            await telegram_notifier.notify_trade(
                                side=trade.side,
                                symbol=trade.symbol,
                                amount=float(trade.amount),
                                price=float(trade.price),
                                strategy_name=strategy.name,
                                reason=final_signal.reason,
                                conviction=final_signal.conviction_score,
                                stop_loss=final_signal.stop_loss,
                                take_profit=final_signal.take_profit,
                                is_paper=trade.is_paper,
                            )
                
                # === 风控拒绝通知 ===
                if risk_decision.action == RiskAction.REJECT:
                    logger.warning(
                        f"[Risk] Rejected {signal.signal.value} for '{strategy.name}': "
                        f"{risk_decision.reason}"
                    )
                    if telegram_notifier.is_enabled:
                        await telegram_notifier.notify_risk_alert(
                            event_type="signal_rejected",
                            message=f"策略 '{strategy.name}' 信号被拒绝: {risk_decision.reason}",
                        )
                
                await db.commit()
                
                logger.info(
                    f"Strategy '{strategy.name}' executed: "
                    f"{signal.signal.value} @ {signal.conviction_score:.1f}% "
                    f"[risk: {risk_decision.action.value}]"
                )
                
            except Exception as e:
                logger.error(f"Strategy {strategy_id} execution failed: {e}", exc_info=True)
                await db.rollback()
    
    async def _build_portfolio_state(self, db: AsyncSession) -> Dict:
        """构建当前组合状态 (供风控使用)"""
        try:
            result = await db.execute(select(Position).where(Position.amount > 0))
            positions = result.scalars().all()
            
            total_value = Decimal("0")
            positions_dict = {}
            
            for pos in positions:
                value = pos.current_value or Decimal("0")
                total_value += value
                positions_dict[str(pos.strategy_id)] = {
                    "symbol": pos.symbol,
                    "value": float(value),
                    "pnl_pct": float(pos.unrealized_pnl_percent or 0),
                }
            
            # 假设初始资金 + 持仓价值
            total_value_float = float(total_value) + 100000  # 基础资金假设
            
            # 更新峰值
            if total_value_float > self._peak_value:
                self._peak_value = total_value_float
            
            # 计算回撤
            drawdown = 0
            if self._peak_value > 0:
                drawdown = (total_value_float - self._peak_value) / self._peak_value * 100
            
            return {
                "total_value": total_value_float,
                "positions": positions_dict,
                "total_pnl_pct": drawdown,
                "daily_pnl": 0,  # Phase 3 完善
            }
        except Exception as e:
            logger.error(f"Failed to build portfolio state: {e}")
            return {"total_value": 100000, "positions": {}, "total_pnl_pct": 0, "daily_pnl": 0}
    
    async def _save_portfolio_snapshot(self):
        """[Phase 1E] 定时保存组合快照"""
        try:
            async with self.db_session_factory() as db:
                portfolio = await self._build_portfolio_state(db)
                
                snapshot = PortfolioSnapshot(
                    total_value=Decimal(str(portfolio["total_value"])),
                    total_pnl=Decimal("0"),
                    total_pnl_percent=Decimal(str(portfolio.get("total_pnl_pct", 0))),
                    positions_json=portfolio.get("positions", {}),
                    drawdown_from_peak=Decimal(str(portfolio.get("total_pnl_pct", 0))),
                    circuit_breaker_active=risk_manager.circuit_breaker_status["active"],
                    snapshot_at=datetime.utcnow(),
                )
                db.add(snapshot)
                await db.commit()
                
                logger.info(f"Portfolio snapshot saved: ${portfolio['total_value']:,.2f}")
        except Exception as e:
            logger.error(f"Failed to save portfolio snapshot: {e}")
    
    async def _flush_risk_events(self):
        """[Phase 1D] 批量写入风控事件到数据库"""
        events = risk_manager.flush_events()
        if not events:
            return
        
        try:
            async with self.db_session_factory() as db:
                for event in events:
                    record = RiskEvent(
                        event_type=event.get("event_type", "unknown"),
                        strategy_id=event.get("strategy_id"),
                        details=event,
                        message=event.get("details", ""),
                        created_at=event.get("timestamp", datetime.utcnow()),
                    )
                    db.add(record)
                
                await db.commit()
                logger.info(f"Flushed {len(events)} risk events to DB")
                
                # 熔断事件推送 Telegram
                for event in events:
                    if "circuit_breaker" in event.get("event_type", ""):
                        if telegram_notifier.is_enabled:
                            await telegram_notifier.notify_risk_alert(
                                event_type=event["event_type"],
                                message=event.get("details", ""),
                            )
        except Exception as e:
            logger.error(f"Failed to flush risk events: {e}")
    
    def _get_strategy_instance(self, strategy: Strategy):
        """获取策略实例（带缓存）"""
        if strategy.id not in self._strategy_cache:
            strategy_class = get_strategy_class(strategy.type)
            if strategy_class is None:
                raise ValueError(f"Unknown strategy type: {strategy.type}")
            self._strategy_cache[strategy.id] = strategy_class(strategy.config)
        return self._strategy_cache[strategy.id]
    
    async def add_strategy(self, db: AsyncSession, strategy: Strategy):
        """添加新策略到调度器"""
        self._add_strategy_job(strategy)
        if strategy.id in self._strategy_cache:
            del self._strategy_cache[strategy.id]
    
    async def remove_strategy(self, strategy_id: int):
        """从调度器移除策略"""
        job_id = f"strategy_{strategy_id}"
        if self.scheduler.get_job(job_id):
            self.scheduler.remove_job(job_id)
            logger.info(f"Removed strategy {strategy_id} from scheduler")
        if strategy_id in self._strategy_cache:
            del self._strategy_cache[strategy_id]
    
    async def run_strategy_now(self, strategy_id: int):
        """立即执行策略（不等待调度）"""
        await self._execute_strategy(strategy_id)
    
    def get_jobs_info(self) -> list:
        """获取所有调度任务信息"""
        jobs = []
        for job in self.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "next_run": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger),
            })
        return jobs
    
    def get_risk_status(self) -> Dict:
        """获取风控状态 (Web API 使用)"""
        return risk_manager.get_status()
    
    def release_circuit_breaker(self) -> bool:
        """手动解除熔断 (Web API 使用)"""
        return risk_manager.manual_release_circuit_breaker()
    
    async def _sync_klines_incremental(self):
        """
        [数据中台] K 线增量同步任务
        
        每 15 分钟运行，对所有 MarketWatch 中的 symbol 进行增量同步。
        首次遇到某 symbol/timeframe 时自动触发全量回填（由 KlineSyncService 内部处理）。
        限速保护由 KlineSyncService 的 RateLimiter 和 Semaphore 负责。
        """
        try:
            from data_collectors.kline_sync import kline_sync
            async with self.db_session_factory() as db:
                summary = await kline_sync.sync_all_watched(
                    db=db,
                    timeframes=["15m", "1h", "4h", "1d"],
                )
                new_bars = sum(v for v in summary.values() if v > 0)
                if new_bars > 0:
                    logger.info(f"[KlineSync] Incremental sync: +{new_bars} new bars across {len(summary)} jobs")
                else:
                    logger.debug(f"[KlineSync] Incremental sync: all up to date ({len(summary)} jobs)")
        except Exception as e:
            logger.error(f"[KlineSync] Incremental sync task failed: {e}", exc_info=True)



# 全局实例
scheduler = StrategyScheduler()
