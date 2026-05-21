# The Everything Code (TEC)

*Repo slug is still `global-m2`; product/branding renamed to The Everything Code. Live at https://islandboy1968.github.io/global-m2/*

A self-updating dashboard tracking global liquidity as **broad money across 47 economies, valued in US dollars** — the GMI method. It reproduces the GMI Total Liquidity level (~$135T). Two charts: the Index level and its year-on-year growth. Built on a **daily** grid (M2 prints monthly and is forward-filled; FX moves daily), so the line updates every day.

## What's here
- `index.html` — the dashboard (loads `data/data.js`, renders with Chart.js). Each chart has its own range buttons and scales independently; overlay charts have an adjustable lead/lag control.
- `update_data.py` — the daily pipeline (pulls data, computes everything, writes `data/`)
- `tv_pull.py` — TradingView history puller
- `econ.py` — the 47-economy table (ticker + FX + currency)
- `data/data.js` + `data/data.json` — generated data
- `.github/workflows/update.yml` — daily refresh at 06:30 UTC

## Deploy (one-time, ~5 minutes)
1. Create a **public** GitHub repo and upload every file in this folder, keeping the folder structure (`data/` and `.github/workflows/` included).
2. **Settings → Pages**: set "Deploy from a branch", branch `main`, folder `/ (root)`. Save. Your dashboard goes live at `https://<your-username>.github.io/<repo>/`.
3. **Settings → Actions → General → Workflow permissions**: choose **Read and write permissions**. Save.
4. **Actions** tab → "Update TGL data" → **Run workflow** once to confirm the daily refresh works.

That's it. The page updates itself every morning.

## Updating China's M2 by hand (optional, ~30 seconds/month)
TradingView's China M2 feed lags about a month. When the PBoC releases a new figure, edit the `CHINA_M2_OVERRIDE` dict near the top of `update_data.py`, e.g. add `"2026-05": 354.5e12` (value in yuan). Everything else updates automatically.

## Method (short)
Each economy's M2 / broad money is converted to USD at spot FX and summed. The money-vs-FX split holds FX at the year-ago level to separate domestic money growth from dollar translation. Central-bank net liquidity = Fed assets − TGA − reverse repo, plus PBoC/ECB/BoJ/BoE balance sheets in USD, shown for comparison only (it is flat and not part of the headline).

Sources: TradingView ECONOMICS (M2 & central bank balance sheets), TradingView FX, FRED (Fed net-liquidity components). All public, no API key.
