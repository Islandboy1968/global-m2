# The Everything Code (TEC) — Dev Notes

Working state of the project, kept in the repo so any fresh session can pick up instantly.
(Formerly "GMI Liquidity Dashboard". The repo slug is still `global-m2`; only the product
name and on-page branding changed.)

## What it is
A multi-tab dashboard (Chart.js) with TradingView-style per-axis zoom/pan and range buttons,
styled in the **GMI brand "light report-chart" theme** (see Styling below). The product is
**The Everything Code (TEC)** — liquidity is the first section; more TEC sections (tabs) will
be added over time.

Layout follows the Claude Design template (GMI house style): a hot-pink top rule, a
`GMI` / `GLOBAL MACRO INVESTOR` masthead, then a title block with a small pink kicker
**"The Everything Code"** (`.kicker`) over the big section headline **"Global Liquidity" /
"US Liquidity"** (`.h1title`, Oswald), with a right-aligned descriptor (`.descr`). The
title/descriptor are page-level and updated by `showTab()` on tab change. A footer reads
`GMI · The Everything Code` / month-year.

- **Global Liquidity tab** — Total Global Liquidity: broad money across 47 economies,
  each converted to USD at spot FX and summed (the GMI method). ~135T, ~8% YoY.
  Four charts: Index level, YoY, liquidity-leads-BTC, liquidity-leads-NDX.
- **US Liquidity tab** — US Total Liquidity (net liquidity). Six charts: Broad level,
  Broad YoY, Narrow level, Narrow YoY, Broad-vs-NDX, Narrow-vs-BTC.
  ("Broad" = the new measure, "Narrow" = the former "old" measure. Same formulas as before;
  only the labels changed.)
- **The Big Picture tab** — structural macro, all FRED. Five linear dual-axis charts:
  (1) LFPR vs US births/1,000 with the births +16yr forward lead; (2) LFPR vs Federal debt/GDP
  with the right axis **inverted**; (3) US Total Liquidity (Narrow, $BN) vs debt/GDP;
  (4) US Total Liquidity (Broad) vs Federal interest payments with the interest +36mo forward
  lead; (5) LFPR vs the US 5-year Treasury yield (`DGS5`, pink RHS) with the **LFPR** carrying a
  +5-month forward lead — the left/black series is the leading indicator here, so it uses
  `controlsFwdLeft`/`buildLagFwdLeft` (shift datasets[0], not datasets[1]).
  Reads `TGL_DATA.big` (FRED series) and reuses `TGL_DATA.us` for the liquidity lines
  (`vo`×1000 = Narrow on chart 3, `vn`×1000 = Broad on chart 4) — no liquidity series is duplicated.
- **The Business Cycle tab** — the ISM as the cycle pivot. Three blocks:
  (1) **The Everything Code Dominoes** — a fixed reference slide reproduced as inline SVG (no
  Chart.js, no controls): the five time bands T≤−2/0/+3/+6/+9 months with the labelled boxes
  (Lagging Economic Data→GDP/CPI; ISM→…→Altcoins; Bitcoin/Tech Stocks/Yield Curve; Liquidity;
  GMI Financial Conditions Index/Gold) on a −3M..12M axis. (2) **ISM vs Global Total Liquidity** —
  ISM (black, LHS) vs the GMI Total Liquidity Index YoY% (pink, RHS) with an adjustable forward
  lead defaulting to 6 months (182d). The liquidity line reuses `TGL_DATA.series[].y` (global YoY),
  so no series is duplicated. (3) **ISM vs ISM New Orders** — both on one shared axis (`overlaySame`),
  New Orders adjustable, defaulting to lead 1 month (30d). (4) **ISM vs GMI Financial Conditions
  Index** — ISM (black) plus two FCI lines on the same left axis: the headline FCI (blue, the 50%
  oil blend) and the ex-oil FCI (light blue); one lead box shifts both, default 9 months (274d).
  The gap between the two lines = the oil contribution / oil risk. (5) **The dominoes** — a triple
  overlay: ISM (black, L) + GMI Total Liquidity YoY (pink, R, fixed +6mo) + GMI FCI blend (blue, L,
  fixed +9mo), the lead chain in one view. Reads `TGL_DATA.cycle` (ISM PMI + New Orders + fci +
  fci_exoil, monthly, from TradingView — FRED no longer carries ISM).
  The FCI is a **reconstruction** (not the proprietary GMI series): inverse of a standardised
  composite of YoY change in a blended Treasury rates leg (2y/5y/10y, dollar-issuance weighted
  0.40/0.40/0.20, each tenor z-scored first), the dollar, and oil at half weight, scaled to ISM;
  it leads ISM ~9 months (corr ~0.37 full sample, ~0.65 since 2014). Copper was tested and dropped
  (coincident, peaks at zero lead). See `build_fci.py`.

Live at: https://islandboy1968.github.io/global-m2/

## UI behaviour (changed — read this)
- **Hover/tooltip uses `interaction.mode:"x"` + a per-dataset dedupe filter** (both in `opts()`).
  `"x"` (not `"index"`) so each line snaps to its own nearest point on the hovered date — required
  because the overlays mix frequencies (monthly ISM vs quarterly GDP/capex vs daily liquidity) and
  `"index"` dropped the sparse series between prints. `"x"` then returns several points per line when
  zoomed out, so `tooltip.filter:(it,i,a)=>a.findIndex(o=>o.datasetIndex===it.datasetIndex)===i`
  keeps exactly one row per line (kills the double/triple tooltip rows).
- **Every chart is fully independent.** There is no longer any cross-chart x-axis sync
  (`syncX` was removed). Zooming, panning, range selection and lead/lag on one chart never
  touch any other chart.
- **Range buttons are per-chart.** Each panel carries its own `1M / 3M / 6M / 1Y / 5Y / All`
  row in a `.ctrls > .ranges` bar (the empty `.ranges`/`.lagctl` divs are pre-placed in the
  HTML inside each `.panel`; `controls(chart)` finds them via `chart.canvas.closest('.panel')`
  and populates them). Each set acts only on its own chart, anchored to that chart's own data
  extent (`xExtent`). Picking a range also auto-fits Y (`fitY`). (Note: the static Claude
  Design mock shows a single top-right range row; we kept per-chart controls per the explicit
  functional requirement — to switch to one master row, move the `.ranges` bar out of the
  panels and have `setRange` loop all charts.)
- **Lead/lag is adjustable per overlay chart.** The lead/lag charts (global BTC & NDX, US NDX
  & BTC) have a `.lagctl` control = a single free numeric input box (the preset buttons were
  removed). Type any value: positive = liquidity leads (asset shifted back), negative = lags.
  `buildLag()` recomputes the asset dataset on the fly (`x = date − days`), rewrites the series
  label and the header caption, then `fitY`. The shipped data still carries the default
  `lag_days` (90); the control just re-shifts client-side, so no pipeline change.
- **Per-chart lock / persist.** Every chart has its own lock toggle (the small padlock top-right of
  each panel). Locking a chart saves *that chart's* view (x/y/y1 min-max + lead) to `localStorage`
  under `tec_charts` (a map keyed by canvas id; presence of an entry = locked). On reload each locked
  chart restores its saved view; unlocked charts fall back to their default view. While a chart is
  locked, its mouse zoom/pan/axis-drag and its lead input are disabled, but its timeline range buttons
  still work and re-save. **Tracking new data:** a lock taken while viewing up to the latest point
  slides forward on reload (keeping the same span + y-scale) to include new prints; a deliberately
  historical lock stays fixed (`snapshot` stores `span` + `atLatest`; `applySnap` re-anchors when
  `atLatest`). Implemented by `snapshot`/`applySnap`/`saveChart`/`toggleChartLock`/`lockUI`/
  `addLock`; `attach()` no-ops when `chart.$locked`; `addLock()` (called from `controls`/`controlsFwd`)
  injects the `.locktoggle` button and registers the chart in `ALL_CHARTS`; lead controls expose
  `chart.$relag`/`$leadInput`/`$lead` for restore. A final pass restores locked charts then sets `READY`.
- **Published default layout (shared baseline).** `data/layout.js` ships `window.TEC_DEFAULT_LOCKS`
  (loaded in `<head>` after `data.js`). At startup `LOCKS = {...TEC_DEFAULT_LOCKS, ...localStorage}`,
  so every visitor opens to the published arrangement and resets to it on reload (localStorage is
  per-device, never shared via the link); a visitor's own locks only override on their machine.
  The **Copy layout** button (top-right of the tab row) writes the current locked charts as a
  ready-to-commit `window.TEC_DEFAULT_LOCKS = {...};` string to the clipboard — paste it into
  `data/layout.js` and commit to publish a new default. The daily Action does not touch this file.
- **Big Picture leads:** charts 1 (births) and 4 (interest) carry forward leads; chart 3 (debt) also
  has an adjustable lead box (default 0 = coincident) for testing a debt-vs-liquidity lead/lag.
- **Frequency:** the Global tab is **daily** (M2 monthly, forward-filled; FX daily). The US tab
  is **weekly** (FRED WALCL is a Wednesday weekly series) — it can't be made truly daily without
  inventing intra-week data. The lead/lag unit is **days** on both, so 90d ≈ 13 weekly US points.
- **Zoom sensitivity is calmer.** Wheel zoom is now magnitude-aware and clamped:
  `f = exp(clamp(normalisedDeltaY) * ZOOM_SENS)` with `ZOOM_SENS=0.0011` (~7–11% per notch,
  smooth on trackpads). Value-axis drag (slide) is damped by `AXIS_DRAG_DAMP=0.55` so overlay
  alignment is fine-grained. Both constants are at the top of the app `<script>`.

## Styling (GMI template — Claude Design)
Built to the Claude Design template PNG + CSS spec. All tokens are CSS vars in `:root`.
- **Page is white;** the colour lives in the chart panels. Each chart sits in a `.panel` with
  the pink gradient `linear-gradient(180deg,#ECC2EA 0%,#F8DDEF 60%,#FBE7F2 100%)`. Above each
  panel a `.chead` row carries a pink section number (`01`…), the Oswald title, and a right
  `.ccap` caption. Inside each panel: a top-left HTML `.legend` (line swatch + label; liquidity
  black, asset pink), the `.chartbox`, the per-chart `.ctrls`, and an italic `.src` source line.
- **Accent = GMI hot pink `#f12a5a` (`PINK`).** Ink `#131316` (`BLACK`). Muted text
  `rgba(19,19,22,.6/.45)`. Borders `rgba(19,19,22,.12)`.
- **Series colours:** index/level + overlay-liquidity lines = black `#131316`; YoY lines and all
  overlay asset lines (BTC/NDX) = hot pink `#f12a5a`; 3m-avg companion = faint `rgba(19,19,22,.16)`
  (`SMOOTH`). All series lines are **1px** (companion 0.75px) — a fine hairline to match the
  GMI house chart. Chart grid `rgba(19,19,22,.07)`, x baseline `rgba(19,19,22,.6)`. **Axis tick
  colour matches its series** — level y ticks black, YoY y ticks pink, overlay right (log) ticks pink.
- **Index/level charts are shown in $BN** (data is $tn, multiplied ×1000 at plot time via `ptsBN`
  / `PBN`; tick formatter `fmtBN` adds thousands separators). YoY stays % (`fmtPCT`). The big
  on-page stat readouts were replaced by the `.ccap` captions (latest value / YoY in the header).
- **Type (all three brand fonts self-hosted in `fonts/`):** **Teko** (the GMI display face) for
  the `GMI` wordmark, section titles, `.h1title`, tabs — SemiBold (600) for titles, Medium (500)
  for tabs; **AT Aero** for legends, body, notes, source lines and chart tooltips; **DM Mono**
  (Google) for the masthead sub-wordmark, kicker, descriptor, captions, range/lag pills, footer,
  axis ticks. `Chart.defaults.font.family` = AT Aero.
- **Embedded via `@font-face`** at the top of `<style>`: Teko (`Teko-Regular/Medium/SemiBold/Bold`,
  weights 400/500/600/700, `.woff2`, converted from the supplied `.ttf` with fontTools); AT Aero
  (`AtAero-Regular`=400, `AtAero-Medium`=500, `.woff2`+`.woff`). No webfonts are pulled from
  Google except DM Mono. Nothing is substituted any more — Teko replaced the earlier Oswald stand-in.

## How data flows (unchanged, important)
Nothing is fetched in the browser. The browser only reads the static file `data/data.js`,
which assigns one object to `window.TGL_DATA`. That file is regenerated once a day by the
GitHub Action and committed back to the repo. "Live" means "refreshed daily server-side",
not "fetched at page load". This is deliberate — it removes all CORS / proxy / flakiness.

`.github/workflows/main.yml` runs daily at 06:30 UTC (and on manual dispatch):
checkout -> setup Python 3.11 -> `pip install -r requirements.txt` -> `python update_data.py`
-> commit `data/data.js` + `data/data.json` -> push. The push uses GitHub's built-in
`GITHUB_TOKEN` (needs Settings -> Actions -> General -> Workflow permissions -> Read and write).

## Files
- `index.html` — the dashboard. Tab nav + two chart groups. Shared helpers: `opts`/`opts2`
  (chart options), `overlay()` (lead/lag chart builder, takes initial lag), `fitY` (auto-fit
  each y-axis to the visible x-window), `attach` (per-axis wheel-zoom + drag-pan, fully local
  to one chart), `xExtent`, `buildRanges` (per-chart range buttons), `buildLag` (per-chart
  lead/lag control), `controls()` (injects the `.ctrls` bar into a card). Reads `TGL_DATA`
  (global) and `TGL_DATA.us` (US). Reuses `TGL_DATA.btc` / `TGL_DATA.ndx` for the overlays.
- `update_data.py` — daily pipeline. Builds the global series from TradingView, then calls
  `build_us()` and `build_big()` and writes everything (incl. `us`, `big`) to `data/data.js`
  and `data/data.json`. US and Big failures are each caught and never break the global build.
- `us_liquidity.py` — US series, computed server-side from FRED's KEYLESS csv endpoint
  (`fredgraph.csv`). No API key in the repo. Two transports (urllib then curl) for resilience.
- `big_picture.py` — The Big Picture FRED series via `build_big()`, reusing `us_liquidity._fetch`.
  Returns `{lfpr, births, debt, interest}`, each `[{d, v}]`. Series: `CIVPART` (LFPR %, monthly),
  `SPDYNCBRTINUSA` (birth rate /1,000, annual), `GFDEGDQ188S` (debt % GDP, quarterly),
  `A091RC1Q027SBEA` (Federal interest payments, $bn, quarterly).
- `build_cycle.py` — The Business Cycle series via `build_cycle()`, reusing `tv_pull.pull_series`.
  Returns `{ism, neworders, gdp, capex, capex_g}`. `CYCLE_SERIES` maps key→(symbol, resolution):
  `ism`=`ECONOMICS:USBCOI` 1M, `neworders`=`ECONOMICS:USMNO` 1M, `gdp`=`ECONOMICS:USGDPQQ` 3M.
  `build_capex()` = `FRED:PNFI`/`FRED:GDP`×100 (nonresidential fixed investment % of GDP, quarterly);
  `build_capex_growth()` = `FRED:PNFI` YoY % (nominal capex growth, quarterly). Both are wrapped in
  try/except so a TradingView hiccup yields `None` and never breaks the cycle block. FRED no longer
  carries ISM (copyright); ISM/GDP come from the ECONOMICS feed and PNFI/GDP from FRED passthrough,
  all over the same `pull_series` websocket (no API key). The dashboard pairs ISM with the global
  liquidity YoY already in `TGL_DATA.series[].y`, so no liquidity series is duplicated.
- `build_fci.py` — GMI Financial Conditions Index reconstruction via `build_fci_set()` (one TV pull,
  returns both `fci` (50% oil blend) and `fci_exoil`). Inputs `TVC:US02Y`+`TVC:US05Y`+`TVC:US10Y`
  (blended rates leg), `TVC:DXY`, `TVC:USOIL`,
  YoY change, z-scored, inverted tightening composite, smoothed, scaled to ISM mean/std. Called from
  `update_data.py` with the cycle ISM; stored as `cycle.fci` / `cycle.fci_exoil`.
- `tv_pull.py` — TradingView websocket history puller (no API key).
- `econ.py` — the 47-economy table (M2 ticker, FX symbol, currency).
- `requirements.txt` — `websocket-client` (only third-party dep; us_liquidity uses stdlib + curl).

## Data shape (`window.TGL_DATA`)
```
{
  updated, freq, lag_days,
  summary: { latest, total_tn, yoy, yoy_s, n_economies },
  series:  [ { d, v, y, ys } ],            // global: level $tn, YoY %, 3m-avg YoY %
  btc:     [ { d, p } ],                    // daily close
  ndx:     [ { d, p } ],
  us: {
    lag_days,
    summary: { latest, new_tn, old_tn, yoy_new, yoy_new_s, yoy_old, yoy_old_s },
    series:  [ { d, vn, vo, yn, yns, yo, yos } ]  // new(Broad)/old(Narrow) level $tn, YoY %, 3m-avg YoY %
  },
  big: {                                          // The Big Picture — FRED structural series
    lfpr:     [ { d, v } ],   // CIVPART, % monthly
    births:   [ { d, v } ],   // SPDYNCBRTINUSA, per 1,000 annual
    debt:     [ { d, v } ],   // GFDEGDQ188S, % of GDP quarterly
    interest: [ { d, v } ],   // A091RC1Q027SBEA, $bn quarterly
    y5:       [ { d, v } ]    // DGS5, US 5-year Treasury yield, % daily
  },
  cycle: {                                        // The Business Cycle — ISM survey series (TradingView)
    ism:       [ { d, v } ],  // ECONOMICS:USBCOI, ISM Manufacturing PMI, monthly
    neworders: [ { d, v } ], // ECONOMICS:USMNO, ISM Manufacturing New Orders, monthly
    fci:       [ { d, v } ], // GMI FCI reconstruction (50% oil blend), ISM units, monthly
    fci_exoil: [ { d, v } ], // FCI ex-oil (rates+dollar only), ISM units, monthly
    gdp:       [ { d, v } ], // ECONOMICS:USGDPQQ, US real GDP QoQ % annualised (SAAR), quarterly
    capex:     [ { d, v } ], // FRED:PNFI / FRED:GDP * 100, nonresidential fixed inv. % of GDP, qtly
    capex_g:   [ { d, v } ]  // FRED:PNFI YoY %, nominal capex growth, quarterly (ISM leads ~3q)
  }
}
// All cycle.* extras are FRED/ECONOMICS via TradingView passthrough — reachable in BOTH sandbox and
// Action runner. gdp/capex/capex_g were injected into the committed data.js this session and are
// regenerated by build_cycle.py on each Action run.
```
Note: the data keys still use `new`/`old` / `vn`/`vo`; only the on-screen labels say
Broad/Narrow. (new = Broad, old = Narrow.)

## Formulas
- Global level = sum over economies of (national M2 in local ccy x USD-per-local FX), in $tn.
  YoY = 365-day offset on a daily grid. 3m avg = 91-day trailing.
- US, weekly (FRED WALCL Wednesday grid), in $tn:
  - Broad (new) = WALCL - WTREGEN - RRPONTSYD*1000 + TOTBKCR*1000   (total bank credit; ~$24T)
  - Narrow (old) = WALCL - WTREGEN - RRPONTSYD*1000 + SBCACBW027NBOG*1000
  - (WALCL/TGA are $M; RRP/loans/securities are $B, so x1000 to $M, then /1e6 to $tn.)
  - YoY = 52-week offset. 3m avg = 13-week trailing.
- Overlay charts: liquidity plotted at real dates; the asset is shifted back by the chart's
  current lead/lag (default `lag_days`=90, adjustable in the UI). Right axis is logarithmic.

## Run / iterate
- Clone (public, read-only, no token): `git clone https://github.com/Islandboy1968/global-m2`
- Regenerate data locally: `pip install -r requirements.txt && python update_data.py`
  (the TradingView pull of ~95 symbols takes a few minutes; FRED part is fast).
- US block only, quick check: `python us_liquidity.py`.
- Frontend sanity check (no browser): load `index.html` in jsdom with a fake `Chart` and the
  real `data/data.js`; assert 10 `.ranges` rows, 60 range buttons, 4 `.lagctl` controls, and
  that a lead/lag change rewrites the `.leadlbl` caption. (Used during the last edit.)
- Pushing requires a fine-grained PAT with Contents + Workflows + Actions write.
  NEVER commit a token to this repo (it is public). Paste it into the chat when a push is needed.

## FRED resilience (us / big blocks)
The `us` and `big` sections come from FRED's keyless CSV endpoint via
`us_liquidity._fetch`, which occasionally read-times-out on the Action runner.
Symptom: a section shows the "generated server-side… once the Action has run"
banner with an empty chart even though the pipeline "succeeded" (the failure is
swallowed by a try/except and the block is written as `null`). Hardening in place:
- `_fetch` is dual-source: it tries the FRED CSV endpoint and FRED's TradingView
  passthrough (`FRED:<id>`), falling back to the other if one fails, so a
  transient outage on either source no longer blanks a block. The two large
  daily series that *reliably* time out on the CSV endpoint from the runner —
  `RRPONTSYD` (US Liquidity) and `DGS5` (big.y5) — are listed in `TV_FIRST` and
  hit TradingView first (the CSV stays as their backup). This is what fixed the
  US Liquidity tab going perpetually stale: RRPONTSYD timing out dropped *every*
  weekly row (`build_us` needs all five inputs per row), emptying the block, so
  it was carried forward unchanged on every run.
- `build_big` is per-series tolerant — one stalled series (it was `DGS5`) no
  longer blanks the whole tab; the others still render.
- `update_data.py` carries forward the last committed `us`/`big` (whole-block,
  and per-series for `big`) when a rebuild comes back empty, so a transient miss
  never regresses a populated section. To diagnose, read the Action run log for
  `US build FAILED` / `BIG build FAILED` / `BIG <key> failed` lines.

## Trust / source-truth freshness (verify_data.py)
The dashboard must never silently show stale data, and we deliberately keep NO
hardcoded release calendar (those rot). Instead `verify_data.py` is a SOURCE-TRUTH
checker: for every series it goes to the actual source (same symbols/resolutions,
imported straight from the builder modules so it can't drift), reads the latest
published observation, and compares it to what we shipped.
- Statuses: IN_SYNC, BEHIND (source has a newer COMPLETE month — real problem),
  MISSING (empty), UNVERIFIED (couldn't reach source — no opinion), DERIVED
  (computed series with no 1:1 source — reported, never gated).
- "Behind" ignores the in-progress current month, so a partial current-month bar
  (a daily series bucketed monthly) never false-flags a correctly-current series.
- It stamps a per-series verdict into `TGL_DATA.freshness[block].series[leaf]`
  ({as_of, source_latest, status}) plus a block-level status. The dashboard badge
  is GREEN only when the tab matches its source, and goes amber NAMING the lagging
  series otherwise — a fresh daily series can no longer mask a stale monthly one.
- CI runs `python verify_data.py --gate` before the commit: it stamps the
  freshness and FAILS the job on any BEHIND/MISSING (DERIVED/UNVERIFIED never
  fail). The commit step is `if: always()` so the honest badge is published even
  when the gate is red.
- `build_us()` is now per-input tolerant: only the four CORE inputs (WALCL,
  WTREGEN, RRPONTSYD, TOTBKCR) are required for the headline Broad measure;
  SBCACBW027NBOG (Narrow-only, absent on TradingView + flaky on FRED CSV) may be
  missing — the Broad series still ships and update_data carries the Narrow leg
  forward per-series. One missing input can no longer blank the whole US tab.
- **Weekly grid / TGA source** (`us_liquidity.build_us`): the US series is built on
  WALCL's weekly (Wednesday) grid with TGA = the Fed's weekly `WTREGEN`, so the levels
  match the established GMI "US Total Liquidity" methodology (~$25.4tn Broad / ~$11.6tn
  Narrow). A daily-grid variant using the U.S. Treasury's daily TGA (DTS
  `operating_cash_balance.close_today_bal`) was tried and REVERTED: the Treasury's
  daily closing balance reads ~$0.5-0.6tn off the Fed's weekly figure (and the gap
  drifts), which shifted the whole Broad/Narrow curve up by that amount. Weekly is
  also the genuine publication frequency of these H.4.1/H.8 inputs. YoY is 52-week
  with a 13-week (~3mo) trailing average.
- **Narrow spread seed** (`us_liquidity._load_spread_seed` + `data/us_narrow_seed.json`):
  the Narrow leg's securities input (`SBCACBW027NBOG`) has no TradingView fallback and
  its FRED CSV times out on most runs, so it cannot be relied on. When it's unavailable
  the Narrow is reconstructed as `Broad − spread`, where the Broad−Narrow spread
  (`= (bank credit − bank-held securities)/1e3`, $tn) comes from a committed seed of the
  last known-good weekly history (last value carried forward for newer weeks — the
  spread moves only glacially). This reproduces the historical Narrow to a rounding
  error and keeps it advancing every week. When `SBCACBW` *does* load live, the live
  value is used and the seed is auto-refreshed (the workflow commits the seed file).
  This replaced the old vo carry-forward, which silently propagated whatever Narrow was
  last shipped (e.g. the wrong daily-grid-era values across a base change).
- **Unit normalization** (`us_liquidity._to_canonical`): FRED's CSV returns the US
  magnitude series in FRED's canonical unit ($M/$B) but FRED's TradingView
  passthrough returns ACTUAL DOLLARS. `_fetch` converts based on WHICH SOURCE
  answered (TradingView → divide by the canonical factor; CSV → as-is), never by
  magnitude — a magnitude test misclassifies small values (near-zero reverse-repo
  from TradingView, ~$0.08B = 8e7 dollars, fell below the old 1e8 threshold and was
  read as $80B, blowing rows up ~1000x). `build_us` also (a) has a $5–80tn guard on
  the latest Broad that carries forward rather than ship a corrupt value, and (b)
  drops any individual day whose Broad is outside $0–100tn (nulls an implausible
  Narrow) so a stray garbage input can never render.
- **Auto-heal** (`update_data._reconcile_behind`): TradingView's monthly feeds
  occasionally serve a month-stale snapshot for one series (caught `cycle.ism`
  once). After the build, any gated TradingView block whose source has a newer
  complete month is re-pulled (≤2 rounds), using `verify_against_source` so "behind"
  matches the gate exactly. Transient misses self-heal (green stays reliable); a
  genuinely stale source stays BEHIND and the gate fails loudly. us/big are excluded
  (their carry-forward state would be clobbered by a blind rebuild). Disable with
  `TGL_NO_HEAL=1`.

## Caches (gitignored, not in repo)
`series_cache.json` (M2, monthly) and `fx_daily_cache.json` (FX + assets, daily) speed up
local reruns. The Action runs without them (full pull each time), which is fine.

## Notes / parked ideas
- China M2 is **feed-first** (was: hand-updated monthly). `reconcile_china_override`
  in update_data.py compares `CHINA_M2_OVERRIDE` against the live `ECONOMICS:CNM2`
  feed each run: the feed is source-of-truth for months it already serves, the
  override only bridges genuinely newer/corrected months. The run logs which
  override months are now redundant (feed caught up → safe to delete) and
  `data["china_override"]` carries `feed_latest` / `override_latest` / `source` /
  `redundant_override_months`. No standing monthly task; add an override line only
  when the feed actually lags.
  - Deferred: add the CN M2 index leg to `verify_data.build_registry()` for a
    formal `BEHIND/MISSING` source gate. Awkward today because the CN leg isn't a
    standalone shipped series (only the summed global `series` is); the feed-aware
    `china_override.stale` banner covers the practical case. Revisit if the leg is
    ever emitted as its own diagnostic series.
- Machine-readable AI surfaces: `summarize.py` emits `data/summary.json` (AI-first
  digest) and `data/index.json` is the agent entry point; `indicators_meta.py` is
  the self-describing meta registry. Shape in `DATA_CONTRACT.md` (shared with EA).
  `schema_version` + `dashboard:"tec"` stamped on data.json and summary.json.
- Done (was pending): GMI design-system restyle — light report-chart theme applied (see Styling).
  Optional follow-up: embed the real licensed Tungsten/AT Aero webfonts for a pixel-exact match.
- Parked: more overlay assets (gold, S&P); a money-vs-FX decomposition panel; more TEC tabs.
- Done (was parked): adjustable lead/lag on the overlay charts.
- Done: chart export. Self-contained IIFE at the end of the inline `<script>` in
  `index.html` (uses html2canvas + JSZip from cdnjs). It wraps each `chead`+`panel`
  into an `.excard`, adds hover Download/Copy buttons (whole-card PNG at 2x), and a
  "Download charts" toolbar button that zips every visible chart across all tabs.
  Pure DOM-driven, so any new charts added later are picked up
  automatically; hidden panels (offsetParent===null) are skipped. The
  controls strip and lock/export buttons are hidden in the capture via `onclone`.
  Couldn't live-render in the web container (no headless browser + runtime CDN);
  validated by node --check. Possible follow-up: crisper chart lines via per-chart
  high-DPI re-render, and a data/manifest sidecar for AI deck tools.
