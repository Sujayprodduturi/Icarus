"""Deterministic exact-time matching and refusal contract on invented rational data."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from importlib import import_module
from types import ModuleType
from typing import Any

import pytest

ENTRY = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
EXIT1 = ENTRY + timedelta(days=1)
EXIT2 = ENTRY + timedelta(days=2)


@pytest.fixture
def m() -> ModuleType:
    try:
        module = import_module("scripts.research.synthetic_benchmark_match")
    except ModuleNotFoundError:
        pytest.fail("synthetic exact-time matching contract is not implemented")
    return module


def identity(m: ModuleType, **updates: Any) -> Any:
    item = m.FixtureIdentity(
        "INVENTED_NIFTY50", "fixture-v1", "PRICE_INDEX", "fixture", "a" * 64, 1
    )
    return replace(item, **updates) if updates else item


def timing(m: ModuleType, ts: datetime | None, **updates: Any) -> Any:
    item = m.Timing(m.Precision.EVENT_RESOLVED, ts)
    return replace(item, **updates) if updates else item


def fragment(m: ModuleType, name: str, quantity: int, ts: datetime, **updates: Any) -> Any:
    item = m.ExitFragment(name, quantity, timing(m, ts), m.FragmentStatus.EXECUTED, ts, ts)
    return replace(item, **updates) if updates else item


def trade(m: ModuleType, **updates: Any) -> Any:
    item = m.SyntheticTrade(
        100, timing(m, ENTRY), (fragment(m, "first", 25, EXIT1), fragment(m, "second", 75, EXIT2))
    )
    return replace(item, **updates) if updates else item


def observation(m: ModuleType, name: str, ts: datetime, price: Fraction, **updates: Any) -> Any:
    item = m.BenchmarkObservation(identity(m), name, ts, ts, price, m.ObservationState.OBSERVED)
    return replace(item, **updates) if updates else item


def observations(m: ModuleType, second: Fraction = Fraction(104)) -> tuple[Any, ...]:
    return (
        observation(m, "entry", ENTRY, Fraction(100)),
        observation(m, "first", EXIT1, Fraction(102)),
        observation(m, "second", EXIT2, second),
    )


def test_unequal_fragments_use_original_quantity_and_exact_rationals(m: ModuleType) -> None:
    result = m.match_benchmark(trade(m), observations(m), identity(m))
    assert result.benchmark_return == Fraction(7, 200)
    assert result.entry_matched is True and result.matched_exit_quantity == 100
    assert result.matched_exit_fragments == ("first", "second")
    assert not result.trade_refusals and all(leg.refusal is None for leg in result.legs)
    assert result.scope == "SYNTHETIC_DECLARATIONS_ONLY_NOT_MARKET_EVIDENCE"
    assert result.policy == "SYNTHETIC_EXACT_TIMESTAMP_ONLY"
    assert not hasattr(result, "alpha") and not hasattr(result, "confidence")


def test_missing_losing_fragment_cannot_release_favorable_subset(m: ModuleType) -> None:
    full = observations(m, Fraction(80))
    assert m.match_benchmark(trade(m), full, identity(m)).benchmark_return == Fraction(-29, 200)
    missing = m.match_benchmark(trade(m), full[:2], identity(m))
    assert missing.benchmark_return is None
    assert missing.entry_matched and missing.matched_exit_quantity == 25
    assert missing.matched_exit_fragments == ("first",)
    assert missing.legs[2].refusal is m.RefusalReason.MISSING_OBSERVATION


def test_flat_observed_benchmark_is_zero_not_unavailable(m: ModuleType) -> None:
    flat = tuple(replace(item, price=Fraction(100)) for item in observations(m))
    result = m.match_benchmark(trade(m), flat, identity(m))
    assert result.benchmark_return == Fraction(0)
    assert m.match_benchmark(trade(m), (), identity(m)).benchmark_return is None


@pytest.mark.parametrize("which", [0, 1, 2])
def test_late_availability_at_exact_event_refuses_whole_trade(m: ModuleType, which: int) -> None:
    rows = list(observations(m))
    rows[which] = replace(
        rows[which], available_ts=rows[which].event_ts + timedelta(microseconds=1)
    )
    result = m.match_benchmark(trade(m), tuple(rows), identity(m))
    assert result.benchmark_return is None
    assert result.legs[which].refusal is m.RefusalReason.LATE_AVAILABILITY


@pytest.mark.parametrize("precision", ["SESSION_ONLY", "BAR_RESOLVED"])
@pytest.mark.parametrize("which", ["entry", "first_exit"])
def test_daily_or_bar_labels_never_become_resolved_points(
    m: ModuleType, precision: str, which: str
) -> None:
    value = trade(m)
    ts = ENTRY if which == "entry" else EXIT1
    unresolved = timing(
        m, ts, precision=getattr(m.Precision, precision), interval_start=ts, interval_end=ts
    )
    if which == "entry":
        value = replace(value, entry_timing=unresolved)
    else:
        value = replace(value, exits=(replace(value.exits[0], timing=unresolved), value.exits[1]))
    result = m.match_benchmark(value, observations(m), identity(m))
    assert result.benchmark_return is None
    assert result.legs[0 if which == "entry" else 1].refusal is m.RefusalReason.UNRESOLVED_PRECISION


def test_nonzero_event_interval_is_not_an_exact_point(m: ModuleType) -> None:
    value = trade(
        m,
        entry_timing=timing(
            m, ENTRY, interval_start=ENTRY, interval_end=ENTRY + timedelta(minutes=15)
        ),
    )
    result = m.match_benchmark(value, observations(m), identity(m))
    assert (
        result.benchmark_return is None and result.legs[0].refusal is m.RefusalReason.AMBIGUOUS_TIME
    )


def test_missing_event_time_has_explicit_refusal(m: ModuleType) -> None:
    result = m.match_benchmark(trade(m, entry_timing=timing(m, None)), observations(m), identity(m))
    assert (
        result.benchmark_return is None
        and result.legs[0].refusal is m.RefusalReason.MISSING_EXECUTION_TIME
    )


@pytest.mark.parametrize("state", ["STALE", "SYNTHESIZED"])
def test_nonobserved_fixture_quotes_refuse(m: ModuleType, state: str) -> None:
    rows = list(observations(m))
    rows[1] = replace(rows[1], state=getattr(m.ObservationState, state))
    result = m.match_benchmark(trade(m), tuple(rows), identity(m))
    assert (
        result.benchmark_return is None
        and result.legs[1].refusal is m.RefusalReason.UNOBSERVED_QUOTE
    )


def test_stale_source_or_recognition_quote_cannot_complete_trade(m: ModuleType) -> None:
    value = trade(m)
    stale = replace(
        value.exits[1], status=m.FragmentStatus.STALE_MARK, recognition_ts=EXIT2 + timedelta(days=1)
    )
    rows = (*observations(m), observation(m, "recognition", stale.recognition_ts, Fraction(200)))
    result = m.match_benchmark(replace(value, exits=(value.exits[0], stale)), rows, identity(m))
    assert result.benchmark_return is None and result.legs[2].refusal is m.RefusalReason.STALE_MARK
    assert result.matched_exit_quantity == 25


@pytest.mark.parametrize("case", ["identical", "changed_price", "same_record_other_time"])
def test_duplicate_or_conflicting_quotes_are_never_overwritten(m: ModuleType, case: str) -> None:
    rows = observations(m)
    extra = rows[1]
    if case == "changed_price":
        extra = replace(extra, price=Fraction(999))
    elif case == "same_record_other_time":
        extra = replace(extra, event_ts=EXIT2, available_ts=EXIT2)
    result = m.match_benchmark(trade(m), (*rows, extra), identity(m))
    assert result.benchmark_return is None
    assert any(leg.refusal is m.RefusalReason.DUPLICATE_OBSERVATION for leg in result.legs)


@pytest.mark.parametrize(
    "field", ["benchmark_id", "benchmark_version", "price_basis", "artifact_id", "artifact_sha256"]
)
def test_incompatible_welltyped_declarations_refuse(m: ModuleType, field: str) -> None:
    rows = list(observations(m))
    wrong = "b" * 64 if field == "artifact_sha256" else "different"
    rows[1] = replace(rows[1], identity=identity(m, **{field: wrong}))
    result = m.match_benchmark(trade(m), tuple(rows), identity(m))
    assert (
        result.benchmark_return is None
        and result.legs[1].refusal is m.RefusalReason.INCOMPATIBLE_IDENTITY
    )


@pytest.mark.parametrize("quantity", [99, 101, 1000])
def test_incomplete_or_excess_quantity_is_not_partial_return(m: ModuleType, quantity: int) -> None:
    result = m.match_benchmark(trade(m, original_quantity=quantity), observations(m), identity(m))
    assert result.benchmark_return is None
    assert result.trade_refusals == (m.RefusalReason.QUANTITY_COVERAGE_MISMATCH,)
    assert result.entry_matched and result.matched_exit_quantity == 100


def test_empty_exit_set_is_welltyped_but_incomplete(m: ModuleType) -> None:
    result = m.match_benchmark(trade(m, exits=()), observations(m), identity(m))
    assert result.benchmark_return is None and result.trade_refusals
    assert result.matched_exit_quantity == 0


@pytest.mark.parametrize("invalid", [0, -1, True, 1.5])
def test_invalid_quantities_fail_constructor(m: ModuleType, invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        trade(m, original_quantity=invalid)
    with pytest.raises((TypeError, ValueError)):
        fragment(m, "bad", invalid, EXIT1)


@pytest.mark.parametrize(
    "invalid", [Fraction(0), Fraction(-1), float("inf"), float("nan"), Decimal("1"), 1, True]
)
def test_price_must_be_positive_exact_fraction(m: ModuleType, invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        observation(m, "bad", ENTRY, invalid)


@pytest.mark.parametrize(
    "invalid", [datetime(2020, 1, 2), ENTRY.astimezone(timezone(timedelta(hours=5, minutes=30)))]
)
def test_non_utc_or_naive_times_fail_constructor(m: ModuleType, invalid: datetime) -> None:
    with pytest.raises((TypeError, ValueError)):
        timing(m, invalid)
    with pytest.raises((TypeError, ValueError)):
        observation(m, "bad", invalid, Fraction(100))


@pytest.mark.parametrize("schema", [0, 2, True, "1"])
def test_schema_is_exact_supported_integer(m: ModuleType, schema: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        identity(m, schema_version=schema)


def test_impossible_availability_and_interval_fail_constructor(m: ModuleType) -> None:
    with pytest.raises(ValueError):
        observation(m, "bad", ENTRY, Fraction(100), available_ts=ENTRY - timedelta(seconds=1))
    with pytest.raises(ValueError):
        timing(m, ENTRY, interval_start=EXIT1, interval_end=ENTRY)
    with pytest.raises(ValueError):
        timing(m, ENTRY, interval_start=ENTRY)
    with pytest.raises(ValueError):
        timing(m, ENTRY, interval_start=EXIT1, interval_end=EXIT2)


def test_fragment_identity_chronology_and_point_contradictions_fail_constructor(
    m: ModuleType,
) -> None:
    value = trade(m)
    with pytest.raises(ValueError):
        trade(m, exits=(value.exits[0], value.exits[0]))
    with pytest.raises(ValueError):
        trade(m, exits=tuple(reversed(value.exits)))
    with pytest.raises(ValueError):
        trade(m, exits=(fragment(m, "early", 100, ENTRY - timedelta(seconds=1)),))
    with pytest.raises(ValueError):
        fragment(m, "bad", 100, EXIT1, recognition_ts=EXIT2)
    with pytest.raises(ValueError):
        fragment(m, "bad", 100, EXIT1, timing=timing(m, EXIT2))


def test_inputs_and_result_are_immutable_and_only_benchmark_arithmetic(m: ModuleType) -> None:
    value, rows, expected = trade(m), observations(m), identity(m)
    before = (value, rows, expected)
    result = m.match_benchmark(value, rows, expected)
    assert before == (value, rows, expected)
    with pytest.raises(FrozenInstanceError):
        result.benchmark_return = Fraction(1)
    with pytest.raises(FrozenInstanceError):
        value.original_quantity = 1
    assert isinstance(result.legs, tuple) and isinstance(result.trade_refusals, tuple)
    assert not hasattr(result, "market_eligible") and not hasattr(result, "excess_return")


def test_fragment_named_entry_has_an_unambiguous_exit_leg_identity(m: ModuleType) -> None:
    value = trade(m)
    value = replace(value, exits=(replace(value.exits[0], fragment_id="entry"), value.exits[1]))
    result = m.match_benchmark(value, observations(m), identity(m))
    assert tuple(leg.leg_id for leg in result.legs) == ("entry", "exit/entry", "exit/second")
    assert result.matched_exit_fragments == ("entry", "second")
