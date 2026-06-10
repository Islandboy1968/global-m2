# DATA_CONTRACT.md — machine-readable contract for the TEC dashboard

Purpose: make TEC (The Everything Code / global-m2) **efficiently consumable by an
AI** that fetches the data and returns compressed summaries and insight — without
scraping charts or loading the full ~1.5 MB series payload into a context window.

This is the **TEC half** of a contract shared with EA (The Exponential Age). The
two dashboards are read together, so they emit the **same `summary.json`
indicator-digest shape** and the same `schema_version` / `dashboard` discriminator
— one parser ingests both. EA's copy of this contract is the companion document;
where the two payloads differ (TEC's `data.json` is block-structured with
`{"d","v"}` points, EA's is a flat `indicators` map with `[x,value]` points), each
repo's contract documents its own `data.json` and they converge at `summary.json`.

Status: **v1.0** — the digest, index, and schema stamp are emitting.

---

## 1. Three surfaces, one source of truth

| File | Size | For | Shape |
|------|------|-----|-------|
| `data/summary.json` | ~36 KB | **AI / agents**, quick reads | per-indicator precomputed digest |
| `data/data.json` | ~1.5 MB | charts, deep analysis | full per-series points |
| `data/data.js` | ~1.5 MB | the browser | `data.json` wrapped as `window.TGL_DATA = {…}` |
| `data/index.json` | ~1 KB | **agent entry point** | lists surfaces, reading order, companion dashboard |

An AI reads `index.json` (where things are) → `summary.json` (every indicator's
current state, trend, units, freshness) and only opens `data.json` when it needs
the *shape* of a specific curve. `summary.json` is ~40× smaller than `data.json`.

Both `data.json` and `summary.json` carry a top-level **`schema_version`** (`"1.0"`)
and **`dashboard`** (`"tec"`). Bump the version on any breaking shape change.
(`data.json`'s version lives in `update_data.SCHEMA_VERSION`; the digest's in
`summarize.SCHEMA_VERSION`.)

**Discipline: the pipeline emits FACTS, never narrative.** `summary.json` carries
latest values, ratios, YoY, and log-linear trends — descriptive statistics over the
emitted series. Synthesis ("the cycle is turning because…") is the AI's job. This
keeps the data trustworthy and the insight layer swappable.

---

## 2. `data.json` shape (the full record)

```
{
  "schema_version": "1.0",
  "dashboard": "tec",
  "updated": "<YYYY-MM-DD HH:MM UTC>",
  "total_liquidity": {                                         // THE HEADLINE — GMI Total Global Liquidity Index
      series:[ {d, v, y, ys} … ],                              //   daily (FX-driven), $tn (FNL+M2)
      series_plus_banksec:[ {d, v, y, ys} … ],                 //   GMI 2025 flagship: + US bank securities
      components:{ balance_sheets:[ {d,v} … ], m2:[ {d,v} … ] },  // monthly decomposition of the one index
      monetization:{ bank_securities, bank_credit, reverse_repo, tga },  // US deficit-monetization watch series (monthly $tn)
      legs_latest:{ <ISO2>: v_tn … },                          //   per-economy contribution
      summary:{ latest, total_tn, total_plus_banksec_tn, yoy, yoy_s, n_economies,
                balance_sheets_tn, m2_tn, us_bank_securities_tn } },
  "summary": { latest, total_tn, yoy, yoy_s, n_economies },   // Global M2 (47-econ) — now a COMPONENT, not the headline
  "series":  [ {d, v, y, ys} … ],                              // Global M2, daily (component / overlay source)
  "btc": [ {d, p} … ], "ndx": [ {d, p} … ],                    // overlays
  "us":   { summary, series:[ {d, v, y, ys, vo, yo, yos} … ] },
  "big" | "cycle" | "exp" | "infl" | "labor" | "rates"
      | "housing" | "credit" | "china":  { <leaf>: [ {d, v} … ] | null },
  "china_override": { latest, feed_latest, override_latest, source,
                      redundant_override_months, active_override_months,
                      next_release_iso, stale, days_until },
  "freshness": { <block>: { status, checked, stale, series:{ <leaf>: {as_of, source, source_latest, status} } } }
}
```

**Point shape:** every series point is a dict with a date `d` (`"YYYY-MM-DD"`) and a
value — `v` for data series, `p` for the price overlays (`btc`/`ndx`). A consumer
reads `point["d"]` and `point["v"]` (or `"p"`); treat any other keys (`y`, `ys`,
`vo`…) as optional secondary measures.

**The self-describing layer lives in `indicators_meta.py`**, keyed by each leaf's
dotted path (`"cycle.fci"`, `"infl.core_yoy"`, …). It is NOT inlined into
`data.json` (which stays pure series) — `summarize.py` joins meta to series when it
builds the digest. Each entry carries `title`, `group`, `role`, `timing`
(leading/coincident/lagging), `unit`, `progress` (higher/lower), `source`,
`description`. This is the TEC counterpart to EA's `indicators.py`.

**Freshness is source-verified.** `verify_data.py` goes to each series' actual
source, compares the latest complete month to what shipped, and stamps
`IN_SYNC | BEHIND | MISSING | UNVERIFIED | DERIVED` per leaf into
`data["freshness"]`. The digest surfaces this verdict per indicator.

---

## 3. `summary.json` shape (the AI-first digest)

```
{
  "schema_version": "1.0",
  "dashboard": "tec",
  "title": "The Everything Code — global liquidity & cycle dashboard",
  "generated": "<iso>",          // when the digest was built
  "data_updated": "<iso>",       // mirrors data.json.updated
  "headline": {                  // the dashboard centrepiece — the Total Liquidity Index
     "metric": "GMI Total Global Liquidity Index (CB balance sheets netted + M2, 10 economies, USD)",
     "level": 142.4, "unit": "$ trillions",
     "yoy_pct": 7.7, "as_of": "<iso>", "n_economies": 10,
     "components": {"balance_sheets_tn": …, "m2_tn": …},
     "global_m2": { … }          // broad-money component (47-econ daily), carried as secondary
  },
  "signals": [                   // computed lead/lag relationships — the SIGNAL layer
     { "relationship": "total_liquidity_leads_btc", "best_lead_months": …,
       "correlation": …, "r2": …, "method": "max cross-correlation, monthly, …",
       "read": "plain-English read" }, …
  ],
  "indicators": {
     "<block.leaf>": {
        "title","group","role","timing","unit","progress","source","description",
        "latest": {"x","value"},        // current point
        "best":   {"value"},            // frontier (min if progress=lower else max)
        "first":  {"x","value"},
        "n_points","span_years",
        "range_factor",                 // max/min — magnitude of the move
        "yoy_pct",
        "trend": { "window_years","log10_per_year",
                   "doubling_years" | "halving_years" },   // recent-window fit, positive series only
        "freshness": {"as_of","status","source_latest"}    // from verify_data
     }
  },
  "build": {
     "blocks_total","blocks_ok",
     "stale":[…], "behind":[…], "missing":[…],   // from source-verified freshness
     "china_override": {
        "latest",          // true CN M2 frontier month (live feed or override, whichever is newer)
        "feed_latest",     // newest month the live ECONOMICS:CNM2 feed serves
        "override_latest", // newest hand-entered override month (or null)
        "source",          // "feed" | "override" — which provided the frontier
        "redundant_override_months",  // override months the feed caught up to — safe to delete
        "active_override_months",     // override months still doing work (bridge/correction)
        "next_release_iso", "stale", "days_until"
     }
  }
}
```

Honest-by-design notes:
- **`trend` is fit over a recent ~12-yr window** and only for strictly-positive
  series — most TEC series are YoY/z-scores that cross zero, so `trend` is
  legitimately `null` for them (don't read null as "no trend computed in error").
- **`freshness.status`** is the source-of-truth verdict, not a calendar guess.
- **`build`** rolls per-block freshness up so an agent can gate on data health,
  and carries the China-M2 override countdown.

---

## 4. Cross-dashboard alignment (TEC + EA)

The two share: the `summary.json` indicator-digest field set, the `schema_version`
scheme, and the `dashboard` discriminator (`"tec"` / `"ea"`). An agent can fetch
both digests and reason across them with one parser.

**Not yet on the TEC side** (EA-only or future): per-panel manifests
(`panels.json`) and the computed chart-relationship checks (`relationships.py`).
TEC is a single-page dashboard without per-tab panel directories; if TEC's
overlay charts (liquidity-leads-BTC/NDX, FCI-leads-ISM) later need machine-readable
construction metadata, adopt EA's §5 panel-manifest shape. Tracked, not built.

---

## 5. Versioning & what's locked

- **Locked:** the three-surface model, `schema_version` + `dashboard` stamp, the
  `summary.json` indicator-digest field set above, "pipeline emits facts not
  narrative," source-verified freshness in the digest.
- **Proposed / not yet locked:** panel manifests + relationship checks for TEC's
  overlay charts. Change freely while v1.0 is young; bump to 1.1 once a consuming
  agent depends on the added shape.

## 6. Licensing / redistribution

If the dashboard moves to a commercial data vendor (Refinitiv/LSEG is the likely
candidate) and ships as a paywalled, GMI-branded product, the **derived-vs-raw**
publish boundary matters: the `summary.json` digest and the index/composites are
derived works (safe), while full raw series in `data.json` may need a
granularity/entitlement boundary. This is a **direction under consideration, not a
decision** — see `LICENSING_NOTES.md`. Do not redesign the data layer for it yet;
just keep the derived-works surface (`summary.json`) the primary one.
