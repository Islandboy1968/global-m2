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

BARS = 400   # monthly: ~33y; quarterly: capped by available history. The frontend windows it.


def _iso(t):
    return dt.datetime.utcfromtimestamp(int(t)).date().strftime("%Y-%m-%d")


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
    return out


if __name__ == "__main__":
    cyc = build_cycle()
    for k, arr in cyc.items():
        if arr:
            print(f"{k:10s}: {len(arr):4d} pts | {arr[0]['d']} -> {arr[-1]['d']} (last {arr[-1]['v']})")
