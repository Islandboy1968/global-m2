# ===========================================================================
#  GMI RISK MONITOR — GMI POSITIONS SYNC  (auto-derived; no hand-edited list)
# ===========================================================================
#  The GMI-branded Risk Monitor page (gmi.html) does NOT use a hand-edited
#  position list like positions.py. Its "GMI Positions" tab follows the GMI
#  Positions dashboard's positions.json (maintained in Cowork, published to
#  Google Drive). When a position is opened or closed there, the next pipeline
#  run picks it up automatically — no edit in this repo.
#
#  How it works, in order:
#    1. fetch_source()  — download positions.json from Google Drive (the file
#       must be shared "anyone with the link can view"). On success the copy
#       is cached to gmi-positions-source.json so the repo always carries the
#       last good snapshot. On failure the cached snapshot is used and the
#       build FAILS LOUD (exit non-zero) so a broken sync is caught in CI,
#       never silently stale on the board.
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
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(HERE, "gmi-positions-source.json")

# Google Drive file ID of positions.json in the "GMI Positions Dashboard"
# folder (drive.google.com/drive/folders/1wKaSzAgTF75CkDDm8cjl2QQmEHhL95xv).
DRIVE_FILE_ID = "1ASs512qjBSBUcT1u4y8w-11n7ZDUdF_0"
DRIVE_URL = "https://drive.google.com/uc?export=download&id=" + DRIVE_FILE_ID

BOOKS = [("tactical", "T"), ("core", "C"), ("long_term", "LT")]
NO_FEED_CLASSES = {"basket", "fund", "option"}

# TradingView symbol map, keyed by the ticker used in positions.json.
# name/ticker are what the table displays (canonical, since the same
# instrument can appear in positions.json under lot labels like
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
    # EU Carbon: positions.json books the EUA future as MO1; the Risk Monitor
    # source for the same exposure is the WisdomTree Carbon ETC (CARB.L).
    "MO1":   {"name": "EU Carbon (EUA)", "ticker": "EUA",  "tv_symbol": "LSE:CARB",        "category": "Commodity", "secular_method": "logchannel", "is_yield": False},
}


def fetch_source(timeout=30):
    """Return (data, source_label, warning). Tries Drive first, caches the
    download; on any failure falls back to the committed cache with a warning
    string the caller must surface (and fail the build on)."""
    try:
        req = urllib.request.Request(DRIVE_URL, headers={"User-Agent": "Mozilla/5.0"})
        raw = urllib.request.urlopen(req, timeout=timeout).read()
        data = json.loads(raw)
        if "sections" not in data:
            raise ValueError("no 'sections' key — not a positions.json payload")
        with open(CACHE_PATH, "wb") as f:
            f.write(raw)
        return data, "Google Drive (live)", None
    except Exception as ex:
        data = json.load(open(CACHE_PATH))
        warning = ("positions.json not reachable on Drive (%r) — built from the "
                   "committed snapshot (as_of %s). If the file isn't shared "
                   "'anyone with link can view' yet, sharing it fixes this."
                   % (ex, data.get("as_of_prices", "unknown")))
        return data, "cached snapshot", warning


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
