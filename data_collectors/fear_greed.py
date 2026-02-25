"""
Fear & Greed Index 数据采集器
从 Alternative.me API 获取恐惧贪婪指数
"""
import httpx
import logging
import time
from core.monitor import monitor
from datetime import datetime
from typing import Dict, Any, Optional

import aiohttp

from config import FEAR_GREED_API_URL

logger = logging.getLogger(__name__)


class FearGreedCollector:
    """Fear & Greed Index 数据采集器"""

    def __init__(self):
        self.base_url = FEAR_GREED_API_URL
        self._session: Optional[aiohttp.ClientSession] = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def get_current(self) -> Dict[str, Any]:
        """
        获取当前恐惧贪婪指数
        
        Returns:
            {
                "value": 65,
                "value_classification": "Greed",
                "timestamp": datetime,
                "time_until_update": "12 hours"
            }
        """
        session = await self._get_session()
        
        try:
            async with session.get(self.base_url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if data.get("data") and len(data["data"]) > 0:
                        item = data["data"][0]
                        return {
                            "value": int(item["value"]),
                            "value_classification": item["value_classification"],
                            "timestamp": datetime.fromtimestamp(int(item["timestamp"])),
                            "time_until_update": item.get("time_until_update", ""),
                        }
                logger.error(f"Fear & Greed API error: {resp.status}")
                return None
        except Exception as e:
            logger.error(f"Failed to get Fear & Greed Index: {e}")
            return None

    async def get_history(self, limit: int = 30) -> list:
        """
        获取历史数据
        
        Args:
            limit: 天数
            
        Returns:
            [
                {"value": 65, "classification": "Greed", "date": datetime},
                ...
            ]
        """
        session = await self._get_session()
        
        try:
            # Use explicit URL with trailing slash to avoid redirect losing params
            url = f"{self.base_url}/?limit={limit}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    history = []
                    for item in data.get("data", []):
                        history.append({
                            "value": int(item["value"]),
                            "classification": item["value_classification"],
                            "date": datetime.fromtimestamp(int(item["timestamp"])),
                        })
                    return history
                return []
        except Exception as e:
            logger.error(f"Failed to get Fear & Greed history: {e}")
            return []


# 全局实例
fear_greed_collector = FearGreedCollector()


# 便捷函数
async def get_fear_greed_index() -> int:
    """获取当前恐惧贪婪指数值"""
    data = await fear_greed_collector.get_current()
    return data["value"] if data else 50
