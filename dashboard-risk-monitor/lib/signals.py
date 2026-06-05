"""
GMI Risk Monitor -- volatility-adaptive trend-signal calculations.

Two pure functions used by the "GMI Risk Monitor" dashboard:

    weekly_signal(closes_with_dates)              -> {trend, since, trendChange,
                                                      band_series}
    monthly_signal(values_with_dates, atr_period, mult)
                                                  -> list[{d, c, s, g}]

Design goals: pure functions, no network, no I/O, dependency-light (stdlib only --
`math` + `datetime`). numpy is intentionally NOT required, matching the sibling
module ``metrics.py`` in this directory so the module runs in the
network-restricted dashboard build environment.

==============================================================================
1. THE WEEKLY SIGNAL -- 1:1 PORT OF THE PINE v6 "GMI Weekly Trend Signal"
==============================================================================
`weekly_signal(...)` is a faithful, line-by-line port of the locked Pine v6
indicator (NOT an ATR/SuperTrend). The band is MULTIPLICATIVE around the close,
sized by the population stdev of weekly log returns. The full Pine source and a
Pine<->Python correspondence table live next to the function. The recurrence:

    logRet = math.log(close / nz(close[1], close))   # bar0 -> log(c/c) = 0
    vol    = ta.stdev(logRet, lookback)              # POPULATION stdev (divisor N)
    avgVol = ta.sma(vol, regimeLen)                  # 50-bar trailing mean of vol
    annVol = avgVol * math.sqrt(52) * 100
    isExtreme = annVol > 45.0
    sens   = isExtreme ? 4.0 : 3.5
    bw     = sens * vol
    rawUp  = close * (1.0 - bw)                       # trailing-stop floor
    rawDn  = close * (1.0 + bw)                       # trailing-stop ceiling

followed by a stateful trailing + ASYMMETRIC-confirmation machine (`var int
trend`, `var float tUp/tDn`, `pendFlip`, `pendCnt`):
  * trend==1 : tUp ratchets UP (tUp = max(tUp,rawUp)); a flip to -1 needs
    `sellConf` CONSECUTIVE closes below tUp (sellConf = 3 if extreme else 2).
  * trend==-1: tDn ratchets DOWN (tDn = min(tDn,rawDn)); a flip to +1 needs
    `confirmBuy`=2 consecutive closes above tDn.
  * pendCnt only accrues on consecutive same-direction breaches; any bar that
    closes back inside the band resets pendFlip/pendCnt to 0.

PARAMETERS (locked, mirrored as module constants):
    lookback=3, sensNorm=3.5, sensXHi=4.0, confirmBuy=2, confirmSell=2,
    confirmSellX=3, regimeLen=50, threshXHi=45.0.

==============================================================================
2. THE MONTHLY SIGNAL -- ATR SUPERTREND (UNCHANGED, author-confirmed)
==============================================================================
`monthly_signal(...)` is the M2/ISM "normal SuperTrend" and is a SEPARATE,
already-confirmed mechanic. It is intentionally left intact:

  * Volatility unit = ATR over a close-to-close true range TR_t=|C_t-C_{t-1}|
    (the dashboard feeds are close-only); SMA smoothing by default, Wilder
    optional via `atr_smoothing`.
  * Bands = close +/- mult*ATR; the active band ratchets monotonically and the
    trend flips INSTANTLY (confirm=1) on the first piercing close.
  * Dev-locked params: M2 (atr_period=6, mult=3.0), ISM (atr_period=12, mult=3.0).

`monthly_signal` and the shared `_supertrend` / ATR helpers below it are NOT part
of the Pine weekly port; the weekly assumptions (A-notes) do not apply to them.

==============================================================================
3-5. IMPLEMENTATION, TESTS, ASSUMPTIONS  -- see code + bottom of file.
==============================================================================
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

# ----------------------------------------------------------------------------
# Dev-locked constants (surfaced so a human can confirm against TradingView)
# ----------------------------------------------------------------------------

# ---- WEEKLY signal: 1:1 port of the Pine "GMI Weekly Trend Signal" ----------
# These names mirror the Pine `// PARAMETERS (locked)` block exactly.
WEEKLY_LOOKBACK = 3            # Pine: lookback = 3        (ta.stdev window for logRet)
SENS_NORM = 3.5               # Pine: sensNorm = 3.5      (band-width mult, normal)
SENS_XHI = 4.0                # Pine: sensXHi = 4.0       (band-width mult, extreme)
CONFIRM_BUY = 2               # Pine: confirmBuy = 2      (closes above tDn to flip up)
CONFIRM_SELL = 2              # Pine: confirmSell = 2     (closes below tUp, normal)
CONFIRM_SELL_X = 3            # Pine: confirmSellX = 3    (closes below tUp, extreme)
REGIME_LEN = 50               # Pine: regimeLen = 50      (ta.sma window for vol)
THRESH_XHI = 45.0             # Pine: threshXHi = 45.0    (annVol % -> extreme)
WEEKS_PER_YEAR = 52           # Pine: math.sqrt(52)       (vol annualisation factor)

MONTHS_PER_YEAR = 12          # (unused for monthly band; kept for documentation)

M2_ATR_PERIOD, M2_MULT = 6, 3.0     # monthly M2 composite dev-locked params
ISM_ATR_PERIOD, ISM_MULT = 12, 3.0  # monthly ISM dev-locked params


# ============================================================================
# Internal helpers
# ============================================================================

def _stdev_pop(xs: Sequence[float]) -> float:
    """Population standard deviation (divisor n) -- matches Pine `ta.stdev`.

    Pine's ``ta.stdev(src, length)`` uses the BIASED estimator (divisor N), not
    the sample (N-1) estimator. We replicate that here. Returns 0.0 for an empty
    window (only reached during warm-up before `lookback` bars exist).
    """
    n = len(xs)
    if n == 0:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / n
    return math.sqrt(var)


def _log_returns(closes: Sequence[float]) -> List[float]:
    """Pine: ``logRet = math.log(close / nz(close[1], close))`` for every bar.

    Bar 0 has no prior close, so ``nz(close[1], close) -> close`` and
    ``logRet[0] = log(close/close) = 0``. Returned list is aligned 1:1 to
    `closes` (same length), with index 0 being that degenerate 0.0.
    """
    n = len(closes)
    out = [0.0] * n
    for i in range(1, n):
        prev = closes[i - 1] if closes[i - 1] else closes[i]   # nz fallback
        out[i] = math.log(closes[i] / prev) if prev and closes[i] else 0.0
    return out


def stdev_series(xs: Sequence[float], length: int) -> List[Optional[float]]:
    """Pine: ``ta.stdev(xs, length)`` aligned 1:1 to `xs`.

    Population (biased) stdev over the trailing `length` values. Pine returns
    ``na`` until `length` values exist, i.e. for index < length-1; we mirror that
    with ``None``. (The warm-up `na` only affects the first `length-1` bars.)
    """
    n = len(xs)
    out: List[Optional[float]] = [None] * n
    for i in range(length - 1, n):
        out[i] = _stdev_pop(xs[i - length + 1:i + 1])
    return out


def sma_series(xs: Sequence[Optional[float]], length: int) -> List[Optional[float]]:
    """Pine: ``ta.sma(xs, length)`` aligned 1:1 to `xs`.

    Trailing simple mean over `length` values. Because `xs` here is the `vol`
    series (which is ``na`` for its first `lookback-1` bars), Pine's `ta.sma`
    only begins emitting once it has `length` consecutive NON-na inputs. We
    replicate the steady-state exactly: output is ``None`` until a full window of
    non-None values is available; thereafter it is the plain mean of that window.
    """
    n = len(xs)
    out: List[Optional[float]] = [None] * n
    for i in range(n):
        if i - length + 1 < 0:
            continue
        window = xs[i - length + 1:i + 1]
        if any(w is None for w in window):
            continue
        out[i] = sum(window) / length            # type: ignore[arg-type]
    return out


def weekly_vol_series(closes: Sequence[float],
                      lookback: int = WEEKLY_LOOKBACK) -> List[Optional[float]]:
    """Pine: ``vol = ta.stdev(logRet, lookback)`` -- per-bar vol of log returns."""
    return stdev_series(_log_returns(closes), lookback)


def weekly_regime_series(closes: Sequence[float],
                         lookback: int = WEEKLY_LOOKBACK,
                         regime_len: int = REGIME_LEN,
                         thresh: float = THRESH_XHI
                         ) -> List[bool]:
    """Per-bar ``isExtreme`` flag, faithful to the Pine REGIME block:

        avgVol   = ta.sma(vol, regimeLen)
        annVol   = avgVol * math.sqrt(52) * 100
        isExtreme = annVol > threshXHi

    Where ``avgVol`` is ``na`` (warm-up), ``annVol`` is ``na`` and the Pine
    ternary ``isExtreme ? ... : ...`` treats the comparison as false, so the bar
    is NOT extreme. We return a plain ``bool`` per bar (False during warm-up).
    """
    vol = weekly_vol_series(closes, lookback)
    avg_vol = sma_series(vol, regime_len)
    out: List[bool] = []
    for av in avg_vol:
        if av is None:
            out.append(False)
        else:
            ann_vol = av * math.sqrt(WEEKS_PER_YEAR) * 100.0
            out.append(ann_vol > thresh)
    return out


def weekly_annvol_series(closes: Sequence[float],
                         lookback: int = WEEKLY_LOOKBACK,
                         regime_len: int = REGIME_LEN
                         ) -> List[Optional[float]]:
    """Pine: ``annVol = ta.sma(vol, regimeLen) * math.sqrt(52) * 100`` per bar.

    Returns the per-bar annualised volatility *percentage* (the exact quantity
    the Pine compares against ``threshXHi`` to set ``isExtreme``). ``None`` where
    Pine's ``annVol`` is ``na`` (warm-up before a full ``regimeLen`` window of
    non-na ``vol`` exists).
    """
    vol = weekly_vol_series(closes, lookback)
    avg_vol = sma_series(vol, regime_len)
    out: List[Optional[float]] = []
    for av in avg_vol:
        out.append(None if av is None
                   else av * math.sqrt(WEEKS_PER_YEAR) * 100.0)
    return out


def realised_vol_weekly(closes: Sequence[float],
                        lookback: int = WEEKLY_LOOKBACK,
                        regime_len: int = REGIME_LEN) -> Optional[float]:
    """Annualised realised volatility (%) on the LAST bar -- the Pine ``annVol``.

    This is a convenience scalar mirroring the Pine REGIME block exactly:
    ``avgVol = ta.sma(ta.stdev(logRet, lookback), regimeLen); annVol =
    avgVol*sqrt(52)*100``. If the series is too short for a full ``regimeLen``
    window of non-na ``vol`` (so Pine's ``avgVol`` would still be ``na``), we
    fall back to the mean of ALL available non-na ``vol`` values so callers and
    tests on short synthetic series still get a representative number. The
    warm-up fallback only affects series shorter than ``lookback + regimeLen``
    bars and never changes the steady-state value. Returns ``None`` if there is
    not even one ``vol`` value (fewer than ``lookback`` bars).
    """
    vol = weekly_vol_series(closes, lookback)
    avg = sma_series(vol, regime_len)
    if avg and avg[-1] is not None:                 # steady state: exact Pine
        return avg[-1] * math.sqrt(WEEKS_PER_YEAR) * 100.0
    non_na = [v for v in vol if v is not None]       # warm-up fallback
    if not non_na:
        return None
    return (sum(non_na) / len(non_na)) * math.sqrt(WEEKS_PER_YEAR) * 100.0


def true_range_close_only(closes: Sequence[float]) -> List[float]:
    """Close-to-close true range: TR_t = |C_t - C_{t-1}|, TR_0 = 0."""
    if not closes:
        return []
    tr = [0.0]
    for i in range(1, len(closes)):
        tr.append(abs(closes[i] - closes[i - 1]))
    return tr


def true_range_ohlc(highs: Sequence[float],
                    lows: Sequence[float],
                    closes: Sequence[float]) -> List[float]:
    """Wilder true range from OHLC. TR_0 = High_0 - Low_0 (no prior close)."""
    n = len(closes)
    if not (len(highs) == len(lows) == n) or n == 0:
        raise ValueError("highs, lows, closes must be same non-zero length")
    tr = [highs[0] - lows[0]]
    for i in range(1, n):
        tr.append(max(highs[i] - lows[i],
                      abs(highs[i] - closes[i - 1]),
                      abs(lows[i] - closes[i - 1])))
    return tr


def atr_series(tr: Sequence[float], period: int,
               smoothing: str = "sma") -> List[Optional[float]]:
    """ATR for each index.

    smoothing="sma": simple moving average of the trailing `period` true ranges.
        ATR is None until `period` TRs are available (index < period-1).
    smoothing="wilder": Wilder/RMA recursive smoothing (TradingView ta.atr default).
        Seeded with the SMA of the first `period` TRs at index period-1, then
        ATR_t = (ATR_{t-1}*(period-1) + TR_t) / period.

    NOTE on indexing: TR[0] is the degenerate first bar (0.0 for close-only).
    We average over the raw TR array as given; the first usable ATR therefore
    appears at index `period-1`. See ASSUMPTIONS M1 (monthly only).
    """
    n = len(tr)
    out: List[Optional[float]] = [None] * n
    if period <= 0 or n < period:
        return out
    seed = sum(tr[:period]) / period
    out[period - 1] = seed
    if smoothing == "sma":
        for i in range(period, n):
            out[i] = sum(tr[i - period + 1:i + 1]) / period
    elif smoothing == "wilder":
        prev = seed
        for i in range(period, n):
            prev = (prev * (period - 1) + tr[i]) / period
            out[i] = prev
    else:
        raise ValueError("smoothing must be 'sma' or 'wilder'")
    return out


# ============================================================================
# Core SuperTrend band engine (shared by weekly + monthly)
# ============================================================================

def _supertrend(closes: Sequence[float],
                atr: Sequence[Optional[float]],
                mult: float,
                confirm: int = 1) -> Tuple[List[Optional[float]], List[Optional[int]]]:
    """Generic SuperTrend trailing band with a consecutive-close confirmation
    filter.

    Args:
      closes : source/close series
      atr    : ATR aligned to `closes` (None where ATR not yet available)
      mult   : ATR multiplier (the "sensitivity")
      confirm: consecutive closes beyond the active band required to flip
               (1 = instant flip, the monthly behaviour).

    Returns (band, dir) aligned to closes:
      band[i] = the active trailing-stop level shown for bar i (None until ATR ready)
      dir[i]  = +1 (rising/green) or -1 (falling/red), or None until initialised.

    Mechanic (strict directional ratchet, faithful to the spec's words
    "support band only ratchets UP (never down)"):
      basicUpper = close + mult*ATR ;  basicLower = close - mult*ATR
      While direction == +1 (uptrend) the ACTIVE band is the SUPPORT, which is
        held at max(prior support, basicLower) -- it can only rise, never fall,
        even if a volatility spike widens basicLower far below it. A flip DOWN
        requires `confirm` consecutive closes strictly below that support.
      While direction == -1 (downtrend) the ACTIVE band is the RESISTANCE, held
        at min(prior resistance, basicUpper) -- it can only fall. A flip UP
        requires `confirm` consecutive closes strictly above that resistance.
      On a confirmed flip the opposite band is (re)seeded from the current
        basic band so the new trailing stop starts at a sensible distance.

    The strict ratchet (rather than the textbook Seban "reset on prior-close
    pierce") is deliberate: with the close-only true range, a single large move
    makes ATR explode, and the textbook reset would let the support collapse
    below price on the very next bar -- silently cancelling the confirmation
    streak. Holding the band monotonic preserves the confirmation streak. See
    ASSUMPTIONS M1 (monthly only -- this engine is NOT used by the weekly Pine
    port, which has its own state machine inline in weekly_signal).
    """
    n = len(closes)
    band: List[Optional[float]] = [None] * n
    direction: List[Optional[int]] = [None] * n

    # find first bar with an ATR value
    start = next((i for i in range(n) if atr[i] is not None), None)
    if start is None:
        return band, direction

    # streak counters of consecutive piercing closes (reset on any non-pierce)
    pierce_up = 0    # consecutive closes ABOVE the active resistance
    pierce_down = 0  # consecutive closes BELOW the active support

    cur_dir = 1                       # seed rising (warm-up; see ASSUMPTIONS M1)
    support = closes[start] - mult * atr[start]    # active band when rising
    resistance = closes[start] + mult * atr[start] # active band when falling

    for i in range(start, n):
        bu = closes[i] + mult * atr[i]   # basic upper
        bl = closes[i] - mult * atr[i]   # basic lower

        if cur_dir == 1:
            # support only ratchets UP
            support = max(support, bl)
            if closes[i] < support:
                pierce_down += 1
            else:
                pierce_down = 0
            pierce_up = 0
            if pierce_down >= confirm:
                # confirmed flip to falling: seed the resistance from this bar
                cur_dir = -1
                resistance = bu
                pierce_down = 0
        else:  # cur_dir == -1
            # resistance only ratchets DOWN
            resistance = min(resistance, bu)
            if closes[i] > resistance:
                pierce_up += 1
            else:
                pierce_up = 0
            pierce_down = 0
            if pierce_up >= confirm:
                # confirmed flip to rising: seed the support from this bar
                cur_dir = 1
                support = bl
                pierce_up = 0

        direction[i] = cur_dir
        band[i] = support if cur_dir == 1 else resistance

    return band, direction


# ============================================================================
# Date helpers
# ============================================================================

_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _month_year(date_str: str) -> str:
    """'YYYY-MM-DD' or 'YYYY-MM' -> 'Mon YYYY' (e.g. '2025-11-07' -> 'Nov 2025')."""
    parts = date_str.split("-")
    y = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 1
    return f"{_MONTHS[m - 1]} {y}"


# ============================================================================
# Public: WEEKLY signal
# ============================================================================
#
# PINE <-> PYTHON CORRESPONDENCE TABLE (proves 1:1 fidelity).
# Pine source line                                  | Python location
# --------------------------------------------------+-------------------------------
# lookback=3                                         | WEEKLY_LOOKBACK = 3
# sensNorm=3.5 / sensXHi=4.0                         | SENS_NORM / SENS_XHI
# confirmBuy=2                                       | CONFIRM_BUY = 2
# confirmSell=2 / confirmSellX=3                     | CONFIRM_SELL / CONFIRM_SELL_X
# regimeLen=50 / threshXHi=45.0                      | REGIME_LEN / THRESH_XHI
# logRet=math.log(close/nz(close[1],close))          | _log_returns()  (bar0 -> 0.0)
# vol=ta.stdev(logRet, lookback)                     | weekly_vol_series()/stdev_series()
#   (Pine ta.stdev = BIASED/population, divisor N)   |   _stdev_pop() (divisor n)
#   (na until `lookback` values exist)               |   None for i < lookback-1
# avgVol=ta.sma(vol, regimeLen)                      | sma_series(vol, REGIME_LEN)
#   (na until regimeLen non-na vol values)           |   None until full non-None window
# annVol=avgVol*math.sqrt(52)*100                    | weekly_annvol_series()
# isExtreme=annVol>threshXHi                         | weekly_regime_series() (False if na)
# sens=isExtreme?sensXHi:sensNorm                    | sens = SENS_XHI if extreme else SENS_NORM
# bw=sens*vol                                        | bw = sens * vol[i]
# rawUp=close*(1.0-bw) / rawDn=close*(1.0+bw)        | raw_up[i] / raw_dn[i]
# var int trend = 1                                  | trend = 1
# var float tUp/tDn = na                             | t_up = None / t_dn = None
# var int pendFlip=0 / pendCnt=0                     | pend_flip = 0 / pend_cnt = 0
# if na(tUp): tUp:=rawUp; tDn:=rawDn                 | if t_up is None: t_up=ru; t_dn=rd
# sellConf=isExtreme?confirmSellX:confirmSell        | sell_conf = CONFIRM_SELL_X/CONFIRM_SELL
# if trend==1: tUp:=math.max(tUp,rawUp)              | t_up = max(t_up, ru)
#   if close<tUp: pendCnt:=pendFlip==-1?pendCnt+1:1  | pend_cnt = pend_cnt+1 if pend_flip==-1 else 1
#     pendFlip:=-1; if pendCnt>=sellConf:            | pend_flip=-1; if pend_cnt>=sell_conf:
#       trend:=-1; tDn:=rawDn; reset pend            |   trend=-1; t_dn=rd; pend_flip=pend_cnt=0
#   else: pendFlip:=0; pendCnt:=0                    | else: pend_flip=pend_cnt=0
# else: tDn:=math.min(tDn,rawDn)                     | t_dn = min(t_dn, rd)
#   if close>tDn: pendCnt:=pendFlip==1?pendCnt+1:1   | pend_cnt = pend_cnt+1 if pend_flip==1 else 1
#     pendFlip:=1; if pendCnt>=confirmBuy:           | pend_flip=1; if pend_cnt>=CONFIRM_BUY:
#       trend:=1; tUp:=rawUp; reset pend             |   trend=1; t_up=ru; pend_flip=pend_cnt=0
#   else: pendFlip:=0; pendCnt:=0                    | else: pend_flip=pend_cnt=0
# alertcondition(trend==1 and trend[1]==-1) Buy      | trend_change (flip vs prior bar)
# alertcondition(trend==-1 and trend[1]==1) Sell     | trend_change (flip vs prior bar)
# --------------------------------------------------+-------------------------------

def weekly_signal(closes_with_dates: Sequence[Tuple[str, float]],
                  lookback: int = WEEKLY_LOOKBACK) -> Optional[Dict]:
    """Compute the GMI Weekly Trend Signal -- a 1:1 port of the Pine v6 indicator
    "GMI Weekly Trend Signal".

    This is NOT an ATR/SuperTrend band. The Pine builds a MULTIPLICATIVE band
    around the close from the population stdev of weekly log returns:

        logRet = log(close / nz(close[1], close))          # bar0 -> 0
        vol    = ta.stdev(logRet, lookback)                # population (biased)
        avgVol = ta.sma(vol, regimeLen)                    # 50-bar mean of vol
        annVol = avgVol * sqrt(52) * 100
        isExtreme = annVol > 45
        sens   = isExtreme ? 4.0 : 3.5
        bw     = sens * vol
        rawUp  = close * (1 - bw)                           # trailing-stop floor
        rawDn  = close * (1 + bw)                           # trailing-stop ceil

    Then a stateful trailing + ASYMMETRIC-confirmation machine (the Pine
    `var int trend` / `var float tUp,tDn` / `pendFlip` / `pendCnt` block):
      * In an uptrend (trend==1) tUp ratchets UP: tUp = max(tUp, rawUp).
        A flip to -1 needs `sellConf` CONSECUTIVE closes below tUp
        (sellConf = 3 if extreme else 2).
      * In a downtrend (trend==-1) tDn ratchets DOWN: tDn = min(tDn, rawDn).
        A flip to +1 needs `confirmBuy`=2 consecutive closes above tDn.
      * pendCnt only accumulates on consecutive same-direction breaches; any bar
        that closes back inside the band resets pendFlip/pendCnt to 0.

    Args:
      closes_with_dates: chronologically sorted list of (date_str, close).
          date_str is 'YYYY-MM-DD' (weekly bar date).
      lookback: Pine `lookback` (dev-locked 3); the ta.stdev window for logRet.

    Returns dict or None (None if no bars):
      {
        "trend":       "green" | "red",   # final Pine `trend` var (1->green, -1->red)
        "since":       "Mon YYYY",        # first bar of the current uninterrupted run
        "trendChange": bool,              # flip on the last bar or the bar before
        "regime":      "normal" | "extreme",   # isExtreme on the LAST bar
        "band_series": [{"d","c","s","g"}, ...]   # full per-bar series
      }
      `s` = the ACTIVE stop AFTER the per-bar update (tUp when trend==1, else
      tDn). `g` = 1 if trend==1 else 0.
    """
    pts = list(closes_with_dates)
    if not pts:
        return None
    dates = [d for d, _ in pts]
    closes = [float(c) for _, c in pts]
    n = len(closes)

    # --- VOLATILITY + REGIME (per bar) --------------------------------------
    vol = weekly_vol_series(closes, lookback)             # ta.stdev(logRet, lookback)
    extreme_bar = weekly_regime_series(closes, lookback)  # isExtreme per bar

    # --- BAND WIDTH (per bar) -----------------------------------------------
    # bw = sens*vol ; rawUp = close*(1-bw) ; rawDn = close*(1+bw).
    # Where vol is na (warm-up), Pine's `bw` is na so rawUp/rawDn are na and the
    # band/state are not yet meaningful; we hold them as None and let the seed
    # logic below pick up the first bar that has a real vol value.
    raw_up: List[Optional[float]] = [None] * n
    raw_dn: List[Optional[float]] = [None] * n
    for i in range(n):
        if vol[i] is None:
            continue
        sens = SENS_XHI if extreme_bar[i] else SENS_NORM
        bw = sens * vol[i]
        raw_up[i] = closes[i] * (1.0 - bw)
        raw_dn[i] = closes[i] * (1.0 + bw)

    # --- TRAILING + ASYMMETRIC CONFIRMATION STATE MACHINE -------------------
    # Pine `var` semantics: trend/tUp/tDn/pendFlip/pendCnt persist across bars.
    trend = 1                       # var int trend = 1
    t_up: Optional[float] = None    # var float tUp = na
    t_dn: Optional[float] = None    # var float tDn = na
    pend_flip = 0                   # var int pendFlip = 0
    pend_cnt = 0                    # var int pendCnt = 0

    trend_hist: List[Optional[int]] = [None] * n   # trend var AFTER each bar
    stop_hist: List[Optional[float]] = [None] * n  # active stop AFTER each bar

    for i in range(n):
        ru = raw_up[i]
        rd = raw_dn[i]
        if ru is None or rd is None:
            # warm-up: rawUp/rawDn na -> nothing updates; record current state.
            trend_hist[i] = None
            stop_hist[i] = None
            continue

        # if na(tUp) -> seed both bands from this bar's raw bands.
        if t_up is None:
            t_up = ru
            t_dn = rd

        sell_conf = CONFIRM_SELL_X if extreme_bar[i] else CONFIRM_SELL

        if trend == 1:
            t_up = max(t_up, ru)            # tUp := math.max(tUp, rawUp)
            if closes[i] < t_up:
                pend_cnt = pend_cnt + 1 if pend_flip == -1 else 1
                pend_flip = -1
                if pend_cnt >= sell_conf:
                    trend = -1
                    t_dn = rd               # tDn := rawDn
                    pend_flip = 0
                    pend_cnt = 0
            else:
                pend_flip = 0
                pend_cnt = 0
        else:  # trend == -1
            t_dn = min(t_dn, rd)            # tDn := math.min(tDn, rawDn)
            if closes[i] > t_dn:
                pend_cnt = pend_cnt + 1 if pend_flip == 1 else 1
                pend_flip = 1
                if pend_cnt >= CONFIRM_BUY:
                    trend = 1
                    t_up = ru               # tUp := rawUp
                    pend_flip = 0
                    pend_cnt = 0
            else:
                pend_flip = 0
                pend_cnt = 0

        trend_hist[i] = trend
        stop_hist[i] = t_up if trend == 1 else t_dn

    # --- build the per-bar series (only bars where the band is live) --------
    series = []
    for i in range(n):
        if trend_hist[i] is None:
            continue
        series.append({
            "d": dates[i][:7] if len(dates[i]) >= 7 else dates[i],
            "c": round(closes[i], 4),
            "s": None if stop_hist[i] is None else round(stop_hist[i], 4),
            "g": 1 if trend_hist[i] == 1 else 0,
        })
    if not series:
        return None

    valid_idx = [i for i in range(n) if trend_hist[i] is not None]

    # final trend var -> colour
    last = valid_idx[-1]
    trend_final = trend_hist[last]
    trend_str = "green" if trend_final == 1 else "red"

    # "since": first bar of the current uninterrupted run (over valid bars)
    since_pos = len(valid_idx) - 1
    while since_pos > 0 and trend_hist[valid_idx[since_pos - 1]] == trend_final:
        since_pos -= 1
    since = _month_year(dates[valid_idx[since_pos]])

    # trendChange: Pine alert fires when trend flips vs the prior bar. We surface
    # it as "flipped on the last bar OR the bar before" (this week / last week).
    trend_change = False
    if len(valid_idx) >= 2:
        flipped_this = trend_hist[valid_idx[-1]] != trend_hist[valid_idx[-2]]
        flipped_prev = (len(valid_idx) >= 3 and
                        trend_hist[valid_idx[-2]] != trend_hist[valid_idx[-3]])
        trend_change = flipped_this or flipped_prev

    return {
        "trend": trend_str,
        "since": since,
        "trendChange": trend_change,
        "regime": "extreme" if extreme_bar[last] else "normal",
        "band_series": series,
    }


# ============================================================================
# Public: MONTHLY signal
# ============================================================================

def monthly_signal(values_with_dates: Sequence[Tuple[str, float]],
                   atr_period: int,
                   mult: float,
                   atr_smoothing: str = "sma") -> List[Dict]:
    """Compute the monthly SuperTrend band that flips INSTANTLY (confirm=1).

    Args:
      values_with_dates: sorted list of (date_str, value). date_str 'YYYY-MM' or
          'YYYY-MM-DD'.
      atr_period: dev-locked 6 for M2, 12 for ISM.
      mult: dev-locked 3.0 for both.

    Returns a list of chart points (only where the band is defined):
      [{"d": "YYYY-MM", "c": value, "s": band_level, "g": 1|0}, ...]
    """
    pts = list(values_with_dates)
    dates = [d for d, _ in pts]
    closes = [float(v) for _, v in pts]
    tr = true_range_close_only(closes)
    atr = atr_series(tr, atr_period, smoothing=atr_smoothing)
    band, direction = _supertrend(closes, atr, mult, confirm=1)

    out = []
    for i in range(len(closes)):
        if direction[i] is None or band[i] is None:
            continue
        out.append({
            "d": dates[i][:7] if len(dates[i]) >= 7 else dates[i],
            "c": round(closes[i], 2),
            "s": round(band[i], 2),
            "g": 1 if direction[i] == 1 else 0,
        })
    return out


# ============================================================================
# SELF-CHECKING TESTS (hand-computable expected outputs)
# ============================================================================

def _run_tests() -> None:
    passed = 0
    failed = 0

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        status = "PASS" if cond else "FAIL"
        if cond:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))
        assert cond, f"TEST FAILED: {name} {detail}"

    print("=" * 72)
    print("signals.py self-checks")
    print("=" * 72)

    def wk_dates(n, start_year=2025, start_month=1):
        """n weekly-ish dates, one per week, as 'YYYY-MM-DD'."""
        import datetime as dt
        d0 = dt.date(start_year, start_month, 1)
        return [(d0 + dt.timedelta(weeks=i)).strftime("%Y-%m-%d") for i in range(n)]

    # ---- Test 1: clean uptrend never flips -> green, no change ------------
    n = 80
    closes = [100.0 * (1.01 ** i) for i in range(n)]   # +1%/wk, low vol, smooth
    series = list(zip(wk_dates(n), closes))
    r1 = weekly_signal(series)
    check("T1 clean uptrend -> trend green", r1["trend"] == "green", f"got {r1['trend']}")
    check("T1 clean uptrend -> trendChange False (no recent flip)",
          r1["trendChange"] is False, f"got {r1['trendChange']}")
    check("T1 all bars green", all(p["g"] == 1 for p in r1["band_series"]),
          f"reds={sum(1 for p in r1['band_series'] if p['g']==0)}")
    # regime must be Normal: ~1%/wk constant -> near-zero realised vol
    check("T1 regime normal", r1["regime"] == "normal", f"got {r1['regime']}")

    # ---- Test 2: sharp 2-week drop flips Normal-regime asset to red -------
    # 60 calm up-weeks, then 2 consecutive sharp drops. Normal confirm=2.
    base = [100.0 + 0.5 * i for i in range(60)]        # gentle rise, low vol
    drop = [base[-1] * 0.80, base[-1] * 0.80 * 0.80]   # two -20% weeks
    closes2 = base + drop
    series2 = list(zip(wk_dates(len(closes2)), closes2))
    r2 = weekly_signal(series2)
    check("T2 two -20% weeks flip Normal asset -> red",
          r2["trend"] == "red", f"got {r2['trend']}; regime={r2['regime']}")
    check("T2 regime normal (gentle history dominates 50wk window)",
          r2["regime"] == "normal", f"got {r2['regime']}")
    check("T2 trendChange True (flip is in last 2 bars)",
          r2["trendChange"] is True, f"got {r2['trendChange']}")

    # ---- Test 3: ONE drop is NOT enough in Normal regime (confirm=2) ------
    closes3 = base + [base[-1] * 0.80]                 # only ONE -20% week
    series3 = list(zip(wk_dates(len(closes3)), closes3))
    r3 = weekly_signal(series3)
    check("T3 single drop does NOT flip (needs 2 consecutive)",
          r3["trend"] == "green", f"got {r3['trend']}")

    # ---- Test 4: Extreme-vol asset needs 3 (2 not enough) ----------------
    # Build a high-vol history so 50wk annualised vol > 45% -> Extreme, confirm=3.
    # Alternating +/-8% weekly moves: weekly stdev ~0.08 -> ann ~0.08*sqrt(52)
    # = ~57.7% > 45%. Then trend up via drift, then test 2 vs 3 down-closes.
    import math as _m
    hist = [100.0]
    for i in range(60):
        # net upward drift but high week-to-week vol
        step = 0.10 if (i % 2 == 0) else -0.085
        hist.append(hist[-1] * (1 + step))
    v = realised_vol_weekly(hist)
    check("T4 history is Extreme regime (vol>45%)",
          v is not None and v > 45.0, f"vol={v:.1f}%")
    # Establish an uptrend tail (several up weeks so dir is green), then drops.
    up_tail = [hist[-1] * (1.02 ** k) for k in range(1, 6)]
    closes4 = hist + up_tail
    # Now append exactly 2 down-closes that pierce the support:
    two_down = [closes4[-1] * 0.85, closes4[-1] * 0.85 * 0.90]
    s4_two = list(zip(wk_dates(len(closes4) + 2), closes4 + two_down))
    r4_two = weekly_signal(s4_two)
    # 3 down-closes:
    three_down = two_down + [two_down[-1] * 0.90]
    s4_three = list(zip(wk_dates(len(closes4) + 3), closes4 + three_down))
    r4_three = weekly_signal(s4_three)
    check("T4 Extreme regime detected on the spliced series",
          r4_three["regime"] == "extreme", f"got {r4_three['regime']}")
    check("T4 Extreme: 2 down-closes do NOT flip (need 3)",
          r4_two["trend"] == "green",
          f"got {r4_two['trend']}")
    check("T4 Extreme: 3 down-closes DO flip -> red",
          r4_three["trend"] == "red",
          f"got {r4_three['trend']}")

    # ---- Test 5: monthly_signal instant flip + output shape --------------
    # Rising then falling monthly composite; confirm=1 so it flips on the 1st
    # piercing close. Check field names/types and that g toggles 1->0.
    mv = [100.0 + i for i in range(12)] + [110.0, 95.0, 80.0, 70.0]
    mdates = [f"2025-{(i % 12) + 1:02d}" for i in range(len(mv))]
    # make dates monotonic across the year boundary
    mdates = []
    yy, mm = 2025, 1
    for _ in range(len(mv)):
        mdates.append(f"{yy}-{mm:02d}")
        mm += 1
        if mm > 12:
            mm = 1; yy += 1
    out = monthly_signal(list(zip(mdates, mv)), M2_ATR_PERIOD, M2_MULT)
    check("T5 monthly_signal returns dicts with d,c,s,g",
          all(set(p) == {"d", "c", "s", "g"} for p in out),
          f"keys={set(out[0]) if out else None}")
    check("T5 monthly_signal first usable point exists",
          len(out) > 0, f"len={len(out)}")
    check("T5 monthly ends red after the crash (g==0)",
          out[-1]["g"] == 0, f"got g={out[-1]['g']}")
    check("T5 monthly starts green during the rise (g==1)",
          out[0]["g"] == 1, f"got g={out[0]['g']}")
    # instant-flip check: the bar AT the first big crash should already be red.
    crash_idx = next(i for i, p in enumerate(out) if p["c"] <= 95.0)
    check("T5 instant flip: crash bar is already red (confirm=1)",
          out[crash_idx]["g"] == 0, f"g at crash={out[crash_idx]['g']}")

    # ---- Test 6: ATR SMA closed form (hand-computable) -------------------
    # TR for closes [10, 12, 11, 14] (close-only) = [0, 2, 1, 3].
    # ATR period 2, SMA: index1 = (0+2)/2 = 1.0; index2 = (2+1)/2=1.5;
    # index3 = (1+3)/2 = 2.0.
    tr6 = true_range_close_only([10, 12, 11, 14])
    check("T6 close-only TR = [0,2,1,3]", tr6 == [0.0, 2.0, 1.0, 3.0], f"got {tr6}")
    a6 = atr_series(tr6, 2, "sma")
    check("T6 ATR SMA period2 = [None,1.0,1.5,2.0]",
          a6 == [None, 1.0, 1.5, 2.0], f"got {a6}")

    # ---- Test 7: regime/vol closed form ---------------------------------
    # Constant geometric growth -> zero return variance -> vol 0% -> Normal.
    flat_growth = [100.0 * (1.005 ** i) for i in range(60)]
    vv = realised_vol_weekly(flat_growth)
    check("T7 constant-CAGR series has ~0 realised vol",
          vv is not None and vv < 1e-6, f"vol={vv}")

    # ---- Test 8: 'since' is Mon-YYYY of current run start ----------------
    check("T8 'since' formatted 'Mon YYYY'",
          len(r1["since"].split()) == 2 and r1["since"].split()[1].isdigit(),
          f"since={r1['since']}")

    # ======================================================================
    # PINE-PRIMITIVE unit tests (pin the NEW logic with hand-math expecteds)
    # ======================================================================

    # ---- Test 9: logRet -- Pine `math.log(close/nz(close[1],close))` ------
    # closes [10, 20, 10]:
    #   bar0: nz(na,10)=10 -> log(10/10)=0
    #   bar1: log(20/10)=ln2  = 0.6931471805599453
    #   bar2: log(10/20)=-ln2 = -0.6931471805599453
    lr9 = _log_returns([10.0, 20.0, 10.0])
    check("T9 logRet[0] == 0 (nz fallback close[1]->close)", lr9[0] == 0.0,
          f"got {lr9[0]}")
    check("T9 logRet[1] == ln(2)", abs(lr9[1] - _m.log(2)) < 1e-12, f"got {lr9[1]}")
    check("T9 logRet[2] == -ln(2)", abs(lr9[2] + _m.log(2)) < 1e-12, f"got {lr9[2]}")

    # ---- Test 10: ta.stdev is POPULATION (divisor N), na before `length` --
    # logRet for [10,20,10] = [0, ln2, -ln2]. stdev over length=3 of these:
    #   mean = 0 ; var = (0 + ln2^2 + ln2^2)/3 = 2*ln2^2/3
    #   stdev = ln2*sqrt(2/3) = 0.6931471805599453*0.816496580927726
    vs10 = stdev_series([0.0, _m.log(2), -_m.log(2)], 3)
    exp10 = _m.log(2) * _m.sqrt(2.0 / 3.0)
    check("T10 stdev na for index < length-1",
          vs10[0] is None and vs10[1] is None, f"got {vs10[:2]}")
    check("T10 stdev is POPULATION (divisor N)",
          vs10[2] is not None and abs(vs10[2] - exp10) < 1e-12,
          f"got {vs10[2]} want {exp10}")
    # sanity: sample (N-1) stdev would be ln2*sqrt(2/2)=ln2; confirm we are NOT that
    check("T10 NOT the sample (N-1) estimator",
          abs(vs10[2] - _m.log(2)) > 1e-6, f"got {vs10[2]}")

    # ---- Test 11: annVol formula avgVol*sqrt(52)*100 & threshold ----------
    # Build closes whose 3-bar logRet stdev is a known constant, then avg over
    # 50 bars equals that constant. Use a +/- alternating multiplicative move of
    # magnitude m so |logRet| = ln(1+m) every bar (after warm-up); with a 3-bar
    # window over alternating +/- values the population stdev is constant.
    # Easiest exact check: feed weekly_annvol_series a constant-vol synthetic and
    # confirm annVol = vol*sqrt(52)*100 with vol the population stdev.
    # Use the T4 extreme history: steady annVol must exceed 45 and equal
    # avgVol*sqrt(52)*100 by construction.
    av_last = sma_series(weekly_vol_series(hist), REGIME_LEN)[-1]
    ann_last = weekly_annvol_series(hist)[-1]
    check("T11 annVol == avgVol*sqrt(52)*100 (exact identity)",
          av_last is not None and ann_last is not None and
          abs(ann_last - av_last * _m.sqrt(52) * 100.0) < 1e-9,
          f"ann={ann_last} avg={av_last}")
    check("T11 isExtreme == (annVol>45) consistent with regime series",
          weekly_regime_series(hist)[-1] == (ann_last > THRESH_XHI),
          f"ann={ann_last}")

    # ---- Test 12: deterministic state machine (hand-traceable) -----------
    # Zero-vol flat-then-step series so bw=0 and tUp==close each bar, isolating
    # the consecutive-confirmation logic. 6 equal bars (warm-up + flat) keep
    # trend=1; then we force closes strictly below the ratcheted tUp.
    # With vol=0, rawUp=close, tUp=max(tUp,close). A strictly DECREASING tail
    # makes close < tUp (=prior max) every step -> pendCnt accrues.
    flat = [100.0] * 6                 # warm-up + establish tUp=100, trend=1
    # one dip then recover (resets pendCnt), then 2 consecutive dips (Normal=2)
    seq = flat + [99.0, 100.0, 99.0, 98.0]
    r12 = weekly_signal(list(zip(wk_dates(len(seq)), seq)))
    # regime normal (vol ~0); single dip at idx6 then recover -> no flip there;
    # two consecutive dips at idx8,9 -> flip to red on idx9.
    check("T12 regime normal (zero-vol flat history)",
          r12["regime"] == "normal", f"got {r12['regime']}")
    check("T12 two consecutive sub-band closes flip Normal asset -> red",
          r12["trend"] == "red", f"got {r12['trend']}")
    # and: a SINGLE dip earlier must NOT have flipped (proves reset-on-recover)
    seq_single = flat + [99.0, 100.0, 99.0, 100.0]   # never 2 in a row
    r12b = weekly_signal(list(zip(wk_dates(len(seq_single)), seq_single)))
    check("T12 isolated single dips never flip (pendCnt resets) -> green",
          r12b["trend"] == "green", f"got {r12b['trend']}")

    print("-" * 72)
    print("Worked numbers (for eyeballing):")
    print(f"  T4 Extreme-history realised vol = {v:.1f}% (threshold 45%)")
    print(f"  T6 ATR SMA period2 = {a6}")
    print(f"  T1 last band point = {r1['band_series'][-1]}")
    print(f"  T5 monthly tail    = {out[-3:]}")
    print("-" * 72)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 72)


# ============================================================================
# ASSUMPTIONS & RESIDUAL AMBIGUITY  (one chart spot-check should confirm)
# ============================================================================
# These are the ONLY places the weekly Pine port could still differ from a live
# TradingView render. The Pine logic/parameters themselves are reproduced 1:1
# (see the correspondence table above); the items below are interpretation calls
# about Pine's built-in `ta.*` warm-up behaviour and the dashboard output shape.
#
# --- WEEKLY (Pine port) -----------------------------------------------------
# W1. ta.stdev BIASED DEFAULT. Pine's `ta.stdev(src,len)` defaults to the BIASED
#     (population, divisor N) estimator. We use population stdev (_stdev_pop,
#     divisor n), NOT the sample (N-1) estimator. If the live indicator passed
#     `ta.stdev(..., biased=false)` (it does not in the locked source), vol would
#     be larger by sqrt(N/(N-1)) = sqrt(3/2) ~ +22% and could tip near-45%
#     assets into Extreme. Pinned by test T10. Spot-check: read annVol off one
#     bar in TradingView vs realised_vol_weekly() on the same closes.
#
# W2. WARM-UP na HANDLING. Pine `ta.stdev` is na for the first `lookback-1` bars;
#     `ta.sma(vol, regimeLen)` is na until it has `regimeLen` consecutive non-na
#     vol inputs. We replicate this (None during warm-up; bw/rawUp/rawDn na ->
#     state machine idles, recording None). The very first non-na bar seeds
#     tUp/tDn (matching Pine's `if na(tUp)` re-seeding through the na warm-up).
#     This only affects roughly the first `lookback+regimeLen` (~53) bars, which
#     are ancient for a 10y weekly series. `realised_vol_weekly()` additionally
#     provides an all-available-bars FALLBACK for series shorter than ~53 bars
#     (used by tests); the steady-state value is exact Pine and unaffected.
#
# W3. ta.sma OVER na INPUTS. We treat `ta.sma(vol, regimeLen)` as requiring a
#     full window of non-na vol values before emitting (any None in the window
#     -> None). This matches Pine's standard `ta.sma` na-propagation on a series
#     that is itself na early. If TradingView's session/gap handling differs on
#     the user's symbol, only the first ~53 bars could shift.
#
# W4. annVol ANNUALISATION. Exactly `avgVol*math.sqrt(52)*100` (sqrt(52), times
#     100 for percent), per the locked source. No alternative (252/52.18) is
#     used. Pinned by test T11.
#
# W5. OUTPUT-SHAPE MAPPING (dashboard contract, not Pine). The dict the pipeline
#     consumes is derived from the Pine `var`s:
#       - trend: final `trend` var (1->"green", -1->"red").
#       - regime: isExtreme on the LAST bar ("extreme"/"normal").
#       - since: first bar of the current uninterrupted run, as "Mon YYYY" from
#         the weekly bar date. (Granularity choice -- exact week/flip-date is a
#         one-line change if the dashboard wants it.)
#       - trendChange: Pine's alertcondition fires on a flip vs the immediately
#         prior bar; we surface it as "flipped on the last bar OR the one before"
#         (this week or last week). If "last week" must mean a fixed calendar
#         lag, adjust.
#       - band_series[i].s: the ACTIVE stop AFTER the per-bar update (tUp when
#         trend==1, tDn when trend==-1); .g = 1 if trend==1 else 0; .d = 'YYYY-MM'.
#     None of this changes the Pine trend/flip computation -- only how it is
#     reported.
#
# --- MONTHLY (ATR SuperTrend -- author-confirmed, NOT part of the Pine port) -
# M1. monthly_signal is the M2/ISM SuperTrend and is left intact by request.
#     It uses a close-to-close true range (feeds are close-only), SMA smoothing
#     by default (Wilder optional via atr_smoothing), seeds direction=+1 at the
#     first ATR-available bar, flips instantly (confirm=1), and reports the active
#     band as `s`. These choices belong to the monthly signal only; the weekly
#     W-notes above do not apply to it.

if __name__ == "__main__":
    _run_tests()
