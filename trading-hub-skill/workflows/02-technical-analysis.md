# Layer 2: Technical Analysis

Multi-timeframe technical analysis on any Binance asset with automated signal generation.

## Service URL

`http://YOUR_SERVER_IP:8080` — AutoM2026 backend

## Step 1: Analyze

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/ta/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframes":["15m","1h","4h"]}'
```

### Parameters

- `symbol` (required): Any Binance USDT pair (BTC, ETH, SOL, BNB, etc.)
- `timeframes` (required): Array of timeframes to analyze
  - Valid: `1m`, `5m`, `15m`, `1h`, `4h`, `1d`
  - Recommended: `["15m","1h","4h"]` or `["1h","4h","1d"]`

### Optional Parameters

| Parameter         | Default | Description                                |
| ----------------- | ------- | ------------------------------------------ |
| `klines_limit`    | 300     | Number of K-lines to fetch per timeframe   |
| `buy_threshold`   | 65      | Conviction score threshold for BUY signal  |
| `sell_threshold`  | 35      | Conviction score threshold for SELL signal |
| `atr_stop_mult`   | 2.0     | ATR multiplier for stop-loss calculation   |
| `atr_target_mult` | 3.0     | ATR multiplier for take-profit calculation |

### Response Structure

Key fields:

- `signal` — BUY / SELL / HOLD
- `conviction` — 0-100 score (higher = stronger signal)
- `grade` — A / B / C (quality rating)
- `current_price` — current asset price
- `stop_loss` — recommended stop-loss level
- `take_profit` — recommended take-profit level
- `risk_reward` — risk/reward ratio
- `position_size` — suggested position size (% of capital)
- `score_by_tf` — per-timeframe conviction breakdown
- `indicators` — detailed indicator values per timeframe
- `reasons` — human-readable signal explanation

### Performance Notes

- **First call** for a new symbol triggers history backfill: 15-60s
- **Subsequent calls**: ~1-3s (uses local DB cache)
- K-line data auto-syncs every 15 min

## Step 2: Record Signal (Mandatory)

Always record your analysis decision:

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/data/signals \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "YOUR_ID",
    "strategy_name": "TA Multi-TF",
    "symbol": "BTC",
    "action": "BUY",
    "conviction": 74.5,
    "price_at_signal": 96420,
    "stop_loss": 93850,
    "take_profit": 101200,
    "reason": "[A] [4h]EMA多头排列; [1h]MACD金叉; RSI超卖(28)"
  }'
```

## Interpretation Protocol

For detailed signal interpretation, grading system, and position sizing rules:
→ See `references/ta-strategy.md`

Key points:

- **Grade A**: All timeframes aligned, high conviction (>75)
- **Grade B**: Majority timeframes aligned, medium conviction (60-75)
- **Grade C**: Mixed signals, low conviction (<60)

## Utilities

### Check Local DB Coverage

```bash
curl -s http://YOUR_SERVER_IP:8080/api/v1/ta/klines-status
```

Returns number of bars stored per symbol/timeframe.

### Raw K-lines (Fast Access)

```bash
# Skip sync for speed (use cached local data)
curl -s "http://YOUR_SERVER_IP:8080/api/v1/data/klines/BTC?timeframe=1h&limit=200&skip_sync=true"
```

## Common Scenarios

### Scenario 1: Quick BTC check (1h + 4h)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/ta/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"BTC","timeframes":["1h","4h"]}'
```

### Scenario 2: Scalping setup (short timeframes)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/ta/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"ETH","timeframes":["5m","15m","1h"]}'
```

### Scenario 3: Swing trade (longer timeframes)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/ta/analyze \
  -H "Content-Type: application/json" \
  -d '{"symbol":"SOL","timeframes":["4h","1d"]}'
```

## Notes

- Indicators calculated: EMA (9/21/50/200), RSI, MACD, Bollinger Bands, Volume
- Multi-timeframe alignment increases signal quality
- ATR-based stop-loss/take-profit adapts to volatility
- Position sizing considers conviction score and risk/reward ratio
