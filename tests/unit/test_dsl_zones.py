"""Hand-worked fixtures for the zone and classic vocabulary — catalogue §6.4-6.5, §7 (task 1.4b).

The look-ahead sweep in ``test_dsl_library.py`` is a net, not a proof: it only sees a disagreement
near a truncation point, and it says nothing about whether a word computes the *right* thing. Every
test here names the exact bar a value is allowed to appear on and the exact number it must be, both
derived by hand in the comment above the fixture. Two classes of bug are the target:

* **A zone reported before it could be known.** An order block is the candle *before* an impulse,
  so it cannot be drawn until the impulse happens; a Darvas box is not a box until the ceiling has
  survived the confirmation bars. Both are the confirmation-lag bug wearing different clothes, and
  both would flatter a backtest by handing it a level days early.
* **A zone still reported after it died.** A gap price has traded through, or a block price has
  closed beyond, must stop being reported. The grammar has no ``not`` operator, so if a dead zone
  kept being reported there would be no way to say "the gap that is still open".
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.strategy.dsl import Bars, Call, evaluate
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    import numpy.typing as npt


def _bars(
    high: list[float],
    low: list[float],
    close: list[float],
    open_: list[float] | None = None,
    volume: list[float] | None = None,
    start: str = "2024-01-01",
) -> Bars:
    size = len(close)
    return Bars(
        ts=np.arange(np.datetime64(start), np.datetime64(start) + size).astype("datetime64[ns]"),
        open=np.array(close if open_ is None else open_, dtype=np.float64),
        high=np.array(high, dtype=np.float64),
        low=np.array(low, dtype=np.float64),
        close=np.array(close, dtype=np.float64),
        volume=np.array([1000.0] * size if volume is None else volume, dtype=np.float64),
    )


def _compute(name: str, bars: Bars, **params: object) -> npt.NDArray[np.float64]:
    registry = default_registry()
    primitive = registry.get(name)
    literals: dict[str, int | float | str] = {}
    for spec in primitive.params:
        literals[spec.name] = params.get(spec.name, getattr(spec, "default", None))  # type: ignore[assignment]
        assert literals[spec.name] is not None, f"{name}.{spec.name} needs a value in this test"
    return evaluate(
        Call(primitive=name, kind=primitive.kind, literals=literals, nested={}), bars, registry
    )


# --------------------------------------------------------------------------------------
# Fair value gaps
# --------------------------------------------------------------------------------------
#
# bar:      0     1     2     3     4
# high:    10    11    15    16    14
# low:      9    10    12    11   9.5
#
# The bullish gap is the three-bar pattern high[0] < low[2]: 10 < 12, so nothing traded between
# 10 and 12 across bars 0-2. It is a fact about bar 2 and knowable on bar 2 — never on bar 1.
#   band = [10, 12], born on bar 2.
#   bar 3: low 11 is inside the band but has not reached the far edge (10) — a partial retrace
#          leaves the gap live, which is the reading that makes it usable as an entry zone.
#   bar 4: low 9.5 <= 10 — traded clean through. The gap is filled and stops existing.
GAP = {
    "high": [10.0, 11.0, 15.0, 16.0, 14.0],
    "low": [9.0, 10.0, 12.0, 11.0, 9.5],
    "close": [9.5, 10.5, 14.0, 12.0, 10.0],
}


def test_a_fair_value_gap_is_not_reported_before_its_third_bar() -> None:
    top = _compute("fvg_up_top", _bars(**GAP), max_age=20)
    assert np.isnan(top[0]) and np.isnan(top[1])
    assert top[2] == pytest.approx(12.0)


def test_a_fair_value_gap_survives_a_partial_retrace() -> None:
    bars = _bars(**GAP)
    top = _compute("fvg_up_top", bars, max_age=20)
    bottom = _compute("fvg_up_bottom", bars, max_age=20)
    assert top[3] == pytest.approx(12.0)
    assert bottom[3] == pytest.approx(10.0)


def test_a_filled_gap_stops_being_reported_on_the_bar_it_fills() -> None:
    """The `intermittent` case: this ``nan`` means "no gap here now", not "not knowable yet"."""
    bars = _bars(**GAP)
    assert _compute("fvg_up_filled", bars, max_age=20)[4] == pytest.approx(1.0)
    assert np.isnan(_compute("fvg_up_top", bars, max_age=20)[4])


def test_an_expired_gap_stops_being_reported() -> None:
    """A gap from four years ago is not a level anyone is trading — `max_age` is load-bearing."""
    padded = {key: [*values[:4], *([values[3]] * 30)] for key, values in GAP.items()}
    top = _compute("fvg_up_top", _bars(**padded), max_age=5)
    assert top[3] == pytest.approx(12.0)
    assert np.isnan(top[10])


# --------------------------------------------------------------------------------------
# Order blocks and breakers
# --------------------------------------------------------------------------------------
#
# k=1, basis=close, search=5.
#
# bar:      0      1      2      3      4      5      6      7
# open:   10.0   10.0   11.0   10.8   10.2   10.4   11.0   12.0
# high:   10.5   11.0  [11.2]  11.0   10.6   11.6   12.2   12.2
# low:     9.5    9.8   10.6   10.0  [ 9.8]  10.3   11.0    9.5
# close:  10.0   10.8   11.0   10.2   10.4   11.5   12.0    9.8
#
#   swing high at bar 2 (11.2 beats 11.0 either side) -> confirmable on bar 3
#   swing low  at bar 4 ( 9.8 beats 10.0 and 10.3)    -> confirmable on bar 5
#   msb_up: close first exceeds the confirmed 11.2 on bar 5 (11.5). Bar 6 is still beyond it but
#           is not a *fresh* break, so it does not fire again.
#   the block is drawn on the last *down* candle before the impulse, searching back from bar 5:
#           bar 4 closed up (10.4 > 10.2), bar 3 closed down (10.2 < 10.8) -> bar 3.
#           band = [low 10.0, high 11.0].
#   bar 7 closes at 9.8, below 10.0: the block is invalidated and flips to a breaker.
BLOCK = {
    "open": [10.0, 10.0, 11.0, 10.8, 10.2, 10.4, 11.0, 12.0],
    "high": [10.5, 11.0, 11.2, 11.0, 10.6, 11.6, 12.2, 12.2],
    "low": [9.5, 9.8, 10.6, 10.0, 9.8, 10.3, 11.0, 9.5],
    "close": [10.0, 10.8, 11.0, 10.2, 10.4, 11.5, 12.0, 9.8],
}


def _block_bars() -> Bars:
    return _bars(BLOCK["high"], BLOCK["low"], BLOCK["close"], open_=BLOCK["open"])


def test_an_order_block_appears_only_on_the_bar_that_broke_structure() -> None:
    """The candle is bar 3; it is not identifiable as a block until the bar-5 impulse."""
    bars = _block_bars()
    top = _compute("order_block_bull_top", bars, k=1, basis="close", search=5)
    bottom = _compute("order_block_bull_bottom", bars, k=1, basis="close", search=5)
    assert np.isnan(top[:5]).all(), "a block reported before its impulse is look-ahead"
    assert top[5] == pytest.approx(11.0)
    assert bottom[5] == pytest.approx(10.0)
    assert top[6] == pytest.approx(11.0)  # still live while price holds above it


def test_an_invalidated_block_stops_being_reported_and_becomes_a_breaker() -> None:
    bars = _block_bars()
    top = _compute("order_block_bull_top", bars, k=1, basis="close", search=5)
    breaker_top = _compute("breaker_bear_top", bars, k=1, basis="close", search=5)
    assert np.isnan(top[7]), "a block price has closed through is not a block"
    assert np.isnan(breaker_top[6]), "nothing has failed yet, so there is no breaker"
    assert breaker_top[7] == pytest.approx(11.0)


def test_a_breaker_dies_when_price_closes_back_through_it() -> None:
    """A failed bullish block is resistance at 11.0; a close above 11.0 is not resistance holding.

    Left un-invalidated, the first failed block of the series would still be reported as "live
    resistance" on the last bar of a fifteen-year backtest, and a strategy would find one on every
    bar forever — the same objection ``max_age`` exists to answer for gaps.
    """
    extended = {key: [*values, 12.5] for key, values in BLOCK.items()}
    bars = _bars(extended["high"], extended["low"], extended["close"], open_=extended["open"])
    breaker_top = _compute("breaker_bear_top", bars, k=1, basis="close", search=5)
    assert breaker_top[7] == pytest.approx(11.0)
    assert np.isnan(breaker_top[8]), "close 12.5 is above the flipped band — it has been taken out"


def test_premium_and_discount_are_unknown_until_both_swings_exist() -> None:
    """Equilibrium is the midpoint of the last confirmed leg: (9.8 + 11.2) / 2 = 10.5."""
    bars = _block_bars()
    mid = _compute("equilibrium", bars, k=1)
    assert np.isnan(mid[4]), "the swing low only confirms on bar 5"
    assert mid[5] == pytest.approx(10.5)
    assert _compute("in_premium", bars, k=1)[5] == pytest.approx(1.0)  # close 11.5 > 10.5
    assert _compute("in_discount", bars, k=1)[5] == pytest.approx(0.0)


# --------------------------------------------------------------------------------------
# Higher-timeframe levels — causal or absent
# --------------------------------------------------------------------------------------
#
# Fifteen weekday bars from Monday 2024-01-01, so weeks are bars 0-4, 5-9 and 10-14. The point of
# the fixture is what is *missing*: during week B the level words may report week A's completed
# high, and must never report week B's own — a weekly high that included the unfinished current
# week would be the swing-confirmation bug keeping time instead of price.


def _weekday_bars() -> Bars:
    days = np.array(
        [np.datetime64("2024-01-01") + offset for offset in range(21)], dtype="datetime64[D]"
    )
    weekdays = days[np.isin(((days.astype(int) + 3) % 7), range(5))][:15]
    close = np.arange(15, dtype=np.float64) + 100.0
    return Bars(
        ts=weekdays.astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(15, 1000.0),
    )


def test_the_previous_week_high_never_includes_the_current_week() -> None:
    bars = _weekday_bars()
    prev = _compute("prev_week_high", bars)
    assert np.isnan(prev[:5]).all(), "there is no completed week yet"
    week_a_high = float(bars.high[:5].max())
    assert prev[5] == pytest.approx(week_a_high)
    assert prev[9] == pytest.approx(week_a_high), "week B's own bars must not leak in"
    assert prev[10] == pytest.approx(float(bars.high[5:10].max()))


def test_the_weekly_open_is_the_current_weeks_first_bar() -> None:
    bars = _weekday_bars()
    weekly = _compute("weekly_open", bars)
    assert weekly[0] == pytest.approx(float(bars.open[0]))
    assert weekly[4] == pytest.approx(float(bars.open[0]))
    assert weekly[5] == pytest.approx(float(bars.open[5]))


def test_htf_bias_needs_two_completed_periods() -> None:
    bars = _weekday_bars()
    bias = _compute("htf_bias", bars, period="week")
    assert np.isnan(bias[:10]).all(), "one completed week is not enough to compare two"
    assert bias[10] == pytest.approx(1.0)  # week B closed above week A on a rising series


# --------------------------------------------------------------------------------------
# The classic operators
# --------------------------------------------------------------------------------------

# The 1.4a fixture: closes step by 1, then jump 13 -> 20. Highs are close+1, lows close-1.
CLOSES = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 20.0, 19.0]


def _step_bars(volume: list[float] | None = None) -> Bars:
    close = np.array(CLOSES, dtype=np.float64)
    return _bars(
        high=list(close + 1.0),
        low=list(close - 1.0),
        close=list(close),
        volume=volume,
    )


def test_a_donchian_breakout_fires_once_on_the_bar_that_clears_the_channel() -> None:
    """donchian_upper(3) at bar 8 is max(high[5..7]) = 14. Close 20 clears it; bar 9's 19 does not
    clear the new channel (max(high[6..8]) = 21), so nothing fires twice."""
    fires = _compute("donchian_breakout_up", _step_bars(), n=3, basis="close")
    assert np.isnan(fires[:3]).all()
    assert fires[8] == pytest.approx(1.0)
    assert float(np.nansum(fires)) == pytest.approx(1.0), "a breakout is one event, not a state"


def test_a_pivotal_point_needs_the_volume_and_not_only_the_breakout() -> None:
    """Same bars, same breakout bar — the only difference is the tape.

    This is the test that would fail if the volume gate were wired up but never actually binding,
    which is how a "volume-confirmed" strategy ends up being a plain breakout strategy.
    """
    flat = _compute("pivotal_point_up", _step_bars(), n=3, basis="close", vol_n=3, vol_mult=1.5)
    assert float(np.nansum(flat)) == pytest.approx(0.0), "constant volume confirms nothing"

    spiked = [1000.0] * 10
    spiked[8] = 5000.0
    loud = _compute(
        "pivotal_point_up", _step_bars(spiked), n=3, basis="close", vol_n=3, vol_mult=1.5
    )
    assert loud[8] == pytest.approx(1.0)


def test_effort_vs_result_is_one_when_volume_and_range_are_both_ordinary() -> None:
    """Every bar in this fixture has range 2.0 and volume 1000, so effort and result cancel."""
    ratio = _compute("effort_vs_result", _step_bars(), n=3)
    assert ratio[5] == pytest.approx(1.0)

    spiked = [1000.0] * 10
    spiked[8] = 3000.0
    loud = _compute("effort_vs_result", _step_bars(spiked), n=3)
    assert loud[8] == pytest.approx(3.0), "3x the volume, unchanged range -> 3x the effort"


def test_the_wyckoff_names_are_the_same_function_object_as_the_smc_ones() -> None:
    """A spring *is* a liquidity sweep. Two implementations would drift, and a strategy using both
    would look to the Validation gate like it had two independent confirmations of one event."""
    registry = default_registry()
    assert registry.get("spring").compute is registry.get("sweep_and_reclaim_low").compute
    assert registry.get("upthrust").compute is registry.get("sweep_and_reclaim_high").compute


# --------------------------------------------------------------------------------------
# Weinstein stages
# --------------------------------------------------------------------------------------


def test_the_four_weinstein_stages_partition_every_knowable_bar() -> None:
    """Exhaustive and mutually exclusive by construction — the property worth pinning, because a
    fifth "none of the above" state would make the stage filter silently drop bars."""
    rng = np.random.default_rng(1954)
    close = np.cumsum(rng.normal(0.0, 1.0, 300)) + 500.0
    bars = _bars(list(close + 1.0), list(close - 1.0), list(close))
    params = {"n": 30, "slope_n": 5, "flat": 0.01}
    stage = _compute("stage", bars, **params)
    flags = np.vstack(
        [
            _compute(name, bars, **params)
            for name in ("stage_basing", "stage_advancing", "stage_topping", "stage_declining")
        ]
    )
    known = ~np.isnan(stage)
    assert known.any()
    assert np.array_equal(np.isnan(flags).any(axis=0), ~known)
    np.testing.assert_array_equal(flags[:, known].sum(axis=0), np.ones(int(known.sum())))


def test_a_steadily_rising_series_is_stage_two() -> None:
    close = np.linspace(100.0, 200.0, 120)
    bars = _bars(list(close + 1.0), list(close - 1.0), list(close))
    stage = _compute("stage", bars, n=30, slope_n=5, flat=0.01)
    assert stage[-1] == pytest.approx(2.0)
    assert _compute("stage_advancing", bars, n=30, slope_n=5, flat=0.01)[-1] == pytest.approx(1.0)


def test_a_steadily_falling_series_is_stage_four() -> None:
    close = np.linspace(200.0, 100.0, 120)
    bars = _bars(list(close + 1.0), list(close - 1.0), list(close))
    assert _compute("stage", bars, n=30, slope_n=5, flat=0.01)[-1] == pytest.approx(4.0)


# --------------------------------------------------------------------------------------
# Darvas box
# --------------------------------------------------------------------------------------
#
# n=3, confirm=2.  prior_high[t] = max(high[t-3 .. t-1]) — the current bar excluded.
#
# bar:      0     1      2      3      4      5      6      7
# high:  10.0  10.5   11.0  [13.0]  12.0   12.5   12.8   14.0
# low:    9.0   9.5   10.0   11.0  [11.2] [11.5]  11.8   12.5
# close:  9.8  10.2   10.8   12.8   11.5   12.0   12.4   13.8
#
#   bar 3: high 13.0 clears prior_high 11.0 -> candidate ceiling 13.0
#   bar 4: 12.0 does not exceed it (1 of 2 confirmation bars)
#   bar 5: 12.5 does not exceed it -> the box is real from *here*, never from bar 3.
#          floor = min(low[4], low[5]) = 11.2
#   bar 7: close 13.8 clears 13.0 -> breakout, and the box stops being reported
DARVAS = {
    "high": [10.0, 10.5, 11.0, 13.0, 12.0, 12.5, 12.8, 14.0],
    "low": [9.0, 9.5, 10.0, 11.0, 11.2, 11.5, 11.8, 12.5],
    "close": [9.8, 10.2, 10.8, 12.8, 11.5, 12.0, 12.4, 13.8],
}


def test_a_darvas_box_is_not_a_box_until_its_ceiling_has_held() -> None:
    bars = _bars(**DARVAS)
    top = _compute("darvas_box_top", bars, n=3, confirm=2)
    bottom = _compute("darvas_box_bottom", bars, n=3, confirm=2)
    assert np.isnan(top[:5]).all(), "reporting the box from bar 3 would be look-ahead"
    assert top[5] == pytest.approx(13.0)
    assert bottom[5] == pytest.approx(11.2)
    assert top[6] == pytest.approx(13.0)


def test_a_darvas_breakout_ends_the_box() -> None:
    bars = _bars(**DARVAS)
    assert _compute("darvas_breakout_up", bars, n=3, confirm=2)[7] == pytest.approx(1.0)
    assert np.isnan(_compute("darvas_box_top", bars, n=3, confirm=2)[7])


# --------------------------------------------------------------------------------------
# Minervini
# --------------------------------------------------------------------------------------
#
# A zigzag with three contracting pullbacks. high = low = close, so each turn is a clean pivot:
# a peak beats its neighbours on the high and a trough beats them on the low, never both.
#
# bar:     0     1     2     3     4     5     6     7
# close:  90  *100*  *80*  *100*  *90*  *100*  *95*  *100*   (starred = a confirmed pivot)
#
#   swing highs at bars 1, 3, 5 -> confirmable at 2, 4, 6   (k=1, so the lag is one bar)
#   swing lows  at bars 2, 4, 6 -> confirmable at 3, 5, 7
#   legs: (100 -> 80) = 20%, (100 -> 90) = 10%, (100 -> 95) = 5%, each confirmed at 3, 5, 7.
#   Three strictly shallower pullbacks are complete only on bar 7.
VCP_CLOSES = [90.0, 100.0, 80.0, 100.0, 90.0, 100.0, 95.0, 100.0]


def test_volatility_contraction_needs_the_full_sequence_of_shallower_pullbacks() -> None:
    bars = _bars(VCP_CLOSES, VCP_CLOSES, VCP_CLOSES)
    vcp = _compute("volatility_contraction", bars, k=1, legs=3)
    assert np.isnan(vcp[:3]).all(), "no leg has been measured yet"
    assert vcp[5] == pytest.approx(0.0), "two contracting legs are not three"
    assert vcp[7] == pytest.approx(1.0)


def test_volatility_contraction_rejects_a_widening_sequence() -> None:
    widening = [90.0, 100.0, 95.0, 100.0, 90.0, 100.0, 80.0, 100.0]
    vcp = _compute("volatility_contraction", _bars(widening, widening, widening), k=1, legs=3)
    assert vcp[7] == pytest.approx(0.0)


def test_pct_off_high_and_low_match_the_hand_computed_window() -> None:
    """n=3 at bar 8: highs are close+1 so max(high[6..8]) = 21 and min(low[6..8]) = 11."""
    bars = _step_bars()
    assert _compute("pct_off_high", bars, n=3)[8] == pytest.approx((21.0 - 20.0) / 21.0)
    assert _compute("pct_off_low", bars, n=3)[8] == pytest.approx((20.0 - 11.0) / 11.0)


def test_the_trend_template_holds_on_a_clean_uptrend_and_not_on_a_downtrend() -> None:
    rising = np.linspace(100.0, 300.0, 300)
    up = _bars(list(rising + 1.0), list(rising - 1.0), list(rising))
    params = {"fast": 30, "slow": 60, "slope_n": 10, "n": 120, "above_low": 0.25, "off_high": 0.25}
    assert _compute("trend_template", up, **params)[-1] == pytest.approx(1.0)

    falling = rising[::-1].copy()
    down = _bars(list(falling + 1.0), list(falling - 1.0), list(falling))
    assert _compute("trend_template", down, **params)[-1] == pytest.approx(0.0)
