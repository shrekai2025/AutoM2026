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

@router.get("/strategies", response_class=HTMLResponse)
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

@router.get("/strategies/new", response_class=HTMLResponse)
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

@router.post("/strategies/create")
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

@router.get("/strategies/{strategy_id}/edit", response_class=HTMLResponse)
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

@router.post("/strategies/{strategy_id}/update")
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

@router.post("/strategies/{strategy_id}/toggle")
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

@router.post("/strategies/{strategy_id}/run")
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

@router.post("/strategies/{strategy_id}/delete")
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

@router.get("/strategies/{strategy_id}", response_class=HTMLResponse)
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

@router.get("/api/strategies")
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

@router.get("/api/scheduler/jobs")
async def api_scheduler_jobs():
    """调度任务列表 API"""
    return scheduler.get_jobs_info()

