
import asyncio
import sys
import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Ensure we can import from parent directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import DATABASE_URL

async def migrate():
    print(f"Connecting to database: {DATABASE_URL}")
    engine = create_async_engine(DATABASE_URL)
    
    async with engine.begin() as conn:
        try:
            print("Checking if column 'schedule_minutes' exists in 'strategies'...")
            # Check if column exists - SQLite specific check
            result = await conn.execute(text("PRAGMA table_info(strategies)"))
            columns = result.fetchall()
            column_names = [col[1] for col in columns]
            
            if 'schedule_minutes' not in column_names:
                print("Adding 'schedule_minutes' column to 'strategies' table...")
                await conn.execute(text("ALTER TABLE strategies ADD COLUMN schedule_minutes INTEGER NOT NULL DEFAULT 5"))
                print("✅ Migration successful: Column 'schedule_minutes' added.")
            else:
                print("ℹ️ Column 'schedule_minutes' already exists. Skipping.")
                
        except Exception as e:
            print(f"❌ Migration failed: {e}")
            raise
    
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(migrate())
