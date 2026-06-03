#!/usr/bin/env python3
"""
The Big Picture — long-horizon structural macro series, server-side from FRED.

Written into data.js as TGL_DATA["big"]. Low-velocity series (monthly/quarterly/
annual), all from FRED's KEYLESS csv endpoint, reusing the fetch helper in
us_liquidity.py so there is no API key and no browser CORS.

Series:
  lfpr     CIVPART          Labor Force Participation Rate, %, monthly
  births   SPDYNCBRTINUSA   Birth rate, crude, per 1,000 people, annual (World Bank)
  debt     GFDEGDQ188S      Federal Debt: Total Public Debt as % of GDP, quarterly
  interest A091RC1Q027SBEA  Federal current expenditures: interest payments, $bn, quarterly
  y5       DGS5             Market Yield on US Treasury at 5-Year Constant Maturity, %, daily

The dashboard pairs these with the US Total Liquidity (Narrow) series already in
TGL_DATA["us"], so no liquidity series is duplicated here.
"""
from us_liquidity import _fetch

BIG_SERIES = {
    "lfpr":     "CIVPART",
    "births":   "SPDYNCBRTINUSA",
    "debt":     "GFDEGDQ188S",
    "interest": "A091RC1Q027SBEA",
    "y5":       "DGS5",
}

START = "1948-01-01"   # full history; the frontend windows it


def build_big(start=START):
    """Return the TGL_DATA['big'] block: {key: [{d, v}, ...]} sorted by date.

    Per-series tolerant: a transient FRED timeout on one series (e.g. DGS5) must
    not blank the whole tab — the failed series comes back empty and the others
    still render. update_data.py then carries forward any empty series from the
    last good build."""
    out = {}
    for key, sid in BIG_SERIES.items():
        try:
            m = _fetch(sid, start=start)
            out[key] = [{"d": d, "v": round(v, 4)} for d, v in sorted(m.items())]
        except Exception as e:
            print(f"  BIG {key} ({sid}) failed: {str(e)[:90]}")
            out[key] = []
    return out


if __name__ == "__main__":
    big = build_big()
    for k, arr in big.items():
        print(f"{k:9s}: {len(arr):4d} pts | {arr[0]['d']} -> {arr[-1]['d']} "
              f"(last {arr[-1]['v']})")
