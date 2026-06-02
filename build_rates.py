#!/usr/bin/env python3
"""
Rates — rates, energy and dollar barometers, server-side from TradingView.

Written into data.js as TGL_DATA["rates"]. The reflexive macro trio MIT tracks:
the 10y yield momentum (YoY change in the yield, z-scored to make regime shifts
legible), crude oil YoY (the inflation/growth impulse), and the dollar index
(level). Monthly resolution. Each pull is independent and fail-safe: a missing
series nulls only itself and logs a line.

Series (key -> candidate symbols, transform):
  y10_yoy_z  TVC:US10Y / FRED:DGS10   10y yield -> YoY change (pts) -> z-score
  oil_yoy    TVC:USOIL / TVC:UKOIL    crude     -> YoY %
  dxy        TVC:DXY                  dollar index (level)
"""
from series_util import iso, to_yoy, to_yoy_diff, zscore_pts, pull_first

BARS = 470   # monthly history
MIN_PTS = 24

# key: (candidate_symbols, transform)  where transform in
#   "yoy_diff_z" | "yoy" | "level"
RATES_SERIES = {
    "y10_yoy_z": (["TVC:US10Y", "FRED:DGS10"], "yoy_diff_z"),
    "oil_yoy":   (["TVC:USOIL", "TVC:UKOIL"],  "yoy"),
    "dxy":       (["TVC:DXY"],                 "level"),
}


def build_rates(bars=BARS):
    """Return the TGL_DATA['rates'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (candidates, transform) in RATES_SERIES.items():
        try:
            sym, pts = pull_first(candidates, bars=bars, min_pts=MIN_PTS)
            if transform == "yoy_diff_z":
                pts = zscore_pts(to_yoy_diff(pts))
            elif transform == "yoy":
                pts = to_yoy(pts)
            arr = [{"d": iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
            out[key] = arr or None
            if arr:
                print(f"  rates/{key:10s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  rates/{key:10s}: NULL")
        except Exception as e:
            out[key] = None
            print(f"  rates/{key:10s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_rates().items():
        print(f"{k:11s}: {len(arr) if arr else 0} pts")
