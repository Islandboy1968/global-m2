# Global M2 Dashboard

A live dashboard tracking Global M2 — the sum of broad money (M2/M3) across the G5 economies, USD-normalised, daily cadence, 4-year rolling window.

## What you get

- `index.html` — the dashboard. Three hero stats, two charts (level and YoY %), and a per-country breakdown table.
- `update_data.py` — the data pipeline. Pulls five M2 series and four FX series, builds a daily grid, writes `data/data.js`.
- `.github/workflows/update.yml` — runs daily at 06:30 UTC, commits a refreshed `data.js`.

## Data sources (no API keys anywhere)

| Country | Source | Notes |
|---|---|---|
| US M2 | FRED `M2SL` | Native USD billions |
| Eurozone M3 | ECB Data Portal SDMX | EUR mn |
| China M2 | chinadata.live (PBoC mirror) | CNY 100mn |
| Japan M2 | FRED `MABMM301JPM189N` | **Stale to Nov 2023** — BoJ direct is geo-blocked from cloud sandboxes; last value carried forward, FX still moves daily |
| UK M2 | BoE IADB `LPMVWYH` | GBP mn |
| FX | ECB daily reference rates | Cross-rates through EUR |

## How the daily series is built

1. Each native M2 series is fetched at its native monthly cadence.
2. A daily grid is created over the rolling 4-year window.
3. Native series are forward-filled onto the grid.
4. Each value is converted to USD billions using that day's ECB FX (cross-rates through EUR).
5. The G5 values are summed → Global M2.
6. YoY % is computed as today vs the same calendar day one year prior.

## Deployment

1. Create a new empty public GitHub repository.
2. Push these files to it.
3. **Settings → Pages** → Deploy from `main`, root folder.
4. **Settings → Actions → General → Workflow permissions** → set to "Read and write".
5. Open the **Actions** tab → "Update Global M2 data" → "Run workflow" once.

After that, the workflow runs every morning at 06:30 UTC and pushes a refreshed `data.js`. The Pages site picks it up automatically.

## Latest reading

| | USD value |
|---|---|
| Global M2 (G5) | ~$109T |
| YoY | +8% |
| 4-year change | ~+20% |

## Adding more countries

The `load_components()` dict is the only place you'd edit. Add a fetcher and append to the dict. The FX layer already supports any ECB-quoted currency.
