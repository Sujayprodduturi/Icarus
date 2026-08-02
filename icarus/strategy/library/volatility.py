"""Volatility, range and risk primitives — catalogue §3 (task 1.4a).

ATR is the unit of risk in half the catalogue: stops, position sizing and the SMC zone definitions
in 1.4b are all expressed in ATR multiples, which is what makes a rule mean the same thing on a
₹200 stock and a ₹4,000 one.

The **range-based volatility estimators** (Parkinson, Garman-Klass, Rogers-Satchell, Yang-Zhang)
are the part worth noticing. Close-to-close volatility throws away the high and the low — roughly
80% of what a daily bar tells you about how much the price moved. These use the full bar and are
several times more statistically efficient at the same sample size, and Yang-Zhang additionally
handles the overnight gap, which matters on NSE where a large share of the move happens between
sessions. They are almost absent from retail toolkits, which is precisely why they are here.

``donchian_*`` deliberately **excludes the current bar**. An n-bar high that includes today is
trivially self-referential — price can never exceed it, so a breakout rule built on it never fires.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, FloatParam, IntParam, Kind, Primitive
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]

_MAX_PERIOD = 1000
_TRADING_DAYS = 252.0
# Precomputed as a plain float: `ndarray * np.sqrt(scalar)` types as Any under the pinned
# mypy/numpy pair, which would quietly switch off checking on every volatility primitive.
_ANNUALISE = 252.0**0.5
_PARKINSON_SCALE = 4.0 * 0.6931471805599453  # 4 * ln(2)


def _period(name: str = "n", default: int | None = None) -> IntParam:
    return IntParam(name, 2, _MAX_PERIOD, default=default)


def _tr(bars: Bars, **_: object) -> Column:
    return _ops.true_range(bars.high, bars.low, bars.close)


def _atr_values(bars: Bars, n: int) -> Column:
    return _ops.wilder(_ops.true_range(bars.high, bars.low, bars.close), n)


def _atr(bars: Bars, *, n: int, **_: object) -> Column:
    return _atr_values(bars, n)


def _natr(bars: Bars, *, n: int, **_: object) -> Column:
    """ATR as a fraction of price — the only ATR that is comparable across symbols."""
    return _ops.safe_divide(_atr_values(bars, n), bars.close)


def _log_returns(close: Column) -> Column:
    out: Column = np.log(_ops.safe_divide(close, _ops.shift(close, 1)))
    return out


def _realized_vol(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.rolling_std(_log_returns(bars.close), n, ddof=1) * _ANNUALISE


def _parkinson(bars: Bars, *, n: int, **_: object) -> Column:
    hl: Column = np.log(_ops.safe_divide(bars.high, bars.low)) ** 2.0
    mean = _ops.rolling_mean(hl, n)
    return _ops.sqrt(mean / (_PARKINSON_SCALE)) * _ANNUALISE


def _garman_klass(bars: Bars, *, n: int, **_: object) -> Column:
    hl: Column = 0.5 * np.log(_ops.safe_divide(bars.high, bars.low)) ** 2.0
    co: Column = (2.0 * 0.6931471805599453 - 1.0) * np.log(
        _ops.safe_divide(bars.close, bars.open)
    ) ** 2.0
    mean = _ops.rolling_mean(hl - co, n)
    return _ops.sqrt(np.maximum(mean, 0.0)) * _ANNUALISE


def _rogers_satchell(bars: Bars, *, n: int, **_: object) -> Column:
    term: Column = np.log(_ops.safe_divide(bars.high, bars.close)) * np.log(
        _ops.safe_divide(bars.high, bars.open)
    ) + np.log(_ops.safe_divide(bars.low, bars.close)) * np.log(
        _ops.safe_divide(bars.low, bars.open)
    )
    mean = _ops.rolling_mean(term, n)
    return _ops.sqrt(np.maximum(mean, 0.0)) * _ANNUALISE


def _yang_zhang(bars: Bars, *, n: int, **_: object) -> Column:
    """Overnight + open-to-close + Rogers-Satchell. Handles gaps, which NSE has plenty of."""
    overnight = np.log(_ops.safe_divide(bars.open, _ops.shift(bars.close, 1)))
    open_close = np.log(_ops.safe_divide(bars.close, bars.open))
    var_o = _ops.rolling_std(overnight, n, ddof=1) ** 2
    var_c = _ops.rolling_std(open_close, n, ddof=1) ** 2
    rs = _rogers_satchell(bars, n=n) ** 2 / _TRADING_DAYS
    k = 0.34 / (1.34 + (n + 1.0) / (n - 1.0))
    return _ops.sqrt(np.maximum(var_o + k * var_c + (1.0 - k) * rs, 0.0)) * _ANNUALISE


def _bollinger(bars: Bars, n: int, k: float) -> tuple[Column, Column, Column]:
    mid = _ops.rolling_mean(bars.close, n)
    band = k * _ops.rolling_std(bars.close, n)
    return mid + band, mid, mid - band


def _boll_upper(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    return _bollinger(bars, n, k)[0]


def _boll_mid(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    return _bollinger(bars, n, k)[1]


def _boll_lower(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    return _bollinger(bars, n, k)[2]


def _bandwidth(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    upper, mid, lower = _bollinger(bars, n, k)
    return _ops.safe_divide(upper - lower, mid)


def _percent_b(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    upper, _mid, lower = _bollinger(bars, n, k)
    return _ops.safe_divide(bars.close - lower, upper - lower)


def _keltner(bars: Bars, n: int, mult: float) -> tuple[Column, Column]:
    mid = _ops.ema(bars.close, n)
    band = mult * _atr_values(bars, n)
    return mid + band, mid - band


def _keltner_upper(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    return _keltner(bars, n, mult)[0]


def _keltner_lower(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    return _keltner(bars, n, mult)[1]


def _donchian_upper(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.shift(_ops.rolling_max(bars.high, n), 1)


def _donchian_lower(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.shift(_ops.rolling_min(bars.low, n), 1)


def _donchian_mid(bars: Bars, *, n: int, **_: object) -> Column:
    return (_donchian_upper(bars, n=n) + _donchian_lower(bars, n=n)) / 2.0


def _squeeze_on(bars: Bars, *, n: int, k: float, mult: float, **_: object) -> Column:
    """Bollinger bands inside Keltner channels — the classic volatility-contraction trigger."""
    b_up, _mid, b_low = _bollinger(bars, n, k)
    k_up, k_low = _keltner(bars, n, mult)
    unknown = np.isnan(b_up) | np.isnan(k_up)
    return _ops.boolean((b_up < k_up) & (b_low > k_low), unknown)


def _vol_percentile(bars: Bars, *, n: int, lookback: int, **_: object) -> Column:
    """Where current volatility sits within its own history — the regime input."""
    vol = _realized_vol(bars, n=n)
    out = _ops.empty_like(vol)
    if lookback <= vol.size:
        windows = np.lib.stride_tricks.sliding_window_view(vol, lookback)
        current = vol[lookback - 1 :]
        out[lookback - 1 :] = (windows <= current[:, None]).sum(axis=1) / lookback
    return np.where(np.isnan(vol), np.nan, out)


def _vol_of_vol(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.rolling_std(_realized_vol(bars, n=n), n, ddof=1)


def _chandelier_stop(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    return _ops.rolling_max(bars.high, n) - mult * _atr_values(bars, n)


def _ulcer_index(bars: Bars, *, n: int, **_: object) -> Column:
    """Depth *and* duration of drawdown — a better filter than max-drawdown, which ignores time."""
    peak = _ops.rolling_max(bars.close, n)
    drawdown = 100.0 * _ops.safe_divide(bars.close - peak, peak)
    return _ops.sqrt(_ops.rolling_mean(drawdown**2, n))


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §3."""
    k = FloatParam("k", 0.1, 10.0, default=2.0)
    mult = FloatParam("mult", 0.1, 20.0, default=1.5)
    return (
        Primitive("true_range", Kind.SERIES, "Gap-aware bar range.", _tr),
        Primitive("atr", Kind.SERIES, "Wilder-smoothed true range.", _atr, (_period(default=14),)),
        Primitive(
            "natr",
            Kind.SERIES,
            "ATR / close — comparable across symbols.",
            _natr,
            (_period(default=14),),
        ),
        Primitive(
            "realized_vol",
            Kind.SERIES,
            "Annualised stdev of log returns.",
            _realized_vol,
            (_period(default=20),),
        ),
        Primitive(
            "parkinson_vol",
            Kind.SERIES,
            "High-low range volatility estimator.",
            _parkinson,
            (_period(default=20),),
        ),
        Primitive(
            "garman_klass_vol",
            Kind.SERIES,
            "OHLC volatility estimator.",
            _garman_klass,
            (_period(default=20),),
        ),
        Primitive(
            "rogers_satchell_vol",
            Kind.SERIES,
            "Drift-independent OHLC volatility estimator.",
            _rogers_satchell,
            (_period(default=20),),
        ),
        Primitive(
            "yang_zhang_vol",
            Kind.SERIES,
            "Gap-aware volatility estimator — best on NSE dailies.",
            _yang_zhang,
            (_period(default=20),),
        ),
        Primitive(
            "bollinger_upper", Kind.LEVEL, "SMA + k*stdev.", _boll_upper, (_period(default=20), k)
        ),
        Primitive(
            "bollinger_mid", Kind.LEVEL, "SMA of close.", _boll_mid, (_period(default=20), k)
        ),
        Primitive(
            "bollinger_lower", Kind.LEVEL, "SMA - k*stdev.", _boll_lower, (_period(default=20), k)
        ),
        Primitive(
            "bollinger_bandwidth",
            Kind.SERIES,
            "Band width / mid — the squeeze detector.",
            _bandwidth,
            (_period(default=20), k),
        ),
        Primitive(
            "percent_b",
            Kind.SERIES,
            "Position of close within the bands.",
            _percent_b,
            (_period(default=20), k),
        ),
        Primitive(
            "keltner_upper",
            Kind.LEVEL,
            "EMA + mult*ATR.",
            _keltner_upper,
            (_period(default=20), mult),
        ),
        Primitive(
            "keltner_lower",
            Kind.LEVEL,
            "EMA - mult*ATR.",
            _keltner_lower,
            (_period(default=20), mult),
        ),
        Primitive(
            "donchian_upper",
            Kind.LEVEL,
            "n-bar high, excluding the current bar.",
            _donchian_upper,
            (_period(default=20),),
        ),
        Primitive(
            "donchian_lower",
            Kind.LEVEL,
            "n-bar low, excluding the current bar.",
            _donchian_lower,
            (_period(default=20),),
        ),
        Primitive(
            "donchian_mid",
            Kind.LEVEL,
            "Midpoint of the Donchian channel.",
            _donchian_mid,
            (_period(default=20),),
        ),
        Primitive(
            "squeeze_on",
            Kind.EVENT,
            "Bollinger inside Keltner — volatility contraction.",
            _squeeze_on,
            (_period(default=20), k, mult),
        ),
        Primitive(
            "vol_percentile",
            Kind.SERIES,
            "Rank of current volatility in its own history.",
            _vol_percentile,
            (_period(default=20), IntParam("lookback", 10, 2000, default=252)),
        ),
        Primitive(
            "vol_of_vol",
            Kind.SERIES,
            "Stdev of realized volatility.",
            _vol_of_vol,
            (_period(default=20),),
        ),
        Primitive(
            "chandelier_stop",
            Kind.LEVEL,
            "Highest high - mult*ATR.",
            _chandelier_stop,
            (_period(default=22), FloatParam("mult", 0.1, 20.0, default=3.0)),
        ),
        Primitive(
            "ulcer_index",
            Kind.SERIES,
            "Depth-and-duration drawdown measure.",
            _ulcer_index,
            (_period(default=14),),
        ),
    )
