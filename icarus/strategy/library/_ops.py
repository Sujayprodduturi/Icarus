"""Rolling-window arithmetic shared by every primitive library (task 1.4a).

**Every function here returns an array the same length as its input, with ``nan`` for bars where
the value is not yet knowable.** That convention is the whole point. A 50-bar average has no
honest value on bar 3, and the two tempting alternatives are both look-ahead bugs wearing a
disguise: returning a shorter array silently re-indexes the series so bar 0 of the result is bar 49
of the input, and back-filling the warm-up invents values from data that had not happened yet.

Smoothing seeds are documented rather than incidental. Wilder's smoothing (RSI, ATR, ADX) and the
EMA family are both **SMA-seeded**: the first output at index ``n-1`` is the simple average of the
first ``n`` inputs, and the recursion runs from there. Seeding from the first value instead is also
"correct" and produces materially different early bars, which is exactly why it has to be a stated
choice — two implementations that disagree on bar 30 will disagree on the backtest.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from icarus.strategy.dsl import IntParam

if TYPE_CHECKING:
    import numpy.typing as npt

Column = "npt.NDArray[np.float64]"


# The one lookback declaration. Six modules had grown a byte-identical private copy of this by
# 1.4c, each with its own `_MAX_PERIOD = 1000` — six places for one number to drift. Minimum 2
# because a one-bar average is the series itself, and is nearly always a typo.
MAX_PERIOD = 1000


def period_param(name: str = "n", default: int | None = None) -> IntParam:
    """A lookback in bars, in ``[2, MAX_PERIOD]``."""
    return IntParam(name, 2, MAX_PERIOD, default=default)


def empty_like(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """An all-``nan`` column shaped like ``a`` — the starting point for every windowed result."""
    return np.full(a.shape, np.nan, dtype=np.float64)


def _windows(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    return sliding_window_view(a, n)


def rolling_mean(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = _windows(a, n).mean(axis=1)
    return out


def rolling_std(a: npt.NDArray[np.float64], n: int, *, ddof: int = 0) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size and n > ddof:
        out[n - 1 :] = _windows(a, n).std(axis=1, ddof=ddof)
    return out


def rolling_sum(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = _windows(a, n).sum(axis=1)
    return out


def rolling_max(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = _windows(a, n).max(axis=1)
    return out


def rolling_min(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = _windows(a, n).min(axis=1)
    return out


def rolling_argmax_age(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    """Bars since the highest value in the trailing ``n``-bar window (0 = the current bar)."""
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = n - 1 - _windows(a, n).argmax(axis=1)
    return out


def rolling_argmin_age(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    out = empty_like(a)
    if n <= a.size:
        out[n - 1 :] = n - 1 - _windows(a, n).argmin(axis=1)
    return out


def shift(a: npt.NDArray[np.float64], k: int) -> npt.NDArray[np.float64]:
    """Move the series ``k`` bars into the future (``k > 0`` looks *back*), padding with ``nan``.

    Only positive ``k`` is allowed. A negative shift would place a future bar's value on today,
    which is the definition of look-ahead (PRD §30.2) — the one displaced primitive that genuinely
    needs it (Ichimoku's chikou span) is handled explicitly at its own call site, with a comment.
    """
    if k < 0:
        raise ValueError(f"shift() looks backwards only; got k={k} (PRD §30.2)")
    out = empty_like(a)
    if k == 0:
        return a.astype(np.float64, copy=True)
    if k < a.size:
        out[k:] = a[:-k]
    return out


def ema(
    a: npt.NDArray[np.float64], n: int, *, alpha: float | None = None
) -> npt.NDArray[np.float64]:
    """SMA-seeded exponential moving average. ``alpha`` defaults to ``2/(n+1)``.

    Pass ``alpha=1/n`` for Wilder's smoothing — the two differ materially, and the RSI/ATR/ADX
    family specifically requires Wilder's rather than the ordinary EMA.

    **Leading ``nan`` values are skipped, never filled.** Almost every input here starts with one:
    a true range or a price change has no value on bar 0. The tempting shortcut is to back-fill it
    with the next value so the seed window is "full" — but that invents an observation, and it
    quietly shifts the seed one bar early *and* double-counts the first real reading. Against
    Wilder's own worked RSI example that error moves the first value by ~3.5 points, which is the
    difference between an overbought signal firing and not firing. So the seed is taken from the
    first ``n`` *consecutive real* observations, and a gap resets the recursion rather than
    smoothing across it.
    """
    out = empty_like(a)
    weight = 2.0 / (n + 1.0) if alpha is None else alpha
    value: float | None = None
    run = 0
    for i in range(a.size):
        if np.isnan(a[i]):
            value, run = None, 0
            continue
        run += 1
        if value is None:
            if run < n:
                continue
            value = float(np.mean(a[i - n + 1 : i + 1]))
        else:
            value = weight * float(a[i]) + (1.0 - weight) * value
        out[i] = value
    return out


def wilder(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    """Wilder's smoothing — an EMA with ``alpha = 1/n``. Used by RSI, ATR, ADX."""
    return ema(a, n, alpha=1.0 / n)


def true_range(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
) -> npt.NDArray[np.float64]:
    """``max(H-L, |H-C_prev|, |L-C_prev|)`` — gap-aware, unlike a bare high-minus-low.

    Bar 0 has no previous close, so it is ``nan`` rather than being filled with ``H-L``. Filling it
    would make the first ATR of every backtest quietly different from every subsequent one.
    """
    prev = shift(close, 1)
    out = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    out[0] = np.nan
    return out


def atr(
    high: npt.NDArray[np.float64],
    low: npt.NDArray[np.float64],
    close: npt.NDArray[np.float64],
    n: int,
) -> npt.NDArray[np.float64]:
    """Wilder-smoothed true range. Lives here rather than in ``volatility`` because half the
    structure and zone vocabulary measures distances in ATR, and two implementations of the unit
    of risk would eventually disagree about what "1 ATR" means."""
    return wilder(true_range(high, low, close), n)


def forward_fill(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Carry each value forward until the next one arrives. **Leading ``nan`` stays ``nan``.**

    This looks like the back-fill bug the module docstring warns about, and it is its exact
    opposite. Back-filling puts a *later* value on an *earlier* bar — the value was not knowable
    then. Forward-filling puts an *earlier* value on a *later* bar, which is simply what "the last
    confirmed swing low is still 412.30" means: it was knowable when it was set and nothing has
    replaced it. Before the first value exists there is nothing honest to carry, so the leading
    stretch is left ``nan``.
    """
    out = a.astype(np.float64, copy=True)
    if out.size == 0:
        return out
    known = ~np.isnan(out)
    idx = np.where(known, np.arange(out.size), 0)
    np.maximum.accumulate(idx, out=idx)
    return np.where(known[idx], out[idx], np.nan)


def rolling_cov(
    a: npt.NDArray[np.float64], b: npt.NDArray[np.float64], n: int
) -> npt.NDArray[np.float64]:
    """Sample covariance (``ddof=1``) over a trailing ``n``-bar window.

    A bar where *either* series is unknown makes the whole window unknown, rather than being
    skipped. Skipping would quietly compute a 60-bar beta from 43 observations and report it as a
    60-bar beta.
    """
    out = empty_like(a)
    if n > a.size or n < 2:
        return out
    wa, wb = _windows(a, n), _windows(b, n)
    centred_a = wa - wa.mean(axis=1, keepdims=True)
    centred_b = wb - wb.mean(axis=1, keepdims=True)
    out[n - 1 :] = (centred_a * centred_b).sum(axis=1) / (n - 1)
    return out


def rolling_corr(
    a: npt.NDArray[np.float64], b: npt.NDArray[np.float64], n: int
) -> npt.NDArray[np.float64]:
    """Pearson correlation over a trailing ``n``-bar window, ``nan`` where either series is flat."""
    return safe_divide(
        rolling_cov(a, b, n), sqrt(rolling_cov(a, a, n)) * sqrt(rolling_cov(b, b, n))
    )


def relative_to_average(a: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    """Today's value against its own trailing ``n``-bar mean, **excluding today**.

    Excluding today is the whole point: a genuine spike included in its own baseline inflates the
    number it is being measured against, so the bigger the spike the more it hides itself. Shared
    rather than spelled out at each call site because three words here compare something to its own
    average (relative volume, Wyckoff's effort-vs-result, Livermore's volume confirmation) and two
    of them disagreeing about whether today counts would make a "volume spike" mean two things.
    """
    return safe_divide(a, shift(rolling_mean(a, n), 1))


def bars_since(flag: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """Bars since ``flag`` was last true (0 on the bar itself), ``nan`` before it ever was."""
    positions = np.arange(flag.size)
    last = np.where(flag, positions, -1)
    np.maximum.accumulate(last, out=last)
    return np.where(last >= 0, (positions - last).astype(np.float64), np.nan)


def previous_value(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """For a sparse column, put the *previous* non-``nan`` value where each value sits.

    Used to compare a just-confirmed swing with the one before it without hunting backwards through
    a mostly-empty array at every bar.
    """
    out = empty_like(a)
    at = np.flatnonzero(~np.isnan(a))
    if at.size > 1:
        out[at[1:]] = a[at[:-1]]
    return out


def previous_bar(mask: npt.NDArray[np.bool_]) -> npt.NDArray[np.bool_]:
    """``mask`` shifted one bar forward — "this was true on the previous bar".

    Bar 0 is ``False``: nothing preceded it.
    """
    out = np.zeros_like(mask)
    out[1:] = mask[:-1]
    return out


def crossed_above(
    a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Strict crossing: ``a`` was at-or-below ``b`` and is now strictly above.

    Strictness matters — with ``<`` on the previous bar, a series that merely *touches* and lifts
    off registers a cross, and a flat-equal stretch fires one on every bar of it.
    """
    prev_a, prev_b = shift(a, 1), shift(b, 1)
    crossed = (prev_a <= prev_b) & (a > b)
    unknown = np.isnan(prev_a) | np.isnan(prev_b) | np.isnan(a) | np.isnan(b)
    return np.where(unknown, np.nan, crossed.astype(np.float64))


def crossed_below(
    a: npt.NDArray[np.float64], b: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    return crossed_above(b, a)


def boolean(mask: npt.NDArray[np.bool_], unknown: npt.NDArray[np.bool_]) -> npt.NDArray[np.float64]:
    """Turn a comparison into the 0.0/1.0/``nan`` column every Event primitive returns."""
    return np.where(unknown, np.nan, mask.astype(np.float64))


def sqrt(a: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Element-wise square root, typed.

    ``np.sqrt`` is declared as returning ``Any`` under the pinned mypy/numpy pair, so calling it
    directly would silently erase the return type of every volatility primitive that uses it.
    """
    out: npt.NDArray[np.float64] = np.sqrt(a)
    return out


def safe_divide(
    numerator: npt.NDArray[np.float64], denominator: npt.NDArray[np.float64]
) -> npt.NDArray[np.float64]:
    """Divide, yielding ``nan`` where the denominator is zero rather than ``inf``.

    An ``inf`` propagates silently through later arithmetic and can end up comparing as a valid
    signal; a ``nan`` is carried as "not knowable" by every primitive here.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.divide(numerator, denominator)
    return np.where(np.isfinite(out), out, np.nan)
