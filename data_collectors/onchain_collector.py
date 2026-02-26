import aiohttp
import asyncio
import logging
from datetime import datetime
import math

from data_collectors.binance import binance_collector

logger = logging.getLogger(__name__)

class OnchainCollector:
    """链上及宏观指标采集器 (Mempool, 各种由 Binance 行情计算的指标等)"""
    
    def __init__(self):
        self.mempool_base = "https://mempool.space/api/v1"

    async def _get_session(self) -> aiohttp.ClientSession:
        from core.http_client import SharedHTTPClient
        return await SharedHTTPClient.get_session()

    async def get_hashrate(self) -> dict:
        """从 mempool 获取全网算力"""
        session = await self._get_session()
        # mempool 提供了 hashrate 接口
        url = f"{self.mempool_base}/mining/hashrate/1m"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # data['currentHashrate'] 也有当前值
                    current = data.get('currentHashrate', 0)
                    if not current and data.get('hashrates'):
                        current = data['hashrates'][-1].get('avgHashrate', 0)
                    return {
                        "value": current,
                        "unit": "H/s"
                    }
        except Exception as e:
            logger.error(f"Mempool hashrate error: {e}")
        return {}

    async def get_halving_info(self) -> dict:
        """从 mempool 获取区块高度并计算距离下次减半的时间"""
        session = await self._get_session()
        url = "https://mempool.space/api/blocks/tip/height"
        try:
            async with session.get(url) as resp:
                if resp.status == 200:
                    current_height = int(await resp.text())
                    # 减半周期 210,000 个块
                    halving_interval = 210000
                    next_halving_height = ((current_height // halving_interval) + 1) * halving_interval
                    blocks_left = next_halving_height - current_height
                    # 假设 10 分钟一个块
                    minutes_left = blocks_left * 10
                    return {
                        "current_height": current_height,
                        "next_halving_height": next_halving_height,
                        "blocks_left": blocks_left,
                        "minutes_left": minutes_left
                    }
        except Exception as e:
            logger.error(f"Mempool block height error: {e}")
        return {}

    async def get_ahr999(self) -> dict:
        """
        计算 ahr999 指数
        ahr999 = (BTC现价 / 200日定投成本) * (BTC现价 / 拟合指数增长估值)
        拟合估值 = 10^(5.84 * log10(天数) - 17.01)
        天数 = 从 2009-01-03 至今的天数
        """
        try:
            # 1. 获取当前价和200日均线
            klines = await binance_collector.get_klines("BTCUSDT", interval="1d", limit=200)
            if not klines:
                return {}
            
            closes = [k["close"] for k in klines]
            current_price = closes[-1]
            ma200 = sum(closes) / len(closes) if closes else current_price
            
            # 2. 计算天数龄
            genesis_date = datetime(2009, 1, 3)
            age_days = (datetime.utcnow() - genesis_date).days
            
            # 3. 拟合估值
            fitted_price = 10 ** (5.84 * math.log10(age_days) - 17.01)
            
            # 4. 计算指数
            ahr999 = (current_price / ma200) * (current_price / fitted_price)
            
            # 评估状态
            classification = "起飞区间"
            if ahr999 < 0.45:
                classification = "抄底区间"
            elif ahr999 < 1.2:
                classification = "定投区间"
            elif ahr999 > 5.0:
                classification = "逃顶区间"
                
            return {
                "value": round(ahr999, 3),
                "classification": classification,
                "current_price": current_price,
                "ma200": ma200,
                "fitted_price": fitted_price
            }
        except Exception as e:
            logger.error(f"Ahr999 calc error: {e}")
            return {}

    async def get_200wma(self) -> dict:
        """获取 200WMA 连云均线 (200周均线)"""
        try:
            klines = await binance_collector.get_klines("BTCUSDT", interval="1w", limit=200)
            if not klines:
                return {}
            
            closes = [k["close"] for k in klines]
            current_price = closes[-1]
            wma200 = sum(closes) / len(closes) if closes else current_price
            
            ratio = current_price / wma200 if wma200 else 0
            
            return {
                "value": round(wma200, 2),
                "current_price": current_price,
                "ratio": round(ratio, 2)
            }
        except Exception as e:
            logger.error(f"200WMA calc error: {e}")
            return {}

    async def get_mvrv_ratio(self) -> dict:
        """从 CoinMetrics 获取每日 MVRV Ratio"""
        url = "https://community-api.coinmetrics.io/v4/timeseries/asset-metrics"
        params = {
            "assets": "btc",
            "metrics": "CapMVRVCur",
            "frequency": "1d",
            "limit_per_asset": "1"
        }
        try:
            session = await self._get_session()
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    items = data.get('data', [])
                    if items:
                        val = float(items[0].get("CapMVRVCur", 0))
                        
                        # 0.x - 1.25 是低估/定投， > 3.7 是高估
                        classification = "正常状态"
                        if val < 1.0:
                            classification = "极度低估"
                        elif val <= 1.5:
                            classification = "正常偏低 (定投)"
                        elif val > 3.7:
                            classification = "极度高估 (逃顶)"
                            
                        return {
                            "value": round(val, 2),
                            "classification": classification
                        }
        except Exception as e:
            logger.error(f"CoinMetrics MVRV fetch error: {e}")
            
        return {}

onchain_collector = OnchainCollector()
