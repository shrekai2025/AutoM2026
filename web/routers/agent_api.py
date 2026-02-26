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

@router.get("/api/price/{symbol}")
async def get_price(symbol: str):
    """获取价格 API"""
    from data_collectors import binance_collector
    data = await binance_collector.get_24h_ticker(f"{symbol}USDT")
    return data or {"error": "Unable to fetch price"}

@router.get("/api/risk/status")
async def api_risk_status():
    """风控状态 API (Phase 1D)"""
    return scheduler.get_risk_status()

@router.post("/api/risk/release-circuit-breaker")
async def api_release_circuit_breaker():
    """手动解除熔断 API (Phase 1D)"""
    success = scheduler.release_circuit_breaker()
    if success:
        return {"status": "ok", "message": "熔断已手动解除"}
    else:
        return {"status": "noop", "message": "熔断未激活，无需解除"}

@router.get("/api/risk/events")
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

@router.get("/api/portfolio/snapshots")
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

@router.get("/api/v1/data/snapshot")
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

@router.get("/api/v1/data/klines/{symbol}")
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

@router.post("/api/v1/data/signals")
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

@router.get("/api/v1/data/signals")
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

