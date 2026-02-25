import logging
import asyncio
from typing import Optional, Type
from datetime import datetime
from playwright.async_api import async_playwright, Browser, Page

from core.database import AsyncSessionLocal
from models.crawler import CrawlSource, CrawlTask, CrawledData

logger = logging.getLogger(__name__)

class CrawlerEngine:
    """
    Core engine to manage browser lifecycle and spider execution
    """
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._playwright = None
        
    async def start(self):
        """Initialize Playwright browser"""
        if not self._playwright:
            self._playwright = await async_playwright().start()
            # Launch in headless mode, but with arguments to mimic real user
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox"]
            )
            logger.info("Crawler Engine started")

    async def stop(self):
        """Close browser resources"""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        logger.info("Crawler Engine stopped")

    async def run_spider(self, source_id: int):
        """
        Execute a spider for a given source
        """
        from crawler.spiders import get_spider_class
        
        async with AsyncSessionLocal() as db:
            # 1. Fetch Source
            source = await db.get(CrawlSource, source_id)
            if not source or not source.is_active:
                logger.warning(f"Source {source_id} not found or inactive")
                return

            # 2. Get Spider Class
            spider_cls = get_spider_class(source.spider_type)
            if not spider_cls:
                logger.error(f"Spider type {source.spider_type} not found")
                return

            # 3. Create Task Record
            task = CrawlTask(source_id=source.id, status="running")
            db.add(task)
            await db.commit()
            
            try:
                # 4. Initialize Resources
                if not self._browser:
                    await self.start()
                
                context = await self._browser.new_context(
                    user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 800}
                )
                page = await context.new_page()
                
                # 5. Run Spider
                logger.info(f"Starting crawl for {source.name} ({source.url})")
                spider = spider_cls(source.url)
                results = await spider.crawl(page)
                
                # 6. Save Results
                count = 0
                for item in results:
                    data = CrawledData(
                        source_id=source.id,
                        task_id=task.id,
                        data_type=item.get("type"),
                        date=item.get("date"),
                        value=item.get("value"),
                        raw_content=str(item)
                    )
                    db.add(data)
                    count += 1
                
                # Update Task
                task.status = "completed"
                task.end_time = datetime.utcnow()
                task.items_count = count
                
                # Update Source
                source.last_run_at = datetime.utcnow()
                
                logger.info(f"Crawl finished for {source.name}: {count} items")

            except Exception as e:
                logger.error(f"Crawl failed for {source.name}: {e}")
                task.status = "failed"
                task.end_time = datetime.utcnow()
                task.error_log = str(e)
            
            finally:
                if 'context' in locals():
                    await context.close()
                await db.commit()

# Global Instance
crawler_engine = CrawlerEngine()
