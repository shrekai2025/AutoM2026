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

@router.post("/api/v1/ta/analyze")
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

@router.get("/api/v1/ta/klines-status")
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

