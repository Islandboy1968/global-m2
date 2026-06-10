# Dashboard Spec & Integration — The GMI Compounding Machine

> Filled into Real Vision's `dashboard-spec-template.md` (per Andrew, 4 Jun), with
> the working prototype included as the design reference, plus an integration
> section (§10) covering the platform build and the three open questions.
>
> **Live prototype (BETA):**
> https://islandboy1968.github.io/global-m2/dashboard-template/compounding-machine-beta.html
> **GMI-branded skin (same engine, accompanies the GMI dashboards):**
> https://islandboy1968.github.io/global-m2/dashboard-template/compounding-machine-gmi-beta.html
> **Code + this doc:** `Islandboy1968/global-m2` → `dashboard-template/`
>
> Two shells, one engine: `compounding-machine.html` (RV dark restyle, the P&E
> hand-off below) and `compounding-machine-gmi.html` (GMI light brand — white
> page, pink `#f12a5a`, Teko/AT Aero/DM Mono, token-for-token with the live
> Everything Code dashboard). Both read the same `data/data.js` + `lib/compute.js`
> + `lib/sources.js`; the hourly pipeline bakes a self-contained beta of each.
> The four-layer split (§10) is what makes the second skin a shell-only file.

---

## 1. Title & Basics

| | |
| --- | --- |
| **Dashboard name** | The GMI Compounding Machine |
| Author | Raoul |
| Version / date | 1.1 — 4 Jun 2026 |
| Refresh cadence | Weekly closes; data refreshed hourly by pipeline (delayed is fine — not an intraday tool) |
| Reuses an existing dashboard's look? | Yes — Real Vision dark dashboard aesthetic (Claude Design restyle) |

---

## 2. Description

An interactive teaching tool that plots an asset (BTC or QQQ) against a **frozen
log-linear trend** with ±1σ / ±2σ bands projected forward, and simulates a simple
rules-based strategy: add a fixed dollar amount when price is "oversold" below the
trend, optionally trim a little when "overbought" above it.

---

## 3. What It Does & The Value It Brings

It answers, at a glance: *"where is this asset versus its long-run trend, and what
would a mechanical buy-the-dips plan have produced?"* The reader sees buy/sell
signals on the price chart and three portfolio paths (HODL, no-sells compounding,
with lifestyle-chip sells) side by side. The point is execution simplicity and
anti-fragility — a green dot appears, you add — without timing tops and bottoms.

---

## 4. How To Use It (reader-facing)

Read the **σ** readout at the top: below −1σ (green) is the buy zone, above +1σ
(red) is the sell zone. Move the sliders to size your own plan — initial stake, how
much to add per dip, whether to take lifestyle chips. Green dots are historical
adds, red dots are trims. The forward channel is a band of *possible* prices, not a
forecast. Treat it as a weekly check-in, not an intraday tool. (This text is also
rendered on the dashboard in the "How to use it" panel.)

---

## 5. Design & Attached Mockups

**Look & feel:** Real Vision dark dashboard aesthetic — bg `#0a0d14`, lime accent
`#c3f53c`, cyan price line `#22d3ee`, green/red buy/sell semantics, hairline-bordered
cards, **Hanken Grotesk** with tabular figures. No drop shadows.

**Design reference (per Andrew's request, include the prototype):**
- The **live BETA** above is the working, high-fidelity reference.
- The restyle was delivered by **Claude Design** (bundle in Drive: `Compounding Machine.html`,
  `engine/`, `README.md` with the exact token list).

**Panels, top → bottom:**

| # | Panel | Type | Shows |
| --- | --- | --- | --- |
| 1 | Top accent bar | banner | lime→cyan hairline |
| 2 | Header | banner | asset eyebrow, title, frozen-CAGR/1σ summary, status pill, BTC\|QQQ toggle |
| 3 | Status strip | summary tiles | price, log trend, distance to trend, current σ + zone pill |
| 4 | Controls | sliders/inputs | initial stake, buy σ, add amount, sell σ, sell % |
| 5 | KPI grid | number tiles | total invested, out of pocket, in-market, cash from sells, vs HODL, no-sells |
| 6 | Price vs Log Trend | chart | price + trend + ±1σ/±2σ bands + forward channel + buy/sell dots |
| 7 | Portfolio Value | chart | strategy vs no-sells vs HODL |
| 8 | Signal History | table | every buy/sell with date + price + amount |
| 9 | How to use it | text | methodology / how-to-read |
| 10 | Footer | text | source label + disclaimer |

---

## 6. Data Sources Needed

| Data input | What it's for | How fresh | If unavailable |
| --- | --- | --- | --- |
| Weekly close series per asset (`{d, c}`) | the price line + all signals | weekly (Fri close); refreshed hourly | reuse last injected file; degrade per-asset, not whole page |
| Asset registry (author-editable) | which assets/tabs appear + source + projection horizon | on edit | n/a |

- **Assets:** BTC and **QQQ** (the tradable Nasdaq-100 proxy — index data is licensed/
  awkward; QQQ percentages track closely, which is what the σ signal needs).
- The frozen regression is computed **in the dashboard** from the weekly series, so
  the only input a feed must supply is the series itself.
- **Today (beta):** a GitHub Action pulls real weekly BTC + QQQ closes from TradingView
  and bakes them into the file hourly — no in-browser data call.
- **Production:** swap to Real Vision's own end-of-day feed (see §10). End-of-day is
  sufficient; this is not a real-time/trading dashboard.

---

## 7. Tiers & Access

Single tier — all panels visible to all users. (If gated later, a natural split is
Free = BTC only, Pro = all assets + editable sliders; one boolean per registry row.)

---

## 8. Formulas & How They're Calculated

### Frozen log-linear trend + σ bands
- **Applies to:** every asset; panels 3, 6, 9.
- **Input:** weekly closes from `2017-09-01` to the freeze date `2025-12-31`.
- **Output:** trend value at any date, ±1σ/±2σ bands, each point's σ-distance.
- **Rule:** Take logs of the closes up to the freeze date, least-squares fit
  log-price vs days-since-start. The line is the "trend"; the stdev of residuals is
  "1σ"; bands are trend ×e^(±σ). `logDev = (log price − trend)/σ`. **Frozen** means
  the fit never moves once past the freeze date — new weeks are scored against the
  locked line.
- **Reference code:** `lib/compute.js` → `fitFrozenRegression`, `buildChannel`.
- **Tunable (author):** `buyThreshold` σ, `sellThreshold` σ. **Dev-locked:** start/freeze dates.

### Buy/sell simulation (lifestyle chips)
- **Input:** the scored series + slider params.
- **Output:** buy/sell signal lists, three portfolio paths, summary stats.
- **Rule:** Start with `initialStake` in the asset. Below −`buyThreshold`σ (armed),
  add a fixed `buyAmount`; re-arm after price recovers past −buyThreshold/2. Symmetric
  for sells above +`sellThreshold`σ, trimming `sellPct` of holdings to cash. Cash funds
  future buys first (reducing out-of-pocket). "No sells" never trims; "HODL" only ever
  holds the initial stake.
- **Reference code:** `lib/compute.js` → `simulate`.

**How we'll know it's right** (runnable headlessly against `lib/compute.js` + `data/data.js`;
defaults: stake 100k, buy/sell 1.0σ, add 25k, sell 20%):
1. **BTC** → **45% implied CAGR**, **1σ = 60%**; **5 buys, 2 sells**; latest ≈ **−1.5σ**
   (buy zone), last close ~$63,354.
2. **QQQ** → **18% implied CAGR**, **1σ = 13%**; **8 buys, 3 sells**; latest ≈ **+1.3σ**
   (sell zone), last close ~$740.
3. Set sell % to 0 → the green "with sells" line hides and Signal History sells reads "disabled".
4. Forward points carry trend + bands but **no price** (the channel is not a forecast).

> These check-cases are the QA hooks — same numbers after any port = faithful.

---

## 9. Component Data Details (implementation reference)

> **Injection contract:** the data pipeline rewrites **only** `data/data.js`, between
> the markers `// __PIPELINE_DATA_START__` / `// __PIPELINE_DATA_END__`. The shell,
> `compute.js`, and `sources.js` are never touched between refreshes.

### Injected data object (`window.DASHBOARD_DATA`)
| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `updated` | string | "2026-06-04 20:20 UTC" | as-of stamp |
| `assets` | object keyed by asset key | `{ BTC:{…}, QQQ:{…} }` | one entry per registry asset |
| `assets.<KEY>.series` | array of `{d,c}` | see below | the weekly close series |

### Series points (`assets.<KEY>.series`)
| Field | Type | Example | Meaning |
| --- | --- | --- | --- |
| `d` | string `"YYYY-MM-DD"` | "2017-09-08" | Friday-anchored week key |
| `c` | number | 4892 | weekly close |

### Asset registry rows (`lib/sources.js` → `ASSET_REGISTRY`, author-editable)
| Field | Type / values | Example | Notes |
| --- | --- | --- | --- |
| `key` | string | "BTC" | must match a `DASHBOARD_DATA.assets` key |
| `name` / `ticker` | string | "Nasdaq 100 (QQQ)" / "QQQ" | display / toggle label |
| `unit` | string | "shares" / "BTC" | used in "% of <unit>" copy |
| `color` | hex | "#60A5FA" | accent |
| `source` | "injected" \| "platform" \| … | "injected" | which adapter feeds it (swap point) |
| `projectToYear` | number | 2030 | forward channel horizon |

**Conventions:** short chart keys (`d`/`c`); dates `"YYYY-MM-DD"`; absent fields typed
`… | null`; one injected global `<THING>_DATA`; `updated` stamp separate from data.

---

## 10. Integration & Hand-off (for P&E)

### The four layers (please preserve the split)
| Layer | File | Global | Role |
| --- | --- | --- | --- |
| **Shell** | `compounding-machine.html` | — | UI/render only; holds no data, no maths |
| **Data** | `data/data.js` | `window.DASHBOARD_DATA` | pipeline-written series (between markers) |
| **Compute** | `lib/compute.js` | `window.GMI_COMPUTE` | pure regression + simulation; ships unchanged |
| **Sources** | `lib/sources.js` | `window.GMI_SOURCES` | asset registry + data-source adapters |

The shell calls **one** entry point — `GMI_COMPUTE.analyse(series, params)` →
`{reg, channel, run, currentSigma, trendNow, lastPrice, lastDate}`. A native port =
rebuild the **shell** with your components against those three globals; `compute.js`
and the `data.js` contract carry over untouched (so the tested maths never drifts).

### Directly addressing the three blockers from the call
1. **"References data outside our platform."** Fixed. The dashboard reads baked-in
   `injected` data — no runtime external call. `lib/sources.js` has a `platform`
   adapter stub: point it at RV's own QQQ/BTC end-of-day feed and set each asset's
   `source:"platform"`. Nothing else changes. (Delete the beta-only external adapters.)
2. **"Doesn't reuse our shared components."** The design lives entirely in the shell —
   the one layer meant to be swapped. Re-skin it with your component/chart library;
   compute + data + sources are untouched.
3. **"Keep a consistent UX."** Same — UX is the shell. Driven by your design system
   once we have the tokens (below).

### What we still need from you (to build the platform-native version)
1. **Shared component / chart library** — what do dashboards render with? (React design
   system? chart lib — Highcharts / Chart.js / in-house? a package or Storybook to see.)
2. **How in-platform data reaches a dashboard** — an API endpoint, a data client/SDK, or
   values passed as props? That's what the `platform` adapter wires to.
3. **Design tokens / design system** — colours, fonts, spacing (Figma / theme file /
   Storybook). The RV "skin."

With those three, the next thing you see is a shell that consumes your components +
platform data — something that drops into your stack, not a thing to translate.

### What's done vs. what's yours
- **Done (content side):** working tool, RV design applied, real data on a schedule,
  the four-layer split, this spec + QA check-cases, the live iframe.
- **Yours (P&E):** keep the iframe as the beta or rebuild the shell in your components;
  wire the `platform` data adapter; hosting, tiering, and "Live" promotion once the
  feed is QA-verified.
