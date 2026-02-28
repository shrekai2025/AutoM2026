# TA Strategy Protocol

Load only when user requests TA analysis or entry/exit decisions.
After analysis, **must writeback** via `POST /api/v1/data/signals`.

---

## Timeframe Weights & Roles

| TF  | Role                 | Weight (3-TF) | Weight (4-TF) |
| --- | -------------------- | ------------- | ------------- |
| 1d  | Macro trend anchor   | —             | 40%           |
| 4h  | Primary trend        | 50%           | 30%           |
| 1h  | Momentum / execution | 35%           | 20%           |
| 15m | Entry timing         | 15%           | 10%           |

**Rule**: Longer TF wins on conflict. 15m BUY vs 4h DOWNTREND → HOLD.

---

## Signal Interpretation

### Grade

| Grade | Condition                               |
| ----- | --------------------------------------- |
| **A** | ≥2/3 TFs aligned + score ≥78 or ≤22     |
| **B** | ≥50% TFs aligned OR MACD cross detected |
| **C** | Single TF trigger or borderline score   |

### Conviction

| Score         | BUY/SELL   | Label  |
| ------------- | ---------- | ------ |
| ≥78 / ≤22     | BUY / SELL | Strong |
| 65–77 / 23–35 | BUY / SELL | Mild   |
| 36–64         | —          | HOLD   |

---

## Indicator Rules

**EMA** (`ema_9/21/50/200`): Price > EMA9 > 21 > 50 > 200 = full bull; reverse = full bear. Each level adds/subtracts confidence.

**RSI** (`rsi`): <30 oversold (buy zone) · >70 overbought (sell zone) · divergence = strong reversal signal.

**StochRSI** (`stoch_rsi.k/d`): k<20 oversold · k>80 overbought · k crosses d from below 20 = bullish · from above 80 = bearish.

**MACD** (`macd.cross / trend / histogram`):

- `cross=golden` → **+2pts** best buy signal
- `cross=death` → **-2pts** best sell signal
- `trend=bullish` + histogram growing → +1; macd_line > 0 → +0.5

**Bollinger** (`bollinger.percent_b / squeeze`):

- %B < 0 extreme oversold · %B > 1 extreme overbought · `squeeze=true` → breakout imminent (direction TBD)

**Volume** (`volume.trend / volume_ratio`):

- `surge` (>2x) = high conviction · `dry` (<0.5x) = treat price moves as suspect

**Trend Structure** (`trend_structure.structure`):

- `UPTREND` HH+HL · `DOWNTREND` LH+LL · `CONSOLIDATION` no clear sequence

**Candle Patterns** (`candle_patterns`):

- `bullish_engulfing` / `hammer` → bullish reversal
- `bearish_engulfing` / `shooting_star` → bearish reversal
- `doji` → indecision, wait for next candle

---

## Multi-TF Confluence

```
≥75% TFs aligned → trust signal fully
50% aligned → standard confidence
<50% aligned → reduce size or skip
```

Golden setup: 4h UPTREND + 1h MACD golden cross + RSI<40 + volume surge → Grade A BUY  
Best exit: 4h DOWNTREND + 1h MACD death cross + RSI>65 + shooting_star → Grade A SELL

---

## Stop Loss / Take Profit

Use API values directly: `stop_loss` = entry ± ATR×2 · `take_profit` = entry ± ATR×3.  
Grade A: consider widening TP to ATR×4-5 in trending markets.  
Grade C: tighten SL to ATR×1.5.

---

## Output Format

```
📈 TA — [SYMBOL] [DATE]
信号: [BUY/SELL/HOLD] | 信念: [X]/100 | 等级: [A/B/C]
价格: $X | 止损: $X | 止盈: $X | R:R = X:1

评分: 4h=[X] · 1h=[X] · 15m=[X]
关键信号: [top 3-5 from reasons[], 中文]
建议: [具体操作 + 仓位 + 等待条件]
风险: [1-2 主要不确定因素]
```

---

## Writeback (mandatory after every analysis)

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/data/signals \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id":"AGENT","strategy_name":"TA Multi-TF",
    "symbol":"BTC","action":"BUY","conviction":74.5,
    "price_at_signal":96420,"stop_loss":93850,"take_profit":101200,
    "reason":"[A] [4h]EMA多头排列; [1h]MACD金叉; RSI超卖(28)",
    "raw_analysis":{"grade":"A","score_by_tf":{"4h":78,"1h":72,"15m":65}}
  }'
```

`action` = BUY if conviction ≥65, SELL if ≤35, else HOLD.
