#!/usr/bin/env python3
"""GMI Risk Monitor — GMI-branded edition (dashboard-risk-monitor/gmi.html).

Same verified pipeline as build_risk_monitor.py (M2/ISM macro spine from
data/data.js, per-asset TradingView pulls through lib/signals.py +
lib/metrics.py) with one difference: the position list is NOT hand-edited.
It is auto-derived from the GMI Positions dashboard's positions.json on
Google Drive (see dashboard-risk-monitor/gmi_positions_sync.py), so opens
and closes published there flow through on the next run.

Outputs:
  dashboard-risk-monitor/gmi.html            — baked page (JS vars + embedded
                                               machine-readable JSON block)
  dashboard-risk-monitor/gmi-positions.json  — the same payload as a sidecar
                                               file for AI/programmatic use

FAIL LOUD (matching build_risk_monitor.py): unresolved feeds, tickers missing
from TV_MAP, or an unreachable Drive source all exit non-zero — but what
resolved is still written, so the gap is visible rather than blank/stale.
"""
import json, os, sys, datetime as dt

HERE = os.path.dirname(os.path.abspath(__file__))
RM = os.path.join(HERE, "dashboard-risk-monitor")
sys.path.insert(0, HERE)

from build_risk_monitor import load_tgl, build_macro, build_row
import positions as POS
import gmi_positions_sync as SYNC


def inject(html, start, end, payload):
    a = html.index(start)
    b = html.index(end) + len(end)
    return html[:a] + payload + html[b:]


def main():
    macro = build_macro(load_tgl())

    src, src_label, warning = SYNC.fetch_source()
    assets, unpriced, unmapped = SYNC.derive_assets(src)

    failures = []
    rows = []
    for a in assets:
        r = build_row(a, failures)
        if r:
            r["books"] = a["books"]
            rows.append(r)
    alpha = [r for r in (build_row(a, failures) for a in POS.ALPHA_ASSETS) if r]

    now = dt.datetime.utcnow()
    months = ["January","February","March","April","May","June","July",
              "August","September","October","November","December"]
    days = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]
    last_updated = "%s, %s %d, %d" % (days[now.weekday()], months[now.month - 1], now.day, now.year)

    meta = {
        "source_publication": src.get("source_publication", ""),
        "as_of_positions": src.get("as_of_prices", ""),
        "source": src_label,
        "unpriced": unpriced,
    }

    block = []
    block.append("// __PIPELINE_DATA_START__")
    block.append("")
    block.append('var lastUpdatedStr = %s;' % json.dumps(last_updated))
    block.append("var m2Roc = %s;" % json.dumps(macro["m2Roc"]))
    block.append("var m2ChartData = %s;" % json.dumps(macro["m2ChartData"]))
    block.append("var ismChartData = %s;" % json.dumps(macro["ismChartData"]))
    block.append("var gmiPositions = %s;" % json.dumps(rows))
    block.append("var alphaAssets = %s;" % json.dumps(alpha))
    block.append("var positionsMeta = %s;" % json.dumps(meta))
    block.append('var m2Trend = %s;' % json.dumps(macro["m2Trend"]))
    block.append('var ismTrend = %s;' % json.dumps(macro["ismTrend"]))
    block.append('var m2Since = %s;' % json.dumps(macro["m2Since"]))
    block.append('var ismSince = %s;' % json.dumps(macro["ismSince"]))
    block.append('var ismValue = %s;' % json.dumps(macro["ismValue"]))
    block.append("")
    block.append("// __PIPELINE_DATA_END__")

    # Machine-readable payload: everything an AI needs to read the board.
    payload = {
        "schema_version": "1.0",
        "dashboard": "GMI Risk Monitor (GMI edition)",
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "macro_regime": {
            "m2_trend": macro["m2Trend"], "m2_since": macro["m2Since"],
            "m2_roc": macro["m2Roc"],
            "ism_trend": macro["ismTrend"], "ism_since": macro["ismSince"],
            "ism_value": macro["ismValue"],
        },
        "positions_meta": meta,
        "gmi_positions": rows,
        "assets": alpha,
    }
    json_text = json.dumps(payload, indent=1).replace("</", "<\\/")
    json_block = ('<!-- __GMI_JSON_START__ -->\n'
                  '<script id="gmi-data" type="application/json">%s</script>\n'
                  '<!-- __GMI_JSON_END__ -->' % json_text)

    path = os.path.join(RM, "gmi.html")
    html = open(path).read()
    html = inject(html, "// __PIPELINE_DATA_START__", "// __PIPELINE_DATA_END__",
                  "\n".join(block))
    html = inject(html, "<!-- __GMI_JSON_START__ -->", "<!-- __GMI_JSON_END__ -->",
                  json_block)
    open(path, "w").write(html)

    sidecar = os.path.join(RM, "gmi-positions.json")
    open(sidecar, "w").write(json.dumps(payload, indent=1))

    print("Wrote %s" % path)
    print("Wrote %s" % sidecar)
    print("  Positions source: %s (%s)" % (src_label, meta["source_publication"]))
    print("  M2 %s (since %s) · ISM %s %.1f (since %s)" % (
        macro["m2Trend"], macro["m2Since"], macro["ismTrend"],
        macro["ismValue"], macro["ismSince"]))
    print("  GMI positions: %d/%d (+%d unpriced) · Assets: %d/%d" % (
        len(rows), len(assets), len(unpriced), len(alpha), len(POS.ALPHA_ASSETS)))
    for r in rows + alpha:
        print("    %-5s %-10s trend=%-5s since=%-9s secular=%-7s vol30=%s" % (
            r["ticker"], ("$%.2f" % r["price"]), r["trend"], r["since"],
            str(r["secular"]), r["vol30d"]))

    bad = False
    if unmapped:
        print("\nUNMAPPED TICKERS (%d) — add to TV_MAP in "
              "dashboard-risk-monitor/gmi_positions_sync.py:" % len(unmapped))
        for t in unmapped:
            print("  - " + t)
        bad = True
    if failures:
        print("\nFAILED FEEDS (%d) — board incomplete:" % len(failures))
        for f in failures:
            print("  - " + f)
        bad = True
    if warning:
        print("\nSOURCE WARNING: " + warning)
        bad = True
    if bad:
        sys.exit(1)
    print("\nAll feeds resolved; positions in sync.")


if __name__ == "__main__":
    main()
