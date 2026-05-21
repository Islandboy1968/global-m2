#!/usr/bin/env python3
"""
US Total Liquidity — computed server-side from FRED, written into data.js as TGL_DATA["us"].

Net liquidity (the GMI "US Total Liquidity" measure):
    NEW (broad) = Fed balance sheet (WALCL) - TGA - RRP + bank loans
    OLD (narrow)= Fed balance sheet (WALCL) - TGA - RRP + Treasury securities held by banks

All series come from FRED's KEYLESS csv endpoint (fredgraph.csv) so there is no
API key in the repo and no browser CORS problem — the GitHub Action fetches the
numbers and bakes them into data.js. The browser only ever reads static data.

Units: WALCL & TGA are $millions; RRP, TOTLL, SBCACBW are $billions (x1000 -> $M).
Output values are in $ trillions to match the global series.

BTC/NDX for the US overlay charts are NOT fetched here — the dashboard reuses
TGL_DATA["btc"] and TGL_DATA["ndx"] already produced by the global pipeline.
"""
import csv, io, urllib.request, subprocess, datetime as dt

FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={id}&cosd={start}"

# series_id -> unit multiplier to reach $millions
SERIES = {
    "WALCL":          1.0,     # Fed balance sheet, $M, weekly (Wed)
    "WTREGEN":        1.0,     # Treasury General Account, $M, weekly (Wed)
    "RRPONTSYD":      1000.0,  # Overnight reverse repo, $B -> $M, daily
    "TOTLL":          1000.0,  # Loans & leases in bank credit, $B -> $M, weekly (Wed)
    "SBCACBW027NBOG": 1000.0,  # Treasury & agency securities held by banks, $B -> $M, weekly (Wed)
}

START = "2010-01-01"   # FRED returns from each series' own start; harmless if earlier than data


def _http_get(url, timeout=30):
    """Fetch a URL as text. Try urllib first, fall back to curl (both present on
    GitHub runners). Two independent transports so a quirk in one never blocks us."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "global-m2-pipeline"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception as urllib_err:
        try:
            out = subprocess.run(
                ["curl", "-fsSL", "--max-time", str(timeout), url],
                capture_output=True, text=True, timeout=timeout + 5,
            )
            if out.returncode == 0 and out.stdout:
                return out.stdout
            raise RuntimeError(f"curl rc={out.returncode}")
        except Exception as curl_err:
            raise RuntimeError(f"urllib={urllib_err!r}; curl={curl_err!r}")


def _parse_csv(text):
    out = {}
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or row[0] == "observation_date":
            continue
        d, v = row[0].strip(), row[1].strip()
        if v in (".", "", "NA"):
            continue
        try:
            out[d] = float(v)
        except ValueError:
            continue
    return out


def _fetch(series_id, start=START, timeout=30, retries=3):
    """Return {date_str: float} from FRED's keyless CSV endpoint."""
    url = FRED_CSV.format(id=series_id, start=start)
    last = None
    for attempt in range(retries):
        try:
            out = _parse_csv(_http_get(url, timeout=timeout))
            if out:
                return out
            last = "empty"
        except Exception as e:
            last = repr(e)
    raise RuntimeError(f"FRED {series_id}: failed after {retries} tries: {last}")


def _closest_before(m, ds, lookback=14):
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


def build_us():
    """Return the TGL_DATA['us'] block, or raise on hard failure."""
    raw = {s: _fetch(s) for s in SERIES}

    walcl = raw["WALCL"]
    tga, rrp = raw["WTREGEN"], raw["RRPONTSYD"]
    loans, secs = raw["TOTLL"], raw["SBCACBW027NBOG"]

    dates = sorted(walcl)  # WALCL weekly grid is the master calendar
    rows = []
    for d in dates:
        w = walcl[d]
        t = _closest_before(tga, d)
        r = _closest_before(rrp, d)
        l = _closest_before(loans, d)
        s = _closest_before(secs, d)
        if None in (t, r, l, s):
            continue
        base = w - t - r * SERIES["RRPONTSYD"]
        new_liq = (base + l * SERIES["TOTLL"]) / 1e6   # $tn
        old_liq = (base + s * SERIES["SBCACBW027NBOG"]) / 1e6
        rows.append({"d": d, "vn": new_liq, "vo": old_liq})

    # 52-week YoY on the weekly grid
    vn = [x["vn"] for x in rows]
    vo = [x["vo"] for x in rows]
    yn = [None] * len(rows)
    yo = [None] * len(rows)
    for i in range(len(rows)):
        j = i - 52
        if j >= 0 and vn[j]:
            yn[i] = (vn[i] / vn[j] - 1) * 100
        if j >= 0 and vo[j]:
            yo[i] = (vo[i] / vo[j] - 1) * 100
    yns = _trailing_avg(yn, 13)   # ~3-month trailing average of YoY
    yos = _trailing_avg(yo, 13)

    series = []
    for i, x in enumerate(rows):
        series.append({
            "d":  x["d"],
            "vn": round(x["vn"], 4),
            "vo": round(x["vo"], 4),
            "yn": (round(yn[i], 2) if yn[i] is not None else None),
            "yns": (round(yns[i], 2) if yns[i] is not None else None),
            "yo": (round(yo[i], 2) if yo[i] is not None else None),
            "yos": (round(yos[i], 2) if yos[i] is not None else None),
        })

    last = series[-1]
    summary = {
        "latest": last["d"],
        "new_tn": last["vn"], "old_tn": last["vo"],
        "yoy_new": last["yn"], "yoy_new_s": last["yns"],
        "yoy_old": last["yo"], "yoy_old_s": last["yos"],
    }
    return {"lag_days": 90, "summary": summary, "series": series}


if __name__ == "__main__":
    us = build_us()
    s = us["summary"]
    print(f"US points: {len(us['series'])} | latest {s['latest']} | "
          f"new ${s['new_tn']:.2f}T (YoY {s['yoy_new']}%) | "
          f"old ${s['old_tn']:.2f}T (YoY {s['yoy_old']}%)")
