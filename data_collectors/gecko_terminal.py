import aiohttp
import asyncio
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class GeckoTerminalCollector:
    """GeckoTerminal API 数据采集器"""
    
    BASE_URL = "https://api.geckoterminal.com/api/v2"
    
    async def get_pool_history(
        self, 
        network: str, 
        pool_address: str, 
        limit: int = 1000,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict[str, Any]]:
        """
        获取指定池子的历史价格数据 (日线为主)
        返回: [{"ts": 170000000, "date": "2023-...", "price": 0.95}, ...]
        """
        url = f"{self.BASE_URL}/networks/{network}/pools/{pool_address}/ohlcv/day"
        params = {"limit": limit, "currency": "token"}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, headers={"Accept": "application/json"}, timeout=15) as response:
                    if response.status == 429:
                        logger.warning("GeckoTerminal API Limit Exceeded (429)")
                        return []
                        
                    response.raise_for_status()
                    data = await response.json()
                    
                    ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
                    if not ohlcv_list:
                        return []
                        
                    result = []
                    for item in ohlcv_list:
                        # item format: [timestamp, open, high, low, close, volume]
                        ts = int(item[0]) * 1000
                        result.append({
                            "ts": ts,
                            "date": datetime.fromtimestamp(ts / 1000).isoformat(),
                            "price": float(item[4])
                        })
                    
                    # 排序: old -> new
                    result.sort(key=lambda x: x["ts"])
                    
                    # 过滤时间
                    if start_date:
                        ts_start = int(start_date.timestamp() * 1000)
                        result = [r for r in result if r["ts"] >= ts_start]
                    if end_date:
                        ts_end = int(end_date.timestamp() * 1000)
                        result = [r for r in result if r["ts"] <= ts_end]
                        
                    return result
        except Exception as e:
            logger.error(f"Failed to fetch GeckoTerminal pool history {network}/{pool_address}: {e}")
            return []

    async def get_pool_metadata(self, network: str, pool_address: str) -> Dict[str, Any]:
        """获取池子元信息"""
        url = f"{self.BASE_URL}/networks/{network}/pools/{pool_address}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"Accept": "application/json"}, timeout=15) as response:
                    if response.status != 200:
                        return {"name": "Unknown", "symbol": "UNK"}
                        
                    data = await response.json()
                    attr = data.get("data", {}).get("attributes", {})
                    name = attr.get("name", "Unknown")
                    return {
                        "name": name,
                        "symbol": name.split(" / ")[0] if " / " in name else name,
                        "reserve_in_usd": attr.get("reserve_in_usd")
                    }
        except Exception as e:
            logger.error(f"Failed to fetch GeckoTerminal pool metadata: {e}")
            return {"name": "Unknown", "symbol": "UNK"}
            
    async def get_current_price(self, network: str, pool_address: str) -> Optional[float]:
        """获取最新池子价格 (base token price in quote token)"""
        url = f"{self.BASE_URL}/networks/{network}/pools/{pool_address}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers={"Accept": "application/json"}, timeout=15) as response:
                    if response.status == 200:
                        data = await response.json()
                        attr = data.get("data", {}).get("attributes", {})
                        price = attr.get("base_token_price_quote_token")
                        if price is not None:
                            return float(price)
            return None
        except Exception as e:
            logger.error(f"Failed to fetch current price from GeckoTerminal: {e}")
            return None

gecko_terminal = GeckoTerminalCollector()
