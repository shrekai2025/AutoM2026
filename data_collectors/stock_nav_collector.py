import logging
import asyncio
from datetime import datetime

logger = logging.getLogger(__name__)

class StockNavCollector:
    """计算美股涉加密资管公司（如 MSTR, MARA 等）持币折溢价 mNAV"""
    
    def __init__(self):
        # 预设各大公司最新硬编码的持币量 (可定期维护更新)
        # 例如: MicroStrategy 截至 2024Q2 持仓大约 386,000 BTC
        self.holdings = {
            "MSTR": 386000,
            # Hypothetical SBET and BMNR mappings for user request
            "SBET": 10000,  
            "BMNR": 15000   
        }

    async def get_nav_ratio(self, symbol: str, btc_price: float) -> dict:
        """获取溢价率 (mNAV Ratio)"""
        if symbol not in self.holdings or not btc_price:
            return {}
            
        try:
            # 使用 TradingView 接口替代 yfinance，避免频繁的 401 封禁
            from core.http_client import SharedHTTPClient
            session = await SharedHTTPClient.get_session()
            
            # 常见映射
            exchange_map = {
                "MSTR": "NASDAQ:MSTR",
                "SBET": "NASDAQ:SBET",
                "BMNR": "AMEX:BMNR",
                "BITF": "NASDAQ:BITF",
                "MARA": "NASDAQ:MARA",
                "COIN": "NASDAQ:COIN"
            }
            tv_symbol = exchange_map.get(symbol, f"NASDAQ:{symbol}")
            
            url = "https://scanner.tradingview.com/america/scan"
            payload = {
                "symbols": {"tickers": [tv_symbol]},
                "columns": ["close", "market_cap_basic"]
            }
            headers = {"Content-Type": "application/json"}
            
            import aiohttp
            async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=8)) as resp:
                if resp.status != 200:
                    logger.error(f"TradingView scanner failed for {symbol}: {resp.status}")
                    return {}
                
                data = await resp.json()
                
            if not data.get("data") or len(data["data"]) == 0:
                logger.warning(f"No TV data found for {symbol}")
                return {}
                
            item = data["data"][0]
            price = item.get("d", [])[0]
            market_cap = item.get("d", [])[1]
            
            if not price or not market_cap:
                return {}
                
            # 基础 NAV = 公司持有的 BTC 总价值 (粗略计算)
            btc_nav_value = self.holdings[symbol] * btc_price
            
            # 计算折溢价率 (mNAV)
            ratio = market_cap / btc_nav_value
            
            classification = "溢价" if ratio > 1 else "折价"
            color_class = "text-error" if ratio > 1.2 else "text-success" if ratio < 0.9 else "text-warning"
            
            return {
                "symbol": symbol,
                "ratio": round(ratio, 2),
                "market_cap": market_cap,
                "btc_nav_value": btc_nav_value,
                "classification": classification,
                "class": color_class
            }
        except Exception as e:
            logger.error(f"Failed to fetch mNAV array for {symbol}: {e}")
            return {}

stock_collector = StockNavCollector()
