#!/usr/bin/env python3
"""
Shared helpers for the macro builders (labor, rates, housing, credit, china, ...).

Keeps each builder small and consistent with the build_inflation / build_exports
template: all data is pulled monthly ("1M") via tv_pull.pull_series, which returns
a sorted list of (epoch_seconds, value). FRED series go through the "FRED:"
passthrough (FRED's own CSV endpoint 403s automated requests), so always pull via
pull_series with a "FRED:" symbol.

Helpers:
  iso(t)              epoch -> "YYYY-MM-DD"
  to_yoy(points)      level -> YoY %  (same calendar month one year prior)
  to_yoy_diff(points) level -> YoY absolute change in points (for yields)
  zscore_pts(points)  v -> z using full-sample mean/std
  pull_first(...)     candidate-symbol fallback, fail-safe, logged
"""
import datetime as dt
from tv_pull import pull_series


def iso(t):
    return dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m-%d")


def _ym(t):
    d = dt.datetime.utcfromtimestamp(int(t)).date()
    return f"{d.year:04d}-{d.month:02d}"


def to_yoy(points):
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


def to_yoy_diff(points):
    """points: list[(epoch, level)] -> list[(epoch, change)] as the absolute
    year-on-year change (level[t] - level[t-12]) in the same units (points).
    Used for yields. Robust to gaps; drops points without a year-ago peer."""
    by_ym = {}
    for t, v in points:
        by_ym[_ym(t)] = (t, v)
    out = []
    for ym, (t, v) in sorted(by_ym.items()):
        y, m = map(int, ym.split("-"))
        prev = f"{y - 1:04d}-{m:02d}"
        if prev in by_ym and by_ym[prev][1] is not None:
            out.append((t, v - by_ym[prev][1]))
    return out


def zscore_pts(points):
    """points: list[(epoch, v)] -> list[(epoch, z)] using full-sample mean/std.
    Returns [] if fewer than 2 points or zero variance."""
    pts = sorted(points)
    vals = [v for _, v in pts]
    n = len(vals)
    if n < 2:
        return []
    mean = sum(vals) / n
    var = sum((v - mean) ** 2 for v in vals) / n
    std = var ** 0.5
    if std == 0:
        return []
    return [(t, (v - mean) / std) for t, v in pts]


def pull_first(candidates, bars=470, min_pts=24):
    """Try each candidate TradingView symbol via pull_series(sym, "1M", bars);
    return (symbol, points) for the first with >= min_pts points, else (None, []).
    Prints a one-line log per skipped candidate."""
    for sym in candidates:
        try:
            pts = pull_series(sym, "1M", bars)
            if pts and len(pts) >= min_pts:
                return sym, pts
            print(f"    {sym}: only {len(pts) if pts else 0} pts, trying next")
        except Exception as e:
            print(f"    {sym}: {str(e)[:60]}")
    return None, []
