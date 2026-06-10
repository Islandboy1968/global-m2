#!/usr/bin/env python3
"""
Global Total Liquidity Index — the GMI-method headline liquidity measure.

This is NOT Global M2 and NOT a sum of central-bank balance sheets. It is the
layered GMI construction: per economy, Net Liquidity = central-bank balance sheet
(netted of government cash + draining facilities where that data exists — US only
today) + M2 (broad money), summed across the major economies in USD.

    Region Net Liquidity = (CB balance sheet − TGA − RRP)  +  M2     [× FX → USD]
    Global Total Liquidity = Σ regions

Why both terms: M2 captures the private credit/deposit side (bank lending creates
deposits), but it does NOT capture central-bank balance sheets — a distinct force,
shrinking under QT everywhere EXCEPT China. Reserves (the big balance-sheet item)
sit outside M2, so summing the two does not double-count (GMI's own
"Fed Net Liquidity + M2" recipe). Components are emitted as a DECOMPOSITION of the
one index (balance-sheets vs M2, and per-economy legs) — never as standalone
headline series.

Validated against GMI's published characterisation (live data, 2026-03):
  level ~$142T · YoY +7.7% (GMI quotes ~8%/yr) · leads BTC ~2mo at 0.96 corr
  (beats Global M2's coincident 0.95) — i.e. it reproduces both the growth rate
  AND the "liquidity leads risk assets" property. Raw CB-balance-sheets-only fails
  this (−0.2% YoY); Global M2 alone misses the balance-sheet + China dynamics.

v1 scope / known simplifications (flagged on the chart):
  - US leg netted (− TGA − RRP); other regions use gross balance sheet (no
    netting feed abroad).
  - Private layer = M2 everywhere; bank credit is a v2 refinement for the three
    economies that publish clean credit levels (US/EU/NZ).
  - NZ excluded: its M2 feed is dead (ends 2017-01).
  - China M2 via ECONOMICS:CNM2 (feed-first; see update_data.reconcile_china_override).
  - Monthly cadence (balance-sheet inputs are monthly).
  - Formula version is FNL + M2 (reproduces +8%); FNL + M2 + bank securities is a
    Raoul sign-off away (see SCOPE_TOTAL_LIQUIDITY.md §6).

Fail-safe: each economy's leg is independent; a failed pull drops that leg (logged)
rather than breaking the index. A leg whose data goes stale (>STALE_MONTHS behind
the others) is dropped so it can't truncate the whole series (the NZ failure mode).
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from tv_pull import pull_series

BARS = 200            # monthly history (~16yr)
STALE_MONTHS = 6      # drop a leg whose latest month trails the median by > this

# economy -> central-bank balance sheet, M2 (broad money), FX (USD per local; None
# for USD), and US-only netting series (government cash + reverse-repo drain).
ECONS = {
    "US": {"bs": "ECONOMICS:USCBBS", "m2": "ECONOMICS:USM2", "fx": None,
           "net": ["FRED:WTREGEN", "FRED:RRPONTSYD"]},
    "CN": {"bs": "ECONOMICS:CNCBBS", "m2": "ECONOMICS:CNM2", "fx": "FX_IDC:CNYUSD"},
    "EU": {"bs": "ECONOMICS:EUCBBS", "m2": "ECONOMICS:EUM2", "fx": "FX:EURUSD"},
    "JP": {"bs": "ECONOMICS:JPCBBS", "m2": "ECONOMICS:JPM2", "fx": "FX_IDC:JPYUSD"},
    "GB": {"bs": "ECONOMICS:GBCBBS", "m2": "ECONOMICS:GBM2", "fx": "FX:GBPUSD"},
    "CA": {"bs": "ECONOMICS:CACBBS", "m2": "ECONOMICS:CAM2", "fx": "FX_IDC:CADUSD"},
    "CH": {"bs": "ECONOMICS:CHCBBS", "m2": "ECONOMICS:CHM2", "fx": "FX_IDC:CHFUSD"},
    "AU": {"bs": "ECONOMICS:AUCBBS", "m2": "ECONOMICS:AUM3", "fx": "FX_IDC:AUDUSD"},
    "SE": {"bs": "ECONOMICS:SECBBS", "m2": "ECONOMICS:SEM2", "fx": "FX_IDC:SEKUSD"},
    "NO": {"bs": "ECONOMICS:NOCBBS", "m2": "ECONOMICS:NOM2", "fx": "FX_IDC:NOKUSD"},
}


def _ym(t):
    return dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m")


def _monthly(sym):
    """sym -> {YYYY-MM: value} or {} on failure (fail-safe)."""
    try:
        return {_ym(t): v for t, v in pull_series(sym, "1M", BARS, retries=3)}
    except Exception as e:
        print(f"  total_liquidity: {sym} pull failed: {str(e)[:60]}")
        return {}


def _pull_all():
    syms = set()
    for c in ECONS.values():
        syms.add(c["bs"]); syms.add(c["m2"])
        if c["fx"]:
            syms.add(c["fx"])
        for s in c.get("net", []):
            syms.add(s)
    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(zip(syms, ex.map(_monthly, syms)))


def _yoy(series):
    """{YYYY-MM: level} -> [{d, v}] YoY %% on a same-month-last-year basis."""
    out = []
    for m in sorted(series):
        y, mo = m.split("-")
        prev = f"{int(y) - 1}-{mo}"
        if prev in series and series[prev]:
            out.append({"d": m + "-01", "v": round((series[m] / series[prev] - 1) * 100, 2)})
    return out


def build_total_liquidity():
    """Return the TGL_DATA['total_liquidity'] block: the composite index plus its
    balance-sheet / M2 decomposition and per-economy legs. Components are parts of
    the one index, not standalone series."""
    D = _pull_all()

    def leg_series(code):
        """Monthly {YYYY-MM: USD level} for one economy's Net Liquidity leg, plus
        its balance-sheet and M2 sub-parts (USD)."""
        c = ECONS[code]
        bs, m2 = D.get(c["bs"], {}), D.get(c["m2"], {})
        fx = None if c["fx"] is None else D.get(c["fx"], {})
        nets = [D.get(s, {}) for s in c.get("net", [])]
        leg, bs_usd, m2_usd = {}, {}, {}
        for m in set(bs) & set(m2):
            rate = 1.0 if fx is None else fx.get(m)
            if rate is None:
                continue
            drain = sum(n.get(m, 0.0) or 0.0 for n in nets)
            bs_usd[m] = (bs[m] - drain) * rate
            m2_usd[m] = m2[m] * rate
            leg[m] = bs_usd[m] + m2_usd[m]
        return leg, bs_usd, m2_usd

    legs, bs_parts, m2_parts = {}, {}, {}
    for code in ECONS:
        l, b, m = leg_series(code)
        if l:
            legs[code], bs_parts[code], m2_parts[code] = l, b, m
        else:
            print(f"  total_liquidity: {code} leg empty — dropped")

    if not legs:
        return None

    # Drop stale legs (latest month trails the median by > STALE_MONTHS) so a dead
    # feed can't truncate the whole index (the NZ M2 failure mode).
    last_ix = {c: max(legs[c]) for c in legs}
    ordered = sorted(last_ix.values())
    median_last = ordered[len(ordered) // 2]
    active = []
    for c in legs:
        if _months_between(last_ix[c], median_last) > STALE_MONTHS:
            print(f"  total_liquidity: {c} stale (last {last_ix[c]} vs median {median_last}) — dropped")
        else:
            active.append(c)

    months = sorted(set.intersection(*[set(legs[c]) for c in active]))
    total = {m: sum(legs[c][m] for c in active) for m in months}
    bs_tot = {m: sum(bs_parts[c][m] for c in active) for m in months}
    m2_tot = {m: sum(m2_parts[c][m] for c in active) for m in months}

    tn = lambda d: [{"d": m + "-01", "v": round(d[m] / 1e12, 2)} for m in months]
    latest = months[-1]
    yoy = _yoy(total)
    # YoY map + 3-month trailing average, so the headline series carries the same
    # {d, v, y, ys} shape the front-end's Global tab expects (drop-in for the old
    # Global M2 series); ys lets the YoY chart show a smoothed line.
    yoy_map = {r["d"][:7]: r["v"] for r in yoy}
    def _trail3(m):
        ks = [k for k in sorted(yoy_map) if k <= m][-3:]
        return round(sum(yoy_map[k] for k in ks) / len(ks), 2) if ks else None
    series_pts = []
    for m in months:
        row = {"d": m + "-01", "v": round(total[m] / 1e12, 2)}
        if m in yoy_map:
            row["y"], row["ys"] = yoy_map[m], _trail3(m)
        series_pts.append(row)
    block = {
        "series": series_pts,                      # the headline index, $tn (with y/ys)
        "yoy": yoy,
        "components": {                            # decomposition of the ONE index
            "balance_sheets": tn(bs_tot),          # netted CB balance sheets (USD)
            "m2": tn(m2_tot),                      # broad money (USD)
        },
        "legs_latest": {c: round(legs[c][latest] / 1e12, 2)
                        for c in active if latest in legs[c]},
        "summary": {
            "latest": latest,
            "total_tn": round(total[latest] / 1e12, 2),
            "yoy": yoy[-1]["v"] if yoy else None,
            "yoy_s": _trail3(latest),
            "n_economies": len(active),
            "balance_sheets_tn": round(bs_tot[latest] / 1e12, 2),
            "m2_tn": round(m2_tot[latest] / 1e12, 2),
        },
    }
    s = block["summary"]
    print(f"  total_liquidity: ${s['total_tn']}T  YoY {s['yoy']}%  "
          f"({s['n_economies']} economies; CB ${s['balance_sheets_tn']}T + M2 ${s['m2_tn']}T) "
          f"| {s['latest']}")
    return block


def _months_between(a, b):
    ya, ma = map(int, a.split("-")); yb, mb = map(int, b.split("-"))
    return abs((ya - yb) * 12 + (ma - mb))


if __name__ == "__main__":
    import json
    print(json.dumps(build_total_liquidity()["summary"], indent=2))
