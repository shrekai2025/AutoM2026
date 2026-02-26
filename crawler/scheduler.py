"""
ETF 爬虫定时调度器（工业化重构版）

变更记录:
- v2: 共享浏览器池（消除内存泄漏） + 任务超时保护（消除僵尸任务）
      + 数据去重（防数据库膨胀） + Task 追踪

三个固定数据源，不依赖数据库 CrawlSource 表。
爬虫结果仍然写入 crawled_data 表供页面展示。
"""
import asyncio
import logging
from datetime import datetime, date as date_type
from typing import Optional, Set, Dict
from playwright.async_api import async_playwright, Browser

from core.database import AsyncSessionLocal
from models.crawler import CrawledData
from crawler.spiders import get_spider_class
from sqlalchemy import select, and_

logger = logging.getLogger(__name__)

# ========== 硬编码 ETF 数据源 ==========
HARDCODED_SOURCES = [
    {
        "name": "Farside BTC ETF",
        "url": "https://farside.co.uk/bitcoin-etf-flow-all-data/",
        "spider_type": "farside",
    },
    {
        "name": "Farside ETH ETF",
        "url": "https://farside.co.uk/eth/",
        "spider_type": "farside",
    },
    {
        "name": "Farside SOL ETF",
        "url": "https://farside.co.uk/sol/",
        "spider_type": "farside",
    },
    # ── Arkham Intelligence 实体页面 (ETF 链上持仓) ──
    {
        "name": "Arkham BlackRock",
        "url": "https://intel.arkm.com/explorer/entity/blackrock",
        "spider_type": "arkham",
    },
    {
        "name": "Arkham Fidelity",
        "url": "https://intel.arkm.com/explorer/entity/fidelity",
        "spider_type": "arkham",
    },
]

# 上次运行时间记录（内存）
_last_run: Dict[str, datetime] = {}
_running: Set[str] = set()
_active_tasks: Dict[str, asyncio.Task] = {}  # 引用追踪，避免 GC 回收
CRAWL_INTERVAL_MINUTES = 60  # 每 1 小时
TASK_TIMEOUT_SECONDS = 300   # 单个爬虫任务最大执行 5 分钟


# ========== 共享浏览器池 ==========
class _BrowserPool:
    """进程内共享的 Playwright 浏览器，避免每次爬虫创建/销毁 Chromium"""
    
    def __init__(self):
        self._playwright = None
        self._browser: Optional[Browser] = None
        self._lock = asyncio.Lock()
        self._usage_count = 0          # 累积使用次数
        self._max_usage = 50           # 每 50 次回收一次，防内存膨胀
        
    async def acquire_page(self):
        """获取一个新的 browser context + page（每次爬虫独立隔离）"""
        async with self._lock:
            if self._browser is None or not self._browser.is_connected():
                await self._launch()
            
            # 周期性回收：超过阈值后重建浏览器释放内存
            self._usage_count += 1
            if self._usage_count >= self._max_usage:
                logger.info(f"[BrowserPool] Recycling after {self._usage_count} uses")
                await self._shutdown()
                await self._launch()
                self._usage_count = 0
        
        context = await self._browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()
        return context, page
    
    async def _launch(self):
        """内部：启动 Playwright + Chromium"""
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
        )
        logger.info("[BrowserPool] Chromium launched")
    
    async def _shutdown(self):
        """内部：安全关闭"""
        try:
            if self._browser and self._browser.is_connected():
                await self._browser.close()
        except Exception:
            pass
        try:
            if self._playwright:
                await self._playwright.stop()
                self._playwright = None
        except Exception:
            pass

    async def close(self):
        """应用关闭时调用"""
        async with self._lock:
            await self._shutdown()
            logger.info("[BrowserPool] Closed")


_browser_pool = _BrowserPool()


# ========== 单源爬取（带超时 + 去重） ==========
async def _run_one_source(source: dict):
    """对一个数据源执行爬虫（带超时保护 + 数据去重）"""
    name = source["name"]
    context = None
    
    try:
        spider_cls = get_spider_class(source["spider_type"])
        if not spider_cls:
            logger.error(f"Spider type '{source['spider_type']}' not found")
            return

        # 从共享池获取页面（不再每次启动 Chromium）
        context, page = await _browser_pool.acquire_page()

        logger.info(f"[Crawler] Starting crawl for {name} ({source['url']})")
        spider = spider_cls(source["url"])
        results = await spider.crawl(page)

        # 写入数据库（带去重）
        async with AsyncSessionLocal() as db:
            saved = 0
            skipped = 0
            for item in results:
                item_type = item.get("type")
                item_date = item.get("date")
                item_value = item.get("value")
                
                if not item_type or item_date is None:
                    continue
                
                # 去重检查：同类型 + 同日期 → 只保留最新
                is_dup = await _check_duplicate(db, item_type, item_date)
                if is_dup:
                    skipped += 1
                    continue
                
                db.add(CrawledData(
                    source_id=None,
                    task_id=None,
                    data_type=item_type,
                    date=item_date,
                    value=item_value,
                    raw_content=str(item),
                ))
                saved += 1
            await db.commit()

        _last_run[name] = datetime.utcnow()
        logger.info(f"[Crawler] {name} finished: {saved} saved, {skipped} skipped (dup)")

        # 状态上报到 /system/status
        from core.monitor import monitor
        await monitor.record_status(name, "Crawler", True, 0, f"saved={saved}, dup={skipped}")

    except asyncio.CancelledError:
        logger.warning(f"[Crawler] {name} was cancelled (timeout)")
        from core.monitor import monitor
        await monitor.record_status(name, "Crawler", False, 0, "Task timed out")
    except Exception as e:
        logger.error(f"[Crawler] {name} failed: {e}", exc_info=True)
        from core.monitor import monitor
        await monitor.record_status(name, "Crawler", False, 0, str(e)[:80])
    finally:
        _running.discard(name)
        _active_tasks.pop(name, None)
        # 关闭 context（page 会跟着释放），浏览器保留复用
        if context:
            try:
                await context.close()
            except Exception:
                pass


async def _check_duplicate(db, data_type: str, item_date) -> bool:
    """检查是否已存在相同 type + date 的记录"""
    try:
        # item_date 可能是 datetime 或 date
        if isinstance(item_date, datetime):
            check_date = item_date.date()
        elif isinstance(item_date, date_type):
            check_date = item_date
        else:
            return False
        
        from sqlalchemy import func
        result = await db.execute(
            select(func.count()).select_from(CrawledData).where(
                and_(
                    CrawledData.data_type == data_type,
                    func.date(CrawledData.date) == check_date
                )
            )
        )
        count = result.scalar()
        return count > 0
    except Exception:
        return False  # 去重失败不阻塞写入


# ========== APScheduler 入口 ==========
async def check_and_run_crawlers():
    """
    APScheduler 定时任务入口。

    检查每个硬编码数据源是否到了应该爬取的时间，
    到了就用 create_task 后台启动（带超时保护）。
    """
    # 先清理已完成/已取消的僵尸引用
    _cleanup_finished_tasks()
    
    for source in HARDCODED_SOURCES:
        name = source["name"]

        if name in _running:
            continue

        last = _last_run.get(name)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds() / 60
            if elapsed < CRAWL_INTERVAL_MINUTES:
                continue

        logger.info(f"[Crawler] Triggering background crawl for {name}")
        _running.add(name)
        task = asyncio.create_task(_run_with_timeout(source))
        _active_tasks[name] = task  # 持有引用，防 GC

    # 专门处理 etf_onchain_collector 的历史快照保存
    name_onchain = "ETF Onchain Snapshot"
    if name_onchain not in _running:
        last_onchain = _last_run.get(name_onchain)
        if not last_onchain or ((datetime.utcnow() - last_onchain).total_seconds() / 60 >= CRAWL_INTERVAL_MINUTES):
            _running.add(name_onchain)
            task = asyncio.create_task(_run_onchain_snapshot(name_onchain))
            _active_tasks[name_onchain] = task


async def _run_with_timeout(source: dict):
    """用 asyncio.wait_for 包装单源爬取，超时自动取消"""
    name = source["name"]
    try:
        await asyncio.wait_for(
            _run_one_source(source),
            timeout=TASK_TIMEOUT_SECONDS
        )
    except asyncio.TimeoutError:
        logger.error(f"[Crawler] {name} TIMEOUT after {TASK_TIMEOUT_SECONDS}s — force cancelled")
        _running.discard(name)
        _active_tasks.pop(name, None)


def _cleanup_finished_tasks():
    """清理已完成的 task 引用"""
    done = [name for name, task in _active_tasks.items() if task.done()]
    for name in done:
        task = _active_tasks.pop(name)
        _running.discard(name)
        # 获取并打 log 未处理的异常
        if task.exception():
            logger.error(f"[Crawler] Task {name} had unhandled exception: {task.exception()}")


async def _run_onchain_snapshot(name: str):
    """单独执行 etf_onchain_collector 快照任务"""
    from data_collectors.etf_onchain_collector import etf_onchain_collector
    try:
        logger.info(f"[Crawler] Triggering background task for {name}")
        await asyncio.wait_for(
            etf_onchain_collector.save_history_to_db(),
            timeout=120  # onchain snapshot 最大 2 分钟
        )
        _last_run[name] = datetime.utcnow()
    except asyncio.TimeoutError:
        logger.error(f"[Crawler] {name} TIMEOUT")
    except Exception as e:
        logger.error(f"[Crawler] Snapshot failed for {name}: {e}")
    finally:
        _running.discard(name)
        _active_tasks.pop(name, None)


async def shutdown_browser_pool():
    """应用关闭时调用，释放浏览器"""
    await _browser_pool.close()


__all__ = ["check_and_run_crawlers", "shutdown_browser_pool"]
