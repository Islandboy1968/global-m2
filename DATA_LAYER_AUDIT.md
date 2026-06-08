# TEC machine-readable data-layer audit

_Date: 2026-06-08. Author: Claude (session `claude/kind-keller-aCeEl`). No code
changes — this is the pre-work audit the bootstrap brief asked for. Scope decision
to be made with Raoul before any fetchers are written._

## TL;DR

TEC has **exactly one** recurring manual touchpoint: the `CHINA_M2_OVERRIDE` dict
in `update_data.py`. Everything else already auto-pulls from a machine-readable
source. And the override is **category (c)**: the machine-readable feed it patches
(`ECONOMICS:CNM2`, the same TradingView ECONOMICS feed used for the other 46
economies) is reachable from here and **currently serves the exact values being
typed in by hand**. The "~1-month lag" the README cites is not present today.

So the brief's headline target — "replace the China M2 banner-and-Claude-update
workflow" — is real but **small and surgical**, not a sweep. The honest fix is to
demote the override from a primary data source to an **auto-expiring timeliness
backstop**, and to close a structural gap: the one series carrying a manual
override is also the one series with **no source-truth verification**.

## 1. Architecture — what TEC actually is (vs the brief's assumption)

The brief was written from EA's notes and assumes EA's three-layer shape
(`fetchers/` → `builders/` → `update_data.py` → `data/data.json`). **TEC does not
have that shape.** TEC is the _parent_; EA formalised the pattern _after_ forking.
TEC's actual structure:

- **Fetch primitives (2):**
  - `tv_pull.py` — `pull_series(symbol, resolution, bars)` over the TradingView
    websocket. Used for all M2, FX, ISM, yields, risk assets, and FRED series
    that TradingView mirrors (`FRED:` passthrough).
  - `fred.py` — `fred_series(id)` over FRED's keyless `fredgraph.csv` endpoint.
- **`series_util.py`** — shared helpers (`iso`, `to_yoy`, `zscore_pts`,
  `pull_first` candidate-fallback). The nearest thing to EA's shared layer.
- **Per-block builders (flat, ~12):** `us_liquidity.py`, `big_picture.py`,
  `build_cycle.py`, `build_fci.py`, `build_exports.py`, `build_inflation.py`,
  `build_labor.py`, `build_rates.py`, `build_housing.py`, `build_credit.py`,
  `build_china.py`. Each exposes a `*_SERIES` source constant + a `build_*()`.
- **`update_data.py`** — orchestrator. Each sub-build wrapped in try/except so one
  failure nulls its block and the rest ship (the design rule the brief lists is
  already satisfied). Carry-forward backstop reuses last-good data on transient
  FRED/TV misses. `_reconcile_behind()` self-heals transient monthly-feed lag.
- **`verify_data.py`** — TEC's distinctive asset, and **more mature than EA's
  staleness story**: it goes to each series' _actual source_, compares the latest
  complete month to what shipped, and stamps `IN_SYNC / BEHIND / MISSING /
  UNVERIFIED / DERIVED` per leaf. `--gate` exits non-zero on `BEHIND`/`MISSING`.
- **`econ.py`** — the 47-economy table: `code → (M2 ticker, FX symbol, currency)`.

**Equivalences to the EA primitives the brief points at:**

| EA reference | TEC equivalent | Status |
|---|---|---|
| `fetchers/_manual_override.py` (staleness + return shape) | `update_data.py` `china_override` block (lines 356-375) + `verify_data.py` source-truth gate | Exists; **arguably stronger** (source comparison, not just calendar) |
| `compute_exit_code(build_status)` (degraded build blocks commit) | `verify_data.py --gate` returns 1 → workflow step fails | Exists, **but commit step is `if: always()`** — see §5 caveat |
| `indicators.py` registry drives JSON shape | `verify_data.build_registry()` imported from the builders' `*_SERIES` | Exists (registry-from-builders, can't drift) |
| CLAUDE.md classification rule | This document applies it below | n/a |

Net: the design rules the brief asks us to "confirm fit" **already hold in TEC**.
TEC doesn't need EA's folder layout retrofitted; it needs the one manual leg
brought up to the standard the rest of the repo already meets.

## 2. Source inventory — a/b/c classification

Legend: **(a)** machine-readable feed, already automated · **(b)** human-published
only, legitimate manual carve-out · **(c)** currently manual but a feed exists →
this is the work.

| Block / series | Source | Transport | Class |
|---|---|---|---|
| Global index — 46 economies' M2 | TradingView `ECONOMICS:*M2/*M3` | `tv_pull` | **a** |
| Global index — **CN M2 leg** | TradingView `ECONOMICS:CNM2` **+ `CHINA_M2_OVERRIDE`** | `tv_pull` + hand-edited dict | **c** |
| Global index — 45 FX pairs | TradingView `FX_IDC:*USD` / `FX:*` | `tv_pull` | **a** |
| Risk overlays (BTC, NDX) | TradingView `INDEX:BTCUSD`, `NASDAQ:NDX` | `tv_pull` | **a** |
| US net liquidity (WALCL, TGA, RRP, TOTBKCR, SBCACBW) | FRED | `fred.py` CSV + `FRED:` passthrough | **a** |
| Big Picture (LFPR, births, debt, interest, 5y) | FRED | `FRED:` passthrough | **a** |
| Business Cycle (ISM, new orders, GDP, capex) | TradingView `ECONOMICS:*` + `FRED:PNFI/GDP` | `tv_pull` | **a** |
| GMI FCI / FCI-ex-oil | derived from ISM | computed | **a** (DERIVED) |
| Exports (TW/KR semis proxy, JP machine tools) | TradingView `ECONOMICS:*` | `tv_pull` | **a** |
| Inflation (CPI components, breakeven, UMich) | FRED | `FRED:` passthrough + CSV | **a** |
| Labor / Rates / Housing / Credit | FRED + TradingView | `tv_pull` / `fred.py` | **a** |
| China tab (PBoC balance sheet, CN 10y) | TradingView `ECONOMICS:CNCBBS`, `TVC:CN10Y` | `tv_pull` | **a** |

**Category (b): none.** TEC has no PDF / paywalled / human-only sources. (Contrast
EA, which legitimately has Lazard/BNEF/IFR PDFs.) Nothing in TEC qualifies for a
manual carve-out under the classification rule.

**Category (c): one — the CN M2 leg.** Detail in §3.

## 3. The China M2 override — current wiring

**The dict** (`update_data.py:37`):
```python
CHINA_M2_OVERRIDE = {"2026-03": 353.86e12, "2026-04": 353.04e12}
```

**How it feeds the build:**
- `monthly_ffill_by_day(m2c["ECONOMICS:CNM2"], grid, CHINA_M2_OVERRIDE)` for the CN
  leg (line 221-222). Inside, `mp.update(override)` — the override **overwrites**
  the feed value for any matching month and **adds** any month the feed lacks.
- Fallback (line 207-217): if the `CNM2` pull is entirely missing from cache, the
  CN leg is synthesised from the override months _only_, with
  `backfill_leading=False` so pre-override dates stay null (no spurious 2010-era
  value from a 2026 yuan number).

**Staleness surfacing** (lines 356-375) → `data["china_override"]`:
- Computes the next expected PBoC release (`month N` published ~13th of `N+1`;
  next print `N+1` lands ~13th of `N+2`), sets `stale`, `days_until`,
  `next_release_iso`. The dashboard banner reads this so Raoul gets a nudge. This
  is a **calendar heuristic**, not a source comparison.

**The empirical finding (probed live this session):**
```
ECONOMICS:CNM2  latest points:  2026-03 = 353,863,650,000,000
                                2026-04 = 353,042,520,000,000   (raw yuan)
CHINA_M2_OVERRIDE:              2026-03 = 353.86e12
                                2026-04 = 353.04e12
```
**They match to the dollar.** The feed is current through 2026-04 — the same month
as the newest hand-entered value, and exactly the correct latest print (PBoC
releases May M2 ~13 June, not yet out on 2026-06-08). So **right now the override
is a no-op duplicate of data the feed already serves.** Units match too — the feed
returns raw yuan, no scaling needed.

**Why the override exists anyway (and why it can't just be deleted):** TradingView's
ECONOMICS China feed _intermittently_ serves a month-stale snapshot — the same
flakiness `_reconcile_behind()` already exists to self-heal for other monthly
blocks. The override is a manual patch for those windows. The problem is it's
maintained _every month unconditionally_, including the (common) months the feed
is already fresh, so it's a standing manual task that's usually redundant.

## 4. Reachability check (this sandbox's network policy)

| Upstream | Result here | Note |
|---|---|---|
| **TradingView** websocket | ✅ reachable | `ECONOMICS:CNM2` pulled live (needs `pip install websocket-client`) |
| **FRED** `fredgraph.csv` | ✅ reachable | **Differs from the historical HANDOVER note** ("FRED not reachable from sandbox"). This environment's network policy permits it. |
| FRED China M2 (`MYAGM2CNM189N`) | ⚠️ reachable but **discontinued** | Last point **2019-08**. Dead end for current China M2 — do **not** use as the feed. |
| Direct PBoC / NBS API | not pursued | No clean machine-readable feed; pbc.gov.cn is HTML/Excel, NBS portal is anti-scrape + Chinese. TradingView's ECONOMICS:CNM2 is the practical machine-readable path and is already wired. |

Reachability does not block the work: the feed we need is already in the pipeline.

## 5. Structural gap worth fixing alongside

The one series with a manual override is **the one series with no source-truth
verification.** `verify_data.build_registry()` gates `us.series` (→WALCL), the
China _tab_ (`china.pboc`, `china.cn10y`), and every macro block — but the **global
index legs (all 47 M2 + FX, including CN M2) are not individually source-gated.**
So the manually-maintained CN leg is invisible to the `--gate` that protects every
other number on the dashboard. If the hand-entered value were wrong or stale, the
gate would not catch it.

Separately, a fail-safe caveat (not China-specific, but relevant to the brief's
"no degraded build overwrites good data" rule): the workflow's commit step is
`if: always()`, so a `--gate` failure turns the run red **but still commits**. This
is a deliberate "always tell the truth" choice (it ships the honest stale-freshness
stamp), but it differs from EA's `compute_exit_code` which _blocks_ the commit.
Worth a conscious confirm: is red-but-committed the intended contract for TEC, or
should a `BEHIND`/`MISSING` gate failure block the commit the way EA's does?

## 6. Proposed automation — the one category-(c) item

**Demote `CHINA_M2_OVERRIDE` from a data source to an auto-expiring backstop.**

Design (no folder restructure; fits TEC's flat shape and EA's discipline):

1. **Feed-first.** The CN leg already reads `ECONOMICS:CNM2`. Keep that as the
   primary. Change the override semantics so it **only contributes months the feed
   does not yet carry** (i.e. apply override month `m` only if `m` is newer than
   the feed's latest, instead of unconditionally overwriting).
2. **Auto-expire.** On each run, drop override months the feed has caught up to
   (feed's value for that month present and within tolerance). This makes the dict
   self-cleaning: in the common case it empties itself and there's nothing to
   maintain. (Could be a printed "you can delete these override months" hint
   rather than self-editing source, to keep the diff human-reviewed — to decide.)
3. **Source-gate the leg.** Add `("series","cn_m2")` (or a dedicated probe) to
   `verify_data.build_registry()` so the CN M2 leg gets the same `BEHIND/MISSING`
   source comparison as everything else — closing the §5 gap. The override is then
   "stale" only when **both** the feed and the override trail the expected PBoC
   release, replacing the pure calendar heuristic with source truth.
4. **Keep the manual escape hatch.** The dict stays as the one sanctioned override
   for genuine feed-lag windows — but it stops being a standing monthly chore.

Net effect: the "~30 seconds/month, every month" task becomes "touch it only in the
rare month TradingView's China feed actually lags," and even then the dashboard
gate (not a human's memory) is what flags the need.

**Nothing else is category (c).** No further fetchers are warranted by this audit.

## 7. Open decisions for Raoul (before any code)

1. **Override semantics:** self-cleaning (pipeline drops caught-up months from the
   dict automatically) vs. advisory (pipeline only _prints_ which months are now
   redundant; human deletes). Self-cleaning is less work; advisory keeps every
   data-shaping change in a human-reviewed diff.
2. **Commit gate (§5):** leave `if: always()` (red-but-committed, honest stamp) or
   move to EA-style block-the-commit on `BEHIND`/`MISSING`. Affects more than
   China, so flagging rather than assuming.
3. **Scope confirm:** is this strictly the China M2 automation (recommended — it's
   the only category-(c) item), or do you also want the §5 gate change generalised
   to add per-leg source verification for the whole global index?
