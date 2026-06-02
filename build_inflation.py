#!/usr/bin/env python3
"""
Inflation — the MIT inflation dashboard, server-side from FRED (via TradingView).

Written into data.js as TGL_DATA["infl"]. The MIT inflation playbook in chart form:
the "Inflation Dominoes" (commodity -> goods -> services sequencing), the second
derivative of CPI (the Macro-Seasons inflation axis), the ex-shelter "real-time"
read (shelter is the super-lagging caboose), and market inflation expectations.
All series are free FRED data pulled directly from FRED's public CSV endpoint
(fred.fred_series) — no API key, and no dependence on TradingView's partial
FRED mirror.

Raw FRED series (monthly, seasonally adjusted index unless noted):
  CPIAUCSL          headline CPI            -> YoY %  (headline_yoy) + 12m accel (accel)
  CPILFESL          core CPI (ex food/enrg) -> YoY %  (core_yoy)
  CUSR0000SACL1E    core goods              -> YoY %  (goods_yoy)
  CUSR0000SASLE     core services           -> YoY %  (services_yoy)
  CUSR0000SA0L2     CPI less shelter        -> YoY %  (exshelter_yoy)
  T10YIE            10y breakeven inflation -> level %  (be10)
  MICH              UMich 1y inflation exp. -> level %  (umich)

Each pull is independent and fail-safe: a missing series nulls only itself. The
'accel' series (CPI YoY second derivative) is derived from headline_yoy as the
12-month change in the year-on-year rate.
"""
import datetime as dt
from fred import fred_series

# key: (FRED series id, needs_yoy)
INFL_SERIES = {
    "headline_yoy":  ("CPIAUCSL",       True),
    "core_yoy":      ("CPILFESL",       True),
    "goods_yoy":     ("CUSR0000SACL1E", True),
    "services_yoy":  ("CUSR0000SASLE",  True),
    "exshelter_yoy": ("CUSR0000SA0L2",  True),
    "be10":          ("T10YIE",         False),
    "umich":         ("MICH",           False),
}


def _iso(t):
    return dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m-%d")


def _ym(t):
    d = dt.datetime.utcfromtimestamp(int(t)).date()
    return f"{d.year:04d}-{d.month:02d}"


def _to_yoy(points):
    """points: list[(epoch, level)] -> list[(epoch, yoy_pct)] matching the same
    month one year earlier. Robust to gaps; drops points without a year-ago peer."""
    by_ym = {}
    for t, v in points:
        by_ym[_ym(t)] = (t, v)
    out = []
    for ym, (t, v) in sorted(by_ym.items()):
        y, m = map(int, ym.split("-"))
        prev = f"{y - 1:04d}-{m:02d}"
        if prev in by_ym and by_ym[prev][1]:
            out.append((t, (v / by_ym[prev][1] - 1) * 100))
    return out


def _accel(yoy_arr):
    """12-month change in the YoY rate — the 'second derivative of CPI' that MIT
    uses as the Macro-Seasons inflation axis. yoy_arr: [{d, v}] -> [{d, v}]."""
    by_ym = {r["d"][:7]: r["v"] for r in yoy_arr}
    out = []
    for r in yoy_arr:
        y, m = map(int, r["d"][:7].split("-"))
        prev = f"{y - 1:04d}-{m:02d}"
        if prev in by_ym:
            out.append({"d": r["d"], "v": round(r["v"] - by_ym[prev], 2)})
    return out


def build_inflation():
    """Return the TGL_DATA['infl'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (sym, needs_yoy) in INFL_SERIES.items():
        try:
            pts = fred_series(sym)
            if needs_yoy:
                pts = _to_yoy(pts)
            arr = [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)]
            out[key] = arr or None
            if arr:
                print(f"  infl/{key:13s}: {len(arr):4d} pts | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  infl/{key:13s}: EMPTY")
        except Exception as e:
            out[key] = None
            print(f"  infl/{key:13s} FAILED:", str(e)[:80])
    # derived: CPI YoY second derivative (acceleration)
    try:
        out["accel"] = _accel(out["headline_yoy"]) if out.get("headline_yoy") else None
        if out["accel"]:
            print(f"  infl/{'accel':13s}: {len(out['accel'])} pts (last {out['accel'][-1]['v']})")
    except Exception as e:
        out["accel"] = None
        print("  infl/accel FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_inflation().items():
        print(f"{k:14s}: {len(arr) if arr else 0} pts")
