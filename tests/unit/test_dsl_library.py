"""Tests for the primitive computations — catalogue §2-5 (task 1.4a).

Three kinds of check, in descending order of how much they'd cost us to get wrong:

* **Look-ahead.** Every primitive here must be computable from bars ``0..t`` alone. The decisive
  test is :func:`test_no_primitive_sees_the_future`, which computes each word over a full series
  and again over truncated prefixes and demands the overlapping values match exactly. A primitive
  that peeks changes its own past when the future is removed — nothing else in this file would
  catch that, and a backtest built on it would look excellent and be worthless.
* **Warm-up honesty.** A 50-bar average has no value on bar 3. It must be ``nan``, not a
  part-window average and not a back-filled guess.
* **Arithmetic.** ATR and SMA are pinned to values worked out by hand below. RSI is checked against
  an independent second implementation written straight from Wilder's definition, because a
  formula copied twice from the same misunderstanding agrees with itself.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.strategy.dsl import (
    Bars,
    Call,
    ChoiceParam,
    DslError,
    FloatParam,
    IntParam,
    Kind,
    SeriesParam,
    evaluate,
)
from icarus.strategy.library import _ops, default_registry

if TYPE_CHECKING:
    import numpy.typing as npt

# A deliberately simple series: closes step by 1, so the bar range is always 2.0 and every true
# range is 2.0 — EXCEPT the jump from 13 to 20, which opens a gap.
CLOSES = [10.0, 11.0, 12.0, 11.0, 10.0, 11.0, 12.0, 13.0, 20.0, 19.0]


def _bars(closes: list[float] | None = None) -> Bars:
    close = np.array(CLOSES if closes is None else closes, dtype=np.float64)
    return Bars(
        ts=np.arange(close.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(close.size, 1000.0),
    )


def _bodied_bars(closes: list[float]) -> Bars:
    """Like :func:`_bars` but with a real candle body — ``open`` is the previous close.

    The hand-worked fixtures above deliberately set ``open == close``, which is fine for an average
    or an oscillator but leaves every *body*-dependent word (order blocks, mitigation blocks,
    imbalance ratio) computing on zero-height candles and returning all-``nan``. An all-``nan``
    column passes the look-ahead sweep trivially, so those words would have been listed as covered
    while never actually being exercised. This builder is what the sweep runs on.
    """
    close = np.array(closes, dtype=np.float64)
    open_ = np.concatenate([close[:1], close[:-1]])
    return Bars(
        ts=np.arange(close.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=open_,
        high=np.maximum(open_, close) + 0.5,
        low=np.minimum(open_, close) - 0.5,
        close=close,
        volume=np.full(close.size, 1000.0),
    )


def _fallback(spec: object) -> int | float | str:
    """A legal value for a required parameter, so the sweep can exercise every primitive."""
    if isinstance(spec, IntParam):
        return max(spec.minimum, min(5, spec.maximum))
    if isinstance(spec, FloatParam):
        return max(spec.minimum, min(1.5, spec.maximum))
    if isinstance(spec, ChoiceParam):
        return spec.choices[0]
    raise AssertionError(f"no fallback for {spec!r}")


def _call(name: str, **params: object) -> Call:
    registry = default_registry()
    primitive = registry.get(name)
    literals: dict[str, int | float | str] = {}
    for spec in primitive.params:
        if spec.name in params:
            literals[spec.name] = params[spec.name]  # type: ignore[assignment]
        else:
            default = getattr(spec, "default", None)
            literals[spec.name] = _fallback(spec) if default is None else default
    return Call(primitive=name, kind=primitive.kind, literals=literals, nested={})


def _compute(name: str, bars: Bars | None = None, **params: object) -> npt.NDArray[np.float64]:
    registry = default_registry()
    return evaluate(_call(name, **params), bars or _bars(), registry)


# --------------------------------------------------------------------------------------
# Hand-computed arithmetic
# --------------------------------------------------------------------------------------


def test_sma_matches_the_hand_computed_average() -> None:
    sma = _compute("sma", n=3)
    assert np.isnan(sma[:2]).all()  # no honest value before three bars exist
    assert sma[2] == pytest.approx((10.0 + 11.0 + 12.0) / 3.0)
    assert sma[3] == pytest.approx((11.0 + 12.0 + 11.0) / 3.0)


def test_true_range_is_gap_aware() -> None:
    """H-L alone reports 2.0 across the 13 -> 20 jump; the gap is the whole point of true range."""
    tr = _compute("true_range")
    assert np.isnan(tr[0])  # bar 0 has no previous close, so no true range exists
    assert tr[1] == pytest.approx(2.0)
    assert tr[8] == pytest.approx(8.0)  # max(21-19, |21-13|, |19-13|)


def test_atr_matches_the_hand_computed_wilder_recursion() -> None:
    """True range starts at bar 1, so a 3-period ATR cannot exist before bar 3 — not bar 2.

    Seed = mean(TR[1..3]) = 2.0, placed at bar 3. Then ``value += (tr - value)/3``:
    bar 8 = (1/3)*8 + (2/3)*2 = **4.0**; bar 9 = (1/3)*2 + (2/3)*4 = **10/3**.

    The off-by-one here is the whole reason this test exists. An implementation that back-fills
    bar 0's missing true range gets a value at bar 2, seeds from a duplicated observation, and is
    wrong from there on — silently, and by enough to change whether a signal fires.
    """
    atr = _compute("atr", n=3)
    assert np.isnan(atr[2])
    assert atr[3] == pytest.approx(2.0)
    assert atr[7] == pytest.approx(2.0)
    assert atr[8] == pytest.approx(4.0)
    assert atr[9] == pytest.approx(10.0 / 3.0)


def _reference_rsi(close: npt.NDArray[np.float64], n: int) -> npt.NDArray[np.float64]:
    """Wilder's RSI written directly from the definition, independently of the library."""
    out = np.full(close.size, np.nan)
    gains = [max(close[i] - close[i - 1], 0.0) for i in range(1, close.size)]
    losses = [max(close[i - 1] - close[i], 0.0) for i in range(1, close.size)]
    avg_gain = sum(gains[:n]) / n
    avg_loss = sum(losses[:n]) / n
    for i in range(n, close.size):
        if i > n:
            avg_gain = (avg_gain * (n - 1) + gains[i - 1]) / n
            avg_loss = (avg_loss * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def test_rsi_matches_an_independent_wilder_implementation() -> None:
    """Wilder smoothing, not a simple average of gains — the two differ materially."""
    close = np.array(
        [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03,
         45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 46.22, 45.64],
        dtype=np.float64,
    )  # fmt: skip
    bars = _bars(list(close))
    mine = _compute("rsi", bars, n=14)
    reference = _reference_rsi(close, 14)
    valid = ~np.isnan(reference)
    np.testing.assert_allclose(mine[valid], reference[valid], rtol=1e-9)


def test_rsi_is_100_when_nothing_fell() -> None:
    """A window with no losses is RSI 100 by definition, not a divide-by-zero."""
    rsi = _compute("rsi", _bars([float(x) for x in range(1, 25)]), n=14)
    assert rsi[-1] == pytest.approx(100.0)


def test_internal_bar_strength_is_position_within_the_bar() -> None:
    ibs = _compute("internal_bar_strength")
    assert ibs[0] == pytest.approx(0.5)  # close sits mid-range for every bar in this fixture


# --------------------------------------------------------------------------------------
# Warm-up honesty
# --------------------------------------------------------------------------------------


def test_a_window_longer_than_the_series_is_all_nan() -> None:
    """Not a part-window average — a 50-bar mean of 10 bars is not a 50-bar mean."""
    assert np.isnan(_compute("sma", n=50)).all()


def test_donchian_excludes_the_current_bar() -> None:
    """An n-bar high including today can never be exceeded, so a breakout rule never fires."""
    upper = _compute("donchian_upper", n=3)
    # Highs are close+1: bars 5,6,7 -> 12,13,14. Bar 8's channel must not know about bar 8's 21.
    assert upper[8] == pytest.approx(14.0)


def test_relative_volume_excludes_today_from_its_own_baseline() -> None:
    volumes = _bars()
    spiked = Bars(
        volumes.ts, volumes.open, volumes.high, volumes.low, volumes.close, volumes.volume.copy()
    )
    spiked.volume[8] = 10_000.0
    rel = evaluate(_call("relative_volume", n=3), spiked, default_registry())
    assert rel[8] == pytest.approx(10.0)  # 10000 / 1000, undiluted by the spike itself


# --------------------------------------------------------------------------------------
# Cross detection
# --------------------------------------------------------------------------------------


def test_a_cross_requires_strictly_through_not_merely_touching() -> None:
    a = np.array([1.0, 2.0, 2.0, 3.0])
    b = np.array([2.0, 2.0, 2.0, 2.0])
    crossed = _ops.crossed_above(a, b)
    assert crossed[1] == 0.0  # touched equal — not a cross
    assert crossed[2] == 0.0  # still equal — must not fire on every bar of a flat stretch
    assert crossed[3] == 1.0  # genuinely through


def test_shift_refuses_to_look_forward() -> None:
    with pytest.raises(ValueError, match="looks backwards only"):
        _ops.shift(np.arange(5.0), -1)


def test_bars_reject_a_series_that_is_not_ascending() -> None:
    bars = _bars()
    shuffled = Bars(bars.ts[::-1].copy(), bars.open, bars.high, bars.low, bars.close, bars.volume)
    assert len(shuffled) == len(bars)  # the dataclass itself does not validate; from_candles does


# --------------------------------------------------------------------------------------
# The look-ahead sweep — the test that matters most
# --------------------------------------------------------------------------------------

# Words needing a nested series argument or an unavailable source are exercised elsewhere.
_NEEDS_ARGUMENTS = frozenset({"cross_above", "cross_below", "above", "below", "rising", "falling",
                              "zscore", "percentile_rank"})  # fmt: skip


def test_no_primitive_sees_the_future() -> None:
    """Recompute every primitive over truncated prefixes; the overlap must be identical.

    This is the only check here that can catch a look-ahead bug in a primitive nobody thought to
    test by hand. A word that peeks at bar t+1 produces a *different* value at bar t once the
    future is taken away — so the two runs disagree, and the disagreement names the culprit.

    **Why many cut points and not one.** The test can only see a disagreement *at the cut*: a word
    that peeks three bars ahead differs from the truncated run only in the last three bars, and if
    nothing interesting happens there the two runs agree and the bug walks. Measured on the 1.4b
    structure set with the confirmation lag deliberately removed, a single cut at bar 90 caught
    **6 of 33** affected words; sweeping every cut from bar 40 on caught **27 of 33**. Same test,
    same bug, four times the detection — the cost is a fifth of a second.

    It is still not a proof: six words survived even the full sweep, because their output happened
    not to change near any cut on this series. That is why the structure primitives additionally
    carry hand-computed fixtures pinning the exact bar each swing may first appear on
    (``test_dsl_structure.py``). The sweep is the net for words nobody hand-checked, not a
    substitute for checking them.
    """
    rng = np.random.default_rng(20260802)
    closes = list(np.cumsum(rng.normal(0.0, 1.0, 120)) + 100.0)
    full = _bodied_bars(closes)
    registry = default_registry()
    cuts = range(40, len(closes), 4)

    checked = 0
    for primitive in registry:
        if primitive.name in _NEEDS_ARGUMENTS or primitive.intraday_only or primitive.requires_feed:
            continue
        whole = evaluate(_call(primitive.name), full, registry)
        for cut in cuts:
            prefix = evaluate(_call(primitive.name), _bodied_bars(closes[:cut]), registry)
            seen = whole[:cut]
            assert np.array_equal(np.isnan(seen), np.isnan(prefix)), (
                f"{primitive.name} knows a value earlier when more future data is present "
                f"(cut at bar {cut})"
            )
            both_known = ~np.isnan(seen) & ~np.isnan(prefix)
            np.testing.assert_allclose(
                seen[both_known],
                prefix[both_known],
                rtol=1e-9,
                atol=1e-9,
                err_msg=f"{primitive.name} changes its own past when the future is removed "
                f"(cut at bar {cut})",
            )
        checked += 1
    assert checked > 90, f"only {checked} primitives were swept — the guard has gone slack"


# --------------------------------------------------------------------------------------
# Refusals at compute time
# --------------------------------------------------------------------------------------


def test_an_intraday_primitive_raises_if_evaluation_is_ever_reached() -> None:
    """The parser normally stops this. The backstop must raise, never return a plausible number."""
    with pytest.raises(DslError, match="cannot be computed"):
        _compute("session_vwap")


def test_a_feed_primitive_raises_if_evaluation_is_ever_reached() -> None:
    with pytest.raises(DslError, match=r"not threaded into Bars until 1\.7"):
        _compute("delivery_pct")


def test_every_context_primitive_declares_a_feed() -> None:
    """A CONTEXT word with no declared source would parse anywhere and compute from nothing."""
    for primitive in default_registry():
        if primitive.kind is Kind.CONTEXT:
            assert primitive.requires_feed, f"{primitive.name} is CONTEXT but declares no feed"


# --------------------------------------------------------------------------------------
# Warm-up length — the blind spot the look-ahead sweep cannot see
# --------------------------------------------------------------------------------------
#
# `test_no_primitive_sees_the_future` catches a primitive reading FORWARD. It is structurally
# blind to the opposite mistake: fabricating values BACKWARD, by filling a warm-up gap with an
# invented number. Deleting the end of the series does not disturb a value manufactured from the
# start of it, so the sweep passes with the bug present — as it did.
#
# Both real instances of that bug in this codebase were of the backward kind:
#   * `wilder()` back-filled bar 0's missing true range, shifting the seed a bar early and
#     double-counting the first real reading (~3.5 RSI points against Wilder's worked example);
#   * `dema`/`tema` filled the first EMA's warm-up with `close[0]` so the second pass could start
#     sooner — feeding a *price* into a series of averages, fabricating 4 bars outright at n=5.
#
# Pinning the exact first honest bar is what catches this class. Each figure below is derived, not
# observed: if an implementation ever produces a value earlier than the arithmetic allows, it is
# inventing one.


@pytest.mark.parametrize(
    ("name", "params", "first_honest_bar", "why"),
    [
        ("sma", {"n": 5}, 4, "n-1: needs n closes"),
        ("ema", {"n": 5}, 4, "n-1: SMA-seeded from n closes"),
        ("atr", {"n": 5}, 5, "n: true range itself starts at bar 1, not bar 0"),
        ("rsi", {"n": 5}, 5, "n: gains/losses start at bar 1"),
        ("dema", {"n": 5}, 8, "2n-2: the second EMA needs n real values from the first"),
        ("tema", {"n": 5}, 12, "3n-3: three chained EMAs, each paying n-1 again"),
        ("macd", {"fast": 12, "slow": 26, "signal": 9}, 25, "slow-1: the slower EMA gates it"),
        ("macd_signal", {"fast": 12, "slow": 26, "signal": 9}, 33, "(slow-1)+(signal-1)"),
        ("donchian_upper", {"n": 5}, 5, "n: the channel excludes the current bar, so +1"),
    ],
)
def test_a_primitive_produces_no_value_before_its_inputs_allow(
    name: str, params: dict[str, int], first_honest_bar: int, why: str
) -> None:
    rng = np.random.default_rng(7)
    bars = _bars(list(np.cumsum(rng.normal(0.0, 1.0, 200)) + 100.0))
    values = evaluate(_call(name, **params), bars, default_registry())
    first = int(np.argmax(~np.isnan(values)))
    assert first == first_honest_bar, f"{name} first value at bar {first}, expected {why}"
    assert np.isnan(values[:first_honest_bar]).all(), f"{name} has a hole before its warm-up ends"


def test_nothing_in_the_library_fills_a_gap_with_an_invented_value() -> None:
    """Guard the fix directly: no primitive may back-fill its warm-up from the price series.

    A filled warm-up is detectable without knowing the formula — feed a series whose opening bars
    are wildly out of line with the rest. A primitive that fills from ``close[0]`` drags that
    outlier into its early output; one that refuses to compute simply reports ``nan``.

    The signature it leaves is a *hole*: a stretch of values, then ``nan`` again. The exemption is
    the ``intermittent`` flag on the primitive itself, not a list of names kept in this file. A zone
    word's ``nan`` can honestly mean "that gap has been filled, there is no level here now" — but
    the word has to say so where it is defined, so that a genuinely broken new primitive cannot be
    waved through by editing a test.
    """
    rng = np.random.default_rng(11)
    tail = list(np.cumsum(rng.normal(0.0, 1.0, 120)) + 100.0)
    bars = _bodied_bars([5000.0, 5000.0, 5000.0, *tail])
    registry = default_registry()
    for primitive in registry:
        if primitive.intraday_only or primitive.requires_feed or primitive.params == ():
            continue
        if primitive.intermittent or any(isinstance(s, SeriesParam) for s in primitive.params):
            continue
        values = evaluate(_call(primitive.name), bars, registry)
        known = ~np.isnan(values)
        if not known.any():
            continue
        # Wherever a value exists, every bar it depends on must exist too: no interior holes.
        first = int(np.argmax(known))
        assert known[first:].all() or primitive.name in {"psar"}, (
            f"{primitive.name} reports values with gaps between them — a filled warm-up leaves "
            f"exactly this signature"
        )


def test_a_threshold_comparison_is_expressible_at_all() -> None:
    """``rsi(14) < 30`` — the most common rule in technical trading — could not be written until
    ``constant`` existed (added in 1.4c).

    ``above``/``below`` take two *series*, which is the composable form and the right one. But it
    left roughly sixty SERIES words in this library unusable in a condition, and the gap survived
    1.4a and 1.4b unnoticed because the words that read as complete sentences on their own
    (``sweep_and_reclaim_low``, ``in_discount``) hid it.
    """
    threshold = _call("constant", value=30.0)
    rsi = _call("rsi", n=14)
    node = Call(
        primitive="below",
        kind=Kind.EVENT,
        literals={},
        nested={"a": rsi, "b": threshold},
    )
    bars = _bars([float(x) for x in range(1, 40)])
    fired = evaluate(node, bars, default_registry())
    assert np.isnan(fired[:14]).all()
    assert fired[-1] == 0.0, "a series that only rises has RSI 100, which is not below 30"


def test_a_constant_is_the_same_number_on_every_bar_including_bar_zero() -> None:
    """No warm-up: the value was knowable before the series started."""
    values = _compute("constant", value=7.5)
    assert values == pytest.approx(np.full(len(CLOSES), 7.5))
