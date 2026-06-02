#!/usr/bin/env python3
"""
Global Leading Edge — export & semis-proxy growth barometers, server-side from TradingView.

Written into data.js as TGL_DATA["exp"]. These are the "first mover" series MIT
tracks to front-run the ISM: small, open, export-led economies (South Korea,
Taiwan, Sweden) plus the compute/semiconductor cycle. Per GMI, Taiwan export
orders and global semiconductor sales are "effectively the same chart", so
Taiwan exports stand in as the tradable semis proxy (clean global semiconductor
billings are not available on the public feeds). Each series is paired on the
dashboard against the ISM held in TGL_DATA["cycle"]["ism"] (or the World
Manufacturing PMI), with an adjustable lead.

Series (key: symbol, resolution, transform):
  twexp_yy   ECONOMICS:TWEXPYY  Taiwan Exports YoY %, monthly        (semis proxy anchor)
  krexp_yy   ECONOMICS:KREXPYY  South Korea Exports YoY %, monthly
  jpmto_yy   ECONOMICS:JPMTO    Japan Machine Tool Orders, monthly  -> YoY %
  sweden_pmi ECONOMICS:SEMPMI   Sweden Manufacturing PMI, monthly    (diffusion index)
  world_pmi  ECONOMICS:WWMPMI   World Manufacturing PMI, monthly     (diffusion index)

The *_yy ECONOMICS series are published already as year-on-year %, so they are
emitted as-is. Level series (machine tool orders) are converted to YoY here by
matching the same calendar month one year prior. Each pull is independent and
fail-safe: a missing/renamed symbol nulls only its own series, never the block.
"""
import datetime as dt
from tv_pull import pull_series

BARS = 400   # monthly: ~33y; the frontend windows it

# key: (symbol, resolution, needs_yoy)
EXP_SERIES = {
    "twexp_yy":   ("ECONOMICS:TWEXPYY", "1M", False),  # already YoY %  (semis proxy)
    "krexp_yy":   ("ECONOMICS:KREXPYY", "1M", False),  # already YoY %
    "jpmto_yy":   ("ECONOMICS:JPMTO",   "1M", True),   # level -> YoY %
    "sweden_pmi": ("ECONOMICS:SEMPMI",  "1M", False),  # diffusion index (level)
    "world_pmi":  ("ECONOMICS:WWMPMI",  "1M", False),  # diffusion index (level)
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


def build_exports(bars=BARS):
    """Return the TGL_DATA['exp'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (sym, res, needs_yoy) in EXP_SERIES.items():
        try:
            pts = pull_series(sym, res, bars)
            if needs_yoy:
                pts = _to_yoy(pts)
            arr = [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)]
            out[key] = arr or None
            if arr:
                print(f"  exp/{key:10s}: {len(arr):4d} pts | {arr[0]['d']} -> "
                      f"{arr[-1]['d']} (last {arr[-1]['v']})")
            else:
                print(f"  exp/{key:10s}: EMPTY")
        except Exception as e:
            out[key] = None
            print(f"  exp/{key:10s} FAILED:", str(e)[:80])
    return out


if __name__ == "__main__":
    for k, arr in build_exports().items():
        n = len(arr) if arr else 0
        print(f"{k:10s}: {n} pts")
