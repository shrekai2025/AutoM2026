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

@router.get("/defi-lab", response_class=HTMLResponse)
async def defi_lab(request: Request):
    """DeFi 实验室 - 双币双向回测与套利分析"""
    return templates.TemplateResponse("defi_lab.html", {
        "request": request,
        "now": datetime.utcnow()
    })

@router.get("/api/defi/pool-metadata/{network}/{address}")
async def get_pool_metadata(network: str, address: str):
    from data_collectors.gecko_terminal import gecko_terminal
    return await gecko_terminal.get_pool_metadata(network, address)

@router.get("/api/defi/pool-history/{network}/{address}")
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

