"""Synthetic-only tests for the Step 6a.1 signal-metric boundary."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import UTC, date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from icarus.common.config import SignalTest
from icarus.engine.costmodel import Charges
from icarus.engine.signalmetrics import (
    CandidateMoments,
    MetricDiagnostic,
    MetricObservation,
    MetricRefusal,
    SignalDiagnostics,
    SourceSessionAxis,
    _cr2_moments,
    _describe,
    summarize_signal_run,
)
from icarus.engine.signaltest import (
    SignalExitFragment,
    SignalMissing,
    SignalMissingReason,
    SignalRunResult,
    SignalSkipped,
    SignalSkipReason,
    SignalTrade,
)
from icarus.engine.simcore import ExitReason, SignalId


def _at(day: int) -> datetime:
    return datetime(2020, 1, 1, tzinfo=UTC) + timedelta(days=day - 1)


def _axis(*, origin: int = 100, stop: int = 106) -> SourceSessionAxis:
    return SourceSessionAxis(
        sessions=tuple((index, _at(index - 99)) for index in range(100, stop + 1)),
        study_origin_index=origin,
    )


def _settings() -> SignalTest:
    return SignalTest(
        registered=date(2026, 8, 22),
        statistics_registered=date(2026, 9, 24),
        notional_inr=100_000,
        one_position_per_symbol=True,
        apply_costs=True,
        apply_tax=False,
        diagnostic_only=True,
        block_min_sessions=63,
        holding_period_block_multiplier=3,
        ci_level=0.95,
        placebo_permutations=4_999,
        rng_seed=20_260_924,
        inference_enabled=False,
    )


def _charges(turnover: Decimal) -> Charges:
    return Charges(
        brokerage=Decimal(0),
        stt=Decimal(0),
        exchange_txn=Decimal(0),
        sebi_fee=Decimal(0),
        gst=Decimal(0),
        stamp_duty=Decimal(0),
        dp_charge=Decimal(0),
        turnover=turnover,
    )


def _fragment(
    *,
    quantity: int,
    price: Decimal,
    source_index: int,
    recognition_index: int | None = None,
    reason: ExitReason = ExitReason.TAKE_PROFIT,
) -> SignalExitFragment:
    recognised = source_index if recognition_index is None else recognition_index
    return SignalExitFragment(
        quantity=quantity,
        price=price,
        price_source_ts=_at(source_index - 99),
        price_source_index=source_index,
        recognition_ts=_at(recognised - 99),
        recognition_index=recognised,
        reason=reason,
        charges=_charges(price * quantity),
    )


def _trade(
    *,
    symbol: str = "AAA",
    decision_index: int = 100,
    entry_index: int = 101,
    entry_price: Decimal = Decimal(100),
    quantity: int = 10,
    fragments: tuple[SignalExitFragment, ...] | None = None,
) -> SignalTrade:
    exits = fragments or (_fragment(quantity=quantity, price=Decimal(110), source_index=102),)
    return SignalTrade(
        signal_id=SignalId(
            strategy_id="breakout",
            strategy_version=2,
            symbol=symbol,
            decision_ts=_at(decision_index - 99),
            decision_index=decision_index,
        ),
        entry_ts=_at(entry_index - 99),
        entry_index=entry_index,
        entry_price=entry_price,
        filled_quantity=quantity,
        intended_notional=entry_price * quantity,
        risk_per_share=Decimal(10),
        entry_charges=_charges(entry_price * quantity),
        exit_fragments=exits,
    )


def _run(
    *,
    trades: tuple[SignalTrade, ...] = (),
    skips: tuple[SignalSkipped, ...] = (),
    missing: tuple[SignalMissing, ...] = (),
) -> SignalRunResult:
    return SignalRunResult(
        trades=trades,
        skips=skips,
        missing=missing,
        emitted_signals=len(trades) + len(skips),
        unfilled_exits=0,
    )


def test_empty_run_returns_typed_component_refusals() -> None:
    """Returning zeros would make absence of evidence look like a flat strategy."""
    result = summarize_signal_run(_run(), source_axis=_axis(), settings=_settings())

    assert result.raw_return == MetricDiagnostic(
        count=0,
        mean=None,
        moments=None,
        refusal=MetricRefusal.EMPTY_SAMPLE,
    )
    assert result.win_rate.refusal is MetricRefusal.EMPTY_SAMPLE
    assert result.benchmark_excess.refusal is MetricRefusal.MISSING_BENCHMARK
    assert result.placebo.refusal is MetricRefusal.INDEFENSIBLE_PLACEBO_NULL
    assert result.filled_count == result.skip_count == result.missing_count == 0
    assert result.longest_holding_sessions is None
    assert result.block_length is None
    assert result.study_origin_index == 100


def test_two_distinct_trades_preserve_descriptive_means_without_inference() -> None:
    """Dropping losses or turning this slice into an interval would misstate the evidence."""
    winner = _trade()
    loser = _trade(
        symbol="BBB",
        decision_index=103,
        entry_index=104,
        fragments=(_fragment(quantity=10, price=Decimal(90), source_index=106),),
    )

    result = summarize_signal_run(
        _run(trades=(winner, loser)), source_axis=_axis(), settings=_settings()
    )

    assert result.raw_return.count == 2
    assert result.raw_return.mean == pytest.approx(0.0)
    assert result.raw_return.moments is None
    assert result.raw_return.refusal is MetricRefusal.TOO_FEW_BLOCKS
    assert result.win_rate.count == 2
    assert result.win_rate.mean == pytest.approx(0.5)
    assert result.win_rate.moments is None
    assert result.longest_holding_sessions == 3
    assert result.block_length == 63
    assert result.method_version == "entry-session-cr2-satterthwaite-v1"


def test_partial_exit_fragments_contribute_one_return_observation() -> None:
    """Counting fragments as trades would double-weight one signal and its entry cost."""
    trade = _trade(
        quantity=10,
        fragments=(
            _fragment(quantity=4, price=Decimal(120), source_index=102),
            _fragment(quantity=6, price=Decimal(90), source_index=104),
        ),
    )

    result = summarize_signal_run(_run(trades=(trade,)), source_axis=_axis(), settings=_settings())

    assert result.filled_count == 1
    assert result.raw_return.count == 1
    assert result.raw_return.mean == pytest.approx(0.02)
    assert result.win_rate.mean == pytest.approx(1.0)
    assert result.longest_holding_sessions == 4
    assert result.block_length == 63


def test_long_holding_period_expands_block_length_from_validated_settings() -> None:
    """Hard-coding the 63-session minimum would ignore the declared 3H dependence rule."""
    trade = _trade(
        fragments=(_fragment(quantity=10, price=Decimal(110), source_index=126),),
    )

    result = summarize_signal_run(
        _run(trades=(trade,)), source_axis=_axis(stop=126), settings=_settings()
    )

    assert result.longest_holding_sessions == 26
    assert result.block_length == 78


@pytest.mark.parametrize("origin", [-1, True])
def test_source_axis_refuses_negative_or_boolean_origin(origin: int) -> None:
    """A Boolean or negative origin would make block identity non-canonical."""
    with pytest.raises((TypeError, ValueError), match="study_origin_index"):
        SourceSessionAxis(sessions=((100, _at(1)),), study_origin_index=origin)


@pytest.mark.parametrize(
    "sessions",
    [
        ((100, _at(1)), (102, _at(2))),
        ((101, _at(1)), (100, _at(2))),
        ((100, _at(2)), (101, _at(1))),
        ((100, _at(1)), (101, _at(1))),
        (
            (100, datetime(2020, 1, 1, 9, tzinfo=UTC)),
            (101, datetime(2020, 1, 1, 15, tzinfo=UTC)),
        ),
    ],
    ids=[
        "index-gap",
        "unsorted-index",
        "unsorted-time",
        "duplicate-timestamp",
        "duplicate-utc-date",
    ],
)
def test_source_axis_refuses_noncanonical_ordering(
    sessions: tuple[tuple[int, datetime], ...],
) -> None:
    """Gapped, reordered, or duplicate sessions would assign unstable time blocks."""
    with pytest.raises(ValueError):
        SourceSessionAxis(sessions=sessions, study_origin_index=100)


@pytest.mark.parametrize(
    "timestamp",
    [
        datetime(2020, 1, 1),
        datetime(2020, 1, 1, tzinfo=timezone(timedelta(0), "NOT_UTC")),
    ],
)
def test_source_axis_requires_datetime_utc_identity(timestamp: datetime) -> None:
    """Offset-equivalent or naive times would weaken the exact source-axis contract."""
    with pytest.raises(ValueError, match=r"datetime\.UTC"):
        SourceSessionAxis(sessions=((100, timestamp),), study_origin_index=100)


def test_source_axis_requires_origin_to_be_present() -> None:
    """An absent origin would let callers silently re-anchor a fold."""
    with pytest.raises(ValueError, match="present"):
        SourceSessionAxis(sessions=((100, _at(1)),), study_origin_index=101)


def test_trade_entry_cannot_precede_the_fixed_study_origin() -> None:
    """Negative block IDs would mean a fold was analysed against the wrong origin."""
    with pytest.raises(ValueError, match="origin"):
        summarize_signal_run(
            _run(trades=(_trade(),)), source_axis=_axis(origin=102), settings=_settings()
        )


def test_trade_coordinate_must_match_the_axis_index_and_timestamp() -> None:
    """Relative ordering alone cannot prove that a trade came from the declared source axis."""
    trade = _trade()
    object.__setattr__(trade.signal_id, "decision_ts", _at(2))

    with pytest.raises(ValueError, match="source axis"):
        summarize_signal_run(_run(trades=(trade,)), source_axis=_axis(), settings=_settings())


def test_trade_coordinate_outside_axis_is_rejected() -> None:
    """A run extending beyond its declared source cannot produce an auditable diagnostic."""
    trade = _trade(
        fragments=(_fragment(quantity=10, price=Decimal(110), source_index=107),),
    )

    with pytest.raises(ValueError, match="source axis"):
        summarize_signal_run(_run(trades=(trade,)), source_axis=_axis(), settings=_settings())


@pytest.mark.parametrize("outcome", ["skip", "missing"])
def test_nontrade_decision_coordinates_are_also_mapped_to_the_axis(outcome: str) -> None:
    """Ignoring non-trades would make denominator provenance weaker than trade provenance."""
    bad_ts = _at(7)
    if outcome == "skip":
        signal_id = SignalId(
            strategy_id="breakout",
            strategy_version=2,
            symbol="SKIP",
            decision_ts=bad_ts,
            decision_index=105,
        )
        run = _run(skips=(SignalSkipped(signal_id, SignalSkipReason.NOT_TRADABLE),))
    else:
        run = _run(missing=(SignalMissing("MISS", bad_ts, 105, SignalMissingReason.MISSING_INPUT),))

    with pytest.raises(ValueError, match="source axis"):
        summarize_signal_run(run, source_axis=_axis(), settings=_settings())


def test_forged_exit_recognition_coordinate_is_refused_before_it_can_change_h_or_l() -> None:
    """Trusting a mutated recognition index would silently lengthen the dependence block."""
    trade = _trade()
    object.__setattr__(trade.exit_fragments[-1], "recognition_index", 103)

    with pytest.raises(ValueError, match="source axis"):
        summarize_signal_run(_run(trades=(trade,)), source_axis=_axis(), settings=_settings())


@pytest.mark.parametrize(
    "value",
    [Decimal("NaN"), Decimal("Infinity"), Decimal("1e10000"), Decimal("1e-10000")],
)
def test_metric_observation_refuses_nonfinite_or_float64_range_loss(value: Decimal) -> None:
    """Overflow or nonzero underflow must not contaminate later arithmetic."""
    with pytest.raises(ValueError, match="finite float64"):
        MetricObservation(_trade().signal_id, 101, 2, value)


def test_descriptive_mean_refuses_nonzero_decimal_underflow_to_float64_zero() -> None:
    """A representable observation pair must not publish a rounded-away nonzero mean."""
    with pytest.raises(ValueError, match="descriptive mean"):
        _describe((Decimal("5e-324"), Decimal("-4e-324")), (0, 1))


def test_cr2_hand_case_preserves_unequal_block_occupancy() -> None:
    """Equal-weighting occupied blocks would change the hand-derived variance and effective N."""
    result = _cr2_moments((0.0, 1.0, 2.0), (0, 1, 1))

    assert isinstance(result, CandidateMoments)
    assert result.count == 3
    assert result.block_counts == ((0, 1), (1, 2))
    assert result.mean == pytest.approx(1.0)
    assert result.sample_variance == pytest.approx(1.0)
    assert result.cr2_variance == pytest.approx(0.5)
    assert result.degrees_of_freedom == pytest.approx(1.0)
    assert result.design_effect == pytest.approx(1.5)
    assert result.effective_n_uncapped == pytest.approx(2.0)
    assert result.effective_n_display == pytest.approx(2.0)
    assert result.effective_n_capped is False


def test_cr2_refusal_precedence_distinguishes_sparse_and_constant_samples() -> None:
    """Checking variance first would mislabel one occupied block as zero-variance evidence."""
    assert _cr2_moments((), ()) is MetricRefusal.EMPTY_SAMPLE
    assert _cr2_moments((1.0, 1.0), (0, 0)) is MetricRefusal.TOO_FEW_BLOCKS
    assert _cr2_moments((1.0, 1.0), (0, 1)) is MetricRefusal.ZERO_VARIANCE


def test_cr2_sample_variance_underflow_is_invalid_not_zero_variance() -> None:
    """Distinct tiny values must not be misreported as genuinely constant evidence."""
    assert _cr2_moments((1e-200, 2e-200), (0, 1)) is MetricRefusal.INVALID_VARIANCE


def test_cr2_block_score_square_underflow_is_invalid_not_exact_cancellation() -> None:
    """Nonzero block scores whose squares round away must fail rather than look independent."""
    assert _cr2_moments((1.0, -1.0, 1e-200, 0.0), (0, 0, 1, 2)) is MetricRefusal.INVALID_VARIANCE


def test_cr2_ratio_denominator_underflow_is_a_typed_refusal() -> None:
    """A positive sample variance that vanishes after division must not raise ZeroDivisionError."""
    assert _cr2_moments((0.0, 0.0, 0.0, 6e-162), (0, 0, 1, 2)) is MetricRefusal.INVALID_VARIANCE


def test_cr2_exact_nonconstant_block_score_cancellation_is_zero_variance() -> None:
    """True zero block scores remain a principled refusal distinct from arithmetic underflow."""
    assert _cr2_moments((-1.0, 1.0, -2.0, 2.0), (0, 0, 1, 1)) is MetricRefusal.ZERO_VARIANCE


@pytest.mark.parametrize(
    "values",
    [
        (1e308, 1e308, -1e308, -1e308),
        (1e308, -1e308),
    ],
    ids=["finite-sum-overflow", "finite-square-overflow"],
)
def test_cr2_finite_input_arithmetic_overflow_is_a_typed_refusal(
    values: tuple[float, ...],
) -> None:
    """Finite inputs must not let overflow escape or publish non-finite variance diagnostics."""
    block_ids = (0, 0, 1, 1) if len(values) == 4 else (0, 1)

    assert _cr2_moments(values, block_ids) is MetricRefusal.INVALID_VARIANCE


def test_cr2_is_stable_to_observation_reordering_and_dates_within_blocks() -> None:
    """Input order and dates that preserve block membership must not change the estimator."""
    original = _cr2_moments((0.0, 1.0, 2.0), (4, 5, 5))
    reordered = _cr2_moments((2.0, 0.0, 1.0), (5, 4, 5))

    assert original == reordered


def test_return_and_win_rate_keep_separate_effective_sample_sizes() -> None:
    """Borrowing return's effective N would overstate the win-rate component's evidence."""
    returns = _describe(
        (Decimal("-2"), Decimal("1"), Decimal("0.5"), Decimal("0.5")),
        (0, 0, 1, 1),
    )
    wins = _describe(
        (Decimal(0), Decimal(1), Decimal(1), Decimal(1)),
        (0, 0, 1, 1),
    )

    assert returns.moments is not None
    assert wins.moments is not None
    assert returns.moments.effective_n_uncapped == pytest.approx(22.0 / 3.0)
    assert wins.moments.effective_n_uncapped == pytest.approx(4.0)
    assert returns.moments.effective_n_capped is True
    assert wins.moments.effective_n_capped is False


def test_public_adapter_uses_fixed_origin_and_retains_empty_calendar_blocks() -> None:
    """Re-anchoring at the first trade or counting empty blocks would invent degrees of freedom."""
    loser = _trade(
        decision_index=162,
        entry_index=163,
        fragments=(_fragment(quantity=10, price=Decimal(90), source_index=164),),
    )
    winner = _trade(
        symbol="BBB",
        decision_index=288,
        entry_index=289,
        fragments=(_fragment(quantity=10, price=Decimal(110), source_index=290),),
    )

    result = summarize_signal_run(
        _run(trades=(winner, loser)), source_axis=_axis(stop=290), settings=_settings()
    )

    assert result.study_origin_index == 100
    assert result.block_length == 63
    assert result.raw_return.moments is not None
    assert result.raw_return.moments.block_counts == ((1, 1), (3, 1))
    assert result.raw_return.moments.degrees_of_freedom == pytest.approx(1.0)


def test_public_adapter_refuses_all_win_variance_without_erasing_return_moments() -> None:
    """A component-local all-win refusal must not discard varying positive return evidence."""
    smaller_winner = _trade(
        decision_index=162,
        entry_index=163,
        fragments=(_fragment(quantity=10, price=Decimal(110), source_index=164),),
    )
    larger_winner = _trade(
        symbol="BBB",
        decision_index=225,
        entry_index=226,
        fragments=(_fragment(quantity=10, price=Decimal(120), source_index=227),),
    )

    result = summarize_signal_run(
        _run(trades=(larger_winner, smaller_winner)),
        source_axis=_axis(stop=227),
        settings=_settings(),
    )

    assert result.raw_return.moments is not None
    assert result.raw_return.refusal is None
    assert result.win_rate.moments is None
    assert result.win_rate.mean == pytest.approx(1.0)
    assert result.win_rate.refusal is MetricRefusal.ZERO_VARIANCE


@pytest.mark.parametrize(
    ("entry_index", "holding_sessions"),
    [(True, 2), (-1, 2), (101, True), (101, 0)],
)
def test_metric_observation_requires_exact_integer_coordinates(
    entry_index: int, holding_sessions: int
) -> None:
    """Boolean and invalid indices would create plausible but false block assignments."""
    with pytest.raises((TypeError, ValueError)):
        MetricObservation(_trade().signal_id, entry_index, holding_sessions, Decimal("0.1"))


def test_public_adapter_requires_validated_signal_settings() -> None:
    """An unvalidated lookalike could bypass the pre-registered block settings."""
    with pytest.raises(TypeError, match="SignalTest"):
        summarize_signal_run(_run(), source_axis=_axis(), settings=object())  # type: ignore[arg-type]


def test_public_records_are_frozen_slotted_and_have_no_inference_fields() -> None:
    """Adding interval or p-value output here would enable inference before calibration."""
    assert [field.name for field in fields(CandidateMoments)] == [
        "count",
        "block_counts",
        "mean",
        "sample_variance",
        "cr2_variance",
        "degrees_of_freedom",
        "design_effect",
        "effective_n_uncapped",
        "effective_n_display",
        "effective_n_capped",
    ]
    assert [field.name for field in fields(SignalDiagnostics)] == [
        "raw_return",
        "win_rate",
        "benchmark_excess",
        "placebo",
        "filled_count",
        "skip_count",
        "missing_count",
        "longest_holding_sessions",
        "block_length",
        "study_origin_index",
        "method_version",
    ]
    forbidden = {"lower", "upper", "confidence_interval", "p_value"}
    for record in (CandidateMoments, MetricDiagnostic, SignalDiagnostics):
        assert forbidden.isdisjoint(field.name for field in fields(record))

    axis = _axis()
    assert not hasattr(axis, "__dict__")
    with pytest.raises(FrozenInstanceError):
        axis.study_origin_index = 101  # type: ignore[misc]
    assert _settings().inference_enabled is False


def test_metric_refusal_surface_is_typed_and_complete_for_step_6a1() -> None:
    """Free-text or missing refusal states would make downstream fail-closed logic brittle."""
    assert set(MetricRefusal) == {
        MetricRefusal.EMPTY_SAMPLE,
        MetricRefusal.TOO_FEW_BLOCKS,
        MetricRefusal.ZERO_VARIANCE,
        MetricRefusal.INVALID_VARIANCE,
        MetricRefusal.INVALID_DF,
        MetricRefusal.MISSING_BENCHMARK,
        MetricRefusal.INDEFENSIBLE_PLACEBO_NULL,
    }
