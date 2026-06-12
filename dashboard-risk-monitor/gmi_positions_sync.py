# ===========================================================================
#  GMI RISK MONITOR — GMI POSITIONS SYNC  (auto-derived; no hand-edited list)
# ===========================================================================
#  The GMI-branded Risk Monitor page (gmi.html) does NOT use a hand-edited
#  position list like positions.py. Its "GMI Positions" tab follows the GMI
#  Positions dashboard's book, which Cowork publishes by committing
#  gmi-positions-source.json (in this directory) to the repo. When a position
#  is opened or closed there, the workflow rebuilds — no edit needed here.
#
#  PUBLISH TARGET, NOT AN EDITING SURFACE (per Cowork, 2026-06-12):
#  gmi-positions-source.json is write-only from Cowork's side. The authoring
#  flow is: Cowork's local canonical book + Raoul's Drive-inbox exports →
#  merge (Raoul's changes win) → commit here. Nothing reads this repo file
#  back into the book, so a direct edit to it on GitHub WILL BE SILENTLY
#  OVERWRITTEN by Cowork's next morning publish. A change to the book itself
#  goes through Raoul, never through this file.
#
#  How it works, in order:
#    1. fetch_source()  — load gmi-positions-source.json, the repo-canonical
#       copy of the GMI Positions book (Cowork-committed). Missing or
#       unparseable file FAILS LOUD in CI — never silently stale.
#       (History: v1 fetched positions.json from Google Drive with this file
#       as cache; flipped to repo-canonical 2026-06-12 once Cowork began
#       committing the book directly — fresher, no public link-sharing, and
#       commits trigger an immediate rebuild.)
#    2. derive_assets() — flatten the three books (Tactical / Core /
#       Long-term) into ONE deduped list of open instruments, in first-
#       appearance order, tagged with which books hold each instrument.
#    3. Each instrument is mapped to a TradingView symbol via TV_MAP below.
#
#  THE ONE MANUAL TOUCHPOINT: TV_MAP. If GMI opens a position in a ticker
#  that has no entry here, the build fails loud naming the ticker — add one
#  line below (same fields as positions.py) and re-run. Closes need nothing.
#
#  Instruments whose asset_class is in NO_FEED_CLASSES (baskets, funds,
#  options) have no market feed; they are listed on the page as unpriced
#  lines rather than trend rows.
# ===========================================================================
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE_PATH = os.path.join(HERE, "gmi-positions-source.json")

BOOKS = [("tactical", "T"), ("core", "C"), ("long_term", "LT")]
NO_FEED_CLASSES = {"basket", "fund", "option"}

# TradingView symbol map, keyed by the ticker used in the positions book.
# name/ticker are what the table displays (canonical, since the same
# instrument can appear in the book under lot labels like
# "SUI (tactical)"). Fields otherwise as in positions.py.
TV_MAP = {
    "BTC":   {"name": "Bitcoin",         "ticker": "BTC",  "tv_symbol": "INDEX:BTCUSD",    "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "ETH":   {"name": "Ethereum",        "ticker": "ETH",  "tv_symbol": "INDEX:ETHUSD",    "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "SOL":   {"name": "Solana",          "ticker": "SOL",  "tv_symbol": "COINBASE:SOLUSD", "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "SUI":   {"name": "Sui",             "ticker": "SUI",  "tv_symbol": "COINBASE:SUIUSD", "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "DOGE":  {"name": "Dogecoin",        "ticker": "DOGE", "tv_symbol": "COINBASE:DOGEUSD","category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "DEEP":  {"name": "DeepBook",        "ticker": "DEEP", "tv_symbol": "COINBASE:DEEPUSD","category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "XRP":   {"name": "XRP",             "ticker": "XRP",  "tv_symbol": "COINBASE:XRPUSD", "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    "MSFT":  {"name": "Microsoft",       "ticker": "MSFT", "tv_symbol": "NASDAQ:MSFT",     "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "AAPL":  {"name": "Apple",           "ticker": "AAPL", "tv_symbol": "NASDAQ:AAPL",     "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "TSLA":  {"name": "Tesla",           "ticker": "TSLA", "tv_symbol": "NASDAQ:TSLA",     "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "GOOGL": {"name": "Google",          "ticker": "GOOGL","tv_symbol": "NASDAQ:GOOGL",    "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "TSM":   {"name": "TSMC",            "ticker": "TSM",  "tv_symbol": "NYSE:TSM",        "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "RKLB":  {"name": "Rocket Lab",      "ticker": "RKLB", "tv_symbol": "NASDAQ:RKLB",     "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "HIMS":  {"name": "Hims & Hers",     "ticker": "HIMS", "tv_symbol": "NYSE:HIMS",       "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "COIN":  {"name": "Coinbase",        "ticker": "COIN", "tv_symbol": "NASDAQ:COIN",     "category": "Equity",    "secular_method": "logchannel", "is_yield": False},
    "HOOD":  {"name": "Robinhood",       "ticker": "HOOD", "tv_symbol": "NASDAQ:HOOD",     "category": "Equity",    "secular_method": "logchannel", "is_yield": False},
    "CRCL":  {"name": "Circle",          "ticker": "CRCL", "tv_symbol": "NYSE:CRCL",       "category": "Equity",    "secular_method": "logchannel", "is_yield": False},
    "QQQ":   {"name": "Nasdaq 100",      "ticker": "QQQ",  "tv_symbol": "NASDAQ:QQQ",      "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    "NDX":   {"name": "Nasdaq 100",      "ticker": "NDX",  "tv_symbol": "NASDAQ:NDX",      "category": "Index",     "secular_method": "sma60",      "is_yield": False},
    "TAN":   {"name": "Invesco Solar",   "ticker": "TAN",  "tv_symbol": "AMEX:TAN",        "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    # EU Carbon: the positions book books the EUA future as MO1; the Risk
    # Monitor source for the same exposure is the WisdomTree Carbon ETC (CARB.L).
    "MO1":   {"name": "EU Carbon (EUA)", "ticker": "EUA",  "tv_symbol": "LSE:CARB",        "category": "Commodity", "secular_method": "logchannel", "is_yield": False},
}


def fetch_source():
    """Return (data, source_label) from the repo-canonical positions book.
    Missing or malformed file raises — the build must fail loud, since
    without a book there is no honest GMI Positions tab to publish."""
    if not os.path.exists(SOURCE_PATH):
        raise SystemExit("FAIL: %s missing — the repo-canonical GMI positions "
                         "book (Cowork-committed) is gone." % SOURCE_PATH)
    data = json.load(open(SOURCE_PATH))
    if "sections" not in data:
        raise SystemExit("FAIL: %s has no 'sections' key — not a positions "
                         "book payload." % SOURCE_PATH)
    return data, "repo (gmi-positions-source.json)"


def derive_assets(data):
    """Flatten open positions across the three books into a deduped,
    TV-mapped asset list. Returns (assets, unpriced, unmapped):
      assets   — positions.py-shaped dicts + 'books' (e.g. "C · LT")
      unpriced — open instruments with no market feed (baskets/funds/options)
      unmapped — tickers needing a TV_MAP entry (build must fail loud on any)
    """
    order, books_of, class_of, name_of = [], {}, {}, {}
    for key, tag in BOOKS:
        for p in data["sections"].get(key, {}).get("positions", []):
            if p.get("status") != "open":
                continue
            t = p["ticker"]
            if t not in order:
                order.append(t)
                class_of[t] = p.get("asset_class", "")
                name_of[t] = p.get("instrument", t)
            if tag not in books_of.setdefault(t, []):
                books_of[t].append(tag)

    assets, unpriced, unmapped = [], [], []
    for t in order:
        books = " · ".join(books_of[t])
        if class_of[t] in NO_FEED_CLASSES:
            unpriced.append({"name": name_of[t], "ticker": t, "books": books,
                             "asset_class": class_of[t]})
        elif t in TV_MAP:
            a = dict(TV_MAP[t])
            a["books"] = books
            assets.append(a)
        else:
            unmapped.append(t)
    return assets, unpriced, unmapped
