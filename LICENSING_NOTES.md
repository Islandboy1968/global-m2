# LICENSING_NOTES.md — data redistribution & the commercial-vendor direction

> **Status: OBJECTIVE UNDER CONSIDERATION, NOT A FINAL DECISION.**
> This file records a direction the project is likely to move in, so every
> session shares the same context and doesn't accidentally design against it.
> Nothing here is committed. Do not refactor the pipeline to match it yet — treat
> it as a constraint to keep in mind, not a spec to implement. Last updated
> 2026-06-08.

## The direction

GMI is likely to license a commercial market-data API — **Refinitiv / Datastream
(LSEG)** is the leading candidate — to source the dashboard's series in one go,
replacing the current TradingView + FRED free-feed mix (and retiring the China M2
override entirely). Not signed; evaluating.

The intended distribution model for the dashboard built on it:

- **Not public.** Behind a paywall, ~300 named clients.
- **GMI-branded**, with **attribution to Refinitiv/LSEG** as the data source.
- **No wholesale distribution of the underlying data** — clients consume GMI's
  derived views, they do not get a re-exportable copy of the raw vendor series.

This model is squarely what LSEG/Refinitiv "value-added / derived works" licenses
contemplate (paywalled, named-client, attributed, no wholesale redistribution), so
it is broadly compatible in principle. The contract terms govern; confirm specifics
with LSEG before signing.

## What this means for the data layer (the part to keep in mind now)

The licensing line is **derived-vs-raw**, not who-can-see-it (the paywall handles
access). The constraint is whether a subscriber can extract the raw licensed series
back out and reconstitute the vendor dataset wholesale.

- **License-friendly by construction:** the GMI Total Liquidity index, YoY, the 3m
  average, composites, and the whole `summary.json` digest (latest / trend / YoY /
  range_factor) are **derived works** — aggregations and statistics over the inputs,
  not the inputs themselves. Safe to surface.
- **The part to think about:** `data/data.json` currently ships **full raw series**
  for every leaf. Under a "no wholesale distribution of underlying data" license,
  the full raw vendor history as a downloadable blob is the thing a client could
  scrape to reconstitute the licensed dataset. Options when the time comes (decide
  then, not now):
    - serve raw series only at chart-display granularity / windowed, not full history;
    - gate full series behind per-client entitlement;
    - publish only sufficiently-derived aggregates on the open surface and keep raw
      series server-side.
- **The machine-readable work already done leans the right way.** `summary.json`
  is almost entirely derived/aggregated, so the AI-readable surface is the
  license-safe one; `data.json` is the surface whose raw-vs-derived boundary needs
  a decision at migration time.

## The migration shape (when/if the LSEG deal firms up)

Small and additive — none of the current machine-readable work becomes throwaway:

1. **`fetchers/` swap at the bottom layer only.** Add a `datastream.py` (or
   `refinitiv.py`) fetch primitive alongside `tv_pull.py` / `fred.py`; point the
   `build_*` modules at it. The builders, `update_data.py`, `summarize.py`,
   `indicators_meta.py`, and `DATA_CONTRACT.md` sit *above* the source and are
   unaffected. Update the `source` field in `indicators_meta.py` per series.
2. **Attribution field.** Add `source_attribution: "Refinitiv / LSEG"` (or
   per-series) to `index.json` / `summary.json`, plus a dashboard footer line.
3. **Raw-series publish boundary.** Decide the `data.json` derived-vs-raw line
   above so the published payload stays derived-works-safe.
4. **Access layer (above the data contract).** ~300 clients ⇒ auth + optional
   per-tier entitlement (which series each tier fetches). App-layer concern; the
   data contract shape does not change.

## Other vendor terms to re-check at the same time

The current free feeds also have redistribution terms that matter the moment the
dashboard goes commercial (even before any LSEG switch):

- **TradingView** websocket data and **FRED** are fine for the current public,
  non-commercial use; re-read their terms for a paywalled commercial product.
- If only *some* series move to LSEG and others stay on free feeds, the
  derived-vs-raw boundary applies per-source, not globally.

---

See `DATA_CONTRACT.md` for the surfaces referenced here. The EA companion repo
(`Islandboy1968/exponential-age`) carries a parallel note for its asset/market
charts.
