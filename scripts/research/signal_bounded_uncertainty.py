"""Finite-sample mathematics for trusted, fixed synthetic fixtures only.

Assumption declarations are research inputs, not an independence detector.
No claim of nominal coverage conditional on data-dependent emission is made.
"""

import itertools
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


class WithinClassIndependence(StrEnum):
    UNKNOWN = "unknown"
    JOINT_FIXTURE_DECLARED = "joint_fixture_declared"
    PAIRWISE_ONLY = "pairwise_only"
    OBSERVED = "observed"


class RefusalReason(StrEnum):
    REAL_DATA_FORBIDDEN = "real_data_forbidden"
    UNKNOWN_INDEPENDENCE = "unknown_independence"
    UNKNOWN_CLASS_INDEPENDENCE = "unknown_class_independence"
    INVALID_CLASS_PARTITION = "invalid_class_partition"
    UNKNOWN_PERSISTENT_MODEL = "unknown_persistent_model"
    INVALID_LATENT_MAP = "invalid_latent_map"
    EXHAUSTED_DEPENDENCE_BUDGET = "exhausted_dependence_budget"
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


@dataclass(frozen=True, slots=True)
class IndependentClass:
    identifier: str
    group_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DependenceContract:
    fixture: str
    provenance: str
    classes: tuple[IndependentClass, ...]
    joint_independence: WithinClassIndependence = WithinClassIndependence.UNKNOWN
    geometry: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class DependenceResult:
    """The calculation's q/range diagnostics retain their unpenalized meanings.

    penalized_q governs the actual radius; penalized concentration is separate.
    """

    calculation: BoundedEstimate | InsufficientEvidence | StructurallyKnown
    original_q: Fraction
    active_classes: int
    penalized_q: Fraction
    penalized_range_effective_groups: Fraction | None
    class_provenance: str
    premise: ClassVar[str] = "FIXTURE_DECLARED_WITHIN_CLASS_JOINT_INDEPENDENCE"


@dataclass(frozen=True, slots=True)
class LatentIndex:
    group_id: str
    index: int
    axis: str


@dataclass(frozen=True, slots=True)
class PersistentModelContract:
    fixture: str
    provenance: str
    latent_axis: str
    indices: tuple[LatentIndex, ...]
    classes: tuple[IndependentClass, ...]
    persistence_bound: Numeric
    stationary_gaussian_start: Declaration = Declaration.UNKNOWN
    independent_gaussian_innovations: Declaration = Declaration.UNKNOWN
    known_persistence_bound: Declaration = Declaration.UNKNOWN
    whole_local_map: Declaration = Declaration.UNKNOWN
    independent_local_noise: Declaration = Declaration.UNKNOWN
    marginal_preservation: Declaration = Declaration.UNKNOWN
    geometry: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class ClassAllowance:
    identifier: str
    indices: tuple[int, ...]
    active_indices: tuple[int, ...]
    gaps: tuple[int, ...]
    q: Fraction
    log_sum_upper: Decimal
    delta_upper: Decimal
    radius_upper: Decimal


@dataclass(frozen=True, slots=True)
class PersistentResult:
    calculation: BoundedEstimate | InsufficientEvidence | StructurallyKnown
    original_q: Fraction
    classes: tuple[ClassAllowance, ...]
    dependence_upper: Decimal
    residual_budget_lower: Fraction
    total_radius_upper: Decimal
    model_provenance: str
    latent_axis: str
    premise: ClassVar[str] = "TRUSTED_STATIONARY_GAUSSIAN_AR_LOCAL_MAP_ONLY"


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
    *,
    require_global_independence: bool = True,
) -> tuple[tuple[Fraction, ...], tuple[int, ...], tuple[tuple[Fraction, Fraction], ...]]:
    if type(source) is not SourceContract or not isinstance(metric, Metric):
        raise _Invalid(RefusalReason.INVALID_INPUT)
    if source.scope is not Scope.SYNTHETIC_FIXTURE:
        raise _Invalid(RefusalReason.REAL_DATA_FORBIDDEN)
    if require_global_independence and source.independence is not Declaration.FIXTURE_DECLARED:
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


def _validate_classes(
    source: SourceContract,
    contract: DependenceContract,
    ranges: tuple[tuple[Fraction, Fraction], ...],
) -> int:
    if type(contract) is not DependenceContract:
        raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
    if contract.joint_independence is not WithinClassIndependence.JOINT_FIXTURE_DECLARED:
        raise _Invalid(RefusalReason.UNKNOWN_CLASS_INDEPENDENCE)
    if contract.geometry is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(RefusalReason.OUTCOME_DEPENDENT_GEOMETRY)
    if contract.fixture != source.fixture or not _valid_text(contract.provenance):
        raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
    return _partition(source, contract.classes, ranges)


def _partition(
    source: SourceContract,
    classes: tuple[IndependentClass, ...],
    ranges: tuple[tuple[Fraction, Fraction], ...],
) -> int:
    """Validate full immutable coverage without asserting a probability premise."""
    if type(classes) is not tuple or not classes:
        raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
    if len(classes) > 4096:
        raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
    groups = sorted(group.identifier for group in source.groups)
    random_groups = {group for group, (lo, hi) in zip(groups, ranges, strict=True) if lo != hi}
    seen_classes: set[str] = set()
    seen_groups: set[str] = set()
    active_classes = 0
    for item in classes:
        if (
            type(item) is not IndependentClass
            or not _valid_text(item.identifier)
            or item.identifier in seen_classes
            or type(item.group_ids) is not tuple
            or not item.group_ids
        ):
            raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
        if len(item.group_ids) > 4096:
            raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
        seen_classes.add(item.identifier)
        for group in item.group_ids:
            if not _valid_text(group) or group not in groups or group in seen_groups:
                raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
            seen_groups.add(group)
        active_classes += int(any(group in random_groups for group in item.group_ids))
    if seen_groups != set(groups):
        raise _Invalid(RefusalReason.INVALID_CLASS_PARTITION)
    return active_classes


def _dependence_result(
    calculation: BoundedEstimate | InsufficientEvidence | StructurallyKnown,
    contract: DependenceContract | None,
    q: Fraction,
    active_classes: int,
    support_width: Fraction,
) -> BoundedEstimate | InsufficientEvidence | StructurallyKnown | DependenceResult:
    if contract is None:
        return calculation
    penalized_q = active_classes * q
    return DependenceResult(
        calculation,
        q,
        active_classes,
        penalized_q,
        support_width**2 / penalized_q if penalized_q else None,
        contract.provenance,
    )


def _decimal(value: Fraction, context: Context, rounding: str) -> Decimal:
    context.rounding = rounding
    return context.divide(Decimal(value.numerator), Decimal(value.denominator))


def _bounded(
    diagnostics: _Diagnostics,
    *,
    q_multiplier: int = 1,
) -> BoundedEstimate | InsufficientEvidence | Refusal:
    # A fresh context isolates precision, exponent limits, traps and flags.
    with localcontext(Context(prec=80, Emax=999999, Emin=-999999)) as context:
        # Fixed jointly independent classes permit arbitrary cross-class dependence.
        # The disjoint-class Holder bound multiplies exact Q by active class count K.
        # Janson proper-cover Theorem 2.1, checked 2026-10-01:
        # https://api.newton.ac.uk/website/v0/events/preprints/NI02024
        q_upper = _decimal(q_multiplier * diagnostics.q, context, ROUND_CEILING)
        argument_upper = _decimal(2 / diagnostics.alpha, context, ROUND_CEILING)
        # Python Decimal ln/sqrt are correctly rounded HALF_EVEN. Moving one
        # representable value upward encloses the exact value, monotonically.
        # https://docs.python.org/3/library/decimal.html checked 2026-09-30.
        log_upper = context.next_plus(context.ln(argument_upper))
        context.rounding = ROUND_CEILING
        square_upper = context.divide(context.multiply(q_upper, log_upper), Decimal(2))
        radius = context.next_plus(context.sqrt(square_upper))
        return _finish(diagnostics, radius, context)


def _finish(
    diagnostics: _Diagnostics,
    radius: Decimal,
    context: Context,
) -> BoundedEstimate | InsufficientEvidence | Refusal:
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
    if not all(v.is_finite() and v > 0 for v in (radius, width_lower)):
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


def _aggregate(
    source: SourceContract,
    values: tuple[Fraction, ...],
    counts: tuple[int, ...],
    ranges: tuple[tuple[Fraction, Fraction], ...],
    metric: Metric,
    a: Fraction,
    precision: Fraction,
) -> _Diagnostics | StructurallyKnown:
    n = len(values)
    weights = tuple(Fraction(count, n) for count in counts)
    mean = sum(values, Fraction()) / n
    support_lower = sum((w * lo for w, (lo, _) in zip(weights, ranges, strict=True)), Fraction())
    support_upper = sum((w * hi for w, (_, hi) in zip(weights, ranges, strict=True)), Fraction())
    if all(lo == hi for lo, hi in ranges):
        if mean != support_lower:
            raise _Invalid(RefusalReason.SUPPORT_VIOLATION)
        known = StructurallyKnown(mean, n, len(counts), metric, source.fixture, source.provenance)
        return known
    q = sum(((w * (hi - lo)) ** 2 for w, (lo, hi) in zip(weights, ranges, strict=True)), Fraction())
    concentration = sum((w * w for w in weights), Fraction())
    return _Diagnostics(
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


def _estimate(
    source: SourceContract,
    observations: Sequence[Observation],
    *,
    metric: Metric,
    alpha: Numeric,
    desired_precision: Numeric,
    dependence: DependenceContract | None = None,
) -> BoundedEstimate | StructurallyKnown | InsufficientEvidence | Refusal | DependenceResult:
    """Return conditional-assumption research math; refuse unsupported input."""
    try:
        a, precision = _fraction(alpha), _fraction(desired_precision)
        if not 0 < a < 1 or not 0 < precision <= 1:
            return Refusal(RefusalReason.INVALID_INPUT)
        values, counts, ranges = _validate(
            source,
            observations,
            metric,
            require_global_independence=dependence is None,
        )
        # Complete partitions and joint premises are checked even for known outcomes.
        active_classes = (
            _validate_classes(source, dependence, ranges) if dependence is not None else 1
        )
        aggregate = _aggregate(source, values, counts, ranges, metric, a, precision)
        if isinstance(aggregate, StructurallyKnown):
            return _dependence_result(aggregate, dependence, Fraction(), active_classes, Fraction())
        calculation = _bounded(aggregate, q_multiplier=active_classes)
        if isinstance(calculation, Refusal):
            return calculation
        return _dependence_result(
            calculation,
            dependence,
            aggregate.q,
            active_classes,
            aggregate.support_upper - aggregate.support_lower,
        )
    except _Invalid as error:
        return Refusal(error.reason)
    except DecimalException:
        return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
    except (TypeError, ValueError, OverflowError):
        return Refusal(RefusalReason.INVALID_INPUT)


def estimate(
    source: SourceContract,
    observations: Sequence[Observation],
    *,
    metric: Metric,
    alpha: Numeric,
    desired_precision: Numeric,
) -> BoundedEstimate | StructurallyKnown | InsufficientEvidence | Refusal:
    """Original globally-independent research route; its contract is unchanged."""
    result = _estimate(
        source, observations, metric=metric, alpha=alpha, desired_precision=desired_precision
    )
    assert not isinstance(result, DependenceResult)
    return result


def estimate_dependence(
    source: SourceContract,
    observations: Sequence[Observation],
    dependence: DependenceContract,
    *,
    metric: Metric,
    alpha: Numeric,
    desired_precision: Numeric,
) -> DependenceResult | Refusal:
    """Use trusted within-class JOINT independence, not source global independence."""
    if type(dependence) is not DependenceContract:
        return Refusal(RefusalReason.INVALID_CLASS_PARTITION)
    result = _estimate(
        source,
        observations,
        metric=metric,
        alpha=alpha,
        desired_precision=desired_precision,
        dependence=dependence,
    )
    assert isinstance(result, (DependenceResult, Refusal))
    return result


def _persistent_model(
    source: SourceContract,
    model: PersistentModelContract,
    ranges: tuple[tuple[Fraction, Fraction], ...],
) -> tuple[Fraction, dict[str, int]]:
    if type(model) is not PersistentModelContract:
        raise _Invalid(RefusalReason.UNKNOWN_PERSISTENT_MODEL)
    declarations = (
        model.stationary_gaussian_start,
        model.independent_gaussian_innovations,
        model.known_persistence_bound,
        model.whole_local_map,
        model.independent_local_noise,
        model.marginal_preservation,
        model.geometry,
    )
    if any(item is not Declaration.FIXTURE_DECLARED for item in declarations):
        raise _Invalid(RefusalReason.UNKNOWN_PERSISTENT_MODEL)
    if model.fixture != source.fixture or not _valid_text(model.provenance):
        raise _Invalid(RefusalReason.UNKNOWN_PERSISTENT_MODEL)
    r = _fraction(model.persistence_bound)
    if not 0 <= r < 1:
        raise _Invalid(RefusalReason.UNKNOWN_PERSISTENT_MODEL)
    _partition(source, model.classes, ranges)
    if not _valid_text(model.latent_axis) or type(model.indices) is not tuple:
        raise _Invalid(RefusalReason.INVALID_LATENT_MAP)
    if len(model.indices) > 4096:
        raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
    groups = {g.identifier for g in source.groups}
    seen: set[int] = set()
    indices: dict[str, int] = {}
    for point in model.indices:
        if (
            type(point) is not LatentIndex
            or not _valid_text(point.group_id)
            or point.group_id not in groups
            or point.group_id in indices
            or type(point.index) is not int
            or point.index < 0
            or point.index in seen
            or point.index.bit_length() > 4096
            or point.axis != model.latent_axis
        ):
            raise _Invalid(RefusalReason.INVALID_LATENT_MAP)
        indices[point.group_id] = point.index
        seen.add(point.index)
    if set(indices) != groups:
        raise _Invalid(RefusalReason.INVALID_LATENT_MAP)
    return r, indices


def _log_upper(argument: Fraction, context: Context) -> Decimal:
    rounded = _decimal(argument, context, ROUND_CEILING)
    return context.next_plus(context.ln(rounded))


def _persistent_classes(
    source: SourceContract,
    model: PersistentModelContract,
    r: Fraction,
    indices: dict[str, int],
    counts: tuple[int, ...],
    ranges: tuple[tuple[Fraction, Fraction], ...],
    alpha: Fraction,
    context: Context,
) -> tuple[tuple[ClassAllowance, ...], Decimal, Fraction, Decimal]:
    groups = sorted(g.identifier for g in source.groups)
    n = sum(counts)
    terms = {
        g: (Fraction(c, n) * (hi - lo)) ** 2
        for g, c, (lo, hi) in zip(groups, counts, ranges, strict=True)
    }
    # Preflight ALL exact powers before allocating any power-sized integer.
    layouts = []
    total_bits = 0
    for item in sorted(model.classes, key=lambda c: tuple(sorted(c.group_ids))):
        full = tuple(sorted(indices[g] for g in item.group_ids))
        active = tuple(sorted(indices[g] for g in item.group_ids if terms[g]))
        gaps = tuple(b - a for a, b in itertools.pairwise(active))
        if r:
            total_bits += sum(
                2 * d * (r.numerator.bit_length() + r.denominator.bit_length()) for d in gaps
            )
            if total_bits > 262144:
                raise _Invalid(RefusalReason.TECHNICAL_LIMIT)
        q = sum((terms[g] for g in item.group_ids), Fraction())
        layouts.append((item.identifier, full, active, gaps, q))
    allowances = []
    dependence = Decimal(0)
    for identifier, full, active, gaps, q in layouts:
        log_sum = Decimal(0)
        if r:
            for gap in gaps:
                x = r ** (2 * gap)
                if not 0 < x < 1:
                    raise _Invalid(RefusalReason.NUMERICAL_RESOLUTION)
                # Gaussian KL/Markov identity and event-TV Pinsker, checked 2026-10-01.
                # https://www.stat.berkeley.edu/~aditya/resources/STAT212aSEP11Lecture3.pdf
                term = _log_upper(1 / (1 - x), context)
                context.rounding = ROUND_CEILING
                log_sum = context.add(log_sum, term)
        if log_sum:
            delta = min(
                Decimal(1),
                context.multiply(Decimal("0.5"), context.next_plus(context.sqrt(log_sum))),
            )
        else:
            delta = Decimal(0)
        context.rounding = ROUND_CEILING
        dependence = context.add(dependence, delta)
        allowances.append(
            ClassAllowance(identifier, full, active, gaps, q, log_sum, delta, Decimal(0))
        )
    residual = alpha - Fraction(dependence)
    if residual <= 0:
        raise _Invalid(RefusalReason.EXHAUSTED_DEPENDENCE_BUDGET)
    k = sum(bool(c.active_indices) for c in allowances)
    total_radius = Decimal(0)
    if k:
        log_arg = Fraction(2 * k) / residual
        log = _log_upper(log_arg, context)
        radii = []
        for c in allowances:
            radius = Decimal(0)
            if c.q:
                q_upper = _decimal(c.q, context, ROUND_CEILING)
                square = context.divide(context.multiply(q_upper, log), Decimal(2))
                radius = context.next_plus(context.sqrt(square))
                if not radius.is_finite() or radius <= 0:
                    raise _Invalid(RefusalReason.NUMERICAL_RESOLUTION)
            context.rounding = ROUND_CEILING
            total_radius = context.add(total_radius, radius)
            radii.append(
                ClassAllowance(
                    c.identifier,
                    c.indices,
                    c.active_indices,
                    c.gaps,
                    c.q,
                    c.log_sum_upper,
                    c.delta_upper,
                    radius,
                )
            )
        allowances = radii
    return tuple(allowances), dependence, residual, total_radius


def estimate_persistent(
    source: SourceContract,
    observations: Sequence[Observation],
    model: PersistentModelContract,
    *,
    metric: Metric,
    alpha: Numeric,
    desired_precision: Numeric,
) -> PersistentResult | Refusal:
    """Stationary Gaussian-law reference; no global or class independence is asserted."""
    try:
        a, precision = _fraction(alpha), _fraction(desired_precision)
        if not 0 < a < 1 or not 0 < precision <= 1:
            return Refusal(RefusalReason.INVALID_INPUT)
        values, counts, ranges = _validate(
            source, observations, metric, require_global_independence=False
        )
        r, indices = _persistent_model(source, model, ranges)
        aggregate = _aggregate(source, values, counts, ranges, metric, a, precision)
        with localcontext(Context(prec=80, Emax=999999, Emin=-999999)) as context:
            classes, dependence, residual, radius = _persistent_classes(
                source,
                model,
                r,
                indices,
                counts,
                ranges,
                a,
                context,
            )
            if isinstance(aggregate, StructurallyKnown):
                calculation: (
                    BoundedEstimate | InsufficientEvidence | StructurallyKnown | Refusal
                ) = aggregate
                q = Fraction()
            else:
                calculation = _finish(aggregate, radius, context)
                q = aggregate.q
        if isinstance(calculation, Refusal):
            return calculation
        return PersistentResult(
            calculation,
            q,
            classes,
            dependence,
            residual,
            radius,
            model.provenance,
            model.latent_axis,
        )
    except _Invalid as error:
        return Refusal(error.reason)
    except DecimalException:
        return Refusal(RefusalReason.NUMERICAL_RESOLUTION)
    except (TypeError, ValueError, OverflowError):
        return Refusal(RefusalReason.INVALID_INPUT)
