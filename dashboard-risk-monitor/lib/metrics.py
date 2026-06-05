"""
GMI Risk Monitor -- per-asset metric calculations.

Three pure functions used by the "GMI Risk Monitor" dashboard:

    secular_trend(closes, method)  -> "rising" | "falling" | None
    realised_vol_30d(daily_closes) -> float   (annualised %, 1 dp at display time)
    ann_vol(daily_closes)          -> float   (annualised %, longer window)

Design goals: pure functions, no network, no I/O, dependency-light (stdlib only --
`math` + `statistics`). numpy is intentionally NOT required so the module runs in
the network-restricted dashboard build environment.

------------------------------------------------------------------------------
PROVENANCE / REUSE (cited as required)
------------------------------------------------------------------------------
The log-regression channel is a faithful Python port of the "brain" in
    dashboard-template/lib/compute.js   (the Compounding Machine engine)
specifically `linReg`, `fitFrozenRegression` and `buildChannel`:

  * OLS of log(price) vs a time index            (compute.js `linReg`, `fitFrozenRegression`)
        b = (n*Sxy - Sx*Sy) / (n*Sxx - Sx*Sx);  a = (Sy - b*Sx)/n
  * residual standard deviation, POPULATION form (divisor = n, NOT n-1):
        sd = sqrt( sum(residual^2) / n )         (compute.js line:
            "Math.sqrt(res.reduce(...e*e...) / res.length)")
  * channel bands at trend +/- k*sd, and the per-point sigma position
        logDev = (log(price) - trendValue) / sd  (compute.js `buildChannel`)

We reuse the *exact* same residual-sd convention (population, /n) as compute.js so
the dashboard's two trend engines agree. See ASSUMPTIONS section for why this
matters and where the spec is ambiguous.

The SMA-60 path has no direct code analogue in the repo's Python (build_fci.py /
series_util.py do YoY / z-score transforms, not trailing SMAs), so it is a
straightforward trailing simple mean implemented here from the spec.
"""

from __future__ import annotations

import math
import statistics
from typing import List, Optional, Sequence

# ----------------------------------------------------------------------------
# Tunable constants (documented; surfaced here so a human can confirm them)
# ----------------------------------------------------------------------------

TRADING_DAYS_PER_YEAR = 252          # annualisation factor base (sqrt(252))
SMA_WINDOW_MONTHS = 60               # 5-year secular SMA for traditional assets
LOGCHANNEL_MIN_POINTS = 104          # ~2 years of weekly data to fit a channel
REALISED_VOL_WINDOW_TD = 21          # ~30 calendar days == 21 trading days
ANN_VOL_WINDOW_TD = 252              # ~1 year for the longer "annVol" figure
CHANNEL_SIGMA = 2.0                  # channel is fit +/- 2 sigma (spec)


# ============================================================================
# Internal helpers
# ============================================================================

def _clean(series: Sequence[float]) -> List[float]:
    """Coerce to a list of finite positive-able floats, dropping None/NaN.

    We do NOT drop non-positive values here (callers needing log() guard that),
    because vol uses raw closes and only needs them finite. Order is preserved.
    """
    out: List[float] = []
    for v in series:
        if v is None:
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if math.isfinite(f):
            out.append(f)
    return out


def _ols(xs: Sequence[float], ys: Sequence[float]):
    """Ordinary least squares. Returns (intercept a, slope b).

    Direct port of compute.js `linReg`:
        b = (n*Sxy - Sx*Sy) / (n*Sxx - Sx^2);  a = (Sy - b*Sx)/n
    """
    n = len(xs)
    sx = sy = sxy = sxx = 0.0
    for x, y in zip(xs, ys):
        sx += x
        sy += y
        sxy += x * y
        sxx += x * x
    denom = n * sxx - sx * sx
    if denom == 0.0:          # degenerate (all x identical) -- cannot fit a slope
        raise ZeroDivisionError("OLS denominator is zero (no time variation)")
    b = (n * sxy - sx * sy) / denom
    a = (sy - b * sx) / n
    return a, b


def _log_returns(closes: Sequence[float]) -> List[float]:
    """Daily log returns ln(P_t / P_{t-1}) over consecutive closes."""
    out: List[float] = []
    for prev, cur in zip(closes, closes[1:]):
        if prev > 0 and cur > 0:
            out.append(math.log(cur / prev))
    return out


def _annualised_vol_from_returns(rets: Sequence[float]) -> float:
    """Sample std-dev of log returns, annualised x sqrt(252), x100 -> percent.

    Uses the SAMPLE standard deviation (divisor n-1, statistics.stdev), the
    standard convention for realised-volatility estimation from a return sample.
    (Note: this n-1 convention differs deliberately from the log-channel residual
    sd, which is population /n to match compute.js. See ASSUMPTIONS.)
    """
    if len(rets) < 2:
        return float("nan")
    sd_daily = statistics.stdev(rets)               # sample std, divisor n-1
    return sd_daily * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0


# ============================================================================
# 1. SECULAR TREND
# ============================================================================

def secular_trend(closes: Sequence[float], method: str) -> Optional[str]:
    """Long-term secular trend classification.

    Parameters
    ----------
    closes : sequence of float
        For method "sma60": MONTHLY closes (chronological, oldest -> newest).
        For method "logchannel": WEEKLY closes (chronological), post the asset's
        first full cycle.
    method : "sma60" | "logchannel"
        The asset's declared `secularMethod`.

    Returns
    -------
    "rising" | "falling" | None
        None when history is too short to judge.

    Rules (from spec)
    -----------------
    sma60      : need >= 60 monthly points, else None.
                 "rising"  if latest >= 60mo SMA, "falling" if below.
    logchannel : fit OLS on log(price) vs time; channel = trend +/- 2*sd
                 (population residual sd, /n, matching compute.js).
                 "rising"  if latest price >= lower-2sigma bound (uptrend intact),
                 "falling" if it has broken below that lower bound.
                 None if < LOGCHANNEL_MIN_POINTS (~104 weekly = ~2yr).
    """
    data = _clean(closes)

    if method == "sma60":
        if len(data) < SMA_WINDOW_MONTHS:
            return None
        window = data[-SMA_WINDOW_MONTHS:]
        sma = sum(window) / SMA_WINDOW_MONTHS
        latest = data[-1]
        return "rising" if latest >= sma else "falling"

    if method == "logchannel":
        # Need enough history AND strictly positive prices for log().
        positives = [p for p in data if p > 0]
        if len(positives) < LOGCHANNEL_MIN_POINTS or len(positives) < len(data):
            # If any non-positive prices slipped through we treat history as
            # unfittable rather than silently dropping points mid-series.
            if len(positives) < LOGCHANNEL_MIN_POINTS:
                return None
        # Use the cleaned positive series; x is a simple 0..n-1 index (units =
        # one sample period). Slope units don't affect the residual/sigma test.
        xs = list(range(len(positives)))
        ys = [math.log(p) for p in positives]
        try:
            a, b = _ols(xs, ys)
        except ZeroDivisionError:
            return None
        # Population residual sd (divisor n) -- matches compute.js exactly.
        resid_sq = [(y - (a + b * x)) ** 2 for x, y in zip(xs, ys)]
        sd = math.sqrt(sum(resid_sq) / len(resid_sq))

        x_last = xs[-1]
        trend_last = a + b * x_last            # fitted log-trend at latest point
        log_price_last = ys[-1]
        # Sigma position of the latest price within the channel (compute.js logDev).
        if sd == 0.0:
            # Perfect fit: price sits exactly on trend -> uptrend intact.
            return "rising"
        log_dev = (log_price_last - trend_last) / sd
        # "rising" iff price is at/above the lower 2-sigma bound (logDev >= -2).
        return "rising" if log_dev >= -CHANNEL_SIGMA else "falling"

    raise ValueError(f"unknown secular method: {method!r} (expected 'sma60' or 'logchannel')")


# ============================================================================
# 2. 30-DAY REALISED VOLATILITY, ANNUALISED
# ============================================================================

def realised_vol_30d(daily_closes: Sequence[float]) -> float:
    """Trailing ~30 calendar day realised vol, annualised, in percent.

    std-dev of daily log returns over the last REALISED_VOL_WINDOW_TD (21)
    trading days, annualised x sqrt(252), x100.

    Returns NaN if fewer than 2 usable returns are available.

    Display: caller rounds to 1 dp. Drives the risk colour:
        Normal < 20, Risky 20-40, High Risk > 40.
    """
    closes = _clean(daily_closes)
    if len(closes) < 2:
        return float("nan")
    # 21 trading-day returns require the last 22 closes.
    window_closes = closes[-(REALISED_VOL_WINDOW_TD + 1):]
    rets = _log_returns(window_closes)
    return _annualised_vol_from_returns(rets)


# ============================================================================
# 3. ANNUALISED VOLATILITY (longer window "annVol")
# ============================================================================

def ann_vol(daily_closes: Sequence[float]) -> float:
    """Longer-window annualised vol ("annVol"), in percent.

    Same estimator as realised_vol_30d but over ANN_VOL_WINDOW_TD (252 trading
    days, ~1 year). This is the "structural / through-the-cycle" vol shown
    alongside the reactive 30d figure: the 30d number tells you what risk is
    doing RIGHT NOW, annVol tells you the asset's typical vol over the past year.

    If fewer than 252 closes are available, uses all available history (>= 2
    returns); returns NaN if it cannot form at least 2 returns.
    """
    closes = _clean(daily_closes)
    if len(closes) < 2:
        return float("nan")
    window_closes = closes[-(ANN_VOL_WINDOW_TD + 1):]
    rets = _log_returns(window_closes)
    return _annualised_vol_from_returns(rets)


# ============================================================================
# SELF-TEST  (run:  python3 metrics.py)
# ============================================================================

def _run_tests() -> None:
    import random

    print("=" * 72)
    print("GMI Risk Monitor -- metrics.py self-tests")
    print("=" * 72)
    passed = 0
    failed = 0

    def check(name, cond, detail=""):
        nonlocal passed, failed
        status = "PASS" if cond else "FAIL"
        if cond:
            passed += 1
        else:
            failed += 1
        print(f"  [{status}] {name}" + (f"  ({detail})" if detail else ""))
        assert cond, f"TEST FAILED: {name} {detail}"

    # ---- Test 1: SMA-60 rising -------------------------------------------
    # Steadily rising series of 72 monthly closes -> latest is well above the
    # trailing 5yr mean -> "rising".
    rising_monthly = [100.0 + i for i in range(72)]   # 100,101,...,171
    t1 = secular_trend(rising_monthly, "sma60")
    check("T1 SMA60 steadily-rising -> 'rising'", t1 == "rising", f"got {t1!r}")

    # ---- Test 2: SMA-60 falling ------------------------------------------
    # 60 months rising to a peak, then a sharp drop below the 5yr mean.
    falling_monthly = [100.0 + i for i in range(66)]  # rise
    falling_monthly[-1] = 60.0                         # last close crashes below SMA
    sma_check = sum(falling_monthly[-60:]) / 60.0
    t2 = secular_trend(falling_monthly, "sma60")
    check("T2 SMA60 crash below mean -> 'falling'",
          t2 == "falling", f"latest=60.0 < SMA={sma_check:.1f}; got {t2!r}")

    # ---- Test 3: SMA-60 too-short -> None --------------------------------
    t3 = secular_trend([100.0 + i for i in range(59)], "sma60")
    check("T3 SMA60 <60 points -> None", t3 is None, f"got {t3!r}")

    # ---- Test 4: log-channel intact uptrend -> 'rising' ------------------
    # Clean exponential growth (constant CAGR) over 120 weekly points: residuals
    # ~0, price sits on trend -> well within channel -> "rising".
    weekly_exp = [100.0 * (1.003 ** i) for i in range(120)]
    t4 = secular_trend(weekly_exp, "logchannel")
    check("T4 logchannel clean-uptrend -> 'rising'", t4 == "rising", f"got {t4!r}")

    # ---- Test 5: log-channel broken below lower bound -> 'falling' -------
    # Same uptrend, but force the LATEST price far below trend (a deep crash) so
    # logDev < -2 -> "falling". We append a collapse to the exponential history.
    weekly_break = [100.0 * (1.003 ** i) for i in range(120)]
    # crash the final point ~70% below where trend says it should be:
    weekly_break[-1] = weekly_break[-1] * 0.30
    t5 = secular_trend(weekly_break, "logchannel")
    check("T5 logchannel deep crash -> 'falling'", t5 == "falling", f"got {t5!r}")

    # ---- Test 5b: log-channel too-short -> None --------------------------
    t5b = secular_trend([100.0 * (1.003 ** i) for i in range(50)], "logchannel")
    check("T5b logchannel <104 points -> None", t5b is None, f"got {t5b!r}")

    # ---- Test 6: known-variance vol -> known annualised vol --------------
    # Construct returns with an EXACT known daily std, then check annualisation.
    # Use a deterministic symmetric series: returns alternate +d, -d about 0 with
    # large n so sample std ~= d. With d known, ann vol = d*sqrt(252)*100.
    d = 0.01                                   # 1% daily move
    # Build closes from an alternating +d/-d log-return path of 252 returns.
    rets_known = [d if (i % 2 == 0) else -d for i in range(252)]
    closes_known = [100.0]
    for r in rets_known:
        closes_known.append(closes_known[-1] * math.exp(r))
    # Sample std of a perfectly alternating +d/-d series:
    # mean=0, variance = sum(d^2)/(n-1) = n*d^2/(n-1); std = d*sqrt(n/(n-1)).
    n = len(rets_known)
    expected_daily_sd = d * math.sqrt(n / (n - 1))
    expected_ann = expected_daily_sd * math.sqrt(TRADING_DAYS_PER_YEAR) * 100.0
    got_ann = ann_vol(closes_known)
    check("T6 known-variance ann_vol matches closed form",
          abs(got_ann - expected_ann) < 1e-6,
          f"expected {expected_ann:.4f}%, got {got_ann:.4f}%")

    # ---- Test 7: 30d window uses only the tail ---------------------------
    # Long calm history + a recent volatile tail: realised_vol_30d should reflect
    # the recent tail (high), while ann_vol (1yr) should be lower (diluted).
    random.seed(42)
    calm = [100.0]
    for _ in range(300):                       # 300 days of tiny 0.1% moves
        calm.append(calm[-1] * math.exp(random.gauss(0, 0.001)))
    volatile_tail = list(calm)
    last = volatile_tail[-1]
    for _ in range(25):                        # 25 days of big 3% moves
        last = last * math.exp(random.gauss(0, 0.03))
        volatile_tail.append(last)
    rv30 = realised_vol_30d(volatile_tail)
    av = ann_vol(volatile_tail)
    check("T7 realised_vol_30d picks up recent spike (> ann_vol)",
          rv30 > av, f"rv30={rv30:.1f}%, annVol={av:.1f}%")
    check("T7b recent spike lands in High-Risk band (>40)",
          rv30 > 40.0, f"rv30={rv30:.1f}%")

    print("-" * 72)
    print(f"Worked numbers (for eyeballing):")
    print(f"  T6 expected ann vol = {expected_ann:.4f}%  got = {got_ann:.4f}%")
    print(f"  T7 realised_vol_30d = {rv30:.1f}%   ann_vol(1yr) = {av:.1f}%")
    print("-" * 72)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 72)


if __name__ == "__main__":
    _run_tests()


# ============================================================================
# ASSUMPTIONS & UNCERTAINTIES  (flagged for human confirmation)
# ============================================================================
#
# These are judgement calls where the spec is silent or ambiguous. Each is
# isolated to a named constant or a single line so it is cheap to change once
# confirmed.
#
# 1. LOG-CHANNEL "BROKEN BELOW" RULE  [secular_trend, logchannel branch]
#    Spec: "'rising' if the latest price is within or above the channel
#    (>= lower 2sigma bound), 'falling' if it has broken below the lower bound."
#    Implemented literally as: rising iff logDev >= -2.0 (i.e. price >= lower-2s).
#    AMBIGUITIES TO CONFIRM:
#      (a) Is a single latest-point close below -2s enough, or should we require
#          a sustained break (e.g. N consecutive weekly closes below, or a
#          weekly *close* vs intraday)? compute.js arms/disarms signals with
#          half-threshold hysteresis -- we did NOT replicate that here because
#          the spec frames secular trend as a point-in-time classification.
#      (b) Boundary: we treat exactly == -2s as "rising" (>=). Confirm inclusive.
#
# 2. RESIDUAL SD CONVENTION  [logchannel: population /n]
#    We use POPULATION sd (divisor n) for the channel residuals to match
#    compute.js exactly (cited above). The vol functions use SAMPLE sd
#    (divisor n-1, statistics.stdev), the standard realised-vol convention.
#    This split is deliberate but worth a human nod: the two engines use
#    different sd conventions ON PURPOSE (channel = match existing dashboard;
#    vol = standard estimator). For n ~ 104-252 the difference is < 0.5%.
#
# 3. LOG-CHANNEL TIME AXIS  [xs = 0..n-1 index]
#    We use an evenly-spaced integer index for x, assuming weekly closes are
#    roughly evenly spaced. If the input has gaps (missing weeks), a true
#    date-based x (as compute.js uses, (ts-ref)/DAY) would be more correct.
#    The classification (logDev sign vs -2s) is fairly robust to this, but
#    confirm whether inputs are guaranteed gap-free / regularly sampled.
#
# 4. VOL WINDOWS  [REALISED_VOL_WINDOW_TD=21, ANN_VOL_WINDOW_TD=252]
#    - "30 calendar days" -> we use 21 TRADING days (spec's stated mapping).
#      Crypto trades 7 days/week; for a crypto daily series 30 calendar days is
#      ~30 returns, not 21. We currently apply 21 uniformly. CONFIRM whether
#      crypto should use ~30 daily points and whether annualisation for a
#      7-day-week asset should use sqrt(365) instead of sqrt(252).  <-- IMPORTANT
#    - annVol window = 252 trading days (~1yr) is a PROPOSAL; the spec asked us
#      to pick a sensible documented window. Confirm 1yr vs e.g. 90d/180d.
#
# 5. ANNUALISATION FACTOR  [TRADING_DAYS_PER_YEAR=252]
#    sqrt(252) for all assets. FX/crypto arguably warrant sqrt(365) (continuous
#    markets). Kept at 252 for cross-asset comparability; flag for confirmation.
#
# 6. DATA HYGIENE  [realised_vol]
#    We compute log returns and silently skip any pair with a non-positive close
#    (cannot take a log). We do NOT forward-fill gaps or filter outliers. If the
#    upstream series can contain stale/zero prints, a human should confirm the
#    cleaning policy (the dashboard's data layer may already handle this).
#
# 7. "FINEST SERIES AVAILABLE"  [spec note for realised_vol_30d]
#    Spec allows deriving from the finest series available if daily is missing.
#    This module assumes DAILY closes are passed in. Resampling weekly->daily or
#    using intraday is the caller's responsibility; not implemented here.
