#!/usr/bin/env python3
"""
Credit — bank lending standards & demand, server-side from FRED (via TradingView).

Written into data.js as TGL_DATA["credit"]. From the Fed's Senior Loan Officer
Opinion Survey (SLOOS): the net % of banks tightening C&I lending standards and
the net % reporting stronger C&I loan demand. These are the credit-impulse
barometers MIT uses to read the supply/demand of bank credit ahead of the cycle.
Quarterly series pulled monthly ("1M") via TradingView's FRED passthrough (FRED's
own CSV endpoint 403s bots). Each pull is independent and fail-safe: a missing
series nulls only itself and logs a line.

Series (key -> candidate symbols, transform):
  ci_standards  FRED:DRTSCILM   net % tightening C&I standards  (level, quarterly)
  ci_demand     FRED:DRSDCIS    net % stronger C&I demand       (level)
"""
from series_util import iso, pull_first

BARS = 470   # monthly resolution over the full history (series itself is quarterly)
MIN_PTS = 24

# key: candidate_symbols  (all levels; net %)
CREDIT_SERIES = {
    "ci_standards": ["FRED:DRTSCILM", "FRED:DRTSCIS"],
    "ci_demand":    ["FRED:DRSDCILM", "FRED:DRSDCIS", "FRED:SUBLPDCISCT"],
}


def build_credit(bars=BARS):
    """Return the TGL_DATA['credit'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, candidates in CREDIT_SERIES.items():
        try:
            sym, pts = pull_first(candidates, bars=bars, min_pts=MIN_PTS)
            arr = [{"d": iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
            out[key] = arr or None
            if arr:
                print(f"  credit/{key:12s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  credit/{key:12s}: NULL")
        except Exception as e:
            out[key] = None
            print(f"  credit/{key:12s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_credit().items():
        print(f"{k:13s}: {len(arr) if arr else 0} pts")
