import asyncio
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from core.database import AsyncSessionLocal

async def migrate():
    print("Starting migration: Adding is_starred to market_watch...")
    
    async with AsyncSessionLocal() as db:
        try:
            # Check if column exists
            result = await db.execute(text("PRAGMA table_info(market_watch)"))
            columns = [row[1] for row in result.fetchall()]
            
            if "is_starred" in columns:
                print("Column 'is_starred' already exists. Skipping.")
                return

            # Add column
            print("Adding column 'is_starred'...")
            # SQLite doesn't support adding column with default value properly for boolean without constraints sometimes, 
            # but usually works. integer 0/1 for boolean.
            await db.execute(text("ALTER TABLE market_watch ADD COLUMN is_starred BOOLEAN DEFAULT 0"))
            await db.commit()
            print("Migration successful!")
            
        except Exception as e:
            print(f"Migration failed: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(migrate())
