# Macro Strategy Analysis Protocol

Load this file ONLY when the user explicitly requests macro analysis, market outlook, or strategy assessment.
After completing analysis, you MUST write back results to the data service (see § Mandatory Writeback).

---

## Step 1 — Fetch Data

```bash
# Primary: macro + real-time prices (always required)
curl -s http://YOUR_SERVER_IP:8080/api/v1/data/snapshot
```

The snapshot now includes **chain-level and valuation fields** in addition to traditional macro data.

---

## Step 2 — Score Each Macro Indicator

Score each indicator: **+1 (bullish)**, **0 (neutral)**, **-1 (bearish)**. Use the snapshot response.

### 2.1 Liquidity & Rate Environment (传统宏观)

| Indicator             | Bullish (+1)    | Neutral (0) | Bearish (-1) |
| --------------------- | --------------- | ----------- | ------------ |
| `macro.fed_rate`      | < 3.5%          | 3.5–5.0%    | > 5.0%       |
| `macro.treasury_10y`  | < 3.5%          | 3.5–4.5%    | > 4.5%       |
| `macro.dxy`           | < 100           | 100–107     | > 107        |
| `macro.m2_growth_yoy` | > 5% and rising | 0–5%        | < 0%         |

> **DXY note**: DXY > 110 counts as **-2** (double weight — strong dollar is the single biggest headwind for crypto).

### 2.2 Market Sentiment (情绪)

| Indicator                         | Bullish (+1)        | Neutral (0) | Bearish (-1)         |
| --------------------------------- | ------------------- | ----------- | -------------------- |
| `macro.fear_greed.value`          | ≤ 25 (Extreme Fear) | 26–55       | ≥ 80 (Extreme Greed) |
| `macro.stablecoin_supply_b` trend | Growing QoQ         | Flat        | Shrinking            |

> **Fear & Greed contrarian rule**: Score ≤ 25 is historically the highest-return entry zone (not a sell signal). Score ≥ 80 signals crowding, not strength.

### 2.3 Institutional Flow — ETF (资金)

Use the latest daily flow from `macro.etf_flows`. Convert to millions for readability.

| BTC ETF Daily Flow | Score |
| ------------------ | ----- |
| > +$200M           | +1    |
| -$200M to +$200M   | 0     |
| < -$200M           | -1    |

Apply same thresholds for ETH (scale: > +$50M = +1, < -$50M = -1).
SOL ETF: any positive flow = +1, any outflow > $20M = -1.

### 2.4 BTC On-Chain Valuation 🆕 (链上估值 — 高权重区)

These are the strongest forward-looking signals for BTC specifically.

| Indicator                    | Bullish (+1)        | Neutral (0)         | Bearish (-1)      | Weight |
| ---------------------------- | ------------------- | ------------------- | ----------------- | ------ |
| `macro.ahr999`               | < 0.45 (抄底区间)   | 0.45–1.2 (定投区间) | > 1.2 (起飞/高估) | **×2** |
| `macro.mvrv_ratio`           | < 1.0 (极度低估)    | 1.0–2.5             | > 3.7 (历史高估)  | **×2** |
| `macro.wma200` (价格/均线比) | 价格 < 200WMA × 1.0 | 1.0×–1.5×           | > 2.5× (偏离过高) | ×1     |

> **ahr999 < 0.45**: 历史上几乎每次都是绝佳买点，直接判定 BUY，conviction 极高。
> **MVRV < 1.0**: 从历史来看每次都是周期底部买入窗口。
> **MVRV > 3.7**: 接近历史顶部区域，应开始减仓计划。

### 2.5 Mining Health 🆕 (矿业健康)

| Indicator                                             | Bullish (+1) | Neutral (0) | Bearish (-1)                |
| ----------------------------------------------------- | ------------ | ----------- | --------------------------- |
| `macro.miners_profitable / macro.miners_total` 存活率 | > 70%        | 40–70%      | < 40% (矿工恐慌性关机/抛售) |

> **矿工存活率低**：电费水下矿机大量关机，短期抛压大，但往往也是阶段性底部信号（反向）。

### 2.6 Institutional Bitcoin Exposure — MSTR mNAV 🆕 (机构溢价)

| Indicator         | Bullish (+1)               | Neutral (0) | Bearish (-1)                     |
| ----------------- | -------------------------- | ----------- | -------------------------------- |
| `macro.mstr_mnav` | < 1.5x (机构不热情 = 底部) | 1.5x–3.0x   | > 4.0x (机构热情过旺 = 顶部预警) |

> **MSTR mNAV 极高** 意味着投机资金正在以远超 BTC 价值的代价涌入，历史上往往先于 BTC 价格见顶。

---

## Step 3 — Aggregate Signal

```
Total Score = sum of all indicator scores
  - ahr999 and mvrv_ratio count ×2 (double weight)
  - dxy > 110 counts as -2

Max possible: +15   Min possible: -16
```

Normalize for output by converting to percentage conviction:

```
Conviction % = (total_score + 16) / 31 × 100  (range 0–100)
```

| Normalized Score | Bias           | Label                               |
| ---------------- | -------------- | ----------------------------------- |
| +8 to +15        | 📈 Strong Bull | 全面做多：链上底部 + 宏观流动性支撑 |
| +3 to +7         | 🟢 Mild Bull   | 宏观偏多，择机建仓                  |
| -2 to +2         | ⚪ Neutral     | 观望，等待方向确认                  |
| -6 to -3         | 🔴 Mild Bear   | 宏观偏空，减仓防守                  |
| < -6             | 💀 Strong Bear | 全面避险，高风险敞口需清退          |

---

## Step 4 — Per-Asset Assessment

For each asset in `markets[]`:

1. **Price context**: 24h change + position in 24h range (near high vs. near low)
2. **Relative strength**: Compare % change across BTC/ETH/SOL — who is leading/lagging?
3. **ETF divergence** (if applicable): is ETF flow direction consistent with price direction?
4. **On-chain divergence** (BTC only): Is `ahr999` / `mvrv_ratio` consistent with current price action?
5. **TA confirmation** (only if K-line data fetched):
   - EMA trend (9/21 cross direction)
   - RSI level (oversold <30, overbought >70)
   - Candle pattern near key levels

---

## Step 5 — Generate Output

Structure your response as:

```
📊 宏观策略分析 — [日期]

综合评分: [X / 15]  →  [Bias Label]  (信心度: X%)

指标打分:
▸ 传统宏观
  • 联储利率 X% → [+1/0/-1]
  • 10Y国债 X% → [+1/0/-1]
  • DXY X → [+1/0/-1/-2]
  • M2同比 X% → [+1/0/-1]
▸ 市场情绪
  • 恐贪指数 X → [+1/0/-1] [逆向逻辑注释]
  • 稳定币规模 $XB → [+1/0/-1]
▸ 机构资金
  • BTC ETF流向 $XM → [+1/0/-1]
  • ETH/SOL ETF → [...]
▸ 链上估值 (×2权重)
  • ahr999: X → [+2/0/-2] [区间判断，如: 抄底区间]
  • MVRV Ratio: X → [+2/0/-2] [低估/正常/高估]
  • 200WMA 位置: $X (当前价 X倍) → [+1/0/-1]
▸ 矿业健康
  • 盈利矿机率 X/X → [+1/0/-1]
▸ 机构溢价
  • MSTR mNAV: Xx → [+1/0/-1]

综合判断:
[2-3句话：当前周期位置 + 链上信号解读 + 主要风险 + 主要机会]

各资产倾向:
• BTC：[看多/中性/看空 + 1句链上判断理由]
• ETH：[看多/中性/看空 + 1句理由]
• SOL：[看多/中性/看空 + 1句理由]

操作建议:
[基于链上指标给出1条具体建议，ahr999<0.45时须明确建议加仓]
```

---

## Step 6 — Mandatory Writeback ⚠️

**You MUST call this after every macro analysis, no exceptions.**
Write one signal record per analyzed asset (at minimum BTC).

```bash
curl -s -X POST http://YOUR_SERVER_IP:8080/api/v1/data/signals \
  -H "Content-Type: application/json" \
  -d '{
    "agent_id": "YOUR_AGENT_ID",
    "strategy_name": "Macro + On-Chain Strategy Analysis",
    "symbol": "BTC",
    "action": "BUY",
    "conviction": 78,
    "price_at_signal": 93200.0,
    "reason": "Macro score +9/15 (Mild Bull): ahr999=0.277 抄底区间 (×2), MVRV=1.18 正常偏低, F&G=8 极度恐慌逆向买点, DXY=118 是主要负向压力。",
    "raw_analysis": {
      "macro_score": 9,
      "bias": "Mild Bull",
      "scores": {
        "fed_rate": 0,
        "treasury_10y": 0,
        "dxy": -2,
        "m2": 0,
        "fear_greed": 1,
        "stablecoin": 0,
        "btc_etf": -1,
        "ahr999": 2,
        "mvrv_ratio": 0,
        "wma200_ratio": 1,
        "miners_health": 0,
        "mstr_mnav": 0
      }
    }
  }'
```

**Field guidelines for writeback:**

- `action`: must be `BUY`, `SELL`, or `HOLD` — map from bias (Strong Bull→BUY, Strong Bear→SELL, else→HOLD)
- `conviction`: derived from normalized score (see Step 3), minimum 10
- `reason`: include macro score, top 2-3 driving factors (especially on-chain), and the key risk
- `raw_analysis.scores`: include every scored indicator including the new on-chain ones

---

## Reference: Macro Cycle Cheat Sheet (with On-Chain)

| Cycle Phase              | DXY          | MVRV    | ahr999   | F&G    | Typical Crypto Action |
| ------------------------ | ------------ | ------- | -------- | ------ | --------------------- |
| Bull top (distribution)  | Turning up   | > 3.5   | > 1.2    | 80–100 | 开始减仓              |
| Early bear               | Rising       | 2.0–3.5 | 0.8–1.2  | 40–60  | 减仓，持现金          |
| Deep bear (accumulation) | Peaking      | < 1.0   | < 0.45   | 0–25   | **强力抄底区间**      |
| Recovery                 | Turning down | 1.0–2.0 | 0.45–1.2 | 25–50  | 加大仓位              |
| Bull run                 | Weak         | 2.0–3.5 | 0.8–1.2  | 50–80  | 持仓/追势             |

> 💡 **When ahr999 < 0.45 AND MVRV < 1.0 simultaneously**: This is a historically rare "double bottom signal" — highest-confidence BUY opportunity. Conviction should be ≥ 85.
