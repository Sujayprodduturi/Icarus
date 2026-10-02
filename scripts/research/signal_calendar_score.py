"""Finite-history calendar-score reference for declared synthetic models only.

Declarations are assumptions, not source/market certificates. Aggregate checks
do not authenticate complete trades, costs, benchmarks or the independence law.
Janson Theorem 2.1 checked 2026-10-02; project derivation and numerical contract:
docs/plans/2026-10-02-calendar-score-revision-design.md. No I/O or sampling.
"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from math import factorial, isqrt

Rational = int | Fraction
_GRID_DIGITS = 60
_SCALE = 10**_GRID_DIGITS
_ALLOWANCE = Fraction(4, _SCALE)
_EXPONENTIAL_LOWER = sum((Fraction(5**j, factorial(j)) for j in range(11)), Fraction())


class ScoreError(ValueError):
    """Unsupported assumptions, malformed totals or bounded numeric inputs."""


class Scope(StrEnum):
    SYNTHETIC = "synthetic"
    REAL = "real"


class Declaration(StrEnum):
    FIXTURE_DECLARED = "fixture_declared"
    UNKNOWN = "unknown"
    OBSERVED = "observed"


class Metric(StrEnum):
    RAW = "raw"
    WIN = "win"
    SYNTHETIC_EXCESS = "synthetic_excess"


@dataclass(frozen=True, slots=True)
class Model:
    n: int
    classes: int
    dense: bool
    scope: Scope
    stationarity: Declaration
    support: Declaration
    independent_classes: Declaration
    complete_calendar: Declaration


@dataclass(frozen=True, slots=True)
class Target:
    metric: Metric
    lower: Rational
    upper: Rational
    width: Rational


@dataclass(frozen=True, slots=True)
class Totals:
    target: Target
    total: Rational
    count: int


@dataclass(frozen=True, slots=True)
class Adequacy:
    decision_eligible: bool
    reason: str
    max_width_squared: tuple[Fraction, ...] | None
    joint_coverage_lower: Fraction | None
    emitted_miss_upper: Fraction


@dataclass(frozen=True, slots=True)
class Interval:
    metric: Metric
    mean: Fraction
    radius_squared: Fraction
    lower: Decimal
    upper: Decimal
    display_width: Fraction
    exact_point: Fraction | None


@dataclass(frozen=True, slots=True)
class Report:
    adequacy: Adequacy
    intervals: tuple[Interval, ...]


def _rational(value: Rational) -> Fraction:
    if type(value) is int:
        if value.bit_length() > 256:
            raise ScoreError("numeric_limit")
        return Fraction(value)
    if type(value) is Fraction:
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > 256:
            raise ScoreError("numeric_limit")
        return value
    raise ScoreError("exact_rational_required")


def _validate_model(model: Model, tail_exponent: int) -> None:
    if type(tail_exponent) is not int or tail_exponent != 5:
        raise ScoreError("unsupported_tail_budget")
    if type(model) is not Model:
        raise ScoreError("model_required")
    if type(model.scope) is not Scope or model.scope is not Scope.SYNTHETIC:
        raise ScoreError("synthetic_only")
    if (
        type(model.n) is not int
        or not 1 <= model.n <= 1048576
        or type(model.classes) is not int
        or not 1 <= model.classes <= 64
        or type(model.dense) is not bool
    ):
        raise ScoreError("invalid_geometry")
    if any(
        type(value) is not Declaration or value is not Declaration.FIXTURE_DECLARED
        for value in (
            model.stationarity,
            model.support,
            model.independent_classes,
            model.complete_calendar,
        )
    ):
        raise ScoreError("unknown_assumptions")


def _target(target: Target) -> tuple[Fraction, Fraction, Fraction]:
    if type(target) is not Target or type(target.metric) is not Metric:
        raise ScoreError("target_required")
    lo, hi, width = (_rational(v) for v in (target.lower, target.upper, target.width))
    if lo > hi or width <= _ALLOWANCE:
        raise ScoreError("invalid_support_or_width")
    if target.metric is Metric.WIN and (lo, hi) != (Fraction(0), Fraction(1)):
        raise ScoreError("win_support_required")
    return lo, hi, width


def assess(model: Model, targets: tuple[Target, ...], *, tail_exponent: int) -> Adequacy:
    """Pre-data useful eligibility, with a fixed outward-display allowance.

    Joint coverage concerns <=3 fixed targets under the declared model. On
    sparse histories only unconditional emitted-and-miss control applies;
    neither zero-count nor precision-selected conditional coverage is claimed.
    Dimensions/256-bit inputs bound all integer arithmetic before computation.
    """
    _validate_model(model, tail_exponent)
    if type(targets) is not tuple or not 1 <= len(targets) <= 3:
        raise ScoreError("invalid_metric_budget")
    supports = tuple(_target(t) for t in targets)
    if len({t.metric for t in targets}) != len(targets):
        raise ScoreError("duplicate_metric")
    squares = tuple(
        Fraction(40 * model.classes, model.n) * (hi - lo) ** 2 for lo, hi, _ in supports
    )
    fits = all(
        square <= (width - _ALLOWANCE) ** 2
        for square, (_, _, width) in zip(squares, supports, strict=True)
    )
    eligible = model.dense and fits
    reason = (
        ""
        if eligible
        else "history_insufficient"
        if model.dense
        else "sparse_selection_unsupported"
    )
    miss_upper = 2 * len(targets) / _EXPONENTIAL_LOWER
    return Adequacy(
        eligible,
        reason,
        squares if model.dense else None,
        1 - miss_upper if model.dense else None,
        miss_upper,
    )


def _upper_radius(square: Fraction) -> Fraction:
    scaled_numerator = square.numerator * _SCALE**2
    floor = isqrt(scaled_numerator // square.denominator)
    ceiling = floor if floor**2 * square.denominator == scaled_numerator else floor + 1
    return Fraction(ceiling, _SCALE)


def _endpoint(value: Fraction, *, upper: bool) -> Decimal:
    scaled = value * _SCALE
    integer = (
        -(-scaled.numerator // scaled.denominator)
        if upper
        else scaled.numerator // scaled.denominator
    )
    digits = tuple(int(c) for c in str(abs(integer)))
    # Tuple construction is exact even with a caller's very small Decimal context.
    return Decimal((int(integer < 0), digits, -_GRID_DIGITS))


def calculate(model: Model, observations: tuple[Totals, ...], *, tail_exponent: int) -> Report:
    """Outward intervals; observed counts never rescue failed pre-data eligibility.

    Counts must represent the same complete selected cohort for every target.
    Aggregate support checks are necessary but cannot certify individual rows.
    """
    if type(observations) is not tuple or not 1 <= len(observations) <= 3:
        raise ScoreError("invalid_metric_budget")
    if any(type(item) is not Totals for item in observations):
        raise ScoreError("totals_required")
    adequacy = assess(
        model, tuple(item.target for item in observations), tail_exponent=tail_exponent
    )
    intervals = []
    for item in observations:
        count = item.count
        if type(count) is not int or not 0 <= count <= 2 * model.n:
            raise ScoreError("invalid_count")
        if count == 0:
            raise ScoreError("zero_count")
        if model.dense and count < model.n:
            raise ScoreError("dense_count_violation")
        if count != observations[0].count:
            raise ScoreError("different_cohorts")
        lo, hi, width = _target(item.target)
        total = _rational(item.total)
        if not lo * count <= total <= hi * count:
            raise ScoreError("support_violation")
        if item.target.metric is Metric.WIN and total.denominator != 1:
            raise ScoreError("integer_wins_required")
        mean = total / count
        square = Fraction(10 * model.classes * model.n, count**2) * (hi - lo) ** 2
        radius = _upper_radius(square)
        lower = _endpoint(mean - radius, upper=False)
        upper = _endpoint(mean + radius, upper=True)
        display_width = Fraction(upper) - Fraction(lower)
        if adequacy.decision_eligible and display_width > width:
            raise ScoreError("numerical_contract_violation")
        intervals.append(
            Interval(
                item.target.metric,
                mean,
                square,
                lower,
                upper,
                display_width,
                lo if lo == hi else None,
            )
        )
    return Report(adequacy, tuple(intervals))
