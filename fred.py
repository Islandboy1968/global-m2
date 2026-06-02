#!/usr/bin/env python3
"""
Direct FRED fetch — public CSV endpoint, no API key.

TradingView's "FRED:" passthrough only mirrors a subset of FRED, so less-common
series (e.g. the CPI component codes CUSR0000SACL1E / SASLE / SA0L2) aren't
reachable that way. FRED's public CSV endpoint returns the full history with no
key and DOES work from the GitHub Actions runner (verified via probe — the dev
sandbox blocks it, but the runner has open internet). A descriptive User-Agent
is sent to be a good citizen.

    https://fred.stlouisfed.org/graph/fredgraph.csv?id=<SERIES_ID>

Returns the same (epoch_seconds, value) shape as tv_pull.pull_series.
"""
import csv, io, time, datetime as dt, urllib.request

_UA = "global-m2 data pipeline (rp@rpbeachhouse.com)"


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
            time.sleep(min(12, 2 ** attempt))
    raise RuntimeError(f"FRED {series_id}: failed after {retries} tries: {last_err}")


if __name__ == "__main__":
    for sid in ("CPIAUCSL", "CUSR0000SACL1E"):
        pts = fred_series(sid)
        print(f"{sid}: {len(pts)} pts | last {pts[-1]}")
