#!/usr/bin/env python3
"""
The Business Cycle — survey + activity series, server-side from TradingView.

Written into data.js as TGL_DATA["cycle"]. Series pulled from TradingView's
ECONOMICS feed and FRED passthrough (no API key), reusing pull_series in
tv_pull.py. FRED no longer carries the ISM series (ISM asserts copyright), so
TradingView's ECONOMICS feed is the source for those.

Series (key: symbol, resolution):
  ism        ECONOMICS:USBCOI    ISM Manufacturing PMI, monthly
  neworders  ECONOMICS:USMNO     ISM Manufacturing New Orders, monthly
  gdp        ECONOMICS:USGDPQQ   US Real GDP, QoQ % annualised (SAAR), quarterly

Derived:
  capex      FRED:PNFI / FRED:GDP * 100  — US private nonresidential fixed
             investment as % of GDP (broad business capex; the "real-world
             infrastructure investment" GMI ties to the ISM), quarterly.

The dashboard pairs ISM with the GMI Total Liquidity Index YoY held in
TGL_DATA["series"], overlays GDP QoQ annualised, and overlays capex/GDP.
No liquidity series is duplicated here.
"""
import datetime as dt
from tv_pull import pull_series

# key: (symbol, resolution)
CYCLE_SERIES = {
    "ism":       ("ECONOMICS:USBCOI",  "1M"),
    "neworders": ("ECONOMICS:USMNO",   "1M"),
    "gdp":       ("ECONOMICS:USGDPQQ", "3M"),
}

# ISM Services / Non-Manufacturing PMI. FRED can't carry ISM (copyright), and
# TradingView's ECONOMICS symbol for it varies, so try a few and use the first
# that returns data (logged so we know which one TradingView served).
# USMNBA = US ISM Non-Manufacturing Business Activity (TradingView ECONOMICS), the
# usual public stand-in for the ISM Services headline. Tried first; the rest are
# fallbacks. A PMI-range guard (build_services_ism) rejects any that mis-resolve.
# Confirmed working symbol (ISM Non-Manufacturing Business Activity, the standard
# ISM-Services stand-in). Kept as a 1-item tuple so a future swap is trivial; a long
# blind-candidate list slowed every run badly (each miss waits out the pull deadline).
SERVICES_ISM_CANDS = ("ECONOMICS:USNMBA",)
# ISM Non-Manufacturing New Orders (services side) — the cyclical-impulse input.
SERVICES_NO_CANDS = ("ECONOMICS:USNMNO",)

BARS = 400   # monthly: ~33y; quarterly: capped by available history. The frontend windows it.


def _iso(t):
    return dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m-%d")


def _pull_first(cands, res, bars):
    """Return (symbol, points) for the first candidate symbol that yields data."""
    for sym in cands:
        try:
            pts = pull_series(sym, res, bars)
        except Exception as e:
            print(f"  {sym}: {str(e)[:60]}")
            continue
        if pts:
            return sym, pts
    return None, []


def _looks_like_pmi(pts):
    """A diffusion index (PMI) sits ~30-75. Guards against a candidate symbol that
    resolves to an unrelated, mis-scaled series (e.g. a millions-level instrument)."""
    vals = sorted(v for _, v in pts)
    if not vals:
        return False
    med = vals[len(vals) // 2]
    return 20.0 <= med <= 80.0


def _build_pmi(cands, label, bars=BARS):
    """First candidate symbol that returns PMI-range monthly data, as [{d, v}].
    A symbol that resolves to a non-PMI (mis-scaled) series is rejected."""
    for sym in cands:
        try:
            pts = pull_series(sym, "1M", bars)
        except Exception as e:
            print(f"  {sym}: {str(e)[:60]}")
            continue
        if pts and _looks_like_pmi(pts):
            print(f"  {label} via {sym} ({len(pts)} pts)")
            return [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)]
        if pts:
            print(f"  {sym}: resolved but not PMI-range (median off) — skipping")
    raise RuntimeError(f"no {label} symbol returned PMI-range data")


def build_services_ism(bars=BARS):
    """ISM Services / Non-Manufacturing Business Activity, monthly, via TradingView."""
    return _build_pmi(SERVICES_ISM_CANDS, "services_ism", bars)


def build_services_neworders(bars=BARS):
    """ISM Non-Manufacturing New Orders (services side), monthly, via TradingView."""
    return _build_pmi(SERVICES_NO_CANDS, "services_neworders", bars)


def _composite(parts):
    """Weighted composite of monthly diffusion series. parts: [(arr, weight), ...]
    where arr is [{d, v}]. Aligns on the year-months common to every input so the
    blend is never distorted by a missing month; returns [{d: 'YYYY-MM-01', v}]."""
    maps = [({r["d"][:7]: r["v"] for r in (arr or [])}, w) for arr, w in parts]
    if any(not m for m, _ in maps):
        return None
    common = set(maps[0][0])
    for m, _ in maps[1:]:
        common &= set(m)
    return [{"d": ym + "-01", "v": round(sum(m[ym] * w for m, w in maps), 2)}
            for ym in sorted(common)]


def build_m2_yoy(bars=BARS):
    """US M2 money stock (FRED:M2SL, $bn), year-on-year % change, monthly."""
    lvl = dict(pull_series("FRED:M2SL", "1M", bars))
    ks = sorted(lvl)
    out = []
    for i, t in enumerate(ks):
        if i >= 12 and lvl[ks[i - 12]]:
            out.append({"d": _iso(t), "v": round((lvl[t] / lvl[ks[i - 12]] - 1) * 100, 2)})
    return out


def build_capex(bars=400):
    """US nonresidential fixed investment as % of GDP, quarterly, via FRED passthrough."""
    pnfi = dict(pull_series("FRED:PNFI", "3M", bars))
    gdp = dict(pull_series("FRED:GDP", "3M", bars))
    common = sorted(set(pnfi) & set(gdp))
    return [{"d": _iso(t), "v": round(pnfi[t] / gdp[t] * 100, 2)}
            for t in common if gdp[t]]


def build_capex_growth(bars=400):
    """US nonresidential fixed investment, YoY % growth (nominal), quarterly, via FRED passthrough.
    ISM leads this by ~3 quarters (r~0.64 since 1995)."""
    lvl = dict(pull_series("FRED:PNFI", "3M", bars))
    ks = sorted(lvl)
    out = []
    for i, t in enumerate(ks):
        if i >= 4 and lvl[ks[i - 4]]:
            out.append({"d": _iso(t), "v": round((lvl[t] / lvl[ks[i - 4]] - 1) * 100, 2)})
    return out


def build_cycle(bars=BARS):
    """Return the TGL_DATA['cycle'] block: {key: [{d, v}, ...]} sorted by date."""
    out = {}
    for key, (sym, res) in CYCLE_SERIES.items():
        pts = pull_series(sym, res, bars)
        out[key] = [{"d": _iso(t), "v": round(v, 2)} for t, v in sorted(pts)]
    try:
        out["capex"] = build_capex(bars)
    except Exception as e:
        out["capex"] = None
        print("  capex build FAILED:", str(e)[:100])
    try:
        out["capex_g"] = build_capex_growth(bars)
    except Exception as e:
        out["capex_g"] = None
        print("  capex_g build FAILED:", str(e)[:100])
    try:
        out["services_ism"] = build_services_ism(bars)
    except Exception as e:
        out["services_ism"] = None
        print("  services_ism build FAILED:", str(e)[:100])
    try:
        out["m2_yoy"] = build_m2_yoy(bars)
    except Exception as e:
        out["m2_yoy"] = None
        print("  m2_yoy build FAILED:", str(e)[:100])
    try:
        out["services_neworders"] = build_services_neworders(bars)
    except Exception as e:
        out["services_neworders"] = None
        print("  services_neworders build FAILED:", str(e)[:100])

    # GDP-weighted Business-Cycle Composite — the services-led "source of truth"
    # (the US economy is ~90% services, ~10% manufacturing by GDP weight).
    out["bc_composite"] = _composite([(out.get("services_ism"), 0.9),
                                       (out.get("ism"), 0.1)])
    if out["bc_composite"]:
        print(f"  bc_composite: {len(out['bc_composite'])} pts (last {out['bc_composite'][-1]['v']})")
    # Cyclical Impulse — manufacturing is small in GDP but high-beta and turns first:
    # 50% Mfg New Orders + 30% Services New Orders + 20% Mfg PMI.
    out["cyclical_impulse"] = _composite([(out.get("neworders"), 0.5),
                                          (out.get("services_neworders"), 0.3),
                                          (out.get("ism"), 0.2)])
    if out["cyclical_impulse"]:
        print(f"  cyclical_impulse: {len(out['cyclical_impulse'])} pts (last {out['cyclical_impulse'][-1]['v']})")
    return out


if __name__ == "__main__":
    cyc = build_cycle()
    for k, arr in cyc.items():
        if arr:
            print(f"{k:10s}: {len(arr):4d} pts | {arr[0]['d']} -> {arr[-1]['d']} (last {arr[-1]['v']})")
