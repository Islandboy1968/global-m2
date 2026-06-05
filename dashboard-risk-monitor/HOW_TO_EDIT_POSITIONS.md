# How to Edit Positions — GMI Risk Monitor

You control which assets appear in the dashboard by editing **one file**:
`dashboard-risk-monitor/positions.py`. It has two lists — `PRO_POSITIONS` (the RV Pro
table) and `ALPHA_ASSETS` (the RV Alpha table). The pipeline reads this file on every
run and recomputes everything. No engineering involvement; you publish positions the
way you publish a research note.

---

## The format
Each position is one line:
```python
{"name": "Bitcoin", "ticker": "BTC", "tv_symbol": "INDEX:BTCUSD", "category": "Crypto", "secular_method": "logchannel", "is_yield": False},
```

## Add a position
Add a line to the relevant list. Example — adding MicroStrategy to Pro:
```python
{"name": "MicroStrategy", "ticker": "MSTR", "tv_symbol": "NASDAQ:MSTR", "category": "Equity", "secular_method": "logchannel", "is_yield": False},
```

## Remove a position
Delete its line.

## Reorder
Move the lines — the table renders in list order.

---

## Field reference
| Field | What it is |
| --- | --- |
| `name` | Display name shown in the table (e.g. "Bitcoin") |
| `ticker` | Short code shown in the table (e.g. "BTC") |
| `tv_symbol` | The TradingView symbol the pipeline pulls — e.g. `INDEX:BTCUSD`, `NASDAQ:MSTR`, `TVC:GOLD`, `COMEX:HG1!` |
| `category` | Free-text grouping label (Crypto / Equity / Commodity / Rates / …) |
| `secular_method` | `"logchannel"` for crypto + crypto-adjacent equities (COIN, HOOD, MSTR…) + carbon; `"sma60"` for traditional assets (equities, FX, rates, commodities, gold) |
| `is_yield` | `True` only for yields/rates (renders the price as a %); otherwise `False` |

---

## How it goes live
1. Save your edit and **commit** it.
2. The **scheduled pipeline** recomputes on its next run — or trigger the workflow to
   refresh immediately.
3. **Safety net:** if a `tv_symbol` doesn't resolve on TradingView, the build **fails
   loud** in CI and names the bad symbol. A typo can never silently blank a row or show
   stale data on the live board.

## Easiest ways to do it
- **Tell Claude** "add MSTR / drop SUI" and it edits the list + refreshes the board.
- **Edit on GitHub:** open `positions.py` → pencil (edit) icon → change a line → Commit.
  `https://github.com/Islandboy1968/global-m2/blob/main/dashboard-risk-monitor/positions.py`

---

### Finding a TradingView symbol
Search the asset on tradingview.com; the symbol is `EXCHANGE:TICKER` shown on the
chart (e.g. `NASDAQ:AAPL`, `AMEX:TAN`, `LSE:CARB`). Crypto often works as
`COINBASE:<COIN>USD` or `INDEX:<COIN>USD`; indices via their ETF proxy (e.g. `NASDAQ:QQQ`).
If unsure, add it and let the fail-loud build tell you whether it resolved.
