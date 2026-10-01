"""Deterministic original-cohort moment checks; true targets live only in oracles."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
from typing import cast

import pytest
from scripts.research import signal_moment_uncertainty as m


def fixture(
    counts: tuple[int, ...] = (1, 2),
    values: tuple[m.Numeric, ...] = (1, 2, 3),
    moments: tuple[m.Numeric, ...] = (4, 9),
    centers: tuple[m.Numeric, ...] = (0, 1),
    metric: m.Metric = m.Metric.RAW,
) -> tuple[m.MomentSourceContract, tuple[m.Observation, ...]]:
    declared = m.Declaration.FIXTURE_DECLARED
    groups = tuple(
        m.MomentGroupContract(
            str(i),
            count,
            f"whole-vector-law-{i}",
            "fixed-artificial-law-v1",
            metric,
            center,
            moment,
            declared,
            declared,
            declared,
        )
        for i, (count, center, moment) in enumerate(zip(counts, centers, moments, strict=True))
    )
    members = tuple(
        m.Member(str(j), j, str(i))
        for i, count in enumerate(counts)
        for j in range(sum(counts[:i]), sum(counts[:i]) + count)
    )
    source = m.MomentSourceContract(
        "fixed-fixture",
        "whole-joint-law-v1",
        0,
        len(values) - 1,
        members,
        groups,
        independence=declared,
        geometry=declared,
    )
    rows = tuple(
        m.Observation(member.identifier, member.entry, value)
        for member, value in zip(members, values, strict=True)
    )
    return source, rows


def request(
    width: m.Numeric = 100,
    alpha: m.Numeric = Fraction(1, 20),
    metric: m.Metric = m.Metric.RAW,
) -> m.MomentRequest:
    return m.MomentRequest(metric, alpha, width, m.Declaration.FIXTURE_DECLARED)


def call(
    source: m.MomentSourceContract,
    rows: tuple[m.Observation, ...],
    width: m.Numeric = 100,
) -> m.Result:
    return m.estimate(source, rows, request(width))


def test_preserves_original_mean_unequal_weights_and_known_moment_geometry() -> None:
    source, rows = fixture()
    result = call(source, rows)
    assert isinstance(result, m.MomentEstimate)
    assert result.mean == 2
    assert result.variance_bound == Fraction(40, 9)
    assert result.group_weights == (Fraction(1, 3), Fraction(2, 3))
    assert result.group_means == (Fraction(1), Fraction(5, 2))
    assert result.centers == (Fraction(0), Fraction(1))
    assert result.second_moments == (Fraction(4), Fraction(9))
    assert Fraction(result.radius) ** 2 >= Fraction(800, 9)
    assert Fraction(result.lower) <= result.mean - Fraction(result.radius)
    assert Fraction(result.upper) >= result.mean + Fraction(result.radius)
    assert Fraction(result.full_width) >= 2 * Fraction(result.radius)
    assert result.authority == "SYNTHETIC_RESEARCH_ONLY"
    assert result.coverage_scope == "UNCONDITIONAL_UNDER_DECLARED_ASSUMPTIONS"
    assert result.law_identities == ("whole-vector-law-0", "whole-vector-law-1")
    assert result.observations == 3 and result.groups == 2
    assert call(source, tuple(reversed(rows))) == result


def test_legal_huge_observations_are_neither_clipped_nor_support_refused() -> None:
    source, rows = fixture((1,), (10**100,), (1,), (0,))
    result = call(source, rows)
    assert isinstance(result, m.MomentEstimate)
    assert result.mean == 10**100
    assert result.lower < result.upper
    assert Fraction(result.lower) <= result.mean - Fraction(result.radius)
    assert Fraction(result.upper) >= result.mean + Fraction(result.radius)


def test_direct_paired_excess_retains_every_pair_and_uses_its_own_moment() -> None:
    source, rows = fixture(metric=m.Metric.SYNTHETIC_EXCESS)
    rows = tuple(replace(row, benchmark=10 + i) for i, row in enumerate(rows))
    result = m.estimate(source, rows, request(metric=m.Metric.SYNTHETIC_EXCESS))
    assert isinstance(result, m.MomentEstimate)
    assert result.mean == -9 and result.variance_bound == Fraction(40, 9)
    refused = m.estimate(source, rows, request())
    assert isinstance(refused, m.MomentRefusal)
    assert refused.reason is m.Reason.INCOMPATIBLE_MOMENT
    missing = m.estimate(
        source,
        (replace(rows[0], benchmark=None), *rows[1:]),
        request(metric=m.Metric.SYNTHETIC_EXCESS),
    )
    assert isinstance(missing, m.MomentRefusal)
    assert missing.reason is m.Reason.MISSING_BENCHMARK


def test_zero_moment_requires_group_average_not_identical_individual_values() -> None:
    source, rows = fixture((2, 1), (7, -3, 8), (0, 0), (2, 8))
    result = call(source, rows)
    assert isinstance(result, m.MomentEstimate)
    assert result.mean == 4 and result.variance_bound == 0
    assert result.radius == 0 and result.lower == result.upper == 4
    bad = call(source, (replace(rows[0], raw=8), *rows[1:]))
    assert isinstance(bad, m.MomentRefusal)
    assert bad.reason is m.Reason.ZERO_MOMENT_CONTRADICTION
    invalid = call(replace(source, independence=m.Declaration.UNKNOWN), rows)
    assert isinstance(invalid, m.MomentRefusal)
    assert invalid.reason is m.Reason.UNKNOWN_INDEPENDENCE


@pytest.mark.parametrize("field", ["moment", "whole_vector", "selection"])
@pytest.mark.parametrize(
    "declaration",
    [
        m.Declaration.UNKNOWN,
        m.Declaration.OBSERVED,
        m.Declaration.OUTCOME_DEPENDENT,
    ],
)
def test_unknown_fitted_or_selected_laws_refuse(field: str, declaration: m.Declaration) -> None:
    source, rows = fixture()
    group = (
        replace(source.groups[0], moment=declaration)
        if field == "moment"
        else replace(source.groups[0], whole_vector=declaration)
        if field == "whole_vector"
        else replace(source.groups[0], selection=declaration)
    )
    result = call(replace(source, groups=(group, source.groups[1])), rows)
    assert isinstance(result, m.MomentRefusal)


@pytest.mark.parametrize("field", ["law_identity", "provenance"])
def test_missing_whole_vector_law_provenance_refuses(field: str) -> None:
    source, rows = fixture()
    source = replace(
        source,
        groups=(
            (
                replace(source.groups[0], law_identity="")
                if field == "law_identity"
                else replace(source.groups[0], provenance="")
            ),
            source.groups[1],
        ),
    )
    assert isinstance(call(source, rows), m.MomentRefusal)


@pytest.mark.parametrize("declaration", list(m.Declaration)[1:])
def test_unknown_or_selected_source_and_precision_premises_refuse(
    declaration: m.Declaration,
) -> None:
    source, rows = fixture()
    for altered in (
        replace(source, geometry=declaration),
        replace(source, independence=declaration),
    ):
        assert isinstance(call(altered, rows), m.MomentRefusal)
    result = m.estimate(source, rows, replace(request(), selection=declaration))
    assert isinstance(result, m.MomentRefusal)


def test_real_data_win_and_wrong_runtime_contract_refuse() -> None:
    source, rows = fixture()
    assert isinstance(call(replace(source, scope=m.Scope.REAL_DATA), rows), m.MomentRefusal)
    assert isinstance(m.estimate(source, rows, request(metric=m.Metric.WIN)), m.MomentRefusal)
    assert isinstance(
        m.estimate(cast(m.MomentSourceContract, None), rows, request()), m.MomentRefusal
    )
    assert isinstance(m.estimate(source, rows, cast(m.MomentRequest, None)), m.MomentRefusal)


def test_complete_cohort_shift_duplicate_missing_and_extra_refuse() -> None:
    source, rows = fixture()
    invalid_rows = (
        rows[:-1],
        (*rows, rows[0]),
        (replace(rows[0], entry=1), *rows[1:]),
        (replace(rows[0], identifier="extra"), *rows[1:]),
    )
    for altered in invalid_rows:
        result = call(source, altered)
        assert isinstance(result, m.MomentRefusal)
        assert result.reason is m.Reason.INVALID_COHORT
    invalid_sources = (
        replace(source, groups=(replace(source.groups[0], count=2), source.groups[1])),
        replace(source, members=(source.members[0], *source.members)),
        replace(source, members=(replace(source.members[0], group_id="bad"), *source.members[1:])),
        replace(source, last_session=1),
    )
    for altered_source in invalid_sources:
        assert isinstance(call(altered_source, rows), m.MomentRefusal)


@pytest.mark.parametrize(
    "number",
    [True, float("inf"), float("nan"), Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")],
)
def test_nonfinite_and_bool_numeric_values_refuse(number: m.Numeric) -> None:
    source, rows = fixture()
    for field in ("center", "second_moment"):
        altered = (
            replace(source.groups[0], center=number)
            if field == "center"
            else replace(source.groups[0], second_moment=number)
        )
        assert isinstance(
            call(replace(source, groups=(altered, source.groups[1])), rows), m.MomentRefusal
        )
    assert isinstance(call(source, (replace(rows[0], raw=number), *rows[1:])), m.MomentRefusal)
    assert isinstance(m.estimate(source, rows, request(alpha=number)), m.MomentRefusal)
    assert isinstance(call(source, rows, width=number), m.MomentRefusal)


@pytest.mark.parametrize("alpha", [-1, 0, 1, 2])
def test_invalid_alpha_refuses(alpha: int) -> None:
    source, rows = fixture()
    assert isinstance(m.estimate(source, rows, request(alpha=alpha)), m.MomentRefusal)


@pytest.mark.parametrize("width", [-1, 0])
def test_invalid_absolute_precision_refuses(width: int) -> None:
    source, rows = fixture()
    assert isinstance(call(source, rows, width=width), m.MomentRefusal)


def test_negative_moment_refuses_and_optional_unused_benchmark_is_finite() -> None:
    source, rows = fixture()
    groups = (replace(source.groups[0], second_moment=-1), source.groups[1])
    assert isinstance(call(replace(source, groups=groups), rows), m.MomentRefusal)
    assert isinstance(
        call(source, (replace(rows[0], benchmark=float("nan")), *rows[1:])), m.MomentRefusal
    )


def test_exact_precision_boundary_passes_and_width_never_trims() -> None:
    source, rows = fixture((1,), (10,), (Fraction(1, 4),), (0,))
    result = m.estimate(source, rows, request(2, Fraction(1, 4)))
    assert isinstance(result, m.MomentEstimate)
    assert result.radius == 1 and result.full_width == 2
    assert result.lower == 9 and result.upper == 11
    insufficient = m.estimate(source, rows, request(Fraction(199, 100), Fraction(1, 4)))
    assert isinstance(insufficient, m.MomentInsufficientEvidence)
    assert insufficient.radius == 1 and insufficient.full_width == 2
    assert not hasattr(insufficient, "lower")
    enlarged = m.estimate(
        replace(source, groups=(replace(source.groups[0], second_moment=1),)),
        rows,
        request(2, Fraction(1, 4)),
    )
    assert isinstance(enlarged, m.MomentInsufficientEvidence)
    assert enlarged.radius == 2


def test_tiny_positive_moment_and_hostile_ambient_decimal_context() -> None:
    source, rows = fixture((1,), (Fraction(1, 3),), (Decimal("1e-500"),), (0,))
    baseline = call(source, rows)
    assert isinstance(baseline, m.MomentEstimate)
    assert baseline.radius > 0
    assert Fraction(baseline.radius) ** 2 >= Fraction(Decimal("1e-500")) * 20
    assert Fraction(baseline.lower) <= baseline.mean - Fraction(baseline.radius)
    assert Fraction(baseline.upper) >= baseline.mean + Fraction(baseline.radius)
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        for signal in context.traps:
            context.traps[signal] = True
        assert call(source, rows) == baseline


@pytest.mark.parametrize(
    "number",
    [Decimal("1e1000000000"), Decimal("1e-1000000000"), 1 << 100000, Fraction(1, 1 << 100000)],
    ids=["positive-exponent", "negative-exponent", "integer", "fraction"],
)
def test_resource_guard_refuses_before_enormous_fraction_allocation(number: m.Numeric) -> None:
    source, rows = fixture()
    result = call(source, (replace(rows[0], raw=number), *rows[1:]))
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT


def test_known_sqrt_enclosure_independent_exact_oracle() -> None:
    source, rows = fixture((1,), (0,), (Fraction(1, 10),), (0,))
    result = m.estimate(source, rows, request(100, Fraction(1, 3)))
    assert isinstance(result, m.MomentEstimate)
    with localcontext() as context:
        context.prec = 200
        oracle = (Decimal(3) / 10).sqrt()
    assert result.radius >= oracle
    assert Fraction(result.radius) ** 2 >= Fraction(3, 10)
    assert result.radius - oracle < Decimal("1e-95")


@pytest.mark.parametrize("sign", [-1, 1])
def test_exact_finite_law_rare_gain_loss_unequal_original_weights(sign: int) -> None:
    # Two independent whole-group vectors: first has one trade, second two perfectly
    # dependent trades. True expectations are used only by this enumerating oracle.
    law = ((Fraction(0), Fraction(9999, 10000)), (Fraction(sign * 10000), Fraction(1, 10000)))
    true_target = Fraction(sign)
    miss = Fraction(0)
    total = Fraction(0)
    for (first, p1), (second, p2) in product(law, repeat=2):
        source, rows = fixture((1, 2), (first, second, second), (10000, 10000), (0, 0))
        result = call(source, rows, 100000)
        assert isinstance(result, m.MomentEstimate)
        assert result.mean == (first + 2 * second) / 3
        probability = p1 * p2
        total += probability
        if not Fraction(result.lower) <= true_target <= Fraction(result.upper):
            miss += probability
    assert total == 1
    assert 0 < miss <= Fraction(1, 20)
    assert miss == Fraction(19999, 100000000)


def test_exact_boundary_event_includes_equality() -> None:
    # Shifted symmetric rare law: outcomes 2, 0, 4 with probabilities 3/4,
    # 1/8, 1/8. Mean 2, centered moment 1, radius 2 at alpha=1/4.
    covered = Fraction(0)
    for value, probability in ((2, Fraction(3, 4)), (0, Fraction(1, 8)), (4, Fraction(1, 8))):
        source, rows = fixture((1,), (value,), (1,), (2,))
        result = m.estimate(source, rows, request(4, Fraction(1, 4)))
        assert isinstance(result, m.MomentEstimate)
        assert result.radius == 2
        assert Fraction(result.lower) <= 2 <= Fraction(result.upper)
        if value in (0, 4):
            assert result.lower == 2 or result.upper == 2
        covered += probability
    assert covered == 1


def test_malformed_runtime_fields_and_string_enums_refuse() -> None:
    source, rows = fixture()
    malformed_sources = (
        replace(source, members=cast(tuple[m.Member, ...], (None,))),
        replace(source, groups=cast(tuple[m.MomentGroupContract, ...], (None,))),
        replace(source, fixture=cast(str, [])),
        replace(source, independence=cast(m.Declaration, "fixture_declared")),
        replace(source, scope=cast(m.Scope, "synthetic_fixture")),
        replace(
            source,
            members=(replace(source.members[0], group_id=cast(str, [])), *source.members[1:]),
        ),
    )
    for malformed in malformed_sources:
        assert isinstance(call(malformed, rows), m.MomentRefusal)
    malformed_rows = (
        cast(tuple[m.Observation, ...], (None,)),
        (replace(rows[0], identifier=cast(str, [])), *rows[1:]),
        (replace(rows[0], raw=cast(m.Numeric, None)), *rows[1:]),
    )
    for malformed_rows_item in malformed_rows:
        assert isinstance(call(source, malformed_rows_item), m.MomentRefusal)
    assert isinstance(
        m.estimate(source, rows, replace(request(), metric=cast(m.Metric, "raw"))), m.MomentRefusal
    )
