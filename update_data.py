#!/usr/bin/env python3
"""
Total Global Liquidity (TGL) Index — daily data pipeline.

Broad money across 47 economies, each valued in USD at spot FX and summed
(the GMI method). National M2 prints monthly; FX moves daily, so the index
is built on a DAILY calendar grid: M2 forward-filled between monthly prints,
FX forward-filled from its daily series (the latest daily point is spot).

Sources (public, no API key): TradingView ECONOMICS (M2) + TradingView FX.
Writes data/data.json and data/data.js for the dashboard.
"""
import json, os, time, datetime as dt
from concurrent.futures import ThreadPoolExecutor, as_completed
from tv_pull import pull_series
from econ import ECON
from us_liquidity import build_us
from big_picture import build_big

HERE = os.path.dirname(os.path.abspath(__file__))
M2_CACHE = os.path.join(HERE, "series_cache.json")
FX_CACHE = os.path.join(HERE, "fx_daily_cache.json")
START = dt.date(2010, 1, 1)
M2_BARS = 220     # monthly, ~18yr
FX_BARS = 6200    # daily, ~17yr

# China's TradingView M2 lags ~1 month; override with latest official PBoC prints (yuan).
CHINA_M2_OVERRIDE = {"2026-03": 353.86e12, "2026-04": 353.04e12}

# Risk assets for the liquidity-leads overlay charts (symbol, daily bars)
ASSETS = {"btc": ("INDEX:BTCUSD", 4300), "ndx": ("NASDAQ:NDX", 6200)}

# ------------------------------------------------------------------ pulls
def pull_into(cache_path, symbols, resolution, bars):
    cache = json.load(open(cache_path)) if os.path.exists(cache_path) else {}
    todo = [s for s in symbols if s not in cache]
    if todo:
        print(f"  pulling {len(todo)} @ {resolution}")
        def g(s): return s, pull_series(s, resolution, bars)
        with ThreadPoolExecutor(max_workers=6) as ex:
            for i, f in enumerate(as_completed([ex.submit(g, s) for s in todo]), 1):
                try:
                    s, d = f.result(); cache[s] = d
                except Exception as e:
                    print("   ERR", str(e)[:70])
                if i % 6 == 0: json.dump(cache, open(cache_path, "w"))
        json.dump(cache, open(cache_path, "w"))
    return cache

def get_data():
    m2_syms = sorted({t for t, f, c in ECON.values()})
    fx_syms = sorted({f for t, f, c in ECON.values() if f})
    m2c = pull_into(M2_CACHE, m2_syms, "1M", M2_BARS)
    fxc = pull_into(FX_CACHE, fx_syms, "1D", FX_BARS)
    # risk assets share the daily cache (with their own bar depth)
    for code, (sym, bars) in ASSETS.items():
        if sym not in fxc:
            try:
                fxc[sym] = pull_series(sym, "1D", bars)
            except Exception as e:
                print("  asset ERR", sym, str(e)[:60])
    json.dump(fxc, open(FX_CACHE, "w"))
    return m2c, fxc

# ------------------------------------------------------------------ build
def _backfill(out):
    """Fill leading None with the first available value (so a series that starts
    late contributes a constant before its data begins, avoiding step-jumps)."""
    first = next((v for v in out if v is not None), None)
    for i in range(len(out)):
        if out[i] is None: out[i] = first
        else: break
    return out

def sanitize_fx(points):
    """Drop bad FX prints (some illiquid TradingView pairs return inverted/garbage
    bars in early history). Most points are correct, so the median is trusted;
    keep only points within a wide 100x band around it."""
    vals = sorted(v for _, v in points if v not in (None, 0))
    if not vals:
        return points
    med = vals[len(vals)//2]
    lo, hi = med/100.0, med*100.0
    return [(t, v) for t, v in points if v not in (None, 0) and lo <= v <= hi]

def daily_ffill(points, grid):
    """points: list[(epoch, value)] -> value forward-filled onto calendar grid (list[date])."""
    points = sanitize_fx(points)
    pts = sorted((dt.datetime.utcfromtimestamp(int(t)).date(), v) for t, v in points)
    out = [None]*len(grid); j = 0; cur = None
    for i, day in enumerate(grid):
        while j < len(pts) and pts[j][0] <= day:
            cur = pts[j][1]; j += 1
        out[i] = cur
    return _backfill(out)

def monthly_ffill_by_day(points, grid, override=None):
    """Monthly series -> daily array (forward-fill by month)."""
    mp = {}
    for t, v in points:
        mp[dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m")] = v
    if override: mp.update(override)
    months = sorted(mp)
    # forward-fill across the month axis
    out = [None]*len(grid); cur = None; mi = 0
    ff = {}
    allm = sorted({d.strftime("%Y-%m") for d in grid} | set(mp))
    last = None
    for m in allm:
        if m in mp: last = mp[m]
        ff[m] = last
    for i, day in enumerate(grid):
        out[i] = ff.get(day.strftime("%Y-%m"))
    return _backfill(out)

def build():
    m2c, fxc = get_data()
    today = dt.datetime.utcnow().date()
    grid = [START + dt.timedelta(days=k) for k in range((today-START).days + 1)]

    # per-economy daily USD leg
    legs = {}
    for code, (m2t, fxs, ccy) in ECON.items():
        m2_arr = monthly_ffill_by_day(m2c[m2t], grid, CHINA_M2_OVERRIDE if code == "CN" else None)
        if fxs is None:
            fx_arr = [1.0]*len(grid)
        else:
            fx_arr = daily_ffill(fxc[fxs], grid)
        legs[code] = [ (m*f if (m is not None and f is not None) else None) for m, f in zip(m2_arr, fx_arr) ]

    total = []
    for i in range(len(grid)):
        vals = [legs[c][i] for c in ECON]
        total.append(sum(v for v in vals if v is not None) if legs["US"][i] and legs["CN"][i] else None)

    # YoY on a 365-day offset (calendar grid)
    yoy = [None]*len(grid)
    for i in range(len(grid)):
        j = i - 365
        if j >= 0 and total[i] and total[j]:
            yoy[i] = total[i]/total[j] - 1
    # 91-day trailing average ("3-month")
    def trail(arr, n):
        out = [None]*len(arr)
        for i in range(len(arr)):
            w = [v for v in arr[max(0, i-n+1):i+1] if v is not None]
            out[i] = sum(w)/len(w) if w else None
        return out
    yoy_s = trail(yoy, 91)

    # emit (skip the warm-up before first valid total)
    series = []
    for i, day in enumerate(grid):
        if total[i] is None: continue
        series.append({"d": day.strftime("%Y-%m-%d"),
                       "v": round(total[i]/1e12, 2),
                       "y": (round(yoy[i]*100, 2) if yoy[i] is not None else None),
                       "ys": (round(yoy_s[i]*100, 2) if yoy_s[i] is not None else None)})
    last = series[-1]
    summary = {"latest": last["d"], "total_tn": last["v"], "yoy": last["y"],
               "yoy_s": last["ys"], "n_economies": len(ECON)}
    # risk assets (raw daily close), for the liquidity-leads overlays
    assets = {}
    for code, (sym, bars) in ASSETS.items():
        pts = sorted((dt.datetime.utcfromtimestamp(int(t)).date(), v) for t, v in fxc[sym])
        assets[code] = [{"d": d.strftime("%Y-%m-%d"), "p": round(v, 2)}
                        for d, v in pts if d >= START and v]

    # US Total Liquidity (FRED, server-side). Never let a US failure break the
    # global build — if FRED is down we just omit the block and the US tab shows
    # a notice; the global dashboard is unaffected.
    try:
        us = build_us()
        print(f"  US: {len(us['series'])} wk | {us['summary']['latest']} "
              f"new ${us['summary']['new_tn']:.2f}T old ${us['summary']['old_tn']:.2f}T")
    except Exception as e:
        us = None
        print("  US build FAILED:", str(e)[:100])

    # The Big Picture — structural macro series (FRED). Same fail-safe pattern:
    # a failure here never breaks the rest of the build.
    try:
        big = build_big()
        print("  BIG: " + ", ".join(f"{k} {len(v)}" for k, v in big.items()))
    except Exception as e:
        big = None
        print("  BIG build FAILED:", str(e)[:100])

    data = {"updated": dt.datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC"),
            "freq": "daily", "lag_days": 90, "summary": summary, "series": series,
            "btc": assets["btc"], "ndx": assets["ndx"], "us": us, "big": big}

    os.makedirs(os.path.join(HERE, "data"), exist_ok=True)
    json.dump(data, open(os.path.join(HERE, "data", "data.json"), "w"), default=str)
    with open(os.path.join(HERE, "data", "data.js"), "w") as f:
        f.write("window.TGL_DATA = " + json.dumps(data, default=str) + ";")
    print(f"WROTE {len(series)} daily points | {summary['latest']} "
          f"${summary['total_tn']}T  YoY {summary['yoy']}% (3m {summary['yoy_s']}%)")

if __name__ == "__main__":
    build()
