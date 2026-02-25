
import asyncio
import logging
from core.database import init_db, AsyncSessionLocal
from models.crawler import CrawlSource
from crawler.core import crawler_engine
from crawler.spiders import get_spider_class

logging.basicConfig(level=logging.INFO)

async def test_crawler():
    await init_db()
    
    async with AsyncSessionLocal() as db:
        # Create test source
        source = CrawlSource(
            name="Farside BTC Test",
            url="https://farside.co.uk/bitcoin-etf-flow-all-data/",
            spider_type="farside",
            is_active=1
        )
        db.add(source)
        try:
            await db.commit()
            print(f"Created source ID: {source.id}")
            
            # Run
            await crawler_engine.run_spider(source.id)
            
        except Exception as e:
            print(f"Error: {e}")
            await db.rollback()
        finally:
            # Clean up?
            pass
            
    await crawler_engine.stop()

if __name__ == "__main__":
    asyncio.run(test_crawler())
