"""Pure, synthetic-only boundary for signal-run statistical diagnostics.

This module validates that every recorded outcome belongs to one caller-supplied canonical
source-session axis, then reports descriptive raw-return and win-rate summaries. The CR2 kernel,
intervals, benchmark matching, and placebo engine are deliberately outside this first slice.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from icarus.common.config import SignalTest
from icarus.engine.signaltest import SignalRunResult
from icarus.engine.simcore import SignalId

METHOD_VERSION = "entry-session-cr2-satterthwaite-v1"


class MetricRefusal(enum.StrEnum):
    """Why a metric cannot advance beyond its available descriptive evidence."""

    EMPTY_SAMPLE = "empty_sample"
    TOO_FEW_BLOCKS = "too_few_blocks"
    ZERO_VARIANCE = "zero_variance"
    INVALID_VARIANCE = "invalid_variance"
    INVALID_DF = "invalid_df"
    MISSING_BENCHMARK = "missing_benchmark"
    INDEFENSIBLE_PLACEBO_NULL = "indefensible_placebo_null"


@dataclass(frozen=True, slots=True)
class MetricObservation:
    """One filled signal's value and canonical entry-session coordinates."""

    signal_id: SignalId
    entry_session_index: int
    holding_sessions: int
    value: Decimal

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId):
            raise TypeError("MetricObservation.signal_id must be a SignalId")
        _require_nonnegative_index(
            "MetricObservation.entry_session_index", self.entry_session_index
        )
        if type(self.holding_sessions) is not int or self.holding_sessions <= 0:
            raise ValueError("MetricObservation.holding_sessions must be a positive whole count")
        _finite_float64_decimal("MetricObservation.value", self.value)


@dataclass(frozen=True, slots=True)
class SourceSessionAxis:
    """Canonical full-source daily sessions and the fixed analysis origin."""

    sessions: tuple[tuple[int, datetime], ...]
    study_origin_index: int

    def __post_init__(self) -> None:
        _require_nonnegative_index("SourceSessionAxis.study_origin_index", self.study_origin_index)
        if type(self.sessions) is not tuple or not self.sessions:
            raise ValueError("SourceSessionAxis.sessions must be a nonempty immutable tuple")

        prior_index: int | None = None
        prior_ts: datetime | None = None
        indices: set[int] = set()
        for position, session in enumerate(self.sessions):
            if type(session) is not tuple or len(session) != 2:
                raise TypeError(
                    "SourceSessionAxis.sessions must contain (source_index, UTC datetime) tuples"
                )
            index, ts = session
            _require_nonnegative_index(f"SourceSessionAxis.sessions[{position}].index", index)
            _require_utc(f"SourceSessionAxis.sessions[{position}].timestamp", ts)
            if prior_index is not None and index != prior_index + 1:
                raise ValueError(
                    "SourceSessionAxis session indices must be contiguous and strictly increasing"
                )
            if prior_ts is not None and ts <= prior_ts:
                raise ValueError("SourceSessionAxis timestamps must be strictly increasing")
            indices.add(index)
            prior_index = index
            prior_ts = ts

        if self.study_origin_index not in indices:
            raise ValueError("SourceSessionAxis.study_origin_index must be present in sessions")


@dataclass(frozen=True, slots=True)
class CandidateMoments:
    """Candidate CR2/Satterthwaite diagnostics populated by the next implementation task."""

    count: int
    block_counts: tuple[tuple[int, int], ...]
    mean: float
    sample_variance: float
    cr2_variance: float
    degrees_of_freedom: float
    design_effect: float
    effective_n_uncapped: float
    effective_n_display: float
    effective_n_capped: bool


@dataclass(frozen=True, slots=True)
class MetricDiagnostic:
    """One metric's descriptive result, future candidate moments, and typed refusal."""

    count: int
    mean: float | None
    moments: CandidateMoments | None
    refusal: MetricRefusal | None

    def __post_init__(self) -> None:
        _require_nonnegative_count("MetricDiagnostic.count", self.count)
        if self.mean is None:
            if self.count != 0:
                raise ValueError("MetricDiagnostic.mean is required when count is positive")
        elif type(self.mean) is not float or not math.isfinite(self.mean):
            raise ValueError("MetricDiagnostic.mean must be a finite float or None")
        if self.moments is not None:
            if not isinstance(self.moments, CandidateMoments):
                raise TypeError("MetricDiagnostic.moments must be CandidateMoments or None")
            if self.moments.count != self.count or self.moments.mean != self.mean:
                raise ValueError("MetricDiagnostic moments must describe the same count and mean")
            if self.refusal is not None:
                raise ValueError("MetricDiagnostic cannot carry moments and a refusal together")
        if self.refusal is not None and not isinstance(self.refusal, MetricRefusal):
            raise TypeError("MetricDiagnostic.refusal must be MetricRefusal or None")
        if self.count == 0 and self.refusal is None:
            raise ValueError("an empty MetricDiagnostic requires a typed refusal")


@dataclass(frozen=True, slots=True)
class SignalDiagnostics:
    """Descriptive signal-run diagnostics with no interval, p-value, or promotion state."""

    raw_return: MetricDiagnostic
    win_rate: MetricDiagnostic
    benchmark_excess: MetricDiagnostic
    placebo: MetricDiagnostic
    filled_count: int
    skip_count: int
    missing_count: int
    longest_holding_sessions: int | None
    block_length: int | None
    study_origin_index: int
    method_version: str

    def __post_init__(self) -> None:
        for name in ("raw_return", "win_rate", "benchmark_excess", "placebo"):
            if not isinstance(getattr(self, name), MetricDiagnostic):
                raise TypeError(f"SignalDiagnostics.{name} must be a MetricDiagnostic")
        for name in ("filled_count", "skip_count", "missing_count"):
            _require_nonnegative_count(f"SignalDiagnostics.{name}", getattr(self, name))
        if self.raw_return.count != self.filled_count or self.win_rate.count != self.filled_count:
            raise ValueError("raw-return and win-rate counts must equal filled_count")
        if (self.longest_holding_sessions is None) != (self.block_length is None):
            raise ValueError("holding-session and block-length provenance must be present together")
        if self.longest_holding_sessions is not None:
            if type(self.longest_holding_sessions) is not int or self.longest_holding_sessions <= 0:
                raise ValueError("longest_holding_sessions must be a positive whole count")
            if type(self.block_length) is not int or self.block_length <= 0:
                raise ValueError("block_length must be a positive whole count")
        _require_nonnegative_index("SignalDiagnostics.study_origin_index", self.study_origin_index)
        if not isinstance(self.method_version, str) or not self.method_version.strip():
            raise ValueError("SignalDiagnostics.method_version must be a nonempty string")


def summarize_signal_run(
    run: SignalRunResult,
    *,
    source_axis: SourceSessionAxis,
    settings: SignalTest,
) -> SignalDiagnostics:
    """Validate run provenance and return synthetic-only descriptive diagnostics."""
    if not isinstance(run, SignalRunResult):
        raise TypeError("run must be a SignalRunResult")
    if not isinstance(source_axis, SourceSessionAxis):
        raise TypeError("source_axis must be a SourceSessionAxis")
    if not isinstance(settings, SignalTest):
        raise TypeError("settings must be an already validated SignalTest")
    if settings.inference_enabled:
        raise ValueError("signal inference remains disabled")

    axis_by_index = dict(source_axis.sessions)
    observations: list[MetricObservation] = []
    for trade in run.trades:
        _require_axis_coordinate(
            axis_by_index,
            trade.signal_id.decision_index,
            trade.signal_id.decision_ts,
            "signal decision",
        )
        _require_axis_coordinate(axis_by_index, trade.entry_index, trade.entry_ts, "trade entry")
        if trade.entry_index < source_axis.study_origin_index:
            raise ValueError("trade entry cannot precede the fixed study origin")
        for fragment in trade.exit_fragments:
            _require_axis_coordinate(
                axis_by_index,
                fragment.price_source_index,
                fragment.price_source_ts,
                "exit price source",
            )
            _require_axis_coordinate(
                axis_by_index,
                fragment.recognition_index,
                fragment.recognition_ts,
                "exit recognition",
            )
        observations.append(
            MetricObservation(
                signal_id=trade.signal_id,
                entry_session_index=trade.entry_index,
                holding_sessions=trade.holding_sessions,
                value=trade.net_return,
            )
        )

    for skipped in run.skips:
        _require_axis_coordinate(
            axis_by_index,
            skipped.signal_id.decision_index,
            skipped.signal_id.decision_ts,
            "skipped signal decision",
        )
    for missing in run.missing:
        _require_axis_coordinate(
            axis_by_index,
            missing.decision_index,
            missing.decision_ts,
            "missing signal decision",
        )

    if not observations:
        raw_return = _unavailable(MetricRefusal.EMPTY_SAMPLE)
        win_rate = _unavailable(MetricRefusal.EMPTY_SAMPLE)
        longest_holding_sessions = None
        block_length = None
    else:
        longest_holding_sessions = max(item.holding_sessions for item in observations)
        block_length = max(
            settings.block_min_sessions,
            settings.holding_period_block_multiplier * longest_holding_sessions,
        )
        block_ids = tuple(
            (item.entry_session_index - source_axis.study_origin_index) // block_length
            for item in observations
        )
        raw_return = _describe(tuple(item.value for item in observations), block_ids)
        win_rate = _describe(
            tuple(Decimal(1) if item.value > 0 else Decimal(0) for item in observations),
            block_ids,
        )

    return SignalDiagnostics(
        raw_return=raw_return,
        win_rate=win_rate,
        benchmark_excess=_unavailable(MetricRefusal.MISSING_BENCHMARK),
        placebo=_unavailable(MetricRefusal.INDEFENSIBLE_PLACEBO_NULL),
        filled_count=len(run.trades),
        skip_count=len(run.skips),
        missing_count=len(run.missing),
        longest_holding_sessions=longest_holding_sessions,
        block_length=block_length,
        study_origin_index=source_axis.study_origin_index,
        method_version=METHOD_VERSION,
    )


def _describe(values: tuple[Decimal, ...], block_ids: tuple[int, ...]) -> MetricDiagnostic:
    mean = float(sum(values, Decimal(0)) / len(values))
    if not math.isfinite(mean):
        raise ValueError("descriptive mean must be representable as a finite float64")
    refusal: MetricRefusal | None = None
    if len(values) < 2 or len(set(block_ids)) < 2:
        refusal = MetricRefusal.TOO_FEW_BLOCKS
    elif len(set(values)) == 1:
        refusal = MetricRefusal.ZERO_VARIANCE
    return MetricDiagnostic(count=len(values), mean=mean, moments=None, refusal=refusal)


def _unavailable(refusal: MetricRefusal) -> MetricDiagnostic:
    return MetricDiagnostic(count=0, mean=None, moments=None, refusal=refusal)


def _require_axis_coordinate(
    axis_by_index: dict[int, datetime], index: int, ts: datetime, label: str
) -> None:
    _require_nonnegative_index(f"{label} index", index)
    _require_utc(f"{label} timestamp", ts)
    if axis_by_index.get(index) != ts:
        raise ValueError(f"{label} does not match the supplied canonical source axis")


def _require_nonnegative_index(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative whole index")


def _require_nonnegative_count(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative whole count")


def _require_utc(name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is not UTC:
        raise ValueError(f"{name} must use datetime.UTC")


def _finite_float64_decimal(name: str, value: Decimal) -> float:
    if not isinstance(value, Decimal):
        raise TypeError(f"{name} must be a Decimal")
    if not value.is_finite():
        raise ValueError(f"{name} must be representable as a finite float64")
    converted = float(value)
    if not math.isfinite(converted):
        raise ValueError(f"{name} must be representable as a finite float64")
    return converted


__all__ = [
    "CandidateMoments",
    "MetricDiagnostic",
    "MetricObservation",
    "MetricRefusal",
    "SignalDiagnostics",
    "SourceSessionAxis",
    "summarize_signal_run",
]
