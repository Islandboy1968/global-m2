#!/usr/bin/env python3
"""
Data health + SOURCE-TRUTH verification for the dashboard data.

Two jobs:
  1. Report every tab/series: populated / MISSING, point count, date range, last value.
  2. Go to each series' ACTUAL SOURCE, read its latest observation, and compare to
     what we shipped — so "fresh" means "matches the source", not a guess about
     release calendars. Results are stamped back into data/data.{json,js} as
     per-series freshness {as_of, source_latest, status} and the dashboard badge
     reads them.

We deliberately keep NO hardcoded release schedule. The only calendar fact used is
"today", and we ignore the in-progress current month when deciding "behind" so a
partial current-month bar (e.g. a mid-June daily print bucketed monthly) never
false-flags a correctly up-to-date series.

The source registry is imported FROM THE BUILDERS themselves (same symbols,
resolutions and fallbacks), so it can't drift from what the pipeline fetches.

Statuses per series:
  IN_SYNC     shipped latest month >= source's latest complete month
  BEHIND      the source has a newer COMPLETE month than we shipped  (real problem)
  MISSING     the series is empty/null in the data                   (real problem)
  UNVERIFIED  could not reach the source this run (no opinion; not a failure)
  DERIVED     a computed series with no 1:1 raw source (reported, never gated)

Usage:
    python verify_data.py [path]          # report + stamp freshness, exit 0
    python verify_data.py --gate [path]   # same, but exit 1 if any BEHIND/MISSING
                                          # (DERIVED/UNVERIFIED never fail the gate)
"""
import json, sys, datetime as dt

from tv_pull import pull_series
from fred import fred_series
from us_liquidity import _fetch as fred_fetch
from big_picture import BIG_SERIES
from build_cycle import CYCLE_SERIES
from build_exports import EXP_SERIES
from build_inflation import INFL_SERIES
from build_labor import LABOR_SERIES
from build_rates import RATES_SERIES
from build_housing import HOUSING_SERIES
from build_credit import CREDIT_SERIES
from build_china import CHINA_SERIES

PROBE_BARS = 60   # enough recent bars to read the latest observation quickly

# Human-readable labels, grouped by dashboard tab (also defines display order).
EXPECTED = {
    "Global Liquidity": {"series": "GMI Total Liquidity (daily)",
                         "btc": "Bitcoin price", "ndx": "Nasdaq 100 price"},
    "US Liquidity": {"us.series": "US net liquidity (weekly)"},
    "Big Picture": {"big.lfpr": "Labour force participation", "big.births": "Birth rate",
                    "big.debt": "Federal debt % GDP", "big.interest": "Interest payments",
                    "big.y5": "5y Treasury yield"},
    "Business Cycle": {"cycle.ism": "ISM PMI", "cycle.neworders": "ISM new orders",
                       "cycle.gdp": "GDP QoQ", "cycle.capex": "Capex % GDP",
                       "cycle.fci": "GMI FCI", "cycle.fci_exoil": "FCI ex-oil"},
    "Global Leading Edge": {"exp.twexp_yy": "Taiwan exports YoY (semis proxy)",
                            "exp.krexp_yy": "South Korea exports YoY",
                            "exp.jpmto_yy": "Japan machine tool orders YoY"},
    "Inflation": {"infl.headline_yoy": "Headline CPI YoY", "infl.core_yoy": "Core CPI YoY",
                  "infl.goods_yoy": "Core goods CPI YoY", "infl.services_yoy": "Core services CPI YoY",
                  "infl.exshelter_yoy": "CPI ex-shelter YoY", "infl.be10": "10y breakeven",
                  "infl.umich": "UMich 1y expectations", "infl.accel": "CPI 2nd derivative"},
    "Labor": {"labor.unrate": "Unemployment rate", "labor.ot_yoy": "Overtime hours YoY",
              "labor.temp_yoy": "Temp help YoY", "labor.jolts": "JOLTS hires",
              "labor.claims": "Initial jobless claims"},
    "Rates & Dollar": {"rates.y10_yoy_z": "10y yield YoY (z-score)", "rates.oil_yoy": "Oil YoY",
                       "rates.dxy": "US dollar (DXY)"},
    "Housing": {"housing.mortgage": "30y mortgage rate", "housing.xhb": "Homebuilders ETF",
                "housing.permits_yoy": "Building permits YoY", "housing.newsales_yoy": "New home sales YoY"},
    "Credit": {"credit.ci_standards": "C&I lending standards", "credit.ci_demand": "C&I loan demand"},
    "China": {"china.pboc": "PBoC balance sheet", "china.cn10y": "China 10y yield"},
}

# Series with no 1:1 raw source (computed/blended). Reported but never gated; we
# still probe a representative input so the report shows roughly how current it is.
DERIVED = {"cycle.capex", "cycle.capex_g", "cycle.fci", "cycle.fci_exoil", "infl.accel"}


def _ym_from_epoch(t):
    return dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m")


def _latest_complete_ym(months, current_ym):
    """Given a set of YYYY-MM strings, return the latest one that is NOT the
    in-progress current month (so a partial current-month bar is ignored). Falls
    back to the overall latest if the source only has the current month."""
    if not months:
        return None
    complete = [m for m in months if m < current_ym]
    return max(complete) if complete else max(months)


def _probe_tv(candidates, res, current_ym):
    """Latest COMPLETE observation month from the first working candidate via
    TradingView, falling back to FRED's CSV for FRED: codes. (sym, ym) or (None, None)."""
    for sym in candidates:
        try:
            pts = pull_series(sym, res, PROBE_BARS, retries=2)
            if pts:
                return sym, _latest_complete_ym({_ym_from_epoch(t) for t, _ in pts}, current_ym)
        except Exception:
            pass
        if sym.startswith("FRED:"):
            try:
                pts = fred_series(sym.split(":", 1)[1], retries=2, timeout=30)
                if pts:
                    return ("FRED-CSV:" + sym.split(":", 1)[1],
                            _latest_complete_ym({_ym_from_epoch(t) for t, _ in pts}, current_ym))
            except Exception:
                pass
    return None, None


def _probe_fred(series_id, current_ym):
    """Latest COMPLETE observation month for a bare FRED id via the dual-source fetch."""
    try:
        m = fred_fetch(series_id)
        if m:
            return series_id, _latest_complete_ym({d[:7] for d in m}, current_ym)
    except Exception:
        pass
    return None, None


def build_registry():
    """(block, leaf) -> ('fred', id) | ('tv', [candidates], res). Imported from the
    builders so it stays in lockstep with what the pipeline actually fetches."""
    reg = {}
    reg[("us", "series")] = ("fred", "WALCL")          # weekly net-liquidity grid tracks WALCL
    for k, sid in BIG_SERIES.items():
        reg[("big", k)] = ("fred", sid)
    for k, (sym, res) in CYCLE_SERIES.items():
        reg[("cycle", k)] = ("tv", [sym], res)
    reg[("cycle", "capex")] = ("tv", ["FRED:PNFI"], "3M")     # derived input
    reg[("cycle", "capex_g")] = ("tv", ["FRED:PNFI"], "3M")   # derived input
    reg[("cycle", "fci")] = ("tv", ["ECONOMICS:USBCOI"], "1M")     # built from ISM
    reg[("cycle", "fci_exoil")] = ("tv", ["ECONOMICS:USBCOI"], "1M")
    for k, (cands, res, _y) in EXP_SERIES.items():
        reg[("exp", k)] = ("tv", cands, res)
    for k, (cands, _y) in INFL_SERIES.items():
        reg[("infl", k)] = ("tv", cands, "1M")
    reg[("infl", "accel")] = ("tv", ["FRED:CPIAUCSL"], "1M")  # derived from headline
    for k, (cands, _y) in LABOR_SERIES.items():
        reg[("labor", k)] = ("tv", cands, "1M")
    for k, (cands, _t) in RATES_SERIES.items():
        reg[("rates", k)] = ("tv", cands, "1M")
    for k, (cands, _y) in HOUSING_SERIES.items():
        reg[("housing", k)] = ("tv", cands, "1M")
    for k, cands in CREDIT_SERIES.items():
        reg[("credit", k)] = ("tv", cands, "1M")
    for k, cands in CHINA_SERIES.items():
        reg[("china", k)] = ("tv", cands, "1M")
    return reg


def _dig(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _shipped_latest(data, jp):
    """Latest observation date string for a dotted json path, or None if empty."""
    v = _dig(data, jp)
    if isinstance(v, list) and v and isinstance(v[-1], dict):
        return v[-1].get("d")
    return None


def verify_against_source(data, current_ym):
    """Probe every registered series at its source and classify it. Returns
    {block: {leaf: {as_of, source, source_latest, status}}}."""
    reg = build_registry()
    results = {}
    for (block, leaf), spec in reg.items():
        jp = f"{block}.{leaf}"   # every registered leaf is nested (incl. us.series)
        shipped = _shipped_latest(data, jp)
        is_derived = jp in DERIVED

        if shipped is None:
            status, src, src_ym = "MISSING", None, None
        else:
            if spec[0] == "fred":
                src, src_ym = _probe_fred(spec[1], current_ym)
            else:
                src, src_ym = _probe_tv(spec[1], spec[2], current_ym)
            if src_ym is None:
                status = "UNVERIFIED"
            elif src_ym > shipped[:7]:
                status = "DERIVED" if is_derived else "BEHIND"
            else:
                status = "IN_SYNC"
        results.setdefault(block, {})[leaf] = {
            "as_of": shipped, "source": src, "source_latest": src_ym, "status": status,
        }
    return results


_RANK = {"BEHIND": 4, "MISSING": 5, "UNVERIFIED": 2, "DERIVED": 1, "IN_SYNC": 0}


def stamp_freshness(data, results):
    """Merge per-series source verdicts into data['freshness'] and set a block-level
    status (worst leaf). Preserves the carry-forward 'stale' flag set by update_data."""
    fr = data.setdefault("freshness", {})
    checked = dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    for block, leaves in results.items():
        blk = fr.setdefault(block, {})
        series = blk.setdefault("series", {})
        # series may currently hold {leaf: date_str} from update_data; upgrade to dicts.
        for leaf, verdict in leaves.items():
            series[leaf] = verdict
        worst = max((v["status"] for v in leaves.values()), key=lambda s: _RANK[s], default="IN_SYNC")
        # carry-forward (fetch failed) outranks a clean source comparison
        if blk.get("stale"):
            worst = "BEHIND" if worst in ("IN_SYNC", "DERIVED", "UNVERIFIED") else worst
        blk["status"] = worst
        blk["checked"] = checked
    return data


def print_report(data, results):
    print(f"=== TEC data health · {data.get('updated', '?')} · source-verified ===\n")
    counts = {"IN_SYNC": 0, "BEHIND": 0, "MISSING": 0, "UNVERIFIED": 0, "DERIVED": 0}
    problems = []
    for tab, series in EXPECTED.items():
        print(f"[{tab}]")
        for jp, label in series.items():
            block, leaf = (jp.split(".", 1) + [jp])[:2] if "." in jp else (jp, jp)
            v = (results.get(block, {}) or {}).get(leaf)
            shipped = _shipped_latest(data, jp)
            if v is None:  # btc/ndx and any series not in the source registry
                tag = "OK   " if shipped else "EMPTY"
                print(f"  {tag:11s} {jp:24s} shipped={shipped}  (no source probe)  ({label})")
                continue
            st = v["status"]; counts[st] = counts.get(st, 0) + 1
            line = (f"  {st:11s} {jp:24s} shipped={v['as_of']}  source={v['source_latest']}"
                    f"  via {v['source']}  ({label})")
            print(line)
            if st in ("BEHIND", "MISSING"):
                problems.append(f"{jp}: {st} (shipped {v['as_of']}, source {v['source_latest']})")
        print()
    print("=== " + " · ".join(f"{k} {n}" for k, n in counts.items()) + " ===")
    if problems:
        print("\nPROBLEMS (gated):")
        for p in problems:
            print("  - " + p)
    return problems


def main():
    args = [a for a in sys.argv[1:] if a != "--gate"]
    gate = "--gate" in sys.argv
    path = args[0] if args else "data/data.json"
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"FATAL: cannot read {path}: {e}")
        return 1

    current_ym = dt.datetime.utcnow().strftime("%Y-%m")
    results = verify_against_source(data, current_ym)
    problems = print_report(data, results)
    stamp_freshness(data, results)

    # Persist the enriched freshness so the dashboard badge reflects source truth.
    import os
    json.dump(data, open(path, "w"), default=str)
    js = os.path.join(os.path.dirname(path) or ".", "data.js")
    try:
        with open(js, "w") as f:
            f.write("window.TGL_DATA = " + json.dumps(data, default=str) + ";")
    except Exception as e:
        print(f"  (could not rewrite {js}: {e})")

    if gate and problems:
        print(f"\nGATE: FAIL — {len(problems)} series behind source or missing.")
        return 1
    if gate:
        print("\nGATE: PASS — every probed series matches its source (or is unverifiable).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
