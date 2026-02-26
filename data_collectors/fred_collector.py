import os
import httpx
import logging
import time
import asyncio
from datetime import datetime, timedelta
from core.monitor import monitor
from typing import Dict, Any, Optional
import aiohttp

from config.settings import FRED_API_KEY

logger = logging.getLogger(__name__)

class FREDCollector:
    """
    FRED (Federal Reserve Economic Data) Collector
    
    Collects:
    - Federal Funds Rate (DFF)
    - 10-Year Treasury Yield (DGS10)
    - M2 Money Supply (M2SL)
    - US Dollar Index Proxy (DTWEXBGS)
    """
    
    BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
    
    # Series IDs
    SERIES_MAPPING = {
        "fed_funds_rate": "DFF",
        "treasury_10y": "DGS10",
        "m2_supply": "M2SL",
        "dollar_index": "DTWEXBGS"  # Nominal Broad U.S. Dollar Index
    }
    
    def __init__(self):
        self.api_key = FRED_API_KEY
        self._cache: Dict[str, Any] = {}
        self._cache_expiry: Dict[str, datetime] = {}
        self._cache_duration = timedelta(hours=24) # Macro data changes slowly
        
    async def get_macro_data(self) -> Dict[str, float]:
        """
        Get all configured macro indicators
        
        Returns:
            Dict with keys: fed_funds_rate, treasury_10y, m2_growth_yoy, dollar_index
        """
        if not self.api_key:
            logger.warning("FRED_API_KEY not configured, skipping macro data")
            return {}
            
        results = {}
        
        from core.http_client import SharedHTTPClient
        session = await SharedHTTPClient.get_session()

        # 1. Fetch Standard Indicators
        tasks = []
        keys = []
        
        for key, series_id in self.SERIES_MAPPING.items():
            if key == "m2_supply": continue # Handle separate
            
            # Check cache
            if self._is_cache_valid(key):
                results[key] = self._cache[key]
                continue
                
            tasks.append(self._fetch_series_latest(session, series_id))
            keys.append(key)
        
        if tasks:
            responses = await asyncio.gather(*tasks, return_exceptions=True)
            for key, resp in zip(keys, responses):
                if isinstance(resp, Exception):
                    logger.error(f"Error fetching {key}: {resp}")
                    results[key] = None
                else:
                    self._cache[key] = resp
                    self._cache_expiry[key] = datetime.now() + self._cache_duration
                    results[key] = resp
        
        # 2. Handle M2 Growth (requires historical comparison)
        if self._is_cache_valid("m2_growth_yoy"):
            results["m2_growth_yoy"] = self._cache["m2_growth_yoy"]
        else:
            try:
                # Fetch Current M2
                current_m2 = await self._fetch_series_latest(session, "M2SL")
                
                # Fetch 1 Year Ago M2
                one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                prev_m2 = await self._fetch_series_observation(session, "M2SL", one_year_ago)
                
                if current_m2 and prev_m2 and prev_m2 > 0:
                    growth = ((current_m2 - prev_m2) / prev_m2) * 100
                    results["m2_growth_yoy"] = round(growth, 2)
                    
                    # Cache the calculated growth
                    self._cache["m2_growth_yoy"] = results["m2_growth_yoy"]
                    self._cache_expiry["m2_growth_yoy"] = datetime.now() + self._cache_duration
                else:
                     logger.warning(f"Could not calc M2 growth: curr={current_m2}, prev={prev_m2}")
                     results["m2_growth_yoy"] = None
                     
            except Exception as e:
                logger.error(f"Error calculating M2 growth: {e}")
                results["m2_growth_yoy"] = None

        return results

    async def get_series_history(self, series_id: str, days: int = 90) -> list:
        """
        Get historical observations for a series
        
        Args:
            series_id: FRED series ID (e.g., 'DFF', 'DGS10')
            days: Number of days of history to fetch
            
        Returns:
            List of dicts with 'date' and 'value' keys
        """
        if not self.api_key:
            logger.warning("FRED_API_KEY not configured")
            return []
        
        start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        end_date = datetime.now().strftime("%Y-%m-%d")
        
        # Determine frequency based on series
        freq = "m" if series_id == "M2SL" else "d"
        
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "observation_start": start_date,
            "observation_end": end_date,
            "frequency": freq,
            "sort_order": "asc"
        }
        
        try:
            start_time = time.time() # Added for latency monitoring
            async with httpx.AsyncClient() as client:
                response = await client.get(self.BASE_URL, params=params, timeout=10)
                response.raise_for_status()
                data = response.json()
                
                # Check status
                latency = int((time.time() - start_time) * 1000)
                await monitor.record_status("FRED API", "Macro", True, latency, f"Fetched {series_id}")
                
                if "observations" in data:
                    observations = data["observations"]
                    # Clean and parse
                    result = []
                    for obs in observations:
                        if obs["value"] != ".":
                            result.append({
                                "date": obs["date"],
                                "value": float(obs["value"])
                            })
                    return result
                return []
        except Exception as e:
            logger.error(f"Error fetching FRED series {series_id}: {e}")
            await monitor.record_status("FRED API", "Macro", False, 0, str(e))
            return []

    async def _fetch_series_latest(self, session: aiohttp.ClientSession, series_id: str) -> Optional[float]:
        """Fetch latest observation for a series"""
        freq = "d"
        if series_id == "M2SL": freq = "m"
            
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": 1,
            "sort_order": "desc",
            "frequency": freq 
        }
        
        return await self._execute_request(session, params)

    async def _fetch_series_observation(self, session: aiohttp.ClientSession, series_id: str, date_str: str) -> Optional[float]:
        """Fetch observation closest to a specific date"""
        freq = "d"
        if series_id == "M2SL": freq = "m"
        
        params = {
            "series_id": series_id,
            "api_key": self.api_key,
            "file_type": "json",
            "limit": 1,
            "sort_order": "desc",
            "observation_end": date_str, # Get entries up to this date
            "frequency": freq
        }
        
        return await self._execute_request(session, params)

    async def _execute_request(self, session: aiohttp.ClientSession, params: Dict) -> Optional[float]:
        try:
            async with session.get(self.BASE_URL, params=params) as response:
                if response.status != 200:
                    logger.warning(f"FRED API Error {response.status}: {await response.text()}")
                    return None
                    
                data = await response.json()
                observations = data.get("observations", [])
                
                if not observations:
                    return None
                    
                val_str = observations[0].get("value", ".")
                if val_str == ".":
                     return None
                     
                return float(val_str)
        except Exception as e:
            logger.error(f"FRED request failed: {e}")
            return None

    def _is_cache_valid(self, key: str) -> bool:
        if key not in self._cache or key not in self._cache_expiry:
            return False
        return datetime.now() < self._cache_expiry[key]

# Global Instance
fred_collector = FREDCollector()
