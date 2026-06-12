#!/usr/bin/env python3
"""
relationships.py — §5b of DATA_CONTRACT.md for the TEC dashboard: independent,
pipeline-computed checks of the chart constructions that data/panels.json (§5a)
declares. Port of EA's relationships.py (the proven reference) with one
deliberate adaptation, documented here because it changes the numbers:

    EA correlates on an integer-YEAR grid (its series are annual/quarterly and
    its claimed leads are multi-year). TEC's regime claims live at ~90-DAY
    leads (liquidity → BTC/NDX) and ~12-18-month leads (FCI → ISM), on
    daily/weekly/monthly series — a year grid would read every TEC lead as 0.
    This port therefore buckets every series to a MONTHLY grid (mean within
    month) and scans integer-month lags to ±36 months. Output carries
    best_lag_months (native) plus best_lag_years (rounded, for the
    cross-dashboard parser that already reads EA's field).

The §5a/§5b handshake is unchanged: panels.json declares which series overlay
and what the author CLAIMS ("liquidity leads BTC ~90d"); this module resolves
the RAW series from data/data.json and recomputes the claim from scratch —
whole-overlap anchor PLUS a rolling-window track and a drift read, so "lead
compressing / correlation decaying" surfaces as the regime-change tell rather
than the overlay being taken on faith.

Like summarize.py this is descriptive only: recomputed facts, never narrative.
It never re-fetches and never recomputes the index.

Usage: imported lazily by summarize.build_summary (emits a `panels` list into
data/summary.json); or standalone: python relationships.py [data/data.json]
"""

import json
import math
import os

from summarize import _sig, _trend

_HERE = os.path.dirname(os.path.abspath(__file__))
_MANIFEST = os.path.join(_HERE, "data", "panels.json")

MAX_LAG_MONTHS = 36          # scan ±3y: covers 90d asset leads and 18mo FCI→ISM
ROLL_WINDOW_MONTHS = 60      # 5y rolling windows for the drift track
ROLL_STEP_MONTHS = 12


# ── series resolution ───────────────────────────────────────────────────────

def _epoch_month(d):
    """ISO date string → integer month index (y*12 + m-1)."""
    try:
        return int(d[:4]) * 12 + int(d[5:7]) - 1
    except (TypeError, ValueError, IndexError):
        return None


def _monthly(points):
    """TEC series shape [{d: ISO, v|p: float}, …] → [(epoch_month, mean value)]
    sorted; daily/weekly series are averaged within the month."""
    if not isinstance(points, list):
        return None
    acc = {}
    for p in points:
        if not isinstance(p, dict):
            return None
        m = _epoch_month(p.get("d", ""))
        v = p.get("v", p.get("p"))
        if m is None or not isinstance(v, (int, float)):
            continue
        acc.setdefault(m, []).append(float(v))
    out = sorted((m, sum(vs) / len(vs)) for m, vs in acc.items())
    return out or None


def _resolve(series, data):
    """Resolve one manifest series spec to [(epoch_month, value)] or None.
    TEC keys: `liquidity_total` → total_liquidity.series; dotted `block.leaf`
    (e.g. cycle.ism) → data[block][leaf]; bare key (btc, ndx) → data[key]."""
    key = series.get("key", "")
    if key == "liquidity_total":
        node = (data.get("total_liquidity") or {}).get("series")
    elif "." in key:
        blk, _, leaf = key.partition(".")
        node = (data.get(blk) or {}).get(leaf) if isinstance(data.get(blk), dict) else None
    else:
        node = data.get(key)
    return _monthly(node)


# ── the §5b math (ported from EA verbatim apart from the month grid) ────────

def _transform(d):
    """Correlation basis per series: log10 for positive multi-OOM LEVEL series
    (BTC, NDX, liquidity) to linearise exponentials; LINEAR otherwise — RoC /
    z-score / oscillating series (ISM, FCI) go negative where log10 is invalid
    and would silently drop half the data."""
    vals = list(d.values())
    use_log = bool(vals) and all(v > 0 for v in vals) and min(vals) > 0 \
        and max(vals) / min(vals) >= 10
    if use_log:
        return {k: math.log10(v) for k, v in d.items()}, True
    return dict(d), False


def _pearson(xs, ys):
    n = len(xs)
    if n < 2:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    sx = sum((x - mx) ** 2 for x in xs)
    sy = sum((y - my) ** 2 for y in ys)
    if sx == 0 or sy == 0:
        return None
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    return cov / math.sqrt(sx * sy)


def _best_lag(ta, tb, months, max_lag=MAX_LAG_MONTHS):
    """(lag_months, corr) maximising |Pearson| of b vs a on the transformed
    value dicts, restricting source months to `months`. Positive lag => a
    leads b by that many months. None if too little overlap."""
    best = None
    for lag in range(-max_lag, max_lag + 1):
        xs = [(ta[m], tb[m + lag]) for m in ta if m in months and (m + lag) in tb]
        if len(xs) < 12:                       # ≥1y of monthly overlap
            continue
        r = _pearson([p for p, _ in xs], [q for _, q in xs])
        if r is not None and (best is None or abs(r) > abs(best[1])):
            best = (lag, r)
    return best


def _lead_lag(a, b, baseline=None):
    """Whole-overlap anchor + rolling-window track + drift — built to surface
    the relationship MOVING (lead compressing, correlation decaying), which is
    the regime tell, not just to prove the overlay once."""
    da, db = dict(a), dict(b)
    if len(da) < 12 or len(db) < 12:
        return None
    ta, la_log = _transform(da)
    tb, lb_log = _transform(db)
    basis = "log10" if (la_log and lb_log) else "linear"
    whole = _best_lag(ta, tb, set(ta))
    if whole is None:
        return None
    out = {"best_lag_months": whole[0],
           "best_lag_years": round(whole[0] / 12, 2),
           "corr_at_best_lag": round(whole[1], 3),
           "method": f"max Pearson xcorr ({basis}), integer-month grid"}

    ms = sorted(ta)
    track, we = [], ms[0] + ROLL_WINDOW_MONTHS
    while we <= ms[-1]:
        bl = _best_lag(ta, tb, set(range(we - ROLL_WINDOW_MONTHS, we + 1)))
        if bl:
            track.append({"window_end": f"{we // 12:04d}-{we % 12 + 1:02d}",
                          "best_lag_months": bl[0], "corr": round(bl[1], 3)})
        we += ROLL_STEP_MONTHS
    last = _best_lag(ta, tb, set(range(ms[-1] - ROLL_WINDOW_MONTHS, ms[-1] + 1)))
    last_tag = f"{ms[-1] // 12:04d}-{ms[-1] % 12 + 1:02d}"
    if last and (not track or track[-1]["window_end"] != last_tag):
        track.append({"window_end": last_tag,
                      "best_lag_months": last[0], "corr": round(last[1], 3)})

    latest = track[-1] if track else {"best_lag_months": whole[0],
                                      "corr": round(whole[1], 3)}

    if baseline:
        # authored §5a baselines carry offset_days or offset_months
        bl_months = None
        if baseline.get("offset_months") is not None:
            bl_months = baseline["offset_months"]
        elif baseline.get("offset_days") is not None:
            bl_months = round(baseline["offset_days"] / 30.44)
        elif baseline.get("best_lag_years") is not None:
            bl_months = round(baseline["best_lag_years"] * 12)
        vb = {}
        if bl_months is not None:
            vb["lag_delta_months"] = latest["best_lag_months"] - bl_months
        if baseline.get("corr") is not None:
            vb["corr_delta"] = round(latest["corr"] - baseline["corr"], 3)
        if vb:
            vb["of"] = "latest window vs authored baseline"
            out["vs_baseline"] = vb

    if len(track) >= 2:
        out["track"] = track
        k = min(3, len(track) - 1)
        prior = track[-1 - k:-1]
        pcorr = sum(w["corr"] for w in prior) / len(prior)
        plag = sum(w["best_lag_months"] for w in prior) / len(prior)
        cc = round(latest["corr"] - pcorr, 3)
        lc = int(round(latest["best_lag_months"] - plag))
        notes = []
        if lc > 0:
            notes.append(f"lead stretching {lc}mo")
        elif lc < 0:
            notes.append(f"lead compressing {abs(lc)}mo")
        if cc <= -0.05:
            notes.append("correlation decaying")
        elif cc >= 0.05:
            notes.append("correlation strengthening")
        out["drift"] = {"corr_change": cc, "lag_change_months": lc,
                        "basis": f"latest vs prior {len(prior)} windows",
                        "windows": len(track),
                        "note": "; ".join(notes) or "stable"}
    return out


def _series_check(name, pairs):
    if not pairs:
        return None
    vals = [v for _, v in pairs]
    lo, hi = min(vals), max(vals)
    ypairs = [(m / 12.0, v) for m, v in pairs]     # year-float for _trend
    return {
        "key": name,
        "n_months": len(pairs),
        "latest": _sig(pairs[-1][1], 6),
        "range_factor": _sig(hi / lo) if lo > 0 else None,
        "trend": _trend(ypairs),
    }


# ── entry point ─────────────────────────────────────────────────────────────

def build_panel_checks(data):
    """Read data/panels.json and return §5b check records — the independent
    recomputation of each panel's authored claim."""
    if not os.path.exists(_MANIFEST):
        return []
    try:
        manifest = json.load(open(_MANIFEST))
    except Exception:
        return []
    out = []
    for panel in manifest.get("panels", []):
        resolved = []
        for s in panel.get("series", []):
            pairs = _resolve(s, data)
            if pairs:
                resolved.append((s.get("key"), pairs))
        rel = panel.get("relationship") or {}
        rec = {
            "panel": panel.get("id"),
            "tab": manifest.get("tab"),
            "title": panel.get("title"),
            "kind": rel.get("kind"),
            "claim": rel.get("claim"),
            "checks": [c for c in (_series_check(k, p) for k, p in resolved) if c],
        }
        if rec["kind"] in ("lead_lag", "overlay", "ratio", "dual_axis", "composite"):
            distinct, seen = [], set()
            for k, p in resolved:
                if k not in seen:
                    seen.add(k)
                    distinct.append((k, p))
            if len(distinct) >= 2 and distinct[0][1] != distinct[1][1]:
                baseline = dict(rel.get("baseline") or {})
                # the authored lead (§5a `lead`) doubles as baseline if no
                # explicit baseline block was written
                for fld in ("offset_days", "offset_months"):
                    if fld not in baseline and (rel.get("lead") or {}).get(fld) is not None:
                        baseline[fld] = rel["lead"][fld]
                ll = _lead_lag(distinct[0][1], distinct[1][1],
                               baseline=baseline or None)
                if ll:
                    rec["lead_lag"] = {"a": distinct[0][0], "b": distinct[1][0], **ll}
        out.append(rec)
    return out


if __name__ == "__main__":
    import sys
    src = sys.argv[1] if len(sys.argv) > 1 else os.path.join(_HERE, "data", "data.json")
    checks = build_panel_checks(json.load(open(src)))
    print(json.dumps(checks, indent=1)[:4000])
    print(f"\n{len(checks)} panel checks built")
