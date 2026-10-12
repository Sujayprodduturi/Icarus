"""Exact benchmark arithmetic under declared invented timing, never market evidence.

This pure helper has no I/O or product integration. Fixture identity and hashes are declarations,
not source or calendar certification. Local quote coverage never implies a partial trade return.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from fractions import Fraction

SCOPE = "SYNTHETIC_DECLARATIONS_ONLY_NOT_MARKET_EVIDENCE"
POLICY = "SYNTHETIC_EXACT_TIMESTAMP_ONLY"


class Precision(StrEnum):
    SESSION_ONLY = "session_only"
    BAR_RESOLVED = "bar_resolved"
    EVENT_RESOLVED = "event_resolved"


class FragmentStatus(StrEnum):
    EXECUTED = "executed"
    STALE_MARK = "stale_mark"


class ObservationState(StrEnum):
    OBSERVED = "observed_in_fixture"
    STALE = "stale"
    SYNTHESIZED = "synthesized"


class RefusalReason(StrEnum):
    MISSING_EXECUTION_TIME = "missing_execution_time"
    UNRESOLVED_PRECISION = "unresolved_precision"
    AMBIGUOUS_TIME = "ambiguous_time"
    STALE_MARK = "stale_mark"
    MISSING_OBSERVATION = "missing_exact_observation"
    LATE_AVAILABILITY = "late_availability"
    UNOBSERVED_QUOTE = "unobserved_quote"
    INCOMPATIBLE_IDENTITY = "incompatible_fixture_identity"
    DUPLICATE_OBSERVATION = "duplicate_or_conflicting_observation"
    QUANTITY_COVERAGE_MISMATCH = "quantity_coverage_mismatch"


def _text(name: str, value: str) -> None:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def _utc(name: str, value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is not UTC:
        raise ValueError(f"{name} must be a datetime using datetime.UTC")


def _quantity(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive whole quantity")


@dataclass(frozen=True, slots=True)
class FixtureIdentity:
    """Expected invented benchmark/artifact metadata; supplies no external authentication."""

    benchmark_id: str
    benchmark_version: str
    price_basis: str
    artifact_id: str
    artifact_sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        for name in ("benchmark_id", "benchmark_version", "price_basis", "artifact_id"):
            _text(name, getattr(self, name))
        if (
            type(self.artifact_sha256) is not str
            or len(self.artifact_sha256) != 64
            or any(character not in "0123456789abcdef" for character in self.artifact_sha256)
        ):
            raise ValueError("artifact_sha256 must be a lowercase SHA256 declaration")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("only integer fixture schema_version 1 is supported")


@dataclass(frozen=True, slots=True)
class Timing:
    precision: Precision
    event_ts: datetime | None = None
    interval_start: datetime | None = None
    interval_end: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.precision, Precision):
            raise TypeError("precision must be Precision")
        for name in ("event_ts", "interval_start", "interval_end"):
            value = getattr(self, name)
            if value is not None:
                _utc(name, value)
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval bounds must both be present or both absent")
        if self.interval_start is not None and self.interval_end is not None:
            if self.interval_end < self.interval_start:
                raise ValueError("interval end precedes start")
            if (
                self.event_ts is not None
                and not self.interval_start <= self.event_ts <= self.interval_end
            ):
                raise ValueError("declared event lies outside its interval")


@dataclass(frozen=True, slots=True)
class ExitFragment:
    fragment_id: str
    quantity: int
    timing: Timing
    status: FragmentStatus
    price_source_ts: datetime
    recognition_ts: datetime

    def __post_init__(self) -> None:
        _text("fragment_id", self.fragment_id)
        _quantity("quantity", self.quantity)
        if not isinstance(self.timing, Timing) or not isinstance(self.status, FragmentStatus):
            raise TypeError("fragment timing/status must be typed declarations")
        _utc("price_source_ts", self.price_source_ts)
        _utc("recognition_ts", self.recognition_ts)
        if self.recognition_ts < self.price_source_ts:
            raise ValueError("recognition precedes price source")
        if self.status is FragmentStatus.EXECUTED:
            if self.recognition_ts != self.price_source_ts:
                raise ValueError("an executed fragment must be recognized at its price-source time")
            if self.timing.event_ts is not None and self.timing.event_ts != self.price_source_ts:
                raise ValueError("executed event contradicts its price-source time")


@dataclass(frozen=True, slots=True)
class SyntheticTrade:
    original_quantity: int
    entry_timing: Timing
    exits: tuple[ExitFragment, ...]

    def __post_init__(self) -> None:
        _quantity("original_quantity", self.original_quantity)
        if not isinstance(self.entry_timing, Timing):
            raise TypeError("entry_timing must be Timing")
        if type(self.exits) is not tuple or any(
            not isinstance(item, ExitFragment) for item in self.exits
        ):
            raise TypeError("exits must be an immutable tuple of ExitFragment")
        ids = [item.fragment_id for item in self.exits]
        if len(set(ids)) != len(ids):
            raise ValueError("exit fragment identities must be unique")
        previous_source = self.entry_timing.event_ts or self.entry_timing.interval_start
        previous_recognition = previous_source
        for item in self.exits:
            if previous_source is not None and item.price_source_ts < previous_source:
                raise ValueError("exit price-source times precede entry or earlier exits")
            if previous_recognition is not None and item.recognition_ts < previous_recognition:
                raise ValueError("exit recognition times precede entry or earlier exits")
            previous_source, previous_recognition = item.price_source_ts, item.recognition_ts


@dataclass(frozen=True, slots=True)
class BenchmarkObservation:
    identity: FixtureIdentity
    record_id: str
    event_ts: datetime
    available_ts: datetime
    price: Fraction
    state: ObservationState

    def __post_init__(self) -> None:
        if not isinstance(self.identity, FixtureIdentity) or not isinstance(
            self.state, ObservationState
        ):
            raise TypeError("observation identity/state must be typed declarations")
        _text("record_id", self.record_id)
        _utc("event_ts", self.event_ts)
        _utc("available_ts", self.available_ts)
        if self.available_ts < self.event_ts:
            raise ValueError("observation cannot be available before its event")
        if type(self.price) is not Fraction or self.price <= 0:
            raise ValueError("fixture price must be a positive exact Fraction")


@dataclass(frozen=True, slots=True)
class LegMatch:
    leg_id: str
    price: Fraction | None
    refusal: RefusalReason | None


@dataclass(frozen=True, slots=True)
class BenchmarkMatch:
    """Coverage describes eligible local quotes, never an available subset benchmark return."""

    benchmark_return: Fraction | None
    entry_matched: bool
    matched_exit_quantity: int
    matched_exit_fragments: tuple[str, ...]
    legs: tuple[LegMatch, ...]
    trade_refusals: tuple[RefusalReason, ...]
    scope: str = field(default=SCOPE, init=False)
    policy: str = field(default=POLICY, init=False)


def _match_leg(
    name: str,
    timing: Timing,
    expected: FixtureIdentity,
    by_time: dict[datetime, BenchmarkObservation],
    duplicated: bool,
) -> LegMatch:
    reason = None
    if timing.precision is not Precision.EVENT_RESOLVED:
        reason = RefusalReason.UNRESOLVED_PRECISION
    elif timing.event_ts is None:
        reason = RefusalReason.MISSING_EXECUTION_TIME
    elif timing.interval_start is not None and timing.interval_start != timing.interval_end:
        reason = RefusalReason.AMBIGUOUS_TIME
    elif duplicated:
        reason = RefusalReason.DUPLICATE_OBSERVATION
    if reason is not None:
        return LegMatch(name, None, reason)
    assert timing.event_ts is not None
    observation = by_time.get(timing.event_ts)
    if observation is None:
        return LegMatch(name, None, RefusalReason.MISSING_OBSERVATION)
    if observation.identity != expected:
        return LegMatch(name, None, RefusalReason.INCOMPATIBLE_IDENTITY)
    if observation.state is not ObservationState.OBSERVED:
        return LegMatch(name, None, RefusalReason.UNOBSERVED_QUOTE)
    if observation.available_ts > timing.event_ts:
        return LegMatch(name, None, RefusalReason.LATE_AVAILABILITY)
    return LegMatch(name, observation.price, None)


def match_benchmark(
    trade: SyntheticTrade,
    observations: tuple[BenchmarkObservation, ...],
    expected: FixtureIdentity,
) -> BenchmarkMatch:
    """Match the complete invented trade or return None with explicit immutable diagnostics."""
    if not isinstance(trade, SyntheticTrade) or not isinstance(expected, FixtureIdentity):
        raise TypeError("trade/expected must be typed synthetic declarations")
    if type(observations) is not tuple or any(
        not isinstance(row, BenchmarkObservation) for row in observations
    ):
        raise TypeError("observations must be an immutable tuple of BenchmarkObservation")
    record_counts = Counter(row.record_id for row in observations)
    time_counts = Counter(row.event_ts for row in observations)
    duplicated = any(count > 1 for count in (*record_counts.values(), *time_counts.values()))
    by_time = {row.event_ts: row for row in observations} if not duplicated else {}
    entry = _match_leg("entry", trade.entry_timing, expected, by_time, duplicated)
    exits = tuple(
        LegMatch(f"exit/{item.fragment_id}", None, RefusalReason.STALE_MARK)
        if item.status is FragmentStatus.STALE_MARK
        else _match_leg(f"exit/{item.fragment_id}", item.timing, expected, by_time, duplicated)
        for item in trade.exits
    )
    quantity = sum(item.quantity for item in trade.exits)
    trade_refusals = (
        () if quantity == trade.original_quantity else (RefusalReason.QUANTITY_COVERAGE_MISMATCH,)
    )
    matched = tuple(
        item.fragment_id
        for item, leg in zip(trade.exits, exits, strict=True)
        if leg.price is not None
    )
    matched_quantity = sum(
        item.quantity for item, leg in zip(trade.exits, exits, strict=True) if leg.price is not None
    )
    value = None
    if (
        not trade_refusals
        and entry.price is not None
        and all(leg.price is not None for leg in exits)
    ):
        value = sum(
            (
                Fraction(item.quantity, trade.original_quantity) * (leg.price / entry.price - 1)
                for item, leg in zip(trade.exits, exits, strict=True)
                if leg.price is not None
            ),
            Fraction(0),
        )
    return BenchmarkMatch(
        value, entry.price is not None, matched_quantity, matched, (entry, *exits), trade_refusals
    )
