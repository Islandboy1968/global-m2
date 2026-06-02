#!/usr/bin/env python3
"""
Global / US PMI — seeded from a Bloomberg export (the only way to get the long
history, which S&P Global paywalls), then extendable monthly from the free
S&P Global / J.P.Morgan press releases at pmi.spglobal.com.

The J.P.Morgan Global Manufacturing PMI and the S&P Global US Manufacturing PMI
are proprietary; full history is subscription-only. Export them once from a
Bloomberg terminal into  data/pmi_seed.csv  with these columns (header required):

    date,world_pmi,us_pmi
    2007-01-01,52.4,51.9
    ...

  - date      = first of the month, YYYY-MM-DD, monthly
  - world_pmi = J.P.Morgan Global Manufacturing PMI   (Bloomberg: MPMIGLMA Index)
  - us_pmi    = S&P Global US Manufacturing PMI        (Bloomberg: MPMIUSMA Index)
  - either column may be left blank per row; blank cells are skipped

This builder reads that seed into TGL_DATA["pmi"]. If the file is missing or has
no usable rows, the bucket is None and the dependent chart auto-hides — so it is
safe to ship before the data exists.
"""
import csv, os, datetime as dt

SEED = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "pmi_seed.csv")
COLS = ("world_pmi", "us_pmi")


def build_pmi(path=SEED):
    """Return the TGL_DATA['pmi'] block: {world_pmi: [...]|None, us_pmi: [...]|None}."""
    acc = {c: [] for c in COLS}
    if not os.path.exists(path):
        print(f"  pmi: no seed file at {path} (chart will hide until provided)")
        return {c: None for c in COLS}
    try:
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                d = (row.get("date") or "").strip()
                try:
                    dt.datetime.strptime(d, "%Y-%m-%d")
                except ValueError:
                    continue
                for c in COLS:
                    v = (row.get(c) or "").strip()
                    if v:
                        try:
                            acc[c].append({"d": d, "v": round(float(v), 2)})
                        except ValueError:
                            pass
    except Exception as e:
        print("  pmi: seed read FAILED:", str(e)[:80])
        return {c: None for c in COLS}
    out = {}
    for c in COLS:
        arr = sorted(acc[c], key=lambda r: r["d"]) or None
        out[c] = arr
        if arr:
            print(f"  pmi/{c:10s}: {len(arr):4d} pts | {arr[0]['d']} -> {arr[-1]['d']} (last {arr[-1]['v']})")
        else:
            print(f"  pmi/{c:10s}: none in seed")
    return out


if __name__ == "__main__":
    for k, arr in build_pmi().items():
        print(f"{k}: {len(arr) if arr else 0} pts")
