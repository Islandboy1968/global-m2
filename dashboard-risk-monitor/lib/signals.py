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
1. INTERPRETATION OF THE INDICATOR
==============================================================================
The spec describes a "volatility-adaptive trailing band" whose support band
"only ratchets UP (never down)" in an uptrend (symmetric on the downside). That
is exactly the mechanic of an **ATR-based SuperTrend / Chandelier-style trailing
stop**:

  * Compute a volatility unit (ATR -- Average True Range).
  * Build an upper band = source + mult*ATR and a lower band = source - mult*ATR.
  * The ACTIVE band ratchets monotonically in the trend direction (lower band can
    only rise while in an uptrend; upper band can only fall while in a downtrend)
    and the trend flips when price closes through the active band.

This is the classic SuperTrend recurrence (Olivier Seban). The only GMI-specific
twist is the **confirmation filter** on the WEEKLY signal: a flip is not taken on
the first piercing close; it requires N consecutive closes beyond the band
(N = 2 normally, N = 3 in the "Extreme" volatility regime). The MONTHLY signal
uses the same band machinery but with N = 1 (flips instantly).

--- ATR with close-only data vs OHLC -----------------------------------------
True Range needs OHLC: TR_t = max(High-Low, |High-Close_{t-1}|, |Low-Close_{t-1}|).
The GMI Risk Monitor feeds (M2 composite, ISM, and the weekly asset closes it
recomputes server-side) are CLOSE-ONLY series. With no high/low, the robust and
standard fallback is the **close-to-close true range**:

        TR_t = |Close_t - Close_{t-1}|        (t >= 1),   TR_0 = 0

ATR is then the rolling average of TR over `atr_period`. We use a **simple moving
average (SMA) of TR**, seeded by the SMA of the first `atr_period` TRs, because it
is exactly reproducible by hand and matches TradingView's default `ta.atr` when
fed a close-only true range. (TradingView's `ta.atr` actually uses RMA/Wilder
smoothing; we expose `atr_smoothing` so a human can switch to Wilder once the real
indicator's setting is confirmed -- see ASSUMPTIONS.)

When OHLC IS available, pass it via `weekly_signal(..., ohlc=...)` /
`true_range_ohlc()` and the full Wilder true range is used instead. The default
path is close-only.

--- Parameter mapping --------------------------------------------------------
"sensitivity 3.5 / 4.0"  -> the ATR multiplier `mult`:
        Normal  regime: mult = 3.5
        Extreme regime: mult = 4.0   (wider band in violent markets -> fewer whipsaws)
"confirm 2 / 2 / 3"      -> consecutive-close confirmation count:
        Normal  regime: 2   (1st number)
        Normal  regime: 2   (2nd number -- the symmetric up/down count; the spec
                             lists the same value for "flip down" and "flip up")
        Extreme regime: 3   (3rd number -- the Extreme-regime confirmation count)
   i.e. the triplet is (confirm_down_normal, confirm_up_normal, confirm_extreme).
   Both directions share the same count within a regime; Extreme raises it to 3.
"lookback 3"             -> the ATR period for the WEEKLY signal (atr_period=3).
"regime lookback 50"     -> the realised-vol window (50 weekly returns).
"extreme threshold 45%"  -> annualised 50-week vol > 45% => Extreme.

==============================================================================
2. THE "EXTREME" VOLATILITY REGIME
==============================================================================
Realised volatility over the trailing `REGIME_LOOKBACK` (=50) weekly log returns,
annualised by sqrt(52):

    r_i      = ln(C_i / C_{i-1})                     (weekly log returns)
    sigma_w  = sample stdev of the last 50 r_i       (divisor n-1)
    vol_ann  = sigma_w * sqrt(52)                     (as a fraction)
    Extreme  <=>  vol_ann * 100 > 45.0               (i.e. > 45%)

If fewer than `REGIME_LOOKBACK`+1 closes exist, all available returns are used.

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

WEEKLY_ATR_PERIOD = 3            # "lookback 3"
SENS_NORMAL = 3.5               # "sensitivity 3.5" -> ATR multiplier, Normal regime
SENS_EXTREME = 4.0              # "sensitivity 4.0" -> ATR multiplier, Extreme regime
CONFIRM_NORMAL = 2             # "confirm 2/2" -> consecutive closes to flip (Normal)
CONFIRM_EXTREME = 3           # "confirm ...3" -> consecutive closes to flip (Extreme)
REGIME_LOOKBACK = 50          # "regime lookback 50 weeks"
EXTREME_VOL_THRESHOLD = 45.0  # "extreme volatility threshold 45%" (annualised, %)
WEEKS_PER_YEAR = 52           # annualisation factor for weekly vol
MONTHS_PER_YEAR = 12          # (unused for monthly band; kept for documentation)

M2_ATR_PERIOD, M2_MULT = 6, 3.0     # monthly M2 composite dev-locked params
ISM_ATR_PERIOD, ISM_MULT = 12, 3.0  # monthly ISM dev-locked params


# ============================================================================
# Internal helpers
# ============================================================================

def _stdev_sample(xs: Sequence[float]) -> float:
    """Sample standard deviation (divisor n-1). 0.0 if fewer than 2 points."""
    n = len(xs)
    if n < 2:
        return 0.0
    mean = sum(xs) / n
    var = sum((x - mean) ** 2 for x in xs) / (n - 1)
    return math.sqrt(var)


def realised_vol_weekly(closes: Sequence[float],
                        lookback: int = REGIME_LOOKBACK) -> Optional[float]:
    """Annualised realised vol (%) from the trailing `lookback` WEEKLY log returns.

    Returns None if there are fewer than 2 closes (cannot form a return).
    """
    if closes is None or len(closes) < 2:
        return None
    rets = [math.log(closes[i] / closes[i - 1])
            for i in range(1, len(closes))
            if closes[i - 1] > 0 and closes[i] > 0]
    if len(rets) < 2:
        return None
    window = rets[-lookback:]
    return _stdev_sample(window) * math.sqrt(WEEKS_PER_YEAR) * 100.0


def is_extreme_regime(closes: Sequence[float],
                      lookback: int = REGIME_LOOKBACK,
                      threshold: float = EXTREME_VOL_THRESHOLD) -> bool:
    """True iff annualised 50-week realised vol > threshold (%). Default False."""
    v = realised_vol_weekly(closes, lookback)
    return v is not None and v > threshold


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
    appears at index `period-1`. See ASSUMPTIONS for why this matters.
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
    streak. Holding the band monotonic preserves the 2/3-close confirmation the
    spec requires. See ASSUMPTIONS A3.
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

    cur_dir = 1                       # seed rising (warm-up; see ASSUMPTIONS A3)
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

def weekly_signal(closes_with_dates: Sequence[Tuple[str, float]],
                  ohlc: Optional[Sequence[Tuple[float, float, float]]] = None,
                  atr_period: int = WEEKLY_ATR_PERIOD,
                  atr_smoothing: str = "sma") -> Optional[Dict]:
    """Compute the GMI Weekly Trend Signal for one asset.

    Args:
      closes_with_dates: chronologically sorted list of (date_str, close).
          date_str is 'YYYY-MM-DD' (weekly bar date).
      ohlc: optional aligned list of (high, low, close) to use the full Wilder
          true range. When None (default) the close-only true range is used.
      atr_period: ATR lookback (dev-locked 3).
      atr_smoothing: "sma" (default, hand-reproducible) or "wilder".

    Returns dict or None (None if fewer than atr_period+1 bars):
      {
        "trend":       "green" | "red",   # current trend (rising/falling)
        "since":       "Mon YYYY",        # date the CURRENT trend began
        "trendChange": bool,              # flipped this week or last week
        "band_series": [{"d","c","s","g"}, ...]   # full per-bar series
      }

    The regime (Normal/Extreme) is evaluated on the trailing 50 weekly returns of
    the SAME closes; it sets the multiplier (3.5/4.0) and confirmation count (2/3).
    """
    pts = list(closes_with_dates)
    if len(pts) < atr_period + 1:
        return None
    dates = [d for d, _ in pts]
    closes = [float(c) for _, c in pts]

    extreme = is_extreme_regime(closes)
    mult = SENS_EXTREME if extreme else SENS_NORMAL
    confirm = CONFIRM_EXTREME if extreme else CONFIRM_NORMAL

    if ohlc is not None:
        highs = [h for h, _, _ in ohlc]
        lows = [l for _, l, _ in ohlc]
        ocl = [c for _, _, c in ohlc]
        tr = true_range_ohlc(highs, lows, ocl)
    else:
        tr = true_range_close_only(closes)

    atr = atr_series(tr, atr_period, smoothing=atr_smoothing)
    band, direction = _supertrend(closes, atr, mult, confirm=confirm)

    # build the per-bar series
    series = []
    for i in range(len(closes)):
        if direction[i] is None:
            continue
        series.append({
            "d": dates[i][:7] if len(dates[i]) >= 7 else dates[i],
            "c": round(closes[i], 4),
            "s": None if band[i] is None else round(band[i], 4),
            "g": 1 if direction[i] == 1 else 0,
        })

    if not series:
        return None

    # current trend
    last_dir = direction[-1]
    trend = "green" if last_dir == 1 else "red"

    # "since": walk back to the first bar of the current uninterrupted run
    since_idx = len(direction) - 1
    while since_idx > 0 and direction[since_idx - 1] == last_dir:
        since_idx -= 1
    # but only count bars that actually have a direction
    since_idx = max(since_idx, next(i for i in range(len(direction))
                                    if direction[i] is not None))
    since = _month_year(dates[since_idx])

    # trendChange: flipped this week (last bar starts a new run) or last week
    valid_idx = [i for i in range(len(direction)) if direction[i] is not None]
    trend_change = False
    if len(valid_idx) >= 2:
        last = valid_idx[-1]
        prev = valid_idx[-2]
        flipped_this_week = direction[last] != direction[prev]
        flipped_last_week = False
        if len(valid_idx) >= 3:
            prev2 = valid_idx[-3]
            flipped_last_week = direction[prev] != direction[prev2]
        trend_change = flipped_this_week or flipped_last_week

    return {
        "trend": trend,
        "since": since,
        "trendChange": trend_change,
        "regime": "extreme" if extreme else "normal",
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
# ASSUMPTIONS & UNCERTAINTIES  (confirm against the real TradingView indicator)
# ============================================================================
#
# A1. ATR DEFINITION (close-only vs OHLC). The dashboard feeds are close-only, so
#     we default to close-to-close true range TR_t=|C_t - C_{t-1}|. The real
#     TradingView indicator very likely runs on OHLC bars and uses ta.atr (full
#     true range). Band WIDTHS will differ. If OHLC is available server-side,
#     pass ohlc= / use true_range_ohlc and reconfirm the multipliers. (Hook
#     provided.)
#
# A2. ATR SMOOTHING. We default to SMA of TR (exactly hand-reproducible).
#     TradingView's ta.atr uses Wilder/RMA smoothing. Set atr_smoothing="wilder"
#     to match if confirmed. This shifts band levels modestly, mostly early in
#     the series. Direction/flip results are usually unaffected for clean tests.
#
# A3. BAND INITIALISATION / SEED DIRECTION. SuperTrend has no canonical first
#     bar. We seed direction=+1 (rising) at the first bar that has an ATR
#     (index atr_period-1) and let the confirmed-pierce logic establish the real
#     trend from there. Early bars (first ~atr_period+confirm) should be treated
#     as warm-up and not trusted. The real indicator may seed from the first
#     close vs its band; confirm the very first few points if they matter.
#
# A4. "CONFIRM 2/2/3" TRIPLET. Interpreted as
#     (confirm_down_normal, confirm_up_normal, confirm_extreme) = (2, 2, 3),
#     i.e. both directions use 2 in Normal and 3 in Extreme. The spec text
#     ("2 consecutive... 3 when Extreme... Symmetric for the reverse") supports
#     a single per-regime count shared by both directions. If instead the three
#     numbers mean (down, up, extreme-for-both) with DIFFERENT up vs down counts,
#     split CONFIRM_NORMAL into two constants -- one-line change.
#
# A5. SENSITIVITY -> MULTIPLIER. We map sensitivity 3.5/4.0 directly to the ATR
#     multiplier (Normal 3.5, Extreme 4.0). Some indicators invert "sensitivity"
#     (higher sensitivity = TIGHTER band = smaller multiplier). The spec's intent
#     ("Extreme regime widens the band to avoid whipsaws") is consistent with our
#     mapping (4.0 > 3.5). Confirm the direction of the sensitivity knob.
#
# A6. REGIME WINDOW UNITS. "regime lookback 50 weeks" is applied to 50 weekly
#     LOG returns, annualised by sqrt(52). If the real indicator uses simple
#     returns or sqrt(52) on a different base (e.g. 52.18), figures shift a few
#     tenths of a percent -- rarely enough to cross the 45% boundary, but check
#     near-boundary assets.
#
# A7. "SINCE" GRANULARITY. We emit "Mon YYYY" (e.g. "Nov 2025") taken from the
#     weekly bar date that STARTS the current run. If the dashboard wants the
#     exact week date or the FLIP-confirmation date (vs the run-start date), this
#     is a one-line change in weekly_signal.
#
# A8. "TRENDCHANGE = this week or last week". We define it as: the trend flipped
#     between the last two valid bars (this week) OR between the prior two (last
#     week). If "last week" should instead mean a fixed calendar lag, adjust.
#
# A9. WEEKLY ATR PERIOD = "lookback 3". We read the weekly "lookback 3" as the
#     ATR period (3 weekly bars). It could alternatively mean a 3-bar source
#     smoothing or a different internal lookback; confirm against the indicator's
#     input labels.
#
# A10. MONTHLY band level reported. We report s = the ACTIVE band (support when
#      green, resistance when red), matching SuperTrend's single visible stop
#      line. If the chart wants BOTH bands or the opposite-side band at a flip,
#      expose final_upper/final_lower (already computed internally).

if __name__ == "__main__":
    _run_tests()
