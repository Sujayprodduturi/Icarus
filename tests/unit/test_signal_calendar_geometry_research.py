"""Independent innovation-vector oracles for exact toy calendar geometry."""

from fractions import Fraction
from itertools import pairwise
from typing import Any, cast

import pytest
from scripts.research import signal_calendar_geometry as module


def _vector(
    coefficients: tuple[Fraction, ...], weights: tuple[Fraction, ...]
) -> dict[int, Fraction]:
    result: dict[int, Fraction] = {}
    for t, weight in enumerate(weights):
        for lag, coefficient in enumerate(coefficients):
            innovation = t - lag
            result[innovation] = result.get(innovation, Fraction(0)) + weight * coefficient
    return result


def _dot(left: dict[int, Fraction], right: dict[int, Fraction]) -> Fraction:
    return sum(
        (value * right.get(index, Fraction(0)) for index, value in left.items()), Fraction(0)
    )


@pytest.mark.parametrize(
    ("coefficients", "variance", "n", "b"),
    [
        ((Fraction(1),), Fraction(1), 8, 3),
        ((Fraction(2),), Fraction(3, 5), 11, 4),
        ((Fraction(1), Fraction(-1)), Fraction(2), 7, 2),
        ((Fraction(1, 3), Fraction(-2, 5), Fraction(7, 4)), Fraction(5, 7), 9, 5),
        ((Fraction(0), Fraction(0)), Fraction(4), 6, 2),
        ((Fraction(1), Fraction(2)), Fraction(0), 5, 1),
        ((Fraction(1), Fraction(-3), Fraction(2)), Fraction(1), 3, 3),
        ((Fraction(2),), Fraction(3), 1, 1),
        (tuple(Fraction((-1) ** j, j + 1) for j in range(64)), Fraction(2, 3), 256, 163),
    ],
)
def test_geometry_matches_independent_innovation_vectors(
    coefficients: tuple[Fraction, ...], variance: Fraction, n: int, b: int
) -> None:
    result = module.diagnose(module.LinearScore(coefficients, variance), n=n, b=b)
    full = _vector(coefficients, (Fraction(1),) * n)
    assert result.full_root_variance == variance * _dot(full, full) / n
    block_vectors = []
    for start in range(n - b + 1):
        weights = tuple(Fraction(int(start <= t < start + b)) - Fraction(b, n) for t in range(n))
        block_vectors.append(_vector(coefficients, weights))
    assert result.centered_block_variances == tuple(
        variance * _dot(vector, vector) / b for vector in block_vectors
    )
    assert result.adjacent_centered_block_covariances == tuple(
        variance * _dot(left, right) / b for left, right in pairwise(block_vectors)
    )
    origin = _vector(coefficients, (Fraction(1),))
    assert result.autocovariances == tuple(
        variance * _dot(origin, _vector(coefficients, (Fraction(0),) * lag + (Fraction(1),)))
        for lag in range(len(coefficients))
    )


def test_iid_centering_reduces_root_variance_by_one_minus_block_fraction() -> None:
    result = module.diagnose(module.LinearScore((3,), Fraction(2, 9)), n=13, b=5)
    assert result.full_root_variance == 2
    assert result.centered_block_variances == (Fraction(16, 13),) * 9
    assert result.adjacent_centered_block_covariances == (Fraction(54, 65),) * 8


def test_full_length_block_is_zero_with_no_adjacent_pair() -> None:
    result = module.diagnose(module.LinearScore((1, -2, 4), 3), n=8, b=8)
    assert result.centered_block_variances == (Fraction(0),)
    assert result.adjacent_centered_block_covariances == ()


@pytest.mark.parametrize(
    "n,b", [(True, 1), (4, False), (4.0, 2), (4, 2.0), (0, 1), (4, 0), (4, 5), (257, 1)]
)
def test_invalid_geometry_refuses(n: object, b: object) -> None:
    with pytest.raises(module.GeometryError):
        module.diagnose(module.LinearScore((1,), 1), n=cast(Any, n), b=cast(Any, b))


@pytest.mark.parametrize(
    "coefficients,variance",
    [
        ((), 1),
        ((1,) * 65, 1),
        ([1], 1),
        ((True,), 1),
        ((0.5,), 1),
        ((Fraction(1),), False),
        ((1,), 0.5),
        ((1,), -1),
        ((1 << 256,), 1),
        ((Fraction(1, 1 << 256),), 1),
        ((1,), Fraction(1, 1 << 256)),
    ],
)
def test_invalid_filter_and_scalar_resources_refuse(coefficients: object, variance: object) -> None:
    with pytest.raises(module.GeometryError):
        module.diagnose(module.LinearScore(cast(Any, coefficients), cast(Any, variance)), n=8, b=3)


def test_unknown_score_contract_refuses() -> None:
    with pytest.raises(module.GeometryError):
        module.diagnose(cast(Any, object()), n=8, b=3)


@pytest.mark.parametrize(
    "block_total,full_total,block_count,full_count,theta",
    [
        (Fraction(9, 7), Fraction(-2, 3), 1, 100, Fraction(11, 13)),
        (Fraction(-8), Fraction(19), 99, 100, Fraction(-7, 9)),
        (Fraction(3, 2), Fraction(3, 2), 7, 7, Fraction(100)),
        (Fraction(0), Fraction(-1, 2), 3, 11, Fraction(0)),
    ],
)
def test_ratio_identity_uses_observed_counts_and_arbitrary_theta(
    block_total: Fraction, full_total: Fraction, block_count: int, full_count: int, theta: Fraction
) -> None:
    result = module.ratio_centering(
        block_total=block_total,
        full_total=full_total,
        block_count=block_count,
        full_count=full_count,
        theta=theta,
    )
    difference = block_total / block_count - full_total / full_count
    score_block = block_total - theta * block_count
    score_full = full_total - theta * full_count
    exact_weight = Fraction(block_count, full_count)
    assert result.observed_difference == difference
    assert (
        result.centered_score_difference == (score_block - exact_weight * score_full) / block_count
    )
    assert result.centered_score_difference == difference
    assert result.count_weight == exact_weight


def test_calendar_fraction_is_not_a_substitute_for_unequal_count_weight() -> None:
    result = module.ratio_centering(
        block_total=3,
        full_total=20,
        block_count=1,
        full_count=100,
        theta=2,
    )
    assert result.centered_score_difference == Fraction(14, 5)
    wrong_calendar_weight = Fraction(1, 2)
    wrong_difference = (1 - wrong_calendar_weight * (-180)) / 1
    assert wrong_difference != result.centered_score_difference


@pytest.mark.parametrize(
    "changes",
    [
        {"block_count": 0},
        {"full_count": 0},
        {"block_count": -1},
        {"block_count": 4},
        {"block_count": True},
        {"full_count": 3.0},
        {"block_total": float("inf")},
        {"full_total": float("nan")},
        {"theta": False},
        {"theta": 0.25},
        {"theta": 1 << 256},
        {"block_total": Fraction(1, 1 << 256)},
        {"full_count": 1 << 256},
    ],
)
def test_ratio_invalid_counts_numerics_and_resources_refuse(changes: dict[str, object]) -> None:
    arguments: dict[str, Any] = {
        "block_total": 1,
        "full_total": 2,
        "block_count": 1,
        "full_count": 3,
        "theta": 0,
    }
    arguments.update(changes)
    with pytest.raises(module.GeometryError):
        module.ratio_centering(**arguments)


def test_large_bounded_rationals_remain_exact() -> None:
    tiny = Fraction(1, 1 << 255)
    result = module.diagnose(module.LinearScore((tiny,), tiny), n=1, b=1)
    assert result.full_root_variance == tiny**3
    assert result.centered_block_variances == (Fraction(0),)
