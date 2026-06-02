#!/usr/bin/env python3
"""
Direct FRED fetch — public CSV endpoint, no API key.

TradingView's "FRED:" passthrough only mirrors a subset of FRED, so less-common
series (CPI components, OECD CLI aggregates, etc.) aren't reachable that way.
This module hits FRED's public CSV endpoint directly:

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>

which returns the full history with no key. Used by the inflation / labour
builders and for the OECD CLI. Returns the same (epoch_seconds, value) shape as
tv_pull.pull_series so the rest of the pipeline is unchanged.
"""
import csv, io, time, datetime as dt, urllib.request

_UA = "Mozilla/5.0 (global-m2 data pipeline)"
RECENT_SECS = 400 * 86400   # "current" = last observation within ~13 months


def fred_series(series_id, retries=4, timeout=30):
    """Return sorted list of (epoch_seconds, float) for a FRED series id.
    Raises RuntimeError after `retries` failed attempts."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    last_err = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                text = r.read().decode("utf-8", "replace")
            out = []
            rows = csv.reader(io.StringIO(text))
            next(rows, None)  # header: observation_date,<ID>
            for row in rows:
                if len(row) < 2:
                    continue
                ds, vs = row[0].strip(), row[1].strip()
                if vs in ("", ".", "NaN", "NA"):
                    continue
                try:
                    v = float(vs)
                    d = dt.datetime.strptime(ds, "%Y-%m-%d")
                except ValueError:
                    continue
                out.append((int(d.replace(tzinfo=dt.timezone.utc).timestamp()), v))
            if out:
                return sorted(out)
            last_err = "no data rows"
        except Exception as e:
            last_err = repr(e)
            time.sleep(min(15, 2 ** attempt))
    raise RuntimeError(f"FRED {series_id}: failed after {retries} tries: {last_err}")


def fred_first(candidates, min_pts=24):
    """Try each FRED series id; prefer the first that has >= min_pts AND is still
    being updated (last obs within RECENT_SECS). Fall back to the first with
    enough points if none are current. Returns (series_id, points) or (None, [])."""
    now = time.time()
    fallback = (None, [])
    for sid in candidates:
        try:
            pts = fred_series(sid)
            if pts and len(pts) >= min_pts:
                if not fallback[1]:
                    fallback = (sid, pts)
                if now - max(t for t, _ in pts) <= RECENT_SECS:
                    return sid, pts
                print(f"    FRED:{sid}: {len(pts)} pts but stale, trying next")
            else:
                print(f"    FRED:{sid}: too few pts, trying next")
        except Exception as e:
            print(f"    FRED:{sid}: {str(e)[:60]}")
    return fallback


if __name__ == "__main__":
    for sid in ("CPIAUCSL", "USALOLITONOSTSAM"):
        pts = fred_series(sid)
        print(f"{sid}: {len(pts)} pts | last {pts[-1]}")
