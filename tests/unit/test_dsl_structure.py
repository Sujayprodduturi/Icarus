"""Tests for market structure, breaks and liquidity — catalogue §6.1-6.3 (task 1.4b).

Every fixture here is worked out by hand in the docstring beside it, because the thing being tested
is *when* a value is allowed to appear, and that cannot be checked against a second implementation
copied from the same misunderstanding.

The load-bearing test is :func:`test_a_swing_is_invisible_until_its_confirmation_bar`. The peak in
``PEAK_AT_3`` sits on bar 3 and every word that depends on it must be ``nan`` on bars 3 and 4 —
because on bar 3 the two bars that make it a peak had not happened yet. Almost every charting
library reports it on bar 3; in a backtest that is a two-day head start on a signal nobody could
have taken, and it propagates into every break, pool and zone defined in terms of swings.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import pytest

from icarus.strategy.dsl import Bars, Call, DslError, Timeframe, evaluate, parse_strategy
from icarus.strategy.library import default_registry

# --------------------------------------------------------------------------------------
# Fixtures, worked out by hand
# --------------------------------------------------------------------------------------

# bar:      0     1     2     3     4     5     6     7     8     9    10    11
# high:    10    11    12  [15]    13    12    11    10    14  [16]    15    14
# low:      8     9    10    13    11    10     9   [8]    12    14    13    12
#
# With k=2 a bar is a swing when it is *strictly* beyond the two bars either side:
#   swing high bar 3  (15 > max(11,12) and > max(13,12))   -> confirmable on bar 5
#   swing high bar 9  (16 > max(10,14) and > max(15,14))   -> confirmable on bar 11
#   swing low  bar 7  ( 8 < min(10, 9) and <  min(12,14))  -> confirmable on bar 9
# Nothing else qualifies: bar 8's high of 14 loses to bar 9, bar 5's low of 10 loses to bar 7.
PEAK_AT_3 = {
    "high": [10.0, 11.0, 12.0, 15.0, 13.0, 12.0, 11.0, 10.0, 14.0, 16.0, 15.0, 14.0],
    "low": [8.0, 9.0, 10.0, 13.0, 11.0, 10.0, 9.0, 8.0, 12.0, 14.0, 13.0, 12.0],
    "close": [9.0, 10.0, 11.0, 14.0, 12.0, 11.0, 10.0, 9.0, 13.0, 15.0, 14.0, 13.0],
}

# bar:      0     1     2     3     4     5     6     7     8     9    10
# high:    12    13    14    12    11    13    14    15    14    13    14
# low:     10    11    12    10   [6]    11    12    13   [5]    11    12
# close:   11    12    13    11     7    12    13    14     9    12    13
#
# k=2 swing lows: bar 4 (6 < min(12,10) and < min(11,12)) -> confirmed bar 6, price 6.0
#                 bar 8 (5 < min(12,13) and < min(11,12)) -> confirmed bar 10, price 5.0
# So from bar 6 the pool below sits at 6.0. On bar 8 the low pierces it (5 < 6) and the close
# returns above it in the same bar (9 > 6) — the classic long-wicked sweep-and-reclaim candle.
SWEEP_AT_8 = {
    "high": [12.0, 13.0, 14.0, 12.0, 11.0, 13.0, 14.0, 15.0, 14.0, 13.0, 14.0],
    "low": [10.0, 11.0, 12.0, 10.0, 6.0, 11.0, 12.0, 13.0, 5.0, 11.0, 12.0],
    "close": [11.0, 12.0, 13.0, 11.0, 7.0, 12.0, 13.0, 14.0, 9.0, 12.0, 13.0],
}


def _bars(spec: dict[str, list[float]], **override: list[float]) -> Bars:
    columns = {**spec, **override}
    close = np.array(columns["close"], dtype=np.float64)
    return Bars(
        ts=np.arange(close.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=close.copy(),
        high=np.array(columns["high"], dtype=np.float64),
        low=np.array(columns["low"], dtype=np.float64),
        close=close,
        volume=np.full(close.size, 1000.0),
    )


def _value(name: str, bars: Bars, **params: object) -> npt.NDArray[np.float64]:
    registry = default_registry()
    primitive = registry.get(name)
    literals: dict[str, int | float | str] = {}
    for spec in primitive.params:
        literals[spec.name] = params.get(spec.name, getattr(spec, "default", None))  # type: ignore[assignment]
    call = Call(primitive=name, kind=primitive.kind, literals=literals, nested={})
    return evaluate(call, bars, registry)


# --------------------------------------------------------------------------------------
# Confirmation lag — the whole point of the module
# --------------------------------------------------------------------------------------


def test_a_swing_is_invisible_until_its_confirmation_bar() -> None:
    """The peak is on bar 3. Nothing may know about it before bar 5.

    Bars 3 and 4 are the ones that matter: on bar 3 the peak has just printed and on bar 4 one of
    its two right-hand neighbours is still missing. A word that has a value on either bar is
    reporting a peak that could not yet be distinguished from a step on the way up.
    """
    bars = _bars(PEAK_AT_3)
    for name in ("last_swing_high", "liquidity_pool_high", "prior_swing_high"):
        column = _value(name, bars, k=2)
        assert np.isnan(column[3]), f"{name} reported the peak on the bar it occurred"
        assert np.isnan(column[4]), f"{name} reported the peak one bar early"

    event = _value("swing_high", bars, k=2)
    assert np.all(np.isnan(event[:4])), "no swing is decidable before bar 2k"
    assert event[4] == 0.0  # bar 2 is judged here, and it is not a peak
    assert event[5] == 1.0  # bar 3's peak becomes confirmable exactly now
    assert event[11] == 1.0  # bar 9's peak, k bars later
    assert event[[6, 7, 8, 9, 10]].tolist() == [0.0] * 5


def test_the_confirmed_swing_price_is_the_peak_itself_not_the_confirmation_bar() -> None:
    """The lag moves *when* you learn it, not *what* you learn. The level is still bar 3's high."""
    bars = _bars(PEAK_AT_3)
    level = _value("last_swing_high", bars, k=2)
    assert level[5] == 15.0  # bar 3's high, learned on bar 5
    assert level[[6, 7, 8, 9, 10]].tolist() == [15.0] * 5  # carried until superseded
    assert level[11] == 16.0  # bar 9's high, learned on bar 11

    low = _value("last_swing_low", bars, k=2)
    assert np.all(np.isnan(low[:9]))
    assert low[[9, 10, 11]].tolist() == [8.0] * 3


def test_the_prior_swing_needs_two_swings_before_it_says_anything() -> None:
    bars = _bars(PEAK_AT_3)
    prior = _value("prior_swing_high", bars, k=2)
    assert np.all(np.isnan(prior[:11])), "one swing is not enough to have a previous one"
    assert prior[11] == 15.0


def test_structure_stays_unknown_until_all_four_swings_exist() -> None:
    """``PEAK_AT_3`` has two swing highs but only one swing low, so there is no HL/LL to read.

    Returning "ranging" here would be the tempting shortcut and it is wrong: ranging is a claim
    about structure, and we do not have enough structure to make any claim at all.
    """
    structure = _value("market_structure", _bars(PEAK_AT_3), k=2)
    assert np.all(np.isnan(structure))


def test_a_plateau_of_equal_highs_produces_no_swing() -> None:
    """Strict comparison on both sides. With ``>=`` every bar of a flat top is a swing, the "last
    swing high" jitters between identical prices, and the structural event count inflates."""
    flat = {"high": [10.0] * 9, "low": [8.0] * 9, "close": [9.0] * 9}
    assert not np.any(_value("swing_high", _bars(flat), k=2) == 1.0)
    assert not np.any(_value("swing_low", _bars(flat), k=2) == 1.0)


# --------------------------------------------------------------------------------------
# The Donlevey core — sweep and reclaim
# --------------------------------------------------------------------------------------


def test_a_sweep_reclaimed_on_the_same_bar_fires_on_that_bar() -> None:
    """Bar 8 pierces the 6.0 pool to 5.0 and closes back at 9.0. One candle, one signal."""
    fired = _value("sweep_and_reclaim_low", _bars(SWEEP_AT_8), k=2, n=3)
    assert np.all(np.isnan(fired[:6])), "no pool is known until bar 6"
    assert fired[[6, 7, 8, 9, 10]].tolist() == [0.0, 0.0, 1.0, 0.0, 0.0]


def test_a_sweep_reclaimed_later_fires_on_the_reclaim_bar_not_the_sweep_bar() -> None:
    """Close on bar 8 held *below* the pool, so bar 8 is not yet a setup — it is just a breakdown.

    Firing on the sweep bar would enter before the thing being traded had happened.
    """
    slow = _bars(SWEEP_AT_8, close=[11.0, 12.0, 13.0, 11.0, 7.0, 12.0, 13.0, 14.0, 5.5, 12.0, 13.0])
    fired = _value("sweep_and_reclaim_low", slow, k=2, n=3)
    assert fired[8] == 0.0
    assert fired[9] == 1.0


def test_a_reclaim_that_arrives_too_late_never_fires() -> None:
    """``n`` is a real deadline. Price came back on bar 10 — two bars after the sweep, with n=1."""
    late = _bars(SWEEP_AT_8, close=[11.0, 12.0, 13.0, 11.0, 7.0, 12.0, 13.0, 14.0, 5.5, 5.5, 13.0])
    assert not np.any(_value("sweep_and_reclaim_low", late, k=2, n=1) == 1.0)
    assert _value("sweep_and_reclaim_low", late, k=2, n=3)[10] == 1.0


def test_the_pool_being_taken_is_a_separate_word_from_the_setup() -> None:
    """``swept_low`` says the stops went; ``sweep_and_reclaim_low`` says they went and price came
    back. On this fixture they coincide, but the late-reclaim case above is where they part."""
    late = _bars(SWEEP_AT_8, close=[11.0, 12.0, 13.0, 11.0, 7.0, 12.0, 13.0, 14.0, 5.5, 5.5, 13.0])
    assert _value("swept_low", late, k=2)[8] == 1.0
    assert _value("sweep_and_reclaim_low", late, k=2, n=1)[8] == 0.0


def test_stop_run_extent_measures_the_overshoot_and_carries_it_to_the_reclaim() -> None:
    """The reclaim usually lands a bar or two after the sweep, so an instantaneous column could not
    be used to filter it. Depth is (6.0 - 5.0) = 1.0 rupee, expressed in ATR."""
    bars = _bars(SWEEP_AT_8)
    extent = _value("stop_run_extent_low", bars, k=2, atr_period=3)
    assert np.all(np.isnan(extent[:8])), "nothing has been swept yet"
    assert extent[8] > 0.0
    assert extent[9] == extent[8], "carried forward, not recomputed from a bar with no sweep"


# --------------------------------------------------------------------------------------
# Breaks — and the close-vs-wick decision
# --------------------------------------------------------------------------------------


def test_a_break_needs_the_close_by_default_and_the_wick_only_on_request() -> None:
    """Bar 9 reaches 16.0 through a 15.0 pool but *settles* at 15.0 — exactly equal, not beyond.

    On the wick basis that is a break; on the close basis it is not. The default is close because
    the loose reading is the one that flatters a backtest: price pokes through a level far more
    often than it settles beyond it, and every poke would become a signal a live trader watching
    the close would never have taken.
    """
    bars = _bars(PEAK_AT_3)
    assert _value("msb_up", bars, k=2, basis="wick")[9] == 1.0
    assert not np.any(_value("msb_up", bars, k=2, basis="close") == 1.0)


def test_a_break_fires_once_not_every_bar_it_stays_beyond_the_level() -> None:
    rising = {
        "high": [10.0, 11.0, 12.0, 15.0, 13.0, 12.0, 16.0, 17.0, 18.0, 19.0],
        "low": [8.0, 9.0, 10.0, 13.0, 11.0, 10.0, 14.0, 15.0, 16.0, 17.0],
        "close": [9.0, 10.0, 11.0, 14.0, 12.0, 11.0, 15.5, 16.5, 17.5, 18.5],
    }
    fired = _value("msb_up", _bars(rising), k=2, basis="close")
    assert fired[6] == 1.0, "first close above the 15.0 pool"
    assert fired[[7, 8, 9]].tolist() == [0.0, 0.0, 0.0], "still above is not a new break"


def test_bos_and_choch_partition_the_breaks_that_msb_reports() -> None:
    """The same geometry, named by the structure it happens in — so neither may invent a break the
    union does not see, and no single bar can be both a continuation and a first crack."""
    rng = np.random.default_rng(20260804)
    close = np.cumsum(rng.normal(0.0, 1.0, 300)) + 500.0
    bars = Bars(
        ts=np.arange(close.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(close.size, 1000.0),
    )
    msb = _value("msb_up", bars, k=3)
    bos = _value("bos_up", bars, k=3)
    choch = _value("choch_up", bars, k=3)
    structure = _value("market_structure", bars, k=3)

    assert np.any(bos == 1.0) and np.any(choch == 1.0), "fixture must exercise both"
    assert not np.any((bos == 1.0) & (choch == 1.0)), "a break cannot be both at once"
    assert np.all(msb[(bos == 1.0) | (choch == 1.0)] == 1.0), "neither may invent a break"
    assert np.all(structure[bos == 1.0] == 1.0), "a BOS only happens in bullish structure"
    assert np.all(structure[choch == 1.0] == -1.0), "a CHoCH only happens against the structure"


def test_a_failed_break_fires_on_the_bar_the_level_is_given_back() -> None:
    """Wyckoff's failed auction. Bar 6 closes above the 15.0 pool; bar 7 closes back below it."""
    reversal = {
        "high": [10.0, 11.0, 12.0, 15.0, 13.0, 12.0, 16.0, 15.5, 14.0, 13.0],
        "low": [8.0, 9.0, 10.0, 13.0, 11.0, 10.0, 14.0, 13.0, 12.0, 11.0],
        "close": [9.0, 10.0, 11.0, 14.0, 12.0, 11.0, 15.5, 14.0, 13.0, 12.0],
    }
    failed = _value("failed_break_up", _bars(reversal), k=2, n=3, basis="close")
    assert failed[6] == 0.0, "the break bar is not itself the failure"
    assert failed[7] == 1.0
    assert failed[[8, 9]].tolist() == [0.0, 0.0], "it fires once, not for the rest of the series"


# --------------------------------------------------------------------------------------
# One geometry, one implementation
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [("liquidity_pool_high", "last_swing_high"), ("liquidity_pool_low", "last_swing_low")],
)
def test_an_alias_shares_the_function_object_it_renames(alias: str, canonical: str) -> None:
    """Not "produces the same numbers" — *is* the same function.

    Two implementations of one geometry drift apart, and a strategy using both then looks like it
    has two independent confirmations of a single signal. The Validation gate would credit that as
    diversification.
    """
    registry = default_registry()
    assert registry.get(alias).compute is registry.get(canonical).compute


# --------------------------------------------------------------------------------------
# Refusals
# --------------------------------------------------------------------------------------


def test_inducement_refuses_on_daily_bars() -> None:
    """Donlevey's strict inducement is an intra-session pullback. A daily bar cannot show one, and
    a degenerate daily version would be a different concept wearing the same name."""
    strategy = """
    name: inducement-on-dailies
    version: 1
    timeframe: 1d
    universe: nifty500
    entry:
      inducement_low: {}
    exit:
      - stop_loss_atr: {atr_mult: 2.0}
    sizing: {risk_r: 0.005}
    """
    with pytest.raises(DslError, match="defined only on intraday bars"):
        parse_strategy(strategy, registry=default_registry(), max_risk_r=0.005)


def test_the_intraday_backstop_raises_if_evaluation_is_ever_reached() -> None:
    registry = default_registry()
    call = Call(primitive="inducement_low", kind=registry.get("inducement_low").kind)
    with pytest.raises(DslError, match="cannot be computed"):
        evaluate(call, _bars(PEAK_AT_3), registry)


# --------------------------------------------------------------------------------------
# The strategy this task exists for
# --------------------------------------------------------------------------------------


def test_the_distilled_donlevey_sweep_strategy_parses_and_evaluates() -> None:
    """The acceptance criterion for 1.4b: the operator's actual method, expressible at last.

    In words — only take longs when structure is bullish, only after price has run the stops below
    a pool and closed back above it, and only when the run was deep enough to have been a genuine
    sweep rather than a slow grind through.
    """
    strategy = """
    name: donlevey-sweep-distilled
    version: 1
    timeframe: 1d
    universe: nifty500
    entry:
      all:
        - structure_bullish: {k: 3}
        - sweep_and_reclaim_low: {k: 3, n: 3}
        - above: {a: {stop_run_extent_low: {k: 3, atr_period: 14}}, b: {close: {}}}
    exit:
      - stop_loss_atr: {atr_mult: 1.5, atr_period: 14}
      - take_profit_r: {r_multiple: 3.0}
    sizing: {risk_r: 0.005}
    """
    registry = default_registry()
    candidate = parse_strategy(strategy, registry=registry, max_risk_r=0.005)
    assert candidate.timeframe is Timeframe.DAILY
    assert "sweep_and_reclaim_low" in candidate.primitives_used()

    rng = np.random.default_rng(20260804)
    close = np.cumsum(rng.normal(0.0, 1.0, 200)) + 500.0
    bars = Bars(
        ts=np.arange(close.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(close.size, 1000.0),
    )
    signal = evaluate(candidate.entry, bars, registry)
    assert signal.shape == close.shape
    assert set(np.unique(signal[~np.isnan(signal)])) <= {0.0, 1.0}
