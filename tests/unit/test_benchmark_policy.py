"""Declared benchmark matching policies remain causal and fail closed."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta
from fractions import Fraction
from typing import Any, cast

import pytest

from icarus.engine.benchmark_match import (
    DEFAULT_MATCHING_POLICY,
    POLICY,
    SCOPE,
    BenchmarkObservation,
    ExitFragment,
    FixtureIdentity,
    FragmentStatus,
    MatchingPolicy,
    ObservationIndex,
    ObservationState,
    Precision,
    RefusalReason,
    SelectionPolicy,
    SyntheticTrade,
    Timing,
    match_benchmark,
)

ENTRY = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
EXIT = ENTRY + timedelta(days=1)


def identity(**updates: Any) -> FixtureIdentity:
    value = FixtureIdentity("INVENTED", "v1", "PRICE_INDEX", "artifact", "a" * 64)
    return replace(value, **updates) if updates else value


def timing(ts: datetime) -> Timing:
    return Timing(Precision.EVENT_RESOLVED, ts)


def trade() -> SyntheticTrade:
    return SyntheticTrade(
        10,
        timing(ENTRY),
        (ExitFragment("all", 10, timing(EXIT), FragmentStatus.EXECUTED, EXIT, EXIT),),
    )


def row(name: str, event: datetime, available: datetime, price: int) -> BenchmarkObservation:
    return BenchmarkObservation(
        identity(), name, event, available, Fraction(price), ObservationState.OBSERVED
    )


def policy(age: timedelta) -> MatchingPolicy:
    return MatchingPolicy("invented-asof-v1", SelectionPolicy.LATEST_AVAILABLE_OBSERVED, age)


def test_default_api_remains_exact_zero_age_and_synthetic_labelled() -> None:
    rows = (row("entry", ENTRY, ENTRY, 100), row("exit", EXIT, EXIT, 110))
    result = match_benchmark(trade(), rows, identity())
    assert result.benchmark_return == Fraction(1, 10)
    assert result.scope == SCOPE == "SYNTHETIC_DECLARATIONS_ONLY_NOT_MARKET_EVIDENCE"
    assert result.policy == POLICY == "SYNTHETIC_EXACT_TIMESTAMP_ONLY"
    assert DEFAULT_MATCHING_POLICY.selection is SelectionPolicy.EXACT
    assert DEFAULT_MATCHING_POLICY.max_age == timedelta(0)


def test_latest_policy_selects_latest_causally_available_observed_row() -> None:
    rows = (
        row("entry-old", ENTRY - timedelta(minutes=4), ENTRY - timedelta(minutes=3), 100),
        row(
            "entry-later-but-late", ENTRY - timedelta(minutes=1), ENTRY + timedelta(seconds=1), 900
        ),
        row("exit", EXIT, EXIT, 110),
    )
    result = match_benchmark(trade(), rows, identity(), policy(timedelta(minutes=5)))
    assert result.benchmark_return == Fraction(1, 10)
    assert result.policy == "invented-asof-v1"
    assert result.legs[0].observation_record_id == "entry-old"
    assert result.legs[0].observation_event_ts == ENTRY - timedelta(minutes=4)
    assert result.legs[0].observation_available_ts == ENTRY - timedelta(minutes=3)
    assert result.legs[0].observation_age == timedelta(minutes=4)


@pytest.mark.parametrize(
    ("changed", "refusal"),
    [
        ({"state": ObservationState.STALE}, RefusalReason.MISSING_OBSERVATION),
        (
            {
                "event_ts": ENTRY + timedelta(seconds=1),
                "available_ts": ENTRY + timedelta(seconds=1),
            },
            RefusalReason.MISSING_OBSERVATION,
        ),
        ({"available_ts": ENTRY + timedelta(seconds=1)}, RefusalReason.MISSING_OBSERVATION),
    ],
)
def test_asof_never_uses_unobserved_future_or_late_rows(
    changed: dict[str, object], refusal: RefusalReason
) -> None:
    candidate = replace(row("candidate", ENTRY, ENTRY, 100), **cast(Any, changed))
    rows = (candidate, row("exit", EXIT, EXIT, 110))
    result = match_benchmark(trade(), rows, identity(), policy(timedelta(minutes=5)))
    assert result.benchmark_return is None
    assert result.legs[0].refusal is refusal


def test_asof_refuses_stale_observation_instead_of_silent_forward_fill() -> None:
    rows = (
        row("entry", ENTRY - timedelta(minutes=6), ENTRY - timedelta(minutes=6), 100),
        row("exit", EXIT, EXIT, 110),
    )
    result = match_benchmark(trade(), rows, identity(), policy(timedelta(minutes=5)))
    assert result.benchmark_return is None
    assert result.legs[0].refusal is RefusalReason.STALE_OBSERVATION


def test_exact_policy_keeps_late_availability_diagnostic() -> None:
    rows = (row("entry", ENTRY, ENTRY + timedelta(seconds=1), 100), row("exit", EXIT, EXIT, 110))
    result = match_benchmark(trade(), rows, identity())
    assert result.legs[0].refusal is RefusalReason.LATE_AVAILABILITY


def test_reusable_index_matches_direct_path_and_is_immutable() -> None:
    rows = (row("entry", ENTRY, ENTRY, 100), row("exit", EXIT, EXIT, 110))
    index = ObservationIndex(rows)
    assert match_benchmark(trade(), rows, identity(), index=index) == match_benchmark(
        trade(), rows, identity()
    )
    mutable: Any = index
    with pytest.raises(FrozenInstanceError):
        mutable.observations = ()
    with pytest.raises(ValueError, match="does not describe"):
        match_benchmark(trade(), rows[:-1], identity(), index=index)


def test_reusable_index_exact_cache_cannot_be_mutated_after_validation() -> None:
    rows = (row("entry", ENTRY, ENTRY, 100), row("exit", EXIT, EXIT, 110))
    index = ObservationIndex(rows)
    internal: Any = index
    with pytest.raises(TypeError):
        internal._by_time[ENTRY] = row("replacement", ENTRY, ENTRY, 999)
    assert index.exact(ENTRY) is rows[0]


def test_duplicate_anywhere_poisoning_is_preserved_in_reusable_index() -> None:
    rows = (
        row("entry", ENTRY, ENTRY, 100),
        row("exit", EXIT, EXIT, 110),
        row("entry", ENTRY - timedelta(days=20), ENTRY - timedelta(days=20), 1),
    )
    result = match_benchmark(trade(), rows, identity(), index=ObservationIndex(rows))
    assert result.benchmark_return is None
    assert all(leg.refusal is RefusalReason.DUPLICATE_OBSERVATION for leg in result.legs)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"policy_id": ""},
        {"policy_id": True},
        {"selection": "exact"},
        {"selection": True},
        {"max_age": -timedelta(microseconds=1)},
        {"max_age": 0},
        {"max_age": float("nan")},
        {"max_age": True},
    ],
)
def test_policy_rejects_untyped_or_negative_fields(kwargs: dict[str, object]) -> None:
    values: dict[str, object] = {
        "policy_id": "pinned-v1",
        "selection": SelectionPolicy.EXACT,
        "max_age": timedelta(0),
    }
    values.update(kwargs)
    with pytest.raises((TypeError, ValueError)):
        MatchingPolicy(**values)  # type: ignore[arg-type]


def test_match_rejects_untyped_policy_and_index() -> None:
    rows = (row("entry", ENTRY, ENTRY, 100), row("exit", EXIT, EXIT, 110))
    with pytest.raises(TypeError):
        match_benchmark(trade(), rows, identity(), policy=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError):
        match_benchmark(trade(), rows, identity(), index=True)  # type: ignore[arg-type]
