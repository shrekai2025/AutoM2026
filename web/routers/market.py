import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc, text, func

from core.database import AsyncSessionLocal
from core.scheduler import scheduler
from models import Strategy, Trade, Position, StrategyStatus, StrategyType, MarketWatch
from strategies import get_strategy_class, STRATEGY_CLASSES

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="web/templates")
router = APIRouter()

@router.get("/market", response_class=HTMLResponse)
async def market_watch(request: Request):
    """行情监控页"""
    from models import MarketWatch
    from data_collectors import binance_collector
    
    async with AsyncSessionLocal() as db:
        # 获取监控列表
        # 获取监控列表
        result = await db.execute(select(MarketWatch).order_by(MarketWatch.display_order, desc(MarketWatch.created_at)))
        watched_items = result.scalars().all()
        
        # 获取实时行情
        # 获取实时行情 (并发)
        import asyncio
        tasks = [binance_collector.get_24h_ticker(f"{item.symbol}USDT") for item in watched_items]
        tickers = await asyncio.gather(*tasks, return_exceptions=True)
        
        market_data = []
        for item, ticker in zip(watched_items, tickers):
            if isinstance(ticker, dict) and ticker:
                market_data.append({
                    "id": item.id,
                    "symbol": item.symbol,
                    "price": ticker["price"],
                    "price_change_24h": ticker["price_change_24h"],
                    "high_24h": ticker["high_24h"],
                    "low_24h": ticker["low_24h"],
                    "volume_24h": ticker["volume_24h"],
                    "is_starred": item.is_starred,
                    "valid": True
                })
            else:
                market_data.append({
                    "id": item.id,
                    "symbol": item.symbol,
                    "is_starred": item.is_starred,
                    "valid": False
                })
        
        # 宏观指标改由 AJAX 异步获取
        macro_indicators = []

        return templates.TemplateResponse("market.html", {
            "request": request,
            "market_data": market_data,
            "macro_indicators": macro_indicators,
        })

@router.get("/api/market/indicators")
async def api_market_indicators():
    """异步获取所有宏观指标（供前端 AJAX 调用）"""
    async with AsyncSessionLocal() as db:
        # 获取宏观指标数据 (并发和缓存)
        from web.services.market_service import market_service
        all_indicators = await market_service.get_all_indicators(db)
        
        macro_raw = all_indicators.get("fred") or {}
        fg_raw = all_indicators.get("fear_greed")
        hash_rate = all_indicators.get("hashrate")
        halving = all_indicators.get("halving")
        ahr999 = all_indicators.get("ahr999")
        wma200 = all_indicators.get("wma200")
        mvrv = all_indicators.get("mvrv")
        miners_data = all_indicators.get("miners")
        stablecoin_supply = all_indicators.get("stablecoin")
        mstr_nav = all_indicators.get("mstr_nav")
        sbet_nav = all_indicators.get("sbet_nav")
        bmnr_nav = all_indicators.get("bmnr_nav")
        etf_onchain_cards = all_indicators.get("etf_onchain") or []
    
        
        # Format for UI
        macro_indicators = []
        
        # 1. Fed Funds Rate
        val = macro_raw.get("fed_funds_rate")
        macro_indicators.append({
            "name_zh": "联邦基金利率",
            "name_en": "Federal Funds Rate",
            "abbr": "DFF",
            "value": f"{val}%" if val is not None else "-",
            "tags": ["宏观", "利率"],
            "desc": "基准利率",
            "trend": "neutral"
        })
        
        # 2. 10Y Yield
        val = macro_raw.get("treasury_10y")
        macro_indicators.append({
            "name_zh": "10年期美债收益率",
            "name_en": "10-Year Treasury Yield",
            "abbr": "DGS10",
            "value": f"{val}%" if val is not None else "-",
            "tags": ["宏观", "利率"],
            "desc": "无风险利率基准"
        })
        
        # 3. DXY
        val = macro_raw.get("dollar_index")
        macro_indicators.append({
            "name_zh": "美元指数",
            "name_en": "US Dollar Index",
            "abbr": "DXY",
            "value": f"{val:.2f}" if val is not None else "-",
            "tags": ["宏观", "汇率"],
            "desc": "美元相对强度"
        })
        
        # 4. M2 Growth
        val = macro_raw.get("m2_growth_yoy")
        macro_indicators.append({
            "name_zh": "M2货币供应量 (同比)",
            "name_en": "M2 Money Supply Growth (YoY)",
            "abbr": "M2SL",
            "value": f"{val}%" if val is not None else "-",
            "tags": ["宏观", "流动性"],
            "class": "text-success" if val and val > 0 else "text-error" if val and val < 0 else "",
            "desc": "市场流动性指标"
        })
        
        # 5. Fear & Greed
        val = int(fg_raw.get("value", 50)) if fg_raw else None
        classification = fg_raw.get("classification", "-") if fg_raw else "-"
        macro_indicators.append({
            "name_zh": "恐慌与贪婪指数",
            "name_en": "Fear & Greed Index",
            "abbr": "F&G",
            "value": str(val) if val is not None else "-",
            "tags": ["情绪", "BTC"],
            "sub_value": classification,
            "class": "text-error" if val is not None and val < 25 else "text-success" if val is not None and val > 75 else "text-warning" if val is not None else "",
            "desc": "市场情绪指标"
        })
        
        # 6. Stablecoin Supply
        val_b = (stablecoin_supply / 1_000_000_000) if stablecoin_supply else None
        macro_indicators.append({
            "name_zh": "稳定币总市值",
            "name_en": "Total Stablecoin Supply",
            "abbr": "STABLE",
            "value": f"${val_b:.2f}B" if val_b is not None else "-",
            "tags": ["流动性", "资金"],
            "class": "text-primary" if val_b is not None else "",
            "desc": "加密市场购买力"
        })
        
        # 7. ETF Inflows (BTC, ETH, SOL)
        from models.crawler import CrawledData
        
        # Helper to get latest flow
        async def get_latest_flow(data_type):
            result = await db.execute(
                select(CrawledData)
                .where(CrawledData.data_type == data_type)
                .order_by(desc(CrawledData.date), desc(CrawledData.created_at))
                .limit(1)
            )
            return result.scalar_one_or_none()
            
        # BTC
        btc_flow = await get_latest_flow("btc_etf_flow")
        val_m = (btc_flow.value / 1_000_000) if btc_flow and btc_flow.value is not None else None
        macro_indicators.append({
            "name_zh": "BTC ETF 净流入",
            "name_en": "BTC ETF Net Flow",
            "abbr": "BTC-ETF",
            "value": f"{'+' if val_m is not None and val_m >= 0 else ''}${val_m:.1f}M" if val_m is not None else "-",
            "tags": ["资金", "BTC", "ETF"],
            "class": "text-success" if val_m is not None and val_m >= 0 else "text-error" if val_m is not None else "",
            "desc": f"最近一日 ({btc_flow.date.strftime('%m-%d')})" if btc_flow else "等待数据"
        })
        
        # ETH
        eth_flow = await get_latest_flow("eth_etf_flow")
        val_m = (eth_flow.value / 1_000_000) if eth_flow and eth_flow.value is not None else None
        macro_indicators.append({
            "name_zh": "ETH ETF 净流入",
            "name_en": "ETH ETF Net Flow",
            "abbr": "ETH-ETF",
            "value": f"{'+' if val_m is not None and val_m >= 0 else ''}${val_m:.1f}M" if val_m is not None else "-",
            "tags": ["资金", "ETH", "ETF"],
            "class": "text-success" if val_m is not None and val_m >= 0 else "text-error" if val_m is not None else "",
            "desc": f"最近一日 ({eth_flow.date.strftime('%m-%d')})" if eth_flow else "等待数据"
        })
        
        # SOL
        sol_flow = await get_latest_flow("sol_etf_flow")
        val_m = (sol_flow.value / 1_000_000) if sol_flow and sol_flow.value is not None else None
        macro_indicators.append({
            "name_zh": "SOL ETF 净流入",
            "name_en": "SOL ETF Net Flow",
            "abbr": "SOL-ETF",
            "value": f"{'+' if val_m is not None and val_m >= 0 else ''}${val_m:.1f}M" if val_m is not None else "-",
            "tags": ["资金", "SOL", "ETF"],
            "class": "text-success" if val_m is not None and val_m >= 0 else "text-error" if val_m is not None else "",
            "desc": f"最近一日 ({sol_flow.date.strftime('%m-%d')})" if sol_flow else "等待数据"
        })

        # 8. Arkham 链上 ETF 持仓量 (IBIT/FBTC BTC/ETH 持有量)
        _arkham_types = {
            "ibit_holdings_btc": ("IBIT 链上BTC", "IBIT On-chain BTC", "IBIT-BTC", "BTC", ["链上", "BTC", "ETF"]),
            "ibit_holdings_eth": ("IBIT 链上ETH", "IBIT On-chain ETH", "IBIT-ETH", "ETH", ["链上", "ETH", "ETF"]),
            "fbtc_holdings_btc": ("FBTC 链上BTC", "FBTC On-chain BTC", "FBTC-BTC", "BTC", ["链上", "BTC", "ETF"]),
            "fbtc_holdings_eth": ("FBTC 链上ETH", "FBTC On-chain ETH", "FBTC-ETH", "ETH", ["链上", "ETH", "ETF"]),
            "blackrock_total_usd": ("贝莱德总持仓", "BlackRock Total Holdings", "IBIT-USD", "USD", ["链上", "BTC", "ETF"]),
            "fidelity_total_usd":  ("富达总持仓",   "Fidelity Total Holdings",   "FBTC-USD", "USD", ["链上", "BTC", "ETF"]),
        }
        for _dtype, (_zh, _en, _abbr, _asset, _tags) in _arkham_types.items():
            _row = await get_latest_flow(_dtype)
            if not _row or _row.value is None:
                _disp = "-"
                _date_str = "等待数据"
            else:
                _val = _row.value
                _date_str = _row.date.strftime("%m-%d") if _row.date else ""
                if _asset == "USD":
                    _disp = f"${_val/1e9:.2f}B"
                else:
                    _disp = f"{_val:,.0f} {_asset}"
            macro_indicators.append({
                "name_zh": _zh,
                "name_en": _en,
                "abbr": _abbr,
                "value": _disp,
                "tags": _tags,
                "class": "text-primary" if _disp != "-" else "",
                "desc": f"来源: Arkham Intel | {_date_str}" if _disp != "-" else "来源: Arkham Intel | 等待数据",
            })

        # --- Onchain Data ---
        val_eh = (hash_rate["value"] / 1_000_000_000_000_000_000) if hash_rate and "value" in hash_rate else None
        macro_indicators.append({
            "name_zh": "全网算力",
            "name_en": "Hashrate",
            "abbr": "HASH",
            "value": f"{val_eh:.1f} EH/s" if val_eh is not None else "-",
            "tags": ["BTC", "矿业", "链上"],
            "desc": "当前比特币网络总算力"
        })
        
        days_left = (halving["minutes_left"] / 60 / 24) if halving and "minutes_left" in halving else None
        macro_indicators.append({
            "name_zh": "下次减半",
            "name_en": "Next Halving",
            "abbr": "HALVING",
            "value": f"{int(days_left)} 天后" if days_left is not None else "-",
            "tags": ["BTC", "矿业"],
            "desc": f"预计仍需 {halving['blocks_left']} 个区块" if halving and "blocks_left" in halving else "等待数据"
        })
        
        val = ahr999.get("value") if ahr999 else None
        classification = ahr999.get("classification", "-") if ahr999 else "-"
        color_class = "text-success" if val is not None and val < 1.2 else "text-warning" if val is not None else ""
        macro_indicators.append({
            "name_zh": "ahr999 定投指数",
            "name_en": "ahr999 Index",
            "abbr": "AHR999",
            "value": f"{val:.2f}" if val is not None else "-",
            "sub_value": classification,
            "tags": ["BTC", "估值", "链上"],
            "class": color_class,
            "desc": "比特币定投/抄底指标"
        })
        
        val = wma200.get("value") if wma200 else None
        ratio = wma200.get("ratio") if wma200 else None
        color_class = "text-success" if ratio is not None and ratio < 1.2 else ""
        macro_indicators.append({
            "name_zh": "200周均线",
            "name_en": "200WMA",
            "abbr": "200WMA",
            "value": f"${val:,.0f}" if val is not None else "-",
            "sub_value": f"倍数: {ratio:.2f}x" if ratio is not None else "-",
            "tags": ["BTC", "估值", "链上"],
            "class": color_class,
            "desc": "长期底部的技术支撑线"
        })
        
        val = mvrv.get("value") if mvrv else None
        classification = mvrv.get("classification", "-") if mvrv else "-"
        color_class = "text-success" if val is not None and val < 1.5 else "text-warning" if val is not None and val > 3.0 else ""
        macro_indicators.append({
            "name_zh": "MVRV Ratio",
            "name_en": "MVRV Ratio",
            "abbr": "MVRV",
            "value": f"{val:.2f}" if val is not None else "-",
            "sub_value": classification,
            "tags": ["BTC", "估值", "链上"],
            "class": color_class,
            "desc": "市值相对其实际已实现成本的比率"
        })
        
        # --- Miners Data ---
        total = miners_data.get("total_miners") if miners_data else None
        profitable = miners_data.get("profitable_miners") if miners_data else None
        shutdown_range = miners_data.get("shutdown_range", "-") if miners_data else "-"
        best_m = miners_data.get("best_miner") if miners_data else None
        
        macro_indicators.append({
            "name_zh": "盈利矿机数",
            "name_en": "Profitable Miners",
            "abbr": "MINER-P",
            "value": f"{profitable}/{total}台" if profitable is not None and total is not None else "-",
            "sub_value": f"电费: $0.06",
            "tags": ["BTC", "矿业"],
            "class": "text-primary" if profitable is not None else "",
            "desc": f"关机价范围: {shutdown_range}"
        })
        
        macro_indicators.append({
            "name_zh": "最效率矿机",
            "name_en": "Most Efficient Miner",
            "abbr": "MINER-E",
            "value": (str(best_m)[:12] + "..") if best_m else "-",
            "sub_value": "最低关机价",
            "tags": ["BTC", "矿业"],
            "class": "text-success" if best_m else "",
            "desc": str(best_m) if best_m else "等待数据"
        })

        # --- Stock mNAV Data ---
        stock_navs = [("MSTR", mstr_nav), ("SBET", sbet_nav), ("BMNR", bmnr_nav)]
        for symbol, st in stock_navs:
            ratio = st["ratio"] if st and "ratio" in st else None
            class_str = st.get("classification", "-") if st else "-"
            macro_indicators.append({
                "name_zh": f"{symbol} 持币溢价",
                "name_en": f"{symbol} mNAV",
                "abbr": f"NAV-{symbol}",
                "value": f"{ratio:.2f}x" if ratio is not None else "-",
                "sub_value": class_str,
                "tags": ["估值", "美股"],
                "class": st.get("class", "text-warning") if st and ratio is not None else "",
                "desc": f"市值相对其实际持有的BTC总价值比率"
            })

        # --- ETF 链上监控卡片 (AUM + 持仓余额) ---
        macro_indicators.extend(etf_onchain_cards)

        return {"indicators": macro_indicators}

@router.get("/market/indicator/{indicator_id}")
async def indicator_detail(request: Request, indicator_id: str, days: int = 90):
    """指标详情页 - 展示历史数据图表"""
    from data_collectors.fred_collector import fred_collector
    from data_collectors import fear_greed_collector
    
    # Map indicator ID to FRED series and metadata
    INDICATOR_MAP = {
        "DFF": {
            "series_id": "DFF",
            "name_zh": "联邦基金利率",
            "name_en": "Federal Funds Rate",
            "desc_zh": "美联储设定的银行间隔夜拆借利率，是美国货币政策的核心工具",
            "desc_en": "The interest rate at which banks lend reserves to each other overnight",
            "unit": "%"
        },
        "DGS10": {
            "series_id": "DGS10",
            "name_zh": "10年期美债收益率",
            "name_en": "10-Year Treasury Yield",
            "desc_zh": "美国政府10年期债券的收益率，被视为无风险利率的基准",
            "desc_en": "Yield on U.S. Treasury securities at 10-year constant maturity",
            "unit": "%"
        },
        "DXY": {
            "series_id": "DTWEXBGS",
            "name_zh": "美元指数",
            "name_en": "US Dollar Index",
            "desc_zh": "衡量美元相对于一篮子主要货币的价值",
            "desc_en": "Nominal Broad U.S. Dollar Index",
            "unit": ""
        },
        "M2SL": {
            "series_id": "M2SL",
            "name_zh": "M2货币供应量",
            "name_en": "M2 Money Supply",
            "desc_zh": "M2货币总量，包括现金、活期存款、储蓄存款等",
            "desc_en": "M2 includes currency, checking deposits, and easily convertible near money",
            "unit": "B USD"
        },
        "F&G": {
            "series_id": None,  # Special case - not from FRED
            "name_zh": "恐慌与贪婪指数",
            "name_en": "Fear & Greed Index",
            "desc_zh": "CNN的市场情绪指数，0表示极度恐慌，100表示极度贪婪",
            "desc_en": "CNN's market sentiment indicator from 0 (Extreme Fear) to 100 (Extreme Greed)",
            "unit": ""
        },
        "STABLE": {
            "series_id": None,
            "name_zh": "稳定币总市值",
            "name_en": "Total Stablecoin Supply",
            "desc_zh": "全网稳定币总流通市值 (USDT, USDC, etc.)",
            "desc_en": "Total circulating supply of all stablecoins pegged to USD",
            "unit": "USD"
        },
        "BTC-ETF": {
            "series_id": None,
            "name_zh": "BTC ETF 净流入",
            "name_en": "BTC ETF Net Flow",
            "desc_zh": "美国现货比特币 ETF 每日净流入/流出金额",
            "desc_en": "Daily net inflow/outflow of US Spot Bitcoin ETFs",
            "unit": "USD",
            "data_type": "btc_etf_flow"
        },
        "ETH-ETF": {
            "series_id": None,
            "name_zh": "ETH ETF 净流入",
            "name_en": "ETH ETF Net Flow",
            "desc_zh": "美国现货以太坊 ETF 每日净流入/流出金额",
            "desc_en": "Daily net inflow/outflow of US Spot Ethereum ETFs",
            "unit": "USD",
            "data_type": "eth_etf_flow"
        },
        "SOL-ETF": {
            "series_id": None,
            "name_zh": "SOL ETF 净流入",
            "name_en": "SOL ETF Net Flow",
            "desc_zh": "美国现货 Solana ETF 每日净流入/流出金额 (如可用)",
            "desc_en": "Daily net inflow/outflow of US Spot Solana ETFs (if available)",
            "unit": "USD",
            "data_type": "sol_etf_flow"
        },
        "HASH": {
            "series_id": None,
            "name_zh": "全网算力",
            "name_en": "Network Hashrate",
            "desc_zh": "比特币全网算力，反映矿工投入和网络安全度",
            "desc_en": "Hashrate",
            "unit": "EH/s"
        },
        "HALVING": {
            "series_id": None,
            "name_zh": "下次减半",
            "name_en": "Next Halving",
            "desc_zh": "距离下一次比特币出块奖励减半的时间",
            "desc_en": "Next Halving Countdown",
            "unit": "Days"
        },
        "AHR999": {
            "series_id": None,
            "name_zh": "ahr999 定投指数",
            "name_en": "ahr999 Index",
            "desc_zh": "抄底定投指数。低于 0.45 为抄底区间，低于 1.2 为定投区间",
            "desc_en": "ahr999 Index",
            "unit": ""
        },
        "200WMA": {
            "series_id": None,
            "name_zh": "200周均线",
            "name_en": "200 Week Moving Average",
            "desc_zh": "长期底部的技术支撑线，是判断市场周期的重要参考",
            "desc_en": "200WMA",
            "unit": "$"
        },
        "MVRV": {
            "series_id": None,
            "name_zh": "MVRV Ratio",
            "name_en": "MVRV Ratio",
            "desc_zh": "Market-Value-to-Realized-Value。市值除以已实现价值。指标偏低代表过度低估，偏高代表处于周期顶峰。",
            "desc_en": "MVRV Ratio",
            "unit": ""
        },
        "MINER-P": {
            "series_id": None,
            "name_zh": "盈利矿机数",
            "name_en": "Profitable Miners",
            "desc_zh": "全网主流矿机在当前币价和正常电费($0.06)下的盈利面概况",
            "desc_en": "Profitable Miners count",
            "unit": "台"
        },
        "MINER-E": {
            "series_id": None,
            "name_zh": "最效率矿机",
            "name_en": "Most Efficient Miner",
            "desc_zh": "目前市面上最抗风险、能效比最低(关机价最低)的机型",
            "desc_en": "Miner",
            "unit": ""
        },
        "NAV-MSTR": {
            "series_id": None,
            "name_zh": "微策略 MSTR",
            "name_en": "MicroStrategy mNAV",
            "desc_zh": "MSTR 市值与其实际持有 BTC 总价值的比率",
            "desc_en": "MSTR Premium",
            "unit": "x"
        },
        "NAV-SBET": {
            "series_id": None,
            "name_zh": "SBET 持币溢价",
            "name_en": "SBET mNAV",
            "desc_zh": "SBET的 mNAV 溢价率",
            "desc_en": "SBET Premium",
            "unit": "x"
        },
        "NAV-BMNR": {
            "series_id": None,
            "name_zh": "BMNR 持币溢价",
            "name_en": "BMNR mNAV",
            "desc_zh": "BMNR的 mNAV 溢价率",
            "desc_en": "BMNR Premium",
            "unit": "x"
        },
        # Arkham 链上资产指标
        "IBIT-BTC": {
            "series_id": None, "data_type": "ibit_holdings_btc", "name_zh": "IBIT 链上BTC", "name_en": "IBIT On-chain BTC",
            "desc_zh": "贝莱德 IBIT 在 Coinbase Custody 的链上真实比特币余额", "desc_en": "IBIT Bitcoin holdings on-chain", "unit": "BTC"
        },
        "IBIT-ETH": {
            "series_id": None, "data_type": "ibit_holdings_eth", "name_zh": "IBIT 链上ETH", "name_en": "IBIT On-chain ETH",
            "desc_zh": "贝莱德 ETHA 链上以太坊余额", "desc_en": "IBIT Ethereum holdings on-chain", "unit": "ETH"
        },
        "IBIT-USD": {
            "series_id": None, "data_type": "blackrock_total_usd", "name_zh": "贝莱德总持仓", "name_en": "BlackRock Total Holdings",
            "desc_zh": "Arkham Intelligence 统计的贝莱德总持仓总净值", "desc_en": "Total Net Value of BlackRock on-chain holdings", "unit": "$"
        },
        "FBTC-BTC": {
            "series_id": None, "data_type": "fbtc_holdings_btc", "name_zh": "FBTC 链上BTC", "name_en": "FBTC On-chain BTC",
            "desc_zh": "富达 FBTC 的链上比特币实际托管余额", "desc_en": "FBTC Bitcoin holdings on-chain", "unit": "BTC"
        },
        "FBTC-ETH": {
            "series_id": None, "data_type": "fbtc_holdings_eth", "name_zh": "FBTC 链上ETH", "name_en": "FBTC On-chain ETH",
            "desc_zh": "富达 FETH 的链上以太坊余额", "desc_en": "FBTC Ethereum holdings on-chain", "unit": "ETH"
        },
        "FBTC-USD": {
            "series_id": None, "data_type": "fidelity_total_usd", "name_zh": "富达总持仓", "name_en": "Fidelity Total Holdings",
            "desc_zh": "Arkham Intelligence 统计的富达实体总净值", "desc_en": "Fidelity Total Network Value on-chain", "unit": "$"
        },
        # 兼容 yfinance 和 blockscout/mempool API 的卡片
        "BTC-ETF-AUM": {
            "series_id": None, "data_type": "total_btc_etf_aum", "name_zh": "BTC ETF 总规模", "name_en": "Total BTC ETF AUM", "desc_zh": "美国现货比特币 ETF 整体资产规模", "desc_en": "Total BTC ETF AUM", "unit": "$"
        },
        "ETH-ETF-AUM": {
            "series_id": None, "data_type": "total_eth_etf_aum", "name_zh": "ETH ETF 总规模", "name_en": "Total ETH ETF AUM", "desc_zh": "美国现货以太坊 ETF 整体资产规模", "desc_en": "Total ETH ETF AUM", "unit": "$"
        },
    }
    
    # 针对类似 "CHAIN-IBIT" 这种动态生成的 id 做的后备方案
    if indicator_id.startswith("CHAIN-"):
        etf_ticker = indicator_id.split("-")[1]
        INDICATOR_MAP[indicator_id] = {
            "series_id": None,
            "data_type": f"{etf_ticker}_onchain_balance",
            "name_zh": f"{etf_ticker} 链上持仓",
            "name_en": f"{etf_ticker} On-chain",
            "desc_zh": f"{etf_ticker} ETF 链上透明地址内的资产余额",
            "desc_en": f"{etf_ticker} on-chain recorded balance",
            "unit": ""
        }
    elif indicator_id not in INDICATOR_MAP and ("IBIT" in indicator_id or "FBTC" in indicator_id or "GBTC" in indicator_id or "ARKB" in indicator_id or "ETHA" in indicator_id):
        # 针对 yfinance AUM 动态卡片 (abbr: ticker)
        INDICATOR_MAP[indicator_id] = {
            "series_id": None,
            "data_type": f"{indicator_id}_aum",
            "name_zh": f"{indicator_id} 资产规模",
            "name_en": f"{indicator_id} AUM",
            "desc_zh": f"{indicator_id} 总净资产规模",
            "desc_en": f"{indicator_id} Net Asset Value",
            "unit": "$"
        }

    
    indicator_id = indicator_id.upper()
    
    if indicator_id not in INDICATOR_MAP:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error": f"Unknown indicator: {indicator_id}"
        }, status_code=404)
    
    meta = INDICATOR_MAP[indicator_id]
    history = []
    current_value = None
    
    if meta["series_id"]:
        # Fetch from FRED
        history = await fred_collector.get_series_history(meta["series_id"], days=days)
        if history:
            current_value = history[-1]["value"]
    elif indicator_id == "STABLE":
        # Stablecoin history
        from data_collectors import stablecoin_collector
        history = await stablecoin_collector.get_history(days=days)
        if history:
            current_value = history[-1]["value"]
    elif "data_type" in meta:
        # ETF Flows from CrawledData
        from models.crawler import CrawledData
        
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(CrawledData)
                .where(CrawledData.data_type == meta["data_type"])
                .order_by(desc(CrawledData.date), desc(CrawledData.created_at))
                .limit(days * 5)  # Fetch more to allow deduplication
            )
            raw_items = result.scalars().all()
            
            # Deduplicate by date (keep the first one encountered which is the newest created_at due to order_by)
            unique_items = []
            seen_dates = set()
            for item in raw_items:
                date_str = item.date.strftime("%Y-%m-%d")
                if date_str not in seen_dates:
                    seen_dates.add(date_str)
                    unique_items.append(item)
                if len(unique_items) == days:
                    break
                    
            items = unique_items
            
            # Format: [{"date": "2024-01-01", "value": 123}]
            # Reverse to have oldest first for chart
            history = []
            for item in reversed(items):
                history.append({
                    "date": item.date.strftime("%Y-%m-%d"),
                    "value": item.value
                })
            
            if items:
                current_value = items[0].value
    elif indicator_id == "F&G":
        # Special handling for Fear & Greed - has its own history API
        fg_history = await fear_greed_collector.get_history(limit=days)
        if fg_history:
            # Convert to same format as FRED data
            history = [{"date": item["date"].strftime("%Y-%m-%d"), "value": item["value"]} for item in reversed(fg_history)]
            current_value = fg_history[0]["value"]  # Most recent is first
        else:
            # Fallback to current only
            fg_data = await fear_greed_collector.get_current()
            if fg_data:
                current_value = int(fg_data.get("value", 50))
                history = [{"date": datetime.now().strftime("%Y-%m-%d"), "value": current_value}]
    else:
        # Fallback to current value for HASH, HALVING, AHR999, 200WMA
        from data_collectors.onchain_collector import onchain_collector
        now_str = datetime.now().strftime("%Y-%m-%d")
        
        if indicator_id == "HASH":
            res = await onchain_collector.get_hashrate()
            if res and "value" in res:
                current_value = res["value"] / 1_000_000_000_000_000_000
                history = [{"date": now_str, "value": current_value}]
        elif indicator_id == "HALVING":
            res = await onchain_collector.get_halving_info()
            if res and "minutes_left" in res:
                current_value = res["minutes_left"] / 60 / 24
                history = [{"date": now_str, "value": current_value}]
        elif indicator_id == "AHR999":
            res = await onchain_collector.get_ahr999()
            if res and "value" in res:
                current_value = res["value"]
                history = [{"date": now_str, "value": current_value}]
        elif indicator_id == "200WMA":
            res = await onchain_collector.get_200wma()
            if res and "value" in res:
                current_value = res["value"]
                history = [{"date": now_str, "value": current_value}]
        elif indicator_id == "MVRV":
            res = await onchain_collector.get_mvrv_ratio()
            if res and "value" in res:
                current_value = res["value"]
                history = [{"date": now_str, "value": current_value}]
        elif indicator_id in ["MINER-P", "MINER-E", "NAV-MSTR", "NAV-SBET", "NAV-BMNR"]:
            current_value = 0
            history = [{"date": now_str, "value": current_value}]
    
    # Convert history to JSON for Chart.js
    import json
    history_json = json.dumps(history)
    
    return templates.TemplateResponse("indicator_detail.html", {
        "request": request,
        "indicator_id": indicator_id,
        "name_zh": meta["name_zh"],
        "name_en": meta["name_en"],
        "desc_zh": meta["desc_zh"],
        "desc_en": meta["desc_en"],
        "unit": meta["unit"],
        "current_value": current_value,
        "days": days,
        "history_json": history_json
    })

@router.post("/market/add")
async def add_market_watch(symbol: str = Form(...)):
    """添加监控"""
    from models import MarketWatch
    from data_collectors import binance_collector
    
    symbol = symbol.upper().strip()
    
    # 验证币种是否存在
    ticker = await binance_collector.get_24h_ticker(f"{symbol}USDT")
    if not ticker:
        raise HTTPException(status_code=400, detail=f"Invalid symbol or pair not supported on Binance: {symbol}USDT")
    
    async with AsyncSessionLocal() as db:
        # 检查是否已存在
        result = await db.execute(select(MarketWatch).where(MarketWatch.symbol == symbol))
        existing = result.scalar_one_or_none()
        
        if not existing:
            watch_item = MarketWatch(symbol=symbol)
            db.add(watch_item)
            await db.commit()
            
    return RedirectResponse(url="/market", status_code=303)

@router.post("/market/delete")
async def delete_market_watch(id: int = Form(...)):
    """删除监控"""
    from models import MarketWatch
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MarketWatch).where(MarketWatch.id == id))
        item = result.scalar_one_or_none()
        
        if item:
            await db.delete(item)
            await db.commit()
            
    return RedirectResponse(url="/market", status_code=303)

@router.post("/market/reorder")
async def reorder_market_watch(order: list[int] = Form(...)):
    """更新排序"""
    from models import MarketWatch
    
    # Form(...) with list expects multiple values with same key, usually passed as order=1&order=2..
    # Or JSON body. Let's support simple JSON list if possible, but for Form it's tricky.
    # Actually, standard way for sortable is often sending an array of IDs.
    # Let's handle it as a JSON post for simplicity in JS.
    pass 

@router.post("/api/market/reorder")
async def api_reorder_market_watch(request: Request):
    """API endpoint for reordering"""
    from models import MarketWatch
    data = await request.json()
    order_ids = data.get("order", [])
    
    if not order_ids:
        return {"status": "ok", "message": "No changes"}
        
    async with AsyncSessionLocal() as db:
        # Fetch all items to be safe? Or just update one by one.
        # Batch update is better.
        for index, item_id in enumerate(order_ids):
            # We can execute direct updates
             await db.execute(
                text("UPDATE market_watch SET display_order = :order WHERE id = :id"),
                {"order": index, "id": item_id}
            )
        await db.commit()
    
    return {"status": "ok"}

@router.post("/market/{id}/toggle_star")
async def toggle_star(id: int):
    """切换标星状态"""
    from models import MarketWatch
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(MarketWatch).where(MarketWatch.id == id))
        item = result.scalar_one_or_none()
        
        if item:
            item.is_starred = not item.is_starred
            await db.commit()
            
    return RedirectResponse(url="/market", status_code=303)

