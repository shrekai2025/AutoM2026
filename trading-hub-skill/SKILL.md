---
name: trading-hub
description: "Unified crypto trading infrastructure: real-time market data, multi-timeframe technical analysis, and pair arbitrage backtesting. Three progressive layers: L1 data queries, L2 TA analysis, L3 strategy backtesting. Service: http://YOUR_SERVER_IP:8080 (AutoM2026)."
metadata: { "openclaw": { "emoji": "🏦", "requires": { "bins": ["curl"] } } }
---

# Trading Hub

Unified access to crypto trading infrastructure. Three progressive layers for different use cases.

## Service

`http://YOUR_SERVER_IP:8080` — AutoM2026 backend (must be running)

## Quick Start

### Most Common: Get Market Snapshot

```bash
curl -s http://YOUR_SERVER_IP:8080/api/v1/data/snapshot | python3 -m json.tool
```

Returns everything in one call: prices, 24h changes, macro indicators (Fed rate, DXY, Fear & Greed), ETF flows, on-chain metrics.

### Technical Analysis

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/ta/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframes":["1h","4h"]}'
```

Returns BUY/SELL/HOLD signal, conviction score, stop-loss/take-profit levels, indicator breakdown.

### Strategy Backtest

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/defi/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "asset_a_symbol": "ETHUSDT",
    "asset_b_symbol": "BTCUSDT",
    "start_date": "2024-01-01"
  }'
```

Returns annualized return, win rate, trade log for pair rotation strategy.

## Three Layers (Progressive Disclosure)

### Layer 1: Market Data

**Use when**: checking prices, macro conditions, market sentiment

→ See `workflows/01-market-data.md` for:

- Market snapshot structure
- K-line queries
- Recording signals
- Macro indicator interpretation

### Layer 2: Technical Analysis

**Use when**: evaluating entry/exit points, multi-timeframe confirmation

→ See `workflows/02-technical-analysis.md` for:

- Multi-timeframe TA workflow
- Indicator interpretation
- Signal grading system
- Position sizing

### Layer 3: Strategy Backtest

**Use when**: testing pair rotation ideas, comparing asset performance

→ See `workflows/03-strategy-backtest.md` for:

- Bollinger Band pair arbitrage
- Fixed range thresholds
- DEX pool backtesting
- Performance metrics

## Recording Decisions

After any analysis, always record your signal:

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
    "reason": "Brief reasoning",
    "stop_loss": 41000.0,
    "take_profit": 48000.0
  }'
```

## Deep References

Only load when needed for specific analysis:

- `references/data-interpretation.md` — macro indicator thresholds
- `references/macro-strategy.md` — market cycle analysis
- `references/ta-strategy.md` — TA interpretation protocol

## Notes

- Market data refreshes every 1 min
- First TA/backtest call for new symbol triggers history backfill (15-60s)
- Subsequent calls are fast (~1-3s)
- K-line data stored locally in SQLite, auto-synced every 15 min
