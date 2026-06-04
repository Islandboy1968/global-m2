#!/usr/bin/env python3
"""
US Total Liquidity — computed server-side from FRED, written into data.js as TGL_DATA["us"].

Net liquidity (the GMI "US Total Liquidity" measure):
    NEW (broad) = Fed balance sheet (WALCL) - TGA - RRP + total bank credit (loans + securities)
    OLD (narrow)= Fed balance sheet (WALCL) - TGA - RRP + Treasury securities held by banks

All series come from FRED's KEYLESS csv endpoint (fredgraph.csv) so there is no
API key in the repo and no browser CORS problem — the GitHub Action fetches the
numbers and bakes them into data.js. The browser only ever reads static data.

The series is built on a DAILY calendar grid: the Fed balance sheet (WALCL, weekly)
and bank-credit series (weekly) are forward-filled, while the two volatile swing
factors are taken at DAILY frequency — TGA from the U.S. Treasury's Daily Treasury
Statement (api.fiscaldata.treasury.gov, public/no key) and RRP from FRED (daily).
So the US line moves day-to-day and runs through the latest published day, instead
of stepping only on WALCL's weekly Wednesday grid. If the Treasury DTS is
unreachable, TGA falls back to FRED's weekly WTREGEN and the series still builds.

Units: WALCL & TGA are $millions; RRP, TOTBKCR, SBCACBW are $billions (x1000 -> $M).
Output values are in $ trillions to match the global series.

BTC/QQQ for the US overlay charts are NOT fetched here — the dashboard reuses
TGL_DATA["btc"] and TGL_DATA["ndx"] (QQQ) already produced by the global pipeline.
"""
import datetime as dt
import json, time, urllib.request
from fred import fred_series
from tv_pull import pull_series

# series_id -> unit multiplier to reach $millions
SERIES = {
    "WALCL":          1.0,     # Fed balance sheet, $M, weekly (Wed)
    "WTREGEN":        1.0,     # Treasury General Account, $M, weekly (Wed) — DTS fallback
    "RRPONTSYD":      1000.0,  # Overnight reverse repo, $B -> $M, daily
    "TOTBKCR":        1000.0,  # Bank credit, all commercial banks (loans + securities), $B -> $M, monthly
    "SBCACBW027NBOG": 1000.0,  # Treasury & agency securities held by banks, $B -> $M, weekly (Wed)
}

START = "2010-01-01"   # FRED returns from each series' own start; harmless if earlier than data

# Large daily FRED series that reliably read-time-out on FRED's keyless CSV
# endpoint from the GitHub Actions runner — RRPONTSYD (overnight reverse repo,
# daily since 2013) and DGS5 (5y Treasury yield, daily since 1962). FRED's
# TradingView passthrough mirrors the identical series and serves them fast and
# reliably from the runner (it's the same path build_inflation / build_labor /
# … already use for their FRED series, e.g. FRED:T10YIE pulls cleanly every
# run). So for these two we hit TradingView first and keep the CSV as a backup;
# every other series keeps the CSV as primary with TradingView as the safety net.
TV_FIRST = {"RRPONTSYD", "DGS5"}
_TV_RES = "1D"     # both fallback series are daily
_TV_BARS = 6200    # ~17yr of daily bars; frontend windows what it shows

# Unit normalization. FRED's keyless CSV returns these magnitude series in FRED's
# canonical unit (WALCL/WTREGEN in $millions; RRP/TOTBKCR/SBCACBW in $billions;
# interest in $billions), but FRED's TradingView passthrough returns them in
# ACTUAL DOLLARS — a 1e6/1e9 difference that silently corrupts the US arithmetic
# when the CSV times out and we fall back to TradingView. We snap every fetched
# value back to FRED's canonical unit, detected by magnitude: canonical values
# for these series are all < 1e8, dollar values are all > 1e11, so a single
# threshold separates them cleanly and stays correct as the series grow. Series
# not listed here (rates/levels like DGS5, CIVPART) read identically from both
# sources and are passed through untouched.
_CANON_DIV = {"WALCL": 1e6, "WTREGEN": 1e6, "RRPONTSYD": 1e9, "TOTBKCR": 1e9,
              "SBCACBW027NBOG": 1e9, "A091RC1Q027SBEA": 1e9}
_DOLLARS_THRESHOLD = 1e8


def _to_canonical(series_id, m):
    """Convert a {date: value} map to the series' canonical FRED unit, dividing
    any actual-dollars values (from TradingView) back down. No-op for series with
    no known unit or values already in canonical range."""
    div = _CANON_DIV.get(series_id)
    if not div or not m:
        return m
    return {d: (v / div if abs(v) > _DOLLARS_THRESHOLD else v) for d, v in m.items()}


def _from_csv(series_id, timeout, retries):
    """{epoch_seconds: float} from FRED's keyless CSV endpoint. We deliberately
    do NOT send FRED's &cosd= range parameter — that makes FRED regenerate a
    custom CSV and hangs indefinitely; the full series returns FRED's cached CSV."""
    return {epoch: v for epoch, v in fred_series(series_id, retries=retries, timeout=timeout)}


def _from_tradingview(series_id):
    """{epoch_seconds: float} from FRED's TradingView passthrough (FRED:<id>)."""
    return {epoch: v for epoch, v in pull_series(f"FRED:{series_id}", _TV_RES, _TV_BARS, retries=3)}


def _fetch(series_id, start=START, timeout=30, retries=4):
    """Return {YYYY-MM-DD: float} for a FRED series, resilient to either source
    failing. The two large daily series in TV_FIRST go to TradingView first
    (the CSV endpoint times out on them from the runner no matter the timeout);
    all others use the CSV first. Whichever is primary, the other is tried as a
    fallback, so a transient outage on one source no longer blanks the block.
    One fetcher serves the whole pipeline (big_picture.py imports this too)."""
    csv = ("FRED CSV", lambda: _from_csv(series_id, timeout, retries))
    tv = ("TradingView FRED", lambda: _from_tradingview(series_id))
    order = [tv, csv] if series_id in TV_FIRST else [csv, tv]

    raw, last_err = None, None
    for name, fn in order:
        try:
            raw = fn()
            if raw:
                break
            last_err = f"{name}: no data rows"
            raw = None
        except Exception as e:
            last_err = f"{name}: {e!r}"
            print(f"    {series_id} via {name} failed: {str(e)[:80]}")
            raw = None
    if not raw:
        raise RuntimeError(f"FRED {series_id}: all sources failed ({last_err})")

    out = {}
    for epoch, v in raw.items():
        d = dt.datetime.fromtimestamp(epoch, dt.timezone.utc).strftime("%Y-%m-%d")
        if d >= start:
            out[d] = v
    return _to_canonical(series_id, out)


def _closest_before(m, ds, lookback=45):
    """Latest value on or before ds (handles weekly vs daily frequency gaps)."""
    if ds in m:
        return m[ds]
    d = dt.date.fromisoformat(ds)
    for _ in range(lookback):
        d -= dt.timedelta(days=1)
        k = d.isoformat()
        if k in m:
            return m[k]
    return None


def _trailing_avg(arr, n):
    out = [None] * len(arr)
    for i in range(len(arr)):
        w = [v for v in arr[max(0, i - n + 1):i + 1] if v is not None]
        out[i] = sum(w) / len(w) if w else None
    return out


# SBCACBW027NBOG feeds ONLY the Narrow measure and is allowed to be missing: it is
# unavailable on TradingView and times out intermittently on FRED's CSV, and one
# optional input must never blank the whole tab. When it's missing the Broad series
# still ships and the Narrow leg is emitted as null (update_data.py carries the last
# good Narrow values forward per-series).

# ---- Daily TGA from the U.S. Treasury Daily Treasury Statement (public, no key) --
_DTS_URL = ("https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
            "/v1/accounting/dts/operating_cash_balance")
# DTS account_type for the TGA closing balance. The modern label has been used
# since Apr-2022; the older "Federal Reserve Account" label covers prior history,
# so honouring both gives a continuous daily series.
_TGA_LABEL = "Treasury General Account (TGA) Closing Balance"
_TGA_LABELS = (_TGA_LABEL, "Federal Reserve Account")


def _fetch_tga_daily(start=START, retries=3):
    """Daily TGA closing balance ($millions) from the Treasury DTS, as
    {YYYY-MM-DD: $M}. Returns {} on failure so the caller falls back to WTREGEN."""
    out, page = {}, 1
    while True:
        q = (f"?fields=record_date,account_type,close_today_bal"
             f"&filter=record_date:gte:{start}"
             f"&sort=-record_date&page[size]=10000&page[number]={page}")
        body = None
        for attempt in range(retries):
            try:
                req = urllib.request.Request(
                    _DTS_URL + q, headers={"User-Agent": "tgl-dashboard/1.0"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    body = json.loads(r.read().decode())
                break
            except Exception as e:
                if attempt == retries - 1:
                    print(f"  US: DTS TGA page {page} failed: {str(e)[:70]}")
                    return out
                time.sleep(1.5 * (attempt + 1))
        rows = (body or {}).get("data", [])
        if not rows:
            break
        for row in rows:
            at = row.get("account_type")
            if at not in _TGA_LABELS:
                continue
            d, v = row.get("record_date"), row.get("close_today_bal")
            if not d or v in (None, "", "null"):
                continue
            try:
                val = float(v)
            except (TypeError, ValueError):
                continue
            # prefer the modern TGA label where both labels exist for a date
            if at == _TGA_LABEL or d not in out:
                out[d] = val
        meta = (body or {}).get("meta", {})
        if page >= int(meta.get("total-pages", page) or page):
            break
        page += 1
    return out


def _tga_plausible(m):
    """True if the latest TGA value is a sane balance ($10B–$10T, in $millions)."""
    if not m:
        return False
    latest = m[max(m)]
    return 1e4 <= latest <= 1e7


def _ffill_onto(grid, m):
    """Forward-fill a {date: value} map onto a sorted list of ISO date strings."""
    if not m:
        return [None] * len(grid)
    items = sorted(m.items())
    out = [None] * len(grid)
    j, cur, n = 0, None, len(items)
    for i, day in enumerate(grid):
        while j < n and items[j][0] <= day:
            cur = items[j][1]; j += 1
        out[i] = cur
    return out


def build_us():
    """Return the TGL_DATA['us'] block, or raise if a CORE input is unavailable.

    Per-input tolerant: a single series failing all its sources no longer aborts
    the build. Only a missing CORE input (needed for the Broad measure) raises,
    in which case update_data.py carries the whole block forward."""
    raw = {}
    for s in SERIES:
        try:
            raw[s] = _fetch(s)
        except Exception as e:
            print(f"  US: {s} unavailable from all sources ({str(e)[:60]})")
            raw[s] = {}

    # Daily TGA from the Treasury DTS (so the line moves day-to-day); fall back to
    # FRED's weekly WTREGEN if the DTS is unreachable or returns an implausible value.
    tga = _fetch_tga_daily()
    if _tga_plausible(tga):
        print(f"  US: TGA daily from Treasury DTS — {len(tga)} days, latest {max(tga)}")
    else:
        tga = raw.get("WTREGEN", {})
        print("  US: DTS TGA unavailable/implausible — using weekly WTREGEN")

    walcl, rrp = raw["WALCL"], raw["RRPONTSYD"]
    credit, secs = raw["TOTBKCR"], raw["SBCACBW027NBOG"]

    need = {"WALCL": walcl, "RRPONTSYD": rrp, "TOTBKCR": credit, "TGA": tga}
    missing = [k for k, v in need.items() if not v]
    if missing:
        raise RuntimeError(f"US core inputs unavailable: {', '.join(missing)}")

    # Daily calendar grid from WALCL's start to the freshest daily input (capped at
    # today). Weekly series (WALCL, bank credit, securities) are forward-filled; TGA
    # and RRP carry their daily movement so the series advances every day.
    today = dt.date.today().isoformat()
    end_d = min(max(max(walcl), max(tga), max(rrp)), today)
    start_d = min(walcl)
    grid, cur, last = [], dt.date.fromisoformat(start_d), dt.date.fromisoformat(end_d)
    while cur <= last:
        grid.append(cur.isoformat()); cur += dt.timedelta(days=1)

    W, T, R = _ffill_onto(grid, walcl), _ffill_onto(grid, tga), _ffill_onto(grid, rrp)
    C, S = _ffill_onto(grid, credit), _ffill_onto(grid, secs)

    rows = []
    for i, d in enumerate(grid):
        w, t, r, c, s = W[i], T[i], R[i], C[i], S[i]
        if None in (w, t, r, c):          # Broad essentials must all be present
            continue
        base = w - t - r * SERIES["RRPONTSYD"]
        new_liq = (base + c * SERIES["TOTBKCR"]) / 1e6   # Broad, $tn
        old_liq = ((base + s * SERIES["SBCACBW027NBOG"]) / 1e6
                   if s is not None else None)            # Narrow, $tn (optional)
        rows.append({"d": d, "vn": new_liq, "vo": old_liq})

    if not rows:
        raise RuntimeError("US: no rows (core inputs produced no overlapping dates)")

    # Value sanity guard: US Total Liquidity (Broad) is ~$20-30tn. A value outside
    # a wide plausibility band means a unit/source mismatch slipped through — raise
    # so update_data carries forward the last good block rather than shipping a
    # corrupt number (a wrong value is worse than a stale one).
    _vn_latest = rows[-1]["vn"]
    if not (5.0 <= _vn_latest <= 80.0):
        raise RuntimeError(f"US Broad implausible (${_vn_latest:.3g}tn) — likely a "
                           f"source unit mismatch; refusing to ship")

    # YoY vs ~365 days earlier on the daily grid (rows are contiguous days once the
    # leading warm-up is skipped), with a ~91-day trailing average for the smoothed line.
    vn = [x["vn"] for x in rows]
    vo = [x["vo"] for x in rows]
    yn = [None] * len(rows)
    yo = [None] * len(rows)
    for i in range(len(rows)):
        j = i - 365
        if j >= 0 and vn[j]:
            yn[i] = (vn[i] / vn[j] - 1) * 100
        if j >= 0 and vo[i] is not None and vo[j]:
            yo[i] = (vo[i] / vo[j] - 1) * 100
    yns = _trailing_avg(yn, 91)   # ~3-month trailing average of YoY
    yos = _trailing_avg(yo, 91)

    series = []
    for i, x in enumerate(rows):
        series.append({
            "d":  x["d"],
            "vn": round(x["vn"], 4),
            "vo": (round(x["vo"], 4) if x["vo"] is not None else None),
            "yn": (round(yn[i], 2) if yn[i] is not None else None),
            "yns": (round(yns[i], 2) if yns[i] is not None else None),
            "yo": (round(yo[i], 2) if yo[i] is not None else None),
            "yos": (round(yos[i], 2) if yos[i] is not None else None),
        })

    last = series[-1]
    # latest row that actually has a Narrow value (for the summary headline)
    last_vo = next((x for x in reversed(series) if x["vo"] is not None), None)
    summary = {
        "latest": last["d"],
        "new_tn": last["vn"], "old_tn": (last_vo["vo"] if last_vo else None),
        "yoy_new": last["yn"], "yoy_new_s": last["yns"],
        "yoy_old": (last_vo["yo"] if last_vo else None),
        "yoy_old_s": (last_vo["yos"] if last_vo else None),
        "narrow_as_of": (last_vo["d"] if last_vo else None),
    }
    return {"lag_days": 90, "summary": summary, "series": series}


if __name__ == "__main__":
    us = build_us()
    s = us["summary"]
    _old = f"${s['old_tn']:.2f}T" if s['old_tn'] is not None else "n/a"
    print(f"US points: {len(us['series'])} | latest {s['latest']} | "
          f"new ${s['new_tn']:.2f}T (YoY {s['yoy_new']}%) | old {_old} (YoY {s['yoy_old']})")
