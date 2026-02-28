# Layer 3: Strategy Backtest

Statistical arbitrage / pair rotation backtest between two crypto assets.

## Service URL

`http://YOUR_SERVER_IP:8080` — AutoM2026 backend

## How It Works

The backtest engine:

1. Fetches daily price history for **Asset A** and **Asset B** (Binance or GeckoTerminal)
2. Calculates the ratio `A/B` over the selected time window
3. Applies **SMA/EMA Bollinger Bands** (dynamic) or **fixed range** thresholds
4. Simulates gradual position rotation: sells A→B when ratio spikes above upper band, buys A←B when ratio falls below lower band
5. Returns annualized return, win rate, trade log, and daily P&L curve

## Running a Backtest

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/defi/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "asset_a_source": "binance",
    "asset_a_symbol": "ETHUSDT",
    "asset_b_source": "binance",
    "asset_b_symbol": "BTCUSDT",
    "start_date": "2024-01-01",
    "end_date": "2025-01-01",
    "mode": "SMA",
    "window_size": 30,
    "std_dev_mult": 2.0,
    "use_ema": true,
    "step_size": 50,
    "no_loss_sell": true
  }' | python3 -m json.tool
```

## Parameter Reference

### Asset Configuration

| Field             | Type   | Default     | Description                                                             |
| ----------------- | ------ | ----------- | ----------------------------------------------------------------------- |
| `asset_a_source`  | string | `"binance"` | `"binance"` (CEX) or `"gecko"` (DEX pool)                               |
| `asset_a_symbol`  | string | `"ETHUSDT"` | Binance trading pair (e.g. `ETHUSDT`) **or** GeckoTerminal pool address |
| `asset_a_network` | string | null        | Required only when source=gecko (e.g. `"eth"`, `"base"`, `"arbitrum"`)  |
| `asset_a_label`   | string | null        | Display name override                                                   |
| `asset_b_source`  | string | `"binance"` | Same as asset_a_source                                                  |
| `asset_b_symbol`  | string | `"BTCUSDT"` | Same as asset_a_symbol                                                  |
| `asset_b_network` | string | null        | Same as asset_a_network                                                 |
| `asset_b_label`   | string | null        | Display name override                                                   |

**If source and market are omitted, both assets default to Binance.**

### Time Range

| Field        | Type   | Default | Description                                                        |
| ------------ | ------ | ------- | ------------------------------------------------------------------ |
| `start_date` | string | null    | ISO date e.g. `"2024-01-01"` — if omitted, uses all available data |
| `end_date`   | string | null    | ISO date e.g. `"2025-01-01"` — if omitted, uses today              |

### Strategy Mode

| Field          | Type   | Default | Description                                                         |
| -------------- | ------ | ------- | ------------------------------------------------------------------- |
| `mode`         | string | `"SMA"` | `"SMA"` = dynamic Bollinger Bands, `"FIXED"` = fixed ratio range    |
| `window_size`  | int    | `30`    | Rolling window for SMA/EMA in days (SMA mode only)                  |
| `std_dev_mult` | float  | `2.0`   | Bollinger Band width in standard deviations (SMA mode)              |
| `use_ema`      | bool   | `true`  | Use EMA instead of SMA as center line                               |
| `min_ratio`    | float  | null    | Lower band threshold — buy A below this (FIXED mode only)           |
| `max_ratio`    | float  | null    | Upper band threshold — sell A above this (FIXED mode only)          |
| `step_size`    | float  | `50`    | % of available position to trade each signal (1-100)                |
| `no_loss_sell` | bool   | `true`  | Prevent "Buy A" trades if it realizes a loss relative to entry cost |

## Response Structure

```json
{
  "summary": {
    "pair": "ETHUSDT / BTCUSDT",
    "mode": "SMA",
    "start": "2024-01-02",
    "end": "2024-12-31",
    "data_points": 365,
    "current_ratio": 0.054321,
    "final_return_pct": 12.34,
    "annualized_pct": 12.34,
    "total_trades": 18,
    "buy_trades": 9,
    "win_rate_pct": 77.8,
    "avg_gain_per_trade_pct": 1.23,
    "current_holding": "A"
  },
  "events": [ ... ],   // Last 50 trades
  "history": [ ... ],  // Last 365 daily P&L snapshots
  "params": { ... }    // Echoed strategy parameters
}
```

### Key `summary` Fields

- `final_return_pct` — total cumulative return over the period (%, vs holding A)
- `annualized_pct` — annualized equivalent return
- `win_rate_pct` — % of "Buy A" trades that were profitable
- `current_holding` — `"A"` or `"B"` — current dominant position at period end
- `current_ratio` — latest A/B price ratio

### Each `events[]` Entry

```json
{
  "date": "2024-03-15",
  "type": "Buy A",
  "ratio": 0.05234,
  "mean": 0.055,
  "deviationBps": -502,
  "amount": 1.2345,
  "gainPct": 2.14,
  "posState": 0.6,
  "unitsA": 6.23,
  "unitsB": 0.0
}
```

## Common Scenarios

### Scenario 1: ETH vs BTC over 2024 (default Binance)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/defi/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "asset_a_symbol": "ETHUSDT",
    "asset_b_symbol": "BTCUSDT",
    "start_date": "2024-01-01"
  }'
```

### Scenario 2: SOL vs ETH, last 180 days, tighter bands

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/defi/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "asset_a_symbol": "SOLUSDT",
    "asset_b_symbol": "ETHUSDT",
    "start_date": "2024-08-01",
    "window_size": 20,
    "std_dev_mult": 1.5
  }'
```

### Scenario 3: weETH / WETH on Base (GeckoTerminal DEX pool)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/defi/backtest \
  -H "Content-Type: application/json" \
  -d '{
    "asset_a_source": "gecko",
    "asset_a_symbol": "0x91f0f34916ca4e2cce120116774b0e4fa0cdcaa8",
    "asset_a_network": "base",
    "asset_a_label": "weETH",
    "asset_b_source": "gecko",
    "asset_b_symbol": "0x4200000000000000000000000000000000000006",
    "asset_b_network": "base",
    "asset_b_label": "WETH",
    "mode": "FIXED",
    "min_ratio": 1.0,
    "max_ratio": 1.05
  }'
```

## Interpreting Results

**When to rotate:**

- `current_ratio` < lower Bollinger Band → Asset A is historically cheap relative to B → signal to **accumulate A**
- `current_ratio` > upper Bollinger Band → Asset A is overbought relative to B → signal to **reduce A / take B**

**Performance benchmarks:**

- `annualized_pct > 10%` — strong strategy for the period
- `win_rate_pct > 60%` — edge over random trading
- `annualized_pct < 0%` — consider inverting A/B or adjusting window/bands

**Note:** Past backtest performance does not guarantee future returns. This is for research only.

## Notes

- Binance K-line data is fetched live; first call may take 2-5 seconds
- GeckoTerminal supports up to ~1000 daily candles (~3 years) per pool
- If two assets have different trading hours, overlapping timestamps only are used for signal generation
- The backtest starts fully holding Asset A and rotates gradually based on signals
