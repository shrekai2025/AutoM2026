# AutoM2026 系统性优化方案

> 生成时间：2026-02-26 | 目标：提升可靠性 & 前端性能

---

## 一、项目现状总结

### 1.1 技术架构
| 层级 | 技术 | 现状评估 |
|---|---|---|
| Web 框架 | FastAPI + Jinja2 SSR | 功能完整，但 app.py **单文件 2,400 行**，职责混杂 |
| 数据库 | SQLite + SQLAlchemy 2.0 (async) | WAL 模式已开启，但缺少连接池配置和重试机制 |
| 调度器 | APScheduler | 运行稳定，Data Service Mode |
| 数据采集 | aiohttp (Binance/FRED/链上) | 各采集器独立创建 session，无统一生命周期管理 |
| 前端 | Jinja2 模板 + Alpine.js | 纯 SSR，行情页每次加载需串行请求 10+ 外部 API |
| 部署 | Docker + docker-compose | 单容器，无健康检查 |

### 1.2 已识别的核心问题

#### 🔴 可靠性问题
1. **`app.py` 上帝文件** — 2,400 行单文件包含 56 个路由函数，难维护、难测试
2. **外部 API 串行调用** — `market_watch()` 串行调用 FRED、F&G、Mempool、CoinMetrics、F2Pool、yfinance 等 10+ 数据源，任一超时将阻塞整个页面渲染
3. **无统一错误处理** — 各数据源的异常处理分散在代码各处，缺少全局异常兜底
4. **aiohttp Session 管理零散** — `BinanceCollector`、`OnchainCollector`、`FREDCollector` 各自管理 session，无统一关闭/重连机制
5. **SQLite 并发限制** — 无连接池大小限制，高并发时可能出现 `database is locked`
6. **缺少健康检查端点** — Docker 容器无 healthcheck，服务假死无法自动重启
7. **内联 import 遍布** — 大量 `from models import ...` 在函数体内，增加运行时开销且难追踪依赖

#### 🟡 前端性能问题
1. **SSR 慢页面** — `/market` 页面每次请求需等待所有外部 API 返回（通常 5-15 秒）
2. **无数据缓存层** — 宏观指标（FRED/F&G 等）几乎不变但每次页面刷新都重新请求
3. **CDN 无版本控制** — `alpinejs@3.x.x`、`@phosphor-icons/web` 未锁定版本，可能因版本变化导致问题
4. **静态资源版本号手动管理** — CSS 文件的 `?v=20260121_2` 需手动更新
5. **无前端数据异步刷新** — 缺少 AJAX 轮询或 WebSocket，用户需手动F5刷新
6. **行情数据串行获取** — 11 个币的行情 for-loop 串行调用 Binance API

---

## 二、优化方案（按优先级排列）

### Phase 1：高优先级 — 可靠性与稳定性 ⚡

#### 1.1 路由模块拆分 — 解体 `app.py`

**目标**：将 2,400 行的 `app.py` 拆分为 6-7 个 Router 模块

```
web/
├── app.py                  # ~100行：FastAPI 初始化、挂载 Router
├── routers/
│   ├── __init__.py
│   ├── dashboard.py        # / 首页
│   ├── strategies.py       # /strategies/* CRUD
│   ├── market.py           # /market 行情 + 指标
│   ├── trading.py          # /positions + /trades
│   ├── crawler.py          # /crawler/* 爬虫管理
│   ├── system.py           # /system/* 系统状态
│   └── api_v1/
│       ├── data.py         # /api/v1/data/* Agent 数据接口
│       ├── ta.py           # /api/v1/ta/* TA 分析接口
│       └── defi.py         # /defi-lab + backtest API
├── services/
│   ├── market_service.py   # 行情指标聚合逻辑（从 market_watch() 抽出）
│   └── indicator_service.py # 指标详情逻辑
```

**收益**：
- 每个模块 200-400 行，职责清晰
- 可独立测试各模块
- 多人/多次迭代时减少冲突

#### 1.2 数据采集层的并发化 + 缓存

**问题**：`market_watch()` 约 430 行代码串行调用 10+ 数据源

**解决方案**：

```python
# web/services/market_service.py
import asyncio
from functools import lru_cache
from datetime import datetime, timedelta

class MarketDataService:
    """聚合所有宏观指标数据，带内存缓存和并发请求"""
    
    def __init__(self):
        self._cache = {}
        self._cache_ttl = {
            "fred": 3600,      # 1小时（FRED 数据日频更新）
            "fear_greed": 300,  # 5分钟
            "onchain": 300,     # 5分钟
            "miners": 1800,     # 30分钟
            "etf_flow": 600,    # 10分钟
            "stablecoin": 600,  # 10分钟
        }
    
    async def get_all_indicators(self, db):
        """并发获取所有数据源，有缓存直接返回"""
        tasks = {
            "fred": self._get_with_cache("fred", fred_collector.get_macro_data),
            "fear_greed": self._get_with_cache("fear_greed", fear_greed_collector.get_current),
            "hashrate": self._get_with_cache("hashrate", onchain_collector.get_hashrate),
            "halving": self._get_with_cache("halving", onchain_collector.get_halving_info),
            "ahr999": self._get_with_cache("ahr999", onchain_collector.get_ahr999),
            "wma200": self._get_with_cache("wma200", onchain_collector.get_200wma),
            "mvrv": self._get_with_cache("mvrv", onchain_collector.get_mvrv_ratio),
            "miners": self._get_with_cache("miners", mining_collector.get_miners_data),
            "stablecoin": self._get_with_cache("stablecoin", stablecoin_collector.get_latest_supply),
        }
        
        # 并发执行，某个失败不影响其他
        results = await asyncio.gather(
            *[self._safe_call(k, v) for k, v in tasks.items()],
            return_exceptions=True
        )
        return dict(zip(tasks.keys(), results))
    
    async def _get_with_cache(self, key, fetch_fn):
        """带 TTL 的内存缓存"""
        if key in self._cache:
            data, cached_at = self._cache[key]
            ttl = self._cache_ttl.get(key, 300)
            if (datetime.utcnow() - cached_at).total_seconds() < ttl:
                return data
        
        result = await fetch_fn()
        self._cache[key] = (result, datetime.utcnow())
        return result
    
    async def _safe_call(self, name, coro):
        """安全执行，超时或异常返回空"""
        try:
            return await asyncio.wait_for(coro, timeout=10)
        except Exception as e:
            logger.warning(f"Data source {name} failed: {e}")
            return None
```

**收益**：
- 页面加载时间从 **5-15秒** 降至 **1-3秒**（并发 + 缓存）
- 单数据源 timeout 不会阻塞其他数据源
- FRED 等低频数据不会重复请求 API

#### 1.3 全局异常处理

```python
# web/app.py
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}", exc_info=True)
    if request.url.path.startswith("/api/"):
        return JSONResponse(status_code=500, content={"error": str(exc)})
    return templates.TemplateResponse("error.html", {
        "request": request,
        "error": "Internal Server Error",
        "detail": str(exc) if settings.DEBUG else "请稍后重试"
    }, status_code=500)
```

#### 1.4 aiohttp Session 生命周期统一管理

```python
# core/http_client.py
import aiohttp
from contextlib import asynccontextmanager

class SharedHTTPClient:
    """全局共享的 HTTP 客户端，统一管理 session 生命周期"""
    _session: aiohttp.ClientSession = None
    
    @classmethod
    async def get_session(cls) -> aiohttp.ClientSession:
        if cls._session is None or cls._session.closed:
            timeout = aiohttp.ClientTimeout(total=30, connect=10)
            cls._session = aiohttp.ClientSession(timeout=timeout)
        return cls._session
    
    @classmethod
    async def close(cls):
        if cls._session and not cls._session.closed:
            await cls._session.close()
            cls._session = None
```

在 `lifespan` 中管理：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    await scheduler.start(AsyncSessionLocal)
    yield
    scheduler.stop()
    await SharedHTTPClient.close()  # 统一关闭
```

#### 1.5 SQLite 稳定性增强

```python
# core/database.py 改进
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_size=5,              # 限制连接数（SQLite 单写者）
    max_overflow=0,           # 不允许溢出
    pool_pre_ping=True,       # 连接前检测有效性
    pool_recycle=3600,        # 1小时回收连接
    connect_args={"timeout": 30}  # 增加超时到30秒
)

@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")   # 新增：忙等待5秒
    cursor.execute("PRAGMA cache_size=-64000")    # 新增：64MB 页缓存
    cursor.execute("PRAGMA foreign_keys=ON")      # 新增：启用外键约束
    cursor.close()
```

#### 1.6 健康检查端点

```python
@app.get("/healthz")
async def healthz():
    """Docker 健康检查端点"""
    checks = {}
    # DB check
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
    
    # Scheduler check
    checks["scheduler"] = "running" if scheduler.scheduler.running else "stopped"
    
    all_ok = all(v == "ok" or v == "running" for v in checks.values())
    return JSONResponse(
        status_code=200 if all_ok else 503,
        content={"status": "healthy" if all_ok else "degraded", "checks": checks}
    )
```

Docker Compose 增加：
```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8080/healthz"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

---

### Phase 2：前端性能优化 🚀

#### 2.1 行情页异步加载架构

**核心思路**：SSR 只渲染页面骨架，数据通过 AJAX/API 异步加载

```
加载流程：
1. SSR 返回页面 HTML（骨架 + loading 动画）——亚秒级
2. 前端 JS 调用 /api/market/indicators 获取指标数据——后台并发
3. 收到数据后通过 Alpine.js 渲染卡片——渐进式呈现
```

**后端 API**：
```python
@router.get("/api/market/indicators")
async def api_market_indicators():
    """异步获取所有宏观指标（供前端 AJAX 调用）"""
    data = await market_service.get_all_indicators()
    return {"indicators": data, "cached_at": datetime.utcnow().isoformat()}
```

**前端 Alpine.js 组件化**：
```html
<div x-data="{ indicators: [], loading: true }" x-init="
    fetch('/api/market/indicators')
      .then(r => r.json())
      .then(data => { indicators = data.indicators; loading = false; })
      .catch(e => { loading = false; })
">
    <!-- Skeleton Loading -->
    <template x-if="loading">
        <div class="grid grid-cols-3 gap-5">
            <div class="skeleton h-32 rounded-xl" x-for="i in 12"></div>
        </div>
    </template>
    
    <!-- Real Data -->
    <template x-if="!loading">
        <template x-for="ind in indicators">
            <div class="card" ...>...</div>
        </template>
    </template>
</div>
```

**收益**：
- 页面首屏从 **5-15秒** 降至 **<1秒**（骨架屏秒出）
- 数据渐进加载，用户感知流畅

#### 2.2 Binance 行情并发获取

```python
# 当前：串行（N 个币 × ~200ms = ~2.2秒）
for item in watched_items:
    ticker = await binance_collector.get_24h_ticker(f"{item.symbol}USDT")

# 优化后：并发（~200ms 总）
async def _fetch_all_tickers(symbols):
    tasks = [binance_collector.get_24h_ticker(f"{s}USDT") for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return dict(zip(symbols, results))
```

#### 2.3 静态资源优化

```python
# 自动版本号（基于文件修改时间）
import hashlib

def file_hash(filepath):
    with open(filepath, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()[:8]

# 在 Jinja2 Environment 注册
templates.env.globals["asset_version"] = file_hash
```

模板中使用：
```html
<link rel="stylesheet" href="/static/css/variables.css?v={{ asset_version('web/static/css/variables.css') }}">
```

#### 2.4 CDN 版本锁定

```html
<!-- Before (危险): -->
<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>

<!-- After (安全): -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.14.3/dist/cdn.min.js"
        integrity="sha384-..." crossorigin="anonymous"></script>
```

#### 2.5 指标自动刷新

```javascript
// 每 60 秒自动刷新行情数据（不刷新整个页面）
setInterval(async () => {
    const resp = await fetch('/api/market/indicators');
    const data = await resp.json();
    Alpine.store('indicators', data.indicators);
}, 60000);
```

---

### Phase 3：代码质量与可维护性 🔧

#### 3.1 消除内联 import

将所有函数体内的 `from models import ...` 移到文件顶部。当前 `app.py` 中至少有 **15 处**内联导入：

```python
# 当前（分散在各函数中）
async def market_watch(request):
    from models import MarketWatch                      # ❌
    from data_collectors import binance_collector       # ❌
    from data_collectors.fred_collector import fred_collector  # ❌
    from data_collectors.onchain_collector import onchain_collector # ❌
    import time as _time                                # ❌

# 优化后（统一在文件顶部或 Router 模块顶部）
from models import MarketWatch
from data_collectors import binance_collector
from data_collectors.fred_collector import fred_collector
```

#### 3.2 消除重复代码

当前 `market_watch()` 中存在 **键名重复赋值** 等代码质量问题：

```python
# Line 427-428 重复键
"volume_24h": ticker["volume_24h"],
"volume_24h": ticker["volume_24h"],  # ← 重复

# Line 435-436 重复键
"symbol": item.symbol,
"symbol": item.symbol,  # ← 重复
```

#### 3.3 配置常量提取

将硬编码的缓存 TTL、超时时间等提取到 `config/settings.py`：

```python
# config/settings.py 新增
MARKET_CACHE_TTL = {
    "fred": int(os.getenv("CACHE_TTL_FRED", "3600")),
    "fear_greed": int(os.getenv("CACHE_TTL_FG", "300")),
    "onchain": int(os.getenv("CACHE_TTL_ONCHAIN", "300")),
}
HTTP_TIMEOUT = int(os.getenv("HTTP_TIMEOUT", "30"))
```

#### 3.4 日志结构化

```python
# 当前（散乱）
logger.info(f"Loaded {len(strategies)} active strategies")

# 优化后（结构化，便于日志分析）
logger.info("strategies_loaded", extra={"count": len(strategies), "module": "scheduler"})
```

---

### Phase 4：生产化增强 🏭

#### 4.1 Uvicorn 生产配置

```python
# main.py
if os.getenv("ENV") == "production":
    uvicorn.run(
        "web.app:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
        workers=1,            # SQLite 限制，只能单 worker
        access_log=False,     # 生产环境减少日志
        log_level="warning",
    )
```

#### 4.2 Graceful Shutdown

确保 APScheduler 和 aiohttp sessions 在容器停止时正确关闭：

```python
import signal

async def shutdown_handler():
    scheduler.stop()
    await SharedHTTPClient.close()
    await engine.dispose()
```

#### 4.3 Docker 优化

```dockerfile
# 多阶段构建减小镜像体积
FROM python:3.10-slim-bookworm AS builder
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.10-slim-bookworm
COPY --from=builder /install /usr/local
# ...
```

---

## 三、实施路线图

| 阶段 | 优化项 | 预计效果 | 复杂度 | 建议顺序 |
|---|---|---|---|---|
| **P1.1** | app.py 拆分为 Router 模块 | 可维护性大幅提升 | 🟡 中 | 1️⃣ |
| **P1.2** | 数据源并发化 + 缓存层 | 页面加载 5-15s → 1-3s | 🟡 中 | 2️⃣ |
| **P1.3** | 全局异常处理 | 杜绝 500 白屏 | 🟢 低 | 3️⃣ |
| **P1.4** | HTTP Session 统一管理 | 减少连接泄漏 | 🟢 低 | 4️⃣ |
| **P1.5** | SQLite 稳定性增强 | 杜绝 database locked | 🟢 低 | 5️⃣ |
| **P1.6** | 健康检查端点 | 容器自动恢复 | 🟢 低 | 6️⃣ |
| **P2.1** | 行情页异步加载 | 首屏 <1s | 🟡 中 | 7️⃣ |
| **P2.2** | Binance 并发获取 | 行情获取 2s → 0.2s | 🟢 低 | 8️⃣ |
| **P2.3-4** | 静态资源 + CDN 优化 | 消除缓存/兼容问题 | 🟢 低 | 9️⃣ |
| **P2.5** | 指标自动刷新 | 无需手动 F5 | 🟢 低 | 🔟 |
| **P3** | 代码质量清理 | Bug 预防 | 🟢 低 | 可随其他任务同步 |
| **P4** | 生产化配置 | 容器稳定性 | 🟢 低 | 最后 |

---

## 四、风险&注意

1. **SQLite 单写者限制**：不能用多 worker，如未来需要扩展须迁移到 PostgreSQL
2. **路由拆分需一次性完成**：中间状态可能导致路由冲突
3. **前端异步化后需保持 SEO**：搜索引擎爬虫无法执行 JS，但本项目为个人工具不受影响
4. **缓存一致性**：缓存 TTL 需根据数据源更新频率合理设置

---

*准备好开始执行后，按优先级逐项推进即可。建议从 P1.1（路由拆分）开始。*
