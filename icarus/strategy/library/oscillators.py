"""Oscillators and mean-reversion primitives — catalogue §4 (task 1.4a).

``rsi`` uses **Wilder's smoothing, not a simple average of gains and losses.** The two are widely
confused and produce materially different numbers — a strategy tuned on one and executed on the
other is trading a different rule than the one that was validated. The hand-computed fixture in
``tests/unit/test_dsl_library.py`` pins Wilder's specifically.

``zscore`` and ``percentile_rank`` are the two general mean-reversion atoms: both take *any* series
as their input, so "RSI is unusually low for this symbol" and "volume is unusually high" are the
same word applied to different arguments rather than two more entries in the vocabulary. That
composability is why :class:`~icarus.strategy.dsl.SeriesParam` exists.

``rsi_divergence`` is **deliberately absent.** It is only definable on *confirmed* swing points,
and a swing is not knowable until k bars after it forms — implementing it before the confirmation
machinery in 1.4b exists would produce the exact look-ahead bug that section is written to prevent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, IntParam, Kind, Primitive, SeriesParam
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]

_RSI_MAX = 100.0


def _rsi_values(close: Column, n: int) -> Column:
    change = np.diff(close, prepend=np.nan)
    gain = np.where(change > 0, change, 0.0)
    loss = np.where(change < 0, -change, 0.0)
    gain[0] = loss[0] = np.nan
    avg_gain = _ops.wilder(gain, n)
    avg_loss = _ops.wilder(loss, n)
    # A window with no losses is RSI 100 by definition, not a division error.
    rs = _ops.safe_divide(avg_gain, avg_loss)
    out = _RSI_MAX - (_RSI_MAX / (1.0 + rs))
    return np.where((avg_loss == 0) & ~np.isnan(avg_gain), _RSI_MAX, out)


def _rsi(bars: Bars, *, n: int, **_: object) -> Column:
    return _rsi_values(bars.close, n)


def _stoch_raw(bars: Bars, n: int) -> Column:
    low = _ops.rolling_min(bars.low, n)
    high = _ops.rolling_max(bars.high, n)
    return 100.0 * _ops.safe_divide(bars.close - low, high - low)


def _stoch_k(bars: Bars, *, n: int, smooth: int, **_: object) -> Column:
    return _ops.rolling_mean(_stoch_raw(bars, n), smooth)


def _stoch_d(bars: Bars, *, n: int, smooth: int, signal: int, **_: object) -> Column:
    return _ops.rolling_mean(_stoch_k(bars, n=n, smooth=smooth), signal)


def _stoch_rsi(bars: Bars, *, n: int, **_: object) -> Column:
    rsi = _rsi_values(bars.close, n)
    low, high = _ops.rolling_min(rsi, n), _ops.rolling_max(rsi, n)
    return _ops.safe_divide(rsi - low, high - low)


def _williams_r(bars: Bars, *, n: int, **_: object) -> Column:
    high, low = _ops.rolling_max(bars.high, n), _ops.rolling_min(bars.low, n)
    return -100.0 * _ops.safe_divide(high - bars.close, high - low)


def _cci(bars: Bars, *, n: int, **_: object) -> Column:
    typical = (bars.high + bars.low + bars.close) / 3.0
    mean = _ops.rolling_mean(typical, n)
    deviation = _ops.empty_like(typical)
    if n <= typical.size:
        windows = np.lib.stride_tricks.sliding_window_view(typical, n)
        deviation[n - 1 :] = np.abs(windows - windows.mean(axis=1, keepdims=True)).mean(axis=1)
    return _ops.safe_divide(typical - mean, 0.015 * deviation)


def _macd_values(close: Column, fast: int, slow: int, signal: int) -> tuple[Column, Column]:
    line = _ops.ema(close, fast) - _ops.ema(close, slow)
    return line, _ops.ema(line, signal)


def _macd(bars: Bars, *, fast: int, slow: int, signal: int, **_: object) -> Column:
    return _macd_values(bars.close, fast, slow, signal)[0]


def _macd_signal(bars: Bars, *, fast: int, slow: int, signal: int, **_: object) -> Column:
    return _macd_values(bars.close, fast, slow, signal)[1]


def _macd_hist(bars: Bars, *, fast: int, slow: int, signal: int, **_: object) -> Column:
    line, sig = _macd_values(bars.close, fast, slow, signal)
    return line - sig


def _ppo(bars: Bars, *, fast: int, slow: int, **_: object) -> Column:
    """MACD in percent — unlike MACD itself, comparable across symbols at different price levels."""
    slow_ema = _ops.ema(bars.close, slow)
    return 100.0 * _ops.safe_divide(_ops.ema(bars.close, fast) - slow_ema, slow_ema)


def _zscore(bars: Bars, *, series: Column, n: int, **_: object) -> Column:
    mean = _ops.rolling_mean(series, n)
    std = _ops.rolling_std(series, n, ddof=1)
    return np.where(np.isnan(series), np.nan, _ops.safe_divide(series - mean, std))


def _percentile_rank(bars: Bars, *, series: Column, n: int, **_: object) -> Column:
    """Non-parametric alternative to the z-score — no normality assumption."""
    filled = series
    out = _ops.empty_like(filled)
    if n <= filled.size:
        windows = np.lib.stride_tricks.sliding_window_view(filled, n)
        current = filled[n - 1 :]
        out[n - 1 :] = (windows <= current[:, None]).sum(axis=1) / n
    return np.where(np.isnan(series), np.nan, out)


def _distance_from_ma(bars: Bars, *, n: int, atr_period: int, **_: object) -> Column:
    """Extension from the mean measured in ATRs, so it means the same thing on any symbol."""
    atr = _ops.wilder(_ops.true_range(bars.high, bars.low, bars.close), atr_period)
    return _ops.safe_divide(bars.close - _ops.rolling_mean(bars.close, n), atr)


def _streak(close: Column, *, up: bool) -> Column:
    change = np.diff(close, prepend=np.nan)
    hit = (change > 0) if up else (change < 0)
    out = _ops.empty_like(close)
    run = 0
    for i in range(1, close.size):
        run = run + 1 if hit[i] else 0
        out[i] = run
    return out


def _up_streak(bars: Bars, **_: object) -> Column:
    return _streak(bars.close, up=True)


def _down_streak(bars: Bars, **_: object) -> Column:
    return _streak(bars.close, up=False)


def _connors_rsi(bars: Bars, *, n: int, streak_n: int, rank_n: int, **_: object) -> Column:
    """Average of price RSI, streak RSI and the percent-rank of the one-bar return."""
    price_rsi = _rsi_values(bars.close, n)
    signed = _up_streak(bars) - _down_streak(bars)
    streak_rsi = _rsi_values(signed, streak_n)
    returns = _ops.safe_divide(np.diff(bars.close, prepend=np.nan), _ops.shift(bars.close, 1))
    rank = _percentile_rank(bars, series=returns, n=rank_n) * 100.0
    return (price_rsi + streak_rsi + rank) / 3.0


def _ibs(bars: Bars, **_: object) -> Column:
    """(C-L)/(H-L). Tiny, cheap, and a well-documented short-horizon reversion signal."""
    return _ops.safe_divide(bars.close - bars.low, bars.high - bars.low)


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §4."""
    return (
        Primitive(
            "rsi",
            Kind.SERIES,
            "Wilder-smoothed RSI.",
            _rsi,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "stoch_k",
            Kind.SERIES,
            "Stochastic %K.",
            _stoch_k,
            (_ops.period_param(default=14), IntParam("smooth", 1, 100, default=3)),
            scale_free=True,
        ),
        Primitive(
            "stoch_d",
            Kind.SERIES,
            "Stochastic %D — signal line of %K.",
            _stoch_d,
            (
                _ops.period_param(default=14),
                IntParam("smooth", 1, 100, default=3),
                IntParam("signal", 1, 100, default=3),
            ),
            scale_free=True,
        ),
        Primitive(
            "stoch_rsi",
            Kind.SERIES,
            "Stochastic applied to RSI.",
            _stoch_rsi,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "williams_r",
            Kind.SERIES,
            "Williams %R.",
            _williams_r,
            (_ops.period_param(default=14),),
            scale_free=True,
        ),
        Primitive(
            "cci",
            Kind.SERIES,
            "Commodity Channel Index.",
            _cci,
            (_ops.period_param(default=20),),
            scale_free=True,
        ),
        Primitive(
            "macd",
            Kind.SERIES,
            "MACD line (fast EMA - slow EMA).",
            _macd,
            (
                IntParam("fast", 2, 200, default=12),
                IntParam("slow", 2, 500, default=26),
                IntParam("signal", 1, 200, default=9),
            ),
            scale_free=False,
        ),
        Primitive(
            "macd_signal",
            Kind.SERIES,
            "MACD signal line.",
            _macd_signal,
            (
                IntParam("fast", 2, 200, default=12),
                IntParam("slow", 2, 500, default=26),
                IntParam("signal", 1, 200, default=9),
            ),
            scale_free=False,
        ),
        Primitive(
            "macd_hist",
            Kind.SERIES,
            "MACD histogram (line - signal).",
            _macd_hist,
            (
                IntParam("fast", 2, 200, default=12),
                IntParam("slow", 2, 500, default=26),
                IntParam("signal", 1, 200, default=9),
            ),
            scale_free=False,
        ),
        Primitive(
            "ppo",
            Kind.SERIES,
            "MACD in percent — cross-symbol comparable.",
            _ppo,
            (IntParam("fast", 2, 200, default=12), IntParam("slow", 2, 500, default=26)),
            scale_free=True,
        ),
        Primitive(
            "zscore",
            Kind.SERIES,
            "(x - rolling mean) / rolling stdev of any series.",
            _zscore,
            (SeriesParam("series"), _ops.period_param(default=20)),
            scale_free=True,
        ),
        Primitive(
            "percentile_rank",
            Kind.SERIES,
            "Rank of any series within its own trailing window.",
            _percentile_rank,
            (SeriesParam("series"), _ops.period_param(default=100)),
            scale_free=True,
        ),
        Primitive(
            "distance_from_ma",
            Kind.SERIES,
            "(close - SMA) / ATR — ATR-normalised extension.",
            _distance_from_ma,
            (_ops.period_param(default=20), IntParam("atr_period", 2, 200, default=14)),
            scale_free=True,
        ),
        Primitive(
            "up_streak",
            Kind.SERIES,
            "Consecutive higher closes.",
            _up_streak,
            scale_free=True,
        ),
        Primitive(
            "down_streak",
            Kind.SERIES,
            "Consecutive lower closes.",
            _down_streak,
            scale_free=True,
        ),
        Primitive(
            "connors_rsi",
            Kind.SERIES,
            "Composite short-term mean-reversion oscillator.",
            _connors_rsi,
            (
                _ops.period_param(default=3),
                IntParam("streak_n", 2, 100, default=2),
                IntParam("rank_n", 2, 500, default=100),
            ),
            scale_free=True,
        ),
        Primitive(
            "internal_bar_strength",
            Kind.SERIES,
            "(C-L)/(H-L).",
            _ibs,
            scale_free=True,
        ),
    )
