# Dashboard Spec & Integration — GMI Risk Monitor

> Filled into Real Vision's `dashboard-spec-template.md`, plus an integration
> section (§10). Companion to the Compounding Machine hand-off; same four-layer
> contract, same pipeline model.
>
> **Live prototype:** https://islandboy1968.github.io/global-m2/dashboard-risk-monitor/index.html
> **Code + this doc:** `Islandboy1968/global-m2` → `dashboard-risk-monitor/` + `build_risk_monitor.py`

---

## 1. Title & Basics
| | |
| --- | --- |
| Dashboard name | GMI Risk Monitor |
| Author | Raoul |
| Version / date | 1.0 — 5 Jun 2026 |
| Refresh cadence | Weekly (after Fri close); pipeline runs Sat + on dispatch |
| Reuses an existing look? | Yes — its existing GMI gold shell (an RV restyle can follow, like the CM) |

## 2. Description
A single-page weekly dashboard showing the current **macro regime** (Global M2 ×
ISM) and the up/down trend of every asset in the GMI portfolio (RV Pro) plus a set
of macro benchmarks (RV Alpha), with per-asset secular trend and realised volatility.

## 3. What It Does & The Value It Brings
Answers two questions at a glance: "what part of the cycle are we in?" and "is each
asset I care about trending up or down right now?" The regime (liquidity × business
cycle) sets the backdrop; the trend tables let a subscriber size exposure with
conviction rather than reacting week to week.

## 4. How To Use It (reader-facing)
Read top-down: the **regime banner** is the backdrop (green/green = Full Expansion,
red/red = Contraction). Then scan the tables: green = rising weekly trend, red =
falling; a pulsing **New Buy/Sell** badge means the trend just flipped this week or
last. Weekly check-in, not an intraday tool. (Full guide is the "How To Use" tab.)

## 5. Design & Attached Mockups
Existing GMI dark/gold shell (`index.html`), tabs: RV Pro · RV Alpha · How To Use.
Regime banner + M2 and ISM SVG mini-charts + two trend tables + paywall preview for
non-Pro. An RV-component restyle can follow later (Claude Design), exactly like the CM.

## 6. Data Sources Needed
| Data input | For | Fresh | If unavailable |
| --- | --- | --- | --- |
| Global M2 composite (47-economy, USD) | regime + M2 chart + RoC | monthly (daily grid) | reuse last (already in `data.js`) |
| ISM Manufacturing PMI | regime + ISM chart | monthly | reuse last |
| Weekly/daily closes per asset | trend, secular, vol | weekly | **fail loud** — skip nothing silently |
| Position list (author-editable) | which Pro/Alpha rows appear | on edit | n/a |

**Reliability (the "data isn't our problem" story):** Global M2 + ISM are reused
**from the existing Everything Code pipeline that already runs the live site daily** —
the same battle-tested, fail-safe build. Per-asset prices use the same TradingView
puller with retry/back-off/cache. The build **fails loud** in CI on any feed that
doesn't resolve (it still commits what did, so the gap is visible) — a broken feed
is caught in CI, never shown blank/stale on the board.

## 7. Tiers & Access
RV Pro table gated by `isProSubscriber` (first 2 rows preview, rest blurred + paywall).
Alpha table, regime, charts, guide = all tiers. **P&E:** wire `isProSubscriber` to real auth.

## 8. Formulas & How They're Calculated
All verified by an independent audit; both calc modules have passing self-tests
(`signals.py` 21/21, `metrics.py` 9/9).

### Macro regime
M2 monthly trend × ISM monthly trend → Full Expansion (g/g) / Early Cycle (g/r) /
Late Cycle (r/g) / Contraction (r/r). Each monthly trend = ATR-SuperTrend that flips
instantly (M2 ATR 6, ISM ATR 12, ×3.0), computed on **full history** so "since" is a
true cross. `lib/signals.py` → `monthly_signal`.

### Weekly trend signal (per asset)
Volatility-adaptive ATR-SuperTrend trailing band; flip needs 2 consecutive weekly
closes through the band (3 in an "Extreme" vol regime, = 50-wk realised vol > 45%).
`lib/signals.py` → `weekly_signal`. **⚠ Needs calibration — see §10.**

### Secular trend
60-month SMA for traditional assets; log-regression ±2σ channel for crypto /
crypto-adjacent / carbon. `lib/metrics.py` → `secular_trend` (faithful port of the
Compounding Machine regression).

### Volatility
30-day realised vol (annualised) drives the risk colour (Normal <20 / Risky 20–40 /
High >40); a 1-year `annVol` is also shown. `lib/metrics.py`.

**How we'll know it's right (verified):** macro outputs reproduce exactly from
`data.js` (M2 green since Mar '25, ISM 54.0 green since Jan '25, YoY 6.5% / 6m 6.6%);
self-tests pass; fail-loud caught 2 bad symbols (SOL, Copper) on the first run.

## 9. Component Data Details
Injection contract: the pipeline rewrites **only** the block between
`// __PIPELINE_DATA_START__` / `// __PIPELINE_DATA_END__` in `index.html`. Variables:
`isProSubscriber, lastUpdatedStr, m2Roc{yoy,mom6}, m2ChartData[{d,c,s,g}],
ismChartData[{d,c,s,g}], proPositions[], alphaAssets[], m2Trend, ismTrend, m2Since,
ismSince, ismValue`. Row schema: `{asset, ticker, trend("green"|"red"), trendChange,
price, category, since, secular("rising"|"falling"|null), vol30d, regime("Normal"|"Extreme"), annVol}`.

## 10. Integration & Hand-off (for P&E)

**Pipeline:** `build_risk_monitor.py` (root) reuses M2/ISM from `data/data.js`, pulls
each position via `tv_pull`, runs `lib/signals.py` + `lib/metrics.py`, injects into
`index.html`. Workflow `.github/workflows/risk-monitor.yml` runs it weekly + on dispatch.

**Add/remove positions (author-owned):** edit `positions.py` (Pro + Alpha lists) —
one row per asset (ticker, TradingView symbol, category, secular method, yield flag).
The pipeline recomputes on the next run. No RV involvement; RV can later put an admin
UI on the same list.

**What's yours (P&E):** wire `isProSubscriber` to real auth + the upgrade link;
optionally re-skin into RV components/design; hosting/cadence. The data layer is done.

**⚠ Open item — weekly-signal calibration (the one thing to confirm before "live"):**
The weekly signal is a *tested interpretation* of the TradingView "GMI Weekly Trend
Signal", built from **close-only** data. Its exact knobs need a spot-check against the
real indicator. Tune order (each is one constant in `lib/signals.py`):
1. **True range** — close-only vs OHLC (`true_range_ohlc` hook exists) — biggest effect.
2. **Smoothing** — SMA vs Wilder (`atr_smoothing="wilder"` hook exists).
3. **Multiplier** — `SENS_NORMAL=3.5 / SENS_EXTREME=4.0`.
4. **Confirmation** — `CONFIRM_NORMAL=2 / CONFIRM_EXTREME=3` (a plain SuperTrend = 1).
5. **Regime** — `EXTREME_VOL_THRESHOLD=45 / REGIME_LOOKBACK=50`.

Minimum 4 spot-checks: (a) band levels on a clean trender (BTC), (b) the exact flip
week on a recently-flipped name (ETH/Gold), (c) regime/band width on a high-vol name
(SUI/DEEP/COIN), (d) band gap on any name. Re-run the self-tests after each change.

**Documented assumptions (audit, non-blocking):** the displayed **regime**
(Normal/Extreme) is the signal's *weekly* 50-wk vol regime, while `annVol` is a
*daily* 1-yr figure — they use different sampling, so a name can read e.g. annVol 47%
but regime Normal; this is by design, worth a one-line footnote. `√252` annualisation
is used for all assets (crypto arguably √365). Per-asset "since" near the start of an
asset's history can reflect the warm-up edge rather than a true flip.
