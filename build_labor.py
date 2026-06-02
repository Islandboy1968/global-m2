#!/usr/bin/env python3
"""
Labor — labor-market barometers, server-side from FRED (via TradingView).

Written into data.js as TGL_DATA["labor"]. The cyclical labor read MIT watches:
the unemployment rate (level), overtime and temp-help as leading second-derivative
employment signals (YoY), JOLTS hires (level), and initial jobless claims (level).
All series are free FRED data pulled through TradingView's FRED passthrough
(pull_series with a "FRED:" symbol; FRED's own CSV endpoint 403s bots). Monthly
resolution. Each pull is independent and fail-safe: a missing series nulls only
itself and logs a line.

Series (key -> symbol, transform):
  unrate    FRED:UNRATE     unemployment rate       (level %)
  ot_yoy    FRED:AWOTMAN    avg weekly overtime hrs  -> YoY %
  temp_yoy  FRED:TEMPHELPS  temporary help services  -> YoY %
  jolts     FRED:JTSHIL     JOLTS hires             (level, thousands)
  claims    FRED:ICSA       initial jobless claims  (level)
"""
from series_util import iso, to_yoy, pull_first

BARS = 470   # monthly history
MIN_PTS = 24

# key: (candidate_symbols, needs_yoy)
LABOR_SERIES = {
    "unrate":   (["FRED:UNRATE"],     False),
    "ot_yoy":   (["FRED:AWOTMAN"],    True),
    "temp_yoy": (["FRED:TEMPHELPS"],  True),
    "jolts":    (["FRED:JTSHIL"],     False),
    "claims":   (["FRED:ICSA"],       False),
}


def build_labor(bars=BARS):
    """Return the TGL_DATA['labor'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (candidates, needs_yoy) in LABOR_SERIES.items():
        try:
            sym, pts = pull_first(candidates, bars=bars, min_pts=MIN_PTS)
            if needs_yoy:
                pts = to_yoy(pts)
            arr = [{"d": iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
            out[key] = arr or None
            if arr:
                print(f"  labor/{key:9s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  labor/{key:9s}: NULL")
        except Exception as e:
            out[key] = None
            print(f"  labor/{key:9s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_labor().items():
        print(f"{k:10s}: {len(arr) if arr else 0} pts")
