#!/usr/bin/env python3
"""
Housing — the interest-rate-sensitive housing barometers, server-side from TradingView.

Written into data.js as TGL_DATA["housing"]. Housing is the most rate-sensitive
part of the cycle, so MIT watches the 30y mortgage rate (level), the homebuilder
ETF (XHB, the market's forward read), building permits (the leading construction
signal, YoY) and new home sales (YoY). Mortgage/permits/new sales are free FRED
data via TradingView's FRED passthrough (FRED's own CSV endpoint 403s bots); XHB
is a TradingView ETF price. Monthly resolution. Each pull is independent and
fail-safe: a missing series nulls only itself and logs a line.

Series (key -> symbol, transform):
  mortgage      FRED:MORTGAGE30US   30y mortgage rate   (level %)
  xhb           AMEX:XHB            homebuilder ETF     (level, price)
  permits_yoy   FRED:PERMIT         building permits    -> YoY %
  newsales_yoy  FRED:HSN1F          new home sales      -> YoY %
"""
from series_util import iso, to_yoy, pull_first

BARS = 470   # monthly history
MIN_PTS = 24

# key: (candidate_symbols, needs_yoy)
HOUSING_SERIES = {
    "mortgage":     (["FRED:MORTGAGE30US"], False),
    "xhb":          (["AMEX:XHB"],          False),
    "permits_yoy":  (["FRED:PERMIT"],       True),
    "newsales_yoy": (["FRED:HSN1F"],        True),
}


def build_housing(bars=BARS):
    """Return the TGL_DATA['housing'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (candidates, needs_yoy) in HOUSING_SERIES.items():
        try:
            sym, pts = pull_first(candidates, bars=bars, min_pts=MIN_PTS)
            if needs_yoy:
                pts = to_yoy(pts)
            arr = [{"d": iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
            out[key] = arr or None
            if arr:
                print(f"  housing/{key:12s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  housing/{key:12s}: NULL")
        except Exception as e:
            out[key] = None
            print(f"  housing/{key:12s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_housing().items():
        print(f"{k:13s}: {len(arr) if arr else 0} pts")
