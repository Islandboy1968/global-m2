#!/usr/bin/env python3
"""
China — PBoC balance sheet & China rates, server-side from TradingView.

Written into data.js as TGL_DATA["china"]. China's liquidity and rates are a
primary global-cycle driver MIT tracks: the PBoC's total assets (a balance-sheet
liquidity proxy) and the China 10y government bond yield. The exact TradingView /
ECONOMICS / FRED symbol codes for the PBoC balance sheet are not uniformly
documented, so each series carries a list of CANDIDATE symbols; the builder tries
them in order and keeps the first with usable history (logging which one won).
Monthly resolution. Each pull is independent and fail-safe: a missing series nulls
only itself and logs a line — the PBoC series in particular is uncertain.

Series (key -> candidate symbols, transform):
  pboc   ECONOMICS:CNCBBS / FRED:HKMBINTDM / ECONOMICS:CNBSA   PBoC total assets (level; uncertain)
  cn10y  TVC:CN10Y / ECONOMICS:CNIRYY                          China 10y yield  (level %)
"""
from series_util import iso, pull_first

BARS = 470   # monthly history
MIN_PTS = 24

# key: candidate_symbols  (all levels)
CHINA_SERIES = {
    "pboc":  ["ECONOMICS:CNCBBS", "FRED:HKMBINTDM", "ECONOMICS:CNBSA"],
    "cn10y": ["TVC:CN10Y", "ECONOMICS:CNIRYY"],
}


def build_china(bars=BARS):
    """Return the TGL_DATA['china'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, candidates in CHINA_SERIES.items():
        try:
            sym, pts = pull_first(candidates, bars=bars, min_pts=MIN_PTS)
            arr = [{"d": iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
            out[key] = arr or None
            if arr:
                print(f"  china/{key:6s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  china/{key:6s}: NULL")
        except Exception as e:
            out[key] = None
            print(f"  china/{key:6s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_china().items():
        print(f"{k:7s}: {len(arr) if arr else 0} pts")
