# AutoM2026 Data Interpretation Reference

## Macro Indicators — Crypto Context

### Federal Funds Rate (`macro.fed_rate`)

| Range    | Crypto Signal                                     |
| -------- | ------------------------------------------------- |
| > 5.0%   | High-rate pressure → risk-off, bearish headwind   |
| 3.0–5.0% | Neutral to slightly negative                      |
| < 3.0%   | Loose policy → liquidity supportive, bullish bias |

**Key signals**: Rate cuts are historically bullish for crypto. Rate hikes are bearish.

### 10-Year Treasury Yield (`macro.treasury_10y`)

- Rising yield → risk assets under pressure (inverse relationship with crypto)
- Yield > 4.5%: meaningful headwind
- Yield < 3.5%: supportive environment

### US Dollar Index — DXY (`macro.dxy`)

- Strong USD (DXY rising) → typically bearish for crypto (inverse correlation ~-0.6 to -0.8)
- DXY > 105: strong headwind
- DXY < 100: tailwind for risk assets

### M2 Money Supply YoY (`macro.m2_growth_yoy`)

- Positive and accelerating → liquidity expansion → bullish
- Negative → liquidity contraction → bearish
- Leading indicator: M2 changes typically precede crypto moves by 3-6 months

### Fear & Greed Index (`macro.fear_greed.value`)

| Score  | Classification | Trading Implication         |
| ------ | -------------- | --------------------------- |
| 0–24   | Extreme Fear   | Contrarian buy zone         |
| 25–44  | Fear           | Potential accumulation      |
| 45–55  | Neutral        | No strong signal            |
| 56–74  | Greed          | Caution, consider reducing  |
| 75–100 | Extreme Greed  | Contrarian sell / high risk |

### Stablecoin Supply (`macro.stablecoin_supply_b`)

- Rising stablecoin supply → dry powder available → latent buying pressure
- Falling → capital flowing out of crypto ecosystem
- Track trend direction, not absolute value

### ETF Net Flows (`macro.etf_flows.btc/eth/sol.value_usd`)

- Value is in USD (not millions)
- e.g., `123000000` = $123M inflow
- Positive = net inflow (bullish institutional signal)
- Negative = net outflow (bearish)

**Significance thresholds for BTC ETF:**
| Daily Flow | Significance |
|---|---|
| > $500M | Very strong institutional buying |
| $100M–$500M | Moderate buying pressure |
| -$100M–$100M | Quiet / neutral |
| < -$100M | Selling pressure |
| < -$500M | Strong institutional selling |

---

## On-Chain Valuation Indicators 🆕

### ahr999 定投指数 (`macro.ahr999`)

| Range    | Signal                                      |
| -------- | ------------------------------------------- |
| < 0.45   | **强力抄底区间** — 历史确定性极高的买入时机 |
| 0.45–1.2 | 定投区间 — 适合持续分批买入                 |
| > 1.2    | 超出定投价值区，价格高于长期回报预期        |

### MVRV Ratio (`macro.mvrv_ratio`)

| Range   | Signal                                              |
| ------- | --------------------------------------------------- |
| < 1.0   | **极度低估** — 市场价格低于已实现成本，历史底部买点 |
| 1.0–2.5 | 正常估值区间                                        |
| 2.5–3.7 | 偏高估，周期中后期                                  |
| > 3.7   | **历史高估区域** — 逢高减仓预警                     |

### 200周均线 (`macro.wma200`)

- 比特币历史最终底部支撑线，从未被长期跌破
- 价格低于 200WMA：历史性买入机会
- 价格 > 200WMA × 3：偏离过大，注意顶部风险

### MSTR mNAV (`macro.mstr_mnav`)

- mNAV = MSTR市值 / MSTR持有BTC总价值
- < 1.5x: 机构情绪冷淡，可能接近底部
- > 4.0x: 机构溢价过高，通常领先 BTC 价格见顶

---

## Technical Analysis — Recommended Combinations

When calling `/api/v1/data/klines`, use these indicator combos:

### Quick Signal (1h timeframe, 100 bars)

- EMA 9/21/50 alignment
- RSI 14 (oversold < 30, overbought > 70)
- MACD histogram direction

### Trend Confirmation (4h timeframe, 100 bars)

- EMA 21/50/200 alignment
- Bollinger Band position (%B)
- ATR for volatility context

### Multi-Timeframe (2 calls: 1h + 4h)

- Use 4h for trend direction
- Use 1h for entry timing

---

## API Response Time Expectations

| Endpoint                       | Expected Latency               |
| ------------------------------ | ------------------------------ |
| `/api/v1/data/snapshot`        | 1–4s (fetches FRED + F&G live) |
| `/api/v1/data/klines/{symbol}` | 0.3–1s                         |
| `/api/v1/data/signals` (GET)   | < 0.1s                         |
| `/api/v1/data/signals` (POST)  | < 0.2s                         |

---

## Common Issues

**`markets[]` is empty**: No symbols in MarketWatch. Add at http://YOUR_SERVER_IP:8080/market  
**`macro.fed_rate` is null**: FRED API key not set or rate limit hit (free tier: 120 req/min)  
**`macro.fear_greed` is null**: External API timeout, retry OK  
**K-lines returns empty**: Symbol not found on Binance — verify symbol exists (e.g., BTC not BTCUSDT)
