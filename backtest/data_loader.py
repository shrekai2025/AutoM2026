"""
回测数据加载器 (Phase 2A)

职责:
1. 从 Binance API 加载历史 K 线
2. 自动缓存到 kline_cache 表 (避免重复请求)
3. 支持大范围数据分批加载 (Binance 单次最多 1000 条)
"""
import logging
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal

import aiohttp

from config import BINANCE_API_URL

logger = logging.getLogger(__name__)

# 各时间框架对应的毫秒间隔
INTERVAL_MS = {
    "1m": 60_000,
    "3m": 180_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "2h": 7_200_000,
    "4h": 14_400_000,
    "6h": 21_600_000,
    "8h": 28_800_000,
    "12h": 43_200_000,
    "1d": 86_400_000,
    "3d": 259_200_000,
    "1w": 604_800_000,
}


class BacktestDataLoader:
    """回测数据加载器"""

    def __init__(self, base_url: str = BINANCE_API_URL):
        self.base_url = base_url

    async def load(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        start_date: str = "2024-01-01",
        end_date: str = "2024-12-31",
        use_cache: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        加载历史 K 线数据

        Args:
            symbol: 交易对 (如 "BTCUSDT")
            interval: 时间框架 (如 "1h", "4h", "1d")
            start_date: 开始日期 "YYYY-MM-DD"
            end_date: 结束日期 "YYYY-MM-DD"
            use_cache: 是否使用/写入 kline_cache 表

        Returns:
            K 线列表 (按时间升序)
        """
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)  # 包含结束日

        start_ms = int(start_dt.timestamp() * 1000)
        end_ms = int(end_dt.timestamp() * 1000)

        # 尝试从缓存加载
        if use_cache:
            cached = await self._load_from_cache(symbol, interval, start_ms, end_ms)
            if cached:
                logger.info(
                    f"Loaded {len(cached)} klines from cache: "
                    f"{symbol} {interval} {start_date}~{end_date}"
                )
                return cached

        # 从 Binance API 分批加载
        klines = await self._fetch_from_binance(symbol, interval, start_ms, end_ms)

        # 写入缓存
        if use_cache and klines:
            await self._save_to_cache(symbol, interval, klines)

        logger.info(
            f"Loaded {len(klines)} klines from Binance: "
            f"{symbol} {interval} {start_date}~{end_date}"
        )
        return klines

    async def _fetch_from_binance(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> List[Dict[str, Any]]:
        """从 Binance API 分批加载 (每批最多 1000 条)"""
        all_klines = []
        current_start = start_ms
        batch_limit = 1000

        async with aiohttp.ClientSession() as session:
            while current_start < end_ms:
                url = f"{self.base_url}/api/v3/klines"
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_start,
                    "endTime": end_ms,
                    "limit": batch_limit,
                }

                try:
                    async with session.get(url, params=params) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if not data:
                                break

                            for k in data:
                                all_klines.append({
                                    "open_time": int(k[0]),
                                    "open": float(k[1]),
                                    "high": float(k[2]),
                                    "low": float(k[3]),
                                    "close": float(k[4]),
                                    "volume": float(k[5]),
                                    "close_time": int(k[6]),
                                    "quote_volume": float(k[7]),
                                    "trades": int(k[8]),
                                })

                            # 下一批的起始 = 最后一条的 close_time + 1
                            last_close = int(data[-1][6])
                            current_start = last_close + 1

                            # 如果返回数量 < limit，说明已到末尾
                            if len(data) < batch_limit:
                                break
                        elif resp.status == 429:
                            # Rate limit，等待后重试
                            logger.warning("Binance rate limit hit, waiting 10s...")
                            await asyncio.sleep(10)
                        else:
                            logger.error(f"Binance API error: {resp.status}")
                            break

                except Exception as e:
                    logger.error(f"Fetch klines failed: {e}")
                    break

                # 礼貌延迟，避免触发限流
                await asyncio.sleep(0.2)

        return all_klines

    async def _load_from_cache(
        self,
        symbol: str,
        interval: str,
        start_ms: int,
        end_ms: int,
    ) -> Optional[List[Dict[str, Any]]]:
        """从 kline_cache 表加载"""
        try:
            from core.database import AsyncSessionLocal
            from models import KlineCache
            from sqlalchemy import select, and_

            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(KlineCache)
                    .where(
                        and_(
                            KlineCache.symbol == symbol,
                            KlineCache.interval == interval,
                            KlineCache.open_time >= start_ms,
                            KlineCache.open_time < end_ms,
                        )
                    )
                    .order_by(KlineCache.open_time)
                )
                rows = result.scalars().all()

                if not rows:
                    return None

                # 检查覆盖率: 缓存的条数应 >= 预期的 80%
                interval_ms = INTERVAL_MS.get(interval, 3_600_000)
                expected = (end_ms - start_ms) / interval_ms
                if len(rows) < expected * 0.8:
                    logger.info(
                        f"Cache incomplete: {len(rows)}/{expected:.0f}, "
                        f"refetching from API"
                    )
                    return None

                return [r.to_dict() for r in rows]

        except Exception as e:
            logger.warning(f"Cache load failed: {e}")
            return None

    async def _save_to_cache(
        self,
        symbol: str,
        interval: str,
        klines: List[Dict[str, Any]],
    ):
        """写入 kline_cache 表"""
        try:
            from core.database import AsyncSessionLocal
            from models import KlineCache
            from sqlalchemy.dialects.sqlite import insert

            async with AsyncSessionLocal() as db:
                for k in klines:
                    # INSERT OR IGNORE (利用唯一索引去重)
                    stmt = insert(KlineCache).values(
                        symbol=symbol,
                        interval=interval,
                        open_time=k["open_time"],
                        close_time=k["close_time"],
                        open=Decimal(str(k["open"])),
                        high=Decimal(str(k["high"])),
                        low=Decimal(str(k["low"])),
                        close=Decimal(str(k["close"])),
                        volume=Decimal(str(k["volume"])),
                    ).on_conflict_do_nothing()
                    await db.execute(stmt)

                await db.commit()
                logger.info(f"Cached {len(klines)} klines: {symbol} {interval}")

        except Exception as e:
            logger.warning(f"Cache save failed: {e}")
