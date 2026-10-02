"""Deterministic confidence, selection and rounding safeguards; no RNG."""

import importlib
from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction as F
from itertools import product
from math import factorial
from types import ModuleType
from typing import Any

import pytest


def module() -> ModuleType:
    name = "scripts.research.signal_calendar_score"
    assert importlib.util.find_spec(name) is not None, "reviewed calendar-score helper is missing"
    return importlib.import_module(name)


def model(n: int = 2048, classes: int = 2, dense: bool = True, **changes: Any) -> Any:
    m = module()
    declared = m.Declaration.FIXTURE_DECLARED
    return replace(
        m.Model(n, classes, dense, m.Scope.SYNTHETIC, declared, declared, declared, declared),
        **changes,
    )


def target(metric: str = "win", lo: Any = 0, hi: Any = 1, width: Any = F(1, 5)) -> Any:
    m = module()
    return m.Target(m.Metric(metric), lo, hi, width)


def test_baseline_plan_is_predata_and_its_report_is_jointly_eligible() -> None:
    m = module()
    targets = (
        target("raw", F(-1, 50), F(1, 50), F(1, 50)),
        target(),
        target("synthetic_excess", F(-2, 125), F(2, 125), F(1, 50)),
    )
    plan = m.assess(model(), targets, tail_exponent=5)
    assert plan.decision_eligible
    assert plan.max_width_squared == (F(1, 16000), F(5, 128), F(1, 25000))
    series = sum((F(5**j, factorial(j)) for j in range(11)), F())
    assert plan.joint_coverage_lower == 1 - 6 / series > F(19, 20)
    observations = tuple(
        m.Totals(t, F(512) if t.metric == m.Metric.WIN else F(0), 2048) for t in targets
    )
    report = m.calculate(model(), observations, tail_exponent=5)
    assert report.adequacy == plan
    assert all(i.display_width <= t.width for i, t in zip(report.intervals, targets, strict=True))


def test_short_history_is_not_rescued_by_high_realized_counts() -> None:
    m = module()
    spec = target()
    report = m.calculate(model(n=512), (m.Totals(spec, 256, 1024),), tail_exponent=5)
    assert report.intervals[0].display_width < F(1, 5)
    assert not report.adequacy.decision_eligible
    assert report.adequacy.reason == "history_insufficient"


def test_rounding_boundary_fails_before_observing_data() -> None:
    m = module()
    spec = target("raw", 0, 1, 1)
    plan = m.assess(model(40, 1), (spec,), tail_exponent=5)
    assert plan.max_width_squared == (F(1),)
    assert not plan.decision_eligible
    interval = m.calculate(
        model(40, 1), (m.Totals(spec, F(40, 3), 40),), tail_exponent=5
    ).intervals[0]
    assert F(interval.lower) <= F(-1, 6)
    assert F(interval.upper) >= F(5, 6)
    assert interval.display_width > 1


@pytest.mark.parametrize("center", [F(-7, 3), F(0), F(1, 3), F(9, 7)])
@pytest.mark.parametrize("n,classes,count", [(8, 1, 8), (64, 9, 100), (131072, 40, 262144)])
def test_exact_rational_oracle_proves_outward_endpoint_and_width_bounds(
    center: F, n: int, classes: int, count: int
) -> None:
    m = module()
    spec = target("raw", center - 1, center + 1, 10)
    interval = m.calculate(
        model(n, classes), (m.Totals(spec, center * count, count),), tail_exponent=5
    ).intervals[0]
    radius2 = F(40 * classes * n, count * count)
    left = center - F(interval.lower)
    right = F(interval.upper) - center
    assert left >= 0 and right >= 0
    assert left * left >= radius2 and right * right >= radius2
    assert interval.radius_squared == radius2
    assert interval.display_width == F(interval.upper) - F(interval.lower)
    d = F(1, 10**60)
    assert (interval.display_width - 4 * d) ** 2 <= 4 * radius2


def test_decimal_context_cannot_change_the_result() -> None:
    m = module()
    observations = (m.Totals(target("raw", -1, 1, 1), F(2048, 3), 2048),)
    with localcontext() as context:
        context.prec = 3
        low_precision = m.calculate(model(), observations, tail_exponent=5)
    with localcontext() as context:
        context.prec = 100
        assert m.calculate(model(), observations, tail_exponent=5) == low_precision


def test_nonterminating_point_retains_exact_truth_and_honest_display_enclosure() -> None:
    m = module()
    spec = target("raw", F(1, 3), F(1, 3), F(1, 100))
    result = m.calculate(model(), (m.Totals(spec, F(2048, 3), 2048),), tail_exponent=5)
    interval = result.intervals[0]
    assert result.adequacy.decision_eligible
    assert interval.exact_point == F(1, 3) and interval.radius_squared == 0
    assert F(interval.lower) <= F(1, 3) <= F(interval.upper)
    assert 0 < interval.display_width <= F(2, 10**60)


def test_sparse_result_has_no_selected_output_guarantee_and_zero_counts_refuse() -> None:
    m = module()
    sparse = model(dense=False)
    result = m.calculate(sparse, (m.Totals(target(), 1, 2),), tail_exponent=5)
    assert not result.adequacy.decision_eligible
    assert result.adequacy.reason == "sparse_selection_unsupported"
    assert result.adequacy.max_width_squared is None
    assert result.adequacy.joint_coverage_lower is None
    assert result.adequacy.emitted_miss_upper < F(1, 20)
    with pytest.raises(m.ScoreError, match="zero_count"):
        m.calculate(sparse, (m.Totals(target(), 0, 0),), tail_exponent=5)


@pytest.mark.parametrize(
    "field", ["stationarity", "support", "independent_classes", "complete_calendar"]
)
def test_unknown_assumptions_refuse(field: str) -> None:
    m = module()
    with pytest.raises(m.ScoreError, match="unknown_assumptions"):
        m.assess(model(**{field: m.Declaration.UNKNOWN}), (target(),), tail_exponent=5)


@pytest.mark.parametrize("scope", ["real", "synthetic", None])
def test_invalid_or_real_scope_refuses(scope: Any) -> None:
    m = module()
    with pytest.raises(m.ScoreError):
        m.assess(model(scope=scope), (target(),), tail_exponent=5)
    with pytest.raises(m.ScoreError):
        m.assess(model(scope=m.Scope.REAL), (target(),), tail_exponent=5)


@pytest.mark.parametrize(
    "field,value",
    [("n", True), ("n", 0), ("n", 1048577), ("classes", False), ("classes", 65), ("dense", 1)],
)
def test_invalid_bounded_geometry_refuses(field: str, value: Any) -> None:
    m = module()
    with pytest.raises(m.ScoreError):
        m.assess(model(**{field: value}), (target(),), tail_exponent=5)


@pytest.mark.parametrize(
    "lo,hi,width",
    [
        (True, 1, 1),
        (0.0, 1, 1),
        (0, Decimal(1), 1),
        (2, 1, 1),
        (0, 1, 0),
        (0, 1, F(4, 10**60)),
        (0, 1 << 257, 1),
    ],
)
def test_invalid_support_and_width_refuse(lo: Any, hi: Any, width: Any) -> None:
    m = module()
    with pytest.raises(m.ScoreError):
        m.assess(model(), (target("raw", lo, hi, width),), tail_exponent=5)


@pytest.mark.parametrize("q", [True, 4, 5.0, 6])
def test_unsupported_tail_budget_refuses(q: Any) -> None:
    m = module()
    with pytest.raises(m.ScoreError, match="tail_budget"):
        m.assess(model(), (target(),), tail_exponent=q)


@pytest.mark.parametrize(
    "count,total",
    [(True, 1), (2047, 1), (4097, 1), (2048, -1), (2048, 2049), (2048, F(1, 2)), (2048, 0.5)],
)
def test_invalid_counts_totals_or_strict_win_values_refuse(count: Any, total: Any) -> None:
    m = module()
    with pytest.raises(m.ScoreError):
        m.calculate(model(), (m.Totals(target(), total, count),), tail_exponent=5)


def test_metric_cohort_and_budget_mismatch_refuse() -> None:
    m = module()
    raw = target("raw", -1, 1, 1)
    with pytest.raises(m.ScoreError):
        m.assess(model(), (target(), target()), tail_exponent=5)
    with pytest.raises(m.ScoreError):
        m.assess(model(), (), tail_exponent=5)
    with pytest.raises(m.ScoreError):
        m.assess(model(), (target("win", -1, 1, 1),), tail_exponent=5)
    with pytest.raises(m.ScoreError):
        m.calculate(
            model(), (m.Totals(raw, 0, 2048), m.Totals(target(), 512, 2049)), tail_exponent=5
        )


def test_all_predeclared_long_geometry_targets_are_rounding_safe() -> None:
    m = module()
    geometries = [
        (2048, 2, F(1, 25), F(4, 125)),
        (2048, 2, F(3, 50), F(7, 250)),
        (16384, 9, F(3, 25), F(11, 125)),
        (8192, 5, F(3, 25), F(11, 125)),
        (32768, 2, F(39, 100), F(179, 500)),
        (131072, 40, F(9, 50), F(37, 250)),
    ]
    for n, classes, raw, paired in geometries:
        specs = (
            target("raw", 0, raw, F(1, 50)),
            target(),
            target("synthetic_excess", 0, paired, F(1, 50)),
        )
        assert m.assess(model(n, classes), specs, tail_exponent=5).decision_eligible


def test_exhaustive_small_iid_law_covers_all_three_targets_as_claimed() -> None:
    m = module()
    specs = (target("raw", -1, 1, 100), target(), target("synthetic_excess", -1, 1, 100))
    covered = 0
    for signs in product((-1, 1), repeat=8):
        observations = (
            m.Totals(specs[0], sum(signs), 8),
            m.Totals(specs[1], signs.count(1), 8),
            m.Totals(specs[2], sum(signs), 8),
        )
        intervals = m.calculate(model(8, 1), observations, tail_exponent=5).intervals
        truths = (F(0), F(1, 2), F(0))
        covered += int(
            all(
                F(i.lower) <= truth <= F(i.upper)
                for i, truth in zip(intervals, truths, strict=True)
            )
        )
    assert F(covered, 256) >= F(19, 20)
