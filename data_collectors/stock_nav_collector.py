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
            # yfinance 存在阻塞 IO，需要放在 executor 中运行
            import yfinance as yf
            
            def fetch_info():
                ticker = yf.Ticker(symbol)
                # handle missing shares info for some small/obscure tickers gracefully
                shares = ticker.info.get("sharesOutstanding") or ticker.info.get("impliedSharesOutstanding")
                price = ticker.info.get("currentPrice") or ticker.info.get("previousClose")
                return price, shares

            price, shares = await asyncio.to_thread(fetch_info)
            
            if not price or not shares:
                return {}
                
            market_cap = price * shares
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
