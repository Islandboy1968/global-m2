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
2. THE MONTHLY SIGNAL -- STANDARD TRADINGVIEW SUPERTREND (Wilder/RMA ATR)
==============================================================================
`monthly_signal(...)` is the M2/ISM "normal SuperTrend". The author confirms it
is just the STANDARD TradingView SuperTrend, so this is a faithful port of the
built-in Pine `ta.supertrend(factor, atrPeriod)` band/flip mechanic:

  * Volatility unit = ATR over a close-to-close true range TR_t=|C_t-C_{t-1}|.
    NOTE: the dashboard feeds are close-only (a single series, no OHLC), so the
    Wilder TR max(H-L, |H-C[1]|, |L-C[1]|) collapses to |C_t - C_{t-1}|. This is
    the ONLY TR definition available without OHLC.
  * ATR = Wilder's RMA of TR (the TradingView `ta.atr` default smoothing), NOT
    a plain SMA. RMA's heavy trailing memory is what gives standard SuperTrend
    its smooth, slow-to-flip bands.
  * upperBasic = src + mult*ATR ; lowerBasic = src - mult*ATR. The canonical TV
    band-carry/lock rule then keeps each final band locked unless the basic band
    moves it further out, or the PRIOR close pierced it (so a touched band is
    released). Trend flips INSTANTLY (no confirmation) when the close crosses the
    locked band, per the standard `ta.supertrend` direction recurrence.
  * Calibrated params (see build_risk_monitor.build_macro): M2 and ISM both use
    atr_period=10 (TV default), mult=3.5 (one notch above the TV default 3.0).
    The factor was raised from 3.0 to 3.5 to widen the bands just enough to
    remove the spurious monthly red flips; everything else is TV-default.

The earlier engine was an SMA-based, close-only ATR SuperTrend with short periods
(M2=6, ISM=12). The SMA smoothing + short ATR made the bands too tight and caused
the over-sensitive red flips this rewrite fixes.

`monthly_signal` and the `_supertrend_standard` / ATR helpers below it are NOT
part of the Pine weekly port; the weekly assumptions (A-notes) do not apply.

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

# Monthly SuperTrend params (standard TradingView SuperTrend, Wilder/RMA ATR).
# TV defaults are length 10 / factor 3.0; we keep length 10 and raise the factor
# to 3.5 (the smallest bump that removes the spurious monthly red flips). Same
# settings for both series so the deviation from default is single + consistent.
M2_ATR_PERIOD, M2_MULT = 10, 3.5     # monthly Global M2 composite SuperTrend
ISM_ATR_PERIOD, ISM_MULT = 10, 3.5   # monthly ISM SuperTrend


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
# Standard TradingView SuperTrend band engine (monthly M2/ISM)
# ============================================================================

def _supertrend_standard(closes: Sequence[float],
                         atr: Sequence[Optional[float]],
                         mult: float
                         ) -> Tuple[List[Optional[float]], List[Optional[int]]]:
    """Faithful port of the built-in TradingView Pine `ta.supertrend(factor,
    atrPeriod)` band + direction recurrence.

    Args:
      closes : source/close series (`src`; close-only, no OHLC).
      atr    : Wilder/RMA ATR aligned to `closes` (None where not yet available).
      mult   : ATR multiplier (`factor`).

    Returns (supertrend, dir) aligned to closes:
      supertrend[i] = the active SuperTrend stop level for bar i (None pre-ATR).
      dir[i]        = +1 rising (uptrend) / -1 falling (downtrend); None pre-ATR.

    Canonical Pine `ta.supertrend` source this mirrors line-for-line::

        upperBasic = src + factor*atr
        lowerBasic = src - factor*atr
        lowerBand := lowerBasic > prevLowerBand or close[1] < prevLowerBand
                       ? lowerBasic : prevLowerBand
        upperBand := upperBasic < prevUpperBand or close[1] > prevUpperBand
                       ? upperBasic : prevUpperBand
        if na(atr[1])
            direction := 1                       // (down-trend seed in Pine)
        else if prevSuperTrend == prevUpperBand
            direction := close > upperBand ? -1 : 1
        else
            direction := close < lowerBand ? 1 : -1
        superTrend := direction == -1 ? lowerBand : upperBand

    Pine encodes direction as -1=up / 1=down. We translate to the dashboard
    convention (+1 rising/green, -1 falling/red) on the way out: a Pine
    direction of -1 (price riding the lower band) -> our +1.

    Bands are LOCKED (carried forward) unless the new basic band is further out
    or the PRIOR close pierced the locked band, which releases it. The trend
    flips INSTANTLY (no confirmation) the bar the close crosses the locked band.
    The wide Wilder/RMA ATR is what keeps the bands smooth and the flips rare.
    """
    n = len(closes)
    st_out: List[Optional[float]] = [None] * n
    dir_out: List[Optional[int]] = [None] * n

    start = next((i for i in range(n) if atr[i] is not None), None)
    if start is None:
        return st_out, dir_out

    prev_lower: Optional[float] = None     # prevLowerBand
    prev_upper: Optional[float] = None     # prevUpperBand
    prev_st: Optional[float] = None        # prevSuperTrend
    prev_close: Optional[float] = None     # close[1]

    for i in range(start, n):
        src = closes[i]
        upper_basic = src + mult * atr[i]
        lower_basic = src - mult * atr[i]

        if prev_lower is None:                       # first ATR bar: na(atr[1])
            lower_band = lower_basic
            upper_band = upper_basic
            pine_dir = 1                             # Pine seeds direction = 1
        else:
            lower_band = (lower_basic
                          if lower_basic > prev_lower or prev_close < prev_lower
                          else prev_lower)
            upper_band = (upper_basic
                          if upper_basic < prev_upper or prev_close > prev_upper
                          else prev_upper)
            if prev_st == prev_upper:
                pine_dir = -1 if src > upper_band else 1
            else:
                pine_dir = 1 if src < lower_band else -1

        super_trend = lower_band if pine_dir == -1 else upper_band

        # translate Pine (-1 up / +1 down) -> dashboard (+1 rising / -1 falling)
        dir_out[i] = 1 if pine_dir == -1 else -1
        st_out[i] = super_trend

        prev_lower, prev_upper, prev_st, prev_close = (
            lower_band, upper_band, super_trend, src)

    return st_out, dir_out


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
                   atr_smoothing: str = "wilder") -> List[Dict]:
    """Compute the monthly STANDARD TradingView SuperTrend (Wilder/RMA ATR).

    This is the standard `ta.supertrend(factor=mult, atrPeriod=atr_period)`:
    Wilder/RMA-smoothed ATR over the close-only true range TR_t=|C_t-C_{t-1}|
    (the only TR available without OHLC), upper/lower basic bands at
    src +/- mult*ATR, the canonical band-carry/lock rule, and an INSTANT flip
    (no confirmation) when the close crosses the locked band.

    Args:
      values_with_dates: sorted list of (date_str, value). date_str 'YYYY-MM' or
          'YYYY-MM-DD'.
      atr_period: ATR length (calibrated 10 for both M2 and ISM; TV default 10).
      mult: ATR multiplier / factor (calibrated 3.5 for both; TV default 3.0).
      atr_smoothing: "wilder" (standard SuperTrend, default) or "sma".

    Returns a list of chart points (only where the band is defined):
      [{"d": "YYYY-MM", "c": value, "s": band_level, "g": 1|0}, ...]
      where s = the active SuperTrend stop and g = 1 rising / 0 falling.
    """
    pts = list(values_with_dates)
    dates = [d for d, _ in pts]
    closes = [float(v) for _, v in pts]
    tr = true_range_close_only(closes)
    atr = atr_series(tr, atr_period, smoothing=atr_smoothing)
    band, direction = _supertrend_standard(closes, atr, mult)

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

    # ---- Test 5: monthly_signal STANDARD SuperTrend (Wilder ATR) ---------
    # Rising then crashing monthly composite. Standard SuperTrend flips INSTANTLY
    # (no confirmation) when the close crosses the locked band. Check field
    # names/types, that it starts green on the rise and ends red after the crash,
    # and that the active stop `s` sits below price while green / above while red.
    mdates = []
    yy, mm = 2023, 1
    # 18 steadily rising months (so the ST locks green well after warm-up) then a
    # sharp crash that pierces the green stop and flips it red.
    mv = [100.0 * (1.03 ** i) for i in range(18)] + [130.0, 100.0, 75.0, 60.0]
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
    # The seed bar's direction is arbitrary (Pine seeds down at the first ATR
    # bar); the steady rise locks the ST green before the crash. There must be a
    # block of green bars during the rise, and the crash flips it back to red.
    check("T5 monthly is green during the rise (>=3 green bars)",
          sum(1 for p in out if p["g"] == 1) >= 3,
          f"green bars={sum(1 for p in out if p['g']==1)}")
    # instant flip: the FIRST crash bar (price drops far below the green stop) is
    # already red on that very bar, with no confirmation lag.
    last_green_i = max(i for i, p in enumerate(out) if p["g"] == 1)
    check("T5 instant flip: bar after last green is red (no confirmation)",
          out[last_green_i + 1]["g"] == 0,
          f"g after last green={out[last_green_i + 1]['g']}")
    # Standard-SuperTrend invariant: while green the stop is the lower band
    # (<= price); while red the stop is the upper band (>= price).
    check("T5 green stop <= price, red stop >= price (band side correct)",
          all((p["s"] <= p["c"]) if p["g"] == 1 else (p["s"] >= p["c"])
              for p in out),
          "a stop is on the wrong side of price")

    # ---- Test 5b: Wilder SuperTrend HAND-COMPUTED on a tiny series -------
    # closes = [10, 11, 12, 9]; TR = [0, 1, 1, 3]; period=2, Wilder ATR:
    #   atr[1] = (0+1)/2 = 0.5  (seed = SMA of first 2 TRs)
    #   atr[2] = (0.5*1 + 1)/2 = 0.75
    #   atr[3] = (0.75*1 + 3)/2 = 1.875
    # factor mult=1.0. Walk the standard SuperTrend:
    #  i=1 (seed): lower=11-0.5=10.5, upper=11+0.5=11.5, pine_dir=1(down) ->
    #              st=upper=11.5, our g = (pine_dir==-1)?1:0 = 0 (red seed).
    #  i=2 src=12 atr=0.75: lowerBasic=11.25 upperBasic=12.75
    #     prev_close=11; lower: 11.25>10.5 -> 11.25; upper: 12.75<11.5? no,
    #       and 11>11.5? no -> keep 11.5. prev_st(11.5)==prev_upper(11.5) ->
    #       pine_dir = (12>11.5)? -1(up): 1 -> -1(up). st=lower=11.25. g=1.
    #  i=3 src=9 atr=1.875: lowerBasic=7.125 upperBasic=10.875
    #     prev_close=12; lower: 7.125>11.25? no, 12<11.25? no -> keep 11.25.
    #       upper: 10.875<11.5 -> 10.875. prev_st(11.25)==prev_upper(11.5)? no ->
    #       pine_dir = (9<11.25)? 1(down): -1 -> 1(down). st=upper=10.875. g=0.
    hb = monthly_signal(
        [("2025-01", 10.0), ("2025-02", 11.0), ("2025-03", 12.0),
         ("2025-04", 9.0)], atr_period=2, mult=1.0)
    check("T5b Wilder ST hand-calc g-sequence == [0,1,0]",
          [p["g"] for p in hb] == [0, 1, 0], f"got {[p['g'] for p in hb]}")
    check("T5b Wilder ST hand-calc stops == [11.5, 11.25, 10.88]",
          [p["s"] for p in hb] == [11.5, 11.25, 10.88],
          f"got {[p['s'] for p in hb]}")
    check("T5b instant flip up at i=2 (no confirmation needed)",
          hb[1]["g"] == 1, f"got g={hb[1]['g']}")

    # ---- Test 6: ATR SMA closed form (hand-computable) -------------------
    # TR for closes [10, 12, 11, 14] (close-only) = [0, 2, 1, 3].
    # ATR period 2, SMA: index1 = (0+2)/2 = 1.0; index2 = (2+1)/2=1.5;
    # index3 = (1+3)/2 = 2.0.
    tr6 = true_range_close_only([10, 12, 11, 14])
    check("T6 close-only TR = [0,2,1,3]", tr6 == [0.0, 2.0, 1.0, 3.0], f"got {tr6}")
    a6 = atr_series(tr6, 2, "sma")
    check("T6 ATR SMA period2 = [None,1.0,1.5,2.0]",
          a6 == [None, 1.0, 1.5, 2.0], f"got {a6}")
    # Wilder/RMA ATR period 2 on the same TR [0,2,1,3]:
    #   seed atr[1] = (0+2)/2 = 1.0
    #   atr[2] = (1.0*1 + 1)/2 = 1.0
    #   atr[3] = (1.0*1 + 3)/2 = 2.0
    a6w = atr_series(tr6, 2, "wilder")
    check("T6 ATR Wilder period2 = [None,1.0,1.0,2.0]",
          a6w == [None, 1.0, 1.0, 2.0], f"got {a6w}")

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
    print(f"  T6 ATR SMA period2 = {a6} ; Wilder period2 = {a6w}")
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
# --- MONTHLY (STANDARD TradingView SuperTrend -- NOT part of the Pine port) --
# M1. monthly_signal is the M2/ISM standard `ta.supertrend`. It uses Wilder/RMA
#     ATR over a close-to-close true range TR_t=|C_t-C_{t-1}| (the feeds are
#     close-only, so this is the only TR definition possible -- the OHLC Wilder
#     TR collapses to it). It applies the canonical band-carry/lock rule, seeds
#     direction at the first ATR-available bar (Pine na(atr[1]) branch), and
#     flips INSTANTLY (no confirmation). Params: M2 and ISM both length 10 /
#     factor 3.5 (TV default 10/3.0, factor raised one notch to widen the bands
#     and remove the over-sensitive monthly red flips).
#
# M2note. ISM "green since early 2023" is NOT achievable for a trend-following
#     SuperTrend and is a genuine data constraint, not a tuning artefact. The
#     real ISM PMI fell from ~57 (Jan 2022) to a 46.0 trough (Jun 2023) and only
#     durably turned up in 2024. Any honest SuperTrend therefore stays RED
#     through the 2022-2023 decline and flips GREEN only as the uptrend forms
#     (Mar 2024 at length 10 / factor 3.5), with ZERO red flips after the 2022
#     red -- which is what the calibration delivers. M2, by contrast, rose from
#     late 2022 and DOES satisfy green-since-Nov-2022 with no later reds.

if __name__ == "__main__":
    _run_tests()
