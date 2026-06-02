#!/usr/bin/env python3
"""
Data health check — verifies the generated dashboard data and prints a per-tab,
per-series report (populated / NULL, point count, date range, last value).

Usage:
    python verify_data.py [path/to/data.json]   # default: data/data.json

Always exits 0 (it is a *report*, not a gate) unless the file is unreadable, so
it can run as a non-failing step in the pipeline or be invoked ad-hoc after a
run to confirm every tab's data actually landed. Series that are expected but
NULL/empty are flagged with "MISSING" so a broken feed is obvious at a glance.
"""
import json, sys, datetime as dt

# bucket -> list of (json_path, label). json_path is dotted; "[]" means "a list
# of {d,v} records under this key". For nested series buckets we check key lists.
EXPECTED = {
    "Global Liquidity": {
        "series": "GMI Total Liquidity (daily)",
        "btc": "Bitcoin price",
        "ndx": "Nasdaq 100 price",
    },
    "US Liquidity": {
        "us.series": "US net liquidity (weekly)",
    },
    "Big Picture": {
        "big.lfpr": "Labour force participation",
        "big.births": "Birth rate",
        "big.debt": "Federal debt % GDP",
        "big.interest": "Interest payments",
        "big.y5": "5y Treasury yield",
    },
    "Business Cycle": {
        "cycle.ism": "ISM PMI",
        "cycle.neworders": "ISM new orders",
        "cycle.gdp": "GDP QoQ",
        "cycle.capex": "Capex % GDP",
        "cycle.fci": "GMI FCI",
        "cycle.fci_exoil": "FCI ex-oil",
    },
    "Global Leading Edge": {
        "exp.twexp_yy": "Taiwan exports YoY (semis proxy)",
        "exp.krexp_yy": "South Korea exports YoY",
        "exp.jpmto_yy": "Japan machine tool orders YoY",
        "pmi.world_pmi": "World mfg PMI (Bloomberg seed)",
    },
    "Inflation": {
        "infl.headline_yoy": "Headline CPI YoY",
        "infl.core_yoy": "Core CPI YoY",
        "infl.goods_yoy": "Core goods CPI YoY",
        "infl.services_yoy": "Core services CPI YoY",
        "infl.exshelter_yoy": "CPI ex-shelter YoY",
        "infl.be10": "10y breakeven",
        "infl.umich": "UMich 1y expectations",
        "infl.accel": "CPI 2nd derivative",
    },
    "Labor": {
        "labor.unrate": "Unemployment rate",
        "labor.ot_yoy": "Overtime hours YoY",
        "labor.temp_yoy": "Temp help YoY",
        "labor.jolts": "JOLTS hires",
        "labor.claims": "Initial jobless claims",
    },
    "Rates & Dollar": {
        "rates.y10_yoy_z": "10y yield YoY (z-score)",
        "rates.oil_yoy": "Oil YoY",
        "rates.dxy": "US dollar (DXY)",
    },
    "Housing": {
        "housing.mortgage": "30y mortgage rate",
        "housing.xhb": "Homebuilders ETF",
        "housing.permits_yoy": "Building permits YoY",
        "housing.newsales_yoy": "New home sales YoY",
    },
    "Credit": {
        "credit.ci_standards": "C&I lending standards",
        "credit.ci_demand": "C&I loan demand",
    },
    "China": {
        "china.pboc": "PBoC balance sheet",
        "china.cn10y": "China 10y yield",
    },
}


def _dig(data, path):
    cur = data
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else "data/data.json"
    try:
        data = json.load(open(path))
    except Exception as e:
        print(f"FATAL: cannot read {path}: {e}")
        return 1

    print(f"=== TEC data health · {data.get('updated', '?')} · {path} ===\n")
    total_ok = total_missing = 0
    missing_list = []
    for tab, series in EXPECTED.items():
        print(f"[{tab}]")
        for jp, label in series.items():
            v = _dig(data, jp)
            if isinstance(v, list) and v:
                first = v[0].get("d", "?") if isinstance(v[0], dict) else "?"
                last = v[-1].get("d", "?") if isinstance(v[-1], dict) else "?"
                lastv = v[-1].get("v", "?") if isinstance(v[-1], dict) else "?"
                print(f"  OK      {jp:24s} {len(v):>5} pts  {first}->{last}  last={lastv}  ({label})")
                total_ok += 1
            else:
                print(f"  MISSING {jp:24s}    --  ({label})")
                total_missing += 1
                missing_list.append(jp)
        print()
    print(f"=== {total_ok} OK · {total_missing} MISSING ===")
    if missing_list:
        print("MISSING: " + ", ".join(missing_list))
    return 0


if __name__ == "__main__":
    sys.exit(main())
