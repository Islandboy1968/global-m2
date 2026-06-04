# Dashboard Spec — The GMI Compounding Machine

> Filled into the P&E template, using the worked-example conventions from the GMI
> Risk Monitor spec. This is the hand-off contract: P&E build/verify from this.

---

## 1. Title & Basics

| | |
| --- | --- |
| **Dashboard name** | The GMI Compounding Machine |
| Author | Raoul |
| Version / date | 1.0 — 4 Jun 2026 |
| Refresh cadence | Weekly, after Friday US close (data is weekly closes) |
| Reuses an existing dashboard's look? | No — its own dark/lilac shell. Self-contained template. |

---

## 2. Description

An interactive teaching tool that plots an asset (BTC or NDX) against a **frozen
log-linear trend** with ±1σ / ±2σ bands, and simulates a simple rules-based
strategy: add a fixed dollar amount every time price is "oversold" below trend,
optionally trim a little when "overbought" above it.

---

## 3. What It Does & The Value It Brings

It answers: *"where is this asset relative to its long-run trend, and what would a
mechanical buy-the-dips plan have produced?"* The reader sees buy/sell signals on
the price chart and three portfolio paths (HODL, no-sells compounding, with
lifestyle-chip sells) side by side. The point is execution simplicity and
anti-fragility — a green dot appears, you add — without timing tops and bottoms.

---

## 4. How To Use It (reader-facing)

Read the σ readout at the top: below −1σ (green) is the buy zone, above +1σ (pink)
is the sell zone. Move the sliders to size your own plan — initial stake, how much
to add per dip, whether to take lifestyle chips. The green dots are historical buy
signals, gold dots are sells. The forward channel is a band of *possible* prices,
not a forecast. Treat it as a weekly framework, not an intraday tool.

---

## 5. Design & Attached Mockups

**Look & feel:** dark (`#08080F`), lilac accent (`#B794F4`), JetBrains Mono for
numbers, Outfit for text. Per-asset accent colour (BTC gold, NDX blue).

**Attachments:** `compounding-machine.html` is the working reference (this folder).

**Panels, top to bottom:**

| # | Panel | Type | Shows |
| --- | --- | --- | --- |
| 1 | Header | banner | title + asset name + frozen-CAGR / 1σ summary |
| 2 | Asset toggle | control | switch asset (driven by the asset registry) |
| 3 | Current Position | status banner | last price, trend, distance, current σ, buy/sell-zone flag, data source |
| 4 | Controls | controls | sliders/inputs: initial stake, buy σ, add amount, sell σ, sell % |
| 5 | The Story | number tiles | total invested, out of pocket, value in market, cash from sells, vs HODL, no-sells |
| 6 | Price vs Log Trend | chart | price + trend + ±1σ/±2σ bands + forward channel + buy/sell dots |
| 7 | Portfolio Comparison | chart | strategy vs no-sells vs HODL paths |
| 8 | Signal History | table | every buy and sell with date + price |
| 9 | How it works | text | methodology |

---

## 6. Data Sources Needed

| Data input | What it's for | How fresh | If unavailable |
| --- | --- | --- | --- |
| Weekly close series per asset (`{d, c}`) | the price line + all signals | weekly (Fri close) | reuse last injected file; degrade per-asset, not whole page |
| Asset registry (author-editable) | which assets/tabs appear + their source + projection horizon | on edit | n/a |

> The frozen regression is computed **in the dashboard** from the weekly series, so
> the only input the pipeline must supply is the series itself. Source is swappable
> per asset (see §9 and the handover doc) — default TradingView; NDX may use an
> internal feed or stay on the injected static series.

---

## 7. Tiers & Access

Single tier — all panels visible to all users. (If gated later, the natural split
is Free = BTC only, Pro = all assets + editable sliders; one boolean on each
registry row.)

---

## 8. Formulas & How They're Calculated

### Frozen log-linear trend + σ bands
- **Applies to:** every asset; panels 3, 6, 9.
- **Input:** weekly closes from `startDate` (2017-09-01) to `freezeDate` (2025-12-31).
- **Output:** trend value at any date, ±1σ/±2σ bands, and each point's σ-distance.
- **Rule (plain English):** Take logs of the closes up to the freeze date, fit a
  straight line (least squares) of log-price vs days-since-start. The line is the
  "trend"; the standard deviation of the residuals is "1σ". Bands are the trend
  ×e^(±σ). A point's `logDev` = (log price − trend) / σ. Frozen means the fit never
  moves once past the freeze date — new weeks are scored against the locked line.
- **Reference code:** `lib/compute.js` → `fitFrozenRegression`, `buildChannel`.
- **Tunable numbers (author):** `buyThreshold` σ, `sellThreshold` σ. **Dev-locked:**
  startDate, freezeDate.

### Buy/sell simulation (lifestyle chips)
- **Applies to:** panels 5, 6, 7, 8.
- **Input:** the scored series + slider params.
- **Output:** buy/sell signal lists, three portfolio paths, summary stats.
- **Rule:** Start with `initialStake` in the asset. When price closes below
  −`buyThreshold`σ and the buy trigger is "armed", add a fixed `buyAmount`; re-arm
  only after price recovers past −buyThreshold/2. Symmetric for sells: above
  +`sellThreshold`σ, trim `sellPct` of holdings to cash. Cash funds future buys
  first (reducing out-of-pocket). The "no sells" path never trims; "HODL" only ever
  holds the initial stake.
- **Reference code:** `lib/compute.js` → `simulate`.
- **Tunable numbers (author):** initialStake, buyThreshold, buyAmount, sellThreshold,
  sellPct (all exposed as sliders).

**How we'll know it's right** (run `node` against `lib/compute.js` + `data/data.js`;
defaults: stake 100k, buy/sell 1.0σ, add 25k, sell 20%):

1. **BTC** frozen fit → **45% implied CAGR**, **1σ = 60%**. Latest point ≈ **−1.2σ**
   (in the buy zone) at last price ~$68,396, trend ~$118,513.
2. **BTC** produces **4 buys and 2 sells**; the **first buy is 2018-11-23 @ ~$4,347**.
3. **NDX** frozen fit → **18% implied CAGR**, **1σ = 13%**; **8 buys, 2 sells**;
   latest ≈ **−0.3σ** (neutral, no zone badge).
4. Set sell % to 0 → Portfolio Comparison hides the green "with sells" line and the
   Signal History sells column reads "DISABLED".
5. Forward points carry trend + bands but **no price** (the channel is not a forecast).

---

## 9. Component Data Details (implementation reference)

> **Injection contract:** the pipeline rewrites **only** `data/data.js`, between the
> markers `// __PIPELINE_DATA_START__` / `// __PIPELINE_DATA_END__`. The shell
> (`compounding-machine.html`), the maths (`lib/compute.js`) and the registry/
> adapters (`lib/sources.js`) are never touched between refreshes.

### Injected data object (`window.DASHBOARD_DATA`)
| Field | Type | Example | Meaning / format |
| --- | --- | --- | --- |
| `updated` | string | "2026-04-10" | as-of stamp (last weekly close) |
| `assets` | object keyed by asset key | `{ BTC: {...}, NDX: {...} }` | one entry per registry asset |
| `assets.<KEY>.series` | array of points | see below | the weekly close series |

### Series points (`assets.<KEY>.series`)
| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `d` | string `"YYYY-MM-DD"` | "2017-09-01" | Friday-anchored week key |
| `c` | number | 4892 | weekly close |

### Asset registry rows (`lib/sources.js` → `ASSET_REGISTRY`, author-editable)
| Field | Type / allowed values | Example | Notes |
| --- | --- | --- | --- |
| `key` | string | "BTC" | must match a `DASHBOARD_DATA.assets` key |
| `name` | string | "Bitcoin" | display name |
| `ticker` | string | "BTC" | toggle label |
| `unit` | string | "BTC" / "units" | used in "% of <unit>" copy |
| `color` | string (hex) | "#F6C343" | accent |
| `source` | "injected" \| "coingecko" \| "internal" | "injected" | which adapter feeds it (the swap point) |
| `symbol` | string | "INDEX:BTCUSD" | provider symbol for live adapters |
| `projectToYear` | number | 2035 | how far the forward channel extends |

**Field conventions** (shared across dashboards): short chart keys (`d`/`c`);
dates `"YYYY-MM-DD"`; any absent field typed `… | null`; one injected global named
`<THING>_DATA`; the human-readable stamp (`updated`) separate from the data.
