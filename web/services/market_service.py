import asyncio
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from data_collectors.fred_collector import fred_collector
from data_collectors.onchain_collector import onchain_collector
from data_collectors.binance import binance_collector
from data_collectors import fear_greed_collector
from data_collectors.mining_collector import mining_collector
from data_collectors.stock_nav_collector import stock_collector
from data_collectors import stablecoin_collector
from data_collectors.etf_onchain_collector import etf_onchain_collector
from core.monitor import monitor

logger = logging.getLogger(__name__)


class MarketDataService:
    """聚合所有宏观指标数据，带内存缓存和并发请求"""

    def __init__(self):
        self._cache: Dict[str, tuple] = {}
        # 针对不同数据源设置不同的 TTL (单位: 秒)
        self._cache_ttl = {
            "fred": 3600,         # 1小时
            "fear_greed": 300,    # 5分钟
            "hashrate": 600,      # 10分钟
            "halving": 3600,      # 1小时
            "ahr999": 600,        # 10分钟
            "wma200": 3600,       # 1小时
            "mvrv": 3600,         # 1小时
            "miners": 1800,       # 30分钟
            "stablecoin": 600,    # 10分钟
            "mstr_nav": 300,      # 5分钟
            "sbet_nav": 300,      # 5分钟
            "bmnr_nav": 300,      # 5分钟
            "etf_onchain": 600,   # 10分钟
            "btc_price": 60,      # 1分钟
            "eth_price": 60,      # 1分钟
        }

    def _cache_get(self, key: str) -> Optional[Any]:
        """从缓存中取值，若过期则返回 sentinel None。"""
        if key in self._cache:
            data, cached_at = self._cache[key]
            ttl = self._cache_ttl.get(key, 300)
            if (datetime.utcnow() - cached_at).total_seconds() < ttl:
                return data
        return None  # 代表"未命中"

    def _cache_set(self, key: str, value: Any):
        self._cache[key] = (value, datetime.utcnow())

    async def _fetch_with_cache(self, key: str, fetch_fn) -> Any:
        """
        先读缓存，若命中直接返回；否则调用 fetch_fn() 并缓存结果。
        fetch_fn 必须是一个返回 Awaitable 的可调用对象（lambda 或函数）。
        """
        hit = self._cache_get(key)
        if hit is not None:
            return hit

        start = datetime.utcnow()
        try:
            result = await fetch_fn()
        except Exception as e:
            logger.warning(f"[MarketService] {key} fetch error: {e}")
            result = None

        latency_ms = int((datetime.utcnow() - start).total_seconds() * 1000)

        # 只缓存非 None 结果，避免把失败结果缓存住
        if result is not None:
            self._cache_set(key, result)

        await self._record_monitor(key, result, latency_ms)
        return result

    async def get_all_indicators(self, db) -> Dict[str, Any]:
        """并发获取所有数据源，有缓存直接返回"""

        # 1. 先拿价格——其他 NAV 计算依赖当前价格
        btc_price_d, eth_price_d = await asyncio.gather(
            self._fetch_with_cache("btc_price", lambda: binance_collector.get_price("BTCUSDT")),
            self._fetch_with_cache("eth_price", lambda: binance_collector.get_price("ETHUSDT")),
            return_exceptions=True
        )

        # asyncio.gather with return_exceptions=True 的返回值可能是 Exception
        if isinstance(btc_price_d, Exception) or not btc_price_d:
            btc_price_d = None
        if isinstance(eth_price_d, Exception) or not eth_price_d:
            eth_price_d = None

        current_btc_usd = btc_price_d["price"] if btc_price_d else 0
        current_eth_usd = eth_price_d["price"] if eth_price_d else 0

        # 2. 定义所有任务——注意每个都是 lambda，避免提前创建协程
        task_defs = {
            "fred":       lambda: fred_collector.get_macro_data(),
            "fear_greed": lambda: fear_greed_collector.get_current(),
            "hashrate":   lambda: onchain_collector.get_hashrate(),
            "halving":    lambda: onchain_collector.get_halving_info(),
            "ahr999":     lambda: onchain_collector.get_ahr999(),
            "wma200":     lambda: onchain_collector.get_200wma(),
            "mvrv":       lambda: onchain_collector.get_mvrv_ratio(),
            "miners":     lambda: mining_collector.get_miners_data(),
            "stablecoin": lambda: stablecoin_collector.get_latest_supply(),
            "mstr_nav":   lambda: stock_collector.get_nav_ratio("MSTR", current_btc_usd),
            "sbet_nav":   lambda: stock_collector.get_nav_ratio("SBET", current_btc_usd),
            "bmnr_nav":   lambda: stock_collector.get_nav_ratio("BMNR", current_btc_usd),
            "etf_onchain": lambda: etf_onchain_collector.get_macro_indicators(
                btc_price=current_btc_usd, eth_price=current_eth_usd
            ),
        }

        # 3. 并发执行（带超时保护）
        async def safe_fetch(key: str, fn) -> tuple[str, Any]:
            try:
                val = await asyncio.wait_for(
                    self._fetch_with_cache(key, fn),
                    timeout=20.0
                )
            except asyncio.TimeoutError:
                logger.warning(f"[MarketService] {key} timed out")
                val = None
            except Exception as e:
                logger.warning(f"[MarketService] {key} error: {e}")
                val = None
            return key, val

        pairs = await asyncio.gather(
            *[safe_fetch(k, fn) for k, fn in task_defs.items()],
            return_exceptions=False
        )

        results: Dict[str, Any] = dict(pairs)
        results["current_btc_usd"] = current_btc_usd
        results["current_eth_usd"] = current_eth_usd
        return results

    async def _record_monitor(self, key: str, result: Any, latency: int):
        """记录各数据源健康状态"""
        try:
            if key == "fred":
                await monitor.record_status("FRED API", "Macro", bool(result), latency,
                                            f"Got {len(result)} fields" if result else "No data")
            elif key == "fear_greed":
                await monitor.record_status("Fear & Greed", "REST", bool(result), latency,
                                            f"Value: {result.get('value')}" if result else "No data")
            elif key == "hashrate":
                await monitor.record_status("Mempool API", "Onchain",
                                            bool(result and "value" in result), latency,
                                            "Hashrate OK" if result else "No data")
            elif key == "halving":
                await monitor.record_status("Mempool Halving", "Onchain", bool(result), latency,
                                            f"Height: {result.get('current_height')}" if result else "No data")
            elif key == "ahr999":
                await monitor.record_status("AHR999 Calc", "Derived", bool(result), latency,
                                            f"Value: {result.get('value')}" if result else "Calc failed")
            elif key == "wma200":
                val_str = f"${result.get('value'):,.0f}" if result and "value" in result else "N/A"
                await monitor.record_status("200WMA Calc", "Derived", bool(result), latency,
                                            f"Value: {val_str}")
            elif key == "mvrv":
                await monitor.record_status("CoinMetrics MVRV", "REST",
                                            bool(result and "value" in result), latency,
                                            f"MVRV: {result.get('value')}" if result else "No data")
            elif key == "miners":
                await monitor.record_status("Mining Data", "Scraper", bool(result), latency,
                                            f"{result.get('total_miners', 0)} miners" if result else "No data")
            elif key == "stablecoin":
                ok = result is not None and result > 0
                await monitor.record_status("Stablecoin Supply", "REST", ok, latency,
                                            f"${result / 1e9:.1f}B" if result else "No data")
            elif key == "etf_onchain":
                await monitor.record_status("ETF Onchain", "ETF", bool(result), latency,
                                            f"{len(result)} metrics" if result else "No data")
        except Exception as e:
            logger.error(f"[MarketService] monitor record failed for {key}: {e}")


market_service = MarketDataService()
