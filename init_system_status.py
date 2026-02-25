#!/usr/bin/env python3
"""
初始化系统状态监控

创建 API 状态记录并进行首次健康检查
"""
import asyncio
import sys
import os
from datetime import datetime
import time

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import init_db, AsyncSessionLocal
from models.system import ApiStatus
from sqlalchemy import select


async def check_binance_api():
    """检查 Binance API"""
    try:
        import aiohttp
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.binance.com/api/v3/ping', timeout=5) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return 'online', latency, 'API 响应正常'
                else:
                    return 'error', latency, f'HTTP {resp.status}'
    except Exception as e:
        return 'error', 0, str(e)


async def check_fred_api():
    """检查 FRED API"""
    try:
        from config import FRED_API_KEY
        if not FRED_API_KEY or FRED_API_KEY == 'your_fred_api_key_here':
            return 'error', 0, '未配置 API Key'

        import aiohttp
        start = time.time()
        url = f'https://api.stlouisfed.org/fred/series?series_id=DGS10&api_key={FRED_API_KEY}&file_type=json'
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return 'online', latency, 'API 响应正常'
                else:
                    return 'error', latency, f'HTTP {resp.status}'
    except Exception as e:
        return 'error', 0, str(e)


async def check_alternative_me():
    """检查 Alternative.me Fear & Greed Index"""
    try:
        import aiohttp
        start = time.time()
        async with aiohttp.ClientSession() as session:
            async with session.get('https://api.alternative.me/fng/', timeout=5) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return 'online', latency, 'API 响应正常'
                else:
                    return 'error', latency, f'HTTP {resp.status}'
    except Exception as e:
        return 'error', 0, str(e)


async def check_openrouter_api():
    """检查 OpenRouter API"""
    try:
        from config import OPENROUTER_API_KEY, LLM_ENABLED

        if not LLM_ENABLED:
            return 'online', 0, 'LLM 功能已禁用'

        if not OPENROUTER_API_KEY or OPENROUTER_API_KEY == 'your_openrouter_api_key_here':
            return 'error', 0, '未配置 API Key'

        import aiohttp
        start = time.time()
        headers = {'Authorization': f'Bearer {OPENROUTER_API_KEY}'}
        async with aiohttp.ClientSession() as session:
            async with session.get('https://openrouter.ai/api/v1/models', headers=headers, timeout=5) as resp:
                latency = int((time.time() - start) * 1000)
                if resp.status == 200:
                    return 'online', latency, 'API 响应正常'
                else:
                    return 'error', latency, f'HTTP {resp.status}'
    except Exception as e:
        return 'error', 0, str(e)


async def update_api_status(db, name: str, type_: str, status: str, latency: int, message: str):
    """更新或创建 API 状态记录"""
    result = await db.execute(select(ApiStatus).where(ApiStatus.name == name))
    api_status = result.scalar_one_or_none()

    if api_status:
        # 更新现有记录
        api_status.status = status
        api_status.latency_ms = latency
        api_status.message = message
        api_status.last_check = datetime.utcnow()

        if status == 'online':
            api_status.success_count_24h += 1
        else:
            api_status.error_count_24h += 1
    else:
        # 创建新记录
        api_status = ApiStatus(
            name=name,
            type=type_,
            status=status,
            latency_ms=latency,
            message=message,
            last_check=datetime.utcnow(),
            success_count_24h=1 if status == 'online' else 0,
            error_count_24h=0 if status == 'online' else 1
        )
        db.add(api_status)

    await db.commit()


async def init_system_status():
    """初始化系统状态监控"""
    print("=" * 60)
    print("初始化系统状态监控")
    print("=" * 60)
    print()

    # 初始化数据库
    await init_db()

    async with AsyncSessionLocal() as db:
        # 检查各个 API
        checks = [
            ("Binance API", "REST", check_binance_api),
            ("FRED API", "REST", check_fred_api),
            ("Fear & Greed Index", "REST", check_alternative_me),
            ("OpenRouter API", "LLM", check_openrouter_api),
        ]

        for name, type_, check_func in checks:
            print(f"检查 {name}...", end=" ")
            status, latency, message = await check_func()

            await update_api_status(db, name, type_, status, latency, message)

            if status == 'online':
                print(f"✓ 正常 ({latency}ms)")
            else:
                print(f"✗ 错误: {message}")

    print()
    print("=" * 60)
    print("初始化完成！")
    print()
    print("访问 http://your-server-ip:8080/system/status 查看系统状态")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(init_system_status())
