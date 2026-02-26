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
    """API 文档页"""
    api_docs = [
        {
            "category": "Market Data & Macro",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/market/indicators",
                    "description": "获取所有宏观经济指标、恐慌指数、ETF规模等核心数据。",
                    "example": '{\n  "status": "success",\n  "indicators": [\n    {"name_zh": "AHR999", "value": "0.65", ...}\n  ]\n}'
                },
                {
                    "method": "GET",
                    "path": "/api/price/{symbol}",
                    "description": "获取特定数字货币的实时价格。",
                    "params": [{"name": "symbol", "type": "string", "required": True, "description": "交易对符号，如 BTCUSDT"}]
                },
                {
                    "method": "GET",
                    "path": "/api/etf/all",
                    "description": "获取 BTC/ETH ETF 的聚合持仓和 AUM 数据。"
                }
            ]
        },
        {
            "category": "AI Agent Service",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/v1/data/snapshot",
                    "description": "提供给 AI Agent 的完整状态快照（持仓、资金、指标）。",
                    "example": '{\n  "timestamp": "...",\n  "portfolio": { ... },\n  "market": { ... }\n}'
                },
                {
                    "method": "GET",
                    "path": "/api/v1/data/klines/{symbol}",
                    "description": "获取指定周期的历史 K 线数据。",
                    "params": [
                        {"name": "symbol", "type": "string", "required": True, "description": "符号"},
                        {"name": "interval", "type": "string", "required": False, "description": "周期, 默认 1h"},
                        {"name": "limit", "type": "int", "required": False, "description": "数量"}
                    ]
                },
                {
                    "method": "POST",
                    "path": "/api/v1/data/signals",
                    "description": "提交由 AI 分析生成的交易信号。",
                    "params": [
                        {"name": "symbol", "type": "string", "required": True, "description": "交易对"},
                        {"name": "side", "type": "string", "required": True, "description": "BUY / SELL"},
                        {"name": "reason", "type": "string", "required": False, "description": "交易理由"}
                    ]
                }
            ]
        },
        {
            "category": "Risk & Portfolio",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/risk/status",
                    "description": "查看风控模块状态及熔断状态。"
                },
                {
                    "method": "GET",
                    "path": "/api/portfolio/snapshots",
                    "description": "获取账户净值历史快照（用于绘图）。"
                }
            ]
        },
        {
            "category": "Strategy & System",
            "endpoints": [
                {
                    "method": "GET",
                    "path": "/api/strategies",
                    "description": "获取当前系统加载的所有策略实例及其状态。"
                },
                {
                    "method": "GET",
                    "path": "/api/scheduler/jobs",
                    "description": "查看定时任务调度器的运行队列。"
                }
            ]
        },
        {
            "category": "DeFi Lab",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/api/defi/backtest",
                    "description": "执行双币轮动策略历史回测。",
                    "params": [
                        {"name": "asset_a_symbol", "type": "string", "required": True, "description": "主资产"},
                        {"name": "asset_b_symbol", "type": "string", "required": True, "description": "对标资产"},
                        {"name": "mode", "type": "string", "required": True, "description": "SMA / FIXED"}
                    ]
                }
            ]
        },
        {
            "category": "Technical Analysis (TA)",
            "endpoints": [
                {
                    "method": "POST",
                    "path": "/api/v1/ta/analyze",
                    "description": "对特定品种进行全家桶技术指标分析。",
                    "params": [
                        {"name": "symbol", "type": "string", "required": True, "description": "交易对"},
                        {"name": "indicators", "type": "list", "required": False, "description": "可选指标列表"}
                    ]
                }
            ]
        }
    ]
    return templates.TemplateResponse("docs.html", {
        "request": request,
        "api_docs": api_docs,
        "title": "API Documentation - AutoM2026"
    })
