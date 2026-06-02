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

Series (key -> candidate symbols, resolution, transform):
  twexp_yy   Taiwan Exports YoY %, monthly        (semis proxy anchor)
  krexp_yy   South Korea Exports, monthly -> YoY %
  jpmto_yy   Japan Machine Tool Orders, monthly  -> YoY %
  oecd_cli   OECD Composite Leading Indicator, monthly (free global growth lead, FRED)

The TradingView ECONOMICS symbol codes for some series are not uniformly
documented, so each series carries a list of CANDIDATE symbols; the builder
tries them in order and keeps the first that returns usable history (logging
which one won). The *_yy ECONOMICS series are published already as year-on-year
%; level series are converted to YoY here by matching the same calendar month
one year prior. Each pull is independent and fail-safe.
"""
import datetime as dt
import time
from tv_pull import pull_series

BARS = 400   # monthly: ~33y; the frontend windows it
MIN_PTS = 24  # a candidate must return at least this many points to be accepted

# key: (candidate_symbols, resolution, needs_yoy)
EXP_SERIES = {
    "twexp_yy": (["ECONOMICS:TWEXPYY"], "1M", False),  # already YoY %  (semis proxy)
    "krexp_yy": (["ECONOMICS:KREXP"],   "1M", True),   # level -> YoY %
    "jpmto_yy": (["ECONOMICS:JPMTO"],   "1M", True),   # level -> YoY %
}

# OECD Composite Leading Indicator — a free global growth lead, via TradingView's
# FRED passthrough (FRED's own CSV endpoint 403s bots). Sweden/World S&P-Global
# PMIs are paywalled, so the OECD CLI is the global cross-check. Try broad
# aggregates first; _pull_first applies a recency guard and falls through to the
# US CLI (confirmed available on TradingView) as a backstop.
OECD_CLI_CANDIDATES = [
    "FRED:G7LOLITONOSTSAM",     # G7, normalised
    "FRED:OECDLOLITOAASTSAM",   # OECD - Total, amplitude adjusted
    "FRED:G7LOLITOAASTSAM",     # G7, amplitude adjusted
    "FRED:USALOLITONOSTSAM",    # US, normalised — confirmed-available backstop
]


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


RECENT_SECS = 400 * 86400   # a candidate is "current" if its last point is within ~13 months

def _pull_first(candidates, res):
    """Try each candidate symbol; return (symbol, points). Prefer the first
    candidate that has >= MIN_PTS points AND is still being updated (last point
    within RECENT_SECS). If none are current, fall back to the first with enough
    points. Returns (None, []) if nothing usable."""
    now = time.time()
    fallback = (None, [])
    for sym in candidates:
        try:
            pts = pull_series(sym, res, BARS)
            if pts and len(pts) >= MIN_PTS:
                if not fallback[1]:
                    fallback = (sym, pts)
                last_t = max(t for t, _ in pts)
                if now - last_t <= RECENT_SECS:
                    return sym, pts
                print(f"    {sym}: {len(pts)} pts but stale "
                      f"(last {time.strftime('%Y-%m', time.gmtime(last_t))}), trying next")
            else:
                print(f"    {sym}: only {len(pts) if pts else 0} pts, trying next")
        except Exception as e:
            print(f"    {sym}: {str(e)[:60]}")
    return fallback


def build_exports(bars=BARS):
    """Return the TGL_DATA['exp'] block: {key: [{d, v}, ...] or None}."""
    out = {}
    for key, (candidates, res, needs_yoy) in EXP_SERIES.items():
        sym, pts = _pull_first(candidates, res)
        if not pts:
            out[key] = None
            print(f"  exp/{key:10s}: NULL (no candidate returned data)")
            continue
        if needs_yoy:
            pts = _to_yoy(pts)
        arr = [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)]
        out[key] = arr or None
        if arr:
            print(f"  exp/{key:10s}: {len(arr):4d} pts via {sym} | {arr[0]['d']} -> "
                  f"{arr[-1]['d']} (last {arr[-1]['v']})")
        else:
            print(f"  exp/{key:10s}: EMPTY after transform ({sym})")

    # OECD CLI — via TradingView's FRED passthrough (candidate fallback + recency).
    # The OECD discontinued the old CLI vintage in 2024, so much of the free data
    # ends early-2024. Rather than show a 2-year-stale line on a "leads ISM" chart,
    # hide it (NULL) unless the chosen series is still current (last point <13mo old).
    sym, pts = _pull_first(OECD_CLI_CANDIDATES, "1M")
    arr = [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)] if pts else None
    if arr and (time.time() - max(t for t, _ in pts)) > 400 * 86400:
        print(f"  exp/{'oecd_cli':10s}: STALE via {sym} (ends {arr[-1]['d']}) — hiding")
        arr = None
    out["oecd_cli"] = arr
    if arr:
        print(f"  exp/{'oecd_cli':10s}: {len(arr):4d} pts via {sym} | "
              f"{arr[0]['d']} -> {arr[-1]['d']} (last {arr[-1]['v']})")
    elif not pts:
        print(f"  exp/{'oecd_cli':10s}: NULL (no candidate returned data)")
    return out


if __name__ == "__main__":
    for k, arr in build_exports().items():
        n = len(arr) if arr else 0
        print(f"{k:10s}: {n} pts")
