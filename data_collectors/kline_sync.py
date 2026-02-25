"""
K 线历史全量同步服务 (KlineSyncService)

功能:
- 支持任意 Binance 交易对 + 时间框架
- 首次使用时自动全量回填历史数据
- 之后每次只同步缺失的最新 K 线（增量更新）
- 数据写入 kline_cache 表，长期保存，供回测和 TA 使用

限频策略 (Binance 公开 API = 1200 weight/min，每次 klines 请求 = 2 weight):
- Token Bucket：最多 10 req/s（600/min），留出安全裕量
- 全局 Semaphore：最多 3 个并发请求，防止多 symbol 同时回填时爆发
- 批次间强制等待：回填时每批 1000 条后 sleep 300ms
- sync_all_watched 严格串行：不并发，逐 symbol 逐 timeframe 顺序执行
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional

import time
import aiohttp
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from config import BINANCE_API_URL
from models.kline_cache import KlineCache

# Binance 数据镜像 API（绕过地区限制，专用于 K线历史数据拉取）
# https://data-api.binance.vision 是 Binance 官方提供的公开数据节点
BINANCE_KLINE_API_URL = "https://data-api.binance.vision"


class RateLimiter:
    """
    Token Bucket 速率限制器

    允许短暂突发，但长期维持在 max_rate 以内。
    Binance 公开 API: 1200 weight/min，klines = 2 weight/req
    安全上限: 500 req/min = ~8.3 req/s → 设 max_rate=8
    """

    def __init__(self, max_rate: float = 8.0, burst: int = 12):
        """
        Args:
            max_rate: 每秒最大请求数（令牌生成速率）
            burst:    令牌桶最大容量（允许的瞬时突发量）
        """
        self.max_rate = max_rate
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """等待直到获得一个令牌（阻塞直到速率允许）"""
        async with self._lock:
            while True:
                now = time.monotonic()
                elapsed = now - self._last_refill
                # 补充令牌
                self._tokens = min(
                    self.burst,
                    self._tokens + elapsed * self.max_rate
                )
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                else:
                    # 计算需要等多久才能获得下一个令牌
                    wait = (1.0 - self._tokens) / self.max_rate
                    await asyncio.sleep(wait)


# ─── 全局限速实例 ───────────────────────────────────────────
# max_rate=8: 每秒最多 8 个 klines 请求（约 480 weight/min，安全裕量 60%）
_rate_limiter = RateLimiter(max_rate=8.0, burst=12)

# 最大并发请求数：防止多 symbol 同时触发回填时并发爆发
_semaphore = asyncio.Semaphore(3)

logger = logging.getLogger(__name__)

# 支持的时间框架及对应毫秒数（用于回填计算）
TIMEFRAME_MS: Dict[str, int] = {
    "1m":  60_000,
    "5m":  300_000,
    "15m": 900_000,
    "1h":  3_600_000,
    "4h":  14_400_000,
    "1d":  86_400_000,
}

# 各时间框架默认全量回填条数（首次同步）
INITIAL_LOOKBACK: Dict[str, int] = {
    "1m":  1440,   # 1 天
    "5m":  2016,   # 7 天
    "15m": 2016,   # 21 天
    "1h":  2000,   # 83 天
    "4h":  2000,   # 333 天（约 11 个月）
    "1d":  1095,   # 3 年
}

BINANCE_MAX_LIMIT = 1000  # Binance 单次最多返回 1000 条


class KlineSyncService:
    """K 线全量历史同步服务"""

    def __init__(self):
        # 优先使用 Binance 数据镜像 API（绕过部分地区访问限制）
        self.base_url = BINANCE_KLINE_API_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    # ─────────────────────────────────────────────
    #  Binance 原始数据拉取
    # ─────────────────────────────────────────────

    async def _fetch_klines_raw(
        self,
        symbol: str,
        interval: str,
        start_time_ms: Optional[int] = None,
        end_time_ms: Optional[int] = None,
        limit: int = 1000,
    ) -> List[List]:
        """
        从 Binance 拉取原始 K 线数据（含限速保护）

        限速: 经过全局 Semaphore（最多 3 并发）+ Token Bucket（最多 8 req/s）
        对 429 响应自动退避重试（最多 3 次）
        
        Returns:
            Binance 原始列表，每项为 [open_time, open, high, low, close, volume, ...]
        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v3/klines"

        params: Dict[str, Any] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, BINANCE_MAX_LIMIT),
        }
        if start_time_ms:
            params["startTime"] = start_time_ms
        if end_time_ms:
            params["endTime"] = end_time_ms

        max_retries = 3
        retry_wait = 2.0  # 初始退避秒数

        for attempt in range(max_retries):
            # 1. 先通过速率限制器获得令牌
            await _rate_limiter.acquire()

            # 2. 全局并发信号量
            async with _semaphore:
                try:
                    async with session.get(
                        url,
                        params=params,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as resp:
                        if resp.status == 200:
                            return await resp.json()
                        elif resp.status == 429:
                            # Rate limited by Binance
                            retry_after = int(resp.headers.get("Retry-After", retry_wait))
                            logger.warning(
                                f"[KlineSync] 429 Rate Limited for {symbol}/{interval}, "
                                f"waiting {retry_after}s (attempt {attempt+1}/{max_retries})"
                            )
                            await asyncio.sleep(retry_after)
                            retry_wait *= 2  # 指数退避
                            continue
                        elif resp.status == 418:
                            # IP banned
                            logger.error(f"[KlineSync] 418 IP banned! Stopping for {symbol}/{interval}")
                            return []
                        else:
                            body = await resp.text()
                            logger.error(
                                f"[KlineSync] Binance error {resp.status} for {symbol}/{interval}: {body[:200]}"
                            )
                            return []
                except asyncio.TimeoutError:
                    logger.error(f"[KlineSync] Timeout fetching {symbol}/{interval} (attempt {attempt+1})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_wait)
                        retry_wait *= 2
                    continue
                except Exception as e:
                    logger.error(f"[KlineSync] Failed to fetch {symbol}/{interval}: {e}")
                    return []

        logger.error(f"[KlineSync] Exhausted retries for {symbol}/{interval}")
        return []

    def _raw_to_model(self, symbol: str, interval: str, raw: List) -> KlineCache:
        """将 Binance 原始 K 线转为 ORM 对象"""
        return KlineCache(
            symbol=symbol,
            interval=interval,
            open_time=int(raw[0]),
            close_time=int(raw[6]),
            open=raw[1],
            high=raw[2],
            low=raw[3],
            close=raw[4],
            volume=raw[5],
        )

    # ─────────────────────────────────────────────
    #  数据库 Upsert
    # ─────────────────────────────────────────────

    async def _upsert_klines(
        self,
        db: AsyncSession,
        symbol: str,
        interval: str,
        raw_list: List[List],
        skip_last: bool = True,
    ) -> int:
        """
        将原始 K 线 upsert 到数据库

        Args:
            skip_last: 跳过最后一根（未闭合的当前 K 线）
            
        Returns:
            写入条数
        """
        if not raw_list:
            return 0

        data = raw_list[:-1] if skip_last and len(raw_list) > 1 else raw_list

        rows = [
            {
                "symbol": symbol,
                "interval": interval,
                "open_time": int(row[0]),
                "close_time": int(row[6]),
                "open": row[1],
                "high": row[2],
                "low": row[3],
                "close": row[4],
                "volume": row[5],
                "created_at": datetime.utcnow(),
            }
            for row in data
        ]

        if not rows:
            return 0

        # SQLite upsert: INSERT OR IGNORE（unique constraint 保证幂等）
        stmt = sqlite_insert(KlineCache).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["symbol", "interval", "open_time"]
        )

        await db.execute(stmt)
        await db.commit()

        return len(rows)

    # ─────────────────────────────────────────────
    #  获取数据库中最新时间戳
    # ─────────────────────────────────────────────

    async def _get_latest_open_time(
        self, db: AsyncSession, symbol: str, interval: str
    ) -> Optional[int]:
        """获取数据库中该 symbol/interval 的最新 open_time（毫秒）"""
        result = await db.execute(
            select(func.max(KlineCache.open_time))
            .where(KlineCache.symbol == symbol)
            .where(KlineCache.interval == interval)
        )
        return result.scalar_one_or_none()

    async def _get_earliest_open_time(
        self, db: AsyncSession, symbol: str, interval: str
    ) -> Optional[int]:
        """获取数据库中该 symbol/interval 的最早 open_time（毫秒）"""
        result = await db.execute(
            select(func.min(KlineCache.open_time))
            .where(KlineCache.symbol == symbol)
            .where(KlineCache.interval == interval)
        )
        return result.scalar_one_or_none()

    # ─────────────────────────────────────────────
    #  全量回填（首次使用）
    # ─────────────────────────────────────────────

    async def backfill(
        self,
        db: AsyncSession,
        symbol: str,
        interval: str,
        lookback_bars: Optional[int] = None,
    ) -> int:
        """
        全量历史回填
        
        策略：从现在往回推 lookback_bars 条，分批拉取（每批 1000 条）

        Returns:
            总写入条数
        """
        tf_ms = TIMEFRAME_MS.get(interval, 3_600_000)
        max_bars = lookback_bars or INITIAL_LOOKBACK.get(interval, 2000)

        total_inserted = 0
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # 计算回填起始时间
        start_ms = now_ms - max_bars * tf_ms

        logger.info(
            f"[KlineSync] Backfilling {symbol}/{interval}: up to {max_bars} bars "
            f"from {datetime.fromtimestamp(start_ms/1000, tz=timezone.utc)}"
        )

        current_start = start_ms
        batch_num = 0

        while current_start < now_ms:
            batch_num += 1
            raw = await self._fetch_klines_raw(
                symbol=symbol,
                interval=interval,
                start_time_ms=current_start,
                limit=BINANCE_MAX_LIMIT,
            )

            if not raw:
                break

            inserted = await self._upsert_klines(db, symbol, interval, raw, skip_last=False)
            total_inserted += inserted

            # 下批从最后一根的 close_time + 1ms 开始
            last_close_time = int(raw[-1][6])
            current_start = last_close_time + 1

            logger.debug(
                f"[KlineSync] Backfill batch #{batch_num}: {symbol}/{interval} "
                f"+{inserted} bars, total={total_inserted}"
            )

            if len(raw) < BINANCE_MAX_LIMIT:
                # 数据已拉完
                break

            # ⚠️ 批次间强制等待 300ms，防止回填多 symbol/timeframe 时超频
            # Rate Limiter 已处理每请求节奏，这里额外加保守等待
            await asyncio.sleep(0.3)

        logger.info(f"[KlineSync] Backfill complete: {symbol}/{interval} → {total_inserted} bars in {batch_num} batch(es)")
        return total_inserted

    # ─────────────────────────────────────────────
    #  增量更新（定时同步）
    # ─────────────────────────────────────────────

    async def sync_incremental(
        self,
        db: AsyncSession,
        symbol: str,
        interval: str,
    ) -> int:
        """
        增量同步：从数据库最新时间戳到现在的缺失 K 线

        Returns:
            写入条数
        """
        latest_ms = await self._get_latest_open_time(db, symbol, interval)

        if latest_ms is None:
            # 首次同步，进行全量回填
            logger.info(f"[KlineSync] No data for {symbol}/{interval}, triggering backfill")
            return await self.backfill(db, symbol, interval)

        # 有历史数据，只取新的
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        raw = await self._fetch_klines_raw(
            symbol=symbol,
            interval=interval,
            start_time_ms=latest_ms + 1,  # +1 避免重复最后一根
            limit=BINANCE_MAX_LIMIT,
        )

        if not raw:
            return 0

        inserted = await self._upsert_klines(db, symbol, interval, raw, skip_last=True)
        if inserted > 0:
            logger.debug(f"[KlineSync] Incremental sync {symbol}/{interval}: +{inserted} bars")

        return inserted

    # ─────────────────────────────────────────────
    #  主调接口：同步并读取
    # ─────────────────────────────────────────────

    async def get_klines(
        self,
        db: AsyncSession,
        symbol: str,
        interval: str,
        limit: int = 500,
        sync_first: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        获取 K 线数据（先同步，后从本地读取）

        Args:
            symbol:     交易对，e.g. "BTCUSDT"
            interval:   时间框架，e.g. "1h"
            limit:      返回条数（最新 N 根）
            sync_first: 是否先进行增量同步

        Returns:
            K 线列表（时间正序），格式兼容现有 indicator_calculator.calculate_all()
        """
        if sync_first:
            try:
                await self.sync_incremental(db, symbol, interval)
            except Exception as e:
                logger.error(f"[KlineSync] Incremental sync error for {symbol}/{interval}: {e}")

        # 从本地数据库读取最新 N 根
        result = await db.execute(
            select(KlineCache)
            .where(KlineCache.symbol == symbol)
            .where(KlineCache.interval == interval)
            .order_by(desc(KlineCache.open_time))
            .limit(limit)
        )
        rows = result.scalars().all()

        if not rows:
            logger.warning(f"[KlineSync] No local data for {symbol}/{interval} after sync")
            return []

        # 反转为时间正序（旧 → 新）
        rows = list(reversed(rows))

        return [row.to_dict() for row in rows]

    async def get_multi_timeframe_klines(
        self,
        db: AsyncSession,
        symbol: str,
        timeframes: List[str],
        limit: int = 500,
        sync_first: bool = True,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        串行获取多时间框架 K 线（不并发）

        \u26a0\ufe0f SQLite 异步不支持单个 session 并发写入。
        必须串行执行，避免 asyncio.gather 并发共享 session 导致事务冲突。

        Returns:
            {"1h": [...], "4h": [...], "1d": [...]}
        """
        output: Dict[str, List[Dict[str, Any]]] = {}

        for tf in timeframes:
            try:
                klines = await self.get_klines(
                    db=db,
                    symbol=symbol,
                    interval=tf,
                    limit=limit,
                    sync_first=sync_first,
                )
                output[tf] = klines
            except Exception as e:
                logger.error(f"[KlineSync] Failed to get {symbol}/{tf}: {e}")
                output[tf] = []

        return output

    # ─────────────────────────────────────────────
    #  批量同步多 symbol（调度器调用）
    # ─────────────────────────────────────────────

    async def sync_all_watched(
        self,
        db: AsyncSession,
        timeframes: Optional[List[str]] = None,
    ) -> Dict[str, int]:
        """
        同步所有 MarketWatch 中的币种

        Args:
            timeframes: 要同步的时间框架，默认 ["15m","1h","4h","1d"]

        Returns:
            {"BTCUSDT/1h": 5, ...}
        """
        from models.market_watch import MarketWatch

        if timeframes is None:
            timeframes = ["15m", "1h", "4h", "1d"]

        result = await db.execute(select(MarketWatch))
        watched = result.scalars().all()

        if not watched:
            return {}

        summary = {}
        total_symbols = len(watched)

        for idx, item in enumerate(watched):
            symbol = f"{item.symbol}USDT"
            for tf in timeframes:
                try:
                    logger.debug(
                        f"[KlineSync] sync_all [{idx+1}/{total_symbols}] {symbol}/{tf}"
                    )
                    inserted = await self.sync_incremental(db, symbol, tf)
                    summary[f"{symbol}/{tf}"] = inserted

                    # ⚠️ 每对 (symbol, timeframe) 间强制等待 200ms
                    # sync_incremental → 内部请求已经过 RateLimiter
                    # 这里额外等待用于全量回填场景下的双重保护
                    await asyncio.sleep(0.2)

                except Exception as e:
                    logger.error(f"[KlineSync] sync_all error for {symbol}/{tf}: {e}")
                    summary[f"{symbol}/{tf}"] = -1

            # 每个 symbol 全部时间框架同步完后，额外等待 500ms
            # 防止连续多 symbol 回填时请求集中爆发
            if idx < total_symbols - 1:  # 最后一个不需要等
                await asyncio.sleep(0.5)

        logger.info(f"[KlineSync] sync_all_watched completed: {len(summary)} jobs")
        return summary


# 全局实例
kline_sync = KlineSyncService()
