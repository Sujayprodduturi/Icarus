"""Finite-sample mathematics for trusted, fixed synthetic fixtures only.

Assumption declarations are research inputs, not an independence detector.
No claim of nominal coverage conditional on data-dependent emission is made.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import (
    ROUND_CEILING,
    ROUND_FLOOR,
    Context,
    Decimal,
    DecimalException,
    localcontext,
)
from enum import StrEnum
from fractions import Fraction
from math import isfinite
from typing import ClassVar

Numeric = int | float | Decimal | Fraction


class Metric(StrEnum):
    RAW = "raw"
    WIN = "win"
    SYNTHETIC_EXCESS = "synthetic_excess"


class Scope(StrEnum):
    SYNTHETIC_FIXTURE = "synthetic_fixture"
    REAL_DATA = "real_data"


class Declaration(StrEnum):
    FIXTURE_DECLARED = "fixture_declared"
    UNKNOWN = "unknown"
    OBSERVED = "observed"
    OUTCOME_DEPENDENT = "outcome_dependent"


class RefusalReason(StrEnum):
    REAL_DATA_FORBIDDEN = "real_data_forbidden"
    UNKNOWN_INDEPENDENCE = "unknown_independence"
    UNKNOWN_SUPPORT = "unknown_support"
    OUTCOME_DEPENDENT_GEOMETRY = "outcome_dependent_geometry"
    INVALID_INPUT = "invalid_input"
    INVALID_COHORT = "invalid_cohort"
    SUPPORT_VIOLATION = "support_violation"
    MISSING_BENCHMARK = "missing_benchmark"
    NONFINITE = "nonfinite"
    TECHNICAL_LIMIT = "technical_limit"
    NUMERICAL_RESOLUTION = "numerical_resolution"
    NEEDS_MORE_INDEPENDENT_EVIDENCE = "needs_more_independent_evidence"


@dataclass(frozen=True, slots=True)
class Support:
    lower: Numeric
    upper: Numeric


@dataclass(frozen=True, slots=True)
class Member:
    identifier: str
    entry: int
    group_id: str


@dataclass(frozen=True, slots=True)
class GroupContract:
    identifier: str
    count: int
    raw_support: Support
    benchmark_support: Support | None = None


@dataclass(frozen=True, slots=True)
class SourceContract:
    fixture: str
    provenance: str
    first_session: int
    last_session: int
    members: tuple[Member, ...]
    groups: tuple[GroupContract, ...]
    scope: Scope = Scope.SYNTHETIC_FIXTURE
    independence: Declaration = Declaration.UNKNOWN
    support: Declaration = Declaration.UNKNOWN
    geometry: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class Observation:
    identifier: str
    entry: int
    raw: Numeric
    benchmark: Numeric | None = None


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: RefusalReason


@dataclass(frozen=True, slots=True)
class _Diagnostics:
    mean: Fraction
    support_lower: Fraction
    support_upper: Fraction
    q: Fraction
    weight_effective_groups: Fraction
    range_effective_groups: Fraction
    observations: int
    groups: int
    alpha: Fraction
    desired_precision: Fraction
    metric: Metric
    fixture: str
    provenance: str
    authority: ClassVar[str] = "SYNTHETIC_RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class BoundedEstimate(_Diagnostics):
    radius: Decimal
    normalized_width: Decimal
    untrimmed_lower: Decimal
    untrimmed_upper: Decimal
    lower: Decimal
    upper: Decimal
    reported_width: Decimal
    coverage_scope: ClassVar[str] = "UNCONDITIONAL_UNDER_DECLARED_ASSUMPTIONS"


@dataclass(frozen=True, slots=True)
class InsufficientEvidence(_Diagnostics):
    radius: Decimal
    normalized_width: Decimal
    reason: ClassVar[RefusalReason] = RefusalReason.NEEDS_MORE_INDEPENDENT_EVIDENCE


@dataclass(frozen=True, slots=True)
class StructurallyKnown:
    value: Fraction
    observations: int
    groups: int
    metric: Metric
    fixture: str
    provenance: str
    authority: ClassVar[str] = "SYNTHETIC_RESEARCH_ONLY"


class _Invalid(Exception):
    def __init__(self, reason: RefusalReason) -> None:
        self.reason = reason


def _fraction(value: Numeric) -> Fraction:
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal, Fraction)):
        raise _Invalid(RefusalReason.INVALID_INPUT)
    if isinstance(value, float) and not isfinite(value):
        raise _Invalid(RefusalReason.NONFINITE)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise _Invalid(RefusalReason.NONFINITE)
        if value and abs(value.adjusted()) > 1000:
            raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
    result = Fraction(value)
    # Scratch resource bounds, not product data floors or statistical assumptions.
    if max(result.numerator.bit_length(), result.denominator.bit_length()) > 4096:
        raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
    return result


def _support(support: Support) -> tuple[Fraction, Fraction]:
    if type(support) is not Support:
        raise _Invalid(RefusalReason.UNKNOWN_SUPPORT)
    lower, upper = _fraction(support.lower), _fraction(support.upper)
    if lower > upper:
        raise _Invalid(RefusalReason.INVALID_INPUT)
    return lower, upper


def _valid_text(value: str) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate(
    source: SourceContract,
    observations: Sequence[Observation],
    metric: Metric,
) -> tuple[tuple[Fraction, ...], tuple[int, ...], tuple[tuple[Fraction, Fraction], ...]]:
    if type(source) is not SourceContract or not isinstance(metric, Metric):
        raise _Invalid(RefusalReason.INVALID_INPUT)
    if source.scope is not Scope.SYNTHETIC_FIXTURE:
        raise _Invalid(RefusalReason.REAL_DATA_FORBIDDEN)
    if source.independence is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(RefusalReason.UNKNOWN_INDEPENDENCE)
    if source.support is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(RefusalReason.UNKNOWN_SUPPORT)
    if source.geometry is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(RefusalReason.OUTCOME_DEPENDENT_GEOMETRY)
    if (
        not _valid_text(source.fixture)
        or not _valid_text(source.provenance)
        or type(source.first_session) is not int
        or type(source.last_session) is not int
        or source.first_session < 0
        or source.last_session < source.first_session
        or type(source.members) is not tuple
        or type(source.groups) is not tuple
        or not source.members
        or not source.groups
    ):
        raise _Invalid(RefusalReason.INVALID_INPUT)
    if max(len(source.members), len(source.groups), len(observations)) > 4096:
        raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
    groups: dict[str, GroupContract] = {}
    for group in source.groups:
        if (
            type(group) is not GroupContract
            or not _valid_text(group.identifier)
            or group.identifier in groups
            or type(group.count) is not int
            or group.count <= 0
        ):
            raise _Invalid(RefusalReason.INVALID_COHORT)
        groups[group.identifier] = group
    members: dict[str, Member] = {}
    counts = dict.fromkeys(groups, 0)
    for member in source.members:
        if (
            type(member) is not Member
            or not _valid_text(member.identifier)
            or member.identifier in members
            or member.group_id not in groups
            or type(member.entry) is not int
            or not source.first_session <= member.entry <= source.last_session
        ):
            raise _Invalid(RefusalReason.INVALID_COHORT)
        members[member.identifier] = member
        counts[member.group_id] += 1
    if any(counts[key] != group.count for key, group in groups.items()):
        raise _Invalid(RefusalReason.INVALID_COHORT)
    rows: dict[str, Observation] = {}
    for row in observations:
        if (
            type(row) is not Observation
            or row.identifier not in members
            or row.identifier in rows
            or type(row.entry) is not int
            or row.entry != members[row.identifier].entry
        ):
            raise _Invalid(RefusalReason.INVALID_COHORT)
        rows[row.identifier] = row
    if rows.keys() != members.keys():
        raise _Invalid(RefusalReason.INVALID_COHORT)
    if metric is Metric.SYNTHETIC_EXCESS and any(row.benchmark is None for row in rows.values()):
        raise _Invalid(RefusalReason.MISSING_BENCHMARK)
    ranges: dict[str, tuple[Fraction, Fraction]] = {}
    raw_ranges = {key: _support(group.raw_support) for key, group in groups.items()}
    bench_ranges: dict[str, tuple[Fraction, Fraction]] = {}
    for key, group in groups.items():
        lo, hi = raw_ranges[key]
        if metric is Metric.RAW:
            ranges[key] = lo, hi
        elif metric is Metric.WIN:
            ranges[key] = (
                (Fraction(1), Fraction(1))
                if lo > 0
                else (Fraction(0), Fraction(0))
                if hi <= 0
                else (Fraction(0), Fraction(1))
            )
        else:
            if group.benchmark_support is None:
                raise _Invalid(RefusalReason.UNKNOWN_SUPPORT)
            blo, bhi = _support(group.benchmark_support)
            bench_ranges[key] = blo, bhi
            ranges[key] = lo - bhi, hi - blo
    values: list[Fraction] = []
    for identifier in sorted(members):
        row = rows[identifier]
        key = members[identifier].group_id
        raw = _fraction(row.raw)
        lo, hi = raw_ranges[key]
        if not lo <= raw <= hi:
            raise _Invalid(RefusalReason.SUPPORT_VIOLATION)
        if metric is Metric.RAW:
            values.append(raw)
        elif metric is Metric.WIN:
            values.append(Fraction(int(raw > 0)))
        else:
            assert row.benchmark is not None
            benchmark = _fraction(row.benchmark)
            blo, bhi = bench_ranges[key]
            if not blo <= benchmark <= bhi:
                raise _Invalid(RefusalReason.SUPPORT_VIOLATION)
            values.append(raw - benchmark)
    keys = sorted(groups)
    return tuple(values), tuple(counts[key] for key in keys), tuple(ranges[key] for key in keys)


def _decimal(value: Fraction, context: Context, rounding: str) -> Decimal:
    context.rounding = rounding
    return context.divide(Decimal(value.numerator), Decimal(value.denominator))


def _bounded(
    diagnostics: _Diagnostics,
) -> BoundedEstimate | InsufficientEvidence | Refusal:
    # A fresh context isolates precision, exponent limits, traps and flags.
    with localcontext(Context(prec=80, Emax=999999, Emin=-999999)) as context:
        q_upper = _decimal(diagnostics.q, context, ROUND_CEILING)
        argument_upper = _decimal(2 / diagnostics.alpha, context, ROUND_CEILING)
        # Python Decimal ln/sqrt are correctly rounded HALF_EVEN. Moving one
        # representable value upward encloses the exact value, monotonically.
        # https://docs.python.org/3/library/decimal.html checked 2026-09-30.
        log_upper = context.next_plus(context.ln(argument_upper))
        context.rounding = ROUND_CEILING
        square_upper = context.divide(context.multiply(q_upper, log_upper), Decimal(2))
        radius = context.next_plus(context.sqrt(square_upper))
        width = diagnostics.support_upper - diagnostics.support_lower
        width_lower = _decimal(width, context, ROUND_FLOOR)
        context.rounding = ROUND_CEILING
        normalized_width = context.divide(context.multiply(Decimal(2), radius), width_lower)
        precision_lower = _decimal(diagnostics.desired_precision, context, ROUND_FLOOR)
        fields = (
            diagnostics.mean,
            diagnostics.support_lower,
            diagnostics.support_upper,
            diagnostics.q,
            diagnostics.weight_effective_groups,
            diagnostics.range_effective_groups,
            diagnostics.observations,
            diagnostics.groups,
            diagnostics.alpha,
            diagnostics.desired_precision,
            diagnostics.metric,
            diagnostics.fixture,
            diagnostics.provenance,
        )
        if normalized_width > precision_lower:
            return InsufficientEvidence(*fields, radius=radius, normalized_width=normalized_width)
        mean_lower = _decimal(diagnostics.mean, context, ROUND_FLOOR)
        mean_upper = _decimal(diagnostics.mean, context, ROUND_CEILING)
        if not all(v.is_finite() and v > 0 for v in (q_upper, log_upper, radius, width_lower)):
            return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
        # Reject arithmetic whose unit of resolution is as large as the radius.
        if (
            max(
                context.subtract(context.next_plus(mean_upper), mean_upper),
                context.subtract(mean_lower, context.next_minus(mean_lower)),
            )
            >= radius
        ):
            return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
        context.rounding = ROUND_FLOOR
        untrimmed_lower = context.subtract(mean_lower, radius)
        context.rounding = ROUND_CEILING
        untrimmed_upper = context.add(mean_upper, radius)
        reported_width = context.subtract(untrimmed_upper, untrimmed_lower)
        actual_ratio = context.divide(reported_width, width_lower)
        if (
            not all(v.is_finite() for v in (untrimmed_lower, untrimmed_upper, actual_ratio))
            or actual_ratio > precision_lower
        ):
            return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
        a_lower = _decimal(diagnostics.support_lower, context, ROUND_FLOOR)
        b_upper = _decimal(diagnostics.support_upper, context, ROUND_CEILING)
        return BoundedEstimate(
            *fields,
            radius=radius,
            normalized_width=normalized_width,
            untrimmed_lower=untrimmed_lower,
            untrimmed_upper=untrimmed_upper,
            lower=max(untrimmed_lower, a_lower),
            upper=min(untrimmed_upper, b_upper),
            reported_width=reported_width,
        )


def estimate(
    source: SourceContract,
    observations: Sequence[Observation],
    *,
    metric: Metric,
    alpha: Numeric,
    desired_precision: Numeric,
) -> BoundedEstimate | StructurallyKnown | InsufficientEvidence | Refusal:
    """Return conditional-assumption research math; refuse unsupported input."""
    try:
        a, precision = _fraction(alpha), _fraction(desired_precision)
        if not 0 < a < 1 or not 0 < precision <= 1:
            return Refusal(RefusalReason.INVALID_INPUT)
        values, counts, ranges = _validate(source, observations, metric)
        n = len(values)
        weights = tuple(Fraction(count, n) for count in counts)
        mean = sum(values, Fraction()) / n
        support_lower = sum(
            (w * lo for w, (lo, _) in zip(weights, ranges, strict=True)), Fraction()
        )
        support_upper = sum(
            (w * hi for w, (_, hi) in zip(weights, ranges, strict=True)), Fraction()
        )
        if all(lo == hi for lo, hi in ranges):
            if mean != support_lower:
                return Refusal(RefusalReason.SUPPORT_VIOLATION)
            return StructurallyKnown(
                mean, n, len(counts), metric, source.fixture, source.provenance
            )
        q = sum(
            ((w * (hi - lo)) ** 2 for w, (lo, hi) in zip(weights, ranges, strict=True)), Fraction()
        )
        concentration = sum((w * w for w in weights), Fraction())
        diagnostics = _Diagnostics(
            mean,
            support_lower,
            support_upper,
            q,
            1 / concentration,
            (support_upper - support_lower) ** 2 / q,
            n,
            len(counts),
            a,
            precision,
            metric,
            source.fixture,
            source.provenance,
        )
        return _bounded(diagnostics)
    except _Invalid as error:
        return Refusal(error.reason)
    except DecimalException:
        return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
    except (TypeError, ValueError, OverflowError):
        return Refusal(RefusalReason.INVALID_INPUT)
