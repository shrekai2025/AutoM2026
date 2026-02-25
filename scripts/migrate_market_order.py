import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from core.database import AsyncSessionLocal, init_db

async def migrate():
    print("Starting migration: Adding display_order to market_watch...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Check if column exists
            # SQLite specific check
            result = await db.execute(text("PRAGMA table_info(market_watch)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "display_order" in columns:
                print("Column 'display_order' already exists. Skipping.")
                return

            # Add column
            print("Adding column 'display_order'...")
            await db.execute(text("ALTER TABLE market_watch ADD COLUMN display_order INTEGER DEFAULT 0"))
            await db.commit()
            print("Migration successful!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(migrate())
