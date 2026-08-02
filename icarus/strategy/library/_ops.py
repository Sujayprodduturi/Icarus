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

if TYPE_CHECKING:
    import numpy.typing as npt

Column = "npt.NDArray[np.float64]"


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
