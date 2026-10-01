"""Original-mean Chebyshev reference for trusted independent artificial group laws.

No finite support, empirical moment fitting, real-data certification, or broker path.
Declarations are trusted premises, never authenticated from the observed sample.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Context, Decimal, DecimalException, localcontext
from enum import StrEnum
from fractions import Fraction
from math import isfinite
from typing import ClassVar

from scripts.research.signal_bounded_uncertainty import (
    Declaration as Declaration,
)
from scripts.research.signal_bounded_uncertainty import (
    Member as Member,
)
from scripts.research.signal_bounded_uncertainty import (
    Metric as Metric,
)
from scripts.research.signal_bounded_uncertainty import (
    Numeric as Numeric,
)
from scripts.research.signal_bounded_uncertainty import (
    Observation as Observation,
)
from scripts.research.signal_bounded_uncertainty import (
    Scope as Scope,
)


class Reason(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_COHORT = "invalid_cohort"
    REAL_DATA_FORBIDDEN = "real_data_forbidden"
    UNKNOWN_INDEPENDENCE = "unknown_independence"
    UNKNOWN_MOMENT = "unknown_moment"
    UNKNOWN_WHOLE_VECTOR = "unknown_whole_vector"
    OUTCOME_DEPENDENT_SELECTION = "outcome_dependent_selection"
    INCOMPATIBLE_MOMENT = "incompatible_moment"
    MISSING_BENCHMARK = "missing_benchmark"
    NONFINITE = "nonfinite"
    TECHNICAL_LIMIT = "technical_limit"
    NUMERICAL_RESOLUTION = "numerical_resolution"
    ZERO_MOMENT_CONTRADICTION = "zero_moment_contradiction"
    NEEDS_MORE_INDEPENDENT_EVIDENCE = "needs_more_independent_evidence"


@dataclass(frozen=True, slots=True)
class MomentGroupContract:
    identifier: str
    count: int
    law_identity: str
    provenance: str
    metric: Metric
    center: Numeric
    second_moment: Numeric
    moment: Declaration = Declaration.UNKNOWN
    whole_vector: Declaration = Declaration.UNKNOWN
    selection: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class MomentSourceContract:
    fixture: str
    provenance: str
    first_session: int
    last_session: int
    members: tuple[Member, ...]
    groups: tuple[MomentGroupContract, ...]
    scope: Scope = Scope.SYNTHETIC_FIXTURE
    independence: Declaration = Declaration.UNKNOWN
    geometry: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class MomentRequest:
    metric: Metric
    alpha: Numeric
    absolute_full_width: Numeric
    selection: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class MomentRefusal:
    reason: Reason


@dataclass(frozen=True, slots=True)
class _Diagnostics:
    mean: Fraction
    variance_bound: Fraction
    group_ids: tuple[str, ...]
    group_counts: tuple[int, ...]
    group_weights: tuple[Fraction, ...]
    group_means: tuple[Fraction, ...]
    centers: tuple[Fraction, ...]
    second_moments: tuple[Fraction, ...]
    law_identities: tuple[str, ...]
    law_provenance: tuple[str, ...]
    observations: int
    groups: int
    alpha: Fraction
    desired_full_width: Fraction
    metric: Metric
    fixture: str
    provenance: str
    radius: Decimal
    # Encloses mathematical 2*radius; outward endpoint rounding can make the
    # displayed endpoint span slightly larger. mean retains its exact Fraction.
    full_width: Decimal
    authority: ClassVar[str] = "SYNTHETIC_RESEARCH_ONLY"


@dataclass(frozen=True, slots=True)
class MomentEstimate(_Diagnostics):
    lower: Decimal
    upper: Decimal
    coverage_scope: ClassVar[str] = "UNCONDITIONAL_UNDER_DECLARED_ASSUMPTIONS"


@dataclass(frozen=True, slots=True)
class MomentInsufficientEvidence(_Diagnostics):
    reason: ClassVar[Reason] = Reason.NEEDS_MORE_INDEPENDENT_EVIDENCE


Result = MomentEstimate | MomentInsufficientEvidence | MomentRefusal

# Scratch allocation limits, not market thresholds. Guard before constructing
# Fraction(Decimal): exponent-only checking would miss an enormous coefficient.
_MAX_ROWS = 4096
_MAX_DIGITS = 4096
_MAX_BITS = 20000


class _Invalid(Exception):
    def __init__(self, reason: Reason) -> None:
        self.reason = reason


def _text(value: object) -> bool:
    return type(value) is str and 0 < len(value) <= 4096 and bool(value.strip())


def _checked(value: Fraction) -> Fraction:
    if max(value.numerator.bit_length(), value.denominator.bit_length()) > _MAX_BITS:
        raise _Invalid(Reason.TECHNICAL_LIMIT)
    return value


def _fraction(value: Numeric) -> Fraction:
    if type(value) is Decimal:
        if not value.is_finite():
            raise _Invalid(Reason.NONFINITE)
        parts = value.as_tuple()
        if len(parts.digits) > _MAX_DIGITS:
            raise _Invalid(Reason.TECHNICAL_LIMIT)
        if not isinstance(parts.exponent, int):
            raise _Invalid(Reason.NONFINITE)
        if abs(parts.exponent) > _MAX_DIGITS:
            raise _Invalid(Reason.TECHNICAL_LIMIT)
    elif type(value) is int:
        if value.bit_length() > _MAX_BITS:
            raise _Invalid(Reason.TECHNICAL_LIMIT)
    elif type(value) is Fraction:
        return _checked(value)
    elif type(value) is float:
        if not isfinite(value):
            raise _Invalid(Reason.NONFINITE)
    else:
        raise _Invalid(Reason.INVALID_INPUT)
    return _checked(Fraction(value))


def _sum(values: tuple[Fraction, ...]) -> Fraction:
    total = Fraction(0)
    for value in values:
        total = _checked(total + value)
    return total


def _validate(
    source: MomentSourceContract,
    observations: tuple[Observation, ...],
    request: MomentRequest,
) -> tuple[
    tuple[MomentGroupContract, ...],
    tuple[Fraction, ...],
    tuple[Fraction, ...],
    tuple[Fraction, ...],
    Fraction,
    Fraction,
]:
    if type(source) is not MomentSourceContract or type(request) is not MomentRequest:
        raise _Invalid(Reason.INVALID_INPUT)
    if source.scope is not Scope.SYNTHETIC_FIXTURE:
        raise _Invalid(Reason.REAL_DATA_FORBIDDEN)
    if source.independence is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(Reason.UNKNOWN_INDEPENDENCE)
    if (
        source.geometry is not Declaration.FIXTURE_DECLARED
        or request.selection is not Declaration.FIXTURE_DECLARED
    ):
        raise _Invalid(Reason.OUTCOME_DEPENDENT_SELECTION)
    if request.metric is not Metric.RAW and request.metric is not Metric.SYNTHETIC_EXCESS:
        raise _Invalid(Reason.INVALID_INPUT)
    alpha, width = _fraction(request.alpha), _fraction(request.absolute_full_width)
    if not 0 < alpha < 1 or width <= 0:
        raise _Invalid(Reason.INVALID_INPUT)
    if (
        not _text(source.fixture)
        or not _text(source.provenance)
        or type(source.first_session) is not int
        or type(source.last_session) is not int
        or source.first_session < 0
        or source.last_session < source.first_session
        or type(source.members) is not tuple
        or type(source.groups) is not tuple
        or type(observations) is not tuple
        or not source.members
        or not source.groups
    ):
        raise _Invalid(Reason.INVALID_INPUT)
    if max(len(source.members), len(source.groups), len(observations)) > _MAX_ROWS:
        raise _Invalid(Reason.TECHNICAL_LIMIT)
    group_map: dict[str, MomentGroupContract] = {}
    centers: dict[str, Fraction] = {}
    moments: dict[str, Fraction] = {}
    for group in source.groups:
        if (
            type(group) is not MomentGroupContract
            or not _text(group.identifier)
            or group.identifier in group_map
            or type(group.count) is not int
            or group.count <= 0
        ):
            raise _Invalid(Reason.INVALID_COHORT)
        if not _text(group.law_identity) or not _text(group.provenance):
            raise _Invalid(Reason.INVALID_INPUT)
        if group.metric is not request.metric:
            raise _Invalid(Reason.INCOMPATIBLE_MOMENT)
        if group.moment is not Declaration.FIXTURE_DECLARED:
            raise _Invalid(Reason.UNKNOWN_MOMENT)
        if group.whole_vector is not Declaration.FIXTURE_DECLARED:
            raise _Invalid(Reason.UNKNOWN_WHOLE_VECTOR)
        if group.selection is not Declaration.FIXTURE_DECLARED:
            raise _Invalid(Reason.OUTCOME_DEPENDENT_SELECTION)
        centers[group.identifier] = _fraction(group.center)
        moments[group.identifier] = _fraction(group.second_moment)
        if moments[group.identifier] < 0:
            raise _Invalid(Reason.INVALID_INPUT)
        group_map[group.identifier] = group
    members: dict[str, Member] = {}
    counts = dict.fromkeys(group_map, 0)
    for member in source.members:
        if (
            type(member) is not Member
            or not _text(member.identifier)
            or member.identifier in members
            or not _text(member.group_id)
            or member.group_id not in group_map
            or type(member.entry) is not int
            or not source.first_session <= member.entry <= source.last_session
        ):
            raise _Invalid(Reason.INVALID_COHORT)
        members[member.identifier] = member
        counts[member.group_id] += 1
    if any(counts[key] != group.count for key, group in group_map.items()):
        raise _Invalid(Reason.INVALID_COHORT)
    rows: dict[str, Observation] = {}
    for row in observations:
        if (
            type(row) is not Observation
            or not _text(row.identifier)
            or row.identifier not in members
            or row.identifier in rows
            or type(row.entry) is not int
            or row.entry != members[row.identifier].entry
        ):
            raise _Invalid(Reason.INVALID_COHORT)
        rows[row.identifier] = row
    if rows.keys() != members.keys():
        raise _Invalid(Reason.INVALID_COHORT)
    values: dict[str, list[Fraction]] = {key: [] for key in group_map}
    for identifier in sorted(members):
        row = rows[identifier]
        value = _fraction(row.raw)
        benchmark = None if row.benchmark is None else _fraction(row.benchmark)
        if request.metric is Metric.SYNTHETIC_EXCESS:
            if benchmark is None:
                raise _Invalid(Reason.MISSING_BENCHMARK)
            value = _checked(value - benchmark)
        values[members[identifier].group_id].append(value)
    groups = tuple(group_map[key] for key in sorted(group_map))
    means = tuple(_checked(_sum(tuple(values[g.identifier])) / g.count) for g in groups)
    ordered_centers = tuple(centers[g.identifier] for g in groups)
    ordered_moments = tuple(moments[g.identifier] for g in groups)
    for mean, center, moment in zip(means, ordered_centers, ordered_moments, strict=True):
        if moment == 0 and mean != center:
            raise _Invalid(Reason.ZERO_MOMENT_CONTRADICTION)
    return groups, means, ordered_centers, ordered_moments, alpha, width


def _decimal(value: Fraction, context: Context, rounding: str) -> Decimal:
    context.rounding = rounding
    return context.divide(Decimal(value.numerator), Decimal(value.denominator))


def estimate(
    source: MomentSourceContract,
    observations: tuple[Observation, ...],
    request: MomentRequest,
) -> Result:
    """Keep all original outcomes; return a range only under declared premises.

    Var(sum(w_g Y_g)) <= sum(w_g**2 M_g) by whole-vector independence.
    Chebyshev, checked 2026-10-01:
    https://www.stat.berkeley.edu/~stark/SticiGui/Text/clt.htm
    """
    try:
        groups, means, centers, moments, alpha, width = _validate(source, observations, request)
        weights = tuple(Fraction(g.count, len(observations)) for g in groups)
        mean = _sum(tuple(_checked(w * y) for w, y in zip(weights, means, strict=True)))
        variance = _sum(
            tuple(_checked(w**2 * moment) for w, moment in zip(weights, moments, strict=True))
        )
        squared_radius = _checked(variance / alpha)
        with localcontext(Context(prec=100, Emin=-999999, Emax=999999)) as context:
            argument = _decimal(squared_radius, context, ROUND_CEILING)
            radius = context.sqrt(argument)
            # Decimal.sqrt rounds nearest even regardless of requested rounding.
            # Certify the REPRESENTED enclosure against the exact rational target.
            if _checked(Fraction(radius) ** 2) < squared_radius:
                radius = context.next_plus(radius)
            if (
                not radius.is_finite()
                or (variance > 0 and radius <= 0)
                or _checked(Fraction(radius) ** 2) < squared_radius
            ):
                raise _Invalid(Reason.NUMERICAL_RESOLUTION)
            full_width = context.multiply(radius, Decimal(2))
            if Fraction(full_width) < 2 * Fraction(radius):
                raise _Invalid(Reason.NUMERICAL_RESOLUTION)
        diagnostics = _Diagnostics(
            mean,
            variance,
            tuple(g.identifier for g in groups),
            tuple(g.count for g in groups),
            weights,
            means,
            centers,
            moments,
            tuple(g.law_identity for g in groups),
            tuple(g.provenance for g in groups),
            len(observations),
            len(groups),
            alpha,
            width,
            request.metric,
            source.fixture,
            source.provenance,
            radius,
            full_width,
        )
        if Fraction(full_width) > width:
            return MomentInsufficientEvidence(
                **{
                    field: getattr(diagnostics, field)
                    for field in diagnostics.__dataclass_fields__
                    if field != "authority"
                }
            )
        lo_exact = _checked(mean - Fraction(radius))
        hi_exact = _checked(mean + Fraction(radius))
        # Size precision from bounded exact operands, so legal large observations
        # and tiny radii do not collapse into a zero-width decimal interval.
        precision = 100 + max(
            abs(value.numerator).bit_length() + value.denominator.bit_length()
            for value in (lo_exact, hi_exact)
        )
        with localcontext(Context(prec=precision, Emin=-999999, Emax=999999)) as context:
            lower = _decimal(lo_exact, context, ROUND_FLOOR)
            upper = _decimal(hi_exact, context, ROUND_CEILING)
        if Fraction(lower) > lo_exact or Fraction(upper) < hi_exact:
            raise _Invalid(Reason.NUMERICAL_RESOLUTION)
        return MomentEstimate(
            **{
                field: getattr(diagnostics, field)
                for field in diagnostics.__dataclass_fields__
                if field != "authority"
            },
            lower=lower,
            upper=upper,
        )
    except _Invalid as error:
        return MomentRefusal(error.reason)
    except (DecimalException, OverflowError):
        return MomentRefusal(Reason.NUMERICAL_RESOLUTION)
