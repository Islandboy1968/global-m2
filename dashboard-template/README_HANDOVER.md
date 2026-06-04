# Compounding Machine — Hand-off to Product & Engineering

**For:** Andrew + the Real Vision front-end team
**What this is:** a finished, self-contained **beta** of the GMI Compounding Machine,
live and ready to iframe. It already wears the Real Vision design, pulls real
data on a schedule, and is split into clean layers so a proper native build later
is a re-skin, not a rewrite.

---

## 1. To stand up the iframe (this is all you need)

It's live on GitHub Pages right now:

```
https://islandboy1968.github.io/global-m2/dashboard-template/compounding-machine-beta.html
```

Embed it anywhere:

```html
<iframe src="https://islandboy1968.github.io/global-m2/dashboard-template/compounding-machine-beta.html"
        width="100%" height="2200" frameborder="0"
        style="border:0; max-width:1240px; display:block; margin:0 auto;"
        title="GMI Compounding Machine (BETA)"></iframe>
```

It's a single self-contained HTML file (React/Recharts via CDN, data baked in) —
no build step, no API keys, no server. The toggle shows **BTC | QQQ**. The status
pill reads **"Beta · demo data"** on purpose (see §5).

---

## 2. Where everything lives

In the `Islandboy1968/global-m2` repo, folder `dashboard-template/`:

| File | Role |
| --- | --- |
| `compounding-machine.html` | **Shell** — the RV-restyled React render (reads three globals, holds no data/maths) |
| `compounding-machine-beta.html` | The **built single-file** version that the iframe points at (shell + engine inlined) |
| `data/data.js` | **Data** — weekly BTC + QQQ closes, written between `__PIPELINE_DATA_*__` markers |
| `lib/compute.js` | **Compute** — pure regression + simulation maths (no React/DOM) |
| `lib/sources.js` | **Sources** — asset registry + data-source adapters |
| `SPEC_compounding-machine.md` | The dashboard spec (formulas + data contract + check-cases) |

Pipeline (repo root):
- `build_dashboard_template_data.py` — pulls real data, writes `data/data.js`, rebuilds the beta.
- `.github/workflows/dashboard-data.yml` — runs it (hourly + manual).

---

## 3. The architecture (four layers — please preserve)

The shell reads exactly three globals and contains zero price data and zero maths:

| Global | From | Role |
| --- | --- | --- |
| `window.DASHBOARD_DATA` | `data/data.js` | `{updated, assets:{BTC:{series:[{d,c}]}, QQQ:{…}}}` — the pipeline rewrites only this, only between the markers |
| `window.GMI_COMPUTE` | `lib/compute.js` | `analyse(series, params)` → `{reg, channel, run, currentSigma, trendNow, lastPrice, lastDate}` — ships unchanged to production |
| `window.GMI_SOURCES` | `lib/sources.js` | `ASSET_REGISTRY` + `getAssetSeries(key)` → `{series, source, live, asOf, asset}` |

So a native port is: rebuild the **shell** with your components against the same
three globals. `compute.js` and the `data.js` contract carry over untouched — the
tested maths never gets re-implemented (and so never drifts from the author's intent).

---

## 4. How data flows now (and the one swap for production)

Today, `dashboard-data.yml` pulls **real weekly BTC + QQQ closes from TradingView**
(reachable on GitHub's runners) and bakes them into `data/data.js` hourly. The
dashboard reads that via the `injected` adapter — **no in-browser fetch, no CORS,
no loading hang.** "Delayed/hourly" by design, which suits a weekly-close tool.

**For the platform build, swap the data source, nothing else:** `lib/sources.js` has
a `platform` adapter stub. Point it at Real Vision's own QQQ/BTC end-of-day feed
(the QQQ-as-Nasdaq-100 proxy you already use) and set each asset's `source:"platform"`.
The shell, compute, and data contract don't change. (The external CoinGecko/Yahoo
adapters in that file are beta-only examples — delete them for production.)

Why QQQ and not NDX: index data is licensed/awkward to source; QQQ is the tradable
proxy (the percentages track closely), which is the call we landed on with your team.
The embedded history is shown in QQQ dollar units; rescaling is a constant log-shift,
so CAGR, σ bands, and every buy/sell signal are unaffected.

---

## 5. Honest labelling (deliberate)

The pill says **"Beta · demo data"** and the footer **"Demo · as of <time>"** because
it's an unproven iframe and we don't yet trust data integrity over time. When the
`platform` adapter is wired and QA-verified, flip the live flag and it reads "Live".

---

## 6. Verifying a port is faithful (QA hooks)

`compute.js` is pure, so the spec's check-cases run headlessly. Current real-data values:

| | BTC | QQQ |
| --- | --- | --- |
| Implied CAGR | 45% | 18% |
| 1σ | 60% | 13% |
| Buys / Sells (defaults) | 5 / 2 | 8 / 3 |
| First buy | 2018-11-23 | 2018-… |

Run them after any port; same numbers = faithful. (Full method + the rest of the
check-cases are in `SPEC_compounding-machine.md` §8.)

---

## 7. What's done vs. what's yours

**Done (content side):** working tool, RV design applied (from Claude Design — dark
navy, lime accent, cyan price line, Hanken Grotesk), real data on a schedule, the
four-layer split, the spec with QA check-cases, live iframe URL.

**Yours (P&E):** decide whether to keep the iframe as the beta or rebuild the shell
in your shared components / design system; wire the `platform` data adapter to RV's
feed; hosting, tiering, and any "Live" promotion once data is QA-verified.

The whole point: the beta proves the tool and the method now; the only part that
genuinely needs you is the data feed and (optionally) re-skinning one layer.
