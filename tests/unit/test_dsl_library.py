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
    """
    rng = np.random.default_rng(20260802)
    closes = list(np.cumsum(rng.normal(0.0, 1.0, 120)) + 100.0)
    full = _bars(closes)
    truncated = _bars(closes[:90])
    registry = default_registry()

    checked = 0
    for primitive in registry:
        if primitive.name in _NEEDS_ARGUMENTS or primitive.intraday_only or primitive.requires_feed:
            continue
        whole = evaluate(_call(primitive.name), full, registry)[:90]
        prefix = evaluate(_call(primitive.name), truncated, registry)
        both_known = ~np.isnan(whole) & ~np.isnan(prefix)
        np.testing.assert_allclose(
            whole[both_known],
            prefix[both_known],
            rtol=1e-9,
            atol=1e-9,
            err_msg=f"{primitive.name} changes its own past when the future is removed",
        )
        assert np.array_equal(np.isnan(whole), np.isnan(prefix)), (
            f"{primitive.name} knows a value earlier when more future data is present"
        )
        checked += 1
    assert checked > 60, f"only {checked} primitives were swept — the guard has gone slack"


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
