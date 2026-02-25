"""
ETF 爬虫定时调度器（硬编码版）

三个固定数据源，不依赖数据库 CrawlSource 表。
爬虫结果仍然写入 crawled_data 表供页面展示。
"""
import asyncio
import logging
from datetime import datetime
from playwright.async_api import async_playwright

from core.database import AsyncSessionLocal
from models.crawler import CrawledData
from crawler.spiders import get_spider_class

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
_last_run: dict[str, datetime] = {}
_running: set[str] = set()
CRAWL_INTERVAL_MINUTES = 60  # 每 1 小时


async def _run_one_source(source: dict):
    """对一个数据源执行爬虫，结果写入 crawled_data 表"""
    name = source["name"]
    if name in _running:
        logger.debug(f"Crawl already running for {name}, skipping")
        return

    _running.add(name)
    playwright_inst = None
    browser = None

    try:
        spider_cls = get_spider_class(source["spider_type"])
        if not spider_cls:
            logger.error(f"Spider type '{source['spider_type']}' not found")
            return

        # 启动浏览器
        playwright_inst = await async_playwright().start()
        browser = await playwright_inst.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        logger.info(f"Starting crawl for {name} ({source['url']})")
        spider = spider_cls(source["url"])
        results = await spider.crawl(page)

        # 写入数据库（单独 session，快速 commit）
        async with AsyncSessionLocal() as db:
            count = 0
            for item in results:
                db.add(CrawledData(
                    source_id=None,  # 硬编码模式不关联 CrawlSource
                    task_id=None,
                    data_type=item.get("type"),
                    date=item.get("date"),
                    value=item.get("value"),
                    raw_content=str(item),
                ))
                count += 1
            await db.commit()

        _last_run[name] = datetime.utcnow()
        logger.info(f"Crawl finished for {name}: {count} items saved")

    except Exception as e:
        logger.error(f"Crawl failed for {name}: {e}", exc_info=True)

    finally:
        _running.discard(name)
        try:
            if browser:
                await browser.close()
            if playwright_inst:
                await playwright_inst.stop()
        except Exception:
            pass


async def check_and_run_crawlers():
    """
    APScheduler 定时任务入口。

    检查每个硬编码数据源是否到了应该爬取的时间，
    到了就用 create_task 后台启动，不阻塞调度器。
    """
    for source in HARDCODED_SOURCES:
        name = source["name"]

        if name in _running:
            continue

        last = _last_run.get(name)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds() / 60
            if elapsed < CRAWL_INTERVAL_MINUTES:
                continue

        logger.info(f"Triggering background crawl for {name}")
        asyncio.create_task(_run_one_source(source))


__all__ = ["check_and_run_crawlers"]
