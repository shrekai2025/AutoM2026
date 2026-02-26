"""
简单 Web UI - 使用 FastAPI + Jinja2

提供策略管理、持仓查看、交易记录等功能
"""
import logging
import asyncio
from datetime import datetime
from typing import Optional
from contextlib import asynccontextmanager

from pydantic import BaseModel
from fastapi import FastAPI, Request, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, desc, text
from sqlalchemy.ext.asyncio import AsyncSession

from config import WEB_HOST, WEB_PORT
from core.database import init_db, AsyncSessionLocal
from core.scheduler import scheduler
from models import Strategy, Trade, Position, StrategyStatus, StrategyType
from strategies import get_strategy_class, STRATEGY_CLASSES
from data_collectors import get_btc_price

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时
    await init_db()
    await scheduler.start(AsyncSessionLocal)
    logger.info("Application started")
    
    yield
    
    # 关闭时
    scheduler.stop()
    logger.info("Application stopped")


app = FastAPI(
    title="AutoM2026",
    description="简化版加密货币策略交易系统",
    version="1.0.0",
    lifespan=lifespan,
)

# 设置模板
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")


# ==================== 页面路由 ====================

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """首页 - 仪表盘"""
    async with AsyncSessionLocal() as db:
        # 获取策略列表
        result = await db.execute(select(Strategy).order_by(desc(Strategy.updated_at)))
        strategies = result.scalars().all()
        
        # 统计策略数据
        total_strategies_count = len(strategies)
        active_strategies_count = sum(1 for s in strategies if s.status == StrategyStatus.ACTIVE.value)
        
        # 获取最近交易
        result = await db.execute(
            select(Trade).order_by(desc(Trade.executed_at)).limit(10)
        )
        recent_trades = result.scalars().all()
        
        # 获取当前持仓计算总资产和盈亏
        result = await db.execute(select(Position).where(Position.amount > 0))
        positions = result.scalars().all()
        
        total_value = sum(float(p.current_value) for p in positions)
        total_pnl = sum(float(p.unrealized_pnl) for p in positions)
        
        # 获取当前 BTC 价格 (保留作为后备或始终显示)
        btc_price = await get_btc_price()
        
        # 获取标星行情 / Starred Markets
        from models import MarketWatch
        from data_collectors import binance_collector
        
        result = await db.execute(select(MarketWatch).where(MarketWatch.is_starred == True))
        starred_items = result.scalars().all()
        
        starred_markets = []
        for item in starred_items:
            ticker = await binance_collector.get_24h_ticker(f"{item.symbol}USDT")
            starred_markets.append({
                "symbol": item.symbol,
                "price": ticker["price"] if ticker else 0,
                "change": ticker["price_change_24h"] if ticker else 0,
                "valid": bool(ticker)
            })
            
        # 如果没有标星，默认显示 BTC
        if not starred_markets:
             starred_markets.append({
                "symbol": "BTC",
                "price": btc_price,
                "change": 0, # get_btc_price simple helper doesn't return change, ok for now
                "valid": True
            })
        
        return templates.TemplateResponse("index.html", {
            "request": request,
            "strategies": strategies,
            "recent_trades": recent_trades,
            "starred_markets": starred_markets,
            "total_value": total_value,
            "total_pnl": total_pnl,
            "active_strategies_count": active_strategies_count,
            "total_strategies_count": total_strategies_count,
            "now": datetime.utcnow(),
        })


@app.get("/strategies", response_class=HTMLResponse)
async def list_strategies(request: Request):
    """策略列表页"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).order_by(desc(Strategy.created_at)))
        strategies = result.scalars().all()
        
        return templates.TemplateResponse("strategies.html", {
            "request": request,
            "strategies": strategies,
            "strategy_types": list(StrategyType),
        })


@app.get("/strategies/new", response_class=HTMLResponse)
async def new_strategy_form(request: Request, type: str = "ta"):
    """新建策略表单"""
    strategy_class = get_strategy_class(type)
    default_config = strategy_class.get_default_config() if strategy_class else {}
    
    return templates.TemplateResponse("strategy_form.html", {
        "request": request,
        "strategy_type": type,
        "default_config": default_config,
        "strategy_types": list(StrategyType),
        "is_edit": False,
    })


@app.post("/strategies/create")
async def create_strategy(
    name: str = Form(...),
    type: str = Form(...),
    symbol: str = Form("BTC"),
    schedule_minutes: int = Form(5),
):
    """创建策略"""
    async with AsyncSessionLocal() as db:
        # 获取默认配置
        strategy_class = get_strategy_class(type)
        config = strategy_class.get_default_config() if strategy_class else {}
        config["symbol"] = symbol
        
        strategy = Strategy(
            name=name,
            type=type,
            symbol=symbol,
            schedule_minutes=schedule_minutes,
            status=StrategyStatus.PAUSED.value,
            config=config,
        )
        
        db.add(strategy)
        
        # 自动添加到行情监控 / Auto-add to Market Watch
        from models import MarketWatch
        result = await db.execute(select(MarketWatch).where(MarketWatch.symbol == symbol))
        if not result.scalar_one_or_none():
            db.add(MarketWatch(symbol=symbol))
            
        await db.commit()
        
        return RedirectResponse(url="/strategies", status_code=303)


@app.get("/strategies/{strategy_id}/edit", response_class=HTMLResponse)
async def edit_strategy_form(request: Request, strategy_id: int):
    """编辑策略表单"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        strategy_class = get_strategy_class(strategy.type)
        default_config = strategy_class.get_default_config() if strategy_class else {}
        
        return templates.TemplateResponse("strategy_form.html", {
            "request": request,
            "strategy": strategy,
            "strategy_type": strategy.type,
            "default_config": default_config,
            "strategy_types": list(StrategyType),
            "is_edit": True,
        })


@app.post("/strategies/{strategy_id}/update")
async def update_strategy(
    strategy_id: int,
    name: str = Form(...),
    schedule_minutes: int = Form(...),
    symbol: str = Form("BTC"),
):
    """更新策略"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
            
        strategy.name = name
        strategy.schedule_minutes = schedule_minutes
        
        # 如果还在暂停状态，允许修改币种（简单处理，如果运行中改币种可能需要重置状态）
        if strategy.status != StrategyStatus.ACTIVE.value:
            strategy.symbol = symbol
            if strategy.config:
                strategy.config["symbol"] = symbol
                # Force update JSON to be detected? 
                # SQLA JSON type usually detects changes if we reassign logic or use mutation tracking.
                # Reassigning the whole dict is safest.
                strategy.config = dict(strategy.config)
        
        await db.commit()
        
        # 如果策略正在运行，需要重启调度任务以应用新的时间间隔
        if strategy.status == StrategyStatus.ACTIVE.value:
            await scheduler.add_strategy(db, strategy)
            
        return RedirectResponse(url=f"/strategies/{strategy_id}", status_code=303)


@app.post("/strategies/{strategy_id}/toggle")
async def toggle_strategy(strategy_id: int):
    """切换策略状态"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        if strategy.status == StrategyStatus.ACTIVE.value:
            strategy.status = StrategyStatus.PAUSED.value
            await scheduler.remove_strategy(strategy_id)
        else:
            strategy.status = StrategyStatus.ACTIVE.value
            await scheduler.add_strategy(db, strategy)
        
        await db.commit()
        
        return RedirectResponse(url="/strategies", status_code=303)


@app.post("/strategies/{strategy_id}/run")
async def run_strategy_now(strategy_id: int, background_tasks: BackgroundTasks):
    """立即执行策略 (异步后台执行)"""
    from models import Strategy
    
    # Verify strategy exists
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
    
    # Queue execution in background
    background_tasks.add_task(scheduler.run_strategy_now, strategy_id)
    
    return {"status": "queued", "message": "策略执行任务已创建", "strategy_id": strategy_id}


@app.post("/strategies/{strategy_id}/delete")
async def delete_strategy(strategy_id: int):
    """删除策略"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.id == strategy_id)
        )
        strategy = result.scalar_one_or_none()
        
        if strategy:
            await scheduler.remove_strategy(strategy_id)
            await db.delete(strategy)
            await db.commit()
        
        return RedirectResponse(url="/strategies", status_code=303)


@app.get("/strategies/{strategy_id}", response_class=HTMLResponse)
async def strategy_detail(request: Request, strategy_id: int):
    """策略详情页 (Observability)"""
    from models.strategy_execution import StrategyExecution
    
    async with AsyncSessionLocal() as db:
        # 获取策略
        result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
        strategy = result.scalar_one_or_none()
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
            
        # 获取执行历史 (最近 50 条)
        result = await db.execute(
            select(StrategyExecution)
            .where(StrategyExecution.strategy_id == strategy_id)
            .order_by(desc(StrategyExecution.executed_at))
            .limit(50)
        )
        executions = result.scalars().all()
        
        # Grid Strategy Status Logic
        grid_status = None
        if strategy.type == 'grid':
            try:
                from strategies import get_strategy_class
                from data_collectors import binance_collector
                
                # Get current price
                pair = f"{strategy.symbol}USDT"
                ticker = await binance_collector.get_price(pair)
                current_price = ticker["price"] if ticker else 0
                
                if current_price > 0:
                    # Try to get running instance
                    strategy_instance = scheduler._strategy_cache.get(strategy.id)
                    
                    # If not running, create temporary instance
                    if not strategy_instance:
                        strategy_class = get_strategy_class('grid')
                        if strategy_class:
                            strategy_instance = strategy_class(strategy.config)
                    
                    if strategy_instance and hasattr(strategy_instance, 'get_grid_status'):
                        grid_status = strategy_instance.get_grid_status(current_price)
            except Exception as e:
                logger.error(f"Failed to get grid status: {e}")
        
        return templates.TemplateResponse("strategy_detail.html", {
            "request": request,
            "strategy": strategy,
            "executions": executions,
            "grid_status": grid_status,
        })


@app.get("/positions", response_class=HTMLResponse)
async def list_positions(request: Request):
    """持仓列表页"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Position).where(Position.amount > 0)
        )
        positions = result.scalars().all()
        
        # 计算总价值
        total_value = sum(float(p.current_value) for p in positions)
        total_pnl = sum(float(p.unrealized_pnl) for p in positions)
        
        return templates.TemplateResponse("positions.html", {
            "request": request,
            "positions": positions,
            "total_value": total_value,
            "total_pnl": total_pnl,
        })


@app.get("/trades", response_class=HTMLResponse)
async def list_trades(request: Request, limit: int = 50):
    """交易记录页"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Trade).order_by(desc(Trade.executed_at)).limit(limit)
        )
        trades = result.scalars().all()
        
        return templates.TemplateResponse("trades.html", {
            "request": request,
            "trades": trades,
        })


@app.get("/market", response_class=HTMLResponse)
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
        market_data = []
        for item in watched_items:
            ticker = await binance_collector.get_24h_ticker(f"{item.symbol}USDT")
            if ticker:
                market_data.append({
                    "id": item.id,
                    "symbol": item.symbol,
                    "price": ticker["price"],
                    "price_change_24h": ticker["price_change_24h"],
                    "high_24h": ticker["high_24h"],
                    "low_24h": ticker["low_24h"],
                    "volume_24h": ticker["volume_24h"],
                    "volume_24h": ticker["volume_24h"],
                    "is_starred": item.is_starred,
                    "valid": True
                })
            else:
                market_data.append({
                    "id": item.id,
                    "symbol": item.symbol,
                    "symbol": item.symbol,
                    "is_starred": item.is_starred,
                    "valid": False
                })
        
        # 获取宏观指标数据
        from data_collectors.fred_collector import fred_collector
        from data_collectors import fear_greed_collector
        from data_collectors.onchain_collector import onchain_collector
        from core.monitor import monitor
        import time as _time
        
        # --- FRED ---
        _t = _time.time()
        macro_raw = await fred_collector.get_macro_data()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("FRED API", "Macro", bool(macro_raw), _lat,
                                     f"Got {len(macro_raw)} fields" if macro_raw else "No data")

        # --- Fear & Greed ---
        _t = _time.time()
        fg_raw = await fear_greed_collector.get_current()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("Fear & Greed", "REST", bool(fg_raw), _lat,
                                     f"Value: {fg_raw.get('value')}" if fg_raw else "No data")

        # --- Mempool (Hashrate) ---
        _t = _time.time()
        hash_rate = await onchain_collector.get_hashrate()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("Mempool API", "Onchain", bool(hash_rate and "value" in hash_rate), _lat,
                                     "Hashrate OK" if hash_rate else "No data")

        # --- Mempool (Halving) ---
        _t = _time.time()
        halving = await onchain_collector.get_halving_info()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("Mempool Halving", "Onchain", bool(halving), _lat,
                                     f"Height: {halving.get('current_height')}" if halving else "No data")

        # --- AHR999 (depends on Binance klines) ---
        _t = _time.time()
        ahr999 = await onchain_collector.get_ahr999()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("AHR999 Calc", "Derived", bool(ahr999), _lat,
                                     f"Value: {ahr999.get('value')}" if ahr999 else "Calc failed")

        # --- 200WMA ---
        _t = _time.time()
        wma200 = await onchain_collector.get_200wma()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("200WMA Calc", "Derived", bool(wma200), _lat,
                                     f"Value: ${wma200.get('value'):,.0f}" if wma200 and "value" in wma200 else "Calc failed")

        # --- MVRV (CoinMetrics) ---
        _t = _time.time()
        mvrv = await onchain_collector.get_mvrv_ratio()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("CoinMetrics MVRV", "REST", bool(mvrv and "value" in mvrv), _lat,
                                     f"MVRV: {mvrv.get('value')}" if mvrv else "No data")
        
        # New Miners and Stock NAV
        from data_collectors.mining_collector import mining_collector
        from data_collectors.stock_nav_collector import stock_collector
        
        # Needs current BTC price for NAVs & miner calculations if dynamic
        btc_price_d = await binance_collector.get_price("BTCUSDT")
        current_btc_usd = btc_price_d["price"] if btc_price_d else 0
        
        _t = _time.time()
        miners_data = await mining_collector.get_miners_data()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("Mining Data", "Scraper", bool(miners_data), _lat,
                                     f"{miners_data.get('total_miners', 0)} miners" if miners_data else "No data")
        
        mstr_nav = await stock_collector.get_nav_ratio("MSTR", current_btc_usd)
        sbet_nav = await stock_collector.get_nav_ratio("SBET", current_btc_usd)
        bmnr_nav = await stock_collector.get_nav_ratio("BMNR", current_btc_usd)

        # ETF 链上监控 (yfinance AUM + Blockchain.info + Etherscan)
        from data_collectors.etf_onchain_collector import etf_onchain_collector
        eth_price_d = await binance_collector.get_price("ETHUSDT")
        current_eth_usd = eth_price_d["price"] if eth_price_d else 0
        _t = _time.time()
        try:
            etf_onchain_cards = await etf_onchain_collector.get_macro_indicators(
                btc_price=current_btc_usd, eth_price=current_eth_usd
            )
        except Exception as _e:
            logger.warning(f"ETF onchain collector error: {_e}")
            etf_onchain_cards = []
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status(
            "ETF Onchain", "ETF", bool(etf_onchain_cards), _lat,
            f"{len(etf_onchain_cards)} metrics" if etf_onchain_cards else "No data"
        )

        # Stablecoin Supply
        from data_collectors import stablecoin_collector
        _t = _time.time()
        stablecoin_supply = await stablecoin_collector.get_latest_supply()
        _lat = int((_time.time() - _t) * 1000)
        await monitor.record_status("Stablecoin Supply", "REST", stablecoin_supply is not None and stablecoin_supply > 0, _lat,
                                     f"${stablecoin_supply/1e9:.1f}B" if stablecoin_supply else "No data")

        
        # Format for UI
        macro_indicators = []
        
        # 1. Fed Funds Rate
        if "fed_funds_rate" in macro_raw:
            val = macro_raw["fed_funds_rate"]
            macro_indicators.append({
                "name_zh": "联邦基金利率",
                "name_en": "Federal Funds Rate",
                "abbr": "DFF",
                "value": f"{val}%" if val is not None else "N/A",
                "tags": ["宏观", "利率"],
                "desc": "基准利率",
                "trend": "neutral" # TODO: compare with previous
            })
            
        # 2. 10Y Yield
        if "treasury_10y" in macro_raw:
            val = macro_raw["treasury_10y"]
            macro_indicators.append({
                "name_zh": "10年期美债收益率",
                "name_en": "10-Year Treasury Yield",
                "abbr": "DGS10",
                "value": f"{val}%" if val is not None else "N/A",
                "tags": ["宏观", "利率"],
                "desc": "无风险利率基准"
            })
            
        # 3. DXY
        if "dollar_index" in macro_raw:
            val = macro_raw["dollar_index"]
            macro_indicators.append({
                "name_zh": "美元指数",
                "name_en": "US Dollar Index",
                "abbr": "DXY",
                "value": f"{val:.2f}" if val is not None else "N/A",
                "tags": ["宏观", "汇率"],
                "desc": "美元相对强度"
            })
            
        # 4. M2 Growth
        if "m2_growth_yoy" in macro_raw:
            val = macro_raw["m2_growth_yoy"]
            macro_indicators.append({
                "name_zh": "M2货币供应量 (同比)",
                "name_en": "M2 Money Supply Growth (YoY)",
                "abbr": "M2SL",
                "value": f"{val}%" if val is not None else "N/A",
                "tags": ["宏观", "流动性"],
                "class": "text-success" if val and val > 0 else "text-error" if val and val < 0 else "",
                "desc": "市场流动性指标"
            })
            
        # 5. Fear & Greed
        if fg_raw:
            val = int(fg_raw.get("value", 50))
            classification = fg_raw.get("classification", "Neutral")
            macro_indicators.append({
                "name_zh": "恐慌与贪婪指数",
                "name_en": "Fear & Greed Index",
                "abbr": "F&G",
                "value": str(val),
                "tags": ["情绪", "BTC"],
                "sub_value": classification,
                "class": "text-error" if val < 25 else "text-success" if val > 75 else "text-warning",
                "desc": "市场情绪指标"
            })
            
        # 6. Stablecoin Supply
        if stablecoin_supply:
            # Format as billions
            val_b = stablecoin_supply / 1_000_000_000
            macro_indicators.append({
                "name_zh": "稳定币总市值",
                "name_en": "Total Stablecoin Supply",
                "abbr": "STABLE",
                "value": f"${val_b:.2f}B",
                "tags": ["流动性", "资金"],
                "class": "text-primary",
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
        if btc_flow:
            val_m = btc_flow.value / 1_000_000
            macro_indicators.append({
                "name_zh": "BTC ETF 净流入",
                "name_en": "BTC ETF Net Flow",
                "abbr": "BTC-ETF",
                "value": f"{'+' if val_m >= 0 else ''}${val_m:.1f}M",
                "tags": ["资金", "BTC", "ETF"],
                "class": "text-success" if val_m >= 0 else "text-error",
                "desc": f"最近一日 ({btc_flow.date.strftime('%m-%d')})"
            })
            
        # ETH
        eth_flow = await get_latest_flow("eth_etf_flow")
        if eth_flow:
            val_m = eth_flow.value / 1_000_000
            macro_indicators.append({
                "name_zh": "ETH ETF 净流入",
                "name_en": "ETH ETF Net Flow",
                "abbr": "ETH-ETF",
                "value": f"{'+' if val_m >= 0 else ''}${val_m:.1f}M",
                "tags": ["资金", "ETH", "ETF"],
                "class": "text-success" if val_m >= 0 else "text-error",
                "desc": f"最近一日 ({eth_flow.date.strftime('%m-%d')})"
            })
            
        # SOL
        sol_flow = await get_latest_flow("sol_etf_flow")
        if sol_flow:
            val_m = sol_flow.value / 1_000_000
            macro_indicators.append({
                "name_zh": "SOL ETF 净流入",
                "name_en": "SOL ETF Net Flow",
                "abbr": "SOL-ETF",
                "value": f"{'+' if val_m >= 0 else ''}${val_m:.1f}M",
                "tags": ["资金", "SOL", "ETF"],
                "class": "text-success" if val_m >= 0 else "text-error",
                "desc": f"最近一日 ({sol_flow.date.strftime('%m-%d')})"
            })

        # 8. Arkham 链上 ETF 持仓量 (IBIT/FBTC BTC/ETH 持有量)
        # 数据来自 Arkham Intelligence 页面爬虫，存入 crawled_data 表
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
            if not _row or not _row.value:
                continue
            _val = _row.value
            _date_str = _row.date.strftime("%m-%d") if _row.date else ""
            if _asset == "USD":
                _disp = f"${_val/1e9:.2f}B"
            else:
                # 持仓量（BTC/ETH 枚数）
                _disp = f"{_val:,.0f} {_asset}"
            macro_indicators.append({
                "name_zh": _zh,
                "name_en": _en,
                "abbr": _abbr,
                "value": _disp,
                "tags": _tags,
                "class": "text-primary",
                "desc": f"来源: Arkham Intel | {_date_str}",
            })

        # --- Onchain Data ---
        if hash_rate and "value" in hash_rate:
            val_eh = hash_rate["value"] / 1_000_000_000_000_000_000
            macro_indicators.append({
                "name_zh": "全网算力",
                "name_en": "Hashrate",
                "abbr": "HASH",
                "value": f"{val_eh:.1f} EH/s",
                "tags": ["BTC", "矿业", "链上"],
                "desc": "当前比特币网络总算力"
            })
            
        if halving and "minutes_left" in halving:
            days_left = halving["minutes_left"] / 60 / 24
            macro_indicators.append({
                "name_zh": "下次减半",
                "name_en": "Next Halving",
                "abbr": "HALVING",
                "value": f"{int(days_left)} 天后",
                "tags": ["BTC", "矿业"],
                "desc": f"预计仍需 {halving['blocks_left']} 个区块"
            })
            
        if ahr999 and "value" in ahr999:
            val = ahr999["value"]
            classification = ahr999.get("classification", "")
            # val < 0.45 抄底, val < 1.2 定投
            color_class = "text-success" if val < 1.2 else "text-warning"
            macro_indicators.append({
                "name_zh": "ahr999 定投指数",
                "name_en": "ahr999 Index",
                "abbr": "AHR999",
                "value": f"{val:.2f}",
                "sub_value": classification,
                "tags": ["BTC", "估值", "链上"],
                "class": color_class,
                "desc": "比特币定投/抄底指标"
            })
            
        if wma200 and "value" in wma200:
            val = wma200["value"]
            ratio = wma200.get("ratio", 0)
            color_class = "text-success" if ratio < 1.2 else ""
            macro_indicators.append({
                "name_zh": "200周均线",
                "name_en": "200WMA",
                "abbr": "200WMA",
                "value": f"${val:,.0f}",
                "sub_value": f"倍数: {ratio:.2f}x",
                "tags": ["BTC", "估值", "链上"],
                "class": color_class,
                "desc": "长期底部的技术支撑线"
            })
            
        if mvrv and "value" in mvrv:
            val = mvrv["value"]
            classification = mvrv.get("classification", "")
            color_class = "text-success" if val < 1.5 else "text-warning" if val > 3.0 else ""
            macro_indicators.append({
                "name_zh": "MVRV Ratio",
                "name_en": "MVRV Ratio",
                "abbr": "MVRV",
                "value": f"{val:.2f}",
                "sub_value": classification,
                "tags": ["BTC", "估值", "链上"],
                "class": color_class,
                "desc": "市值相对其实际已实现成本的比率"
            })
            
        # --- Miners Data ---
        # 挖矿数据（电费 $0.06/kWh）
        if miners_data or True:
            # Provide default mirror to user spec if actual F2Pool scrape is empty/failed
            total = miners_data.get("total_miners", 22) if miners_data else 22
            profitable = miners_data.get("profitable_miners", 13) if miners_data else 13
            shutdown_range = miners_data.get("shutdown_range", "$31,423 ~ $97,576") if miners_data else "$31,423 ~ $97,576"
            best_m = miners_data.get("best_miner", "Antminer U3S23 Hyd.") if miners_data else "Antminer U3S23 Hyd."
            
            macro_indicators.append({
                "name_zh": "盈利矿机数",
                "name_en": "Profitable Miners",
                "abbr": "MINER-P",
                "value": f"{profitable}/{total}台",
                "sub_value": f"电费: $0.06",
                "tags": ["BTC", "矿业"],
                "class": "text-primary",
                "desc": f"关机价范围: {shutdown_range}"
            })
            
            macro_indicators.append({
                "name_zh": "最效率矿机",
                "name_en": "Most Efficient Miner",
                "abbr": "MINER-E",
                "value": str(best_m)[:12] + "..",
                "sub_value": "最低关机价",
                "tags": ["BTC", "矿业"],
                "class": "text-success",
                "desc": str(best_m)
            })

        # --- Stock mNAV Data ---
        for st in [mstr_nav, sbet_nav, bmnr_nav]:
            if st and "ratio" in st:
                symbol = st["symbol"]
                ratio = st["ratio"]
                class_str = st.get("classification", "")
                macro_indicators.append({
                    "name_zh": f"{symbol} 持币溢价",
                    "name_en": f"{symbol} mNAV",
                    "abbr": f"NAV-{symbol}",
                    "value": f"{ratio:.2f}x",
                    "sub_value": class_str,
                    "tags": ["估值", "美股"],
                    "class": st.get("class", "text-warning"),
                    "desc": f"市值相对其实际持有的BTC总价值比率"
                })

        # --- ETF 链上监控卡片 (AUM + 持仓余额) ---
        macro_indicators.extend(etf_onchain_cards)

        return templates.TemplateResponse("market.html", {
            "request": request,
            "market_data": market_data,
            "macro_indicators": macro_indicators,
        })


@app.get("/market/indicator/{indicator_id}")
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

@app.post("/market/add")
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


@app.post("/market/delete")
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


@app.post("/market/reorder")
async def reorder_market_watch(order: list[int] = Form(...)):
    """更新排序"""
    from models import MarketWatch
    
    # Form(...) with list expects multiple values with same key, usually passed as order=1&order=2..
    # Or JSON body. Let's support simple JSON list if possible, but for Form it's tricky.
    # Actually, standard way for sortable is often sending an array of IDs.
    # Let's handle it as a JSON post for simplicity in JS.
    pass 

# Redefine below as standard JSON endpoint
@app.post("/api/market/reorder")
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


@app.post("/market/{id}/toggle_star")
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



# ==================== Crawler Routes ====================

@app.get("/crawler/sources", response_class=HTMLResponse)
async def list_crawl_sources(request: Request):
    """展示硬编码的 ETF 爬虫数据源（只读）"""
    from crawler.scheduler import HARDCODED_SOURCES, _last_run, _running, CRAWL_INTERVAL_MINUTES

    sources = []
    for src in HARDCODED_SOURCES:
        name = src["name"]
        sources.append({
            "name": name,
            "url": src["url"],
            "spider_type": src["spider_type"],
            "interval": CRAWL_INTERVAL_MINUTES,
            "last_run_at": _last_run.get(name),
            "is_running": name in _running,
        })

    return templates.TemplateResponse("crawler_sources.html", {
        "request": request,
        "sources": sources,
    })


@app.get("/system/status", response_class=HTMLResponse)
async def system_status(request: Request):
    """系统状态页 — 从内存读取，不碰数据库"""
    from core.monitor import monitor

    return templates.TemplateResponse("system_status.html", {
        "request": request,
        "api_status_list": monitor.get_latest_status(),
        "recent_logs": monitor.get_recent_logs(50),
    })


@app.get("/crawler/data", response_class=HTMLResponse)
async def view_crawled_data(request: Request):
    """View crawled data"""
    from models.crawler import CrawledData
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CrawledData)
            .order_by(desc(CrawledData.created_at))
            .limit(100)
        )
        items = result.scalars().all()

        # 用 data_type 推断来源名
        SOURCE_NAMES = {
            "btc_etf_flow": "Farside BTC ETF",
            "eth_etf_flow": "Farside ETH ETF",
            "sol_etf_flow": "Farside SOL ETF",
            # Arkham Sources
            "ibit_holdings_btc": "Arkham BlackRock (BTC)",
            "ibit_holdings_eth": "Arkham BlackRock (ETH)",
            "blackrock_total_usd": "Arkham BlackRock (Net Value)",
            "fbtc_holdings_btc": "Arkham Fidelity (BTC)",
            "fbtc_holdings_eth": "Arkham Fidelity (ETH)",
            "fidelity_total_usd": "Arkham Fidelity (Net Value)",
        }
        rows = []
        for d in items:
            rows.append({
                "source": SOURCE_NAMES.get(d.data_type, d.data_type or "Unknown"),
                "type": d.data_type,
                "date": d.date,
                "value": d.value,
                "created_at": d.created_at,
            })

        return templates.TemplateResponse("crawled_data.html", {

            "request": request,
            "data": rows
        })
# ==================== API 路由 ====================

@app.get("/api/etf/all")
async def get_all_etf_data(live: bool = False):
    """
    返回所有 ETF 链上持仓数据
    
    - 默认 (live=false): 从数据库读取 Arkham 爬虫最新快照（毫秒级响应）
    - live=true: 实时调用外部 API（耗时 30~60s，慎用）
    
    数据来源:
      - Arkham 爬虫写入的 crawled_data (ibit_holdings_btc 等)
      - yfinance ETF AUM（需 live=true）
      - mempool.space BTC 地址余额（需 live=true）
      - blockscout ETH 地址余额（需 live=true）
    """
    from models.crawler import CrawledData

    if live:
        # 实时调用外部 API（耗时较长）
        from data_collectors.etf_onchain_collector import etf_onchain_collector
        try:
            data = await etf_onchain_collector.get_all()
            return {"status": "ok", "source": "live", "data": data}
        except Exception as e:
            logger.error(f"ETF live fetch error: {e}")
            return {"status": "error", "message": str(e)}

    # 默认：从数据库读取最新爬虫快照（快速）
    ETF_DB_TYPES = [
        "ibit_holdings_btc", "ibit_holdings_eth", "blackrock_total_usd",
        "fbtc_holdings_btc", "fbtc_holdings_eth", "fidelity_total_usd",
        "btc_etf_flow", "eth_etf_flow", "sol_etf_flow",
    ]
    ETF_LABELS = {
        "ibit_holdings_btc":  {"name": "IBIT 链上BTC持仓",   "unit": "BTC",  "entity": "BlackRock"},
        "ibit_holdings_eth":  {"name": "IBIT 链上ETH持仓",   "unit": "ETH",  "entity": "BlackRock"},
        "blackrock_total_usd":{"name": "贝莱德 链上总规模",  "unit": "USD",  "entity": "BlackRock"},
        "fbtc_holdings_btc":  {"name": "FBTC 链上BTC持仓",   "unit": "BTC",  "entity": "Fidelity"},
        "fbtc_holdings_eth":  {"name": "FBTC 链上ETH持仓",   "unit": "ETH",  "entity": "Fidelity"},
        "fidelity_total_usd": {"name": "富达 链上总规模",     "unit": "USD",  "entity": "Fidelity"},
        "btc_etf_flow":       {"name": "BTC ETF 当日净流入", "unit": "USD",  "entity": "Farside"},
        "eth_etf_flow":       {"name": "ETH ETF 当日净流入", "unit": "USD",  "entity": "Farside"},
        "sol_etf_flow":       {"name": "SOL ETF 当日净流入", "unit": "USD",  "entity": "Farside"},
    }

    result = {}
    async with AsyncSessionLocal() as db:
        for dtype in ETF_DB_TYPES:
            row = await db.execute(
                select(CrawledData)
                .where(CrawledData.data_type == dtype)
                .order_by(desc(CrawledData.date), desc(CrawledData.created_at))
                .limit(1)
            )
            row = row.scalar_one_or_none()
            label = ETF_LABELS.get(dtype, {})
            result[dtype] = {
                "name":       label.get("name", dtype),
                "unit":       label.get("unit", ""),
                "entity":     label.get("entity", ""),
                "value":      row.value if row else None,
                "date":       row.date.isoformat() if row and row.date else None,
                "updated_at": row.created_at.isoformat() if row and row.created_at else None,
                "available":  row is not None,
            }

    return {"status": "ok", "source": "db", "data": result}

@app.get("/api/price/{symbol}")
async def get_price(symbol: str):
    """获取价格 API"""
    from data_collectors import binance_collector
    data = await binance_collector.get_24h_ticker(f"{symbol}USDT")
    return data or {"error": "Unable to fetch price"}


@app.get("/api/strategies")
async def api_list_strategies():
    """策略列表 API"""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Strategy))
        strategies = result.scalars().all()
        
        return [
            {
                "id": s.id,
                "name": s.name,
                "type": s.type,
                "status": s.status,
                "symbol": s.symbol,
                "last_signal": s.last_signal,
                "last_conviction_score": s.last_conviction_score,
            }
            for s in strategies
        ]


@app.get("/api/scheduler/jobs")
async def api_scheduler_jobs():
    """调度任务列表 API"""
    return scheduler.get_jobs_info()


# ==================== Phase 1 新增 API ====================

@app.get("/api/risk/status")
async def api_risk_status():
    """风控状态 API (Phase 1D)"""
    return scheduler.get_risk_status()


@app.post("/api/risk/release-circuit-breaker")
async def api_release_circuit_breaker():
    """手动解除熔断 API (Phase 1D)"""
    success = scheduler.release_circuit_breaker()
    if success:
        return {"status": "ok", "message": "熔断已手动解除"}
    else:
        return {"status": "noop", "message": "熔断未激活，无需解除"}


@app.get("/api/risk/events")
async def api_risk_events(limit: int = 50):
    """风控事件历史 API (Phase 1E)"""
    from models import RiskEvent
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(RiskEvent).order_by(desc(RiskEvent.created_at)).limit(limit)
        )
        events = result.scalars().all()
        return [
            {
                "id": e.id,
                "event_type": e.event_type,
                "strategy_id": e.strategy_id,
                "message": e.message,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in events
        ]


@app.get("/api/portfolio/snapshots")
async def api_portfolio_snapshots(limit: int = 168):
    """
    组合净值快照 API (Phase 1E)
    默认返回最近 168 个点 (7天 x 24小时/天, 每小时一个快照)
    """
    from models import PortfolioSnapshot
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PortfolioSnapshot)
            .order_by(desc(PortfolioSnapshot.snapshot_at))
            .limit(limit)
        )
        snapshots = result.scalars().all()
        return [
            {
                "total_value": float(s.total_value),
                "total_pnl_percent": float(s.total_pnl_percent),
                "drawdown_from_peak": float(s.drawdown_from_peak),
                "circuit_breaker_active": s.circuit_breaker_active,
                "snapshot_at": s.snapshot_at.isoformat() if s.snapshot_at else None,
            }
            for s in reversed(snapshots)  # 按时间正序返回 (旧->新)
        ]


# ===================================================================
# Data Service API  —  供 OpenClaw Agent 调用
# Base: /api/v1/data
# ===================================================================

@app.get("/api/v1/data/snapshot")
async def api_data_snapshot():
    """
    [Agent 主入口] 综合市场快照

    将行情、宏观指标和情绪数据聚合为单次响应。
    Agent 通常只需调用这一个接口即可获得完整的市场上下文。

    返回结构:
    {
        "generated_at": "ISO8601",
        "markets": [ {symbol, price, change_pct_24h, ...} ],
        "macro": {
            "fed_rate": float|null,
            "treasury_10y": float|null,
            "dxy": float|null,
            "m2_growth_yoy": float|null,
            "fear_greed": { value, classification },
            "stablecoin_supply_b": float|null,
            "etf_flows": { btc, eth, sol }  # 最新一日 (USD)
        },
        "data_freshness": { key: ISO8601 }  # 各数据源最后更新时间
    }
    """
    from datetime import datetime, timezone
    from models.market_cache import MarketCache
    from models.crawler import CrawledData
    from data_collectors.fred_collector import fred_collector
    from data_collectors import fear_greed_collector, stablecoin_collector

    result_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "markets": [],
        "macro": {},
        "data_freshness": {},
    }

    async with AsyncSessionLocal() as db:
        # ── 1. 行情 (优先从 Binance 获取实时数据，失败则回退缓存) ────────────────────
        from models import MarketWatch
        from data_collectors import binance_collector
        import asyncio

        watched_rows = await db.execute(select(MarketWatch))
        watched_symbols = [w.symbol for w in watched_rows.scalars().all()]
        
        markets_data = []
        oldest_cache_time = None

        if watched_symbols:
            tasks = [binance_collector.get_24h_ticker(f"{sym}USDT") for sym in watched_symbols]
            live_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for symbol, live_data in zip(watched_symbols, live_results):
                if not isinstance(live_data, Exception) and live_data is not None:
                    # 实时获取成功
                    markets_data.append({
                        "symbol": symbol,
                        "price": live_data["price"],
                        "change_24h": 0, # get_24h_ticker returns percent in price_change_24h
                        "change_pct_24h": live_data.get("price_change_24h", 0),
                        "high_24h": live_data.get("high_24h"),
                        "low_24h": live_data.get("low_24h"),
                        "volume_24h": live_data.get("volume_24h"),
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                        "is_live": True
                    })
                else:
                    # 获取失败时回退到数据库缓存
                    cached_row = await db.get(MarketCache, symbol)
                    if cached_row:
                        data_dict = cached_row.to_dict()
                        data_dict["is_live"] = False
                        markets_data.append(data_dict)
                        # 记录最老的缓存时间
                        if oldest_cache_time is None or (cached_row.updated_at and cached_row.updated_at < oldest_cache_time):
                            oldest_cache_time = cached_row.updated_at

        result_data["markets"] = markets_data
        result_data["data_freshness"]["markets"] = oldest_cache_time.isoformat() if oldest_cache_time else datetime.now(timezone.utc).isoformat()

        # ── 2. ETF 净流入 (从爬虫数据库读最新一条) ────────────────────
        async def _latest_flow(data_type: str):
            r = await db.execute(
                select(CrawledData)
                .where(CrawledData.data_type == data_type)
                .order_by(desc(CrawledData.date), desc(CrawledData.created_at))
                .limit(1)
            )
            return r.scalar_one_or_none()

        btc_flow = await _latest_flow("btc_etf_flow")
        eth_flow = await _latest_flow("eth_etf_flow")
        sol_flow = await _latest_flow("sol_etf_flow")

        result_data["macro"]["etf_flows"] = {
            "btc": {
                "value_usd": float(btc_flow.value) if btc_flow else None,
                "date": btc_flow.date.strftime("%Y-%m-%d") if btc_flow else None,
            },
            "eth": {
                "value_usd": float(eth_flow.value) if eth_flow else None,
                "date": eth_flow.date.strftime("%Y-%m-%d") if eth_flow else None,
            },
            "sol": {
                "value_usd": float(sol_flow.value) if sol_flow else None,
                "date": sol_flow.date.strftime("%Y-%m-%d") if sol_flow else None,
            },
        }

    # ── 3. FRED 宏观指标 ────────────────────────────────────────────
    try:
        macro_raw = await fred_collector.get_macro_data()
        result_data["macro"]["fed_rate"] = macro_raw.get("fed_funds_rate")
        result_data["macro"]["treasury_10y"] = macro_raw.get("treasury_10y")
        result_data["macro"]["dxy"] = macro_raw.get("dollar_index")
        result_data["macro"]["m2_growth_yoy"] = macro_raw.get("m2_growth_yoy")
        result_data["data_freshness"]["fred"] = datetime.now(timezone.utc).isoformat()
    except Exception as e:
        logger.warning(f"FRED data fetch failed in snapshot: {e}")
        result_data["macro"]["fed_rate"] = None
        result_data["macro"]["treasury_10y"] = None
        result_data["macro"]["dxy"] = None
        result_data["macro"]["m2_growth_yoy"] = None

    # ── 4. 恐惧贪婪指数 ──────────────────────────────────────────────
    try:
        fg = await fear_greed_collector.get_current()
        if fg:
            value = int(fg.get("value", 50))
            # collector 返回 value_classification，不是 classification
            api_classification = fg.get("value_classification") or fg.get("classification")
            # 以 value 为准，服务端兜底计算（防止 API 返回错误分类）
            if value <= 24:
                computed = "Extreme Fear"
            elif value <= 44:
                computed = "Fear"
            elif value <= 55:
                computed = "Neutral"
            elif value <= 74:
                computed = "Greed"
            else:
                computed = "Extreme Greed"
            result_data["macro"]["fear_greed"] = {
                "value": value,
                "classification": computed,  # 始终用服务端计算值
            }
            result_data["data_freshness"]["fear_greed"] = datetime.now(timezone.utc).isoformat()
        else:
            result_data["macro"]["fear_greed"] = None
    except Exception as e:
        logger.warning(f"Fear & Greed fetch failed in snapshot: {e}")
        result_data["macro"]["fear_greed"] = None

    # ── 5. 稳定币市值 ──────────────────────────────────────────────
    try:
        supply = await stablecoin_collector.get_latest_supply()
        result_data["macro"]["stablecoin_supply_b"] = round(supply / 1e9, 2) if supply else None
    except Exception as e:
        logger.warning(f"Stablecoin supply fetch failed in snapshot: {e}")
        result_data["macro"]["stablecoin_supply_b"] = None

    # ── 6. Onchain & Valuation Data ──────────────────────────────────────
    try:
        from data_collectors.onchain_collector import onchain_collector
        from data_collectors.mining_collector import mining_collector
        from data_collectors.stock_nav_collector import stock_collector

        # Mempool & Binance derived
        hashrate = await onchain_collector.get_hashrate()
        halving = await onchain_collector.get_halving_info()
        ahr999 = await onchain_collector.get_ahr999()
        wma200 = await onchain_collector.get_200wma()
        mvrv = await onchain_collector.get_mvrv_ratio()

        result_data["macro"]["hashrate"] = hashrate.get("value") if hashrate else None
        result_data["macro"]["halving_days"] = round(halving.get("minutes_left", 0) / 60 / 24, 1) if halving and "minutes_left" in halving else None
        result_data["macro"]["ahr999"] = ahr999.get("value") if ahr999 else None
        result_data["macro"]["wma200"] = wma200.get("value") if wma200 else None
        result_data["macro"]["mvrv_ratio"] = mvrv.get("value") if mvrv else None

        # Mining
        miners = await mining_collector.get_miners_data()
        result_data["macro"]["miners_profitable"] = miners.get("profitable_miners") if miners else None
        result_data["macro"]["miners_total"] = miners.get("total_miners") if miners else None

        # Stock NAVs
        mstr_nav = await stock_collector.get_nav_ratio("MSTR", result_data["markets"][0]["price"] if result_data["markets"] else 0)
        result_data["macro"]["mstr_mnav"] = mstr_nav.get("ratio") if mstr_nav else None

    except Exception as e:
        logger.warning(f"On-chain extension fetch failed in snapshot: {e}")

    return result_data


@app.get("/api/v1/data/klines/{symbol}")
async def api_data_klines(symbol: str, timeframe: str = "1h", limit: int = 100, skip_sync: bool = False):
    """
    [Agent 细粒度接口] K线历史数据

    优先从本地数据库读取（含自动增量同步），数据更全更快。
    首次请求某 symbol/timeframe 时会触发全量回填（约 10-60 秒，取决于深度）。

    Args:
        symbol:    币种代码，e.g. BTC、ETH（不含 USDT）
        timeframe: K 线周期，支持 1m/5m/15m/1h/4h/1d
        limit:     返回条数，默认 100，最大 500
        skip_sync: 跳过增量同步，直接读本地缓存（适合高频调用场景）
    """
    from data_collectors.kline_sync import kline_sync

    symbol = symbol.upper()
    limit = min(limit, 500)
    pair = f"{symbol}USDT"

    try:
        async with AsyncSessionLocal() as db:
            klines = await kline_sync.get_klines(
                db=db,
                symbol=pair,
                interval=timeframe,
                limit=limit,
                sync_first=(not skip_sync),
            )

        if not klines:
            return {"symbol": symbol, "timeframe": timeframe, "klines": [], "error": "No data", "source": "local_db"}

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "count": len(klines),
            "source": "local_db",
            "klines": klines,
        }
    except Exception as e:
        logger.error(f"Klines fetch failed for {symbol}/{timeframe}: {e}")
        # Fallback 到 Binance 直接拉取
        try:
            from data_collectors import binance_collector
            klines = await binance_collector.get_klines(pair, timeframe, limit=limit)
            return {
                "symbol": symbol, "timeframe": timeframe,
                "count": len(klines), "source": "binance_live",
                "klines": klines,
            }
        except Exception as e2:
            return {"symbol": symbol, "timeframe": timeframe, "klines": [], "error": str(e2)}


@app.post("/api/v1/data/signals")
async def api_data_store_signal(request: Request):
    """
    [Agent 写入接口] 存储 Agent 决策信号

    Agent 完成分析后调用此接口记录决策，用于审计追踪和复盘。

    请求体 (JSON):
    {
        "agent_id": "str (optional)",
        "strategy_name": "str (optional)",
        "symbol": "BTC",
        "action": "BUY|SELL|HOLD",
        "conviction": 75.0,
        "price_at_signal": 45000.0,
        "reason": "str (optional)",
        "raw_analysis": {} (optional),
        "stop_loss": 42000.0 (optional),
        "take_profit": 50000.0 (optional)
    }
    """
    from models.agent_signal import AgentSignal
    from decimal import Decimal

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    symbol = (body.get("symbol") or "").upper()
    action = (body.get("action") or "").upper()

    if not symbol:
        raise HTTPException(status_code=400, detail="'symbol' is required")
    if action not in ("BUY", "SELL", "HOLD"):
        raise HTTPException(status_code=400, detail="'action' must be BUY, SELL, or HOLD")

    price_raw = body.get("price_at_signal")

    async with AsyncSessionLocal() as db:
        signal = AgentSignal(
            agent_id=body.get("agent_id"),
            strategy_name=body.get("strategy_name"),
            symbol=symbol,
            action=action,
            conviction=body.get("conviction"),
            price_at_signal=Decimal(str(price_raw)) if price_raw is not None else None,
            reason=body.get("reason"),
            raw_analysis=body.get("raw_analysis"),
            stop_loss=body.get("stop_loss"),
            take_profit=body.get("take_profit"),
        )
        db.add(signal)
        await db.commit()
        await db.refresh(signal)

    return {"status": "ok", "id": signal.id, "symbol": symbol, "action": action}


@app.get("/api/v1/data/signals")
async def api_data_list_signals(symbol: str = None, limit: int = 50):
    """
    [Agent 读取接口] 查询历史信号记录

    Args:
        symbol: 可选，按币种过滤
        limit: 返回条数，默认 50
    """
    from models.agent_signal import AgentSignal

    async with AsyncSessionLocal() as db:
        query = select(AgentSignal).order_by(desc(AgentSignal.created_at)).limit(limit)
        if symbol:
            query = query.where(AgentSignal.symbol == symbol.upper())
        result = await db.execute(query)
        signals = result.scalars().all()

    return [s.to_dict() for s in signals]


# ===================================================================
# TA Analysis API  —  多时间框架技术分析接口
# Base: /api/v1/ta
# ===================================================================

@app.post("/api/v1/ta/analyze")
async def api_ta_analyze(request: Request):
    """
    [Agent TA 分析接口] 多时间框架技术分析

    执行完整的多时间框架 TA 分析，返回信号、信念分数、止损/止盈和各维度明细。
    K 线数据优先从本地数据库读取（含自动增量同步），首次使用某 symbol 时会自动回填历史。

    请求体 (JSON):
    {
        "symbol":     "BTC",              # 币种代码（必填）
        "timeframes": ["15m","1h","4h"], # 时间框架（可选，默认三框架）
        "klines_limit": 300,              # 每框架加载 K 线数量（可选，默认 300）
        "buy_threshold":  65,             # BUY 触发阈值（可选）
        "sell_threshold": 35,             # SELL 触发阈值（可选）
        "atr_stop_mult":  2.0,            # ATR 止损倍数（可选）
        "atr_target_mult": 3.0            # ATR 止盈倍数（可选）
    }

    响应体:
    {
        "symbol": "BTC",
        "signal": "BUY",          # BUY / SELL / HOLD
        "conviction": 74.5,       # 0-100，信念分
        "grade": "A",             # A/B/C 信号质量
        "current_price": 96420.0,
        "stop_loss": 93850.0,
        "take_profit": 101200.0,
        "risk_reward": 1.5,
        "position_size": 0.175,   # 建议仓位比例
        "timeframes_used": ["15m","1h","4h"],
        "score_by_tf": {"1h": 72.3, "4h": 78.1, "15m": 65.2},
        "indicators": {           # 各时间框架指标快照
            "1h": {
                "ema_9":..., "ema_21":..., "ema_50":..., "ema_200":...,
                "rsi":..., "stoch_rsi":{"k":...,"d":...},
                "macd":{"macd_line":..., "signal_line":..., "histogram":..., "cross":...},
                "bollinger":{"upper":...,"lower":...,"percent_b":...},
                "atr":...,
                "volume":{"volume_ratio":...,"trend":...},
                "trend_structure":{"structure":...,"strength":...},
                "candle_patterns":[...]
            }
        },
        "reasons": ["[4h]EMA多头排列", "[1h]MACD金叉🟢", ...],
        "analyzed_at": "ISO8601"
    }
    """
    from datetime import timezone
    from strategies.ta_strategy import TAStrategy

    # ── 解析请求 ──────────────────────────────────────────────
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    symbol = (body.get("symbol") or "BTC").upper().strip()
    timeframes = body.get("timeframes") or ["15m", "1h", "4h"]

    # 验证时间框架
    valid_tfs = {"1m", "5m", "15m", "1h", "4h", "1d"}
    invalid = [tf for tf in timeframes if tf not in valid_tfs]
    if invalid:
        raise HTTPException(status_code=400, detail=f"Invalid timeframes: {invalid}. Valid: {sorted(valid_tfs)}")

    # 构造策略配置（覆盖用户传入的参数）
    config = TAStrategy.get_default_config()
    config["symbol"] = symbol
    config["timeframes"] = timeframes
    if "klines_limit" in body:     config["klines_limit"] = int(body["klines_limit"])
    if "buy_threshold" in body:    config["buy_threshold"] = float(body["buy_threshold"])
    if "sell_threshold" in body:   config["sell_threshold"] = float(body["sell_threshold"])
    if "atr_stop_mult" in body:    config["atr_stop_mult"] = float(body["atr_stop_mult"])
    if "atr_target_mult" in body:  config["atr_target_mult"] = float(body["atr_target_mult"])

    # ── 执行分析 ──────────────────────────────────────────────
    try:
        strategy = TAStrategy(config)
        sig = await strategy.analyze()
    except Exception as e:
        logger.error(f"TA analyze error for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")

    # ── 组装响应：从 metadata 取详细指标 ─────────────────────
    meta = sig.metadata or {}

    # 获取各时间框架指标快照（精简版，避免响应过大）
    indicators_snapshot = {}
    try:
        from data_collectors.kline_sync import kline_sync
        from indicators.calculator import indicator_calculator as calc

        pair = f"{symbol}USDT"
        async with AsyncSessionLocal() as db:
            tf_data = await kline_sync.get_multi_timeframe_klines(
                db=db, symbol=pair,
                timeframes=timeframes,
                limit=config["klines_limit"],
                sync_first=False,   # 已经在 analyze() 内同步过，这里不再重复
            )

        for tf, klines in tf_data.items():
            if not klines:
                continue
            ind = calc.calculate_all(klines)
            # 只返回关键字段（完整 klines 太大）
            indicators_snapshot[tf] = {
                "current_price": ind.get("current_price"),
                "ema_9":  round(ind.get("ema_9", 0), 2),
                "ema_21": round(ind.get("ema_21", 0), 2),
                "ema_50": round(ind.get("ema_50", 0), 2),
                "ema_200": round(ind.get("ema_200", 0), 2),
                "rsi":    round(ind.get("rsi", 50), 1),
                "stoch_rsi": {
                    "k": round(ind.get("stoch_rsi", {}).get("k", 50), 1),
                    "d": round(ind.get("stoch_rsi", {}).get("d", 50), 1),
                },
                "macd": {
                    "macd_line":   round(ind.get("macd", {}).get("macd_line", 0), 4),
                    "signal_line": round(ind.get("macd", {}).get("signal_line", 0), 4),
                    "histogram":   round(ind.get("macd", {}).get("histogram", 0), 4),
                    "trend":  ind.get("macd", {}).get("trend"),
                    "cross":  ind.get("macd", {}).get("cross"),
                },
                "bollinger": {
                    "upper":     round(ind.get("bollinger", {}).get("upper", 0), 2),
                    "middle":    round(ind.get("bollinger", {}).get("middle", 0), 2),
                    "lower":     round(ind.get("bollinger", {}).get("lower", 0), 2),
                    "percent_b": round(ind.get("bollinger", {}).get("percent_b", 0.5), 3),
                    "squeeze":   ind.get("bollinger", {}).get("squeeze", False),
                },
                "atr": round(ind.get("atr", 0), 2),
                "volume": {
                    "volume_ratio": round(ind.get("volume", {}).get("volume_ratio", 1), 2),
                    "trend":        ind.get("volume", {}).get("trend"),
                },
                "trend_structure": {
                    "structure": ind.get("trend_structure", {}).get("structure"),
                    "strength":  round(ind.get("trend_structure", {}).get("strength", 50), 1),
                },
                "candle_patterns": ind.get("candle_patterns", []),
            }
    except Exception as e:
        logger.warning(f"Failed to build indicators snapshot: {e}")

    # ── 获取实时价格（覆盖K线收盘价，避免价格滞后）─────────────────
    # current_price 来自 closes[-1]，即最近一根已闭合K线的收盘价，
    # 可能比实时价格滞后 1 个K线周期（如 1h 时可能滞后 ~1小时）。
    # 这里额外调用 Binance ticker 获取实时价格来覆盖它。
    live_price = meta.get("current_price")  # 默认回退到K线价格
    try:
        from data_collectors import binance_collector
        ticker_live = await binance_collector.get_24h_ticker(f"{symbol}USDT")
        if ticker_live and ticker_live.get("price"):
            live_price = ticker_live["price"]
    except Exception as e_price:
        logger.warning(f"Failed to fetch live price for {symbol}, using kline close: {e_price}")

    return {
        "symbol":         symbol,
        "signal":         sig.signal.value.upper(),
        "conviction":     sig.conviction_score,
        "grade":          meta.get("grade", "B"),
        "current_price":  live_price,
        "stop_loss":      sig.stop_loss,
        "take_profit":    sig.take_profit,
        "risk_reward":    meta.get("risk_reward"),
        "position_size":  sig.position_size,
        "atr":            meta.get("atr"),
        "timeframes_used": timeframes,
        "score_by_tf":    meta.get("score_by_tf", {}),
        "indicators":     indicators_snapshot,
        "reasons":        sig.reason.split("; ") if sig.reason else [],
        "analyzed_at":    datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/v1/ta/klines-status")
async def api_ta_klines_status():
    """
    K 线本地数据库覆盖情况查询

    返回各 symbol/timeframe 在本地数据库中的数据条数和时间范围。
    用于确认数据是否已经回填完成。
    """
    from models.kline_cache import KlineCache
    from sqlalchemy import func
    from datetime import timezone

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(
                KlineCache.symbol,
                KlineCache.interval,
                func.count(KlineCache.id).label("count"),
                func.min(KlineCache.open_time).label("oldest_ms"),
                func.max(KlineCache.open_time).label("newest_ms"),
            ).group_by(KlineCache.symbol, KlineCache.interval)
            .order_by(KlineCache.symbol, KlineCache.interval)
        )
        rows = result.all()

    status = []
    for row in rows:
        oldest = datetime.fromtimestamp(row.oldest_ms / 1000, tz=timezone.utc).isoformat() if row.oldest_ms else None
        newest = datetime.fromtimestamp(row.newest_ms / 1000, tz=timezone.utc).isoformat() if row.newest_ms else None
        status.append({
            "symbol":   row.symbol,
            "interval": row.interval,
            "count":    row.count,
            "oldest":   oldest,
            "newest":   newest,
        })

    return {"klines_db_status": status, "total_entries": sum(r["count"] for r in status)}


# ==================== DeFi Lab ====================

@app.get("/defi-lab", response_class=HTMLResponse)
async def defi_lab(request: Request):
    """DeFi 实验室 - 双币双向回测与套利分析"""
    return templates.TemplateResponse("defi_lab.html", {
        "request": request,
        "now": datetime.utcnow()
    })

@app.get("/api/defi/pool-metadata/{network}/{address}")
async def get_pool_metadata(network: str, address: str):
    from data_collectors.gecko_terminal import gecko_terminal
    return await gecko_terminal.get_pool_metadata(network, address)

@app.get("/api/defi/pool-history/{network}/{address}")
async def get_pool_history(network: str, address: str, limit: int = 1000, start: str = None, end: str = None):
    from data_collectors.gecko_terminal import gecko_terminal
    from datetime import datetime, timezone
    
    def parse_iso(s: str):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None
    
    history = await gecko_terminal.get_pool_history(
        network, address,
        limit=limit,
        start_date=parse_iso(start),
        end_date=parse_iso(end)
    )
    return {"data": history}


class BacktestRequest(BaseModel):
    """双币轮动回测请求参数"""
    # Asset A — 基础资产 (被轮动的主资产)
    asset_a_source: str = "binance"          # "binance" 或 "gecko"
    asset_a_symbol: str = "ETHUSDT"          # Binance symbol 或 Gecko pool address
    asset_a_network: Optional[str] = None    # gecko 时必填 (e.g. "eth")
    asset_a_label: Optional[str] = None      # 显示名称 (缺省自动推断)

    # Asset B — 对标资产
    asset_b_source: str = "binance"
    asset_b_symbol: str = "BTCUSDT"
    asset_b_network: Optional[str] = None
    asset_b_label: Optional[str] = None

    # 时间段
    start_date: Optional[str] = None         # ISO 8601, e.g. "2024-01-01"
    end_date: Optional[str] = None           # ISO 8601, e.g. "2025-01-01"

    # 策略模式
    mode: str = "SMA"                        # "SMA" 或 "FIXED"
    window_size: int = 30                    # SMA 窗口天数
    std_dev_mult: float = 2.0               # 布林带倍数
    use_ema: bool = True                     # 用 EMA 代替 SMA 均值线
    min_ratio: Optional[float] = None        # FIXED 模式: 下轨比率
    max_ratio: Optional[float] = None        # FIXED 模式: 上轨比率
    step_size: float = 50.0                  # 单次交易仓位 % (1–100)
    no_loss_sell: bool = True                # 买回 A (卖出 B) 时必须不亏损


@app.post("/api/defi/backtest")
async def run_pair_backtest(req: BacktestRequest):
    """
    双币统计套利回测 API
    
    支持从 Binance (CEX K 线) 或 GeckoTerminal (DEX 池子) 获取价格序列，
    根据 SMA/EMA 均值回归或固定阈值策略模拟轮动交易，返回完整回测结果。
    """
    import numpy as np
    from datetime import datetime
    from data_collectors.gecko_terminal import gecko_terminal
    from data_collectors.binance import binance_collector

    def parse_iso(s):
        if not s:
            return None
        try:
            return datetime.fromisoformat(s.replace("Z", "+00:00")).replace(tzinfo=None)
        except Exception:
            return None

    start_dt = parse_iso(req.start_date)
    end_dt = parse_iso(req.end_date)
    
    # ── 1. 拉取价格序列 ────────────────────────────────────────────────────
    async def fetch_series(source, symbol, network, start_dt, end_dt):
        if source == "binance":
            start_ts = int(start_dt.timestamp() * 1000) if start_dt else None
            end_ts = int(end_dt.timestamp() * 1000) if end_dt else int(datetime.utcnow().timestamp() * 1000)
            if not start_ts:
                # 如果没传开始时间，默认拉取最多 20 年的行情数据 (币安 2017 成立，所以实际拉取全量)
                start_ts = int((datetime.utcnow().timestamp() - 20 * 365 * 86400) * 1000)
            
            klines = []
            curr_start = start_ts
            limit = 1000
            
            # 使用循环分页，突破 Binance 1000 根单次请求的限制
            while True:
                chunk = await binance_collector.get_klines(
                    symbol=symbol.upper(), interval="1d", limit=limit,
                    start_time=curr_start, end_time=end_ts
                )
                if not chunk:
                    break
                
                klines.extend(chunk)
                if len(chunk) < limit:
                    break
                    
                # 下一次请求的时间起点：最后一条K线的 open_time + 1 天 (86400秒 * 1000)
                last_open = int(chunk[-1]["open_time"].timestamp() * 1000)
                curr_start = last_open + 86400000
                
                if curr_start > end_ts:
                    break
            series = [
                {"ts": int(k["open_time"].timestamp() * 1000), "price": k["close"]}
                for k in klines
            ]
        else:
            series = await gecko_terminal.get_pool_history(
                network=network, pool_address=symbol,
                limit=1000, start_date=start_dt, end_date=end_dt
            )
        
        # 按时间过滤
        if start_dt:
            ts_start = int(start_dt.timestamp() * 1000)
            series = [s for s in series if s["ts"] >= ts_start]
        if end_dt:
            ts_end = int(end_dt.timestamp() * 1000)
            series = [s for s in series if s["ts"] <= ts_end]
        
        return sorted(series, key=lambda x: x["ts"])

    try:
        series_a, series_b = await asyncio.gather(
            fetch_series(req.asset_a_source, req.asset_a_symbol, req.asset_a_network, start_dt, end_dt),
            fetch_series(req.asset_b_source, req.asset_b_symbol, req.asset_b_network, start_dt, end_dt),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Data fetch failed: {e}")

    if len(series_a) < 2 or len(series_b) < 2:
        raise HTTPException(status_code=422, detail="Insufficient price data for the given date range")

    # ── 2. 对齐数据 ────────────────────────────────────────────────────────
    map_b = {d["ts"]: d["price"] for d in series_b}
    common = []
    for a in series_a:
        pb = map_b.get(a["ts"])
        if pb and pb > 0 and a["price"] > 0:
            common.append({
                "ts": a["ts"],
                "date": datetime.fromtimestamp(a["ts"] / 1000).strftime("%Y-%m-%d"),
                "priceA": a["price"],
                "priceB": pb,
                "ratio": a["price"] / pb
            })

    if len(common) < max(2, req.window_size):
        raise HTTPException(status_code=422, detail=f"Not enough overlapping data points ({len(common)})")

    # ── 3. 指标计算 ────────────────────────────────────────────────────────
    is_fixed = req.mode == "FIXED"
    window = req.window_size
    k_ema = 2 / (window + 1)
    ema_prev = None

    enriched = []
    for i, d in enumerate(common):
        mean_val = upper = lower = std_dev = None

        if is_fixed:
            mean_val = ((req.min_ratio or 0) + (req.max_ratio or 0)) / 2
            lower = req.min_ratio or 0
            upper = req.max_ratio or float("inf")
        elif i >= window - 1:
            slice_vals = [c["ratio"] for c in common[i - window + 1: i + 1]]
            sma = float(np.mean(slice_vals))
            std_dev = float(np.std(slice_vals))

            if req.use_ema:
                ema_prev = sma if ema_prev is None else d["ratio"] * k_ema + ema_prev * (1 - k_ema)
                mean_val = ema_prev
            else:
                mean_val = sma

            upper = mean_val + req.std_dev_mult * std_dev
            lower = mean_val - req.std_dev_mult * std_dev

        row = {**d, "meanVal": mean_val, "upper": upper, "lower": lower,
               "stdDev": std_dev,
               "discountBps": round((mean_val - d["ratio"]) / mean_val * 10000) if mean_val else 0}
        enriched.append(row)

    # ── 4. 轮动模拟 ────────────────────────────────────────────────────────
    step_pct = max(0.01, min(1.0, req.step_size / 100))
    units_a, units_b = 10.0, 0.0
    invested_a = 0.0
    pos_state = 1.0
    events, history = [], []

    for i, d in enumerate(enriched):
        if not is_fixed and i < window:
            continue
        if d["upper"] is None:
            continue

        signal_sell_a = d["ratio"] > d["upper"]
        signal_buy_a  = d["ratio"] < d["lower"]
        dev = ((d["ratio"] - d["meanVal"]) / d["meanVal"] * 10000) if d["meanVal"] else 0

        action = realized_gain = trade_amt_a = 0

        if signal_sell_a and pos_state > 0.001:
            reduce = min(pos_state, step_pct)
            if reduce > 0.001:
                sell_a = units_a * (reduce / pos_state)
                buy_b  = sell_a * d["ratio"]
                units_a -= sell_a; units_b += buy_b
                invested_a += sell_a; pos_state -= reduce
                action = "Sell A"; trade_amt_a = sell_a

        elif signal_buy_a and pos_state < 0.999:
            increase = min(1 - pos_state, step_pct)
            if increase > 0.001:
                total_val_a = units_a + units_b / d["ratio"]
                cost_b = total_val_a * increase * d["ratio"]
                actual_cost_b = min(units_b, cost_b)
                actual_buy_a  = actual_cost_b / d["ratio"]

                gain = 0.0
                cost_basis = 0.0
                if units_b > 0 and invested_a > 0:
                    frac = actual_cost_b / units_b
                    cost_basis = invested_a * frac
                    gain = (actual_buy_a - cost_basis) / cost_basis if cost_basis else 0

                if req.no_loss_sell and gain < -0.0001:
                    pass
                else:
                    invested_a -= cost_basis
                    units_b -= actual_cost_b; units_a += actual_buy_a
                    pos_state += increase
                    action = "Buy A"; trade_amt_a = actual_buy_a; realized_gain = gain

        if action:
            events.append({
                "date": d["date"], "type": action,
                "ratio": round(d["ratio"], 6),
                "mean": round(d["meanVal"], 6) if d["meanVal"] else None,
                "deviationBps": round(dev),
                "amount": round(trade_amt_a, 4),
                "gainPct": round(realized_gain * 100, 4) if action == "Buy A" else None,
                "posState": round(pos_state, 3),
                "unitsA": round(units_a, 4),
                "unitsB": round(units_b, 4),
            })

        val_in_a = units_a + units_b / d["ratio"]
        history.append({
            "date": d["date"],
            "valInA": round(val_in_a, 4),
            "cumReturn": round((val_in_a - 10) / 10 * 100, 3),
            "posState": round(pos_state, 3),
        })

    # ── 5. 汇总统计 ────────────────────────────────────────────────────────
    final_return_pct = history[-1]["cumReturn"] if history else 0.0
    n_days = len(history)
    annualized_pct = (final_return_pct / n_days * 365) if n_days > 0 else 0.0
    buy_events  = [e for e in events if e["type"] == "Buy A" and e["gainPct"] is not None]
    win_events  = [e for e in buy_events if e["gainPct"] > 0]
    avg_gain    = float(np.mean([e["gainPct"] for e in buy_events])) if buy_events else 0.0
    total_trades = len(events)
    label_a = req.asset_a_label or req.asset_a_symbol
    label_b = req.asset_b_label or req.asset_b_symbol
    current_ratio = enriched[-1]["ratio"] if enriched else None

    return {
        "summary": {
            "asset_a": label_a,
            "asset_b": label_b,
            "pair": f"{label_a} / {label_b}",
            "mode": req.mode,
            "start": common[0]["date"] if common else None,
            "end":   common[-1]["date"] if common else None,
            "data_points": len(common),
            "current_ratio": round(current_ratio, 6) if current_ratio else None,
            "final_return_pct": round(final_return_pct, 2),
            "annualized_pct": round(annualized_pct, 2),
            "total_trades": total_trades,
            "buy_trades": len(buy_events),
            "win_rate_pct": round(len(win_events) / len(buy_events) * 100, 1) if buy_events else None,
            "avg_gain_per_trade_pct": round(avg_gain, 3),
            "current_holding": "A" if (history[-1]["posState"] if history else 1) > 0.5 else "B",
        },
        "events": events[-50:],      # 最近 50 条交易记录
        "history": history[-365:],   # 最近 365 天净值曲线
        "params": {
            "mode": req.mode,
            "window_size": req.window_size if not is_fixed else None,
            "std_dev_mult": req.std_dev_mult if not is_fixed else None,
            "use_ema": req.use_ema if not is_fixed else None,
            "min_ratio": req.min_ratio if is_fixed else None,
            "max_ratio": req.max_ratio if is_fixed else None,
            "step_size_pct": req.step_size,
            "no_loss_sell": req.no_loss_sell,
        }
    }
