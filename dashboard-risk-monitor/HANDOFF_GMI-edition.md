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
GMI Positions book is **repo-canonical**: Cowork publishes it by committing
`dashboard-risk-monitor/gmi-positions-source.json` to `main`. The pipeline
(`build_gmi_risk_monitor.py` via `.github/workflows/gmi-risk-monitor.yml`)
rebuilds **on every commit to that file** plus a daily price refresh, so:

- **Open a position** in the GMI Positions dashboard → Cowork commits the
  book → the board updates within minutes (provided the ticker is in
  `TV_MAP`, below).
- **Close a position** → it drops off automatically. Nothing to edit.

Sync logic lives in `gmi_positions_sync.py`. A missing or malformed book
**fails loud** in CI — never silently stale.

> **The repo file is a publish target, not an editing surface** (per Cowork,
> 2026-06-12). The authoring flow is: Cowork's local canonical book +
> Raoul's Drive-inbox exports (`gmi-positions-YYYY-MM-DD.json`, Raoul's
> changes win) → merge → commit here. Nothing reads the repo file back into
> the book, so a direct edit to `gmi-positions-source.json` on GitHub is
> **silently overwritten** by Cowork's next morning publish. Changes to the
> book itself go through Raoul. The dated Drive snapshots are write-only
> convenience copies; the pipeline reads none of them.

> **History:** v1 fetched `positions.json` from the Google Drive folder
> (`1wKaSzAgTF75CkDDm8cjl2QQmEHhL95xv`) with the repo file as cache.
> Flipped to repo-canonical on 2026-06-12 once Cowork began committing the
> book directly — fresher data, no public link-sharing, instant rebuilds.
> The Drive copy is now human-facing only; the pipeline never reads it.

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
