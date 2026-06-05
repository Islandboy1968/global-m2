# ===========================================================================
#  GMI RISK MONITOR — POSITIONS LIST  (author-editable)
# ===========================================================================
#  THIS is the file you edit to add / remove / reorder positions.
#  The pipeline reads it on every run and recomputes everything — no RV/P&E
#  involvement, no code changes. You "publish" positions the way you publish a
#  research note: edit this list, commit, done. (RV can later put an admin UI
#  on top of this same list.)
#
#  To ADD a position:    copy a row, set the fields below.
#  To REMOVE a position: delete its row.
#  To REORDER:           move rows — the table renders in list order.
#
#  Fields per asset:
#    name            display name (e.g. "Bitcoin")
#    ticker          short code shown in the table (e.g. "BTC")
#    tv_symbol       TradingView symbol the pipeline pulls (see notes below)
#    category        free-text grouping label (Crypto / Equity / Commodity / Rates / ...)
#    secular_method  "logchannel" for crypto + crypto-adjacent equities + carbon,
#                    "sma60" for traditional assets (60-month moving average)
#    is_yield        True only for rates/yields (renders the price as a % and
#                    skips $ formatting); otherwise False
#
#  NOTE ON SYMBOLS: the symbols below are the starting set. The build verifies
#  each one resolves on TradingView and FAILS LOUDLY (not silently) for any that
#  don't, so a position can never quietly show stale/blank data. Niche tokens
#  (e.g. SUI, DEEP) are the most likely to need an alternative feed — flagged.
# ===========================================================================

PRO_POSITIONS = [
    # name,              ticker, tv_symbol,           category,     secular,       is_yield
    {"name": "Bitcoin",      "ticker": "BTC",  "tv_symbol": "INDEX:BTCUSD",   "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    {"name": "Ethereum",     "ticker": "ETH",  "tv_symbol": "INDEX:ETHUSD",   "category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    {"name": "Solana",       "ticker": "SOL",  "tv_symbol": "COINBASE:SOLUSD","category": "Crypto",    "secular_method": "logchannel", "is_yield": False},
    {"name": "Sui",          "ticker": "SUI",  "tv_symbol": "COINBASE:SUIUSD","category": "Crypto",    "secular_method": "logchannel", "is_yield": False},  # verify feed
    {"name": "DeepBook",     "ticker": "DEEP", "tv_symbol": "COINBASE:DEEPUSD","category": "Crypto",   "secular_method": "logchannel", "is_yield": False},  # verify feed (niche)
    {"name": "Nasdaq 100",   "ticker": "QQQ",  "tv_symbol": "NASDAQ:QQQ",     "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    {"name": "Apple",        "ticker": "AAPL", "tv_symbol": "NASDAQ:AAPL",    "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    {"name": "Tesla",        "ticker": "TSLA", "tv_symbol": "NASDAQ:TSLA",    "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    {"name": "Coinbase",     "ticker": "COIN", "tv_symbol": "NASDAQ:COIN",    "category": "Equity",    "secular_method": "logchannel", "is_yield": False},
    {"name": "Robinhood",    "ticker": "HOOD", "tv_symbol": "NASDAQ:HOOD",    "category": "Equity",    "secular_method": "logchannel", "is_yield": False},
    {"name": "Invesco Solar","ticker": "TAN",  "tv_symbol": "AMEX:TAN",       "category": "Equity",    "secular_method": "sma60",      "is_yield": False},
    {"name": "EU Carbon (EUA)","ticker":"EUA", "tv_symbol": "LSE:CARB",       "category": "Commodity", "secular_method": "logchannel", "is_yield": False},  # WisdomTree Carbon ETC (CARB.L)
]

ALPHA_ASSETS = [
    {"name": "Bitcoin",        "ticker": "BTC",   "tv_symbol": "INDEX:BTCUSD", "category": "Risk Asset", "secular_method": "logchannel", "is_yield": False},
    {"name": "Nasdaq 100",     "ticker": "NDX",   "tv_symbol": "NASDAQ:NDX",   "category": "Risk Asset", "secular_method": "sma60",      "is_yield": False},
    {"name": "Gold",           "ticker": "XAU",   "tv_symbol": "TVC:GOLD",     "category": "Safe Haven", "secular_method": "sma60",      "is_yield": False},
    {"name": "Copper",         "ticker": "HG",    "tv_symbol": "COMEX:HG1!",   "category": "Cyclical",   "secular_method": "sma60",      "is_yield": False},
    {"name": "US Dollar Index","ticker": "DXY",   "tv_symbol": "TVC:DXY",      "category": "Currency",   "secular_method": "sma60",      "is_yield": False},
    {"name": "2-Year Yields",  "ticker": "US2Y",  "tv_symbol": "TVC:US02Y",    "category": "Rates",      "secular_method": "sma60",      "is_yield": True},
    {"name": "10-Year Yields", "ticker": "US10Y", "tv_symbol": "TVC:US10Y",    "category": "Rates",      "secular_method": "sma60",      "is_yield": True},
    {"name": "Crude Oil",      "ticker": "CL",    "tv_symbol": "TVC:USOIL",    "category": "Cyclical",   "secular_method": "sma60",      "is_yield": False},
]
