"""Market structure, breaks and liquidity — catalogue §6.1-6.3 (task 1.4b).

**Everything here rests on one fact: a swing is known late.** A bar is a swing high when its high
exceeds the ``k`` bars on *either* side of it. The right-hand side has not happened yet, so a peak
that *occurred* on bar ``t`` only becomes *knowable* on bar ``t+k``. Every primitive in this module
places its result on the confirmation bar, never on the bar the swing occurred.

Recording the swing on bar ``t`` is what nearly every charting library does, and on a chart it is
correct — you are looking at the past. In a backtest it hands the strategy a peak ``k`` days before
anyone could have identified it, and because *breaks, liquidity pools, order blocks and
premium/discount zones are all defined in terms of swings*, the head start propagates into fifty
downstream words at once, always flattering, never visible in the results. It is the single most
likely way this project produces a strategy that backtests beautifully and loses money live.

Two things pin it: ``test_no_primitive_sees_the_future`` (a swing recorded early *disappears* when
the future is truncated, and the nan-pattern assertion catches that), and hand-computed fixtures
that name the exact bar each swing is allowed to appear on.

**Moment events vs state events.** Two different jobs, deliberately not blurred:

* *Moment* — fires on one bar and is 0.0 elsewhere: ``swing_high``, ``msb_up``, ``bos_up``,
  ``choch_up``, ``swept_low``, ``sweep_and_reclaim_low``, ``failed_break_up``.
* *State* — true for as long as it holds, refreshed at each swing confirmation:
  ``structure_bullish``, ``higher_highs``, ``equal_lows``.

A trend filter that only fired on the bar the trend was confirmed would be useless as a filter, and
a sweep that stayed true for weeks would be useless as a trigger. Each word is one or the other,
and its summary says which.

**Names that are the same geometry share one implementation.** Wyckoff's *spring* (1930s) and SMC's
*liquidity sweep* (2010s) are the same event described twice; ``liquidity_pool_high`` is the same
price as ``last_swing_high``. The aliases exist because a Donlevey-style strategy reads better in
its own vocabulary — but they point at the same function object, because two implementations would
drift apart and a strategy using both would look like it had two independent confirmations of one
signal. That is fake diversification, and the Validation gate would credit it.

**BOS vs CHoCH vs MSB.** All three are the same break; the *prevailing structure* is what names it.
``msb_up`` is any fresh break above the last confirmed swing high. ``bos_up`` is that break while
structure is already bullish (continuation); ``choch_up`` is it while structure is bearish (the
first crack). A break inside a *ranging* structure is neither, and shows only in ``msb_up`` — the
catalogue asks for the difference to be documented rather than silently decided, so it is.

**Deliberately absent.** ``liquidity_void`` is catalogued as a "daily-computable approximation of an
imbalance" — but the fair value gap in :mod:`~icarus.strategy.library.zones` is the exact,
non-approximate version of the same idea, and this project does not ship approximations of things
it can compute properly. ``trendline_liquidity`` needs a fitted diagonal whose slope is a
discretionary choice; it is deferred rather than guessed at.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

from icarus.strategy.dsl import Bars, ChoiceParam, DslError, FloatParam, IntParam, Kind, Primitive
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]

# A swing needs 2k+1 bars, so k is bounded well below any usable series length.
_MAX_K = 100
_MAX_BARS = 500
_BULLISH = 1.0
_BEARISH = -1.0
_RANGING = 0.0

# swing_sequence encoding. Highs and lows share one column so a strategy can read "what just
# happened structurally" as a single number; the magnitude says which extreme moved.
_HIGHER_HIGH = 2.0
_HIGHER_LOW = 1.0
_EQUAL = 0.0
_LOWER_HIGH = -1.0
_LOWER_LOW = -2.0


def _swing_param() -> IntParam:
    """``k`` — bars either side. The confirmation lag *is* ``k``; a bigger k is a slower, surer
    swing."""
    return IntParam("k", 1, _MAX_K, default=3)


def _bar_count(name: str, default: int) -> IntParam:
    return IntParam(name, 1, _MAX_BARS, default=default)


def _basis_param() -> ChoiceParam:
    """Whether a break needs the *close* beyond the level or merely the wick.

    ``close`` is the default because the loose reading is the one that flatters a backtest: price
    pokes through a level intraday far more often than it settles beyond it, and every one of those
    pokes becomes a signal that a live trader watching the close would never have taken.
    """
    return ChoiceParam("basis", ("close", "wick"), default="close")


# --------------------------------------------------------------------------------------
# Swing detection — the foundation everything else stands on
# --------------------------------------------------------------------------------------


def _confirmed(values: Column, k: int, *, peak: bool) -> Column:
    """Sparse column: the swing's price, placed on the bar it became **confirmable**.

    A bar is a swing when it is *strictly* beyond both neighbourhoods. Strictness matters: with
    ``>=`` a plateau of equal highs makes every bar in it a swing, and the "last swing high" then
    jitters between identical prices while the count of structural events inflates.
    """
    out = _ops.empty_like(values)
    span = 2 * k + 1
    if span <= values.size:
        windows = sliding_window_view(values, span)
        centre = windows[:, k]
        if peak:
            beyond = (centre > windows[:, :k].max(axis=1)) & (
                centre > windows[:, k + 1 :].max(axis=1)
            )
        else:
            beyond = (centre < windows[:, :k].min(axis=1)) & (
                centre < windows[:, k + 1 :].min(axis=1)
            )
        # Window j is centred on bar j+k and is complete only at bar j+2k — hence the offset.
        out[2 * k :] = np.where(beyond, centre, np.nan)
    return out


def _swing_highs(bars: Bars, k: int) -> Column:
    return _confirmed(bars.high, k, peak=True)


def _swing_lows(bars: Bars, k: int) -> Column:
    return _confirmed(bars.low, k, peak=False)


def _swing_high_event(bars: Bars, *, k: int, **_: object) -> Column:
    known = np.arange(bars.close.size) >= 2 * k
    return _ops.boolean(~np.isnan(_swing_highs(bars, k)), ~known)


def _swing_low_event(bars: Bars, *, k: int, **_: object) -> Column:
    known = np.arange(bars.close.size) >= 2 * k
    return _ops.boolean(~np.isnan(_swing_lows(bars, k)), ~known)


def _last_swing_high(bars: Bars, *, k: int, **_: object) -> Column:
    return _ops.forward_fill(_swing_highs(bars, k))


def _last_swing_low(bars: Bars, *, k: int, **_: object) -> Column:
    return _ops.forward_fill(_swing_lows(bars, k))


def _prior_swing_high(bars: Bars, *, k: int, **_: object) -> Column:
    return _ops.forward_fill(_ops.previous_value(_swing_highs(bars, k)))


def _prior_swing_low(bars: Bars, *, k: int, **_: object) -> Column:
    return _ops.forward_fill(_ops.previous_value(_swing_lows(bars, k)))


def _swing_sequence(bars: Bars, *, k: int, **_: object) -> Column:
    """The HH/HL/LH/LL chain as one number, carried forward: see the ``_HIGHER_HIGH`` constants.

    When a high and a low confirm on the same bar the high's classification is reported — an
    arbitrary but *fixed* choice, so the column is deterministic; the low is still readable through
    ``last_swing_low``.
    """
    out = _ops.empty_like(bars.close)
    for values, up, down in (
        (_swing_lows(bars, k), _HIGHER_LOW, _LOWER_LOW),
        (_swing_highs(bars, k), _HIGHER_HIGH, _LOWER_HIGH),
    ):
        prior = _ops.previous_value(values)
        at = ~np.isnan(prior)
        out[at] = np.where(
            values[at] > prior[at], up, np.where(values[at] < prior[at], down, _EQUAL)
        )
    return _ops.forward_fill(out)


def _structure(bars: Bars, k: int) -> Column:
    """+1 bullish (HH *and* HL), -1 bearish (LH *and* LL), 0 ranging. ``nan`` until four swings."""
    high, prior_high = _last_swing_high(bars, k=k), _prior_swing_high(bars, k=k)
    low, prior_low = _last_swing_low(bars, k=k), _prior_swing_low(bars, k=k)
    unknown = np.isnan(high) | np.isnan(prior_high) | np.isnan(low) | np.isnan(prior_low)
    bullish = (high > prior_high) & (low > prior_low)
    bearish = (high < prior_high) & (low < prior_low)
    label = np.where(bullish, _BULLISH, np.where(bearish, _BEARISH, _RANGING))
    return np.where(unknown, np.nan, label)


def _market_structure(bars: Bars, *, k: int, **_: object) -> Column:
    return _structure(bars, k)


def _structure_is(bars: Bars, k: int, label: float) -> Column:
    structure = _structure(bars, k)
    return _ops.boolean(structure == label, np.isnan(structure))


def _structure_bullish(bars: Bars, *, k: int, **_: object) -> Column:
    return _structure_is(bars, k, _BULLISH)


def _structure_bearish(bars: Bars, *, k: int, **_: object) -> Column:
    return _structure_is(bars, k, _BEARISH)


def _structure_ranging(bars: Bars, *, k: int, **_: object) -> Column:
    return _structure_is(bars, k, _RANGING)


def _monotone_run(values: Column, n: int, *, rising: bool) -> Column:
    """State event: the last ``n`` confirmed swings ran strictly one way. Carried forward."""
    out = _ops.empty_like(values)
    at = np.flatnonzero(~np.isnan(values))
    run = 0
    for position, index in enumerate(at):
        if position == 0:
            out[index] = np.nan
            continue
        previous = values[at[position - 1]]
        stepped = values[index] > previous if rising else values[index] < previous
        run = run + 1 if stepped else 0
        out[index] = 1.0 if run >= n - 1 else 0.0
    return _ops.forward_fill(out)


def _higher_highs(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _monotone_run(_swing_highs(bars, k), n, rising=True)


def _higher_lows(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _monotone_run(_swing_lows(bars, k), n, rising=True)


def _lower_highs(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _monotone_run(_swing_highs(bars, k), n, rising=False)


def _lower_lows(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _monotone_run(_swing_lows(bars, k), n, rising=False)


# --------------------------------------------------------------------------------------
# Breaks — one implementation, three names
# --------------------------------------------------------------------------------------


def _price_for(bars: Bars, basis: str, *, up: bool) -> Column:
    if basis == "close":
        return bars.close
    return bars.high if up else bars.low


def _fresh_break(bars: Bars, k: int, basis: str, *, up: bool) -> Column:
    """A break that is *new* on this bar. Beyond-and-staying-beyond is not an event every day.

    Re-crossing the same level after falling back does fire again, which is the honest reading: the
    level was reclaimed and then broken a second time, and a trader watching would have seen two
    breaks.
    """
    level = _last_swing_high(bars, k=k) if up else _last_swing_low(bars, k=k)
    price = _price_for(bars, basis, up=up)
    beyond = (price > level) if up else (price < level)
    return _ops.boolean(beyond & ~_ops.previous_bar(beyond), np.isnan(level))


def _msb_up(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _fresh_break(bars, k, basis, up=True)


def _msb_down(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _fresh_break(bars, k, basis, up=False)


def _break_in_structure(bars: Bars, k: int, basis: str, *, up: bool, label: float) -> Column:
    broke = _fresh_break(bars, k, basis, up=up)
    structure = _structure(bars, k)
    unknown = np.isnan(broke) | np.isnan(structure)
    return _ops.boolean((broke == 1.0) & (structure == label), unknown)


def _bos_up(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _break_in_structure(bars, k, basis, up=True, label=_BULLISH)


def _bos_down(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _break_in_structure(bars, k, basis, up=False, label=_BEARISH)


def _choch_up(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _break_in_structure(bars, k, basis, up=True, label=_BEARISH)


def _choch_down(bars: Bars, *, k: int, basis: str, **_: object) -> Column:
    return _break_in_structure(bars, k, basis, up=False, label=_BULLISH)


def _failed_break(bars: Bars, k: int, n: int, basis: str, *, up: bool) -> Column:
    """A break that is given back within ``n`` bars — Wyckoff's failed auction, fired on the bar the
    close returns to the wrong side of the broken level."""
    level = _last_swing_high(bars, k=k) if up else _last_swing_low(bars, k=k)
    broke = _fresh_break(bars, k, basis, up=up)
    out = _ops.empty_like(bars.close)
    active = np.nan
    deadline = -1
    for t in range(bars.close.size):
        if np.isnan(level[t]):
            continue
        out[t] = 0.0
        if broke[t] == 1.0:
            active, deadline = float(level[t]), t + n
            continue
        if np.isnan(active) or t > deadline:
            continue
        returned = bars.close[t] < active if up else bars.close[t] > active
        if returned:
            out[t] = 1.0
            active = np.nan
    return out


def _failed_break_up(bars: Bars, *, k: int, n: int, basis: str, **_: object) -> Column:
    return _failed_break(bars, k, n, basis, up=True)


def _failed_break_down(bars: Bars, *, k: int, n: int, basis: str, **_: object) -> Column:
    return _failed_break(bars, k, n, basis, up=False)


# --------------------------------------------------------------------------------------
# Liquidity — pools, sweeps, and the Donlevey core
# --------------------------------------------------------------------------------------


def _swept_high(bars: Bars, *, k: int, **_: object) -> Column:
    """A pool above was taken. Identical to ``msb_up`` on the wick basis, by construction — a
    liquidity sweep and a wick-basis structure break *are* the same geometry."""
    return _fresh_break(bars, k, "wick", up=True)


def _swept_low(bars: Bars, *, k: int, **_: object) -> Column:
    return _fresh_break(bars, k, "wick", up=False)


def _sweep_and_reclaim(bars: Bars, k: int, n: int, *, low_side: bool) -> Column:
    """**The Donlevey core.** Price takes the stops beyond a pool, then closes back inside it.

    The reclaim may land on the sweep bar itself — the classic long-wicked candle that pokes below
    support and settles back above it — or on any of the next ``n`` bars. It fires on the *reclaim*
    bar, not the sweep bar: until price comes back, a break below support is just a break below
    support, and treating the sweep bar as the signal would enter before the setup existed.
    """
    level = _last_swing_low(bars, k=k) if low_side else _last_swing_high(bars, k=k)
    probe = bars.low if low_side else bars.high
    out = _ops.empty_like(bars.close)
    active = np.nan
    deadline = -1
    for t in range(bars.close.size):
        if np.isnan(level[t]):
            continue
        out[t] = 0.0
        if (probe[t] < level[t]) if low_side else (probe[t] > level[t]):
            active, deadline = float(level[t]), t + n
        if np.isnan(active) or t > deadline:
            continue
        reclaimed = bars.close[t] > active if low_side else bars.close[t] < active
        if reclaimed:
            out[t] = 1.0
            active = np.nan
    return out


def _sweep_and_reclaim_low(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _sweep_and_reclaim(bars, k, n, low_side=True)


def _sweep_and_reclaim_high(bars: Bars, *, k: int, n: int, **_: object) -> Column:
    return _sweep_and_reclaim(bars, k, n, low_side=False)


def _stop_run_extent(bars: Bars, k: int, atr_period: int, *, low_side: bool) -> Column:
    """How far past the pool the most recent sweep reached, in ATR — carried forward.

    Carried rather than instantaneous because the reclaim it qualifies usually lands a bar or two
    after the sweep, and a column that was ``nan`` by then could not be used to filter it. In ATR
    because a 3-rupee overshoot means something different on a ₹200 stock and a ₹4,000 one.
    """
    level = _last_swing_low(bars, k=k) if low_side else _last_swing_high(bars, k=k)
    probe = bars.low if low_side else bars.high
    beyond = (probe < level) if low_side else (probe > level)
    depth = (level - probe) if low_side else (probe - level)
    extent = _ops.safe_divide(depth, _ops.atr(bars.high, bars.low, bars.close, atr_period))
    return _ops.forward_fill(np.where(beyond, extent, np.nan))


def _stop_run_extent_low(bars: Bars, *, k: int, atr_period: int, **_: object) -> Column:
    return _stop_run_extent(bars, k, atr_period, low_side=True)


def _stop_run_extent_high(bars: Bars, *, k: int, atr_period: int, **_: object) -> Column:
    return _stop_run_extent(bars, k, atr_period, low_side=False)


def _equal_swings(bars: Bars, k: int, tol: float, atr_period: int, *, peak: bool) -> Column:
    """State event: the two most recent confirmed swings on this side sit within ``tol`` ATR.

    A denser stop cluster than a single swing, which is what makes it worth sweeping. Tolerance is
    in ATR for the same reason as ``stop_run_extent``.
    """
    values = _swing_highs(bars, k) if peak else _swing_lows(bars, k)
    prior = _ops.previous_value(values)
    atr = _ops.atr(bars.high, bars.low, bars.close, atr_period)
    out = _ops.empty_like(bars.close)
    at = ~np.isnan(prior) & ~np.isnan(atr)
    out[at] = (np.abs(values[at] - prior[at]) <= tol * atr[at]).astype(np.float64)
    return _ops.forward_fill(out)


def _equal_highs(bars: Bars, *, k: int, tol: float, atr_period: int, **_: object) -> Column:
    return _equal_swings(bars, k, tol, atr_period, peak=True)


def _equal_lows(bars: Bars, *, k: int, tol: float, atr_period: int, **_: object) -> Column:
    return _equal_swings(bars, k, tol, atr_period, peak=False)


def _refuses(name: str, reason: str) -> object:
    def compute(bars: Bars, **_: object) -> Column:
        raise DslError(f"{name} cannot be computed: {reason}")

    return compute


# The intra-library API. `zones` builds order blocks on top of structure breaks and measures
# premium/discount against the structural range; `classics` measures Minervini's contracting
# pullbacks between confirmed swings and re-exports the sweep as Wyckoff's spring. Exporting the
# *same function objects* rather than reimplementing either means a zone, a classic and a structure
# word can never disagree about where the last swing was or when the break happened.
#
# The two *parameter* declarations are exported for the same reason one notch further down: `k` and
# `basis` mean the same thing in all three modules, and a second copy of `k`'s upper bound written
# as a bare number is precisely how two words that must agree stop agreeing.
last_swing_high = _last_swing_high
last_swing_low = _last_swing_low
msb_up = _msb_up
msb_down = _msb_down
swing_highs = _swing_highs
swing_lows = _swing_lows
sweep_and_reclaim_low = _sweep_and_reclaim_low
sweep_and_reclaim_high = _sweep_and_reclaim_high
swing_param = _swing_param
basis_param = _basis_param
refuses = _refuses


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §6.1-6.3."""
    k = _swing_param()
    basis = _basis_param()
    tol = FloatParam("tol", 0.01, 5.0, default=0.25)
    atr_period = IntParam("atr_period", 2, 200, default=14)
    return (
        # ---- swings ----
        Primitive(
            "swing_high",
            Kind.EVENT,
            "A swing high was confirmed on this bar (it occurred k bars ago).",
            _swing_high_event,
            (k,),
        ),
        Primitive(
            "swing_low",
            Kind.EVENT,
            "A swing low was confirmed on this bar (it occurred k bars ago).",
            _swing_low_event,
            (k,),
        ),
        Primitive(
            "last_swing_high",
            Kind.LEVEL,
            "Price of the most recently confirmed swing high.",
            _last_swing_high,
            (k,),
        ),
        Primitive(
            "last_swing_low",
            Kind.LEVEL,
            "Price of the most recently confirmed swing low.",
            _last_swing_low,
            (k,),
        ),
        Primitive(
            "prior_swing_high",
            Kind.LEVEL,
            "The confirmed swing high before the last one.",
            _prior_swing_high,
            (k,),
        ),
        Primitive(
            "prior_swing_low",
            Kind.LEVEL,
            "The confirmed swing low before the last one.",
            _prior_swing_low,
            (k,),
        ),
        Primitive(
            "swing_sequence",
            Kind.SERIES,
            "HH=2, HL=1, equal=0, LH=-1, LL=-2 for the latest confirmed swing.",
            _swing_sequence,
            (k,),
        ),
        # ---- structure ----
        Primitive(
            "market_structure",
            Kind.SERIES,
            "+1 bullish (HH+HL), -1 bearish (LH+LL), 0 ranging.",
            _market_structure,
            (k,),
        ),
        Primitive(
            "structure_bullish",
            Kind.EVENT,
            "State: higher high and higher low both stand.",
            _structure_bullish,
            (k,),
        ),
        Primitive(
            "structure_bearish",
            Kind.EVENT,
            "State: lower high and lower low both stand.",
            _structure_bearish,
            (k,),
        ),
        Primitive(
            "structure_ranging",
            Kind.EVENT,
            "State: structure is neither cleanly bullish nor bearish.",
            _structure_ranging,
            (k,),
        ),
        Primitive(
            "higher_highs",
            Kind.EVENT,
            "State: the last n confirmed swing highs rose in sequence.",
            _higher_highs,
            (k, _bar_count("n", 2)),
        ),
        Primitive(
            "higher_lows",
            Kind.EVENT,
            "State: the last n confirmed swing lows rose in sequence.",
            _higher_lows,
            (k, _bar_count("n", 2)),
        ),
        Primitive(
            "lower_highs",
            Kind.EVENT,
            "State: the last n confirmed swing highs fell in sequence.",
            _lower_highs,
            (k, _bar_count("n", 2)),
        ),
        Primitive(
            "lower_lows",
            Kind.EVENT,
            "State: the last n confirmed swing lows fell in sequence.",
            _lower_lows,
            (k, _bar_count("n", 2)),
        ),
        # ---- breaks ----
        Primitive(
            "msb_up",
            Kind.EVENT,
            "Fresh break above the last confirmed swing high, in any structure.",
            _msb_up,
            (k, basis),
        ),
        Primitive(
            "msb_down",
            Kind.EVENT,
            "Fresh break below the last confirmed swing low, in any structure.",
            _msb_down,
            (k, basis),
        ),
        Primitive(
            "bos_up",
            Kind.EVENT,
            "Break of Structure up — a break while structure is already bullish.",
            _bos_up,
            (k, basis),
        ),
        Primitive(
            "bos_down",
            Kind.EVENT,
            "Break of Structure down — a break while structure is already bearish.",
            _bos_down,
            (k, basis),
        ),
        Primitive(
            "choch_up",
            Kind.EVENT,
            "Change of Character up — the first break against bearish structure.",
            _choch_up,
            (k, basis),
        ),
        Primitive(
            "choch_down",
            Kind.EVENT,
            "Change of Character down — the first break against bullish structure.",
            _choch_down,
            (k, basis),
        ),
        Primitive(
            "failed_break_up",
            Kind.EVENT,
            "A break up given back within n bars.",
            _failed_break_up,
            (k, _bar_count("n", 3), basis),
        ),
        Primitive(
            "failed_break_down",
            Kind.EVENT,
            "A break down given back within n bars.",
            _failed_break_down,
            (k, _bar_count("n", 3), basis),
        ),
        # ---- liquidity ----
        Primitive(
            "liquidity_pool_high",
            Kind.LEVEL,
            "Where stops rest above — the same price as last_swing_high, in SMC vocabulary.",
            _last_swing_high,
            (k,),
        ),
        Primitive(
            "liquidity_pool_low",
            Kind.LEVEL,
            "Where stops rest below — the same price as last_swing_low, in SMC vocabulary.",
            _last_swing_low,
            (k,),
        ),
        Primitive(
            "equal_highs",
            Kind.EVENT,
            "State: the last two confirmed swing highs sit within tol ATR of each other.",
            _equal_highs,
            (k, tol, atr_period),
        ),
        Primitive(
            "equal_lows",
            Kind.EVENT,
            "State: the last two confirmed swing lows sit within tol ATR of each other.",
            _equal_lows,
            (k, tol, atr_period),
        ),
        Primitive(
            "swept_high",
            Kind.EVENT,
            "Price traded through the pool above.",
            _swept_high,
            (k,),
        ),
        Primitive(
            "swept_low",
            Kind.EVENT,
            "Price traded through the pool below.",
            _swept_low,
            (k,),
        ),
        Primitive(
            "sweep_and_reclaim_low",
            Kind.EVENT,
            "Swept the pool below and closed back above it within n bars.",
            _sweep_and_reclaim_low,
            (k, _bar_count("n", 3)),
        ),
        Primitive(
            "sweep_and_reclaim_high",
            Kind.EVENT,
            "Swept the pool above and closed back below it within n bars.",
            _sweep_and_reclaim_high,
            (k, _bar_count("n", 3)),
        ),
        Primitive(
            "stop_run_extent_low",
            Kind.SERIES,
            "How far the last sweep below reached, in ATR.",
            _stop_run_extent_low,
            (k, atr_period),
        ),
        Primitive(
            "stop_run_extent_high",
            Kind.SERIES,
            "How far the last sweep above reached, in ATR.",
            _stop_run_extent_high,
            (k, atr_period),
        ),
        # ---- INTRADAY: defined so they exist in the grammar, refusing on daily bars ----
        Primitive(
            "inducement_high",
            Kind.EVENT,
            "Engineered minor high baited before the real move. Needs intraday bars.",
            _refuses(  # type: ignore[arg-type]
                "inducement_high",
                "the strict sense needs the intra-session pullback, not a daily bar",
            ),
            intraday_only=True,
        ),
        Primitive(
            "inducement_low",
            Kind.EVENT,
            "Engineered minor low baited before the real move. Needs intraday bars.",
            _refuses(  # type: ignore[arg-type]
                "inducement_low",
                "the strict sense needs the intra-session pullback, not a daily bar",
            ),
            intraday_only=True,
        ),
    )
