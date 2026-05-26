# The Everything Code (TEC)

*Repo slug is still `global-m2`; product/branding renamed to The Everything Code. Live at https://islandboy1968.github.io/global-m2/*

A self-updating dashboard built around the GMI Total Global Liquidity index (broad money across 47 economies, valued in US dollars at spot FX and summed). It reproduces the GMI Total Liquidity level (currently ~$136T) and the year-on-year growth that drives the Everything Code framework. The line is built on a daily calendar grid (M2 prints monthly and is forward-filled; FX moves daily), so it updates every day. Four additional tabs sit alongside it for the full Everything Code view.

## What the dashboard shows

The page has five logical sections, each independent so one failing does not break the others.

1. **Global Total Liquidity**: the headline index and its year-on-year growth (with a 91-day trailing average overlay).
2. **US Net Liquidity** (weekly, FRED): the GMI "new/broad" measure `WALCL - TGA - RRP + bank credit` and the "old/narrow" measure `WALCL - TGA - RRP + securities held by banks`. Both reported with YoY and a 3-month YoY average.
3. **Big Picture**: five structural macro series from FRED (labour force participation, births, debt, interest, 5-year yield).
4. **Business Cycle**: ISM, new orders, GDP, capex, capex growth, plus the GMI Financial Conditions Index reconstruction (and FCI ex-oil), which leads ISM by about nine months.
5. **Liquidity-leads overlays**: BTC and NDX layered against the global liquidity line, with an adjustable lead/lag control.

## What's in the repo

- `index.html` — the dashboard front-end. Loads `data/data.js` and renders with Chart.js. Each chart has its own range buttons and scales independently.
- `update_data.py` — the master daily pipeline. Pulls everything, computes everything, writes `data/data.json` and `data/data.js`.
- `tv_pull.py` — TradingView websocket client used for M2, FX, ISM, and the risk-asset overlays.
- `econ.py` — the 47-economy table (M2 ticker, FX ticker, currency code).
- `us_liquidity.py` — US Net Liquidity build from FRED (H.4.1 + H.8).
- `big_picture.py` — Big Picture structural series from FRED.
- `build_cycle.py` — Business Cycle and ISM series from TradingView.
- `build_fci.py` — GMI Financial Conditions Index reconstruction from the ISM series.
- `data/data.js` + `data/data.json` — generated outputs, committed by the workflow.
- `.github/workflows/main.yml` — daily refresh at 06:30 UTC, plus manual `workflow_dispatch` trigger.
- `requirements.txt` — Python dependencies.

The TradingView pull caches (`series_cache.json`, `fx_daily_cache.json`) are gitignored on purpose. The workflow persists them across runs via the GitHub Actions cache, so each daily refresh only fetches genuinely new bars rather than re-pulling all symbols.

## How it stays live

The daily workflow runs hands-off. Resilience guards in `update_data.py` mean that if TradingView rate-limits the websocket and a couple of exotic symbols fail to pull, those economies are skipped for that day and the global index is built from the remaining ones rather than crashing the whole run. Sub-builds for US Net Liquidity, Big Picture, Business Cycle, and FCI are each wrapped in fail-safes so a problem in any one section nulls that block but leaves the rest of the dashboard intact. The TradingView pulls run with three concurrent connections and exponential backoff with jitter on retry, which keeps the daily refresh comfortably below the rate-limit threshold.

If a run does fail, the diagnostic path is the Actions tab at https://github.com/Islandboy1968/global-m2/actions. The `Run pipeline` step prints which symbols were skipped and which sub-builds, if any, returned a `FAILED` line. The dashboard itself shows the timestamp of the last successful refresh in the `updated` field, so a stale page is easy to spot.

## Updating China's M2 by hand (~30 seconds/month)

TradingView's China M2 feed lags the PBoC by about a month. When the PBoC releases a new monthly figure, add one line to the `CHINA_M2_OVERRIDE` dict near the top of `update_data.py`. The format is `"YYYY-MM": value_in_yuan`, e.g. `"2026-05": 354.5e12` for 354.5 trillion yuan. Everything else updates automatically. This is the only recurring manual task.

## Method (short)

Each economy's M2 (broad money) is converted to USD at spot FX and summed onto a daily calendar grid. M2 is monthly and forward-filled between prints. FX is daily and forward-filled across non-trading days. The global index level is the cross-sectional sum on each day; the headline YoY is a calendar 365-day offset; the 91-day trailing average smooths the wiggle. Each economy contributes from when its data series begins (leading None values are filled with the first available value so a late-starting series adds a constant baseline rather than a step jump).

US Net Liquidity uses WALCL as the master weekly calendar; TGA, RRP, bank credit, and securities held by banks are forward-filled onto that grid. The two definitions (new/broad and old/narrow) are computed in parallel.

The GMI FCI reconstruction is built from the ISM series (and a no-oil variant) and is the leading indicator for the cycle by approximately nine months.

## Sources

TradingView ECONOMICS (M2 and central bank balance sheets), TradingView FX, TradingView indices for BTC/NDX, FRED CSV for Fed and macro series. All public endpoints. No API keys anywhere.

## Deploy (for forking, ~5 minutes)

1. Create a public GitHub repo and upload every file in this folder, keeping the folder structure (`data/` and `.github/workflows/` included).
2. **Settings → Pages**: set "Deploy from a branch", branch `main`, folder `/ (root)`. Save. The dashboard goes live at `https://<your-username>.github.io/<repo>/`.
3. **Settings → Actions → General → Workflow permissions**: choose "Read and write permissions". Save.
4. **Actions** tab → "Update Global M2 data" → **Run workflow** once to confirm the daily refresh works.

The page updates itself every morning thereafter.
