"""Deterministic independent checks of the bounded synthetic research contract."""

from dataclasses import replace
from decimal import Decimal, getcontext, localcontext
from fractions import Fraction
from itertools import product
from typing import cast

import pytest
from scripts.research import signal_bounded_uncertainty as m

Result = m.BoundedEstimate | m.StructurallyKnown | m.InsufficientEvidence | m.Refusal


def fixture(
    counts: tuple[int, ...],
    values: tuple[m.Numeric, ...],
    lower: m.Numeric = 0,
    upper: m.Numeric = 1,
) -> tuple[m.SourceContract, tuple[m.Observation, ...]]:

    groups = tuple(
        m.GroupContract(str(g), n, m.Support(lower, upper)) for g, n in enumerate(counts)
    )
    members = tuple(
        m.Member(str(i), i, str(g))
        for g, n in enumerate(counts)
        for i in range(sum(counts[:g]), sum(counts[: g + 1]))
    )
    source = m.SourceContract(
        "scripted-fixture",
        "predeclared-script-v1",
        0,
        len(values) - 1,
        members,
        groups,
        independence=m.Declaration.FIXTURE_DECLARED,
        support=m.Declaration.FIXTURE_DECLARED,
        geometry=m.Declaration.FIXTURE_DECLARED,
    )
    observations = tuple(
        m.Observation(member.identifier, member.entry, value)
        for member, value in zip(members, values, strict=True)
    )
    return source, observations


def call(
    source: m.SourceContract,
    observations: tuple[m.Observation, ...],
    epsilon: m.Numeric = 1,
    metric: m.Metric | None = None,
) -> Result:

    return m.estimate(
        source,
        observations,
        metric=m.Metric.RAW if metric is None else metric,
        alpha=Fraction(1, 20),
        desired_precision=epsilon,
    )


def test_independent_high_precision_oracle_and_exact_weights() -> None:

    counts = (1, 2, 3, 4) * 3
    values = tuple(Fraction(i % 5, 4) for i in range(sum(counts)))
    source, rows = fixture(counts, values)
    result = call(source, rows)
    assert isinstance(result, m.BoundedEstimate)
    assert result.mean == sum(values) / len(values)
    q = sum(Fraction(n, sum(counts)) ** 2 for n in counts)
    assert result.q == q and result.weight_effective_groups == 1 / q
    with localcontext() as context:
        context.prec = 160
        qd = Decimal(q.numerator) / Decimal(q.denominator)
        mean = Decimal(result.mean.numerator) / Decimal(result.mean.denominator)
        radius = (qd * Decimal(40).ln() / 2).sqrt()
        assert result.radius >= radius
        assert result.untrimmed_lower <= mean - radius
        assert result.untrimmed_upper >= mean + radius
        assert result.lower <= max(Decimal(0), mean - radius)
        assert result.upper >= min(Decimal(1), mean + radius)
    assert result.authority == "SYNTHETIC_RESEARCH_ONLY"
    assert result.coverage_scope == "UNCONDITIONAL_UNDER_DECLARED_ASSUMPTIONS"


def test_observed_constants_keep_positive_radius() -> None:

    source, rows = fixture((1,) * 8, (1,) * 8)
    result = call(source, rows)
    assert isinstance(result, m.BoundedEstimate)
    assert result.radius > 0 and result.lower < 1 and result.upper == 1


def test_heterogeneous_singletons_have_exact_weighted_value() -> None:

    source, rows = fixture((1, 2), (Fraction(1, 3), Fraction(2, 7), Fraction(2, 7)))
    groups = (
        m.GroupContract("0", 1, m.Support(Fraction(1, 3), Fraction(1, 3))),
        m.GroupContract("1", 2, m.Support(Fraction(2, 7), Fraction(2, 7))),
    )
    result = call(replace(source, groups=groups), rows)
    assert isinstance(result, m.StructurallyKnown)
    assert result.value == Fraction(19, 63)


def test_precision_counts_groups_not_trades_or_clipping() -> None:

    source, rows = fixture((8,) * 24, (0,) * 192)
    result = call(source, rows, Fraction(1, 4))
    assert isinstance(result, m.InsufficientEvidence)
    assert result.reason is m.RefusalReason.NEEDS_MORE_INDEPENDENT_EVIDENCE
    assert result.normalized_width > Decimal(".554442622")
    assert result.weight_effective_groups == 24
    assert not hasattr(result, "lower")
    for groups in (119, 192):
        source, rows = fixture((1,) * groups, (0,) * groups)
        assert isinstance(call(source, rows, Fraction(1, 4)), m.BoundedEstimate)
    source, rows = fixture((1,) * 118, (0,) * 118)
    assert isinstance(call(source, rows, Fraction(1, 4)), m.InsufficientEvidence)


def test_concentration_and_permutation_invariance() -> None:

    source, rows = fixture((4, 8, 16, 32) * 6, (Fraction(1, 2),) * 360)
    result = call(source, rows)
    assert isinstance(result, m.BoundedEstimate)
    assert result.weight_effective_groups == Fraction(270, 17)
    assert call(source, rows[::-1]) == result
    assert (
        call(replace(source, members=source.members[::-1], groups=source.groups[::-1]), rows[::-1])
        == result
    )


def test_signed_affine_support_transform() -> None:

    values = (Fraction(0), Fraction(1)) * 4
    source, rows = fixture((1,) * 8, values)
    base = call(source, rows)
    other_source, other_rows = fixture((1,) * 8, tuple(3 - 2 * x for x in values), 1, 3)
    other = call(other_source, other_rows)
    assert isinstance(base, m.BoundedEstimate) and isinstance(other, m.BoundedEstimate)
    assert other.mean == 3 - 2 * base.mean and other.q == 4 * base.q
    assert abs(Fraction(other.radius) - 2 * Fraction(base.radius)) < Fraction(1, 10**75)
    assert abs(Fraction(other.lower) - (3 - 2 * Fraction(base.upper))) < Fraction(1, 10**75)
    assert abs(Fraction(other.upper) - (3 - 2 * Fraction(base.lower))) < Fraction(1, 10**75)


def test_win_is_derived_from_raw_and_excess_requires_whole_pairing() -> None:

    source, rows = fixture((1,) * 8, (-1, 1) * 4, -1, 1)
    win = call(source, rows, metric=m.Metric.WIN)
    assert isinstance(win, m.BoundedEstimate) and win.mean == Fraction(1, 2)
    missing = call(source, rows, metric=m.Metric.SYNTHETIC_EXCESS)
    assert isinstance(missing, m.Refusal) and missing.reason is m.RefusalReason.MISSING_BENCHMARK
    groups = tuple(replace(g, benchmark_support=m.Support(-1, 1)) for g in source.groups)
    rows = tuple(replace(row, benchmark=Fraction(1, 2)) for row in rows)
    result = call(replace(source, groups=groups), rows, metric=m.Metric.SYNTHETIC_EXCESS)
    assert isinstance(result, m.BoundedEstimate)
    assert (
        result.mean == Fraction(-1, 2) and result.support_lower == -2 and result.support_upper == 2
    )


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("scope", "real_data", "REAL_DATA_FORBIDDEN"),
        ("independence", "unknown", "UNKNOWN_INDEPENDENCE"),
        ("support", "observed", "UNKNOWN_SUPPORT"),
        ("geometry", "outcome_dependent", "OUTCOME_DEPENDENT_GEOMETRY"),
    ],
)
def test_assumption_refusals(field: str, value: str, reason: str) -> None:

    source, rows = fixture((1,) * 8, (0,) * 8)
    if field == "scope":
        source = replace(source, scope=m.Scope(value))
    elif field == "independence":
        source = replace(source, independence=m.Declaration(value))
    elif field == "support":
        source = replace(source, support=m.Declaration(value))
    else:
        source = replace(source, geometry=m.Declaration(value))
    result = call(source, rows)
    assert isinstance(result, m.Refusal) and result.reason is m.RefusalReason[reason]


@pytest.mark.parametrize(
    "change",
    [
        "duplicate",
        "missing",
        "coordinate",
        "count",
        "outside",
        "bool",
        "nan",
        "unknown_provenance",
        "bad_span",
    ],
)
def test_input_refusals(change: str) -> None:

    source, rows = fixture((1,) * 8, (0,) * 8)
    if change == "duplicate":
        rows = (*rows[:-1], rows[0])
    elif change == "missing":
        rows = rows[:-1]
    elif change == "coordinate":
        rows = (replace(rows[0], entry=1), *rows[1:])
    elif change == "count":
        source = replace(source, groups=(replace(source.groups[0], count=2), *source.groups[1:]))
    elif change == "outside":
        rows = (replace(rows[0], raw=2), *rows[1:])
    elif change == "bool":
        rows = (replace(rows[0], raw=True), *rows[1:])
    elif change == "nan":
        rows = (replace(rows[0], raw=Decimal("NaN")), *rows[1:])
    elif change == "unknown_provenance":
        source = replace(source, provenance="")
    else:
        source = replace(source, first_session=True)
    assert isinstance(call(source, rows), m.Refusal)


@pytest.mark.parametrize(
    ("alpha", "precision"),
    [(0, 1), (1, 1), (Fraction(-1, 2), 1), (Fraction(1, 20), 0), (Fraction(1, 20), 2), (True, 1)],
)
def test_alpha_precision_refuse(alpha: object, precision: object) -> None:

    source, rows = fixture((1,) * 8, (0,) * 8)
    assert isinstance(
        m.estimate(
            source,
            rows,
            metric=m.Metric.RAW,
            alpha=cast(m.Numeric, alpha),
            desired_precision=cast(m.Numeric, precision),
        ),
        m.Refusal,
    )


def test_exhaustive_bernoulli_coverage_with_exact_probabilities() -> None:

    probability = Fraction(1, 2)
    covered = Fraction(0)
    refused = 0
    for values in product((0, 1), repeat=8):
        source, rows = fixture((1,) * 8, values)
        result = call(source, rows)
        if not isinstance(result, m.BoundedEstimate):
            refused += 1
            continue
        if result.lower <= Decimal(".5") <= result.upper:
            covered += probability**8
    assert refused == 0
    assert covered == Fraction(127, 128)
    assert covered >= Fraction(19, 20)


def test_local_decimal_context_and_resolution_refusal() -> None:

    before = getcontext().copy()
    source, rows = fixture((1,) * 8, (Fraction(1, 2),) * 8)
    result = call(source, rows)
    assert isinstance(result, m.BoundedEstimate)
    assert getcontext().prec == before.prec and getcontext().rounding == before.rounding
    lower = 10**100
    source, rows = fixture((1,) * 8, (lower,) * 8, lower, lower + 1)
    result = call(source, rows)
    assert isinstance(result, m.Refusal) and result.reason is m.RefusalReason.NUMERICAL_RESOLUTION


@pytest.mark.parametrize("upper", [Fraction(1, 10**400), float.fromhex("0x0.0000000000001p-1022")])
def test_tiny_nonzero_support_never_becomes_known(upper: m.Numeric) -> None:

    source, rows = fixture((1,) * 8, (0,) * 8, 0, upper)
    result = call(source, rows)
    assert isinstance(result, m.BoundedEstimate) and result.radius > 0
    assert result.support_upper > 0 and result.q > 0


def test_unknown_benchmark_support_refuses_paired_values() -> None:

    source, rows = fixture((1,) * 8, (0,) * 8)
    paired = tuple(replace(row, benchmark=0) for row in rows)
    result = call(source, paired, metric=m.Metric.SYNTHETIC_EXCESS)
    assert isinstance(result, m.Refusal) and result.reason is m.RefusalReason.UNKNOWN_SUPPORT


def test_extreme_alpha_ignores_ambient_decimal_limits() -> None:

    source, rows = fixture((1,) * 4096, (0,) * 4096)
    baseline = m.estimate(
        source, rows, metric=m.Metric.RAW, alpha=Fraction(1, 10**400), desired_precision=1
    )
    assert isinstance(baseline, m.BoundedEstimate)
    with localcontext() as context:
        context.prec = 7
        context.Emax = 9
        context.Emin = -9
        for signal in context.traps:
            context.traps[signal] = True
        actual = m.estimate(
            source, rows, metric=m.Metric.RAW, alpha=Fraction(1, 10**400), desired_precision=1
        )
        assert actual == baseline
        assert context.prec == 7 and context.Emax == 9 and context.Emin == -9


def test_exhaustive_rare_bernoulli_coverage() -> None:

    p = Fraction(1, 10)
    covered = Fraction(0)
    for values in product((0, 1), repeat=8):
        source, rows = fixture((1,) * 8, values)
        result = call(source, rows)
        assert isinstance(result, m.BoundedEstimate)
        if result.lower <= Decimal(".1") <= result.upper:
            successes = sum(values)
            covered += p**successes * (1 - p) ** (8 - successes)
    assert covered == Fraction(19991367, 20000000)
    assert covered >= Fraction(19, 20)


def test_precision_plan_does_not_depend_on_observed_mean() -> None:

    zero_source, zeros = fixture((1,) * 8, (0,) * 8)
    third_source, thirds = fixture((1,) * 8, (Fraction(1, 3),) * 8)
    zero = call(zero_source, zeros)
    third = call(third_source, thirds)
    assert isinstance(zero, m.BoundedEstimate) and isinstance(third, m.BoundedEstimate)
    assert zero.normalized_width == third.normalized_width


@pytest.mark.parametrize(
    ("omitted", "reason"),
    [
        ("independence", "UNKNOWN_INDEPENDENCE"),
        ("support", "UNKNOWN_SUPPORT"),
        ("geometry", "OUTCOME_DEPENDENT_GEOMETRY"),
    ],
)
def test_omitted_assumption_is_not_a_positive_certificate(omitted: str, reason: str) -> None:

    source, rows = fixture((1,) * 8, (0,) * 8)
    common = (
        source.fixture,
        source.provenance,
        source.first_session,
        source.last_session,
        source.members,
        source.groups,
    )
    declared = m.Declaration.FIXTURE_DECLARED
    if omitted == "independence":
        omitted_source = m.SourceContract(*common, support=declared, geometry=declared)
    elif omitted == "support":
        omitted_source = m.SourceContract(*common, independence=declared, geometry=declared)
    else:
        omitted_source = m.SourceContract(*common, independence=declared, support=declared)
    result = call(omitted_source, rows)
    assert isinstance(result, m.Refusal) and result.reason is m.RefusalReason[reason]
