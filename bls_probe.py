#!/usr/bin/env python3
"""
One-off reachability probe — run in GitHub Actions (open internet) to learn which
direct data hosts actually work from the runner (the dev sandbox blocks them all).
Tests BLS API for the CPI components and FRED CSV (incl. a current OECD CLI code).
Prints a compact report to the Actions log. Safe to delete after.
"""
import urllib.request, urllib.parse, json, csv, io

UA = {"User-Agent": "global-m2 research (rp@rpbeachhouse.com)"}

def bls_v2(seriesids, startyear="2014", endyear="2026"):
    body = json.dumps({"seriesid": seriesids, "startyear": startyear, "endyear": endyear}).encode()
    req = urllib.request.Request("https://api.bls.gov/publicAPI/v2/timeseries/data/",
                                 data=body, headers={**UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())

def fred_csv(sid):
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    rows = list(csv.reader(io.StringIO(text)))[1:]
    rows = [x for x in rows if len(x) >= 2 and x[1] not in ("", ".")]
    return rows

print("=== BLS API v2 (no key) — CPI components ===")
try:
    j = bls_v2(["CUSR0000SACL1E", "CUSR0000SASLE", "CUSR0000SA0L2"])
    print("status:", j.get("status"), "| messages:", j.get("message"))
    for s in j.get("Results", {}).get("series", []):
        d = s.get("data", [])
        if d:
            print(f"  {s['seriesID']}: {len(d)} pts  {d[-1]['year']}-{d[-1]['period']} .. {d[0]['year']}-{d[0]['period']}  last={d[0]['value']}")
        else:
            print(f"  {s['seriesID']}: NO DATA")
except Exception as e:
    print("  BLS v2 ERR:", repr(e)[:160])

print("=== FRED CSV direct ===")
for sid in ["CPIAUCSL", "USALOLITONOSTSAM", "OECDLOLITONOSTSAM", "CUSR0000SACL1E"]:
    try:
        rows = fred_csv(sid)
        print(f"  {sid}: {len(rows)} pts  first={rows[0][0]} last={rows[-1][0]}={rows[-1][1]}")
    except Exception as e:
        print(f"  {sid}: ERR {repr(e)[:100]}")
