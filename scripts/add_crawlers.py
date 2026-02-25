import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.database import AsyncSessionLocal, init_db
from models.crawler import CrawlSource
from sqlalchemy import select

async def add_sources():
    await init_db()
    
    sources = [
        {
            "name": "Farside ETH ETF",
            "url": "https://farside.co.uk/eth/",
            "spider_type": "farside",
            "interval": 360
        },
        {
            "name": "Farside SOL ETF",
            "url": "https://farside.co.uk/sol/",
            "spider_type": "farside",
            "interval": 360
        }
    ]
    
    async with AsyncSessionLocal() as db:
        for s in sources:
            # Check if exists
            result = await db.execute(select(CrawlSource).where(CrawlSource.name == s["name"]))
            existing = result.scalar_one_or_none()
            
            if not existing:
                print(f"Adding {s['name']}...")
                new_source = CrawlSource(
                    name=s["name"],
                    url=s["url"],
                    spider_type=s["spider_type"],
                    schedule_interval=s["interval"],
                    is_active=1
                )
                db.add(new_source)
            else:
                print(f"Source {s['name']} already exists.")
        
        await db.commit()
    print("Done.")

if __name__ == "__main__":
    asyncio.run(add_sources())
