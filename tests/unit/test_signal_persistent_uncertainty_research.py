"""Deterministic persistent-law geometry, error-budget and arithmetic checks."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import cast

import pytest
from scripts.research import signal_bounded_uncertainty as m


def fixture(
    n: int, count: int = 1, lower: m.Numeric = 0, upper: m.Numeric = 1
) -> tuple[m.SourceContract, tuple[m.Observation, ...]]:
    groups = tuple(m.GroupContract(str(g), count, m.Support(lower, upper)) for g in range(n))
    members = tuple(m.Member(str(i), i, str(i // count)) for i in range(n * count))
    source = m.SourceContract(
        "ar-fixture",
        "fixed-source-v1",
        0,
        n * count - 1,
        members,
        groups,
        support=m.Declaration.FIXTURE_DECLARED,
        geometry=m.Declaration.FIXTURE_DECLARED,
    )
    rows = tuple(m.Observation(member.identifier, member.entry, lower) for member in members)
    return source, rows


def model(
    source: m.SourceContract, r: m.Numeric = Fraction(1, 2), k: int = 10
) -> m.PersistentModelContract:
    classes = tuple(
        m.IndependentClass(
            str(c), tuple(g.identifier for i, g in enumerate(source.groups) if i % k == c)
        )
        for c in range(min(k, len(source.groups)))
    )
    indices = tuple(m.LatentIndex(g.identifier, i, "latent-F") for i, g in enumerate(source.groups))
    declared = m.Declaration.FIXTURE_DECLARED
    return m.PersistentModelContract(
        source.fixture,
        "stationary-law-v1",
        "latent-F",
        indices,
        classes,
        r,
        stationary_gaussian_start=declared,
        independent_gaussian_innovations=declared,
        known_persistence_bound=declared,
        whole_local_map=declared,
        independent_local_noise=declared,
        marginal_preservation=declared,
        geometry=declared,
    )


def call(
    source: m.SourceContract,
    rows: tuple[m.Observation, ...],
    contract: m.PersistentModelContract,
    metric: m.Metric = m.Metric.RAW,
    alpha: m.Numeric = Fraction(1, 20),
    precision: m.Numeric = 1,
) -> m.PersistentResult | m.Refusal:
    return m.estimate_persistent(
        source, rows, contract, metric=metric, alpha=alpha, desired_precision=precision
    )


@pytest.mark.parametrize("alpha", [Fraction(1, 20), Fraction(1, 3)])
def test_zero_persistence_one_class_recovers_original_exact_arithmetic(alpha: Fraction) -> None:
    source, rows = fixture(24)
    original = m.estimate(
        replace(source, independence=m.Declaration.FIXTURE_DECLARED),
        rows,
        metric=m.Metric.RAW,
        alpha=alpha,
        desired_precision=1,
    )
    result = call(source, rows, model(source, 0, 1), alpha=alpha)
    assert isinstance(result, m.PersistentResult)
    assert result.calculation == original and result.dependence_upper == 0
    assert result.residual_budget_lower == alpha
    assert result.classes[0].delta_upper == 0


@pytest.mark.parametrize(
    ("n", "count", "r", "width", "delta"),
    [
        (24, 8, Fraction(1, 2), "2.245471627255", ".005691824721"),
        (192, 1, Fraction(1, 2), ".824724309740", ".020829557400"),
    ],
)
def test_proposal_examples_and_exact_original_trade_weights(
    n: int,
    count: int,
    r: Fraction,
    width: str,
    delta: str,
) -> None:
    source, rows = fixture(n, count)
    result = call(source, rows, model(source, r))
    assert isinstance(result, m.PersistentResult)
    assert isinstance(result.calculation, (m.BoundedEstimate, m.InsufficientEvidence))
    assert abs(Fraction(result.calculation.normalized_width) - Fraction(width)) < Fraction(
        1, 10**11
    )
    assert abs(Fraction(result.dependence_upper) - Fraction(delta)) < Fraction(1, 10**11)
    assert result.original_q == Fraction(1, n)
    assert sum((c.q for c in result.classes), Fraction()) == result.original_q
    assert result.residual_budget_lower == Fraction(1, 20) - Fraction(result.dependence_upper)
    assert isinstance(result.calculation, m.InsufficientEvidence if n == 24 else m.BoundedEstimate)


def test_error_budget_exhaustion_and_singleton_classes_have_exact_zero_transfer() -> None:
    source, rows = fixture(192)
    assert isinstance(call(source, rows, model(source, Fraction(3, 5))), m.Refusal)
    source, rows = fixture(8)
    result = call(source, rows, model(source, Fraction(999, 1000), 8), alpha=Fraction(1, 2))
    assert isinstance(result, m.PersistentResult)
    assert result.dependence_upper == 0
    assert all(c.delta_upper == 0 and c.gaps == () for c in result.classes)


def test_irregular_latent_gaps_not_calendar_spacing_and_monotone_persistence() -> None:
    source, rows = fixture(16)
    contract = model(source, Fraction(1, 10), 1)
    indices = tuple(replace(x, index=10 * i + (i % 2)) for i, x in enumerate(contract.indices))
    contract = replace(contract, indices=indices)
    first = call(source, rows, contract)
    assert isinstance(first, m.PersistentResult)
    assert first.classes[0].gaps == (11, 9) * 7 + (11,)
    members = tuple(replace(x, entry=100 * x.entry) for x in source.members)
    rows = tuple(replace(x, entry=100 * x.entry) for x in rows)
    changed = call(replace(source, members=members, last_session=1500), rows, contract)
    assert changed == first
    stronger = call(
        replace(source, members=members, last_session=1500),
        rows,
        replace(contract, persistence_bound=Fraction(1, 5)),
    )
    assert isinstance(stronger, m.PersistentResult)
    assert stronger.dependence_upper >= first.dependence_upper
    assert stronger.total_radius_upper >= first.total_radius_upper


def test_local_singleton_projection_and_model_validation_even_known() -> None:
    source, rows = fixture(8, lower=1, upper=2)
    contract = model(source, Fraction(1, 2), 2)
    win = call(source, rows, contract, m.Metric.WIN)
    assert isinstance(win, m.PersistentResult) and isinstance(win.calculation, m.StructurallyKnown)
    assert win.original_q == 0 and win.dependence_upper == 0
    assert all(c.active_indices == () for c in win.classes)
    assert all(c.indices for c in win.classes)
    groups = tuple(
        replace(g, raw_support=m.Support(1, 1)) if i % 2 == 0 else g
        for i, g in enumerate(source.groups)
    )
    raw = call(replace(source, groups=groups), rows, replace(contract, persistence_bound=0))
    assert isinstance(raw, m.PersistentResult)
    assert raw.classes[0].q == 0 and raw.classes[0].active_indices == ()
    assert raw.classes[1].q > 0
    invalid = replace(contract, indices=contract.indices[:-1])
    assert isinstance(call(source, rows, invalid, m.Metric.WIN), m.Refusal)


@pytest.mark.parametrize(
    "field",
    [
        "stationary_gaussian_start",
        "independent_gaussian_innovations",
        "known_persistence_bound",
        "whole_local_map",
        "independent_local_noise",
        "marginal_preservation",
        "geometry",
    ],
)
@pytest.mark.parametrize(
    "state", [m.Declaration.UNKNOWN, m.Declaration.OBSERVED, m.Declaration.OUTCOME_DEPENDENT]
)
def test_unjustified_law_and_local_map_premises_refuse(field: str, state: m.Declaration) -> None:
    source, rows = fixture(8)
    contract = model(source)
    if field == "stationary_gaussian_start":
        contract = replace(contract, stationary_gaussian_start=state)
    elif field == "independent_gaussian_innovations":
        contract = replace(contract, independent_gaussian_innovations=state)
    elif field == "known_persistence_bound":
        contract = replace(contract, known_persistence_bound=state)
    elif field == "whole_local_map":
        contract = replace(contract, whole_local_map=state)
    elif field == "independent_local_noise":
        contract = replace(contract, independent_local_noise=state)
    elif field == "marginal_preservation":
        contract = replace(contract, marginal_preservation=state)
    else:
        assert field == "geometry"
        contract = replace(contract, geometry=state)
    assert isinstance(call(source, rows, contract), m.Refusal)


@pytest.mark.parametrize(
    "change",
    [
        "default",
        "fixture",
        "provenance",
        "axis",
        "wrong_axis",
        "duplicate_index",
        "missing",
        "duplicate_group",
        "unknown_group",
        "bool_index",
        "negative",
        "float_index",
        "mutable",
        "partition",
        "power_cap",
        "bool_r",
        "negative_r",
        "unit_r",
        "nan_r",
    ],
)
def test_model_map_partition_and_preallocation_refusals(change: str) -> None:
    source, rows = fixture(8)
    contract = model(source, Fraction(1, 2), 1)
    first = contract.indices[0]
    if change == "default":
        contract = m.PersistentModelContract(
            source.fixture,
            contract.provenance,
            contract.latent_axis,
            contract.indices,
            contract.classes,
            Fraction(1, 2),
        )
    elif change == "fixture":
        contract = replace(contract, fixture="foreign")
    elif change == "provenance":
        contract = replace(contract, provenance="")
    elif change == "axis":
        contract = replace(contract, latent_axis="")
    elif change == "wrong_axis":
        contract = replace(
            contract, indices=(replace(first, axis="calendar"), *contract.indices[1:])
        )
    elif change == "duplicate_index":
        contract = replace(
            contract,
            indices=(first, replace(contract.indices[1], index=first.index), *contract.indices[2:]),
        )
    elif change == "missing":
        contract = replace(contract, indices=contract.indices[:-1])
    elif change == "duplicate_group":
        contract = replace(contract, indices=(*contract.indices[:-1], first))
    elif change == "unknown_group":
        contract = replace(
            contract, indices=(replace(first, group_id="foreign"), *contract.indices[1:])
        )
    elif change == "bool_index":
        contract = replace(contract, indices=(replace(first, index=True), *contract.indices[1:]))
    elif change == "negative":
        contract = replace(contract, indices=(replace(first, index=-1), *contract.indices[1:]))
    elif change == "float_index":
        contract = replace(
            contract, indices=(replace(first, index=cast(int, 0.5)), *contract.indices[1:])
        )
    elif change == "mutable":
        contract = replace(
            contract, indices=cast(tuple[m.LatentIndex, ...], list(contract.indices))
        )
    elif change == "partition":
        contract = replace(contract, classes=())
    elif change == "power_cap":
        contract = replace(
            contract,
            indices=tuple(replace(x, index=i * 10**100) for i, x in enumerate(contract.indices)),
        )
    elif change == "bool_r":
        contract = replace(contract, persistence_bound=True)
    elif change == "negative_r":
        contract = replace(contract, persistence_bound=Fraction(-1, 2))
    elif change == "unit_r":
        contract = replace(contract, persistence_bound=1)
    else:
        contract = replace(contract, persistence_bound=Decimal("NaN"))
    assert isinstance(call(source, rows, contract), m.Refusal)


def test_positive_tiny_persistence_and_hostile_context_never_become_independence() -> None:
    source, rows = fixture(16)
    contract = model(source, Fraction(1, 10**400), 1)
    result = call(source, rows, contract)
    assert isinstance(result, m.PersistentResult)
    assert result.dependence_upper > 0 and result.classes[0].log_sum_upper > 0
    with localcontext() as context:
        context.prec = 7
        context.Emax = 9
        context.Emin = -9
        for signal in context.traps:
            context.traps[signal] = True
        assert call(source, rows, contract) == result
        assert context.prec == 7 and context.Emax == 9


def test_complete_bounded_pairing_and_outcome_independent_precision() -> None:
    source, rows = fixture(192)
    contract = model(source)
    assert isinstance(call(source, rows, contract, m.Metric.SYNTHETIC_EXCESS), m.Refusal)
    source = replace(
        source, groups=tuple(replace(g, benchmark_support=m.Support(0, 0)) for g in source.groups)
    )
    paired = tuple(replace(row, benchmark=0) for row in rows)
    raw = call(source, paired, contract)
    excess = call(source, paired, contract, m.Metric.SYNTHETIC_EXCESS)
    assert isinstance(raw, m.PersistentResult) and isinstance(excess, m.PersistentResult)
    assert raw.total_radius_upper == excess.total_radius_upper
    thirds = call(source, tuple(replace(row, raw=Fraction(1, 3)) for row in paired), contract)
    assert isinstance(thirds, m.PersistentResult)
    assert isinstance(raw.calculation, m.BoundedEstimate) and isinstance(
        thirds.calculation, m.BoundedEstimate
    )
    assert raw.calculation.normalized_width == thirds.calculation.normalized_width
    narrow = call(source, paired, contract, precision=Fraction(1, 4))
    assert isinstance(narrow, m.PersistentResult)
    assert isinstance(narrow.calculation, m.InsufficientEvidence)


@pytest.mark.parametrize(
    "change",
    [
        "real",
        "support",
        "geometry",
        "missing",
        "duplicate",
        "coordinate",
        "count",
        "outside",
        "nonfinite",
        "pair_missing",
        "pair_unknown",
        "pair_outside",
        "bad_alpha",
        "bad_precision",
    ],
)
def test_persistent_entry_dispatch_retains_source_and_pair_guards(change: str) -> None:
    source, rows = fixture(16)
    contract = model(source, 0, 1)
    metric = m.Metric.RAW
    alpha: m.Numeric = Fraction(1, 20)
    precision: m.Numeric = 1
    if change == "real":
        source = replace(source, scope=m.Scope.REAL_DATA)
    elif change == "support":
        source = replace(source, support=m.Declaration.UNKNOWN)
    elif change == "geometry":
        source = replace(source, geometry=m.Declaration.OUTCOME_DEPENDENT)
    elif change == "missing":
        rows = rows[:-1]
    elif change == "duplicate":
        rows = (*rows[:-1], rows[0])
    elif change == "coordinate":
        rows = (replace(rows[0], entry=1), *rows[1:])
    elif change == "count":
        source = replace(source, groups=(replace(source.groups[0], count=2), *source.groups[1:]))
    elif change == "outside":
        rows = (replace(rows[0], raw=2), *rows[1:])
    elif change == "nonfinite":
        rows = (replace(rows[0], raw=Decimal("Infinity")), *rows[1:])
    elif change == "bad_alpha":
        alpha = 0
    elif change == "bad_precision":
        precision = 0
    else:
        metric = m.Metric.SYNTHETIC_EXCESS
        if change != "pair_missing":
            rows = tuple(replace(row, benchmark=2) for row in rows)
        if change == "pair_outside":
            source = replace(
                source,
                groups=tuple(replace(g, benchmark_support=m.Support(0, 1)) for g in source.groups),
            )
    assert isinstance(call(source, rows, contract, metric, alpha, precision), m.Refusal)


@pytest.mark.parametrize("change", ["rho", "model", "partition", "map"])
def test_all_known_still_validates_entire_persistent_contract(change: str) -> None:
    source, rows = fixture(8, lower=1, upper=1)
    contract = model(source)
    if change == "rho":
        contract = replace(contract, persistence_bound=1)
    elif change == "model":
        contract = replace(contract, stationary_gaussian_start=m.Declaration.UNKNOWN)
    elif change == "partition":
        contract = replace(contract, classes=())
    else:
        contract = replace(contract, indices=(contract.indices[0],) * 8)
    assert isinstance(call(source, rows, contract), m.Refusal)


def test_projected_random_gap_retains_removed_singleton_contribution() -> None:
    source, rows = fixture(4)
    source = replace(
        source,
        groups=tuple(
            replace(g, raw_support=m.Support(0, 0)) if i % 2 else g
            for i, g in enumerate(source.groups)
        ),
    )
    result = call(source, rows, model(source, Fraction(1, 10), 1), alpha=Fraction(1, 2))
    assert isinstance(result, m.PersistentResult)
    c = result.classes[0]
    assert c.indices == (0, 1, 2, 3) and c.active_indices == (0, 2) and c.gaps == (2,)
    assert c.q == Fraction(1, 8) and result.original_q == Fraction(1, 8)


def test_small_gaussian_covariance_determinant_matches_class_log_upper() -> None:
    source, rows = fixture(3)
    contract = model(source, Fraction(1, 10), 1)
    contract = replace(
        contract,
        indices=tuple(
            replace(point, index=t) for point, t in zip(contract.indices, (0, 2, 7), strict=True)
        ),
    )
    result = call(source, rows, contract, alpha=Fraction(1, 2))
    assert isinstance(result, m.PersistentResult)
    a, b, c = Fraction(1, 10) ** 2, Fraction(1, 10) ** 7, Fraction(1, 10) ** 5
    determinant = (
        1 + 2 * a * b * c - a * a - b * b - c * c
    )  # Independent 3x3 covariance determinant.
    with localcontext() as context:
        context.prec = 160
        exact_log = -(Decimal(determinant.numerator) / Decimal(determinant.denominator)).ln()
        assert result.classes[0].log_sum_upper >= exact_log
        assert abs(Fraction(result.classes[0].log_sum_upper) - Fraction(exact_log)) < Fraction(
            1, 10**75
        )


def test_unequal_counts_heterogeneous_support_and_separate_class_radii() -> None:
    counts = (1, 2, 3, 4) * 3
    groups = tuple(
        m.GroupContract(str(g), n, m.Support(0, 1 + g % 3)) for g, n in enumerate(counts)
    )
    members = tuple(
        m.Member(str(i), i, str(g))
        for g, n in enumerate(counts)
        for i in range(sum(counts[:g]), sum(counts[: g + 1]))
    )
    source = m.SourceContract(
        "ar-fixture",
        "fixed-source-v1",
        0,
        29,
        members,
        groups,
        support=m.Declaration.FIXTURE_DECLARED,
        geometry=m.Declaration.FIXTURE_DECLARED,
    )
    rows = tuple(m.Observation(x.identifier, x.entry, 0) for x in members)
    result = call(source, rows, model(source, Fraction(1, 100), 2), alpha=Fraction(1, 2))
    assert isinstance(result, m.PersistentResult)
    expected = sum((Fraction(n, 30) * (1 + g % 3)) ** 2 for g, n in enumerate(counts))
    assert (
        result.original_q == expected and sum((c.q for c in result.classes), Fraction()) == expected
    )
    with localcontext() as context:
        context.prec = 160
        residual = Decimal(result.residual_budget_lower.numerator) / Decimal(
            result.residual_budget_lower.denominator
        )
        log = (Decimal(4) / residual).ln()
        radius = sum(
            (Decimal(c.q.numerator) / Decimal(c.q.denominator) * log / 2).sqrt()
            for c in result.classes
        )
        assert result.total_radius_upper >= radius


def test_near_zero_residual_is_exact_and_numerical_refusals_remain_honest() -> None:
    source, rows = fixture(192)
    contract = model(source)
    baseline = call(source, rows, contract)
    assert isinstance(baseline, m.PersistentResult)
    tiny = Fraction(1, 10**100)
    narrow = call(source, rows, contract, alpha=Fraction(baseline.dependence_upper) + tiny)
    assert isinstance(narrow, m.PersistentResult)
    assert narrow.residual_budget_lower == tiny
    assert isinstance(narrow.calculation, m.InsufficientEvidence)
    assert not hasattr(narrow.calculation, "lower")
    source, rows = fixture(16, lower=10**100, upper=10**100 + 1)
    assert isinstance(call(source, rows, model(source, 0, 1)), m.Refusal)
    source, rows = fixture(16, upper=Fraction(1, 10**400))
    tiny_support = call(source, rows, model(source, 0, 1))
    assert isinstance(tiny_support, m.PersistentResult)
    assert isinstance(tiny_support.calculation, m.BoundedEstimate)
    assert tiny_support.original_q > 0 and tiny_support.total_radius_upper > 0


def test_order_permutation_preserves_model_geometry_and_arithmetic() -> None:
    source, rows = fixture(192)
    contract = model(source)
    expected = call(source, rows, contract)
    changed = replace(
        contract,
        indices=contract.indices[::-1],
        classes=tuple(replace(c, group_ids=c.group_ids[::-1]) for c in contract.classes[::-1]),
    )
    actual = call(
        replace(source, members=source.members[::-1], groups=source.groups[::-1]),
        rows[::-1],
        changed,
    )
    assert actual == expected
