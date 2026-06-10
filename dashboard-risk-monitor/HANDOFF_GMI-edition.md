# GMI Risk Monitor — GMI edition (`gmi.html`)

The GMI-branded version of the Risk Monitor: same verified data pipeline as
the RV pages, restyled in the GMI design system (white ground, magenta
hairline, Teko display type), with two tabs:

| Tab | What it shows |
| --- | --- |
| **GMI Positions** | The weekly trend / secular / vol read for **every open position in the GMI book** — auto-derived from the GMI Positions dashboard, deduplicated across Tactical / Core / Long-term (the *Book* column shows which sleeves hold each instrument: T · C · LT). |
| **Assets** | The same macro benchmark list as the RV pages (`ALPHA_ASSETS` in `positions.py`). |

**Live page:** https://islandboy1968.github.io/global-m2/dashboard-risk-monitor/gmi.html

It does NOT touch the RV-facing pages: `index.html` / `alpha.html`, their
weekly workflow, and the `make_alpha_html()` derivation are unchanged.

## How positions auto-update

The position list is **not hand-edited** (unlike `positions.py`). The
pipeline (`build_gmi_risk_monitor.py`, daily via
`.github/workflows/gmi-risk-monitor.yml`) reads the GMI Positions
dashboard's `positions.json` from Google Drive
(folder `1wKaSzAgTF75CkDDm8cjl2QQmEHhL95xv`), so:

- **Open a position** in the GMI Positions dashboard → it appears here on
  the next daily run (provided its ticker is in `TV_MAP`, below).
- **Close a position** → it drops off automatically. Nothing to edit.

Sync logic lives in `gmi_positions_sync.py`. Each successful Drive fetch is
cached to `gmi-positions-source.json` (committed), so the build always has a
last-good snapshot; if Drive is unreachable the build uses the snapshot and
**fails loud** so the broken sync is caught in CI, never silently stale.

> **One-time setup:** the Drive `positions.json` must be shared
> **"anyone with the link can view"** for the GitHub runner to fetch it.
> Until then every run is RED with a clear SOURCE WARNING (the page still
> builds from the snapshot).

## The one manual touchpoint

`TV_MAP` in `gmi_positions_sync.py` maps each positions.json ticker to its
TradingView symbol (+ category / secular method). If GMI opens a position in
a **brand-new ticker**, the build fails loud naming it — add one line to the
map (same fields as `positions.py`) and re-run. Closes never need anything.

Instruments with no market feed (baskets / funds / options, e.g. the
Exponential Age Basket and EADAF) are listed as unpriced lines under the
table rather than trend rows.

## Machine-readable

Both for AI parsing, refreshed on every run:

- embedded in the page: `<script id="gmi-data" type="application/json">`
- sidecar file: `dashboard-risk-monitor/gmi-positions.json`

Payload: macro regime (M2/ISM trend + since + RoC), the deduped GMI position
rows (trend, since, secular, vol, books), the Assets rows, and source
provenance (`positions_meta`).

## Formulas

Identical to the RV pages — `lib/signals.py` (weekly + monthly trend) and
`lib/metrics.py` (secular, vol), reused via `build_risk_monitor.build_row` /
`build_macro`. See `HANDOFF_Risk-Monitor.md` §8 for the verified details.
