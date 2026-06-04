# Dashboard Template — Handover & How To Scale It

**For:** Real Vision Product & Engineering
**From:** Content (Raoul)
**What this is:** one working dashboard (the GMI Compounding Machine), deliberately
built as a *pattern* so that integrating it — and every dashboard after it — is a
wiring job, not a rewrite.

This is the self-contained demonstration we agreed on. It runs by opening
`compounding-machine.html` in a browser. No build step, no server, no API keys.
Below is how it's structured, why, and how to turn it into the shared template.

---

## TL;DR — why this isn't painful to integrate

The dashboard is split into **four files with one job each**. Only one of them ever
changes between data refreshes, and only one of them changes when you swap data
providers. Nobody re-reads a 600-line file to find the seam.

| File | Role | Who touches it | Changes when… |
| --- | --- | --- | --- |
| `compounding-machine.html` | **Shell** — UI + render only | built once | the *design* changes (rare) |
| `data/data.js` | **Data** — the injected series | the pipeline (automated) | every weekly refresh |
| `lib/compute.js` | **Compute** — pure maths (regression + sim) | built once, shipped as-is | the *methodology* changes (rare) |
| `lib/sources.js` | **Sources** — asset list + provider adapters | config edit | you add/swap an asset or data feed |

The shell reads three globals the other files publish: `window.DASHBOARD_DATA`,
`window.GMI_COMPUTE`, `window.GMI_SOURCES`. That's the whole contract.

This mirrors how the live **Everything Code** dashboard already works in this repo:
`index.html` (shell) reads `window.TGL_DATA` from `data/data.js` (written by the
Python pipeline). We've just made the same separation explicit and reusable.

---

## The injection contract (the rule that prevents merge pain)

> The pipeline rewrites **only** `data/data.js`, and **only** between the markers:
> ```js
> // __PIPELINE_DATA_START__
> window.DASHBOARD_DATA = { ... };
> // __PIPELINE_DATA_END__
> ```
> Nothing else in any file is ever machine-edited.

Because data lives in its own file behind markers, a weekly refresh is a one-line
diff. The shell, the maths and the config are stable and reviewable. (Exact field
names and types are the contract in `SPEC_compounding-machine.md` §9.)

---

## The data-source socket (this is how we solve "we can't use NDX / we have our own feeds")

The shell never talks to a data provider. It calls **one** function —
`getAssetSeries(key)` in `lib/sources.js` — which returns a standard series of
`{ d:"YYYY-MM-DD", c:number }`. *How* that series is produced is decided per-asset
by the `source` field in `ASSET_REGISTRY`, which dispatches to an **adapter**.

```
shell ──asks──> getAssetSeries("BTC") ──dispatch by source──> adapter ──> [{d,c}] ──> compute ──> render
```

Provided adapters: `injected` (reads the pipeline's `data.js` — the default,
production path) and `coingecko` (an example live feed, BTC only). Every adapter
returns the same shape, so swapping is invisible to everything downstream.

**Therefore:**
- **Use your own data instead of TradingView/CoinGecko:** add an `internal` adapter
  in `lib/sources.js` that returns `Promise<[{d,c}]>` from your feed, and set the
  asset's `source: "internal"`. *No other file changes.*
- **Can't ship NDX:** delete the NDX row from `ASSET_REGISTRY` (and its block in
  `data.js`). The toggle, charts and maths adjust automatically. It's a config edit.
- **Add an asset (ETH, gold, an RV index):** copy a registry row, point it at a
  source, drop its series into `data.js`. Done.

We *suggest* TradingView as the default (this repo already pulls weekly BTC & NDX
that way, so there's no new dependency), but the socket means that's your call, not
a hard-coded assumption.

There's one graceful-degradation nicety: if a live adapter errors, `getAssetSeries`
falls back to the injected series so the dashboard never goes blank — the same
"skip it, keep the rest" spirit as the existing pipeline.

---

## Verifying a build matches the prototype (no guesswork)

`SPEC_compounding-machine.md` §8 lists concrete check-cases. They're runnable
headlessly against the pure compute module — this is the fastest way to confirm a
port (or a Chart.js re-skin) is faithful:

```bash
cd dashboard-template
node -e '
  const fs=require("fs"),vm=require("vm");
  const sb={};sb.window=sb;sb.globalThis=sb;sb.fetch=()=>Promise.reject();vm.createContext(sb);
  ["data/data.js","lib/compute.js","lib/sources.js"].forEach(f=>vm.runInContext(fs.readFileSync(f,"utf8"),sb));
  sb.GMI_SOURCES.getAssetSeries("BTC").then(r=>{
    const a=sb.GMI_COMPUTE.analyse(r.series,{startDate:"2017-09-01",freezeDate:"2025-12-31",projectToYear:2035,initialStake:100000,buyThreshold:1,buyAmount:25000,sellThreshold:1,sellPct:20});
    console.log("CAGR",a.reg.impliedCAGR,"1sd",a.reg.sd1pct,"sigma",a.currentSigma.toFixed(2),"buys",a.run.buys.length,"sells",a.run.sells.length);
  });
'
# expect: CAGR 45 1sd 60 sigma -1.17 buys 4 sells 2
```

Because the maths is a pure module, these same numbers hold whether the front-end is
this Recharts shell, a Chart.js shell, or a unit test. The compute module ships
unchanged — nobody re-implements the regression and risks drifting from the author's
intent.

---

## How a content creator makes the NEXT dashboard from this (the scalable bit)

This is the part that turns one tool into a method. To author a new dashboard:

1. **Copy this folder.** Rename the shell.
2. **Write the compute module** (`lib/compute.js`) — the dashboard's maths as pure
   functions taking data + params, returning numbers. (Claude is good at this; keep
   it framework-free.)
3. **Define the data contract** — decide the named variable(s) and field shapes,
   and write a sample `data/data.js` between the markers so the thing runs offline.
4. **Register sources** (`lib/sources.js`) — list the assets/series and which
   adapter feeds each. Reuse `injected`; add live adapters only if needed.
5. **Build the shell** to read those globals and render. Design lives here and
   nowhere else.
6. **Fill in the spec** (`SPEC_*.md`) — especially §8 check-cases and §9 field
   table. That document *is* the hand-off.

Hand P&E the folder + the spec. Integration on their side is then: point the pipeline
at the data contract, (optionally) re-skin into the production shell, run the
check-cases, ship. No archaeology.

---

## What P&E still owns (explicitly out of scope for content)

So expectations are clear — the content side delivers the four files + spec above.
P&E decides and owns:

- **Production substrate.** This demo uses React+Recharts via in-browser Babel
  (zero-build, easy to review). For production you may re-skin the *shell* into the
  Everything Code Chart.js shell (shared layout/lock/Copy-layout system, brand
  fonts, freshness badges). Only the render layer changes; `compute.js`,
  `data.js`'s contract and `sources.js` carry over. Pre-compiling the JSX (esbuild)
  to drop the ~1s Babel delay is the same one-time step.
- **The real pipeline.** Wire your data feed to emit `data.js` between the markers
  on the weekly cadence (this repo's `update_data.py` + GitHub Action is the model).
- **Hosting / tiering / embed.** Iframe vs native page; any Free/Pro gating (see
  spec §7).

---

## File map

```
dashboard-template/
├── README_HANDOVER.md          ← this file
├── SPEC_compounding-machine.md ← the filled-in P&E spec (the hand-off contract)
├── compounding-machine.html    ← SHELL  (fixed: UI + render)
├── data/
│   └── data.js                 ← DATA   (pipeline rewrites between markers)
└── lib/
    ├── compute.js              ← COMPUTE (pure maths, ships unchanged)
    └── sources.js              ← SOURCES (asset registry + swappable adapters)
```
