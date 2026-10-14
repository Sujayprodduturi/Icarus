"""Pure benchmark matching under declared policies, without source authentication."""

from bisect import bisect_right
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from fractions import Fraction
from types import MappingProxyType

from icarus.engine.timing import Precision as Precision
from icarus.engine.timing import Timing as Timing

SCOPE = "SYNTHETIC_DECLARATIONS_ONLY_NOT_MARKET_EVIDENCE"
POLICY = "SYNTHETIC_EXACT_TIMESTAMP_ONLY"


class FragmentStatus(StrEnum):
    EXECUTED = "executed"
    STALE_MARK = "stale_mark"


class ObservationState(StrEnum):
    OBSERVED = "observed_in_fixture"
    STALE = "stale"
    SYNTHESIZED = "synthesized"


class SelectionPolicy(StrEnum):
    EXACT = "exact"
    LATEST_AVAILABLE_OBSERVED = "latest_available_observed"


class RefusalReason(StrEnum):
    MISSING_EXECUTION_TIME = "missing_execution_time"
    UNRESOLVED_PRECISION = "unresolved_precision"
    AMBIGUOUS_TIME = "ambiguous_time"
    STALE_MARK = "stale_mark"
    MISSING_OBSERVATION = "missing_exact_observation"
    STALE_OBSERVATION = "stale_observation"
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
class MatchingPolicy:
    """Pinned mechanics; this declaration does not authenticate its source."""

    policy_id: str
    selection: SelectionPolicy
    max_age: timedelta

    def __post_init__(self) -> None:
        _text("policy_id", self.policy_id)
        if not isinstance(self.selection, SelectionPolicy):
            raise TypeError("selection must be SelectionPolicy")
        if type(self.max_age) is not timedelta:
            raise TypeError("max_age must be timedelta")
        if self.max_age < timedelta(0):
            raise ValueError("max_age cannot be negative")
        if self.selection is SelectionPolicy.EXACT and self.max_age != timedelta(0):
            raise ValueError("exact selection requires zero max_age")


DEFAULT_MATCHING_POLICY = MatchingPolicy(POLICY, SelectionPolicy.EXACT, timedelta(0))


@dataclass(frozen=True, slots=True)
class FixtureIdentity:
    """Expected benchmark/artifact metadata; supplies no external authentication."""

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
class ObservationIndex:
    """Validated immutable rows with logarithmic exact and causal queries."""

    observations: tuple[BenchmarkObservation, ...]
    duplicated: bool = field(init=False)
    _by_time: Mapping[datetime, BenchmarkObservation] = field(init=False, repr=False, compare=False)
    _available_times: tuple[datetime, ...] = field(init=False, repr=False, compare=False)
    _latest_event_prefix: tuple[BenchmarkObservation, ...] = field(
        init=False, repr=False, compare=False
    )

    def __post_init__(self) -> None:
        if type(self.observations) is not tuple or any(
            not isinstance(row, BenchmarkObservation) for row in self.observations
        ):
            raise TypeError("observations must be an immutable tuple of BenchmarkObservation")
        records = Counter(row.record_id for row in self.observations)
        events = Counter(row.event_ts for row in self.observations)
        duplicated = any(count > 1 for count in (*records.values(), *events.values()))
        object.__setattr__(self, "duplicated", duplicated)
        object.__setattr__(
            self,
            "_by_time",
            MappingProxyType(
                {} if duplicated else {row.event_ts: row for row in self.observations}
            ),
        )
        observed = sorted(
            (row for row in self.observations if row.state is ObservationState.OBSERVED),
            key=lambda row: (row.available_ts, row.event_ts, row.record_id),
        )
        prefix: list[BenchmarkObservation] = []
        latest: BenchmarkObservation | None = None
        for item in observed:
            if latest is None or item.event_ts > latest.event_ts:
                latest = item
            prefix.append(latest)
        object.__setattr__(self, "_available_times", tuple(row.available_ts for row in observed))
        object.__setattr__(self, "_latest_event_prefix", tuple(prefix))

    def exact(self, event_ts: datetime) -> BenchmarkObservation | None:
        return self._by_time.get(event_ts)

    def latest_available(self, fill_ts: datetime) -> BenchmarkObservation | None:
        offset = bisect_right(self._available_times, fill_ts) - 1
        if offset < 0:
            return None
        candidate = self._latest_event_prefix[offset]
        return candidate if candidate.event_ts <= fill_ts else None


@dataclass(frozen=True, slots=True)
class LegMatch:
    leg_id: str
    price: Fraction | None
    refusal: RefusalReason | None
    observation_record_id: str | None = None
    observation_event_ts: datetime | None = None
    observation_available_ts: datetime | None = None
    observation_age: timedelta | None = None


@dataclass(frozen=True, slots=True)
class BenchmarkMatch:
    benchmark_return: Fraction | None
    entry_matched: bool
    matched_exit_quantity: int
    matched_exit_fragments: tuple[str, ...]
    legs: tuple[LegMatch, ...]
    trade_refusals: tuple[RefusalReason, ...]
    scope: str = field(default=SCOPE, init=False)
    policy: str = field(default=POLICY)


def _refused(name: str, reason: RefusalReason) -> LegMatch:
    return LegMatch(name, None, reason)


def _match_leg(
    name: str,
    timing: Timing,
    expected: FixtureIdentity,
    index: ObservationIndex,
    policy: MatchingPolicy,
) -> LegMatch:
    if timing.precision is not Precision.EVENT_RESOLVED:
        return _refused(name, RefusalReason.UNRESOLVED_PRECISION)
    if timing.event_ts is None:
        return _refused(name, RefusalReason.MISSING_EXECUTION_TIME)
    if timing.interval_start is not None and timing.interval_start != timing.interval_end:
        return _refused(name, RefusalReason.AMBIGUOUS_TIME)
    if index.duplicated:
        return _refused(name, RefusalReason.DUPLICATE_OBSERVATION)
    fill_ts = timing.event_ts
    observation = (
        index.exact(fill_ts)
        if policy.selection is SelectionPolicy.EXACT
        else index.latest_available(fill_ts)
    )
    if observation is None:
        return _refused(name, RefusalReason.MISSING_OBSERVATION)
    age = fill_ts - observation.event_ts
    diagnostics = (
        observation.record_id,
        observation.event_ts,
        observation.available_ts,
        age,
    )
    if observation.identity != expected:
        return LegMatch(name, None, RefusalReason.INCOMPATIBLE_IDENTITY, *diagnostics)
    if observation.state is not ObservationState.OBSERVED:
        return LegMatch(name, None, RefusalReason.UNOBSERVED_QUOTE, *diagnostics)
    if observation.available_ts > fill_ts:
        return LegMatch(name, None, RefusalReason.LATE_AVAILABILITY, *diagnostics)
    if age < timedelta(0):
        return _refused(name, RefusalReason.MISSING_OBSERVATION)
    if age > policy.max_age:
        return LegMatch(name, None, RefusalReason.STALE_OBSERVATION, *diagnostics)
    return LegMatch(name, observation.price, None, *diagnostics)


def match_benchmark(
    trade: SyntheticTrade,
    observations: tuple[BenchmarkObservation, ...],
    expected: FixtureIdentity,
    policy: MatchingPolicy = DEFAULT_MATCHING_POLICY,
    index: ObservationIndex | None = None,
) -> BenchmarkMatch:
    """Match a complete trade under one declared policy or return explicit refusals."""
    if not isinstance(trade, SyntheticTrade) or not isinstance(expected, FixtureIdentity):
        raise TypeError("trade/expected must be typed declarations")
    if not isinstance(policy, MatchingPolicy):
        raise TypeError("policy must be MatchingPolicy")
    if index is not None and not isinstance(index, ObservationIndex):
        raise TypeError("index must be ObservationIndex or None")
    selected_index = ObservationIndex(observations) if index is None else index
    if selected_index.observations is not observations:
        raise ValueError("index does not describe the supplied observations tuple")
    entry = _match_leg("entry", trade.entry_timing, expected, selected_index, policy)
    exits = tuple(
        _refused(f"exit/{item.fragment_id}", RefusalReason.STALE_MARK)
        if item.status is FragmentStatus.STALE_MARK
        else _match_leg(f"exit/{item.fragment_id}", item.timing, expected, selected_index, policy)
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
        value,
        entry.price is not None,
        matched_quantity,
        matched,
        (entry, *exits),
        trade_refusals,
        policy=policy.policy_id,
    )


__all__ = [
    "DEFAULT_MATCHING_POLICY",
    "POLICY",
    "SCOPE",
    "BenchmarkMatch",
    "BenchmarkObservation",
    "ExitFragment",
    "FixtureIdentity",
    "FragmentStatus",
    "LegMatch",
    "MatchingPolicy",
    "ObservationIndex",
    "ObservationState",
    "Precision",
    "RefusalReason",
    "SelectionPolicy",
    "SyntheticTrade",
    "Timing",
    "match_benchmark",
]
