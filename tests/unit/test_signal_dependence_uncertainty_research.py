"""Deterministic proof fixtures for the explicit within-class joint premise."""

from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from itertools import product
from typing import cast

import pytest
from scripts.research import signal_bounded_uncertainty as m


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
        "fixed-dependent-fixture",
        "scripted-before-outcomes",
        0,
        len(values) - 1,
        members,
        groups,
        support=m.Declaration.FIXTURE_DECLARED,
        geometry=m.Declaration.FIXTURE_DECLARED,
    )
    rows = tuple(
        m.Observation(member.identifier, member.entry, value)
        for member, value in zip(members, values, strict=True)
    )
    return source, rows


def partition(source: m.SourceContract, k: int = 2) -> m.DependenceContract:
    classes = tuple(
        m.IndependentClass(
            str(c), tuple(group.identifier for i, group in enumerate(source.groups) if i % k == c)
        )
        for c in range(k)
    )
    return m.DependenceContract(
        source.fixture,
        "fixed-latent-footprint-v1",
        classes,
        joint_independence=m.WithinClassIndependence.JOINT_FIXTURE_DECLARED,
        geometry=m.Declaration.FIXTURE_DECLARED,
    )


def call(
    source: m.SourceContract,
    rows: tuple[m.Observation, ...],
    contract: m.DependenceContract,
    metric: m.Metric = m.Metric.RAW,
    alpha: m.Numeric = Fraction(1, 2),
    precision: m.Numeric = 1,
) -> m.DependenceResult | m.Refusal:
    return m.estimate_dependence(
        source, rows, contract, metric=metric, alpha=alpha, desired_precision=precision
    )


@pytest.mark.parametrize("metric", list(m.Metric))
def test_one_class_reproduces_independent_calculation(metric: m.Metric) -> None:
    source, rows = fixture((1,) * 16, (-1, 1) * 8, -1, 1)
    source = replace(
        source, groups=tuple(replace(g, benchmark_support=m.Support(-1, 1)) for g in source.groups)
    )
    rows = tuple(replace(row, benchmark=Fraction(1, 4)) for row in rows)
    original = m.estimate(
        replace(source, independence=m.Declaration.FIXTURE_DECLARED),
        rows,
        metric=metric,
        alpha=Fraction(1, 20),
        desired_precision=1,
    )
    result = call(source, rows, partition(source, 1), metric, Fraction(1, 20))
    assert isinstance(result, m.DependenceResult)
    assert result.calculation == original
    assert result.active_classes == 1 and result.penalized_q == result.original_q
    assert source.independence is m.Declaration.UNKNOWN


def test_unequal_trade_weights_kq_and_independent_arithmetic_oracle() -> None:
    counts = (1, 2, 3, 4) * 4
    source, rows = fixture(counts, tuple(Fraction(i % 5, 4) for i in range(sum(counts))))
    result = call(source, rows, partition(source))
    assert isinstance(result, m.DependenceResult)
    calc = result.calculation
    assert isinstance(calc, m.BoundedEstimate)
    expected_q = sum((Fraction(n, sum(counts)) ** 2 for n in counts), Fraction())
    assert result.original_q == calc.q == expected_q == Fraction(3, 40)
    assert result.active_classes == 2 and result.penalized_q == Fraction(3, 20)
    assert calc.weight_effective_groups == Fraction(40, 3)
    assert result.penalized_range_effective_groups == Fraction(20, 3)
    with localcontext() as context:
        context.prec = 160
        radius = (Decimal(3) / 20 * Decimal(4).ln() / 2).sqrt()
        exact_mean = Decimal(calc.mean.numerator) / Decimal(calc.mean.denominator)
        assert calc.radius >= radius
        assert calc.untrimmed_lower <= exact_mean - radius
        assert calc.untrimmed_upper >= exact_mean + radius
    assert result.class_provenance == "fixed-latent-footprint-v1"


def test_permutation_class_labels_and_declared_k_monotonicity() -> None:
    source, rows = fixture((1,) * 192, (Fraction(1, 3),) * 192)
    results = [
        call(source, rows, partition(source, k), alpha=Fraction(1, 20)) for k in (1, 2, 4, 192)
    ]
    assert all(isinstance(r, m.DependenceResult) for r in results)
    radii = []
    for result in results:
        assert isinstance(result, m.DependenceResult)
        assert isinstance(result.calculation, (m.BoundedEstimate, m.InsufficientEvidence))
        radii.append(result.calculation.radius)
    assert radii == sorted(radii) and len(set(radii)) == 4
    assert isinstance(results[-1], m.DependenceResult)
    assert isinstance(results[-1].calculation, m.InsufficientEvidence)
    contract = partition(source)
    changed = replace(
        contract,
        classes=tuple(
            replace(c, identifier=f"renamed-{i}", group_ids=c.group_ids[::-1])
            for i, c in enumerate(contract.classes[::-1])
        ),
    )
    reversed_source = replace(source, members=source.members[::-1], groups=source.groups[::-1])
    assert call(reversed_source, rows[::-1], changed) == call(source, rows, contract)


def test_k_is_metric_support_only_and_known_classes_keep_contributions() -> None:
    source, rows = fixture((1,) * 8, (1,) * 8, 1, 2)
    contract = partition(source)
    raw = call(source, rows, contract)
    win = call(source, rows, contract, m.Metric.WIN)
    assert isinstance(raw, m.DependenceResult) and isinstance(raw.calculation, m.BoundedEstimate)
    assert raw.active_classes == 2 and raw.calculation.radius > 0
    assert isinstance(win, m.DependenceResult) and isinstance(win.calculation, m.StructurallyKnown)
    assert win.calculation.value == 1
    assert (win.original_q, win.active_classes, win.penalized_q) == (Fraction(), 0, Fraction())
    assert win.penalized_range_effective_groups is None
    groups = tuple(
        replace(g, raw_support=m.Support(1, 1)) if i % 2 == 0 else g
        for i, g in enumerate(source.groups)
    )
    mixed = call(replace(source, groups=groups), rows, contract)
    assert isinstance(mixed, m.DependenceResult) and isinstance(
        mixed.calculation, m.BoundedEstimate
    )
    assert mixed.active_classes == 1
    assert mixed.calculation.mean == 1 and mixed.calculation.support_lower == 1
    assert mixed.calculation.support_upper == Fraction(3, 2)
    assert mixed.original_q == Fraction(1, 16)


@pytest.mark.parametrize(
    "change",
    [
        "empty",
        "partial",
        "duplicate_group",
        "unknown_group",
        "duplicate_class",
        "empty_class",
        "bad_class_id",
        "bad_group_id",
        "mutable_groups",
        "provenance",
        "fixture",
        "unknown_joint",
        "pairwise",
        "observed",
        "geometry",
        "missing_defaults",
    ],
)
@pytest.mark.parametrize("singleton", [False, True])
def test_partition_refusals_even_when_support_is_structurally_known(
    change: str, singleton: bool
) -> None:
    source, rows = fixture((1,) * 8, (0,) * 8, 0, 0 if singleton else 1)
    contract = partition(source)
    first = contract.classes[0]
    if change == "empty":
        contract = replace(contract, classes=())
    elif change == "partial":
        contract = replace(contract, classes=contract.classes[:1])
    elif change == "duplicate_group":
        contract = replace(
            contract,
            classes=(
                replace(first, group_ids=(*first.group_ids, first.group_ids[0])),
                contract.classes[1],
            ),
        )
    elif change == "unknown_group":
        contract = replace(
            contract,
            classes=(replace(first, group_ids=(*first.group_ids, "foreign")), contract.classes[1]),
        )
    elif change == "duplicate_class":
        contract = replace(
            contract, classes=(first, replace(contract.classes[1], identifier=first.identifier))
        )
    elif change == "empty_class":
        contract = replace(contract, classes=(first, replace(contract.classes[1], group_ids=())))
    elif change == "bad_class_id":
        contract = replace(
            contract, classes=(replace(first, identifier=cast(str, True)), contract.classes[1])
        )
    elif change == "bad_group_id":
        contract = replace(
            contract, classes=(replace(first, group_ids=(cast(str, True),)), contract.classes[1])
        )
    elif change == "mutable_groups":
        contract = replace(
            contract,
            classes=(
                replace(first, group_ids=cast(tuple[str, ...], list(first.group_ids))),
                contract.classes[1],
            ),
        )
    elif change == "provenance":
        contract = replace(contract, provenance="")
    elif change == "fixture":
        contract = replace(contract, fixture="another-fixture")
    elif change == "unknown_joint":
        contract = replace(contract, joint_independence=m.WithinClassIndependence.UNKNOWN)
    elif change == "pairwise":
        contract = replace(contract, joint_independence=m.WithinClassIndependence.PAIRWISE_ONLY)
    elif change == "observed":
        contract = replace(contract, joint_independence=m.WithinClassIndependence.OBSERVED)
    elif change == "geometry":
        contract = replace(contract, geometry=m.Declaration.OUTCOME_DEPENDENT)
    else:
        contract = m.DependenceContract(source.fixture, contract.provenance, contract.classes)
    assert isinstance(call(source, rows, contract), m.Refusal)


@pytest.mark.parametrize(
    "change",
    [
        "real",
        "unknown_support",
        "geometry",
        "missing",
        "duplicate",
        "coordinate",
        "count",
        "outside",
        "nonfinite",
        "bool",
        "alpha",
        "precision",
        "cap",
        "paired_missing",
        "paired_unknown",
        "paired_outside",
    ],
)
def test_shared_source_metric_numeric_refusals(change: str) -> None:
    source, rows = fixture((1,) * 8, (0,) * 8)
    contract = partition(source)
    metric = m.Metric.RAW
    alpha: m.Numeric = Fraction(1, 2)
    precision: m.Numeric = 1
    if change == "real":
        source = replace(source, scope=m.Scope.REAL_DATA)
    elif change == "unknown_support":
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
        rows = (replace(rows[0], raw=Decimal("NaN")), *rows[1:])
    elif change == "bool":
        rows = (replace(rows[0], raw=True), *rows[1:])
    elif change == "alpha":
        alpha = 0
    elif change == "precision":
        precision = 0
    elif change == "cap":
        contract = replace(contract, classes=contract.classes * 2049)
    else:
        metric = m.Metric.SYNTHETIC_EXCESS
        if change != "paired_missing":
            rows = tuple(replace(row, benchmark=2) for row in rows)
        if change == "paired_outside":
            source = replace(
                source,
                groups=tuple(replace(g, benchmark_support=m.Support(0, 1)) for g in source.groups),
            )
    assert isinstance(call(source, rows, contract, metric, alpha, precision), m.Refusal)


def test_whole_paired_excess_uses_same_declared_partition() -> None:
    source, rows = fixture((1,) * 16, (-1, 1) * 8, -1, 1)
    source = replace(
        source, groups=tuple(replace(g, benchmark_support=m.Support(0, 1)) for g in source.groups)
    )
    rows = tuple(replace(row, benchmark=Fraction(1, 2)) for row in rows)
    result = call(source, rows, partition(source), m.Metric.SYNTHETIC_EXCESS)
    assert isinstance(result, m.DependenceResult) and isinstance(
        result.calculation, m.BoundedEstimate
    )
    assert result.calculation.mean == Fraction(-1, 2)
    assert result.calculation.support_lower == -2 and result.calculation.support_upper == 1
    assert result.original_q == Fraction(9, 16) and result.penalized_q == Fraction(9, 8)


def test_numerical_extremes_and_precision_are_shared_and_outcome_independent() -> None:
    source, rows = fixture((1,) * 16, (0,) * 16, 0, Fraction(1, 10**400))
    result = call(source, rows, partition(source))
    assert isinstance(result, m.DependenceResult) and isinstance(
        result.calculation, m.BoundedEstimate
    )
    assert result.calculation.radius > 0 and result.active_classes == 2
    hostile = localcontext()
    with hostile as context:
        context.prec = 7
        context.Emax = 9
        context.Emin = -9
        for signal in context.traps:
            context.traps[signal] = True
        assert call(source, rows, partition(source)) == result
        assert context.prec == 7 and context.Emax == 9 and context.Emin == -9
    large = 10**100
    source, rows = fixture((1,) * 16, (large,) * 16, large, large + 1)
    assert isinstance(call(source, rows, partition(source)), m.Refusal)
    source, rows = fixture((1,) * 192, (0,) * 192)
    zero = call(source, rows, partition(source), alpha=Fraction(1, 20))
    thirds = call(
        source,
        tuple(replace(r, raw=Fraction(1, 3)) for r in rows),
        partition(source),
        alpha=Fraction(1, 20),
    )
    assert isinstance(zero, m.DependenceResult) and isinstance(thirds, m.DependenceResult)
    assert isinstance(zero.calculation, m.BoundedEstimate)
    assert isinstance(thirds.calculation, m.BoundedEstimate)
    assert zero.calculation.normalized_width == thirds.calculation.normalized_width


@pytest.mark.parametrize("p", [Fraction(1, 10), Fraction(1, 2), Fraction(9, 10)])
@pytest.mark.parametrize("metric", [m.Metric.RAW, m.Metric.WIN])
def test_exhaustive_known_neighbor_latents_and_separate_95_percent_insufficiency(
    p: Fraction,
    metric: m.Metric,
) -> None:
    # Each same-parity class uses disjoint latent footprints, proving the fixture premise.
    footprints = [{i, i + 1} for i in range(8)]
    for parity in (0, 1):
        chosen = footprints[parity::2]
        assert all(not chosen[i] & chosen[j] for i in range(4) for j in range(i))
    target = p if metric is m.Metric.RAW else 1 - (1 - p) ** 2
    generated = emitted = refused = insufficient_95 = 0
    total_probability = covered = Fraction()
    for shocks in product((0, 1), repeat=9):
        raw = tuple(Fraction(shocks[i] + shocks[i + 1], 2) for i in range(8))
        source, rows = fixture((1,) * 8, raw)
        contract = partition(source)
        result = call(source, rows, contract, metric)
        generated += 1
        probability = p ** sum(shocks) * (1 - p) ** (9 - sum(shocks))
        total_probability += probability
        if isinstance(result, m.DependenceResult) and isinstance(
            result.calculation, m.BoundedEstimate
        ):
            emitted += 1
            if Fraction(result.calculation.lower) <= target <= Fraction(result.calculation.upper):
                covered += probability
        else:
            refused += 1
        at_95 = call(source, rows, contract, metric, Fraction(1, 20))
        assert isinstance(at_95, m.DependenceResult)
        assert isinstance(at_95.calculation, m.InsufficientEvidence)
        assert not hasattr(at_95.calculation, "lower")
        insufficient_95 += 1
    assert (generated, emitted, refused, insufficient_95) == (512, 512, 0, 512)
    expected = {
        (m.Metric.RAW, Fraction(1, 10)): Fraction(199867743, 200000000),
        (m.Metric.RAW, Fraction(1, 2)): Fraction(253, 256),
        (m.Metric.RAW, Fraction(9, 10)): Fraction(199867743, 200000000),
        (m.Metric.WIN, Fraction(1, 10)): Fraction(965392101, 1000000000),
        (m.Metric.WIN, Fraction(1, 2)): Fraction(499, 512),
        (m.Metric.WIN, Fraction(9, 10)): Fraction(999939411, 1000000000),
    }
    assert covered == expected[metric, p]
    assert total_probability == 1 and Fraction(1, 2) <= covered < 1


@pytest.mark.parametrize(("k", "insufficient", "sufficient"), [(2, 236, 237), (4, 472, 473)])
def test_predeclared_quarter_width_thresholds(k: int, insufficient: int, sufficient: int) -> None:
    for n, passes in ((insufficient, False), (sufficient, True)):
        source, rows = fixture((1,) * n, (0,) * n)
        result = call(
            source, rows, partition(source, k), alpha=Fraction(1, 20), precision=Fraction(1, 4)
        )
        assert isinstance(result, m.DependenceResult)
        expected = m.BoundedEstimate if passes else m.InsufficientEvidence
        assert isinstance(result.calculation, expected)


def test_uniform_more_trades_do_not_create_new_class_evidence() -> None:
    source, rows = fixture((1,) * 192, (0,) * 192)
    more_source, more_rows = fixture((2,) * 192, (0,) * 384)
    first = call(source, rows, partition(source))
    more = call(more_source, more_rows, partition(more_source))
    assert isinstance(first, m.DependenceResult) and isinstance(more, m.DependenceResult)
    assert isinstance(first.calculation, m.BoundedEstimate)
    assert isinstance(more.calculation, m.BoundedEstimate)
    assert first.calculation.normalized_width == more.calculation.normalized_width
    assert first.active_classes == more.active_classes == 2
    assert first.original_q == more.original_q and first.penalized_q == more.penalized_q


def test_pairwise_independent_xor_triple_does_not_supply_joint_premise() -> None:
    triples = tuple((u, v, u ^ v) for u, v in product((0, 1), repeat=2))
    for i, j in ((0, 1), (0, 2), (1, 2)):
        assert {(row[i], row[j]) for row in triples} == set(product((0, 1), repeat=2))
    assert (1, 1, 1) not in triples  # Joint support differs from three independent shocks.
    for values in triples:
        source, rows = fixture((1,) * 3, values)
        contract = replace(
            partition(source, 1), joint_independence=m.WithinClassIndependence.PAIRWISE_ONLY
        )
        result = call(source, rows, contract)
        assert isinstance(result, m.Refusal)
        assert result.reason is m.RefusalReason.UNKNOWN_CLASS_INDEPENDENCE
