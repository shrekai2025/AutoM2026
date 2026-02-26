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
from data_collectors import get_btc_price

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory="web/templates")
router = APIRouter()

@router.get("/", response_class=HTMLResponse)
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

@router.get("/positions", response_class=HTMLResponse)
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

@router.get("/trades", response_class=HTMLResponse)
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

@router.get("/system/status", response_class=HTMLResponse)
async def system_status(request: Request):
    """系统状态页 — 从内存读取，不碰数据库"""
    from core.monitor import monitor

    return templates.TemplateResponse("system_status.html", {
        "request": request,
        "api_status_list": monitor.get_latest_status(),
        "recent_logs": monitor.get_recent_logs(50),
    })
@router.get("/docs", response_class=HTMLResponse)
async def api_docs_page(request: Request):
    """API 终极参考手册 - 每一个字段都有据可查"""
    api_docs = [
        {
            "category": "1. Market Data & Comprehensive Stats",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/market/indicators",
                    "description": "获取系统仪表盘所有核心指标卡片。聚合了 FRED 宏观经济数据、CoinGecko 估值、算力及波动率。",
                    "inputs": [],
                    "outputs": [
                        {"name": "indicators", "type": "array", "description": "所有卡片数据的集合"},
                        {"name": "indicators[].name_zh", "type": "string", "description": "中文友好名称 (e.g. 10年期美债收益率)"},
                        {"name": "indicators[].abbr", "type": "string", "description": "代码标识 (e.g. US10Y, AHR999)"},
                        {"name": "indicators[].value", "type": "string", "description": "带单位的格式化值 (e.g. 4.3%, $68K)"},
                        {"name": "indicators[].tags", "type": "array", "description": "分类标签 (宏观, 情绪, 估值)"},
                        {"name": "indicators[].desc", "type": "string", "description": "数据含义详细描述或数据来源网站"}
                    ]
                },
                {
                    "method": "GET",
                    "path": "/api/etf/all",
                    "description": "实时获取全网 BTC 和 ETH 现货 ETF 的净值/持仓/AUM 数据。优先读取爬虫缓存，失效后触发链上实时校对。",
                    "inputs": [],
                    "outputs": [
                        {"name": "etf_aum", "type": "object", "description": "按 Ticker 索引的详情 (IBIT, FBTC, FBTC, etc.)"},
                        {"name": "etf_aum.{Ticker}.aum_usd", "type": "number", "description": "该 ETF 持仓折合美元价值"},
                        {"name": "etf_aum.{Ticker}.ok", "type": "boolean", "description": "数据是否成功获取"},
                        {"name": "btc_total", "type": "number", "description": "全网 BTC ETF 算力币持仓合计数"},
                        {"name": "eth_total", "type": "number", "description": "全网 ETH ETF 持仓合计数"}
                    ]
                }
            ]
        },
        {
            "category": "2. AI Agent Core Hub (V1)",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/data/snapshot",
                    "description": "Agent 决策专用全局快照。一次性包含所有必要上下文：实时行情 + 宏观指标 + 溢价指标 + 算力数据。",
                    "inputs": [],
                    "outputs": [
                        {"name": "generated_at", "type": "ISO8601", "description": "快照生成精确时间"},
                        {"name": "markets", "type": "array", "description": "观察列表中的币种动态: [symbol, price, change_24h, high_24h, volume, is_live]"},
                        {"name": "macro.fed_rate", "type": "number", "description": "美联储隔夜拆借利率 (%)"},
                        {"name": "macro.fear_greed", "type": "object", "description": "{value: 0-100, classification: Fear/Greed/...}"},
                        {"name": "macro.mstr_mnav", "type": "number", "description": "MSTR 溢价率 (mNAV)。> 1 代表美股市场看涨情绪强于现货"},
                        {"name": "macro.stablecoin_supply_b", "type": "number", "description": "全网稳定币存量 (B USD)，反映入场流动性"},
                        {"name": "macro.etf_flows", "type": "object", "description": "BTC/ETH ETF 当日详细流入额 (USD)"}
                    ]
                },
                {
                    "method": "GET",
                    "path": "/api/v1/data/klines/{symbol}",
                    "description": "高性能历史 K 线。本地数据库优先，自动增量补齐。适合回测或策略分析。",
                    "inputs": [
                        {"name": "symbol", "type": "string", "required": True, "description": "代币代码 (如 BTC, SOL)"},
                        {"name": "timeframe", "type": "string", "required": False, "description": "1m, 5m, 15m, 1h, 4h, 1d", "default": "1h"},
                        {"name": "limit", "type": "integer", "required": False, "description": "返回深度 (1-500)", "default": "100"},
                        {"name": "skip_sync", "type": "boolean", "required": False, "description": "跳过后台数据补全逻辑，立刻返回缓存", "default": "false"}
                    ]
                },
                {
                    "method": "POST",
                    "path": "/api/v1/data/signals",
                    "description": "将分布式 Agent 的分析结果回传并入库，实现统一监控和反馈学习。",
                    "inputs": [
                        {"name": "symbol", "type": "string", "required": True, "description": "标的代码"},
                        {"name": "action", "type": "string", "required": True, "description": "BUY | SELL | HOLD"},
                        {"name": "conviction", "type": "number", "required": False, "description": "信心指数 (0.0-100.0)", "default": "50.0"},
                        {"name": "reason", "type": "string", "required": False, "description": "详细分析理由 (JSON 或长文本)"},
                        {"name": "price_at_signal", "type": "number", "required": False, "description": "发出信号时的当前价格"}
                    ]
                },
                {
                    "method": "GET",
                    "path": "/api/v1/data/signals",
                    "description": "检索历史决策信号。用于 AI 复盘分析效果。",
                    "inputs": [
                        {"name": "symbol", "type": "string", "required": False, "description": "按币种过滤"},
                        {"name": "limit", "type": "integer", "required": False, "description": "返回条目数", "default": "50"}
                    ]
                }
            ]
        },
        {
            "category": "3. DeFi & On-chain Analysis",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/api/defi/backtest",
                    "description": "双币资产轮动模拟器。支持币安或 Gecko 端数据回测。",
                    "inputs": [
                        {"name": "asset_a_symbol", "type": "string", "required": True, "description": "基础资产 (e.g. ETH)"},
                        {"name": "asset_b_symbol", "type": "string", "required": True, "description": "对标资产 (e.g. BTC)"},
                        {"name": "mode", "type": "string", "required": True, "description": "SMA | EMA (均线回归) | FIXED (固定百分比区间)"},
                        {"name": "use_ema", "type": "boolean", "required": False, "description": "是否启用指数移动平均", "default": "true"},
                        {"name": "window_size", "type": "integer", "required": False, "description": "计算均线的窗口天数", "default": "30"},
                        {"name": "no_loss_sell", "type": "boolean", "required": False, "description": "防回撤保护：买回基准资产时如低于卖出价则拒绝成交", "default": "true"}
                    ],
                    "outputs": [
                        {"name": "summary.total_return_pct", "type": "number", "description": "累计绝对收益率"},
                        {"name": "summary.annualized_return_pct", "type": "number", "description": "年化收益率"},
                        {"name": "summary.max_drawdown_pct", "type": "number", "description": "最大回撤深度"},
                        {"name": "trades", "type": "array", "description": "全部模拟成交历史"}
                    ]
                },
                {
                    "method": "GET",
                    "path": "/api/defi/pool-history/{network}/{address}",
                    "description": "拉取 DEX 的池子历史价格点位。",
                    "inputs": [
                        {"name": "network", "type": "string", "required": True, "description": "网络标识 (eth, sol, polygon...)"},
                        {"name": "address", "type": "string", "required": True, "description": "池子合约地址"},
                        {"name": "start", "type": "string", "required": False, "description": "ISO 开始日期"},
                        {"name": "end", "type": "string", "required": False, "description": "ISO 结束日期"}
                    ]
                }
            ]
        },
        {
            "category": "4. Strategy Management",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/strategies",
                    "description": "查询当前所有自动化策略的活跃状态及参数配置。",
                    "outputs": [
                        {"name": "[].id", "type": "string", "description": "唯一特征 ID"},
                        {"name": "[].status", "type": "string", "description": "ACTIVE | PAUSED | CLOSED"},
                        {"name": "[].pnl_pct", "type": "number", "description": "该策略自启动以来的盈亏率"}
                    ]
                },
                {
                    "method": "POST",
                    "path": "/api/strategies/{id}/toggle",
                    "description": "即时控制策略的运行或停止。",
                    "inputs": [{"name": "id", "type": "string", "required": True, "description": "策略数据库 ID"}]
                }
            ]
        },
        {
            "category": "5. Risk Management",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/risk/status",
                    "description": "核心熔断器状态检测。包含回撤报警等级和熔断开关状态。",
                    "outputs": [
                        {"name": "circuit_breaker_active", "type": "boolean", "description": "全站是否处在禁买锁定期 (熔断状态)"},
                        {"name": "risk_level", "type": "string", "description": "LOW | MEDIUM | HIGH"}
                    ]
                },
                {
                    "method": "GET",
                    "path": "/api/risk/events",
                    "description": "审计追踪：获取最近触碰风控线的详细事件记录。",
                    "inputs": [{"name": "limit", "type": "integer", "required": False, "description": "回访条目", "default": "50"}]
                }
            ]
        }
    ]
    return templates.TemplateResponse("docs.html", {
        "request": request,
        "api_docs": api_docs,
        "title": "Developer Documentation - AutoM2026"
    })
