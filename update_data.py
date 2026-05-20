"""
Global M2 Dashboard — data pipeline.

Global M2 = sum of broad money (M2/M3) for the G5 economies, USD-normalised,
daily cadence with FX revaluation, 4-year rolling window.

Sources (all public, no API keys):
    US M2        FRED M2SL                                  monthly  USD bn
    EZ M3        ECB SDMX BSI.M.U2.Y.V.M30.X.1.U2.2300.Z01.E   monthly  EUR mn
    China M2     chinadata.live /api/v2/data                 monthly  CNY 100mn
    Japan M2     FRED MABMM301JPM189N                        monthly  JPY (stale to Nov 2023)
    UK M2        BoE IADB LPMVWYH                            monthly  GBP mn

FX  ECB daily reference rates (vs EUR) for USD CNY JPY GBP

Output: data/data.js (JS file defining window.GLOBAL_M2_DATA)
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
import datetime as dt
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent / "data"
OUT_DIR.mkdir(exist_ok=True)

TODAY = dt.date.today()
WINDOW_YEARS = 4
START_DATE = dt.date(TODAY.year - WINDOW_YEARS, TODAY.month, TODAY.day)

# ---------------------------------------------------------------------------
# fetch helpers
# ---------------------------------------------------------------------------

def _get(url: str, ua: str | None = None, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url)
    if ua:
        req.add_header("User-Agent", ua)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_fred_csv(series_id: str) -> dict[str, float]:
    """FRED CSV. Important: do NOT set Mozilla UA — Akamai blocks it."""
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}"
    raw = _get(url).decode("utf-8")
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        date_str = row.get("observation_date") or row.get("DATE")
        val_str = row.get(series_id, "").strip()
        if not date_str or not val_str or val_str == ".":
            continue
        try:
            out[date_str] = float(val_str)
        except ValueError:
            continue
    return out


def fetch_ecb_m3() -> dict[str, float]:
    url = (
        "https://data-api.ecb.europa.eu/service/data/BSI/"
        "M.U2.Y.V.M30.X.1.U2.2300.Z01.E?format=csvdata"
    )
    raw = _get(url).decode("utf-8")
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        date_str = row["TIME_PERIOD"]
        try:
            val = float(row["OBS_VALUE"])
        except (ValueError, KeyError):
            continue
        out[f"{date_str}-01"] = val
    return out


def fetch_china_m2() -> dict[str, float]:
    url = "https://chinadata.live/api/v2/data/china-m2-money-supply"
    payload = json.loads(_get(url, ua="Mozilla/5.0").decode("utf-8"))
    out: dict[str, float] = {}
    for pt in payload["data"]["data"]:
        date_str = pt["date"]
        out[f"{date_str}-01"] = float(pt["value"]) * 1e8  # 100mn CNY -> CNY
    return out


def fetch_boe_uk_m2() -> dict[str, float]:
    url = (
        "https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
        "?csv.x=yes&Datefrom=01/Jan/2021&Dateto=01/Dec/2026"
        "&SeriesCodes=LPMVWYH&UsingCodes=Y&CSVF=TT&VPD=Y&VFD=N"
    )
    raw = _get(url, ua="Mozilla/5.0").decode("utf-8")
    out: dict[str, float] = {}
    data_started = False
    for line in raw.splitlines():
        if line.startswith("DATE,"):
            data_started = True
            continue
        if not data_started or not line.strip():
            continue
        try:
            date_str, val_str = line.split(",", 1)
            d = dt.datetime.strptime(date_str.strip(), "%d %b %Y").date()
            out[d.isoformat()] = float(val_str.strip())
        except Exception:
            continue
    return out


def fetch_ecb_fx(currency: str) -> dict[str, float]:
    url = (
        "https://data-api.ecb.europa.eu/service/data/EXR/"
        f"D.{currency}.EUR.SP00.A?format=csvdata"
    )
    raw = _get(url).decode("utf-8")
    out: dict[str, float] = {}
    for row in csv.DictReader(io.StringIO(raw)):
        date_str = row["TIME_PERIOD"]
        try:
            out[date_str] = float(row["OBS_VALUE"])
        except (ValueError, KeyError):
            continue
    return out


# ---------------------------------------------------------------------------
# catalogue
# ---------------------------------------------------------------------------

def load_components() -> dict[str, dict]:
    print("Fetching M2 series...", flush=True)
    out = {}

    us = fetch_fred_csv("M2SL")
    print(f"  US M2:   {len(us)} obs, last {max(us)} = {us[max(us)]:.1f} (USD bn)")
    out["US M2"] = {"currency": "USD", "native_unit_to_bn": 1.0, "values": us, "country": "United States"}

    ez = fetch_ecb_m3()
    print(f"  EZ M3:   {len(ez)} obs, last {max(ez)} = {ez[max(ez)]:.0f} (EUR mn)")
    out["EZ M3"] = {"currency": "EUR", "native_unit_to_bn": 1e-3, "values": ez, "country": "Eurozone"}

    cn = fetch_china_m2()
    print(f"  China:   {len(cn)} obs, last {max(cn)} = {cn[max(cn)]:,.0f} (CNY)")
    out["China M2"] = {"currency": "CNY", "native_unit_to_bn": 1e-9, "values": cn, "country": "China"}

    jp = fetch_fred_csv("MABMM301JPM189N")
    stale = max(jp) < (TODAY.isoformat()[:7] + "-01")
    print(f"  Japan:   {len(jp)} obs, last {max(jp)} = {jp[max(jp)]:,.0f} (JPY){'  STALE' if stale else ''}")
    out["Japan M2"] = {"currency": "JPY", "native_unit_to_bn": 1e-9, "values": jp, "country": "Japan"}

    uk = fetch_boe_uk_m2()
    print(f"  UK M2:   {len(uk)} obs, last {max(uk)} = {uk[max(uk)]:,.0f} (GBP mn)")
    out["UK M2"] = {"currency": "GBP", "native_unit_to_bn": 1e-3, "values": uk, "country": "United Kingdom"}

    return out


# ---------------------------------------------------------------------------
# transformation
# ---------------------------------------------------------------------------

def daily_grid(start: dt.date, end: dt.date) -> list[str]:
    out = []
    d = start
    while d <= end:
        out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def reindex_to_daily(values: dict[str, float], grid: list[str]) -> list[float | None]:
    items = sorted(values.items())
    out: list[float | None] = []
    last_val = None
    idx = 0
    for day in grid:
        while idx < len(items) and items[idx][0] <= day:
            last_val = items[idx][1]
            idx += 1
        out.append(last_val)
    return out


def build_daily_usd_series(component: dict, fx_to_eur: dict, grid: list[str]) -> list[float | None]:
    native_daily = reindex_to_daily(component["values"], grid)
    ccy = component["currency"]
    to_bn = component["native_unit_to_bn"]
    out = []
    for i in range(len(grid)):
        v = native_daily[i]
        if v is None:
            out.append(None); continue
        v_bn_native = v * to_bn
        if ccy == "EUR":
            v_eur_bn = v_bn_native
        else:
            rate = fx_to_eur[ccy][i]
            if not rate: out.append(None); continue
            v_eur_bn = v_bn_native / rate
        usd_per_eur = fx_to_eur["USD"][i]
        if not usd_per_eur: out.append(None); continue
        out.append(v_eur_bn * usd_per_eur)
    return out


def yoy_pct(series: list[float | None], grid: list[str]) -> list[float | None]:
    out = []
    by_date = {grid[i]: i for i in range(len(grid))}
    for i, day in enumerate(grid):
        d = dt.date.fromisoformat(day)
        try:
            ly = dt.date(d.year - 1, d.month, d.day).isoformat()
        except ValueError:
            ly = dt.date(d.year - 1, d.month, 28).isoformat()
        j = by_date.get(ly)
        v = series[i]
        if j is None or v is None:
            out.append(None); continue
        v0 = series[j]
        if v0 is None or v0 == 0:
            out.append(None); continue
        out.append((v / v0 - 1) * 100.0)
    return out


def main() -> None:
    print(f"=== Global M2 build: {TODAY.isoformat()} ===")
    components = load_components()

    print("Fetching ECB FX...", flush=True)
    fx = {}
    for c in ["USD", "GBP", "JPY", "CNY"]:
        fx[c] = fetch_ecb_fx(c)
        print(f"  {c}/EUR: {len(fx[c])} obs, last {max(fx[c])} = {fx[c][max(fx[c])]:.4f}")

    grid = daily_grid(START_DATE, TODAY)
    n = len(grid)
    print(f"Daily grid: {n} days, {grid[0]} -> {grid[-1]}")

    fx_daily = {c: reindex_to_daily(fx[c], grid) for c in ["USD", "GBP", "JPY", "CNY"]}
    fx_daily["EUR"] = [1.0] * n

    component_usd: dict[str, list[float | None]] = {}
    component_latest: dict[str, dict] = {}
    for name, comp in components.items():
        usd = build_daily_usd_series(comp, fx_daily, grid)
        component_usd[name] = usd
        latest_native_date = max(comp["values"])
        latest_native_val = comp["values"][latest_native_date]
        last_usd_today = next((v for v in reversed(usd) if v is not None), None)
        component_latest[name] = {
            "country": comp["country"],
            "currency": comp["currency"],
            "native_date": latest_native_date,
            "native_value": latest_native_val,
            "usd_bn_today": last_usd_today,
        }

    # Global M2 = sum of all M2 components
    total: list[float | None] = []
    for i in range(n):
        s = 0.0
        valid = True
        for name in components:
            v = component_usd[name][i]
            if v is None: valid = False; break
            s += v
        total.append(s if valid else None)

    total_yoy = yoy_pct(total, grid)

    last_idx = next((i for i in range(n - 1, -1, -1) if total[i] is not None), None)
    print()
    print(f"Latest reading ({grid[last_idx]}):")
    print(f"  Global M2:  ${total[last_idx]/1000:.2f}T  YoY {total_yoy[last_idx]:+.2f}%")
    print()
    for name, info in component_latest.items():
        if info["usd_bn_today"] is None: continue
        print(f"  {name:<12}  native last {info['native_date']:<12} USD ${info['usd_bn_today']/1000:>7.2f}T  ({info['country']})")

    payload = {
        "generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "today": TODAY.isoformat(),
        "window_start": START_DATE.isoformat(),
        "dates": grid,
        "global_m2_usd_bn": total,
        "global_m2_yoy_pct": total_yoy,
        "components": {
            name: {
                "country": components[name]["country"],
                "currency": components[name]["currency"],
                "values_usd_bn": component_usd[name],
                "latest": component_latest[name],
            }
            for name in components
        },
        "notes": {
            "Japan M2": "FRED mirror MABMM301JPM189N stops late 2023; last value carried forward. BoJ direct API is geo-blocked from typical sandboxes. JPY/USD FX still moves daily so the USD contribution still wobbles correctly, just on a flat native base.",
        },
    }
    out_json = OUT_DIR / "data.json"
    out_json.write_text(json.dumps(payload, default=lambda x: None))
    out_js = OUT_DIR / "data.js"
    out_js.write_text("window.GLOBAL_M2_DATA = " + json.dumps(payload, default=lambda x: None) + ";")
    print(f"\nWrote {out_json} ({out_json.stat().st_size:,} bytes)")
    print(f"Wrote {out_js} ({out_js.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
