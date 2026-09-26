"""Pure, synthetic-only boundary for candidate signal-run statistical diagnostics.

This module validates every outcome against a caller-supplied canonical source-session axis and
computes descriptive raw-return and win-rate summaries with candidate CR2/Satterthwaite moments.
Intervals, benchmark matching, and the placebo engine remain deliberately unavailable.
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
            if prior_ts is not None and ts.date() <= prior_ts.date():
                raise ValueError("SourceSessionAxis UTC dates must be strictly increasing")
            indices.add(index)
            prior_index = index
            prior_ts = ts

        if self.study_origin_index not in indices:
            raise ValueError("SourceSessionAxis.study_origin_index must be present in sessions")


@dataclass(frozen=True, slots=True)
class CandidateMoments:
    """Candidate CR2/Satterthwaite diagnostics without interval or calibration claims."""

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


def _cr2_moments(
    values: tuple[float, ...], block_ids: tuple[int, ...]
) -> CandidateMoments | MetricRefusal:
    """Compute candidate CR2/Satterthwaite moments for occupied time blocks."""
    count = len(values)
    if count == 0:
        return MetricRefusal.EMPTY_SAMPLE
    if len(block_ids) != count:
        raise ValueError("values and block_ids must have equal length")

    grouped: dict[int, list[float]] = {}
    for value, block_id in zip(values, block_ids, strict=True):
        if type(value) is not float or not math.isfinite(value):
            raise ValueError("CR2 values must be finite floats")
        if type(block_id) is not int:
            raise TypeError("CR2 block IDs must be whole integers")
        grouped.setdefault(block_id, []).append(value)

    block_counts = tuple((block_id, len(grouped[block_id])) for block_id in sorted(grouped))
    if count < 2 or len(block_counts) < 2:
        return MetricRefusal.TOO_FEW_BLOCKS

    try:
        mean = math.fsum(values) / count
        sample_variance = math.fsum((value - mean) ** 2 for value in values) / (count - 1)
    except OverflowError:
        return MetricRefusal.INVALID_VARIANCE
    if not math.isfinite(mean) or not math.isfinite(sample_variance):
        return MetricRefusal.INVALID_VARIANCE
    if sample_variance == 0.0:
        if all(value == values[0] for value in values):
            return MetricRefusal.ZERO_VARIANCE
        return MetricRefusal.INVALID_VARIANCE
    if sample_variance < 0.0:
        return MetricRefusal.INVALID_VARIANCE

    try:
        variance_terms = []
        scores = []
        for block_id, block_count in block_counts:
            leverage = block_count / count
            score = math.fsum(value - mean for value in grouped[block_id])
            scores.append(score)
            variance_terms.append(score * score / (1.0 - leverage))
        cr2_variance = math.fsum(variance_terms) / (count * count)
    except OverflowError:
        return MetricRefusal.INVALID_VARIANCE
    if cr2_variance == 0.0:
        if all(score == 0.0 for score in scores):
            return MetricRefusal.ZERO_VARIANCE
        return MetricRefusal.INVALID_VARIANCE
    if not math.isfinite(cr2_variance) or cr2_variance < 0.0:
        return MetricRefusal.INVALID_VARIANCE

    try:
        k_matrix = tuple(
            tuple(
                ((left_count if left_id == right_id else 0.0) - left_count * right_count / count)
                / (
                    count
                    * count
                    * math.sqrt((1.0 - left_count / count) * (1.0 - right_count / count))
                )
                for right_id, right_count in block_counts
            )
            for left_id, left_count in block_counts
        )
        trace = math.fsum(k_matrix[index][index] for index in range(len(k_matrix)))
        trace_squared = math.fsum(item * item for row in k_matrix for item in row)
        degrees_of_freedom = trace * trace / trace_squared
    except (OverflowError, ZeroDivisionError):
        return MetricRefusal.INVALID_DF
    if not math.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0.0:
        return MetricRefusal.INVALID_DF

    variance_of_mean_iid = sample_variance / count
    if not math.isfinite(variance_of_mean_iid) or variance_of_mean_iid <= 0.0:
        return MetricRefusal.INVALID_VARIANCE
    try:
        design_effect = cr2_variance / variance_of_mean_iid
        effective_n_uncapped = sample_variance / cr2_variance
    except (OverflowError, ZeroDivisionError):
        return MetricRefusal.INVALID_VARIANCE
    if (
        not math.isfinite(design_effect)
        or design_effect <= 0.0
        or not math.isfinite(effective_n_uncapped)
        or effective_n_uncapped <= 0.0
    ):
        return MetricRefusal.INVALID_VARIANCE
    effective_n_capped = effective_n_uncapped > count
    effective_n_display = min(effective_n_uncapped, float(count))
    return CandidateMoments(
        count=count,
        block_counts=block_counts,
        mean=mean,
        sample_variance=sample_variance,
        cr2_variance=cr2_variance,
        degrees_of_freedom=degrees_of_freedom,
        design_effect=design_effect,
        effective_n_uncapped=effective_n_uncapped,
        effective_n_display=effective_n_display,
        effective_n_capped=effective_n_capped,
    )


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
    if not values:
        return _unavailable(MetricRefusal.EMPTY_SAMPLE)
    mean = _finite_float64_decimal("descriptive mean", sum(values, Decimal(0)) / len(values))
    float_values = tuple(_finite_float64_decimal("metric value", value) for value in values)
    moments = _cr2_moments(float_values, block_ids)
    if isinstance(moments, CandidateMoments):
        return MetricDiagnostic(count=len(values), mean=moments.mean, moments=moments, refusal=None)
    return MetricDiagnostic(count=len(values), mean=mean, moments=None, refusal=moments)


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
    if not math.isfinite(converted) or (converted == 0.0 and value != 0):
        raise ValueError(f"{name} must be representable as a finite float64 without underflow")
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
