"""
Database Connection Manager
"""
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

from config import DATABASE_URL, DATABASE_PATH
from models import Base


# 创建异步引擎
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"timeout": 15}
)

from sqlalchemy import event

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()

# 创建会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def init_db():
    """初始化数据库，创建所有表"""
    # 确保数据目录存在
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    print(f"✅ Database initialized: {DATABASE_PATH}")


async def drop_db():
    """删除所有表（慎用）"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    print("⚠️ All tables dropped")


@asynccontextmanager
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """获取数据库会话（上下文管理器）"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def get_session() -> AsyncSession:
    """获取数据库会话（直接返回）"""
    return AsyncSessionLocal()


# 同步初始化辅助函数
def init_db_sync():
    """同步方式初始化数据库"""
    async def _init_and_dispose():
        await init_db()
        await engine.dispose()
        
    asyncio.run(_init_and_dispose())


if __name__ == "__main__":
    # 直接运行此文件可初始化数据库
    init_db_sync()
