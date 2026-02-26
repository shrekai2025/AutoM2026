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
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
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
    # 释放共享浏览器池
    try:
        from crawler.scheduler import shutdown_browser_pool
        await shutdown_browser_pool()
    except Exception:
        pass
    # 释放共享 HTTP Client
    try:
        from core.http_client import SharedHTTPClient
        await SharedHTTPClient.close()
    except Exception:
        pass
    logger.info("Application stopped")


app = FastAPI(
    title="AutoM2026",
    description="简化版加密货币策略交易系统",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None,  # 禁用默认 Swagger UI，使用自定义文档页
    redoc_url=None,
)

# 设置模板
app.mount("/static", StaticFiles(directory="web/static"), name="static")
templates = Jinja2Templates(directory="web/templates")

# --- Route Includes ---
from web.routers import dashboard, market, strategies, agent_api, ta_api, defi, crawler
app.include_router(dashboard.router)
app.include_router(market.router)
app.include_router(strategies.router)
app.include_router(agent_api.router)
app.include_router(ta_api.router)
app.include_router(defi.router)
app.include_router(crawler.router)
# ----------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"error": "Internal Server Error"})
    return templates.TemplateResponse("error.html", {
        "request": request,
        "error": "Internal Server Error",
        "detail": str(exc)
    }, status_code=500)

@app.get("/healthz")
async def healthz():
    """Docker 健康检查端点"""
    checks = {}
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    
    checks["scheduler"] = "running" if scheduler.scheduler.running else "stopped"
    
    all_ok = all(v == "ok" or v == "running" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "healthy" if all_ok else "degraded", "checks": checks}
    )

# ==================== 页面路由 ====================




































# Redefine below as standard JSON endpoint





# ==================== Crawler Routes ====================





# ==================== API 路由 ====================








# ==================== Phase 1 新增 API ====================









# ===================================================================
# Data Service API  —  供 OpenClaw Agent 调用
# Base: /api/v1/data
# ===================================================================









# ===================================================================
# TA Analysis API  —  多时间框架技术分析接口
# Base: /api/v1/ta
# ===================================================================





# ==================== DeFi Lab ====================





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
