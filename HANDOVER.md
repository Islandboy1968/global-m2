# The Everything Code — Session Handover

Read this first, then `DEV_NOTES.md` for the deep architecture detail. This file is the
"how to work on this safely" guide plus the next task brief. Last updated end of the session
that built the per-chart lock + published default layout.

## Live state
- Repo (public): https://github.com/Islandboy1968/global-m2  (slug is still `global-m2`)
- Live site: https://islandboy1968.github.io/global-m2/  (GitHub Pages, root of `main`)
- Latest `main` at handover: `81b4f48` (published default layout). Data refreshes daily.
- Product name: **The Everything Code (TEC)**. Three tabs so far: Global Liquidity, US Liquidity,
  The Big Picture. Next: **The Business Cycle** (see bottom).

## Environment gotchas (READ — these will bite a fresh session)
1. **Clone into the sandbox's own filesystem, not the mounted folder.** `git` cannot lock files
   on the mounted Cowork folder. Work in `/tmp/work/global-m2` (bash). The Read/Edit tools,
   however, can ONLY reach the mounted outputs folder, not `/tmp`. So the workflow is:
   edit a file in the mounted outputs dir with Write/Edit, then `cp` it into `/tmp/work/global-m2`
   for git. To read repo files, use `cat` in bash (Read can't see `/tmp`).
2. **`/tmp` can be wiped between bash calls.** Re-clone defensively at the start of a call
   (`[ -d global-m2/.git ] || git clone ...`). When writing a file's content in bash (e.g. a
   layout/data file via heredoc), do the write + `git add` + commit + push in the SAME bash call,
   or it may vanish before the commit.
3. **Pushing needs a fine-grained PAT, pasted in chat — never commit it.** The repo is public.
   Push with an inline URL and redact it in any output:
   `git push "https://x-access-token:<TOKEN>@github.com/Islandboy1968/global-m2.git" HEAD:main`
   then pipe through `sed -E 's/github_pat_[A-Za-z0-9_]+/[REDACTED]/g'`.
   **The token in use expires 2026-06-20** — ask Raoul for a fresh one after that.
4. **FRED is NOT reachable from the sandbox** (network times out) and `web_fetch` is
   provenance-locked (only URLs Raoul pasted). So you cannot pull market/economic data locally.
   Data is generated server-side by the GitHub Action (its runner CAN reach FRED/TradingView).
   To get new data live: edit the Python pipeline, push, then trigger the Action and poll:
   ```
   curl -fsS -X POST -H "Authorization: Bearer <TOKEN>" -H "Accept: application/vnd.github+json" \
     https://api.github.com/repos/Islandboy1968/global-m2/actions/workflows/main.yml/dispatches \
     -d '{"ref":"main"}'
   # poll: GET .../actions/runs?per_page=1  -> wait for completed/success (takes ~4-5 min;
   # the TradingView pull of ~95 symbols is the slow part), then git fetch and inspect data/data.js
   ```
   The Action commits a "data: refresh" commit, so after it runs you must `git fetch` + rebase
   before your next push.
5. **Verify the frontend headlessly with jsdom + a fake `Chart`** (no browser/canvas in sandbox).
   Pattern used all session: extract the last `<script>` from index.html, stub a `Chart` class
   that records `data`/`options`/`scales`, bind the canvas-id globals, run in jsdom with
   `runScripts:'dangerously'`, assert on `window.GLOBAL/US/BIG`, control counts, colours, captions,
   lock behaviour. `node --check` for syntax first. (jsdom doubles a couple of `querySelectorAll`
   counts oddly — trust grep on the file for element counts.)

## What's built (see DEV_NOTES.md for full detail)
- **Single file frontend:** `index.html` (HTML + CSS + one app `<script>`). Charts via Chart.js
  4.4.1 + chartjs-plugin-zoom. Data is static `data/data.js` (`window.TGL_DATA`), regenerated
  daily by the Action — nothing is fetched in the browser.
- **Pipeline (Python, runs in the Action):** `update_data.py` orchestrates; `tv_pull.py`
  (TradingView), `econ.py` (47-economy M2 table), `us_liquidity.py` (`build_us`, FRED keyless csv),
  `big_picture.py` (`build_big`, FRED). Each sub-build is wrapped in try/except so one failure
  never breaks the rest.
- **Data shape:** `TGL_DATA = { updated, summary, series[], btc[], ndx[], us{summary,series[]},
  big{lfpr[],births[],debt[],interest[]} }`. US `vn`=Broad, `vo`=Narrow ($tn). Charts show $BN
  (×1000). Broad = WALCL − TGA − RRP + **TOTBKCR** (total bank credit, ~$25T). Narrow = …+ bank
  Treasury securities (~$12T).
- **GMI styling (Claude Design template):** white page; each chart on a pink-gradient `.panel`
  with a top-left HTML legend (liquidity black `#131316`, asset hot-pink `#f12a5a`), a numbered
  `.chead`, and a source line. Fonts self-hosted in `fonts/`: **Teko** (display titles), **AT Aero**
  (body/legends), **DM Mono** (small labels). Series lines 1px (companion 0.75px). Wheel zoom is
  damped (`ZOOM_SENS`, `AXIS_DRAG_DAMP`).
- **Per-chart controls:** each chart is independent (no cross-chart sync). Every panel has its own
  range buttons (`1M…All`, `buildRanges`), overlay charts have a single free lead/lag day-input
  (`buildLag` back-shift for price overlays; `buildLagFwd` forward-shift for Big Picture), and a
  **padlock** (`addLock`) top-right.
- **Per-chart lock + published default:** locking a chart saves its view to `localStorage`
  (`tec_charts`); locked-at-latest charts slide forward with new data at the same scale. The repo
  ships a baseline `data/layout.js` (`window.TEC_DEFAULT_LOCKS`) that ALL visitors load and reset to;
  personal localStorage overrides locally only. The **Copy layout** button exports the current
  locked charts as a `window.TEC_DEFAULT_LOCKS = {...};` string to paste into `data/layout.js`.
  (localStorage is per-device; locks never travel via the shared link unless baked into layout.js.)

## How to add a new tab (the proven pattern — mirror "The Big Picture")
1. **Data (if new series needed):** add a `build_<x>()` to a new module (or extend `big_picture.py`),
   fetch via `from us_liquidity import _fetch` (FRED keyless csv). Wire into `update_data.py` inside
   try/except and add the block to the `data` dict. Push, trigger the Action, verify `data/data.js`.
   (`_closest_before` default lookback is 45 days so monthly series forward-fill on a weekly grid.)
2. **Tab nav:** add a `<button data-tab="cycle">The Business Cycle</button>` to `#tabnav`; add the
   tab name to `TABMETA` and the `secDescr` logic in `showTab`; add `cycle:document.getElementById(...)`
   to `panes`.
3. **Markup:** add a `<section id="tab-cycle" class="pane" hidden>` with a `<div class="note" hidden>`
   missing-data notice and one `.chead`+`.panel` block per chart (copy a Big Picture block: legend,
   `.chartbox` canvas with a unique id, `.ctrls` with empty `.ranges` and optional `.lagctl`, `.src`).
4. **JS IIFE:** build it like the `BIG` IIFE — read the data, build charts with `overlayLin`
   (linear dual axis; pass `rightReverse=true` for an inverted axis) or `opts(...)` for single-series,
   call `attach(canvas,chart)`, then `controls(chart)` / `controlsFwd(chart,{...})` (these auto-add
   the padlock and register the chart in `ALL_CHARTS`). Set sensible default windows with the
   `bigStart(chart, "YYYY-01-01")` helper pattern. `return {charts}` and expose `window.CYCLE=CYCLE`.
5. **Lock restore loop:** the existing final pass over `ALL_CHARTS` will pick up the new charts
   automatically (they register via `addLock`). No change needed.
6. **Verify** with the jsdom harness (stub the new data block), update DEV_NOTES, commit, push.

## NEXT TASK: The Business Cycle section
Goal: a new tab titled **The Business Cycle** (kicker stays "The Everything Code", big title
"The Business Cycle"), same GMI styling and per-chart controls/lock as the others.

Open questions to confirm with Raoul before building (he'll specify the exact charts, as he did
for The Big Picture):
- Which charts/series? Likely candidates from his framework: ISM Manufacturing PMI, the ISM vs a
  market (e.g. liquidity or NDX with a lead), the 10y–2y yield curve, unemployment rate / claims,
  copper/gold or other cyclical ratios, leading economic indicators. **Get the exact list + which
  is left vs right axis, any leads, and any inversion.**
- All FRED-able? Confirm each series id (most US macro is on FRED keyless csv). Some ratios may need
  TradingView (use `tv_pull`) — confirm source per series.
- Default view windows to match the GMI house charts (as we did: e.g. 2001/2004/2010 starts).
Then build per the pattern above, trigger the Action to bake the data, verify, and push.

## Quick reference — recent commits
- `81b4f48` publish default layout · `c24c62f` publishable layout + Copy button · `47f25e2` lock
  tracks-latest · `e18d4be` per-chart lock · `9c386b6` Broad=TOTBKCR · `23775a7` data refresh ·
  Big Picture, fonts (Teko/AT Aero), Claude Design template, rebrand earlier in history.
