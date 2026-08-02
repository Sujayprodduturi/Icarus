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

_MAX_PERIOD = 1000


def _period(name: str = "n", default: int | None = None) -> IntParam:
    """A lookback. Minimum 2 — a one-bar average is the series itself, and usually a typo."""
    return IntParam(name, 2, _MAX_PERIOD, default=default)


# --------------------------------------------------------------------------------------
# Raw fields — the atoms every other word is a function of
# --------------------------------------------------------------------------------------


def _field(name: str) -> Primitive:
    def compute(bars: Bars, **_: object) -> Column:
        column: Column = getattr(bars, name)
        return column.astype(np.float64, copy=True)

    return Primitive(
        name=name, kind=Kind.SERIES, summary=f"Raw {name} of each bar.", compute=compute
    )


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
    first = _ops.ema(bars.close, n)
    return 2.0 * first - _ops.ema(np.nan_to_num(first, nan=bars.close[0]), n)


def _tema(bars: Bars, *, n: int, **_: object) -> Column:
    e1 = _ops.ema(bars.close, n)
    e2 = _ops.ema(np.nan_to_num(e1, nan=bars.close[0]), n)
    e3 = _ops.ema(np.nan_to_num(e2, nan=bars.close[0]), n)
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


def _momentum(bars: Bars, *, n: int, **_: object) -> Column:
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
        Primitive("typical_price", Kind.SERIES, "(H+L+C)/3.", _typical),
        Primitive("median_price", Kind.SERIES, "(H+L)/2.", _median_price),
        Primitive("ohlc4", Kind.SERIES, "(O+H+L+C)/4.", _ohlc4),
        Primitive("sma", Kind.SERIES, "Simple moving average of close.", _sma, (_period(),)),
        Primitive("ema", Kind.SERIES, "SMA-seeded exponential MA of close.", _ema, (_period(),)),
        Primitive("wma", Kind.SERIES, "Linearly weighted MA of close.", _wma, (_period(),)),
        Primitive("hma", Kind.SERIES, "Hull MA — WMA arithmetic, lower lag.", _hma, (_period(),)),
        Primitive("dema", Kind.SERIES, "Double exponential MA.", _dema, (_period(),)),
        Primitive("tema", Kind.SERIES, "Triple exponential MA.", _tema, (_period(),)),
        Primitive(
            "kama",
            Kind.SERIES,
            "Kaufman adaptive MA — speed tracks the efficiency ratio.",
            _kama,
            (_period(), IntParam("fast", 2, 100, default=2), IntParam("slow", 2, 500, default=30)),
        ),
        Primitive(
            "efficiency_ratio",
            Kind.SERIES,
            "Net move / summed absolute move. Cheap trend-vs-chop measure.",
            _er,
            (_period(),),
        ),
        Primitive(
            "linreg_slope",
            Kind.SERIES,
            "Least-squares slope over n bars.",
            _linreg_slope,
            (_period(),),
        ),
        Primitive(
            "linreg_value",
            Kind.SERIES,
            "Fitted regression value at the last bar.",
            _linreg_value,
            (_period(),),
        ),
        Primitive(
            "r2", Kind.SERIES, "Regression R² — how trend-like the window is.", _r2, (_period(),)
        ),
        Primitive("roc", Kind.SERIES, "Percent change over n bars.", _roc, (_period(),)),
        Primitive("momentum", Kind.SERIES, "Absolute change over n bars.", _momentum, (_period(),)),
        Primitive(
            "adx",
            Kind.SERIES,
            "Wilder ADX — trend strength, direction-agnostic.",
            _adx,
            (_period(default=14),),
        ),
        Primitive("di_plus", Kind.SERIES, "Wilder +DI.", _di_plus, (_period(default=14),)),
        Primitive("di_minus", Kind.SERIES, "Wilder -DI.", _di_minus, (_period(default=14),)),
        Primitive(
            "aroon_up",
            Kind.SERIES,
            "0-100: recency of the n-bar high.",
            _aroon_up,
            (_period(default=25),),
        ),
        Primitive(
            "aroon_down",
            Kind.SERIES,
            "0-100: recency of the n-bar low.",
            _aroon_down,
            (_period(default=25),),
        ),
        Primitive(
            "supertrend",
            Kind.LEVEL,
            "ATR-banded trailing trend line.",
            _supertrend,
            (_period(default=10), FloatParam("mult", 0.1, 20.0, default=3.0)),
        ),
        Primitive(
            "psar",
            Kind.LEVEL,
            "Parabolic SAR — stateful, forward-only.",
            _psar,
            (
                FloatParam("step", 0.001, 0.5, default=0.02),
                FloatParam("maximum", 0.01, 1.0, default=0.2),
            ),
        ),
        Primitive(
            "ichimoku_tenkan", Kind.LEVEL, "Conversion line.", _tenkan, (_period(default=9),)
        ),
        Primitive("ichimoku_kijun", Kind.LEVEL, "Base line.", _kijun, (_period(default=26),)),
        Primitive(
            "ichimoku_chikou",
            Kind.SERIES,
            "Close from n bars ago (NOT the future-displaced plot).",
            _chikou,
            (_period(default=26),),
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
            (SeriesParam("series"), _period()),
        ),
        Primitive(
            "falling",
            Kind.EVENT,
            "series is lower than n bars ago.",
            _falling,
            (SeriesParam("series"), _period()),
        ),
        Primitive(
            "slope_positive",
            Kind.EVENT,
            "Regression slope over n bars is positive.",
            _slope_positive,
            (_period(),),
        ),
    )
