import logging
from datetime import datetime
from sqlalchemy import select

from core.database import AsyncSessionLocal
from models.crawler import CrawlSource
from crawler.core import crawler_engine

logger = logging.getLogger(__name__)

async def check_and_run_crawlers():
    """
    Periodic task to check if any crawler source needs to run
    """
    logger.debug("Checking crawler schedules...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(CrawlSource).where(CrawlSource.is_active == 1))
        sources = result.scalars().all()
        
        for source in sources:
            should_run = False
            if not source.last_run_at:
                should_run = True
            else:
                # Check interval
                elapsed_minutes = (datetime.utcnow() - source.last_run_at).total_seconds() / 60
                if elapsed_minutes >= source.schedule_interval:
                    should_run = True
            
            if should_run:
                logger.info(f"Triggering scheduled crawl for {source.name}")
                # We can run this in background or await it? 
                # Await might block scheduler, better to fire task.
                # Since crawler_engine.run_spider is async, we can await it here if we want sequential execution,
                # or better, use asyncio.create_task if we want parallel.
                # For safety, let's await to avoid overwhelming resources
                await crawler_engine.run_spider(source.id)

# Export for scheduler to use
__all__ = ["check_and_run_crawlers"]
