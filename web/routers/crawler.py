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

@router.get("/crawler/sources", response_class=HTMLResponse)
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

@router.get("/crawler/data", response_class=HTMLResponse)
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

@router.get("/api/etf/all")
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

