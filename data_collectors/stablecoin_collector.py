import logging
import aiohttp
from datetime import datetime
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

class StablecoinCollector:
    """
    Stablecoin Supply Collector
    Fetches data from DefiLlama
    """
    
    BASE_URL = "https://stablecoins.llama.fi/stablecoincharts/all"
    
    def __init__(self):
        self._cache_latest: Optional[Dict[str, Any]] = None
        self._cache_history: List[Dict[str, Any]] = []
        self._last_update: Optional[datetime] = None
        self._cache_duration = 3600  # 1 hour cache
        
    async def get_latest_supply(self) -> Optional[float]:
        """
        Get latest total stablecoin supply in USD
        """
        if self._is_cache_valid() and self._cache_latest:
            return self._cache_latest.get("totalCirculating", {}).get("peggedUSD")
            
        await self._fetch_data()
        
        if self._cache_latest:
            # The API returns nested dictionary structure:
            # { ..., "totalCirculating": {"peggedUSD": 123456...}, ... }
            return self._cache_latest.get("totalCirculating", {}).get("peggedUSD")
        return None
        
    async def get_history(self, days: int = 90) -> List[Dict[str, Any]]:
        """
        Get historical total supply data
        
        Returns:
            List of dicts with 'date' and 'value' keys
        """
        if not self._is_cache_valid() or not self._cache_history:
            await self._fetch_data()
            
        if not self._cache_history:
            return []
            
        # Filter by days
        if days > 0:
            start_ts = datetime.now().timestamp() - (days * 24 * 3600)
            # API returns integer timestamps in 'date' field
            return [
                {
                    "date": datetime.fromtimestamp(int(item["date"])).strftime("%Y-%m-%d"),
                    "value": item.get("totalCirculating", {}).get("peggedUSD", 0)
                }
                for item in self._cache_history
                if int(item["date"]) >= start_ts
            ]
            
        return [
            {
                "date": datetime.fromtimestamp(int(item["date"])).strftime("%Y-%m-%d"),
                "value": item.get("totalCirculating", {}).get("peggedUSD", 0)
            }
            for item in self._cache_history
        ]

    async def _fetch_data(self):
        """Fetch all data from DefiLlama and update cache"""
        import time
        from core.monitor import monitor
        start = time.monotonic()
        try:
            from core.http_client import SharedHTTPClient
            session = await SharedHTTPClient.get_session()
            async with session.get(self.BASE_URL) as response:
                if response.status != 200:
                    logger.warning(f"DefiLlama API Error {response.status}")
                    await monitor.record_status("DefiLlama", "REST", False, 0, f"HTTP {response.status}")
                    return

                data = await response.json()
                if data and isinstance(data, list):
                    self._cache_history = data
                    self._cache_latest = data[-1] if data else None
                    self._last_update = datetime.now()
                    latency = int((time.monotonic() - start) * 1000)
                    supply = self._cache_latest.get("totalCirculating", {}).get("peggedUSD") if self._cache_latest else None
                    await monitor.record_status("DefiLlama", "REST", True, latency, f"${supply/1e9:.1f}B" if supply else "OK")
        except Exception as e:
            logger.error(f"Error fetching Stablecoin data: {e}")
            await monitor.record_status("DefiLlama", "REST", False, 0, str(e)[:80])

    def _is_cache_valid(self) -> bool:
        if not self._last_update:
            return False
            
        age = (datetime.now() - self._last_update).total_seconds()
        return age < self._cache_duration

# Global Instance
stablecoin_collector = StablecoinCollector()
