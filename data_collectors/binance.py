"""
Binance 数据采集器
从 Binance 公开 API 获取 K 线和价格数据
"""
import httpx
import logging
import time
from core.monitor import monitor
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Dict, List, Any, Optional

import aiohttp

from config import BINANCE_API_URL

logger = logging.getLogger(__name__)


class BinanceCollector:
    """Binance 数据采集器"""

    def __init__(self):
        self.base_url = BINANCE_API_URL

    async def _get_session(self) -> aiohttp.ClientSession:
        from core.http_client import SharedHTTPClient
        return await SharedHTTPClient.get_session()

    async def close(self):
        pass # Managed centrally in app.py lifespan

    async def get_price(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """
        获取当前价格
        
        Returns:
            {
                "symbol": "BTCUSDT",
                "price": 43250.50,
                "timestamp": datetime
            }
        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v3/ticker/price"
        
        try:
            async with session.get(url, params={"symbol": symbol}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return {
                        "symbol": symbol,
                        "price": float(data["price"]),
                        "timestamp": datetime.utcnow(),
                    }
                else:
                    logger.error(f"Binance API error: {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Failed to get price: {e}")
            return None

    async def get_24h_ticker(self, symbol: str = "BTCUSDT") -> Dict[str, Any]:
        """
        获取24小时行情
        
        Returns:
            {
                "symbol": "BTCUSDT",
                "price": 43250.50,
                "price_change_24h": 3.5,
                "high_24h": 44000.0,
                "low_24h": 42000.0,
                "volume_24h": 50000.0,
                "timestamp": datetime
            }
        """
        start_time = time.time() # Added for latency calculation
        session = await self._get_session()
        url = f"{self.base_url}/api/v3/ticker/24hr"
        
        try:
            async with session.get(url, params={"symbol": symbol}) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    latency = int((time.time() - start_time) * 1000) # Added
                    await monitor.record_status("Binance API (Public)", "REST", True, latency, f"Fetched 24h ticker for {symbol}") # Added
                    return {
                        "symbol": symbol,
                        "price": float(data["lastPrice"]),
                        "price_change_24h": float(data["priceChangePercent"]),
                        "high_24h": float(data["highPrice"]),
                        "low_24h": float(data["lowPrice"]),
                        "volume_24h": float(data["volume"]),
                        "quote_volume_24h": float(data["quoteVolume"]),
                        "timestamp": datetime.utcnow(),
                    }
                else:
                    logger.error(f"Binance API error: {resp.status}")
                    latency = int((time.time() - start_time) * 1000) # Added
                    await monitor.record_status("Binance API (Public)", "REST", False, latency, f"API error {resp.status} for {symbol}") # Added
                    return None
        except Exception as e:
            logger.error(f"Failed to get 24h ticker: {e}")
            await monitor.record_status("Binance API (Public)", "REST", False, 0, str(e)) # Added
            return None

    async def get_klines(
        self,
        symbol: str = "BTCUSDT",
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        获取 K 线数据
        
        Args:
            symbol: 交易对
            interval: 时间间隔 (1m, 5m, 15m, 1h, 4h, 1d)
            limit: 数量 (最大1000)
            
        Returns:
            [
                {
                    "open_time": datetime,
                    "open": 43000.0,
                    "high": 43500.0,
                    "low": 42800.0,
                    "close": 43250.0,
                    "volume": 1000.5,
                    "close_time": datetime,
                },
                ...
            ]
        """
        session = await self._get_session()
        url = f"{self.base_url}/api/v3/klines"
        
        try:
            params = {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            }
            if start_time:
                params["startTime"] = start_time
            if end_time:
                params["endTime"] = end_time
            
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    klines = []
                    for k in data:
                        klines.append({
                            "open_time": datetime.fromtimestamp(k[0] / 1000),
                            "open": float(k[1]),
                            "high": float(k[2]),
                            "low": float(k[3]),
                            "close": float(k[4]),
                            "volume": float(k[5]),
                            "close_time": datetime.fromtimestamp(k[6] / 1000),
                            "quote_volume": float(k[7]),
                            "trades": int(k[8]),
                        })
                    return klines
                else:
                    logger.error(f"Binance API error: {resp.status}")
                    return []
        except Exception as e:
            logger.error(f"Failed to get klines: {e}")
            return []

    async def get_multi_timeframe_data(
        self,
        symbol: str = "BTCUSDT",
        timeframes: List[str] = ["15m", "1h", "4h"]
    ) -> Dict[str, List[Dict]]:
        """
        获取多时间框架 K 线数据
        
        Returns:
            {
                "15m": [...klines...],
                "1h": [...klines...],
                "4h": [...klines...],
            }
        """
        result = {}
        for tf in timeframes:
            klines = await self.get_klines(symbol=symbol, interval=tf, limit=200)
            result[tf] = klines
        return result


# 全局实例
binance_collector = BinanceCollector()


# 便捷函数
async def get_btc_price() -> float:
    """获取 BTC 当前价格"""
    data = await binance_collector.get_price("BTCUSDT")
    return data["price"] if data else 0.0


async def get_eth_price() -> float:
    """获取 ETH 当前价格"""
    data = await binance_collector.get_price("ETHUSDT")
    return data["price"] if data else 0.0
