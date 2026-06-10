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
one index (balance-sheets vs M2), never as standalone headline series.

DAILY GRID (like the Global M2 headline): the balance-sheet and M2 inputs are
monthly and are forward-filled between prints; FX is daily. So the index updates
EVERY DAY, and the daily moves are driven by the dollar (spot FX revaluing the
non-US legs) — the laggy monthly stocks only step on each new print. This matches
how update_data builds the Global M2 line.

Validated against GMI's published characterisation (live data):
  level ~$142T · YoY ~+8% (3m-avg; GMI quotes ~8%/yr) · correlates with BTC/NDX at
  r² ~0.92/0.97 (best lead 0–2mo; the near-peak cross-correlation profile is flat,
  so the exact lead is noise-sensitive — see summarize.py's live `signals` block for
  the recomputed values). Raw CB-balance-sheets-only fails this (−0.2% YoY); Global
  M2 alone misses the balance-sheet + China dynamics.

v1 scope / known simplifications (flagged on the chart):
  - US leg netted (− TGA − RRP); other regions use gross balance sheet (no
    netting feed abroad). Netting inputs forward-filled monthly.
  - Private layer = M2 everywhere; bank credit is a v2 refinement for the three
    economies that publish clean credit levels (US/EU/NZ).
  - NZ excluded: its M2 feed is dead (ends 2017-01).
  - China M2 via ECONOMICS:CNM2 (feed-first; see update_data.reconcile_china_override).
  - Formula version is FNL + M2 (reproduces +8%); FNL + M2 + bank securities is a
    Raoul sign-off away (see SCOPE_TOTAL_LIQUIDITY.md §6).

Fail-safe: each economy's leg is independent; a failed pull drops that leg (logged)
rather than breaking the index. A leg whose monthly data goes stale (> STALE_MONTHS
behind the others) is dropped so a dead feed can't forward-fill a flat line forever
(the NZ failure mode).
"""
import datetime as dt
from concurrent.futures import ThreadPoolExecutor
from tv_pull import pull_series

START = dt.date(2011, 1, 1)   # daily-grid start (composite emits once all legs begin)
M2_BARS = 220                 # monthly balance-sheet / M2 / netting history (~18yr)
FX_BARS = 6200                # daily FX history (~17yr)
STALE_MONTHS = 6              # drop a leg whose latest monthly print trails the median by > this

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

# US deficit-monetization extras (FRED, USD, no FX). Bank securities held by banks
# = total bank credit − loans (reliable derivation; ~$5.7T, matches GMI's ~$5tn).
# Used for (A) the GMI "FNL + M2 + bank securities" US-leg variant and (B) the
# deficit-monetization watch series. RRP / TGA reuse the US netting symbols.
US_EXTRA = {"bank_credit": "FRED:TOTBKCR", "loans": "FRED:TOTLL",
            "rrp": "FRED:RRPONTSYD", "tga": "FRED:WTREGEN"}


def _ym(t):
    return dt.datetime.utcfromtimestamp(int(t)).strftime("%Y-%m")


def _pull(spec):
    """(sym, resolution, bars) -> sorted [(epoch, value)] or [] on failure."""
    sym, res, bars = spec
    try:
        return sym, pull_series(sym, res, bars, retries=3)
    except Exception as e:
        print(f"  total_liquidity: {sym} pull failed: {str(e)[:60]}")
        return sym, []


def _pull_all():
    """Pull balance sheets / M2 / netting MONTHLY and FX DAILY, in parallel."""
    specs = []
    for c in ECONS.values():
        specs.append((c["bs"], "1M", M2_BARS))
        specs.append((c["m2"], "1M", M2_BARS))
        if c["fx"]:
            specs.append((c["fx"], "1D", FX_BARS))
        for s in c.get("net", []):
            specs.append((s, "1M", M2_BARS))
    for s in US_EXTRA.values():
        specs.append((s, "1M", M2_BARS))
    seen, uniq = set(), []
    for s in specs:
        if s[0] not in seen:
            seen.add(s[0]); uniq.append(s)
    with ThreadPoolExecutor(max_workers=6) as ex:
        return dict(ex.map(_pull, uniq))


# ----------------------------------------------------------------- ffill
def _grid(today):
    return [START + dt.timedelta(days=k) for k in range((today - START).days + 1)]


def _month_ffill(points, grid):
    """Monthly (epoch, val) points -> daily array, forward-filled by month."""
    mp = {_ym(t): v for t, v in points}
    if not mp:
        return [None] * len(grid)
    allm = sorted({d.strftime("%Y-%m") for d in grid} | set(mp))
    ff, last = {}, None
    for m in allm:
        if m in mp:
            last = mp[m]
        ff[m] = last
    return [ff.get(d.strftime("%Y-%m")) for d in grid]


def _sanitize_fx(points):
    """Drop garbage FX bars (some illiquid pairs return inverted/zero early bars)."""
    vals = sorted(v for _, v in points if v)
    if not vals:
        return points
    med = vals[len(vals) // 2]
    lo, hi = med / 100.0, med * 100.0
    return [(t, v) for t, v in points if v and lo <= v <= hi]


def _day_ffill(points, grid):
    """Daily (epoch, val) points -> daily array forward-filled onto the grid."""
    pts = sorted((dt.datetime.utcfromtimestamp(int(t)).date(), v)
                 for t, v in _sanitize_fx(points))
    out = [None] * len(grid)
    j, cur = 0, None
    for i, day in enumerate(grid):
        while j < len(pts) and pts[j][0] <= day:
            cur = pts[j][1]; j += 1
        out[i] = cur
    return out


def _trail(arr, n):
    out = [None] * len(arr)
    for i in range(len(arr)):
        w = [v for v in arr[max(0, i - n + 1):i + 1] if v is not None]
        out[i] = sum(w) / len(w) if w else None
    return out


def _months_between(a, b):
    ya, ma = map(int, a.split("-")); yb, mb = map(int, b.split("-"))
    return abs((ya - yb) * 12 + (ma - mb))


def _ffill_monthmap(mp, grid):
    """{YYYY-MM: value} -> daily array, forward-filled by month onto the grid."""
    if not mp:
        return [None] * len(grid)
    allm = sorted({d.strftime("%Y-%m") for d in grid} | set(mp))
    ff, last = {}, None
    for m in allm:
        if m in mp:
            last = mp[m]
        ff[m] = last
    return [ff.get(d.strftime("%Y-%m")) for d in grid]


def _daily_series(total_arr, grid):
    """A daily [{d, v, y, ys}] series from a daily USD total array: $tn level, YoY
    on a 365-day offset, 91-day trailing-average YoY — same shape as Global M2."""
    n = len(total_arr)
    yoy = [None] * n
    for i in range(n):
        j = i - 365
        if j >= 0 and total_arr[i] and total_arr[j]:
            yoy[i] = (total_arr[i] / total_arr[j] - 1) * 100
    ys = _trail(yoy, 91)
    out = []
    for i, day in enumerate(grid):
        if total_arr[i] is None:
            continue
        row = {"d": day.strftime("%Y-%m-%d"), "v": round(total_arr[i] / 1e12, 2)}
        if yoy[i] is not None:
            row["y"] = round(yoy[i], 2)
        if ys[i] is not None:
            row["ys"] = round(ys[i], 2)
        out.append(row)
    return out


# ----------------------------------------------------------------- build
def build_total_liquidity():
    """Return the TGL_DATA['total_liquidity'] block: the daily composite index plus
    its (monthly) balance-sheet / M2 decomposition and per-economy legs."""
    D = _pull_all()
    today = dt.datetime.utcnow().date()
    grid = _grid(today)
    N = len(grid)

    # Stale-leg guard on the monthly stocks (a dead feed must not forward-fill flat).
    last_month = {}
    for code, c in ECONS.items():
        bs, m2 = D.get(c["bs"], []), D.get(c["m2"], [])
        if bs and m2:
            last_month[code] = min(_ym(bs[-1][0]), _ym(m2[-1][0]))
    if not last_month:
        return None
    median_last = sorted(last_month.values())[len(last_month) // 2]

    legs, bs_parts, m2_parts = {}, {}, {}
    for code, c in ECONS.items():
        bs, m2 = D.get(c["bs"], []), D.get(c["m2"], [])
        if not bs or not m2:
            print(f"  total_liquidity: {code} leg empty — dropped"); continue
        if _months_between(last_month[code], median_last) > STALE_MONTHS:
            print(f"  total_liquidity: {code} stale ({last_month[code]} vs {median_last}) — dropped"); continue
        bs_arr = _month_ffill(bs, grid)
        m2_arr = _month_ffill(m2, grid)
        net_arr = [0.0] * N
        for s in c.get("net", []):
            na = _month_ffill(D.get(s, []), grid)
            net_arr = [(net_arr[i] + (na[i] or 0.0)) for i in range(N)]
        fx_arr = [1.0] * N if c["fx"] is None else _day_ffill(D.get(c["fx"], []), grid)
        leg, bsd, m2d = [None] * N, [None] * N, [None] * N
        for i in range(N):
            if bs_arr[i] is None or m2_arr[i] is None or fx_arr[i] is None:
                continue
            bsd[i] = (bs_arr[i] - net_arr[i]) * fx_arr[i]
            m2d[i] = m2_arr[i] * fx_arr[i]
            leg[i] = bsd[i] + m2d[i]
        legs[code], bs_parts[code], m2_parts[code] = leg, bsd, m2d

    if not legs:
        return None
    active = list(legs)

    total = [None] * N; bstot = [None] * N; m2tot = [None] * N
    for i in range(N):
        if all(legs[c][i] is not None for c in active):
            total[i] = sum(legs[c][i] for c in active)
            bstot[i] = sum(bs_parts[c][i] for c in active)
            m2tot[i] = sum(m2_parts[c][i] for c in active)

    series = _daily_series(total, grid)
    if not series:
        return None

    # --- US deficit monetization: bank securities = total bank credit − loans -----
    # (A) GMI's "FNL + M2 + bank securities" flagship: add US bank securities to the
    #     US leg (US has no FX, so it adds 1:1 in USD) -> series_plus_banksec.
    # (B) the watch series for the monetization-engine chart (banks hoarding
    #     Treasuries while RRP is drained).
    def _mm(sym):
        return {_ym(t): v for t, v in D.get(sym, [])}
    cr, ln = _mm(US_EXTRA["bank_credit"]), _mm(US_EXTRA["loans"])
    banksec_m = {m: cr[m] - ln[m] for m in (set(cr) & set(ln))}
    banksec_arr = _ffill_monthmap(banksec_m, grid)
    total_plus = [(total[i] + banksec_arr[i])
                  if (total[i] is not None and banksec_arr[i] is not None) else None
                  for i in range(N)]
    series_plus = _daily_series(total_plus, grid)

    # Components as a MONTHLY decomposition (month-end snapshot) to keep the payload
    # small — the headline series is daily, the breakdown only needs to step monthly.
    def month_end(arr):
        out = {}
        for i, day in enumerate(grid):
            if arr[i] is not None:
                out[day.strftime("%Y-%m")] = arr[i]   # last day of month wins
        return [{"d": m + "-01", "v": round(v / 1e12, 2)} for m, v in sorted(out.items())]

    def month_series(mp):
        return [{"d": m + "-01", "v": round(mp[m] / 1e12, 2)} for m in sorted(mp)]

    li = max(i for i in range(N) if total[i] is not None)   # latest complete day
    banksec_tn = round(banksec_arr[li] / 1e12, 2) if banksec_arr[li] is not None else None
    block = {
        "series": series,                                   # daily, $tn, with y/ys
        # (A) GMI's current-flagship variant: US leg + bank securities. Front-end toggle.
        "series_plus_banksec": series_plus,
        "components": {
            "balance_sheets": month_end(bstot),
            "m2": month_end(m2tot),
        },
        # (B) US deficit-monetization watch series — banks hoarding Treasuries while
        # the RRP buffer is drained: the engine extending the cycle.
        "monetization": {
            "bank_securities": month_series(banksec_m),         # TOTBKCR − TOTLL
            "bank_credit": month_series(_mm(US_EXTRA["bank_credit"])),
            "reverse_repo": month_series(_mm(US_EXTRA["rrp"])),
            "tga": month_series(_mm(US_EXTRA["tga"])),
        },
        "legs_latest": {c: round(legs[c][li] / 1e12, 2) for c in active if legs[c][li] is not None},
        "summary": {
            "latest": series[-1]["d"],
            "total_tn": series[-1]["v"],
            "total_plus_banksec_tn": series_plus[-1]["v"] if series_plus else None,
            "yoy": series[-1].get("y"),
            "yoy_s": series[-1].get("ys"),
            "n_economies": len(active),
            "balance_sheets_tn": round(bstot[li] / 1e12, 2),
            "m2_tn": round(m2tot[li] / 1e12, 2),
            "us_bank_securities_tn": banksec_tn,
        },
    }
    s = block["summary"]
    print(f"  total_liquidity: ${s['total_tn']}T (+banksec ${s['total_plus_banksec_tn']}T)  "
          f"YoY {s['yoy']}%  ({s['n_economies']} econ; CB ${s['balance_sheets_tn']}T + "
          f"M2 ${s['m2_tn']}T + US banksec ${s['us_bank_securities_tn']}T) | {s['latest']} | "
          f"{len(series)} daily pts")
    return block


if __name__ == "__main__":
    import json
    print(json.dumps(build_total_liquidity()["summary"], indent=2))
