"""Independent formula and fail-closed tests for isolated research inference."""

import math

import pytest
from scripts.research import signal_uncertainty as module


def _dense(values: list[float], ids: list[int], first: int, last: int) -> float:
    # Independent dense matrix multiplication, deliberately no lag summation.
    mean = math.fsum(values) / len(values)
    scores = [
        math.fsum(v - mean for v, block in zip(values, ids, strict=True) if block == g)
        for g in range(first, last + 1)
    ]
    bandwidth = len(scores) // 4
    kernel = [
        [max(0.0, 1.0 - abs(i - j) / bandwidth) for j in range(len(scores))]
        for i in range(len(scores))
    ]
    return (
        math.fsum(
            scores[i] * kernel[i][j] * scores[j]
            for i in range(len(scores))
            for j in range(len(scores))
        )
        / len(values) ** 2
    )


def test_dense_oracle_unequal_counts_and_known_critical() -> None:

    values = [-3.0, 1.0, 2.0, 8.0, -2.0, 4.0, 7.0]
    ids = [0, 0, 1, 10, 10, 10, 23]
    result = module.estimate(values, ids, first_block=0, last_block=23)
    assert isinstance(result, module.Estimate)
    assert result.mean == pytest.approx(17 / 7)
    assert result.variance == pytest.approx(_dense(values, ids, 0, 23), rel=1e-13)
    assert result.critical == pytest.approx(2.72003125, abs=1e-14)
    assert (result.grid_blocks, result.occupied_blocks, result.bandwidth) == (24, 4, 6)
    assert result.lower == pytest.approx(result.mean - 2.72003125 * math.sqrt(result.variance))
    assert result.upper == pytest.approx(result.mean + 2.72003125 * math.sqrt(result.variance))


@pytest.mark.parametrize("last", [7, 8, 23, 24, 4095])
def test_grid_boundaries_match_dense_or_hand_oracle(last: int) -> None:

    result = module.estimate([-1.0, 1.0], [0, last], first_block=0, last_block=last)
    assert isinstance(result, module.Estimate)
    assert result.variance == pytest.approx(0.5)
    b = ((last + 1) // 4) / (last + 1)
    assert result.critical == pytest.approx(1.96 + 2.9694 * b + 0.416 * b * b - 0.5324 * b * b * b)


def test_gaps_and_empty_edges_do_not_compress() -> None:

    far = module.estimate([-1.0, 1.0], [0, 10], first_block=0, last_block=15)
    near = module.estimate([-1.0, 1.0], [0, 1], first_block=0, last_block=15)
    assert isinstance(far, module.Estimate) and isinstance(near, module.Estimate)
    assert far.variance == pytest.approx(0.5)
    assert near.variance == pytest.approx(0.125)
    shifted = module.estimate([-1.0, 1.0], [100, 110], first_block=100, last_block=115)
    assert shifted == far
    edge = module.estimate([-1.0, 1.0], [0, 2], first_block=0, last_block=7)
    assert isinstance(edge, module.Estimate)
    assert edge.variance == pytest.approx(0.5)


def test_permutation_and_signed_scale() -> None:

    values, ids = [-3.0, 1.0, 2.0, 8.0, -2.0, 4.0, 7.0], [0, 0, 1, 10, 10, 10, 23]
    result = module.estimate(values, ids, first_block=0, last_block=23)
    assert isinstance(result, module.Estimate)
    assert module.estimate(values[::-1], ids[::-1], first_block=0, last_block=23) == result
    scaled = module.estimate([-2 * v for v in values], ids, first_block=0, last_block=23)
    assert isinstance(scaled, module.Estimate)
    assert scaled.mean == pytest.approx(-2 * result.mean)
    assert scaled.variance == pytest.approx(4 * result.variance)
    assert scaled.lower == pytest.approx(-2 * result.upper)
    assert scaled.upper == pytest.approx(-2 * result.lower)


@pytest.mark.parametrize(
    ("values", "ids", "first", "last", "reason"),
    [
        ([], [], 0, 7, "EMPTY"),
        ([1.0], [0], 0, 7, "TOO_FEW_OBSERVATIONS"),
        ([1.0, 2.0], [0, 0], 0, 7, "TOO_FEW_OCCUPIED_BLOCKS"),
        ([1.0, 2.0], [0, 1], 0, 6, "TOO_FEW_GRID_BLOCKS"),
        ([1.0, 2.0], [0, 1], 0, 4096, "TOO_LARGE_GRID"),
        ([1.0, 2.0], [0], 0, 7, "INVALID_INPUT"),
        ([1.0, 2.0], [0, 8], 0, 7, "INVALID_BLOCK_ID"),
        ([1.0, 2.0], [False, 1], 0, 7, "INVALID_BLOCK_ID"),
        ([1.0, 2.0], [0.0, 1], 0, 7, "INVALID_BLOCK_ID"),
        ([1.0, 2.0], [0, 1], True, 7, "INVALID_GEOMETRY"),
        ([1.0, 2.0], [0, 1], 0, 7.0, "INVALID_GEOMETRY"),
        ([1.0, 2.0], [0, 1], 7, 0, "INVALID_GEOMETRY"),
        ([math.nan, 2.0], [0, 1], 0, 7, "NONFINITE"),
        ([math.inf, 2.0], [0, 1], 0, 7, "NONFINITE"),
        ([1e308, 1e308], [0, 1], 0, 7, "NONFINITE"),
        ([-1e308, 1e308], [0, 1], 0, 7, "NONFINITE"),
        ([1.0, 1.0], [0, 1], 0, 7, "ZERO_VARIANCE"),
        ([0.0, 0.0], [0, 1], 0, 7, "ZERO_VARIANCE"),
        ([-1e-200, 1e-200], [0, 1], 0, 7, "ZERO_VARIANCE"),
    ],
)
def test_refusal_reasons(
    values: list[float], ids: list[int], first: int, last: int, reason: str
) -> None:

    result = module.estimate(values, ids, first_block=first, last_block=last)
    assert isinstance(result, module.Refusal)
    assert result.reason == module.RefusalReason[reason]


@pytest.mark.parametrize(("value", "count"), [(0.1, 3), (0.1234, 9)])
def test_constant_decimals_refuse_despite_mean_roundoff(value: float, count: int) -> None:
    result = module.estimate([value] * count, [0] + [1] * (count - 1), first_block=0, last_block=23)
    assert isinstance(result, module.Refusal)
    assert result.reason == module.RefusalReason.ZERO_VARIANCE
