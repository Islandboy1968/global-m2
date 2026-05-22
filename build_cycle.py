#!/usr/bin/env python3
"""
The Business Cycle — ISM survey series, server-side from TradingView.

Written into data.js as TGL_DATA["cycle"]. Monthly series pulled from
TradingView's ECONOMICS feed (no API key), reusing pull_series in tv_pull.py.
FRED no longer carries the ISM series (ISM asserts copyright; the old NAPM*
series were discontinued), so TradingView is the source here.

Series:
  ism        ECONOMICS:USBCOI   ISM Manufacturing PMI (PMI composite), monthly
  neworders  ECONOMICS:USMNO    ISM Manufacturing New Orders index, monthly

The dashboard pairs ISM with the GMI Total Liquidity Index YoY already held in
TGL_DATA["series"] (forward-shifted ~6 months in the UI), so no liquidity series
is duplicated here.
"""
import datetime as dt
from tv_pull import pull_series

CYCLE_SERIES = {
    "ism":       "ECONOMICS:USBCOI",
    "neworders": "ECONOMICS:USMNO",
}

BARS = 400   # ~33 years of monthly history; the frontend windows it


def build_cycle(bars=BARS):
    """Return the TGL_DATA['cycle'] block: {key: [{d, v}, ...]} sorted by date."""
    out = {}
    for key, sym in CYCLE_SERIES.items():
        pts = pull_series(sym, "1M", bars)
        out[key] = [{"d": dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m-%d"),
                     "v": round(v, 2)}
                    for t, v in sorted(pts)]
    return out


if __name__ == "__main__":
    cyc = build_cycle()
    for k, arr in cyc.items():
        print(f"{k:10s}: {len(arr):4d} pts | {arr[0]['d']} -> {arr[-1]['d']} "
              f"(last {arr[-1]['v']})")
