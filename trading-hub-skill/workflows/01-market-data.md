# Layer 1: Market Data

Real-time and historical crypto market data, macro indicators, and institutional flows.

## Service URL

`http://YOUR_SERVER_IP:8080` — AutoM2026 backend

## Standard Workflow

### Step 1: Get Market Snapshot (90% of use cases)

```bash
curl -s http://YOUR_SERVER_IP:8080/api/v1/data/snapshot | python3 -m json.tool
```

Returns in one response:

- `markets[]` — all watched symbols with price, 24h change
- `macro.fed_rate` — Federal Funds Rate (%)
- `macro.treasury_10y` — 10-Year Treasury Yield (%)
- `macro.dxy` — US Dollar Index
- `macro.m2_growth_yoy` — M2 money supply YoY growth (%)
- `macro.fear_greed` — `{value: 0-100, classification: "..."}`
- `macro.stablecoin_supply_b` — total stablecoin market cap (billions USD)
- `macro.etf_flows` — latest BTC/ETH/SOL ETF net flow (USD)
- `macro.hashrate` — BTC network hashrate (H/s raw value)
- `macro.halving_days` — days until next BTC halving (float)
- `macro.ahr999` — ahr999 定投指数 (< 0.45 抄底区间, < 1.2 定投区间, 否则高估)
- `macro.wma200` — 200-week moving average price (USD)
- `macro.mvrv_ratio` — MVRV Ratio (< 1.0 极度低估, 1-3.7 正常, > 3.7 周期顶部)
- `macro.miners_profitable` / `macro.miners_total` — miner health count
- `macro.mstr_mnav` — MicroStrategy mNAV ratio (market cap / BTC holdings value)
- `data_freshness` — timestamps of each data source

### Step 2 (Optional): Get K-lines for Manual TA

Only needed when performing manual TA (EMA, RSI, MACD, Bollinger Bands).
For automated multi-timeframe TA, use **Layer 2: Technical Analysis** instead.

```bash
# Default: 1h timeframe, 100 bars (served from local DB, auto-synced)
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/klines/BTC?timeframe=1h&limit=100"

# 4h timeframe for macro-level TA
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/klines/BTC?timeframe=4h&limit=200"

# Skip incremental sync for fast repeated calls (use cached local data)
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/klines/BTC?timeframe=1h&limit=100&skip_sync=true"
```

Valid timeframes: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
Max limit: 500

**Note**: K-line data is stored locally in SQLite and auto-synced every 15 min.
First request for a new symbol/timeframe triggers full history backfill (10-60s).
Response includes `"source": "local_db"` or `"binance_live"` (fallback).

## Recording Decisions

After completing analysis, always store your signal:

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/data/signals \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "your-agent-name",
    "strategy_name": "Strategy description",
    "symbol": "BTC",
    "action": "BUY",
    "conviction": 72.5,
    "price_at_signal": 43250.0,
    "reason": "EMA bullish alignment + Fear & Greed oversold + ETF inflows positive",
    "stop_loss": 41000.0,
    "take_profit": 48000.0
  }'
```

`action` must be one of: `BUY`, `SELL`, `HOLD`

## Reading Past Signals

```bash
# All recent signals
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/signals"

# Filter by symbol
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/signals?symbol=BTC&limit=10"
```

## Data Interpretation

See `references/data-interpretation.md` for:

- How to read macro indicators in crypto context
- ETF flow significance thresholds
- Fear & Greed classification table
- Recommended TA indicator combinations

## Macro Strategy Analysis

When the user explicitly asks for macro analysis, strategy assessment, or market outlook, read and follow:
`references/macro-strategy.md`

Do NOT load this file for simple price/data queries.

## Notes

- Market cache refreshes every 1 minute; data is never more than ~60s stale
- FRED macro data refreshes every 4 hours; ETF flows update daily via crawler
- If `markets[]` is empty, the MarketWatch list has no entries — add symbols at http://YOUR_SERVER_IP:8080/market
- Snapshot call takes ~1-3s (fetches FRED + Fear & Greed live); K-lines take ~0.5-1s
