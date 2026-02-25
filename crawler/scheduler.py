import asyncio
import logging
from datetime import datetime
from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.crawler import CrawlSource
from crawler.core import crawler_engine

logger = logging.getLogger(__name__)

# Track running crawl tasks to avoid duplicate runs
_running_tasks: dict = {}

async def _run_spider_bg(source_id: int, source_name: str):
    """Run spider in background, with cleanup on finish."""
    try:
        await crawler_engine.run_spider(source_id)
    except Exception as e:
        logger.error(f"Background crawl failed for {source_name}: {e}")
    finally:
        _running_tasks.pop(source_id, None)
        logger.info(f"Background crawl finished for {source_name}")

async def check_and_run_crawlers():
    """
    Periodic task to check if any crawler source needs to run.
    Spiders are launched as background tasks so they never block the event loop.
    """
    logger.debug("Checking crawler schedules...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CrawlSource).where(CrawlSource.is_active == 1))
        sources = result.scalars().all()

        for source in sources:
            # Skip if this source is already running
            if source.id in _running_tasks:
                logger.debug(f"Crawl already running for {source.name}, skipping")
                continue

            should_run = False
            if not source.last_run_at:
                should_run = True
            else:
                elapsed_minutes = (datetime.utcnow() - source.last_run_at).total_seconds() / 60
                if elapsed_minutes >= source.schedule_interval:
                    should_run = True

            if should_run:
                logger.info(f"Triggering background crawl for {source.name}")
                # Fire-and-forget: does NOT block the scheduler or FastAPI event loop
                task = asyncio.create_task(_run_spider_bg(source.id, source.name))
                _running_tasks[source.id] = task

# Export for scheduler to use
__all__ = ["check_and_run_crawlers"]

