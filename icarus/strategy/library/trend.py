"""Price, trend and moving-average primitives — catalogue §2 (task 1.4a).

The oldest vocabulary in the document, and individually the most heavily mined: nobody has an edge
because they discovered the 50-day average. They are here because they are the connective tissue
almost every other school builds on — a liquidity sweep is *defined* relative to trend, a Weinstein
stage is defined by an average, and the SMC set in 1.4b will lean on these.

Two entries earn their place on the guard they force rather than on their signal value:

* ``psar`` is **stateful and forward-only** — its value on bar *t* depends on the running extreme
  since the trend began. It cannot be computed with a window function, which makes it a real test
  of our no-look-ahead discipline.
* ``ichimoku_chikou`` is displaced **backwards** by convention: the classic plot puts today's close
  26 bars in the past. Implemented literally that would hand bar *t* a value from bar *t+26*, which
  is the textbook look-ahead bug. Here it is defined as what it honestly is — the close from 26
  bars *ago* — and the docstring says so, because the naive version is what most libraries ship.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, FloatParam, IntParam, Kind, Primitive, SeriesParam
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]


# --------------------------------------------------------------------------------------
# Raw fields — the atoms every other word is a function of
# --------------------------------------------------------------------------------------


def _field(name: str) -> Primitive:
    def compute(bars: Bars, **_: object) -> Column:
        column: Column = getattr(bars, name)
        return column.astype(np.float64, copy=True)

    # None of the five is comparable between symbols: four are prices, and a share count is set by
    # how the company was capitalised rather than by how much interest it is seeing. The rupee
    # version of that question is `traded_value`, which is scale-free.
    return Primitive(
        name=name,
        kind=Kind.SERIES,
        summary=f"Raw {name} of each bar.",
        compute=compute,
        scale_free=False,
    )


def _constant(bars: Bars, *, value: float, **_: object) -> Column:
    """The same number on every bar — the missing half of every comparison (added in 1.4c).

    ``above`` and ``below`` take two *series*, because a comparison between two computed things is
    the composable form. But that left ``rsi(14) < 30`` — the single most common rule in technical
    trading — literally unsayable, and it went unnoticed through 1.4a and 1.4b because the words
    that read as complete sentences on their own (``sweep_and_reclaim_low``, ``in_discount``) hid
    the gap. Roughly sixty ``SERIES`` words in this library could not be used in a condition at all.

    Shipped as a word rather than by letting ``above``'s parameters accept a bare number, so that
    the rule "a series parameter is always a primitive" stays true with no exceptions — and so the
    threshold shows up in ``primitives_used()``, which is what the audit log records.
    """
    return np.full(bars.close.shape, float(value), dtype=np.float64)


def _typical(bars: Bars, **_: object) -> Column:
    return (bars.high + bars.low + bars.close) / 3.0


def _median_price(bars: Bars, **_: object) -> Column:
    return (bars.high + bars.low) / 2.0


def _ohlc4(bars: Bars, **_: object) -> Column:
    return (bars.open + bars.high + bars.low + bars.close) / 4.0


# --------------------------------------------------------------------------------------
# Moving averages
# --------------------------------------------------------------------------------------


def _sma(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.rolling_mean(bars.close, n)


def _ema(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.ema(bars.close, n)


def _wma(bars: Bars, *, n: int, **_: object) -> Column:
    weights = np.arange(1.0, n + 1.0)
    out = _ops.empty_like(bars.close)
    if n <= bars.close.size:
        windows = np.lib.stride_tricks.sliding_window_view(bars.close, n)
        out[n - 1 :] = windows @ weights / weights.sum()
    return out


def _hma(bars: Bars, *, n: int, **_: object) -> Column:
    """Hull: WMA of (2*WMA(n/2) - WMA(n)), smoothed over sqrt(n)."""
    half, root = max(2, n // 2), max(2, int(np.sqrt(n)))
    raw = 2.0 * _wma(bars, n=half) - _wma(bars, n=n)
    return _wma(Bars(bars.ts, bars.open, bars.high, bars.low, raw, bars.volume), n=root)


def _dema(bars: Bars, *, n: int, **_: object) -> Column:
    """Double EMA. First honest value at bar ``2n-2`` — the second pass needs ``n`` real inputs.

    The second EMA is fed the *first* EMA directly, warm-up ``nan``s and all, because
    :func:`_ops.ema` skips them. An earlier version filled those with ``close[0]`` so the second
    pass could start sooner; that fabricated four values outright at ``n=5`` and shifted four more,
    by feeding a *price* into a series of averages — two different quantities.
    """
    first = _ops.ema(bars.close, n)
    return 2.0 * first - _ops.ema(first, n)


def _tema(bars: Bars, *, n: int, **_: object) -> Column:
    """Triple EMA. First honest value at bar ``3n-3``.

    See :func:`_dema` for why the warm-up is passed through rather than filled.
    """
    e1 = _ops.ema(bars.close, n)
    e2 = _ops.ema(e1, n)
    e3 = _ops.ema(e2, n)
    return 3.0 * e1 - 3.0 * e2 + e3


def _efficiency_ratio(close: Column, n: int) -> Column:
    """Kaufman: net move ÷ summed absolute move. 1.0 = a straight line, ~0 = chop."""
    net = np.abs(close - _ops.shift(close, n))
    churn = _ops.rolling_sum(np.abs(np.diff(close, prepend=np.nan)), n)
    return _ops.safe_divide(net, churn)


def _er(bars: Bars, *, n: int, **_: object) -> Column:
    return _efficiency_ratio(bars.close, n)


def _kama(bars: Bars, *, n: int, fast: int, slow: int, **_: object) -> Column:
    """Adaptive MA: smoothing speed tracks the efficiency ratio, so it stalls in chop."""
    er = _efficiency_ratio(bars.close, n)
    fast_a, slow_a = 2.0 / (fast + 1.0), 2.0 / (slow + 1.0)
    alpha = (er * (fast_a - slow_a) + slow_a) ** 2
    out = _ops.empty_like(bars.close)
    start = n
    if start >= bars.close.size:
        return out
    value = float(np.mean(bars.close[:start]))
    out[start - 1] = value
    for i in range(start, bars.close.size):
        a = alpha[i]
        if np.isnan(a):
            out[i] = value
            continue
        value = value + a * (bars.close[i] - value)
        out[i] = value
    return out


# --------------------------------------------------------------------------------------
# Regression, rate of change, directional movement
# --------------------------------------------------------------------------------------


def _linreg(close: Column, n: int) -> tuple[Column, Column, Column]:
    """Slope, fitted end value and R² of a least-squares line over each trailing window."""
    slope, value, r2 = (_ops.empty_like(close) for _ in range(3))
    if n > close.size:
        return slope, value, r2
    x = np.arange(n, dtype=np.float64)
    x_centred = x - x.mean()
    denom = float((x_centred**2).sum())
    windows = np.lib.stride_tricks.sliding_window_view(close, n)
    y_mean = windows.mean(axis=1, keepdims=True)
    y_centred = windows - y_mean
    beta = (y_centred @ x_centred) / denom
    alpha = y_mean.ravel() - beta * x.mean()
    slope[n - 1 :] = beta
    value[n - 1 :] = alpha + beta * (n - 1)
    total = (y_centred**2).sum(axis=1)
    explained = beta**2 * denom
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(total > 0, explained / total, np.nan)
    r2[n - 1 :] = ratio
    return slope, value, r2


def _linreg_slope(bars: Bars, *, n: int, **_: object) -> Column:
    return _linreg(bars.close, n)[0]


def _linreg_value(bars: Bars, *, n: int, **_: object) -> Column:
    return _linreg(bars.close, n)[1]


def _r2(bars: Bars, *, n: int, **_: object) -> Column:
    return _linreg(bars.close, n)[2]


def _roc(bars: Bars, *, n: int, **_: object) -> Column:
    past = _ops.shift(bars.close, n)
    return _ops.safe_divide(bars.close - past, past) * 100.0


def _roc_skip(bars: Bars, *, n: int, skip: int, **_: object) -> Column:
    """Percent change from ``n`` bars ago to ``skip`` bars ago — the "12-1" momentum construction.

    Standard cross-sectional momentum measures the twelve-month return but *stops a month short*
    (Jegadeesh & Titman 1993; Asness, Moskowitz & Pedersen 2013). The skipped month is not a
    refinement, it is what makes the factor work: the most recent month carries short-horizon
    reversal, which points the opposite way and cancels much of the signal. Without this word the
    only expressible form was ``roc(252)``, so a weak result could not be told apart from a
    faithfully-implemented factor that simply does not pay on NSE (finding F22).
    """
    past = _ops.shift(bars.close, n)
    return _ops.safe_divide(_ops.shift(bars.close, skip) - past, past) * 100.0


def _momentum_abs(bars: Bars, *, n: int, **_: object) -> Column:
    """Change over ``n`` bars **in rupees**.

    Named for its units because the old name — ``momentum`` — did not have them, and three
    strategies ranked their universe with it believing they were ranking by strength. On this panel
    (median price ₹470, top 5% above ₹3,748) that is a standing bet on expensive shares. The word
    survives for within-symbol use, where rupees are the right unit; ``scale_free=False`` is what
    stops it reaching a cross-section again.
    """
    return bars.close - _ops.shift(bars.close, n)


def _directional(bars: Bars, n: int) -> tuple[Column, Column, Column]:
    """Wilder's +DI, -DI and ADX."""
    up_move = bars.high - _ops.shift(bars.high, 1)
    down_move = _ops.shift(bars.low, 1) - bars.low
    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)
    plus_dm[0] = minus_dm[0] = np.nan
    atr = _ops.wilder(_ops.true_range(bars.high, bars.low, bars.close), n)
    plus_di = 100.0 * _ops.safe_divide(_ops.wilder(plus_dm, n), atr)
    minus_di = 100.0 * _ops.safe_divide(_ops.wilder(minus_dm, n), atr)
    dx = 100.0 * _ops.safe_divide(np.abs(plus_di - minus_di), plus_di + minus_di)
    adx = _ops.wilder(dx, n)
    return plus_di, minus_di, adx


def _adx(bars: Bars, *, n: int, **_: object) -> Column:
    return _directional(bars, n)[2]


def _di_plus(bars: Bars, *, n: int, **_: object) -> Column:
    return _directional(bars, n)[0]


def _di_minus(bars: Bars, *, n: int, **_: object) -> Column:
    return _directional(bars, n)[1]


def _aroon_up(bars: Bars, *, n: int, **_: object) -> Column:
    return 100.0 * (n - _ops.rolling_argmax_age(bars.high, n)) / n


def _aroon_down(bars: Bars, *, n: int, **_: object) -> Column:
    return 100.0 * (n - _ops.rolling_argmin_age(bars.low, n)) / n


def _supertrend(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    """ATR-banded trailing trend line. Widely used in Indian retail algos specifically."""
    atr = _ops.wilder(_ops.true_range(bars.high, bars.low, bars.close), n)
    mid = (bars.high + bars.low) / 2.0
    upper, lower = mid + mult * atr, mid - mult * atr
    out = _ops.empty_like(bars.close)
    trend_up = True
    final_upper, final_lower = np.nan, np.nan
    for i in range(bars.close.size):
        if np.isnan(atr[i]):
            continue
        final_upper = (
            upper[i]
            if np.isnan(final_upper) or upper[i] < final_upper or bars.close[i - 1] > final_upper
            else final_upper
        )
        final_lower = (
            lower[i]
            if np.isnan(final_lower) or lower[i] > final_lower or bars.close[i - 1] < final_lower
            else final_lower
        )
        if trend_up and bars.close[i] < final_lower:
            trend_up = False
        elif not trend_up and bars.close[i] > final_upper:
            trend_up = True
        out[i] = final_lower if trend_up else final_upper
    return out


def _psar(bars: Bars, *, step: float, maximum: float, **_: object) -> Column:
    """Parabolic SAR — stateful, computed strictly forward. No window function can produce this."""
    out = _ops.empty_like(bars.close)
    if bars.close.size < 2:
        return out
    rising = bars.close[1] >= bars.close[0]
    sar = bars.low[0] if rising else bars.high[0]
    extreme = bars.high[0] if rising else bars.low[0]
    acceleration = step
    for i in range(1, bars.close.size):
        sar = sar + acceleration * (extreme - sar)
        if rising:
            sar = min(sar, bars.low[i - 1], bars.low[i])
            if bars.low[i] < sar:
                rising, sar, extreme, acceleration = False, extreme, bars.low[i], step
            elif bars.high[i] > extreme:
                extreme = bars.high[i]
                acceleration = min(acceleration + step, maximum)
        else:
            sar = max(sar, bars.high[i - 1], bars.high[i])
            if bars.high[i] > sar:
                rising, sar, extreme, acceleration = True, extreme, bars.high[i], step
            elif bars.low[i] < extreme:
                extreme = bars.low[i]
                acceleration = min(acceleration + step, maximum)
        out[i] = sar
    return out


def _ichimoku_line(high: Column, low: Column, n: int) -> Column:
    return (_ops.rolling_max(high, n) + _ops.rolling_min(low, n)) / 2.0


def _tenkan(bars: Bars, *, n: int, **_: object) -> Column:
    return _ichimoku_line(bars.high, bars.low, n)


def _kijun(bars: Bars, *, n: int, **_: object) -> Column:
    return _ichimoku_line(bars.high, bars.low, n)


def _chikou(bars: Bars, *, n: int, **_: object) -> Column:
    """The close from ``n`` bars ago.

    The conventional Ichimoku plot draws today's close displaced *backwards* n bars, and a literal
    implementation of that hands bar *t* the close from bar *t+n* — a future price. That is the
    single most common look-ahead bug in charting libraries. What is honestly knowable at bar *t*
    is the close from *n* bars ago, which is what this returns.
    """
    return _ops.shift(bars.close, n)


# --------------------------------------------------------------------------------------
# Events
# --------------------------------------------------------------------------------------


def _cross_above(bars: Bars, *, a: Column, b: Column, **_: object) -> Column:
    return _ops.crossed_above(a, b)


def _cross_below(bars: Bars, *, a: Column, b: Column, **_: object) -> Column:
    return _ops.crossed_below(a, b)


def _above(bars: Bars, *, a: Column, b: Column, **_: object) -> Column:
    return _ops.boolean(a > b, np.isnan(a) | np.isnan(b))


def _below(bars: Bars, *, a: Column, b: Column, **_: object) -> Column:
    return _ops.boolean(a < b, np.isnan(a) | np.isnan(b))


def _rising(bars: Bars, *, series: Column, n: int, **_: object) -> Column:
    past = _ops.shift(series, n)
    return _ops.boolean(series > past, np.isnan(series) | np.isnan(past))


def _falling(bars: Bars, *, series: Column, n: int, **_: object) -> Column:
    past = _ops.shift(series, n)
    return _ops.boolean(series < past, np.isnan(series) | np.isnan(past))


def _slope_positive(bars: Bars, *, n: int, **_: object) -> Column:
    slope = _linreg(bars.close, n)[0]
    return _ops.boolean(slope > 0, np.isnan(slope))


_SERIES_PAIR = (SeriesParam("a"), SeriesParam("b"))


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §2. Pure — the registry is assembled by the caller, never by import side effect."""
    return (
        *(_field(f) for f in ("open", "high", "low", "close", "volume")),
        Primitive("typical_price", Kind.SERIES, "(H+L+C)/3.", _typical, scale_free=False),
        Primitive("median_price", Kind.SERIES, "(H+L)/2.", _median_price, scale_free=False),
        Primitive("ohlc4", Kind.SERIES, "(O+H+L+C)/4.", _ohlc4, scale_free=False),
        Primitive(
            "constant",
            Kind.SERIES,
            "A fixed number on every bar — the threshold side of a comparison.",
            _constant,
            (FloatParam("value", -1e9, 1e9),),
            # Its units are whatever it is compared against, which is usually a price. Refusing it
            # in a cross-section is right for a second reason anyway: the same number for every
            # symbol is not an ordering.
            scale_free=False,
        ),
        Primitive(
            "sma",
            Kind.SERIES,
            "Simple moving average of close.",
            _sma,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "ema",
            Kind.SERIES,
            "SMA-seeded exponential MA of close.",
            _ema,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "wma",
            Kind.SERIES,
            "Linearly weighted MA of close.",
            _wma,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "hma",
            Kind.SERIES,
            "Hull MA — WMA arithmetic, lower lag.",
            _hma,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "dema",
            Kind.SERIES,
            "Double exponential MA.",
            _dema,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "tema",
            Kind.SERIES,
            "Triple exponential MA.",
            _tema,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "kama",
            Kind.SERIES,
            "Kaufman adaptive MA — speed tracks the efficiency ratio.",
            _kama,
            (
                _ops.period_param(),
                IntParam("fast", 2, 100, default=2),
                IntParam("slow", 2, 500, default=30),
            ),
            scale_free=False,
            requires_lt=(("fast", "slow"),),
        ),
        Primitive(
            "efficiency_ratio",
            Kind.SERIES,
            "Net move / summed absolute move. Cheap trend-vs-chop measure.",
            _er,
            (_ops.period_param(),),
            scale_free=True,
        ),
        Primitive(
            "linreg_slope",
            Kind.SERIES,
            "Least-squares slope over n bars.",
            _linreg_slope,
            (_ops.period_param(),),
            # Rupees per bar. The scale-free cousin is r2, which measures how *cleanly* the window
            # trends without caring how large the move was in currency.
            scale_free=False,
        ),
        Primitive(
            "linreg_value",
            Kind.SERIES,
            "Fitted regression value at the last bar.",
            _linreg_value,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "r2",
            Kind.SERIES,
            "Regression R² — how trend-like the window is.",
            _r2,
            (_ops.period_param(),),
            scale_free=True,
        ),
        Primitive(
            "roc",
            Kind.SERIES,
            "Percent change over n bars.",
            _roc,
            (_ops.period_param(),),
            scale_free=True,
        ),
        Primitive(
            "roc_skip",
            Kind.SERIES,
            "Percent change from n bars ago to skip bars ago — 12-1 momentum.",
            _roc_skip,
            (_ops.period_param(), IntParam("skip", 1, _ops.MAX_PERIOD, default=21)),
            requires_lt=(("skip", "n"),),
            scale_free=True,
        ),
        Primitive(
            "momentum_abs",
            Kind.SERIES,
            "Change over n bars in RUPEES. Not comparable across symbols — see roc.",
            _momentum_abs,
            (_ops.period_param(),),
            scale_free=False,
        ),
        Primitive(
            "adx",
            Kind.SERIES,
            "Wilder ADX — trend strength, direction-agnostic.",
            _adx,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "di_plus",
            Kind.SERIES,
            "Wilder +DI.",
            _di_plus,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "di_minus",
            Kind.SERIES,
            "Wilder -DI.",
            _di_minus,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "aroon_up",
            Kind.SERIES,
            "0-100: recency of the n-bar high.",
            _aroon_up,
            (_ops.period_param(default=25),),
            scale_free=True,
        ),
        Primitive(
            "aroon_down",
            Kind.SERIES,
            "0-100: recency of the n-bar low.",
            _aroon_down,
            (_ops.period_param(default=25),),
            scale_free=True,
        ),
        Primitive(
            "supertrend",
            Kind.LEVEL,
            "ATR-banded trailing trend line.",
            _supertrend,
            (_ops.period_param(default=10), FloatParam("mult", 0.1, 20.0, default=3.0)),
        ),
        Primitive(
            "psar",
            Kind.LEVEL,
            "Parabolic SAR — stateful, forward-only. No lead-in reproduces it.",
            _psar,
            (
                FloatParam("step", 0.001, 0.5, default=0.02),
                FloatParam("maximum", 0.01, 1.0, default=0.2),
            ),
            # Doubly unreachable by the lead-in heuristic. Its acceleration factor is carried
            # forward through an entire trend, so the state at any bar depends on where the last
            # reversal was — a distance nothing bounds; and both its parameters are decimals, so
            # the largest-integer rule sees no number at all and would grant it a lead-in of zero.
            # Measured: it does not drift steadily toward the right answer, it oscillates —
            # matching full history at 300 sessions of lead-in, missing at 700, matching again at
            # 900. So no lead-in can be named and defended.
            opaque_lookback=True,
        ),
        Primitive(
            "ichimoku_tenkan",
            Kind.LEVEL,
            "Conversion line.",
            _tenkan,
            (_ops.period_param(default=9),),
        ),
        Primitive(
            "ichimoku_kijun", Kind.LEVEL, "Base line.", _kijun, (_ops.period_param(default=26),)
        ),
        Primitive(
            "ichimoku_chikou",
            Kind.SERIES,
            "Close from n bars ago (NOT the future-displaced plot).",
            _chikou,
            (_ops.period_param(default=26),),
            scale_free=False,
        ),
        Primitive(
            "cross_above", Kind.EVENT, "a crosses strictly above b.", _cross_above, _SERIES_PAIR
        ),
        Primitive(
            "cross_below", Kind.EVENT, "a crosses strictly below b.", _cross_below, _SERIES_PAIR
        ),
        Primitive("above", Kind.EVENT, "a is above b on this bar.", _above, _SERIES_PAIR),
        Primitive("below", Kind.EVENT, "a is below b on this bar.", _below, _SERIES_PAIR),
        Primitive(
            "rising",
            Kind.EVENT,
            "series is higher than n bars ago.",
            _rising,
            (SeriesParam("series"), _ops.period_param()),
        ),
        Primitive(
            "falling",
            Kind.EVENT,
            "series is lower than n bars ago.",
            _falling,
            (SeriesParam("series"), _ops.period_param()),
        ),
        Primitive(
            "slope_positive",
            Kind.EVENT,
            "Regression slope over n bars is positive.",
            _slope_positive,
            (_ops.period_param(),),
        ),
    )
