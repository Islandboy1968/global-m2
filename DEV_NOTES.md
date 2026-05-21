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

Live at: https://islandboy1968.github.io/global-m2/

## UI behaviour (changed — read this)
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
  `build_us()` and writes everything (incl. `us`) to `data/data.js` and `data/data.json`.
  A US failure is caught and never breaks the global build.
- `us_liquidity.py` — US series, computed server-side from FRED's KEYLESS csv endpoint
  (`fredgraph.csv`). No API key in the repo. Two transports (urllib then curl) for resilience.
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
  }
}
```
Note: the data keys still use `new`/`old` / `vn`/`vo`; only the on-screen labels say
Broad/Narrow. (new = Broad, old = Narrow.)

## Formulas
- Global level = sum over economies of (national M2 in local ccy x USD-per-local FX), in $tn.
  YoY = 365-day offset on a daily grid. 3m avg = 91-day trailing.
- US, weekly (FRED WALCL Wednesday grid), in $tn:
  - Broad (new) = WALCL - WTREGEN - RRPONTSYD*1000 + TOTLL*1000
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

## Caches (gitignored, not in repo)
`series_cache.json` (M2, monthly) and `fx_daily_cache.json` (FX + assets, daily) speed up
local reruns. The Action runs without them (full pull each time), which is fine.

## Notes / parked ideas
- China M2 lags ~1 month on TradingView; `CHINA_M2_OVERRIDE` in update_data.py carries the
  latest official PBoC print. Update one line each month.
- Done (was pending): GMI design-system restyle — light report-chart theme applied (see Styling).
  Optional follow-up: embed the real licensed Tungsten/AT Aero webfonts for a pixel-exact match.
- Parked: more overlay assets (gold, S&P); a money-vs-FX decomposition panel; more TEC tabs.
- Done (was parked): adjustable lead/lag on the overlay charts.
