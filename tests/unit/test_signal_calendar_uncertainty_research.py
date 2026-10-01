"""Invented calendar arithmetic only; no simulator data or random draws."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, cast

import pytest
from scripts.research import signal_calendar_uncertainty as m


def fixture(
    sums: tuple[Fraction, ...] = (
        Fraction(2, 100),
        Fraction(0),
        Fraction(-1, 100),
        Fraction(3, 100),
        Fraction(0),
        Fraction(4, 100),
        Fraction(-2, 100),
        Fraction(1, 100),
    ),
    counts: tuple[int, ...] = (2, 0, 1, 3, 0, 2, 1, 1),
) -> tuple[m.CalendarSource, m.CalendarModel, m.CalendarRequest]:
    declared = m.Declaration.FIXTURE_DECLARED
    records = tuple(
        m.TradeRecord(
            f"t-{t}-{i}",
            f"stock-{i}",
            t - 1,
            t,
            (t + 1,),
            (t - 1, t, t + 1),
            t + 1,
            a / c,
            benchmark_excess=a / c - Fraction(1, 1000),
            benchmark_complete=declared,
        )
        for t, (a, c) in enumerate(zip(sums, counts, strict=True))
        for i in range(c)
    )
    source = m.CalendarSource(
        "invented-calendar",
        "whole-run-v1",
        "reset-v1",
        tuple(range(len(sums))),
        -4,
        len(sums) + 8,
        records,
        cohort_complete=declared,
        geometry=declared,
        accounting=m.Accounting.BEFORE_TAX_MODEL_COST,
        expected_core_ids=tuple(record.identifier for record in records),
    )
    model = m.CalendarModel(
        source.fixture,
        "stationary-artificial-law",
        m.Metric.RAW,
        2,
        4,
        declared,
        declared,
        declared,
        declared,
        declared,
        declared,
        declared,
        declared,
    )
    request = m.CalendarRequest(m.Metric.RAW, Fraction(1, 20), 1, declared)
    return source, model, request


def test_original_ratio_calendar_counts_and_reversed_quantiles() -> None:
    source, model, request = fixture()
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarCandidate)
    assert result.mean == Fraction(7, 1000)
    assert result.total_count == 10
    assert result.session_counts == (2, 0, 1, 3, 0, 2, 1, 1)
    assert result.block_size == 4
    assert result.block_counts == (6, 4, 6, 6, 4)
    assert result.block_means == (
        Fraction(1, 150),
        Fraction(1, 200),
        Fraction(1, 100),
        Fraction(1, 120),
        Fraction(3, 400),
    )
    assert result.quantile_ranks == (0, 4)
    assert result.quantile_deviations == (Fraction(-1, 500), Fraction(3, 1000))
    assert Decimal("0.00487867965") < result.candidate_lower < Decimal("0.00487867967")
    assert Decimal("0.00841421355") < result.candidate_upper < Decimal("0.00841421357")
    assert result.market_eligible is False
    assert result.authority == "ASYMPTOTIC_CANDIDATE_UNCALIBRATED"
    assert not hasattr(result, "lower")


def test_boundary_complete_outcome_and_halo_only_entrant_preserve_mean() -> None:
    source, model, request = fixture()
    records = list(source.records)
    records[0] = replace(records[0], exits=(1, 4), recognition=4, source_sessions=(-1, 0, 1, 4))
    halo = m.TradeRecord("halo-only", "halo-stock", 8, 9, (10,), (8, 9, 10), 10, 999)
    result = m.estimate(replace(source, records=(*tuple(records), halo)), model, request)
    assert isinstance(result, m.CalendarCandidate)
    assert result.mean == Fraction(7, 1000)
    assert result.total_count == 10
    assert result.halo_only_trade_ids == ("halo-only",)
    assert result.block_trade_ids[0].count(records[0].identifier) == 1
    assert 4 in result.block_halos[0]


def test_empty_scheduled_slice_refuses_without_discard() -> None:
    source, model, request = fixture((Fraction(1),) + (Fraction(0),) * 7, (1, 0, 0, 0, 0, 0, 0, 0))
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.ZERO_COUNT_SLICE
    assert result.zero_count_slices == (1, 2, 3, 4)
    assert result.total_count == 1


def test_degenerate_roots_refuse() -> None:
    source, model, request = fixture((Fraction(1),) * 8, (1,) * 8)
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.DEGENERATE_ROOTS


@pytest.mark.parametrize(
    "field",
    [
        "stationarity",
        "strong_mixing",
        "finite_two_plus_delta",
        "summable_mixing",
        "positive_entry_intensity",
        "positive_long_run_variance",
        "finite_footprint",
        "shift_equivariance",
    ],
)
def test_unknown_model_premise_refuses(field: str) -> None:
    source, model, request = fixture()
    result = m.estimate(
        source, replace(model, **cast(dict[str, Any], {field: m.Declaration.UNKNOWN})), request
    )
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.UNKNOWN_MODEL


def test_width_insufficient_retains_only_labelled_candidate_endpoints() -> None:
    source, model, request = fixture()
    result = m.estimate(source, model, replace(request, absolute_full_width=Fraction(1, 10000)))
    assert isinstance(result, m.CalendarInsufficientEvidence)
    assert result.candidate_lower < result.candidate_upper
    assert result.market_eligible is False
    assert not hasattr(result, "lower")


@pytest.mark.parametrize(
    "change",
    [
        "axis_gap",
        "duplicate",
        "unauthorized",
        "unbounded",
        "stale",
        "terminal",
        "accounting",
        "realdata",
    ],
)
def test_observable_contract_failures_refuse(change: str) -> None:
    source, model, request = fixture()
    if change == "axis_gap":
        source = replace(source, core_sessions=(0, 1, 2, 4, 5, 6, 7, 8))
    elif change == "duplicate":
        source = replace(source, records=(*source.records, source.records[0]))
    elif change == "unauthorized":
        source = replace(source, authorized_source_end=7)
    elif change == "unbounded":
        model = replace(model, completion_bound=None)
    elif change == "accounting":
        source = replace(source, accounting=m.Accounting.UNKNOWN)
    elif change == "realdata":
        source = replace(source, scope=m.Scope.REAL_DATA)
    else:
        source = replace(
            source,
            records=(
                replace(source.records[0], **cast(dict[str, Any], {change: True})),
                *source.records[1:],
            ),
        )
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.market_eligible is False


def test_missing_paired_benchmark_refuses_no_matched_subset_raw_survives() -> None:
    source, model, request = fixture()
    source = replace(
        source, records=(replace(source.records[0], benchmark_excess=None), *source.records[1:])
    )
    assert isinstance(m.estimate(source, model, request), m.CalendarCandidate)
    result = m.estimate(
        source,
        replace(model, metric=m.Metric.SYNTHETIC_EXCESS),
        replace(request, metric=m.Metric.SYNTHETIC_EXCESS),
    )
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.MISSING_BENCHMARK
    assert result.total_count == 10


def test_direct_excess_and_strict_positive_win_targets() -> None:
    source, model, request = fixture()
    for metric, expected in (
        (m.Metric.SYNTHETIC_EXCESS, Fraction(6, 1000)),
        (m.Metric.WIN, Fraction(8, 10)),
    ):
        result = m.estimate(source, replace(model, metric=metric), replace(request, metric=metric))
        assert isinstance(result, m.CalendarCandidate)
        assert result.mean == expected


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), Decimal("NaN"), True, Decimal("0.1" + "0" * 4999)]
)
def test_nonfinite_or_oversized_numeric_refuses(value: object) -> None:
    source, model, request = fixture()
    source = replace(
        source,
        records=(replace(source.records[0], raw=cast(m.Numeric, value)), *source.records[1:]),
    )
    assert isinstance(m.estimate(source, model, request), m.CalendarRefusal)


def test_ambient_decimal_context_does_not_change_results() -> None:
    source, model, request = fixture()
    expected = m.estimate(source, model, request)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        for signal in context.traps:
            context.traps[signal] = True
        assert m.estimate(source, model, request) == expected


def test_unknown_precision_and_outcome_selection_refuse() -> None:
    source, model, request = fixture()
    assert isinstance(
        m.estimate(source, model, replace(request, absolute_full_width=None)), m.CalendarRefusal
    )
    assert isinstance(
        m.estimate(source, model, replace(request, selection=m.Declaration.OBSERVED)),
        m.CalendarRefusal,
    )


def test_omitted_core_entry_is_rejected_against_pinned_ids() -> None:
    source, model, request = fixture()
    result = m.estimate(replace(source, records=source.records[1:]), model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.INCOMPLETE_COHORT


def test_halo_only_missing_benchmark_does_not_block_paired_core() -> None:
    source, model, request = fixture()
    halo = m.TradeRecord("halo-only", "halo-stock", 8, 9, (10,), (8, 9, 10), 10, 999)
    result = m.estimate(
        replace(source, records=(*source.records, halo)),
        replace(model, metric=m.Metric.SYNTHETIC_EXCESS),
        replace(request, metric=m.Metric.SYNTHETIC_EXCESS),
    )
    assert isinstance(result, m.CalendarCandidate)
    assert result.mean == Fraction(6, 1000)


def test_zero_selected_quantile_spread_refuses_even_nonconstant_roots() -> None:
    source, model, request = fixture((Fraction(100),) + (Fraction(0),) * 63, (1,) * 64)
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.DEGENERATE_QUANTILES


def test_total_declared_footprint_budget_refuses_before_expansion() -> None:
    source, model, request = fixture(counts=(10,) * 8)
    records = tuple(
        replace(record, source_sessions=tuple(range(-1000, record.entry + 2)))
        for record in source.records
    )
    source = replace(source, records=records, authorized_source_start=-2000)
    result = m.estimate(source, replace(model, lookback_bound=2000), request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT


def test_repeated_block_footprint_budget_refuses_before_diagnostics() -> None:
    source, model, request = fixture(tuple(Fraction(t % 3) for t in range(64)), (1,) * 64)
    records = tuple(
        replace(record, source_sessions=tuple(range(-400, record.entry + 2)))
        for record in source.records
    )
    source = replace(source, records=records, authorized_source_start=-500)
    result = m.estimate(source, replace(model, lookback_bound=500), request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT


def test_same_sign_quantiles_reverse_subtraction_outward() -> None:
    source, model, request = fixture(
        (Fraction(-10),) + (Fraction(1),) * 7 + (Fraction(-10),), (1,) * 9
    )
    result = m.estimate(source, model, replace(request, absolute_full_width=100))
    assert isinstance(result, m.CalendarCandidate)
    assert result.quantile_deviations[0] > 0
    assert result.quantile_deviations[1] > result.quantile_deviations[0]
    assert Fraction(result.candidate_lower) < Fraction(result.candidate_upper) < result.mean
    assert Fraction(result.candidate_lower) <= result.mean - result.quantile_deviations[
        1
    ] * Fraction(result.sqrt_ratio_upper)
    assert Fraction(result.candidate_upper) >= result.mean - result.quantile_deviations[
        0
    ] * Fraction(result.sqrt_ratio_lower)


def test_labelled_stale_raw_arithmetic_retains_full_mean_in_refusal() -> None:
    source, model, request = fixture()
    source = replace(source, records=(replace(source.records[0], stale=True), *source.records[1:]))
    result = m.estimate(source, model, request)
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.STALE_OUTCOME
    assert result.raw_mean == Fraction(7, 1000)
    assert result.total_count == 10


def test_same_bar_decision_and_missing_actual_source_event_refuse() -> None:
    source, model, request = fixture()
    for first in (
        replace(source.records[0], decision=source.records[0].entry),
        replace(source.records[0], source_sessions=(-1, 0)),
    ):
        result = m.estimate(replace(source, records=(first, *source.records[1:])), model, request)
        assert isinstance(result, m.CalendarRefusal)
        assert result.reason is m.Reason.INVALID_RECORD


def test_extreme_large_integer_mean_keeps_complete_outcomes_and_finite_endpoints() -> None:
    source, model, request = fixture()
    records = tuple(
        replace(record, raw=10**4000 + Fraction(record.raw)) for record in source.records
    )
    result = m.estimate(replace(source, records=records), model, request)
    assert isinstance(result, m.CalendarCandidate)
    assert result.mean == 10**4000 + Fraction(7, 1000)
    assert result.candidate_lower.is_finite() and result.candidate_upper.is_finite()
    assert Fraction(result.candidate_lower) < result.mean < Fraction(result.candidate_upper)


def test_plain_string_metric_refuses_instead_of_enum_alias() -> None:
    source, model, request = fixture()
    metric = cast(m.Metric, "raw")
    result = m.estimate(source, replace(model, metric=metric), replace(request, metric=metric))
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.INVALID_INPUT


def test_expected_id_manifest_budget_refuses_before_set_allocation() -> None:
    source, model, request = fixture()
    result = m.estimate(
        replace(source, expected_core_ids=tuple(str(i) for i in range(5000))), model, request
    )
    assert isinstance(result, m.CalendarRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT
