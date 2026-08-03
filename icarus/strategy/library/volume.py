"""Volume, participation and flow primitives — catalogue §5 (task 1.4a).

This module carries the two honesty flags that the rest of the vocabulary does not, so it is where
the refusal machinery in :mod:`icarus.strategy.dsl` actually earns its keep.

**INTRADAY.** A true session-anchored VWAP and a volume profile both need to know how volume was
distributed *within* the bar. A daily bar cannot tell you that — it reports one total. The honest
options were to define them and refuse on daily bars, or to silently substitute a rolling
approximation; the second produces a backtest whose "VWAP" is not the VWAP anyone trades, and no
error is raised anywhere. They refuse.

**FEED.** The India-only context primitives (delivery split, participant-wise F&O positioning, the
F&O ban list) read from the sources built in 1.1d. They are declared here so the vocabulary is
complete and a strategy naming one gets a clear refusal rather than "unknown primitive" — but their
values are not yet threaded into :class:`~icarus.strategy.dsl.Bars`, which is 1.7's wiring job. Two
independent guards keep that from becoming a silent zero: the parser rejects them unless the caller
proves the feed exists, and the compute function raises if it is ever reached anyway.

``in_fno_ban`` is a **veto, not a signal** — it is registered as a CONTEXT primitive so a strategy
can express "do not trade this today", and there is deliberately no ban-frequency or days-in-ban
counter anywhere. A compliance boundary that becomes a numeric feature is something the learning
loop can learn to *seek* rather than respect (invariant #4).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, DslError, IntParam, Kind, Primitive
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]

_MAX_PERIOD = 1000

# Feed names a caller must declare in `available_feeds` before these parse.
FEED_DELIVERY = "nse-delivery"
FEED_PARTICIPANTS = "nse-participants"
FEED_FNO_BAN = "nse-fno-ban"


def _period(name: str = "n", default: int | None = None) -> IntParam:
    return IntParam(name, 2, _MAX_PERIOD, default=default)


def _volume_sma(bars: Bars, *, n: int, **_: object) -> Column:
    return _ops.rolling_mean(bars.volume, n)


def _relative_volume(bars: Bars, *, n: int, **_: object) -> Column:
    """Today's volume against its own average. Excludes today from the average — otherwise a
    genuine volume spike inflates the very baseline it is being measured against."""
    return _ops.safe_divide(bars.volume, _ops.shift(_ops.rolling_mean(bars.volume, n), 1))


def _traded_value(bars: Bars, *, n: int, **_: object) -> Column:
    """Rupee turnover, not share count — the only honest cross-symbol liquidity measure.

    Share count is meaningless across symbols: a million shares of a ₹15 stock and a million of a
    ₹3,000 one are three orders of magnitude apart in what they can absorb. This feeds the capacity
    model (1.8b), where getting it wrong means backtesting a size the market could never fill.
    """
    return _ops.rolling_mean(bars.close * bars.volume, n)


def _obv(bars: Bars, **_: object) -> Column:
    """On-balance volume.

    The ``nan`` fills below are 0.0, and that is a different act from filling with a *value*: zero
    means "this bar contributes nothing to the running total", which is exactly true when there is
    no previous close to compare against. Bar 0 is then masked back to ``nan`` so no reader mistakes
    an empty total for a real one.
    """
    direction = np.sign(np.diff(bars.close, prepend=np.nan))
    signed = np.nan_to_num(direction, nan=0.0) * bars.volume
    out: Column = np.cumsum(signed)
    out[0] = np.nan
    return out


def _ad_line(bars: Bars, **_: object) -> Column:
    """Accumulation/distribution line.

    The multiplier is ``nan`` only on a zero-range bar (high == low), where the standard treatment
    is no accumulation. Filling with 0.0 states exactly that; it invents no price.
    """
    multiplier = _ops.safe_divide(
        (bars.close - bars.low) - (bars.high - bars.close), bars.high - bars.low
    )
    return np.cumsum(np.nan_to_num(multiplier * bars.volume, nan=0.0))


def _cmf(bars: Bars, *, n: int, **_: object) -> Column:
    """Chaikin money flow. Zero-range bars contribute no flow — see :func:`_ad_line`."""
    multiplier = _ops.safe_divide(
        (bars.close - bars.low) - (bars.high - bars.close), bars.high - bars.low
    )
    flow = np.nan_to_num(multiplier, nan=0.0) * bars.volume
    return _ops.safe_divide(_ops.rolling_sum(flow, n), _ops.rolling_sum(bars.volume, n))


def _mfi(bars: Bars, *, n: int, **_: object) -> Column:
    """Volume-weighted RSI."""
    typical = (bars.high + bars.low + bars.close) / 3.0
    raw_flow = typical * bars.volume
    change = np.diff(typical, prepend=np.nan)
    positive = np.where(change > 0, raw_flow, 0.0)
    negative = np.where(change < 0, raw_flow, 0.0)
    positive[0] = negative[0] = np.nan
    ratio = _ops.safe_divide(_ops.rolling_sum(positive, n), _ops.rolling_sum(negative, n))
    return 100.0 - (100.0 / (1.0 + ratio))


def _rolling_vwap(bars: Bars, *, n: int, **_: object) -> Column:
    """Volume-weighted average price over a rolling window.

    Named ``rolling_vwap`` and not ``vwap`` on purpose: the thing traders mean by "VWAP" is
    anchored to the session and needs intraday data. Calling this one ``vwap`` would invite a
    strategy to claim it trades against the session VWAP when it does not (see ``session_vwap``).
    """
    typical = (bars.high + bars.low + bars.close) / 3.0
    return _ops.safe_divide(
        _ops.rolling_sum(typical * bars.volume, n), _ops.rolling_sum(bars.volume, n)
    )


def _vwap_band(bars: Bars, n: int, k: float, *, upper: bool) -> Column:
    vwap = _rolling_vwap(bars, n=n)
    typical = (bars.high + bars.low + bars.close) / 3.0
    spread = _ops.rolling_std(typical - vwap, n, ddof=1)
    return vwap + k * spread if upper else vwap - k * spread


def _vwap_upper(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    return _vwap_band(bars, n, k, upper=True)


def _vwap_lower(bars: Bars, *, n: int, k: float, **_: object) -> Column:
    return _vwap_band(bars, n, k, upper=False)


def _refuses(name: str, reason: str) -> object:
    """A compute function that raises rather than returning a plausible number.

    The parser normally stops these before evaluation. This is the backstop for the case where a
    caller declares a feed available that is not actually wired — the failure has to be loud,
    because the quiet version is a strategy whose filter silently passed everything.
    """

    def compute(bars: Bars, **_: object) -> Column:
        raise DslError(f"{name} cannot be computed: {reason}")

    return compute


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §5 — computable, intraday-gated and feed-gated words together."""
    from icarus.strategy.dsl import FloatParam

    return (
        Primitive(
            "volume_sma",
            Kind.SERIES,
            "Average volume over n bars.",
            _volume_sma,
            (_period(default=20),),
        ),
        Primitive(
            "relative_volume",
            Kind.SERIES,
            "Volume / its trailing average, excluding today.",
            _relative_volume,
            (_period(default=20),),
        ),
        Primitive(
            "traded_value",
            Kind.SERIES,
            "Average rupee turnover — the liquidity filter.",
            _traded_value,
            (_period(default=20),),
        ),
        Primitive("obv", Kind.SERIES, "On-balance volume.", _obv),
        Primitive("ad_line", Kind.SERIES, "Accumulation/distribution line.", _ad_line),
        Primitive(
            "chaikin_money_flow", Kind.SERIES, "Chaikin money flow.", _cmf, (_period(default=20),)
        ),
        Primitive(
            "mfi",
            Kind.SERIES,
            "Money flow index — volume-weighted RSI.",
            _mfi,
            (_period(default=14),),
        ),
        Primitive(
            "rolling_vwap",
            Kind.LEVEL,
            "Rolling volume-weighted average price.",
            _rolling_vwap,
            (_period(default=20),),
        ),
        Primitive(
            "vwap_upper",
            Kind.LEVEL,
            "Rolling VWAP + k*spread.",
            _vwap_upper,
            (_period(default=20), FloatParam("k", 0.1, 10.0, default=2.0)),
        ),
        Primitive(
            "vwap_lower",
            Kind.LEVEL,
            "Rolling VWAP - k*spread.",
            _vwap_lower,
            (_period(default=20), FloatParam("k", 0.1, 10.0, default=2.0)),
        ),
        # ---- INTRADAY: defined so they exist in the grammar, refusing on daily bars ----
        Primitive(
            "session_vwap",
            Kind.LEVEL,
            "Session-anchored VWAP. Needs intraday bars.",
            _refuses("session_vwap", "session anchoring needs intraday bars (Phase 2)"),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "volume_profile_poc",
            Kind.LEVEL,
            "Point of control of the volume profile. Needs intraday bars.",
            _refuses("volume_profile_poc", "a daily bar has no intra-bar volume distribution"),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "value_area_high",
            Kind.LEVEL,
            "Upper bound of the value area. Needs intraday bars.",
            _refuses("value_area_high", "a daily bar has no intra-bar volume distribution"),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "value_area_low",
            Kind.LEVEL,
            "Lower bound of the value area. Needs intraday bars.",
            _refuses("value_area_low", "a daily bar has no intra-bar volume distribution"),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        # ---- FEED: the India-only context words from 1.1d, not yet threaded into Bars ----
        Primitive(
            "delivery_pct",
            Kind.CONTEXT,
            "Percent of volume that settled as delivery (India-only, 2011->).",
            _refuses("delivery_pct", "feed values are not threaded into Bars until 1.7"),  # type: ignore[arg-type]
            requires_feed=FEED_DELIVERY,
        ),
        Primitive(
            "delivery_qty",
            Kind.CONTEXT,
            "Shares that settled as delivery.",
            _refuses("delivery_qty", "feed values are not threaded into Bars until 1.7"),  # type: ignore[arg-type]
            requires_feed=FEED_DELIVERY,
        ),
        Primitive(
            "fii_net_index_fut",
            Kind.CONTEXT,
            "FII net index-futures position, market-wide.",
            _refuses("fii_net_index_fut", "feed values are not threaded into Bars until 1.7"),  # type: ignore[arg-type]
            requires_feed=FEED_PARTICIPANTS,
        ),
        Primitive(
            "client_net_index_fut",
            Kind.CONTEXT,
            "Retail net index-futures position — the natural fade.",
            _refuses("client_net_index_fut", "feed values are not threaded into Bars until 1.7"),  # type: ignore[arg-type]
            requires_feed=FEED_PARTICIPANTS,
        ),
        Primitive(
            "in_fno_ban",
            Kind.CONTEXT,
            "Symbol is in the F&O ban list. A veto, never a signal.",
            _refuses("in_fno_ban", "feed values are not threaded into Bars until 1.7"),  # type: ignore[arg-type]
            requires_feed=FEED_FNO_BAN,
        ),
    )
