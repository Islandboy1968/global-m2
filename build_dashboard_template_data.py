#!/usr/bin/env python3
"""Refresh real weekly data for the Compounding Machine dashboard template.

Pulls weekly closes for the configured assets from TradingView (the same
source the main pipeline uses, reachable from GitHub's runners), writes them
into dashboard-template/data/data.js between the injection markers, and
rebuilds the self-contained dashboard-template/compounding-machine-beta.html.

The dashboard reads this baked-in data via the `injected` adapter — no live
browser fetch, no CORS, no hang. Run hourly by the workflow; the in-progress
weekly bar carries the latest (delayed) price, so each run refreshes "now".
"""
import json, os, time, datetime as dt
import tv_pull

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "dashboard-template")
START = dt.date(2017, 9, 1)

# asset key -> (TradingView symbol, weekly bars to request)
ASSETS = {
    "BTC": ("INDEX:BTCUSD", 480),
    "QQQ": ("NASDAQ:QQQ", 480),
}


def friday_key(epoch):
    """Map a weekly bar's epoch to that week's Friday as 'YYYY-MM-DD'."""
    d = dt.datetime.utcfromtimestamp(epoch).date()
    return (d + dt.timedelta(days=(4 - d.weekday()) % 7)).isoformat()


def weekly_series(symbol, bars):
    rows = tv_pull.pull_series(symbol, "1W", bars)
    by_week = {}
    for epoch, close in rows:
        d = dt.datetime.utcfromtimestamp(epoch).date()
        if d < START:
            continue
        by_week[friday_key(epoch)] = round(float(close), 2)
    return [{"d": k, "c": by_week[k]} for k in sorted(by_week)]


def main():
    # Keep any existing series as a fallback so one bad pull never blanks an asset.
    data_path = os.path.join(TPL, "data", "data.js")
    existing = {}
    if os.path.exists(data_path):
        txt = open(data_path).read()
        s, e = txt.find("{"), txt.rfind("}")
        if s != -1 and e != -1:
            try:
                existing = json.loads(txt[s:e + 1]).get("assets", {})
            except Exception:
                existing = {}

    assets = {}
    for key, (symbol, bars) in ASSETS.items():
        try:
            series = weekly_series(symbol, bars)
            if len(series) < 50:
                raise RuntimeError("only %d points" % len(series))
            assets[key] = {"series": series}
            print("%s (%s): %d weekly points, last %s = %s"
                  % (key, symbol, len(series), series[-1]["d"], series[-1]["c"]))
        except Exception as ex:
            print("%s (%s): FAILED %r — keeping existing" % (key, symbol, ex))
            if key in existing:
                assets[key] = existing[key]

    if not assets:
        raise SystemExit("no assets pulled and no existing data; aborting")

    updated = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    payload = {"updated": updated, "assets": assets}
    banner = (
        "// ===========================================================================\n"
        "//  DATA FILE  —  the only file the pipeline rewrites on each refresh.\n"
        "//  The dashboard shell never changes; it reads ONLY the named variable below.\n"
        "//  Everything between the two markers is machine-generated. Do not hand-edit.\n"
        "// ===========================================================================\n"
    )
    body = ("// __PIPELINE_DATA_START__\nwindow.DASHBOARD_DATA = "
            + json.dumps(payload) + ";\n// __PIPELINE_DATA_END__\n")
    open(data_path, "w").write(banner + body)
    print("wrote", data_path, "updated", updated)

    build_beta(banner + body)


def build_beta(data_js):
    """Assemble the single-file beta: inline data + compute + sources into the
    shell (assets stay on their default `injected` source — no browser fetch)."""
    shell = open(os.path.join(TPL, "compounding-machine.html")).read()
    compute = open(os.path.join(TPL, "lib", "compute.js")).read()
    sources = open(os.path.join(TPL, "lib", "sources.js")).read()

    def inline(js):
        return "<script>\n" + js + "\n</scr" + "ipt>"

    shell = shell.replace('<script src="data/data.js"></script>', inline(data_js))
    shell = shell.replace('<script src="lib/compute.js"></script>', inline(compute))
    shell = shell.replace('<script src="lib/sources.js"></script>', inline(sources))
    out = os.path.join(TPL, "compounding-machine-beta.html")
    open(out, "w").write(shell)
    print("rebuilt", out)


if __name__ == "__main__":
    main()
