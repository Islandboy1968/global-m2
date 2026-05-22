#!/usr/bin/env python3
"""
GMI Financial Conditions Index (reconstruction) — server-side from TradingView.

Written into data.js as TGL_DATA["cycle"]["fci"]. A leading conditions index that
runs ahead of the ISM by ~9 months. Reconstructed (not the proprietary GMI series)
as the inverse of a standardised composite of three tightening inputs:

  - 5-year Treasury yield   (TVC:US05Y)   year-on-year change, in points
  - US dollar               (TVC:DXY)     year-on-year % change
  - WTI crude oil           (TVC:USOIL)   year-on-year % change, half weight

Each input is z-scored, signed so that rising rates / rising dollar / rising oil
all read as TIGHTER conditions, summed with oil at HALF weight (the "50% oil
blend": oil carries almost all of its leading signal at half the supply-shock
noise), lightly 3-month smoothed, then rescaled to the ISM's own mean and standard
deviation so it overlays the ISM directly. Copper is intentionally excluded — it
tested as coincident (peaks at zero lead), so it confirms ISM rather than leading it.

The frontend shifts this series forward by the lead (default 9 months) at plot time,
so build_fci stores it at its native (unshifted) monthly dates.
"""
import datetime as dt
import math
from tv_pull import pull_series

FCI_SYMBOLS = {
    "y5":  "TVC:US05Y",   # 5-year Treasury yield, %
    "dxy": "TVC:DXY",     # US dollar index
    "oil": "TVC:USOIL",   # WTI crude
}
OIL_WEIGHT = 0.5          # the 50% oil blend
BARS = 400                # ~33 years monthly


def _to_ym(points):
    out = {}
    for t, v in points:
        d = dt.datetime.utcfromtimestamp(int(t)).date()
        out[f"{d.year:04d}-{d.month:02d}"] = v
    return out


def _shift(k, n):
    y, m = map(int, k.split("-"))
    m -= n
    while m <= 0:
        m += 12; y -= 1
    while m > 12:
        m -= 12; y += 1
    return f"{y:04d}-{m:02d}"


def _zscore(vals):
    xs = [v for v in vals if v is not None and not math.isnan(v)]
    if len(xs) < 2:
        return [None] * len(vals)
    mu = sum(xs) / len(xs)
    sd = (sum((x - mu) ** 2 for x in xs) / len(xs)) ** 0.5 or 1.0
    return [None if (v is None or math.isnan(v)) else (v - mu) / sd for v in vals]


def _smooth(vals, w=3):
    out = []
    for i in range(len(vals)):
        win = [v for v in vals[max(0, i - w + 1): i + 1] if v is not None]
        out.append(sum(win) / len(win) if win else None)
    return out


def _compose(ym, z5, zd, zo, ism, oil_weight):
    """Build one FCI series (ISM units) at the given oil weight."""
    denom = 2.0 + oil_weight
    comp = [-(z5[i] + zd[i] + oil_weight * zo[i]) / denom for i in range(len(ym))]
    comp = _smooth(comp, 3)
    isvals = [ism[k] for k in ym if k in ism]
    cvals = [c for c in comp if c is not None]
    if not isvals or not cvals:
        return []
    imu = sum(isvals) / len(isvals)
    isd = (sum((x - imu) ** 2 for x in isvals) / len(isvals)) ** 0.5 or 1.0
    cmu = sum(cvals) / len(cvals)
    csd = (sum((x - cmu) ** 2 for x in cvals) / len(cvals)) ** 0.5 or 1.0
    out = []
    for i, k in enumerate(ym):
        if comp[i] is None:
            continue
        out.append({"d": k + "-01", "v": round((comp[i] - cmu) / csd * isd + imu, 2)})
    return out


def build_fci_set(ism_series, bars=BARS):
    """Pull the inputs once and return both FCI variants in ISM units, at native dates:
       {"fci": <50% oil blend>, "fci_exoil": <rates+dollar only>}.
    ism_series: list[{d:'YYYY-MM-DD', v:float}] (USBCOI)."""
    raw = {k: _to_ym(pull_series(sym, "1M", bars)) for k, sym in FCI_SYMBOLS.items()}
    ism = {r["d"][:7]: r["v"] for r in ism_series}
    keys = sorted(set(raw["y5"]) & set(raw["dxy"]) & set(raw["oil"]))

    def yoy_diff(s, k):
        p = _shift(k, 12)
        return (s[k] - s[p]) if (k in s and p in s) else None

    def yoy_pct(s, k):
        p = _shift(k, 12)
        return (s[k] / s[p] - 1) * 100 if (k in s and p in s and s[p]) else None

    ym, d5, dd, do = [], [], [], []
    for k in keys:
        a, b, c = yoy_diff(raw["y5"], k), yoy_pct(raw["dxy"], k), yoy_pct(raw["oil"], k)
        if None in (a, b, c):
            continue
        ym.append(k); d5.append(a); dd.append(b); do.append(c)

    z5, zd, zo = _zscore(d5), _zscore(dd), _zscore(do)
    return {
        "fci":       _compose(ym, z5, zd, zo, ism, OIL_WEIGHT),  # 50% oil blend (headline)
        "fci_exoil": _compose(ym, z5, zd, zo, ism, 0.0),         # rates + dollar only
    }


def build_fci(ism_series, bars=BARS, oil_weight=OIL_WEIGHT):
    """Single-variant convenience wrapper (kept for compatibility)."""
    s = build_fci_set(ism_series, bars)
    return s["fci"] if oil_weight else s["fci_exoil"]


if __name__ == "__main__":
    import json, re
    src = open("data/data.js").read()
    D = json.loads(re.sub(r"^window\.TGL_DATA\s*=\s*", "", src).rstrip().rstrip(";"))
    s = build_fci_set(D["cycle"]["ism"])
    for name, arr in s.items():
        print(f"{name:10s}: {len(arr)} pts | {arr[0]['d']} -> {arr[-1]['d']} | last {arr[-1]['v']}")
