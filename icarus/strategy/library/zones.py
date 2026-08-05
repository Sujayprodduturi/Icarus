"""Imbalance, zones and reference levels — catalogue §6.4-6.5 (task 1.4b).

**A zone is a band, not a line.** An order block or a fair value gap occupies a *range* of prices,
and the honest way to say that in a vocabulary of one-number-per-bar words is an explicit
``_top``/``_bottom`` pair (operator decision, 2026-08-04). The alternative — one word returning the
near edge — reads shorter and quietly makes "price is inside the block" inexpressible, which is the
only question anyone actually asks of a zone.

**Zones are reported only while they are alive.** A fair value gap that price has traded back
through is not a fair value gap any more, and an order block price has closed beyond has been
invalidated. Both stop being reported the moment that happens, rather than staying on the chart
where a strategy could still trade them. This matters because the grammar has no ``not`` operator:
if a dead zone kept being reported there would be no way to write "the gap that is still open".

**Blocks are known late, like swings.** An order block is the last opposing candle *before* an
impulsive move — so you cannot identify it until the impulse happens. It is reported from the
impulse bar, never from the candle itself, for exactly the reason set out in
:mod:`~icarus.strategy.library.structure`. Four block families share one implementation and differ
only in what triggers them and which part of the candle forms the band:

======================  ==========================================  =========================
Family                  Trigger                                     Band
======================  ==========================================  =========================
``order_block``         a structure break (``msb``)                 the whole candle
``breaker``             an order block price then closed beyond     the whole candle, flipped
``mitigation``          displacement *without* a structure break    the whole candle
``rejection``           displacement, origin chosen by wick         wick only
======================  ==========================================  =========================

**The institutional claim is not made.** The literature says an order block is where institutions
accumulated. On a daily bar we can see the geometry and nothing about who was trading; the word
implements the geometry and the docstring declines the story. The same restraint is why
``premium``/``discount`` are here as plain arithmetic — the value in them is the *discipline* of
only buying the lower half of a range, not any claim about what the halves mean.

**Higher-timeframe levels are causal or they are absent.** ``prev_week_high`` uses the last
*completed* week; ``weekly_open`` uses the current week's first bar, which is known once that bar
opens. A weekly high that included the current, unfinished week would be the same look-ahead bug as
an early swing, wearing a calendar.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, ChoiceParam, FloatParam, IntParam, Kind, Primitive
from icarus.strategy.library import _ops
from icarus.strategy.library.structure import (
    basis_param,
    last_swing_high,
    last_swing_low,
    msb_down,
    msb_up,
    refuses,
    swing_param,
)

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]

_MAX_AGE = 500
_FVG_BARS = 3  # a fair value gap is a three-bar pattern; bars 0 and 1 cannot carry one
_EPOCH_THURSDAY_OFFSET = 3  # 1970-01-01 was a Thursday; +3 puts week boundaries on Monday
_DAYS_PER_WEEK = 7


def _age(name: str = "max_age", default: int = 20) -> IntParam:
    """How long a zone stays live. Not a cosmetic limit: a gap from four years ago is not a level
    anyone is trading, and carrying it forever would let a strategy "find" one on every bar."""
    return IntParam(name, 1, _MAX_AGE, default=default)


# --------------------------------------------------------------------------------------
# Fair value gaps
# --------------------------------------------------------------------------------------


def _gaps(bars: Bars, max_age: int, *, up: bool) -> tuple[Column, Column, Column]:
    """``(top, bottom, filled)`` for the most recent *unfilled* gap of this direction.

    A bullish gap is a three-bar pattern where bar 1's high never met bar 3's low: nothing traded
    in between, which is the exact, non-approximate sense of an imbalance. It is knowable on bar 3.
    "Filled" means price has traded back through the *far* edge — a partial retrace into the gap
    leaves it live, which is the reading that makes a gap useful as an entry zone.
    """
    size = bars.close.size
    top, bottom = _ops.empty_like(bars.close), _ops.empty_like(bars.close)
    filled = _ops.empty_like(bars.close)
    active_top = active_bottom = np.nan
    born = -1
    for t in range(size):
        if t >= _FVG_BARS - 1:
            filled[t] = 0.0
            if up and bars.high[t - 2] < bars.low[t]:
                active_bottom, active_top, born = float(bars.high[t - 2]), float(bars.low[t]), t
            elif not up and bars.low[t - 2] > bars.high[t]:
                active_bottom, active_top, born = float(bars.high[t]), float(bars.low[t - 2]), t
        if np.isnan(active_top):
            continue
        if t - born > max_age:
            active_top = active_bottom = np.nan
            continue
        through = bars.low[t] <= active_bottom if up else bars.high[t] >= active_top
        if through and t > born:
            filled[t] = 1.0
            active_top = active_bottom = np.nan
            continue
        top[t], bottom[t] = active_top, active_bottom
    return top, bottom, filled


def _fvg_up_top(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=True)[0]


def _fvg_up_bottom(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=True)[1]


def _fvg_up_filled(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=True)[2]


def _fvg_down_top(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=False)[0]


def _fvg_down_bottom(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=False)[1]


def _fvg_down_filled(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _gaps(bars, max_age, up=False)[2]


def _balanced_range(bars: Bars, max_age: int) -> tuple[Column, Column]:
    """Where a live bullish and a live bearish gap overlap — opposing imbalances in one place."""
    up_top, up_bottom, _ = _gaps(bars, max_age, up=True)
    down_top, down_bottom, _ = _gaps(bars, max_age, up=False)
    top = np.minimum(up_top, down_top)
    bottom = np.maximum(up_bottom, down_bottom)
    overlaps = top > bottom
    return np.where(overlaps, top, np.nan), np.where(overlaps, bottom, np.nan)


def _bpr_top(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _balanced_range(bars, max_age)[0]


def _bpr_bottom(bars: Bars, *, max_age: int, **_: object) -> Column:
    return _balanced_range(bars, max_age)[1]


# --------------------------------------------------------------------------------------
# Displacement — the energy that qualifies a block
# --------------------------------------------------------------------------------------


def _displacement(bars: Bars, n: int, mult: float, *, up: bool) -> Column:
    """A bar that both *travelled* (range beyond ``mult`` ATR) and *committed* (closed near its
    extreme). Range alone would count a wide indecisive bar that closed mid-range."""
    span = bars.high - bars.low
    atr = _ops.atr(bars.high, bars.low, bars.close, n)
    position = _ops.safe_divide(bars.close - bars.low, span)
    committed = position >= 2.0 / 3.0 if up else position <= 1.0 / 3.0
    unknown = np.isnan(atr) | np.isnan(position)
    return _ops.boolean((span > mult * atr) & committed, unknown)


def _displacement_up(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    return _displacement(bars, n, mult, up=True)


def _displacement_down(bars: Bars, *, n: int, mult: float, **_: object) -> Column:
    return _displacement(bars, n, mult, up=False)


def _imbalance_ratio(bars: Bars, *, n: int, **_: object) -> Column:
    """Mean body-to-range over n bars — a cheap read on whether moves are being finished."""
    body = np.abs(bars.close - bars.open)
    return _ops.rolling_mean(_ops.safe_divide(body, bars.high - bars.low), n)


# --------------------------------------------------------------------------------------
# Blocks — one loop, four families
# --------------------------------------------------------------------------------------


def _origin(bars: Bars, t: int, search: int, *, bullish: bool, wick_ratio: float | None) -> int:
    """The candle a block is drawn on: the most recent *opposing* one before the impulse.

    With ``wick_ratio`` it is instead the most recent candle that was rejected from the level — a
    long tail on the relevant side — which is what distinguishes a rejection block from an order
    block drawn on the same impulse.
    """
    span = bars.high - bars.low
    for j in range(t - 1, max(t - search - 1, -1), -1):
        if wick_ratio is None:
            opposing = bars.close[j] < bars.open[j] if bullish else bars.close[j] > bars.open[j]
            if opposing:
                return j
            continue
        body_edge = (
            min(bars.open[j], bars.close[j]) if bullish else max(bars.open[j], bars.close[j])
        )
        tail = body_edge - bars.low[j] if bullish else bars.high[j] - body_edge
        if span[j] > 0.0 and tail / span[j] >= wick_ratio:
            return j
    return -1


def _blocks(
    bars: Bars,
    trigger: Column,
    *,
    bullish: bool,
    search: int,
    wick_ratio: float | None = None,
) -> tuple[Column, Column, Column, Column]:
    """``(top, bottom, breaker_top, breaker_bottom)``.

    A block lives until price *closes* beyond its far edge; at that moment it does not simply
    vanish, it flips — a demand zone that failed becomes supply. That flipped band is the breaker,
    and it is returned from the same loop so the two can never disagree about which block failed.

    **A breaker dies the same way a block does.** A failed bullish block is now resistance, and
    resistance a close has gone above is not resistance any more — it is invalidated by exactly the
    mirror of the rule that created it. Without that the breaker would be reported for the rest of
    the series: the first failed block of 2011 would still be "live resistance" in 2026, and a
    strategy would find one on every bar forever. That is the same objection the ``max_age``
    parameter exists to answer for gaps, and it is why ``breaker_*`` is ``intermittent``.
    """
    top, bottom = _ops.empty_like(bars.close), _ops.empty_like(bars.close)
    breaker_top, breaker_bottom = _ops.empty_like(bars.close), _ops.empty_like(bars.close)
    live_top = live_bottom = flip_top = flip_bottom = np.nan
    for t in range(bars.close.size):
        if trigger[t] == 1.0:
            j = _origin(bars, t, search, bullish=bullish, wick_ratio=wick_ratio)
            if j >= 0:
                if wick_ratio is None:
                    live_top, live_bottom = float(bars.high[j]), float(bars.low[j])
                elif bullish:
                    live_top = float(min(bars.open[j], bars.close[j]))
                    live_bottom = float(bars.low[j])
                else:
                    live_top = float(bars.high[j])
                    live_bottom = float(max(bars.open[j], bars.close[j]))
        # The breaker is tested *before* the block, and independently of whether one is live. Its
        # own invalidation has nothing to do with whether a new block happens to be forming — and a
        # new block usually forms on exactly the impulse that took the old breaker out, so gating
        # this on "no live block" would keep the dead breaker alive precisely when it died.
        if not np.isnan(flip_top):
            # The flip faces the other way, so its invalidation test is the other way too.
            failed = bars.close[t] > flip_top if bullish else bars.close[t] < flip_bottom
            if failed:
                flip_top = flip_bottom = np.nan
        if not np.isnan(live_top):
            invalidated = bars.close[t] < live_bottom if bullish else bars.close[t] > live_top
            if invalidated:
                # No risk of the line above killing this flip on its own birth bar: the close that
                # invalidated the block is below its floor, and the breaker dies on a close above
                # its ceiling.
                flip_top, flip_bottom = live_top, live_bottom
                live_top = live_bottom = np.nan
        top[t], bottom[t] = live_top, live_bottom
        breaker_top[t], breaker_bottom[t] = flip_top, flip_bottom
    return top, bottom, breaker_top, breaker_bottom


def _order_blocks(
    bars: Bars, k: int, basis: str, search: int, *, bullish: bool
) -> tuple[Column, Column, Column, Column]:
    trigger = msb_up(bars, k=k, basis=basis) if bullish else msb_down(bars, k=k, basis=basis)
    return _blocks(bars, trigger, bullish=bullish, search=search)


def _order_block_bull_top(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=True)[0]


def _order_block_bull_bottom(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=True)[1]


def _order_block_bear_top(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=False)[0]


def _order_block_bear_bottom(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=False)[1]


def _breaker_bear_top(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    """A failed *bullish* block is *bearish* resistance. The flip is the whole point of the word."""
    return _order_blocks(bars, k, basis, search, bullish=True)[2]


def _breaker_bear_bottom(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=True)[3]


def _breaker_bull_top(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=False)[2]


def _breaker_bull_bottom(bars: Bars, *, k: int, basis: str, search: int, **_: object) -> Column:
    return _order_blocks(bars, k, basis, search, bullish=False)[3]


def _mitigation(
    bars: Bars, k: int, basis: str, search: int, n: int, mult: float, *, bullish: bool
) -> tuple[Column, Column, Column, Column]:
    """Origin of a move that ran *without* taking the prior extreme — an internal move.

    That "without" is what separates it from an order block: same candle geometry, but the impulse
    stayed inside the existing structure instead of breaking it.
    """
    push = (
        _displacement(bars, n, mult, up=True) if bullish else _displacement(bars, n, mult, up=False)
    )
    broke = msb_up(bars, k=k, basis=basis) if bullish else msb_down(bars, k=k, basis=basis)
    unknown = np.isnan(push) | np.isnan(broke)
    trigger = _ops.boolean((push == 1.0) & (broke != 1.0), unknown)
    return _blocks(bars, trigger, bullish=bullish, search=search)


def _mitigation_bull_top(
    bars: Bars, *, k: int, basis: str, search: int, n: int, mult: float, **_: object
) -> Column:
    return _mitigation(bars, k, basis, search, n, mult, bullish=True)[0]


def _mitigation_bull_bottom(
    bars: Bars, *, k: int, basis: str, search: int, n: int, mult: float, **_: object
) -> Column:
    return _mitigation(bars, k, basis, search, n, mult, bullish=True)[1]


def _mitigation_bear_top(
    bars: Bars, *, k: int, basis: str, search: int, n: int, mult: float, **_: object
) -> Column:
    return _mitigation(bars, k, basis, search, n, mult, bullish=False)[0]


def _mitigation_bear_bottom(
    bars: Bars, *, k: int, basis: str, search: int, n: int, mult: float, **_: object
) -> Column:
    return _mitigation(bars, k, basis, search, n, mult, bullish=False)[1]


def _rejection(
    bars: Bars, search: int, n: int, mult: float, wick_ratio: float, *, bullish: bool
) -> tuple[Column, Column, Column, Column]:
    trigger = _displacement(bars, n, mult, up=bullish)
    return _blocks(bars, trigger, bullish=bullish, search=search, wick_ratio=wick_ratio)


def _rejection_bull_top(
    bars: Bars, *, search: int, n: int, mult: float, wick_ratio: float, **_: object
) -> Column:
    return _rejection(bars, search, n, mult, wick_ratio, bullish=True)[0]


def _rejection_bull_bottom(
    bars: Bars, *, search: int, n: int, mult: float, wick_ratio: float, **_: object
) -> Column:
    return _rejection(bars, search, n, mult, wick_ratio, bullish=True)[1]


def _rejection_bear_top(
    bars: Bars, *, search: int, n: int, mult: float, wick_ratio: float, **_: object
) -> Column:
    return _rejection(bars, search, n, mult, wick_ratio, bullish=False)[0]


def _rejection_bear_bottom(
    bars: Bars, *, search: int, n: int, mult: float, wick_ratio: float, **_: object
) -> Column:
    return _rejection(bars, search, n, mult, wick_ratio, bullish=False)[1]


# --------------------------------------------------------------------------------------
# Premium / discount / OTE — the discipline, expressed as arithmetic
# --------------------------------------------------------------------------------------


def _leg(bars: Bars, k: int) -> tuple[Column, Column]:
    """The current structural range: last confirmed swing low to last confirmed swing high.

    There is no separate ``structure_range_high/low`` word because it would be the same two prices
    under a second name — and a near-duplicate is how two things that must agree stop agreeing.
    """
    return last_swing_low(bars, k=k), last_swing_high(bars, k=k)


def _equilibrium(bars: Bars, *, k: int, **_: object) -> Column:
    low, high = _leg(bars, k)
    return (low + high) / 2.0


def _in_premium(bars: Bars, *, k: int, **_: object) -> Column:
    mid = _equilibrium(bars, k=k)
    return _ops.boolean(bars.close > mid, np.isnan(mid))


def _in_discount(bars: Bars, *, k: int, **_: object) -> Column:
    mid = _equilibrium(bars, k=k)
    return _ops.boolean(bars.close < mid, np.isnan(mid))


def _ote(bars: Bars, k: int, near: float, far: float, *, bullish: bool) -> tuple[Column, Column]:
    low, high = _leg(bars, k)
    span = high - low
    if bullish:
        return high - near * span, high - far * span
    return low + far * span, low + near * span


def _ote_bull_top(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    return _ote(bars, k, near, far, bullish=True)[0]


def _ote_bull_bottom(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    return _ote(bars, k, near, far, bullish=True)[1]


def _ote_bear_top(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    return _ote(bars, k, near, far, bullish=False)[0]


def _ote_bear_bottom(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    return _ote(bars, k, near, far, bullish=False)[1]


def _in_ote_bull(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    top, bottom = _ote(bars, k, near, far, bullish=True)
    return _ops.boolean((bars.low <= top) & (bars.high >= bottom), np.isnan(top))


def _in_ote_bear(bars: Bars, *, k: int, near: float, far: float, **_: object) -> Column:
    top, bottom = _ote(bars, k, near, far, bullish=False)
    return _ops.boolean((bars.low <= top) & (bars.high >= bottom), np.isnan(top))


def _fib_retracement(bars: Bars, *, k: int, level: float, **_: object) -> Column:
    low, high = _leg(bars, k)
    return high - level * (high - low)


# --------------------------------------------------------------------------------------
# Reference levels — causal by construction
# --------------------------------------------------------------------------------------


def _period_id(bars: Bars, period: str) -> npt.NDArray[np.int64]:
    days = bars.ts.astype("datetime64[D]").astype(np.int64)
    if period == "week":
        return (days + _EPOCH_THURSDAY_OFFSET) // _DAYS_PER_WEEK
    return bars.ts.astype("datetime64[M]").astype(np.int64)


def _period_levels(bars: Bars, period: str) -> tuple[Column, Column, Column, Column]:
    """``(open_of_current, high_of_previous, low_of_previous, close_of_previous)``.

    The current period contributes only its *open*, which is fixed the moment the period starts.
    Its high and low are still being written and cannot be read until the period closes — the same
    confirmation-lag rule as a swing, keeping time instead of price.
    """
    ids = _period_id(bars, period)
    size = bars.close.size
    current_open = _ops.empty_like(bars.close)
    prev_high, prev_low = _ops.empty_like(bars.close), _ops.empty_like(bars.close)
    prev_close = _ops.empty_like(bars.close)
    open_now = np.nan
    high_now = low_now = close_now = np.nan
    done_high = done_low = done_close = np.nan
    for t in range(size):
        if t == 0 or ids[t] != ids[t - 1]:
            done_high, done_low, done_close = high_now, low_now, close_now
            open_now = float(bars.open[t])
            high_now, low_now = float(bars.high[t]), float(bars.low[t])
        else:
            high_now = max(high_now, float(bars.high[t]))
            low_now = min(low_now, float(bars.low[t]))
        close_now = float(bars.close[t])
        current_open[t] = open_now
        prev_high[t], prev_low[t], prev_close[t] = done_high, done_low, done_close
    return current_open, prev_high, prev_low, prev_close


def _prev_day_high(bars: Bars, **_: object) -> Column:
    return _ops.shift(bars.high, 1)


def _prev_day_low(bars: Bars, **_: object) -> Column:
    return _ops.shift(bars.low, 1)


def _prev_day_close(bars: Bars, **_: object) -> Column:
    return _ops.shift(bars.close, 1)


def _daily_open(bars: Bars, **_: object) -> Column:
    """Today's open. Known at the open, and execution is next-bar (§30.2), so it is not a peek."""
    return bars.open.astype(np.float64, copy=True)


def _weekly_open(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "week")[0]


def _monthly_open(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "month")[0]


def _prev_week_high(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "week")[1]


def _prev_week_low(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "week")[2]


def _prev_month_high(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "month")[1]


def _prev_month_low(bars: Bars, **_: object) -> Column:
    return _period_levels(bars, "month")[2]


def _htf_bias(bars: Bars, *, period: str, **_: object) -> Column:
    """+1/-1/0 from the last two *completed* higher-timeframe closes. Resampling must be causal:
    a weekly bar is only usable after the week ends.

    The comparison is made on the period *boundaries* rather than bar to bar. ``prev_close`` is
    already carried across every bar of the current period, so asking for "the previous value" of
    that dense column would return yesterday's copy of the same number and the bias would always
    read 0.
    """
    ids = _period_id(bars, period)
    prev_close = _period_levels(bars, period)[3]
    starts = np.ones(ids.size, dtype=bool)
    starts[1:] = ids[1:] != ids[:-1]
    at_boundary = np.where(starts, prev_close, np.nan)
    earlier = _ops.forward_fill(_ops.previous_value(at_boundary))
    unknown = np.isnan(prev_close) | np.isnan(earlier)
    bias = np.where(prev_close > earlier, 1.0, np.where(prev_close < earlier, -1.0, 0.0))
    return np.where(unknown, np.nan, bias)


_NEEDS_INTRADAY = "a daily bar has no intra-session detail"


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §6.4-6.5."""
    k = swing_param()
    basis = basis_param()
    search = IntParam("search", 1, 50, default=5)
    atr_n = IntParam("n", 2, 200, default=14)
    mult = FloatParam("mult", 0.1, 10.0, default=1.5)
    wick_ratio = FloatParam("wick_ratio", 0.1, 0.95, default=0.5)
    near = FloatParam("near", 0.1, 0.95, default=0.62)
    far = FloatParam("far", 0.1, 0.99, default=0.79)
    return (
        # ---- fair value gaps ----
        Primitive(
            "fvg_up_top",
            Kind.LEVEL,
            "Upper edge of the live bullish gap.",
            _fvg_up_top,
            (_age(),),
            intermittent=True,
        ),
        Primitive(
            "fvg_up_bottom",
            Kind.LEVEL,
            "Lower edge of the live bullish gap.",
            _fvg_up_bottom,
            (_age(),),
            intermittent=True,
        ),
        Primitive(
            "fvg_down_top",
            Kind.LEVEL,
            "Upper edge of the live bearish gap.",
            _fvg_down_top,
            (_age(),),
            intermittent=True,
        ),
        Primitive(
            "fvg_down_bottom",
            Kind.LEVEL,
            "Lower edge of the live bearish gap.",
            _fvg_down_bottom,
            (_age(),),
            intermittent=True,
        ),
        Primitive(
            "fvg_up_filled",
            Kind.EVENT,
            "Price traded back through the bullish gap.",
            _fvg_up_filled,
            (_age(),),
        ),
        Primitive(
            "fvg_down_filled",
            Kind.EVENT,
            "Price traded back through the bearish gap.",
            _fvg_down_filled,
            (_age(),),
        ),
        Primitive(
            "bpr_top",
            Kind.LEVEL,
            "Upper edge where opposing gaps overlap.",
            _bpr_top,
            (_age(),),
            intermittent=True,
        ),
        Primitive(
            "bpr_bottom",
            Kind.LEVEL,
            "Lower edge where opposing gaps overlap.",
            _bpr_bottom,
            (_age(),),
            intermittent=True,
        ),
        # ---- displacement ----
        Primitive(
            "displacement_up",
            Kind.EVENT,
            "Wide bar closing near its high — the energy that validates a block.",
            _displacement_up,
            (atr_n, mult),
        ),
        Primitive(
            "displacement_down",
            Kind.EVENT,
            "Wide bar closing near its low.",
            _displacement_down,
            (atr_n, mult),
        ),
        Primitive(
            "imbalance_ratio",
            Kind.SERIES,
            "Mean body-to-range over n bars.",
            _imbalance_ratio,
            (IntParam("n", 2, 200, default=5),),
        ),
        # ---- blocks ----
        Primitive(
            "order_block_bull_top",
            Kind.LEVEL,
            "Top of the live bullish order block.",
            _order_block_bull_top,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "order_block_bull_bottom",
            Kind.LEVEL,
            "Bottom of the live bullish order block.",
            _order_block_bull_bottom,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "order_block_bear_top",
            Kind.LEVEL,
            "Top of the live bearish order block.",
            _order_block_bear_top,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "order_block_bear_bottom",
            Kind.LEVEL,
            "Bottom of the live bearish order block.",
            _order_block_bear_bottom,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "breaker_bull_top",
            Kind.LEVEL,
            "Top of a failed bearish block, now support.",
            _breaker_bull_top,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "breaker_bull_bottom",
            Kind.LEVEL,
            "Bottom of a failed bearish block, now support.",
            _breaker_bull_bottom,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "breaker_bear_top",
            Kind.LEVEL,
            "Top of a failed bullish block, now resistance.",
            _breaker_bear_top,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "breaker_bear_bottom",
            Kind.LEVEL,
            "Bottom of a failed bullish block, now resistance.",
            _breaker_bear_bottom,
            (k, basis, search),
            intermittent=True,
        ),
        Primitive(
            "mitigation_bull_top",
            Kind.LEVEL,
            "Top of the origin candle of an internal move up.",
            _mitigation_bull_top,
            (k, basis, search, atr_n, mult),
            intermittent=True,
        ),
        Primitive(
            "mitigation_bull_bottom",
            Kind.LEVEL,
            "Bottom of the origin candle of an internal move up.",
            _mitigation_bull_bottom,
            (k, basis, search, atr_n, mult),
            intermittent=True,
        ),
        Primitive(
            "mitigation_bear_top",
            Kind.LEVEL,
            "Top of the origin candle of an internal move down.",
            _mitigation_bear_top,
            (k, basis, search, atr_n, mult),
            intermittent=True,
        ),
        Primitive(
            "mitigation_bear_bottom",
            Kind.LEVEL,
            "Bottom of the origin candle of an internal move down.",
            _mitigation_bear_bottom,
            (k, basis, search, atr_n, mult),
            intermittent=True,
        ),
        Primitive(
            "rejection_bull_top",
            Kind.LEVEL,
            "Top of the lower wick price was rejected from.",
            _rejection_bull_top,
            (search, atr_n, mult, wick_ratio),
            intermittent=True,
        ),
        Primitive(
            "rejection_bull_bottom",
            Kind.LEVEL,
            "Bottom of the lower wick price was rejected from.",
            _rejection_bull_bottom,
            (search, atr_n, mult, wick_ratio),
            intermittent=True,
        ),
        Primitive(
            "rejection_bear_top",
            Kind.LEVEL,
            "Top of the upper wick price was rejected from.",
            _rejection_bear_top,
            (search, atr_n, mult, wick_ratio),
            intermittent=True,
        ),
        Primitive(
            "rejection_bear_bottom",
            Kind.LEVEL,
            "Bottom of the upper wick price was rejected from.",
            _rejection_bear_bottom,
            (search, atr_n, mult, wick_ratio),
            intermittent=True,
        ),
        # ---- premium / discount / OTE ----
        Primitive(
            "equilibrium",
            Kind.LEVEL,
            "Midpoint of the current structural range.",
            _equilibrium,
            (k,),
        ),
        Primitive(
            "in_premium", Kind.EVENT, "Close in the upper half of the range.", _in_premium, (k,)
        ),
        Primitive(
            "in_discount", Kind.EVENT, "Close in the lower half of the range.", _in_discount, (k,)
        ),
        Primitive(
            "ote_bull_top",
            Kind.LEVEL,
            "Shallow edge of the long OTE band.",
            _ote_bull_top,
            (k, near, far),
        ),
        Primitive(
            "ote_bull_bottom",
            Kind.LEVEL,
            "Deep edge of the long OTE band.",
            _ote_bull_bottom,
            (k, near, far),
        ),
        Primitive(
            "ote_bear_top",
            Kind.LEVEL,
            "Deep edge of the short OTE band.",
            _ote_bear_top,
            (k, near, far),
        ),
        Primitive(
            "ote_bear_bottom",
            Kind.LEVEL,
            "Shallow edge of the short OTE band.",
            _ote_bear_bottom,
            (k, near, far),
        ),
        Primitive(
            "in_ote_bull",
            Kind.EVENT,
            "Price traded into the long OTE band.",
            _in_ote_bull,
            (k, near, far),
        ),
        Primitive(
            "in_ote_bear",
            Kind.EVENT,
            "Price traded into the short OTE band.",
            _in_ote_bear,
            (k, near, far),
        ),
        Primitive(
            "fib_retracement",
            Kind.LEVEL,
            "Retracement of the last confirmed swing leg.",
            _fib_retracement,
            (k, FloatParam("level", 0.0, 1.0, default=0.618)),
        ),
        # ---- reference levels ----
        Primitive("prev_day_high", Kind.LEVEL, "Yesterday's high (PDH).", _prev_day_high),
        Primitive("prev_day_low", Kind.LEVEL, "Yesterday's low (PDL).", _prev_day_low),
        Primitive("prev_day_close", Kind.LEVEL, "Yesterday's close.", _prev_day_close),
        Primitive("daily_open", Kind.LEVEL, "Today's open.", _daily_open),
        Primitive("weekly_open", Kind.LEVEL, "Open of the current week.", _weekly_open),
        Primitive("monthly_open", Kind.LEVEL, "Open of the current month.", _monthly_open),
        Primitive(
            "prev_week_high", Kind.LEVEL, "High of the last completed week.", _prev_week_high
        ),
        Primitive("prev_week_low", Kind.LEVEL, "Low of the last completed week.", _prev_week_low),
        Primitive(
            "prev_month_high", Kind.LEVEL, "High of the last completed month.", _prev_month_high
        ),
        Primitive(
            "prev_month_low", Kind.LEVEL, "Low of the last completed month.", _prev_month_low
        ),
        Primitive(
            "htf_bias",
            Kind.SERIES,
            "+1/-1/0 from the last two completed higher-timeframe closes.",
            _htf_bias,
            (ChoiceParam("period", ("week", "month"), default="week"),),
        ),
        # ---- INTRADAY: defined so they exist in the grammar, refusing on daily bars ----
        Primitive(
            "killzone",
            Kind.EVENT,
            "Inside a London/NY/Asia session window. Needs intraday bars.",
            refuses("killzone", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            (ChoiceParam("name", ("london", "new_york", "asia"), default="london"),),
            intraday_only=True,
        ),
        Primitive(
            "session_range_high",
            Kind.LEVEL,
            "High of a named session. Needs intraday bars.",
            refuses("session_range_high", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "session_range_low",
            Kind.LEVEL,
            "Low of a named session. Needs intraday bars.",
            refuses("session_range_low", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "opening_range_high",
            Kind.LEVEL,
            "High of the first n minutes (ORB). Needs intraday bars.",
            refuses("opening_range_high", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "opening_range_low",
            Kind.LEVEL,
            "Low of the first n minutes (ORB). Needs intraday bars.",
            refuses("opening_range_low", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "judas_swing",
            Kind.EVENT,
            "Early-session false move. Needs intraday bars.",
            refuses("judas_swing", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "power_hour",
            Kind.EVENT,
            "Final hour of the session. Needs intraday bars.",
            refuses("power_hour", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
        Primitive(
            "silver_bullet",
            Kind.EVENT,
            "The specific hour-window ICT setup. Needs intraday bars.",
            refuses("silver_bullet", _NEEDS_INTRADAY),  # type: ignore[arg-type]
            intraday_only=True,
        ),
    )
