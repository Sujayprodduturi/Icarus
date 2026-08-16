"""The classic operators — catalogue §7 (task 1.4b).

Six discretionary traditions, mined for the parts that are actually mechanical. The test each one
had to pass to appear here is narrow: **can the rule be written down completely enough that two
people reading it compute the same column?** Where the answer is no, the word is absent and the
reason is recorded, because a half-specified word is worse than a missing one — it looks like the
method is implemented when what is implemented is one particular guess at it.

**Wyckoff's spring is SMC's liquidity sweep, forty years earlier.** ``spring`` and ``upthrust``
are the *same function objects* as
:func:`~icarus.strategy.library.structure.sweep_and_reclaim_low` and ``_high``, not
reimplementations. The names exist because a Wyckoff-flavoured strategy reads better in its own
vocabulary; sharing the object means a strategy that uses both cannot end up looking like it has
two independent confirmations of one event. That is fake diversification, and the Validation gate
would credit it.

**Named recipes are one word, not a lucky combination.** ``trend_template`` and ``stage`` bundle
several conditions each. They could be written as ``all: [...]`` in a strategy file, and a strategy
is free to do that — but then the exact recipe would live in whichever file happened to spell it
out, and two strategies would drift into two different "Minervini templates". As one word it is one
definition, parameterised where Minervini himself parameterised it and fixed where he fixed it.

**What is deliberately absent:**

* *Elliott wave / Gann* — banned by the catalogue (§11). Wave labelling is discretionary by
  construction, so no two runs agree; it also violates the white-box requirement in spirit.
* *O'Neil's CANSLIM letters* — C, A, N, S and I need earnings and institutional-ownership data we
  do not have. The RS-rating is cross-sectional and belongs to task 1.4c, not here.
* *The Turtle exit* — the system's opposite-breakout exit ("leave a long on a 10-day low") is a
  genuine mechanical rule, and ``donchian_breakout_down(n=10)`` is exactly that column. It cannot
  be *wired up* yet: the exit vocabulary in :mod:`~icarus.strategy.dsl` is a fixed list of
  position-relative rules and does not accept an event. The word is here and correct; the wiring is
  a DSL change, noted rather than faked with a stop that approximates it.
* *Turtle pyramiding* (add 0.5N in the trade's favour, up to four units) — position management, not
  a signal. It belongs to the Risk agent, and inventing a primitive for it would put sizing logic
  somewhere the risk caps do not see it (invariant #4).
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import Bars, FloatParam, IntParam, Kind, Primitive
from icarus.strategy.library import _ops, structure
from icarus.strategy.library.structure import basis_param
from icarus.strategy.library.volatility import donchian_lower, donchian_upper

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]
    Mask = npt.NDArray[np.bool_]

_MAX_LEGS = 10

# Weinstein counts in weeks and Minervini in months and years; the library speaks in bars, so the
# conversions are named here rather than appearing as bare numbers in a default.
_WEINSTEIN_MA_BARS = 150  # his 30-week MA, at 5 trading days a week
_TRADING_DAYS_PER_YEAR = 252
_TRADING_DAYS_PER_MONTH = 21

# stage() encoding. Weinstein numbers his stages 1-4 and every description of the method uses those
# numbers, so the column carries them literally rather than a private encoding.
_BASING = 1.0
_ADVANCING = 2.0
_TOPPING = 3.0
_DECLINING = 4.0


# --------------------------------------------------------------------------------------
# Turtles and Livermore — range breakouts, with and without volume
# --------------------------------------------------------------------------------------


def _range_breakout(bars: Bars, n: int, basis: str, *, up: bool) -> tuple[Mask, Mask]:
    """``(fires, unknown)`` for a fresh break of the prior ``n``-bar extreme.

    The extreme is ``donchian_upper``/``donchian_lower`` itself, not a second spelling of it, so a
    breakout can never disagree with the channel it is breaking. That channel **excludes the current
    bar**: an n-bar high that includes today can never be exceeded, so a breakout rule built on it
    would never fire. Only *fresh* breaks count — price sitting above a level it broke a week ago is
    not a breakout every day since.
    """
    extreme = donchian_upper(bars, n=n) if up else donchian_lower(bars, n=n)
    if basis == "close":
        price = bars.close
    else:
        price = bars.high if up else bars.low
    beyond = (price > extreme) if up else (price < extreme)
    return beyond & ~_ops.previous_bar(beyond), np.isnan(extreme)


def _donchian_breakout_up(bars: Bars, *, n: int, basis: str, **_: object) -> Column:
    fires, unknown = _range_breakout(bars, n, basis, up=True)
    return _ops.boolean(fires, unknown)


def _donchian_breakout_down(bars: Bars, *, n: int, basis: str, **_: object) -> Column:
    fires, unknown = _range_breakout(bars, n, basis, up=False)
    return _ops.boolean(fires, unknown)


def _pivotal_point(
    bars: Bars, n: int, basis: str, vol_n: int, vol_mult: float, *, up: bool
) -> Column:
    """Livermore's pivotal point — the same breakout, but only when volume confirms it.

    Built on ``_range_breakout`` rather than re-derived, so a pivotal point can never fire on a bar
    ``donchian_breakout_*`` says was not a breakout.
    """
    fires, unknown = _range_breakout(bars, n, basis, up=up)
    relative = _ops.relative_to_average(bars.volume, vol_n)
    return _ops.boolean(fires & (relative > vol_mult), unknown | np.isnan(relative))


def _pivotal_point_up(
    bars: Bars, *, n: int, basis: str, vol_n: int, vol_mult: float, **_: object
) -> Column:
    return _pivotal_point(bars, n, basis, vol_n, vol_mult, up=True)


def _pivotal_point_down(
    bars: Bars, *, n: int, basis: str, vol_n: int, vol_mult: float, **_: object
) -> Column:
    return _pivotal_point(bars, n, basis, vol_n, vol_mult, up=False)


# --------------------------------------------------------------------------------------
# Wyckoff
# --------------------------------------------------------------------------------------


def _effort_vs_result(bars: Bars, *, n: int, **_: object) -> Column:
    """Volume relative to its own average, divided by range relative to its own average.

    Above 1 means more effort than result — heavy trade that did not move price, which is what
    Wyckoff read as absorption. Both sides are normalised by their own ``n``-bar mean because
    volume and price are in different units and their raw ratio would say more about the share
    price than about the tape; both exclude today, for the reason in
    :func:`~icarus.strategy.library._ops.relative_to_average`.
    """
    effort = _ops.relative_to_average(bars.volume, n)
    result = _ops.relative_to_average(bars.high - bars.low, n)
    return _ops.safe_divide(effort, result)


# --------------------------------------------------------------------------------------
# Weinstein stage analysis
# --------------------------------------------------------------------------------------


def _stage(bars: Bars, *, n: int, slope_n: int, flat: float, **_: object) -> Column:
    """Weinstein's four stages from a long moving average and its slope.

    The partition is exhaustive and mutually exclusive by construction — every bar with a knowable
    MA gets exactly one stage:

    ========  ==================================  ===================================
    Stage     Condition                           Reading
    ========  ==================================  ===================================
    1 basing  below the MA, MA not falling        accumulation after a decline
    2 advance above the MA, MA rising             the only stage Weinstein buys in
    3 topping above the MA, MA not rising         distribution
    4 decline below the MA, MA falling            the only stage he is short or out
    ========  ==================================  ===================================

    "Rising" is a move of more than ``flat`` (a fraction of the MA itself) over ``slope_n`` bars.
    A bare ``ma > ma_prev`` would call a MA that drifted 0.01% "rising" and make stages 1 and 3
    effectively unreachable — the flat band is what makes the four-way split mean anything.
    """
    ma = _ops.rolling_mean(bars.close, n)
    past = _ops.shift(ma, slope_n)
    change = _ops.safe_divide(ma - past, np.abs(past))
    above = bars.close > ma
    rising = change > flat
    falling = change < -flat
    stage = np.where(
        above,
        np.where(rising, _ADVANCING, _TOPPING),
        np.where(falling, _DECLINING, _BASING),
    )
    unknown = np.isnan(ma) | np.isnan(change)
    return np.where(unknown, np.nan, stage)


def _stage_is(bars: Bars, label: float, *, n: int, slope_n: int, flat: float) -> Column:
    stage = _stage(bars, n=n, slope_n=slope_n, flat=flat)
    return _ops.boolean(stage == label, np.isnan(stage))


def _stage_basing(bars: Bars, *, n: int, slope_n: int, flat: float, **_: object) -> Column:
    return _stage_is(bars, _BASING, n=n, slope_n=slope_n, flat=flat)


def _stage_advancing(bars: Bars, *, n: int, slope_n: int, flat: float, **_: object) -> Column:
    return _stage_is(bars, _ADVANCING, n=n, slope_n=slope_n, flat=flat)


def _stage_topping(bars: Bars, *, n: int, slope_n: int, flat: float, **_: object) -> Column:
    return _stage_is(bars, _TOPPING, n=n, slope_n=slope_n, flat=flat)


def _stage_declining(bars: Bars, *, n: int, slope_n: int, flat: float, **_: object) -> Column:
    return _stage_is(bars, _DECLINING, n=n, slope_n=slope_n, flat=flat)


# --------------------------------------------------------------------------------------
# Darvas box
# --------------------------------------------------------------------------------------


def _darvas(bars: Bars, n: int, confirm: int) -> tuple[Column, Column, Column]:
    """``(top, bottom, broke_out)`` for the live box.

    Darvas drew a box when a new high held: a fresh ``n``-bar high sets a candidate ceiling, and if
    the next ``confirm`` bars fail to exceed it the box is real, its floor being the lowest low of
    those bars. The box is only *knowable* on the confirming bar — the same late knowledge as a
    swing, and for the same reason — so nothing is reported before then.

    A live box ends the moment a close leaves it: above the top is the breakout Darvas traded,
    below the bottom is the box failing. Either way it stops being reported, because a box price
    has left is not a box.
    """
    size = bars.close.size
    top, bottom = _ops.empty_like(bars.close), _ops.empty_like(bars.close)
    broke = _ops.empty_like(bars.close)
    prior_high = _ops.shift(_ops.rolling_max(bars.high, n), 1)
    live_top = live_bottom = np.nan
    candidate = np.nan
    candidate_bar = -1
    for t in range(size):
        if np.isnan(prior_high[t]):
            continue
        broke[t] = 0.0
        # A fresh n-bar high restarts the count; exceeding a pending candidate does the same.
        if bars.high[t] > prior_high[t] and (np.isnan(candidate) or bars.high[t] > candidate):
            candidate, candidate_bar = float(bars.high[t]), t
        elif not np.isnan(candidate) and t - candidate_bar >= confirm:
            live_top = candidate
            live_bottom = float(bars.low[candidate_bar + 1 : t + 1].min())
            candidate = np.nan
        if np.isnan(live_top):
            continue
        if bars.close[t] > live_top:
            broke[t] = 1.0
            live_top = live_bottom = np.nan
            continue
        if bars.close[t] < live_bottom:
            live_top = live_bottom = np.nan
            continue
        top[t], bottom[t] = live_top, live_bottom
    return top, bottom, broke


def _darvas_box_top(bars: Bars, *, n: int, confirm: int, **_: object) -> Column:
    return _darvas(bars, n, confirm)[0]


def _darvas_box_bottom(bars: Bars, *, n: int, confirm: int, **_: object) -> Column:
    return _darvas(bars, n, confirm)[1]


def _darvas_breakout_up(bars: Bars, *, n: int, confirm: int, **_: object) -> Column:
    return _darvas(bars, n, confirm)[2]


# --------------------------------------------------------------------------------------
# Minervini — VCP and the trend template
# --------------------------------------------------------------------------------------


def _pullback_depths(bars: Bars, k: int) -> list[tuple[int, float]]:
    """``(confirmation_bar, depth)`` for each confirmed swing-high-to-swing-low leg, in order.

    Depth is a *fraction* of the swing high, not a rupee amount, so a contraction sequence means
    the same thing at ₹200 and ₹4,000. Both ends come from the shared swing detector in
    :mod:`~icarus.strategy.library.structure`, so a pullback cannot be measured from a peak the
    structure words do not agree existed.
    """
    highs = structure.swing_highs(bars, k)
    lows = structure.swing_lows(bars, k)
    legs: list[tuple[int, float]] = []
    pending = np.nan
    for t in range(bars.close.size):
        if not np.isnan(highs[t]):
            pending = float(highs[t])
        if np.isnan(lows[t]) or np.isnan(pending) or pending <= 0.0:
            continue
        legs.append((t, (pending - float(lows[t])) / pending))
        pending = np.nan
    return legs


def _volatility_contraction(bars: Bars, *, k: int, legs: int, **_: object) -> Column:
    """Minervini's VCP: the last ``legs`` pullbacks each shallower than the one before.

    A state event, carried forward from the bar the final swing low confirms — the pattern is a
    description of where price *is*, and one that was true for a single bar could not filter
    anything. It goes false again the moment a deeper pullback breaks the sequence.
    """
    out = _ops.empty_like(bars.close)
    depths = _pullback_depths(bars, k)
    for position, (t, _depth) in enumerate(depths):
        window = [depth for _, depth in depths[position - legs + 1 : position + 1]]
        contracting = len(window) == legs and all(
            later < earlier for earlier, later in itertools.pairwise(window)
        )
        out[t] = 1.0 if contracting else 0.0
    return _ops.forward_fill(out)


def _pct_off_high(bars: Bars, *, n: int, **_: object) -> Column:
    """How far below its own ``n``-bar high price is, as a fraction. 0 means at the high.

    The window *includes* today, unlike the breakout words: this describes where price stands
    relative to a range that is already known, rather than asking whether price has exceeded
    something — so there is nothing self-referential about counting today in it.
    """
    highest = _ops.rolling_max(bars.high, n)
    return _ops.safe_divide(highest - bars.close, highest)


def _pct_off_low(bars: Bars, *, n: int, **_: object) -> Column:
    """How far above its own ``n``-bar low price is, as a fraction of that low."""
    lowest = _ops.rolling_min(bars.low, n)
    return _ops.safe_divide(bars.close - lowest, lowest)


def _trend_template(
    bars: Bars,
    *,
    fast: int,
    slow: int,
    slope_n: int,
    n: int,
    above_low: float,
    off_high: float,
    **_: object,
) -> Column:
    """Minervini's trend template, as the catalogue states it (§7).

    Close above the ``fast`` MA, ``fast`` above ``slow``, ``slow`` rising over ``slope_n`` bars,
    price at least ``above_low`` above its ``n``-bar low and within ``off_high`` of its ``n``-bar
    high. The published template also names a 50-day MA and a relative-strength rank; the RS rank
    is cross-sectional (task 1.4c) and the 50-day leg is not in the catalogue's wording, so neither
    is invented here — the word implements the stated recipe and no more.
    """
    fast_ma = _ops.rolling_mean(bars.close, fast)
    slow_ma = _ops.rolling_mean(bars.close, slow)
    slow_past = _ops.shift(slow_ma, slope_n)
    from_low = _pct_off_low(bars, n=n)
    from_high = _pct_off_high(bars, n=n)
    holds = (
        (bars.close > fast_ma)
        & (fast_ma > slow_ma)
        & (slow_ma > slow_past)
        & (from_low >= above_low)
        & (from_high <= off_high)
    )
    unknown = (
        np.isnan(fast_ma)
        | np.isnan(slow_ma)
        | np.isnan(slow_past)
        | np.isnan(from_low)
        | np.isnan(from_high)
    )
    return _ops.boolean(holds, unknown)


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §7."""
    # The Turtles themselves traded resting stop orders — the wick reading — so `basis` stays a
    # parameter here rather than a decision made for the strategy. Same declaration as structure's,
    # imported rather than respelled.
    basis = basis_param()
    vol_n = _ops.period_param("vol_n", default=50)
    vol_mult = FloatParam("vol_mult", 1.0, 10.0, default=1.5)
    k = IntParam("k", 1, 100, default=3)
    # No `requires_lt=(("slope_n", "n"),)`, deliberately. It was added on 2026-08-16 and removed
    # the same day, because it was asserted from the shape of the parameter names rather than
    # measured. `_stage` compares an `n`-bar moving average with itself `slope_n` bars ago, so
    # `slope_n >= n` is a longer-horizon slope on a shorter average — `stage(n=50, slope_n=63)` is
    # a quarterly slope on a ten-week MA, which is a perfectly ordinary thing to ask for and was
    # being refused at parse time. Contrast `macd`, where transposing `fast`/`slow` flips the sign
    # on 100% of bars: that word comes to mean the opposite of its name, and is refused for it.
    stage_params = (
        _ops.period_param(default=_WEINSTEIN_MA_BARS),
        _ops.period_param("slope_n", default=_TRADING_DAYS_PER_MONTH),
        FloatParam("flat", 0.0, 0.5, default=0.01),
    )
    return (
        # ---- Turtles ----
        Primitive(
            "donchian_breakout_up",
            Kind.EVENT,
            "Fresh break above the prior n-bar high — the Turtle entry.",
            _donchian_breakout_up,
            (_ops.period_param(default=20), basis),
        ),
        Primitive(
            "donchian_breakout_down",
            Kind.EVENT,
            "Fresh break below the prior n-bar low — the Turtle short entry.",
            _donchian_breakout_down,
            (_ops.period_param(default=20), basis),
        ),
        # ---- Wyckoff ----
        Primitive(
            "spring",
            Kind.EVENT,
            "Wyckoff spring — swept the low and reclaimed it. Same event as sweep_and_reclaim_low.",
            structure.sweep_and_reclaim_low,
            (k, IntParam("n", 1, 500, default=3)),
        ),
        Primitive(
            "upthrust",
            Kind.EVENT,
            "Wyckoff upthrust — swept the high and lost it. Same event as sweep_and_reclaim_high.",
            structure.sweep_and_reclaim_high,
            (k, IntParam("n", 1, 500, default=3)),
        ),
        Primitive(
            "effort_vs_result",
            Kind.SERIES,
            "Relative volume divided by relative range; above 1 is effort without result.",
            _effort_vs_result,
            (_ops.period_param(default=20),),
            scale_free=True,
        ),
        # ---- Weinstein ----
        Primitive(
            "stage",
            Kind.SERIES,
            "Weinstein stage: 1 basing, 2 advancing, 3 topping, 4 declining.",
            _stage,
            stage_params,
            scale_free=True,
        ),
        Primitive(
            "stage_basing",
            Kind.EVENT,
            "State: Weinstein stage 1.",
            _stage_basing,
            stage_params,
        ),
        Primitive(
            "stage_advancing",
            Kind.EVENT,
            "State: Weinstein stage 2 — the only stage the method buys in.",
            _stage_advancing,
            stage_params,
        ),
        Primitive(
            "stage_topping",
            Kind.EVENT,
            "State: Weinstein stage 3.",
            _stage_topping,
            stage_params,
        ),
        Primitive(
            "stage_declining",
            Kind.EVENT,
            "State: Weinstein stage 4.",
            _stage_declining,
            stage_params,
        ),
        # ---- Darvas ----
        # No `requires_lt` on `confirm`/`n`, deliberately. It was added on 2026-08-16 and removed
        # the same day: `confirm` is how many bars a fresh `n`-bar high must stand unexceeded
        # before the box is real, and there is nothing degenerate about requiring a 3-bar high to
        # hold for 20 sessions. Measured, it produces a distinct, meaningful column. See the note
        # on `stage_params` above.
        Primitive(
            "darvas_box_top",
            Kind.LEVEL,
            "Ceiling of the live Darvas box.",
            _darvas_box_top,
            (_ops.period_param(default=20), _ops.period_param("confirm", default=3)),
            intermittent=True,
        ),
        Primitive(
            "darvas_box_bottom",
            Kind.LEVEL,
            "Floor of the live Darvas box.",
            _darvas_box_bottom,
            (_ops.period_param(default=20), _ops.period_param("confirm", default=3)),
            intermittent=True,
        ),
        Primitive(
            "darvas_breakout_up",
            Kind.EVENT,
            "Close above the ceiling of a live Darvas box.",
            _darvas_breakout_up,
            (_ops.period_param(default=20), _ops.period_param("confirm", default=3)),
        ),
        # ---- Minervini ----
        Primitive(
            "volatility_contraction",
            Kind.EVENT,
            "State: the last `legs` pullbacks each shallower than the one before (VCP).",
            _volatility_contraction,
            (k, IntParam("legs", 2, _MAX_LEGS, default=3)),
        ),
        Primitive(
            "pct_off_high",
            Kind.SERIES,
            "Fraction below the n-bar high (default 252 bars ~ 52 weeks).",
            _pct_off_high,
            (_ops.period_param(default=_TRADING_DAYS_PER_YEAR),),
            scale_free=True,
        ),
        Primitive(
            "pct_off_low",
            Kind.SERIES,
            "Fraction above the n-bar low (default 252 bars ~ 52 weeks).",
            _pct_off_low,
            (_ops.period_param(default=_TRADING_DAYS_PER_YEAR),),
            scale_free=True,
        ),
        Primitive(
            "trend_template",
            Kind.EVENT,
            "State: Minervini's trend template holds on this bar.",
            _trend_template,
            (
                _ops.period_param("fast", default=150),
                _ops.period_param("slow", default=200),
                _ops.period_param("slope_n", default=_TRADING_DAYS_PER_MONTH),
                _ops.period_param(default=_TRADING_DAYS_PER_YEAR),
                FloatParam("above_low", 0.0, 5.0, default=0.25),
                FloatParam("off_high", 0.0, 1.0, default=0.25),
            ),
        ),
        # ---- Livermore ----
        Primitive(
            "pivotal_point_up",
            Kind.EVENT,
            "Break above the prior n-bar high on expanded volume.",
            _pivotal_point_up,
            (_ops.period_param(default=20), basis, vol_n, vol_mult),
        ),
        Primitive(
            "pivotal_point_down",
            Kind.EVENT,
            "Break below the prior n-bar low on expanded volume.",
            _pivotal_point_down,
            (_ops.period_param(default=20), basis, vol_n, vol_mult),
        ),
    )
