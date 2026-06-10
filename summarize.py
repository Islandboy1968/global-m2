#!/usr/bin/env python3
"""
summarize.py — compact, AI-first digest of the TEC dashboard payload.

WHY THIS EXISTS
===============
data/data.json is the full record: the 6,000-point daily global-liquidity line
plus ~45 macro leaves, ~1.5 MB. That is the right shape for charts and deep
analysis but a poor shape for an AI asked for a *compressed read* of the cycle —
loading 1.5 MB into a context window to answer "where is global liquidity and is
the cycle turning?" is wasteful.

data/summary.json is the dense companion (~36 KB): per indicator, the precomputed
facts an analysis agent reasons over — latest value, change factor, YoY, the
recent-window trend, units, which direction is favourable, and the source-verified
freshness TEC already computes. An AI reads THIS first and only opens data.json
when it needs the shape of a specific curve.

This is the TEC half of the cross-dashboard contract in DATA_CONTRACT.md — it
emits the SAME shape as EA's summarize.py (`dashboard:"tec"` discriminator) so one
parser ingests both dashboards.

DISCIPLINE
==========
This module computes DESCRIPTIVE STATISTICS over already-emitted series only
(latest / ratio / log-linear trend). It emits NO narrative: the pipeline owns
facts, the AI owns insight. It never re-fetches and never recomputes the index.

Usage:
    python summarize.py [data/data.json]   # writes data/summary.json next to it
"""
import json, math, os, sys
from datetime import datetime, timezone

from indicators_meta import META, meta_for

SCHEMA_VERSION = "1.0"
_TREND_WINDOW_YEARS = 12   # fit the CURRENT exponential rate, not the full tail


# ----------------------------------------------------------------- helpers
def _x_to_year(x):
    """'YYYY' / 'YYYY-MM' / 'YYYY-MM-DD' (or numeric year) -> float year."""
    if isinstance(x, (int, float)):
        return float(x)
    if not isinstance(x, str):
        return None
    parts = x.split("-")
    try:
        y = int(parts[0])
    except (ValueError, IndexError):
        return None
    frac = 0.0
    if len(parts) >= 2:
        try:
            frac += (int(parts[1]) - 1) / 12.0
        except ValueError:
            pass
    if len(parts) >= 3:
        try:
            frac += (int(parts[2]) - 1) / 365.0
        except ValueError:
            pass
    return y + frac


def _val_key(points):
    """TEC points are dicts: most carry 'v', the asset overlays carry 'p'."""
    for p in points:
        if isinstance(p, dict):
            if "v" in p:
                return "v"
            if "p" in p:
                return "p"
    return "v"


def _pairs(points):
    """[(year_float, value_float)] from a list of TEC {'d':..,'v'/'p':..} dicts,
    sorted by date and skipping null/non-numeric points."""
    if not points:
        return []
    vk = _val_key(points)
    out = []
    for p in points:
        if not isinstance(p, dict) or p.get("d") is None:
            continue
        yr = _x_to_year(p["d"])
        v = p.get(vk)
        if yr is None or v is None:
            continue
        try:
            out.append((yr, float(v)))
        except (TypeError, ValueError):
            continue
    out.sort(key=lambda t: t[0])
    return out


def _sig(x, n=4):
    """Round to n significant figures (None/0-safe) so small values survive."""
    if x is None or x == 0:
        return x
    try:
        return round(x, -int(math.floor(math.log10(abs(x)))) + (n - 1))
    except (ValueError, OverflowError):
        return x


def _best(pairs, progress):
    """Frontier point: min if progress is 'lower' (cost/rate), else max."""
    if not pairs:
        return None
    return min(pairs, key=lambda t: t[1]) if progress == "lower" \
        else max(pairs, key=lambda t: t[1])


def _trend(pairs):
    """Log-linear least-squares slope over the recent window. Reported only for
    strictly-positive series (logs undefined otherwise — most TEC series are
    YoY/z-scores that cross zero, so trend is commonly null, which is correct)."""
    pts = [(y, v) for y, v in pairs if v > 0]
    if len(pts) < 3:
        return None
    latest_year = pts[-1][0]
    window = [(y, v) for y, v in pts if y >= latest_year - _TREND_WINDOW_YEARS]
    used = window if len(window) >= 3 else pts
    ys = [y for y, _ in used]
    if max(ys) - min(ys) < 0.5:
        return None
    n = len(used)
    ls = [math.log10(v) for _, v in used]
    mx = sum(ys) / n
    ml = sum(ls) / n
    den = sum((x - mx) ** 2 for x in ys)
    if den == 0:
        return None
    slope = sum((x - mx) * (l - ml) for x, l in zip(ys, ls)) / den  # log10/yr
    out = {"window_years": round(max(ys) - min(ys), 1),
           "log10_per_year": round(slope, 4),
           "doubling_years": None, "halving_years": None}
    if abs(slope) > 1e-9:
        t = round(math.log10(2.0) / abs(slope), 2)
        out["doubling_years" if slope > 0 else "halving_years"] = t
    return out


def _yoy_pct(pairs):
    """% change of the latest point vs the point closest to one year earlier
    (within 0.6yr). None when no such prior point or the base is zero."""
    if len(pairs) < 2:
        return None
    ly, lv = pairs[-1]
    target = ly - 1.0
    base = min(pairs[:-1], key=lambda t: abs(t[0] - target))
    if abs(base[0] - target) > 0.6 or base[1] == 0:
        return None
    return round((lv - base[1]) / abs(base[1]) * 100.0, 2)


# ----------------------------------------------------------------- walk
# Leaf series live at these dotted paths in data.json. "series", "btc", "ndx"
# are top-level lists; "us.series" is nested; the rest are {block: {leaf: [...]}}.
TOP_LEVEL_SERIES = ["series", "btc", "ndx"]
BLOCKS = ["big", "cycle", "exp", "infl", "labor", "rates", "housing", "credit", "china"]


def _iter_leaves(data):
    """Yield (dotted_path, points_list) for every leaf series in data.json."""
    for k in TOP_LEVEL_SERIES:
        if isinstance(data.get(k), list):
            yield k, data[k]
    us = data.get("us")
    if isinstance(us, dict) and isinstance(us.get("series"), list):
        yield "us.series", us["series"]
    # Global Total Liquidity Index + its decomposition (components are parts of the
    # one index, surfaced so an AI sees the balance-sheet vs M2 split).
    tl = data.get("total_liquidity")
    if isinstance(tl, dict):
        if isinstance(tl.get("series"), list):
            yield "total_liquidity.series", tl["series"]
        comps = tl.get("components") or {}
        for ck in ("balance_sheets", "m2"):
            if isinstance(comps.get(ck), list):
                yield f"total_liquidity.components.{ck}", comps[ck]
    for blk in BLOCKS:
        b = data.get(blk)
        if isinstance(b, dict):
            for leaf, series in b.items():
                if isinstance(series, list):
                    yield f"{blk}.{leaf}", series


def _freshness_status(data, path):
    """Pull TEC's source-verified status for a leaf out of data['freshness'],
    so the digest carries the SAME live/behind/stale verdict the dashboard badge
    shows. Returns a small {as_of, status, source_latest} or None."""
    fr = data.get("freshness") or {}
    block = path.split(".", 1)[0]
    leaf = path.split(".", 1)[1] if "." in path else "series"
    blk = fr.get(block) or {}
    entry = (blk.get("series") or {}).get(leaf)
    if isinstance(entry, dict):  # post-verify shape: {as_of, status, source_latest,...}
        return {"as_of": entry.get("as_of"), "status": entry.get("status"),
                "source_latest": entry.get("source_latest")}
    if isinstance(entry, str):   # pre-verify shape: just the date string
        return {"as_of": entry, "status": None, "source_latest": None}
    return None


def _summarize_leaf(path, points):
    pairs = _pairs(points)
    if not pairs:
        return None
    meta = meta_for(path)
    progress = meta.get("progress") or "higher"
    (fy, fv), (ly, lv) = pairs[0], pairs[-1]
    vals = [v for _, v in pairs]
    lo, hi = min(vals), max(vals)
    range_factor = _sig(hi / lo) if lo > 0 else None
    best = _best(pairs, progress)
    vk = _val_key(points)
    return {
        "title":        meta.get("title"),
        "group":        meta.get("group"),
        "role":         meta.get("role"),
        "timing":       meta.get("timing"),
        "unit":         meta.get("unit"),
        "progress":     progress,
        "latest":       {"x": points[-1].get("d"), "value": _sig(lv, 6)},
        "best":         {"value": _sig(best[1], 6)} if best else None,
        "first":        {"x": points[0].get("d"), "value": _sig(fv, 6)},
        "n_points":     len(pairs),
        "span_years":   round(ly - fy, 2),
        "range_factor": range_factor,
        "yoy_pct":      _yoy_pct(pairs),
        "trend":        _trend(pairs),
        "source":       meta.get("source"),
        "description":  meta.get("description"),
        "_val_key":     vk,
    }


def _headline(data):
    """The dashboard centrepiece: the GMI Total Global Liquidity Index (CB balance
    sheets netted + M2, 10 economies). Global M2 is carried as a secondary
    component read, not a competing headline."""
    tl = (data.get("total_liquidity") or {}).get("summary") or {}
    m2 = data.get("summary") or {}
    return {
        "metric": "GMI Total Global Liquidity Index (central-bank balance sheets "
                  "netted + M2, summed across the major economies in USD; see n_economies)",
        "level": tl.get("total_tn"),
        "unit": "$ trillions",
        "yoy_pct": tl.get("yoy"),
        "as_of": tl.get("latest"),
        "n_economies": tl.get("n_economies"),
        "components": {"balance_sheets_tn": tl.get("balance_sheets_tn"),
                       "m2_tn": tl.get("m2_tn")},
        "global_m2": {"level_tn": m2.get("total_tn"), "yoy_pct": m2.get("yoy"),
                      "yoy_3m_pct": m2.get("yoy_s"), "as_of": m2.get("latest"),
                      "n_economies": m2.get("n_economies"),
                      "note": "broad-money component, 47 economies (daily); a part of "
                              "the Total Liquidity picture, not the headline"},
    }


def _build_status(data):
    """Roll the per-block source-verified freshness up into a build summary
    mirroring EA's `build` block (ok / stale / behind / missing counts)."""
    fr = data.get("freshness") or {}
    blocks_total = len(fr)
    stale, behind, missing = [], [], []
    for name, blk in fr.items():
        if not isinstance(blk, dict):
            continue
        st = blk.get("status")
        if blk.get("stale"):
            stale.append(name)
        if st == "BEHIND":
            behind.append(name)
        elif st == "MISSING":
            missing.append(name)
    ok = blocks_total - len(set(behind) | set(missing) | set(stale))
    return {
        "blocks_total": blocks_total,
        "blocks_ok": ok,
        "stale": sorted(set(stale)),
        "behind": sorted(set(behind)),
        "missing": sorted(set(missing)),
        "china_override": data.get("china_override"),
    }


def _month_map(points, key):
    """{YYYY-MM: value} from a series, month-end (last value in each month)."""
    out = {}
    for p in points or []:
        if isinstance(p, dict) and p.get("d") and p.get(key) is not None:
            out[p["d"][:7]] = p[key]
    return out


def _add_months(m, k):
    y, mo = map(int, m.split("-")); mo += k; y += (mo - 1) // 12; mo = (mo - 1) % 12 + 1
    return f"{y:04d}-{mo:02d}"


def _xcorr(driver, target, maxlead=12, logd=False, logt=False, minn=24):
    """Best (lead_months, correlation) where driver[t] leads target[t+lead]."""
    def tx(d, lg):
        if not lg:
            return dict(d)
        return {k: math.log(v) for k, v in d.items() if v > 0}
    dd, tt = tx(driver, logd), tx(target, logt)
    best = (0, None)
    for L in range(maxlead + 1):
        xs, ys = [], []
        for m in dd:
            t = _add_months(m, L)
            if t in tt:
                xs.append(dd[m]); ys.append(tt[t])
        n = len(xs)
        if n < minn:
            continue
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        vx = sum((x - mx) ** 2 for x in xs); vy = sum((y - my) ** 2 for y in ys)
        if vx > 0 and vy > 0:
            r = cov / (vx * vy) ** 0.5
            if best[1] is None or r > best[1]:
                best = (L, r)
    return best


def _signals(data):
    """Computed lead/lag relationships — the machine-readable SIGNAL layer. An AI
    reads these instead of re-deriving them: each is recomputed from the raw series
    (best lead + correlation), so it gets the regime signal AND its strength."""
    tl = (data.get("total_liquidity") or {}).get("series") or []
    cyc = data.get("cycle") or {}
    liq_lvl, liq_yoy = _month_map(tl, "v"), _month_map(tl, "ys")
    ism = _month_map(cyc.get("ism"), "v")
    btc, ndx = _month_map(data.get("btc"), "p"), _month_map(data.get("ndx"), "p")
    out = []
    def add(name, driver, target, logd, logt, read):
        lead, r = _xcorr(driver, target, logd=logd, logt=logt)
        if r is None:
            return
        out.append({
            "relationship": name, "best_lead_months": lead,
            "correlation": round(r, 3), "r2": round(r * r, 3),
            "method": "max cross-correlation, monthly, " + ("log-levels" if (logd or logt) else "levels"),
            "read": read,
        })
    add("total_liquidity_leads_btc", liq_lvl, btc, True, True,
        "GMI Total Global Liquidity leads Bitcoin")
    add("total_liquidity_leads_ndx", liq_lvl, ndx, True, True,
        "GMI Total Global Liquidity leads the Nasdaq 100")
    add("total_liquidity_yoy_leads_ism", liq_yoy, ism, False, False,
        "Total Liquidity YoY (3m) leads the ISM manufacturing cycle")
    # NB: fci -> ism deliberately omitted — the FCI reconstruction has its own
    # sign/transform convention, so a naive level cross-correlation understates the
    # ~9mo lead and would ship a misleading signal. Add once the transform is specced.
    return out


def build_summary(data):
    """Build the summary.json digest from the assembled data.json payload."""
    indicators = {}
    for path, points in _iter_leaves(data):
        try:
            s = _summarize_leaf(path, points)
            if s is None:
                continue
            s.pop("_val_key", None)
            fresh = _freshness_status(data, path)
            if fresh:
                s["freshness"] = fresh
            indicators[path] = s
        except Exception:  # a bad series must never break the digest
            continue
    return {
        "schema_version": SCHEMA_VERSION,
        "dashboard": "tec",
        "title": "The Everything Code — global liquidity & cycle dashboard",
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_updated": data.get("updated"),
        "headline": _headline(data),
        "signals": _signals(data),
        "indicators": indicators,
        "build": _build_status(data),
    }


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join("data", "data.json")
    with open(path) as f:
        data = json.load(f)
    summary = build_summary(data)
    out = os.path.join(os.path.dirname(path) or ".", "summary.json")
    with open(out, "w") as f:
        json.dump(summary, f, indent=1, default=str)
    n = len(summary["indicators"])
    size = os.path.getsize(out)
    print(f"WROTE {out} | {n} indicators | {size/1024:.1f} KB | "
          f"headline {summary['headline']['level']}T "
          f"YoY {summary['headline']['yoy_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
