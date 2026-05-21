# GMI Liquidity Dashboard — Dev Notes

Working state of the project, kept in the repo so any fresh session can pick up instantly.

## What it is
A two-tab liquidity dashboard (Chart.js, light theme, teal accent `#0e7490`) with
TradingView-style per-axis zoom/pan and range buttons.

- **Global Liquidity tab** — Total Global Liquidity: broad money across 47 economies,
  each converted to USD at spot FX and summed (the GMI method). ~135T, ~8% YoY.
  Four charts: Index level, YoY, liquidity-leads-BTC, liquidity-leads-NDX (assets lagged 90d).
- **US Liquidity tab** — US Total Liquidity (net liquidity). Six charts: new-measure level,
  new-measure YoY, old-measure level, old-measure YoY, new-vs-NDX (90d lag), old-vs-BTC (90d lag).

Live at: https://islandboy1968.github.io/global-m2/

## How data flows (important)
Nothing is fetched in the browser. The browser only reads the static file `data/data.js`,
which assigns one object to `window.TGL_DATA`. That file is regenerated once a day by the
GitHub Action and committed back to the repo. "Live" means "refreshed daily server-side",
not "fetched at page load". This is deliberate — it removes all CORS / proxy / flakiness.

`.github/workflows/main.yml` runs daily at 06:30 UTC (and on manual dispatch):
checkout -> setup Python 3.11 -> `pip install -r requirements.txt` -> `python update_data.py`
-> commit `data/data.js` + `data/data.json` -> push. The push uses GitHub's built-in
`GITHUB_TOKEN` (needs Settings -> Actions -> General -> Workflow permissions -> Read and write).

## Files
- `index.html` — the dashboard. Tab nav + two chart groups. All chart options, the
  `overlay()` helper, the per-axis zoom/pan (`attach`), `fitY`, and the range buttons are
  shared by both tabs. Reads `TGL_DATA` (global) and `TGL_DATA.us` (US). Reuses
  `TGL_DATA.btc` / `TGL_DATA.ndx` for the US overlay charts.
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
    series:  [ { d, vn, vo, yn, yns, yo, yos } ]  // new/old level $tn, YoY %, 3m-avg YoY %
  }
}
```

## Formulas
- Global level = sum over economies of (national M2 in local ccy x USD-per-local FX), in $tn.
  YoY = 365-day offset on a daily grid. 3m avg = 91-day trailing.
- US, weekly (FRED WALCL Wednesday grid), in $tn:
  - NEW (broad) = WALCL - WTREGEN - RRPONTSYD*1000 + TOTLL*1000
  - OLD (narrow) = WALCL - WTREGEN - RRPONTSYD*1000 + SBCACBW027NBOG*1000
  - (WALCL/TGA are $M; RRP/loans/securities are $B, so x1000 to $M, then /1e6 to $tn.)
  - YoY = 52-week offset. 3m avg = 13-week trailing.
- Overlay charts: liquidity plotted at real dates; the asset is shifted back by `lag_days`
  (90), so liquidity visually leads. Right axis is logarithmic.

## Run / iterate
- Clone (public, read-only, no token): `git clone https://github.com/Islandboy1968/global-m2`
- Regenerate data locally: `pip install -r requirements.txt && python update_data.py`
  (the TradingView pull of ~95 symbols takes a few minutes; FRED part is fast).
- US block only, quick check: `python us_liquidity.py`.
- Pushing requires a fine-grained PAT with Contents + Workflows + Actions write.
  NEVER commit a token to this repo (it is public). Paste it into the chat when a push is needed.

## Caches (gitignored, not in repo)
`series_cache.json` (M2, monthly) and `fx_daily_cache.json` (FX + assets, daily) speed up
local reruns. The Action runs without them (full pull each time), which is fine.

## Notes / parked ideas
- China M2 lags ~1 month on TradingView; `CHINA_M2_OVERRIDE` in update_data.py carries the
  latest official PBoC print. Update one line each month.
- Parked: adjustable lag slider on the lead/lag charts; more overlay assets (gold, S&P);
  a money-vs-FX decomposition panel.
