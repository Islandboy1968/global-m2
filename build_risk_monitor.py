#!/usr/bin/env python3
"""GMI Risk Monitor — data pipeline.

Reuses the existing Everything Code pipeline for the macro spine (Global M2 +
ISM) and pulls each position's price from TradingView, then runs everything
through the VERIFIED calc modules (lib/signals.py, lib/metrics.py) and injects
the result into dashboard-risk-monitor/index.html between the markers.

Design decisions (from the Compounding Machine build):
- Data is computed on the runner (TradingView reachable there) and baked into
  the file — no in-browser feeds, no CORS, no loading hang.
- FAIL LOUD: if a position's feed doesn't resolve, we still write what we have
  but exit non-zero with a clear list, so a broken feed is caught in CI and
  never shows blank/stale on the live board.
"""
import json, os, sys, time, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
RM = os.path.join(HERE, "dashboard-risk-monitor")
sys.path.insert(0, HERE)               # tv_pull
sys.path.insert(0, RM)                 # positions
sys.path.insert(0, os.path.join(RM, "lib"))   # signals, metrics

import tv_pull
import positions as POS
import signals
import metrics

DAILY_BARS = 2600          # ~10y of daily closes per asset
M2_CHART_MONTHS = 49       # window shown on the M2 chart
ISM_CHART_MONTHS = 36


# ── helpers ────────────────────────────────────────────────────────────────
def iso(epoch):
    return dt.datetime.utcfromtimestamp(epoch).strftime("%Y-%m-%d")

def to_weekly(daily):
    """daily: [(epoch, close)] -> [(YYYY-MM-DD, close)] one point per ISO week (last close)."""
    by_week = {}
    for ep, c in daily:
        d = dt.datetime.utcfromtimestamp(ep)
        y, w, _ = d.isocalendar()
        by_week[(y, w)] = (iso(ep), c)
    return [by_week[k] for k in sorted(by_week)]

def to_monthly_pairs(daily):
    """daily: [(epoch, close)] -> [(YYYY-MM, close)] one point per month (last close)."""
    by_month = {}
    for ep, c in daily:
        d = dt.datetime.utcfromtimestamp(ep)
        by_month[(d.year, d.month)] = c
    return [("%04d-%02d" % (y, m), by_month[(y, m)]) for (y, m) in sorted(by_month)]

def load_tgl():
    txt = open(os.path.join(HERE, "data", "data.js")).read()
    s, e = txt.find("{"), txt.rfind("}")
    return json.loads(txt[s:e + 1])

def trend_and_since(band_points):
    """From a list of {d,c,s,g}, return (trend 'green'/'red', since 'Mon YYYY')."""
    if not band_points:
        return "green", ""
    last_g = band_points[-1]["g"]
    i = len(band_points) - 1
    while i > 0 and band_points[i - 1]["g"] == last_g:
        i -= 1
    d = band_points[i]["d"]            # 'YYYY-MM'
    y, m = d.split("-")[0], d.split("-")[1]
    months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    return ("green" if last_g == 1 else "red"), "%s %s" % (months[int(m) - 1], y)


# ── macro spine: Global M2 + ISM (reused from the existing pipeline) ────────
def build_macro(tgl):
    # M2 monthly level from the daily Total Liquidity series (field v, $tn)
    m2_monthly = {}
    for pt in tgl.get("series", []):
        v = pt.get("v")
        if v is None:
            continue
        ym = pt["d"][:7]
        m2_monthly[ym] = v
    keys = sorted(m2_monthly)
    if len(keys) < 14:
        raise SystemExit("FAIL: not enough Global M2 history in data.js")
    levels = [m2_monthly[k] for k in keys]

    # rate-of-change on the raw level
    yoy = round((levels[-1] / levels[-13] - 1) * 100, 1)
    mom6 = round(((levels[-1] / levels[-7]) ** 2 - 1) * 100, 1)   # 6m change, compounded-annualised

    # Compute the signal on the FULL monthly history so trend + "since" reflect
    # the true last flip (not a truncated-window warm-up artifact); slice only
    # for the chart display. Raw $tn level (the signal is scale-invariant; the
    # SVG chart auto-scales and shows no absolute y-labels).
    m2_full = [(k, m2_monthly[k]) for k in keys]
    m2_sig = signals.monthly_signal(m2_full, atr_period=10, mult=3.5)
    m2_trend, m2_since = trend_and_since(m2_sig)
    m2_chart = m2_sig[-M2_CHART_MONTHS:]

    # ISM monthly (reused: TGL_DATA.cycle.ism) — full history for trend/since.
    ism_raw = tgl.get("cycle", {}).get("ism", [])
    ism_all = [(p["d"][:7], p["v"]) for p in ism_raw if p.get("v") is not None]
    if len(ism_all) < 14:
        raise SystemExit("FAIL: not enough ISM history in data.js")
    ism_sig = signals.monthly_signal(ism_all, atr_period=10, mult=3.5)
    ism_trend, ism_since = trend_and_since(ism_sig)
    ism_chart = ism_sig[-ISM_CHART_MONTHS:]
    ism_value = round(ism_all[-1][1], 1)

    return {
        "m2Roc": {"yoy": yoy, "mom6": mom6},
        "m2ChartData": m2_chart, "ismChartData": ism_chart,
        "m2Trend": m2_trend, "ismTrend": ism_trend,
        "m2Since": m2_since, "ismSince": ism_since, "ismValue": ism_value,
    }


# ── per-asset rows ──────────────────────────────────────────────────────────
def build_row(a, failures):
    try:
        daily = tv_pull.pull_series(a["tv_symbol"], "1D", DAILY_BARS)
    except Exception as ex:
        failures.append("%s (%s): %r" % (a["ticker"], a["tv_symbol"], ex))
        return None
    if not daily or len(daily) < 30:
        failures.append("%s (%s): only %d bars" % (a["ticker"], a["tv_symbol"], len(daily or [])))
        return None

    daily_closes = [c for _, c in daily]
    weekly = to_weekly(daily)
    price = daily_closes[-1]

    sig = signals.weekly_signal(weekly)
    if not sig:
        failures.append("%s: weekly_signal returned None" % a["ticker"])
        return None

    if a["secular_method"] == "sma60":
        sec_input = [c for _, c in to_monthly_pairs(daily)]
    else:
        sec_input = [c for _, c in weekly]
    secular = metrics.secular_trend(sec_input, a["secular_method"])

    v30 = metrics.realised_vol_30d(daily_closes)
    av = metrics.ann_vol(daily_closes)

    return {
        "asset": a["name"], "ticker": a["ticker"],
        "trend": sig["trend"], "trendChange": sig["trendChange"],
        "price": round(price, 4),
        "category": a["category"], "since": sig["since"],
        "secular": secular,
        "vol30d": None if v30 != v30 else round(v30, 1),     # NaN guard
        "regime": "Extreme" if sig["regime"] == "extreme" else "Normal",
        "annVol": None if av != av else round(av, 1),
    }


# ── Alpha-tier page ─────────────────────────────────────────────────────────
def make_alpha_html(html):
    """Derive alpha.html (the RV Alpha tier page) from the freshly-baked Pro
    index.html. Same data block, presentation differences only:
      - isProSubscriber = false (Pro table paywalled)
      - tier pill reads RV ALPHA (on both trend tabs)
      - RV Alpha Trends tab is first and opens by default
      - 3 preview rows above the paywall (overlay repositioned at runtime to
        the top of row 4 — the source hard-codes top:120px, the 2-row mark)
    FAIL LOUD: every anchor must match exactly once, so a future redesign of
    index.html that breaks an anchor fails the build rather than silently
    shipping a stale/wrong Alpha page.
    """
    def sub(s, old, new):
        if s.count(old) != 1:
            raise SystemExit("FAIL: alpha.html anchor matched %d times (want 1): %r"
                             % (s.count(old), old[:70]))
        return s.replace(old, new)

    html = sub(html, "var isProSubscriber = true;", "var isProSubscriber = false;")

    html = sub(html, '<span class="tag" id="tierTag">RV PRO</span>',
                     '<span class="tag" id="tierTag">RV ALPHA</span>')
    html = sub(html, 'var tags = { pro: "RV PRO", alpha: "ASSETS", guide: "GUIDE" };',
                     'var tags = { pro: "RV ALPHA", alpha: "RV ALPHA", guide: "GUIDE" };')
    html = sub(html, 'document.getElementById("tierTag").textContent = tags[tab] || "RV PRO";',
                     'document.getElementById("tierTag").textContent = tags[tab] || "RV ALPHA";')

    # Pro labels this tab "Assets" (P&E request); on the Alpha page it is the
    # headline tab, so it carries the tier name.
    html = sub(html, """    <button class="tab-btn active" id="tabPro" onclick="switchTab('pro')">RV Pro Positions</button>
    <button class="tab-btn" id="tabAlpha" onclick="switchTab('alpha')">Assets</button>""",
                     """    <button class="tab-btn active" id="tabAlpha" onclick="switchTab('alpha')">RV Alpha Trends</button>
    <button class="tab-btn" id="tabPro" onclick="switchTab('pro')">RV Pro Positions</button>""")

    html = sub(html, '<div id="proContent" style="position: relative;">',
                     '<div id="proContent" class="hidden" style="position: relative;">')
    html = sub(html, '<div id="alphaContent" class="hidden">', '<div id="alphaContent">')

    # Guide copy: name the tabs as this tier sees them (Alpha first, Pro gated).
    html = sub(html, """        <div style="font-size: 11px; font-weight: 700; color: #e9ecf3; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em;">RV Pro Positions vs Assets</div>
        <p style="font-size: 12px; color: #aab3c4; line-height: 1.7; margin: 0 0 10px 0;"><span style="color: #e9ecf3; font-weight: 600;">RV Pro Positions</span> tracks the weekly trend for every asset in the current GMI portfolio. This is the tab most subscribers should focus on.</p>
        <p style="font-size: 12px; color: #aab3c4; line-height: 1.7; margin: 0;"><span style="color: #e9ecf3; font-weight: 600;">Assets</span> tracks broader macro assets (gold, copper, oil, yields, the dollar) that inform the overall macro picture but are not necessarily GMI positions.</p>""",
                     """        <div style="font-size: 11px; font-weight: 700; color: #e9ecf3; margin-bottom: 10px; text-transform: uppercase; letter-spacing: 0.06em;">RV Alpha Trends vs RV Pro Positions</div>
        <p style="font-size: 12px; color: #aab3c4; line-height: 1.7; margin: 0 0 10px 0;"><span style="color: #e9ecf3; font-weight: 600;">RV Alpha Trends</span> tracks broader macro assets (gold, copper, oil, yields, the dollar) that inform the overall macro picture but are not necessarily GMI positions.</p>
        <p style="font-size: 12px; color: #aab3c4; line-height: 1.7; margin: 0;"><span style="color: #e9ecf3; font-weight: 600;">RV Pro Positions</span> tracks the weekly trend for every asset in the current GMI portfolio. The first three positions are shown as a preview &mdash; the full table is available with an RV Pro subscription.</p>""")

    html = sub(html, "// Blur rows beyond the first 2 (preview rows)",
                     "// Blur rows beyond the first 3 (preview rows)")
    html = sub(html, "for (var i = 2; i < rows.length; i++) {",
                     "for (var i = 3; i < rows.length; i++) {")
    html = sub(html, "First 2 rows visible as preview", "First 3 rows visible as preview")

    html = sub(html, """    for (var i = 3; i < rows.length; i++) {
      rows[i].style.filter = "blur(6px)";
      rows[i].style.pointerEvents = "none";
      rows[i].style.userSelect = "none";
    }
  }
})();""",
                     """    for (var i = 3; i < rows.length; i++) {
      rows[i].style.filter = "blur(6px)";
      rows[i].style.pointerEvents = "none";
      rows[i].style.userSelect = "none";
    }
    // Align the overlay with the first blurred row (row 4). Must be measured
    // while the Pro tab is visible, so re-run on every switch to it.
    window.positionProPaywall = function() {
      var content = document.getElementById("proContent");
      if (!content || content.classList.contains("hidden") || rows.length <= 3) return;
      var top = rows[3].getBoundingClientRect().top - content.getBoundingClientRect().top;
      wall.style.top = Math.max(0, Math.round(top)) + "px";
    };
    var origSwitchTab = switchTab;
    switchTab = function(tab) {
      origSwitchTab(tab);
      if (tab === "pro") window.positionProPaywall();
    };
  }
})();""")
    return html


def main():
    tgl = load_tgl()
    macro = build_macro(tgl)

    failures = []
    pro = [r for r in (build_row(a, failures) for a in POS.PRO_POSITIONS) if r]
    alpha = [r for r in (build_row(a, failures) for a in POS.ALPHA_ASSETS) if r]

    now = dt.datetime.utcnow()
    months = ["January","February","March","April","May","June","July",
              "August","September","October","November","December"]
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    last_updated = "%s, %s %d, %d" % (days[now.weekday()], months[now.month - 1], now.day, now.year)

    block = []
    block.append("// __PIPELINE_DATA_START__")
    block.append("")
    block.append("// P&E: replace with your real auth check (Pro = true, free/Alpha = false).")
    block.append("var isProSubscriber = true;")
    block.append("")
    block.append('var lastUpdatedStr = %s;' % json.dumps(last_updated))
    block.append("")
    block.append("var m2Roc = %s;" % json.dumps(macro["m2Roc"]))
    block.append("")
    block.append("var m2ChartData = %s;" % json.dumps(macro["m2ChartData"]))
    block.append("")
    block.append("var ismChartData = %s;" % json.dumps(macro["ismChartData"]))
    block.append("")
    block.append("var proPositions = %s;" % json.dumps(pro))
    block.append("")
    block.append("var alphaAssets = %s;" % json.dumps(alpha))
    block.append("")
    block.append('var m2Trend = %s;' % json.dumps(macro["m2Trend"]))
    block.append('var ismTrend = %s;' % json.dumps(macro["ismTrend"]))
    block.append('var m2Since = %s;' % json.dumps(macro["m2Since"]))
    block.append('var ismSince = %s;' % json.dumps(macro["ismSince"]))
    block.append('var ismValue = %s;' % json.dumps(macro["ismValue"]))
    block.append("")
    block.append("// __PIPELINE_DATA_END__")
    new_block = "\n".join(block)

    path = os.path.join(RM, "index.html")
    html = open(path).read()
    a = html.index("// __PIPELINE_DATA_START__")
    b = html.index("// __PIPELINE_DATA_END__") + len("// __PIPELINE_DATA_END__")
    html = html[:a] + new_block + html[b:]
    open(path, "w").write(html)

    alpha_path = os.path.join(RM, "alpha.html")
    open(alpha_path, "w").write(make_alpha_html(html))

    print("Wrote %s" % path)
    print("Wrote %s" % alpha_path)
    print("  M2 %s (since %s) · ISM %s %.1f (since %s) · YoY %.1f%% 6m %.1f%%" % (
        macro["m2Trend"], macro["m2Since"], macro["ismTrend"], macro["ismValue"],
        macro["ismSince"], macro["m2Roc"]["yoy"], macro["m2Roc"]["mom6"]))
    print("  Pro positions: %d/%d · Alpha: %d/%d" % (
        len(pro), len(POS.PRO_POSITIONS), len(alpha), len(POS.ALPHA_ASSETS)))
    for r in pro + alpha:
        print("    %-5s %-9s trend=%-5s since=%-9s secular=%-7s vol30=%s regime=%s" % (
            r["ticker"], ("$%.2f" % r["price"]), r["trend"], r["since"],
            str(r["secular"]), r["vol30d"], r["regime"]))

    if failures:
        print("\nFAILED FEEDS (%d) — board incomplete, fix before going live:" % len(failures))
        for f in failures:
            print("  - " + f)
        sys.exit(1)
    print("\nAll feeds resolved.")


if __name__ == "__main__":
    main()
