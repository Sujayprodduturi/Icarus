"""Independent dense-matrix oracle for the compact signal CR2 estimator."""

from __future__ import annotations

import math

import numpy as np
import pytest

from icarus.engine.signalmetrics import CandidateMoments, _cr2_moments


def _dense_oracle(values: tuple[float, ...], block_ids: tuple[int, ...]) -> tuple[float, float]:
    """Evaluate the design formula directly, independently of the scalar implementation."""
    y = np.asarray(values, dtype=np.float64)
    count = len(values)
    identity = np.eye(count)
    residual_maker = identity - np.ones((count, count)) / count
    q = np.zeros((count, count), dtype=np.float64)
    for block_id in sorted(set(block_ids)):
        membership = np.asarray([item == block_id for item in block_ids], dtype=np.float64)
        block_count = float(membership.sum())
        p_g = residual_maker @ membership / (count * math.sqrt(1.0 - block_count / count))
        q += np.outer(p_g, p_g)
    variance = float(y @ q @ y)
    degrees_of_freedom = float(np.trace(q) ** 2 / np.trace(q @ q))
    return variance, degrees_of_freedom


@pytest.mark.parametrize(
    ("values", "block_ids", "expected_variance", "expected_df"),
    [
        ((0.0, 2.0, 4.0, 6.0), (0, 0, 1, 1), 4.0, 1.0),
        ((0.0, 1.0, 2.0, 3.0, 4.0, 5.0), (0, 1, 1, 2, 2, 2), 1.5, 5.0 / 3.0),
    ],
)
def test_compact_estimator_matches_hand_checked_dense_cases(
    values: tuple[float, ...],
    block_ids: tuple[int, ...],
    expected_variance: float,
    expected_df: float,
) -> None:
    """A wrong leverage correction or matrix trace must fail literal hand calculations."""
    oracle_variance, oracle_df = _dense_oracle(values, block_ids)
    result = _cr2_moments(values, block_ids)

    assert isinstance(result, CandidateMoments)
    assert oracle_variance == pytest.approx(expected_variance)
    assert oracle_df == pytest.approx(expected_df)
    assert result.cr2_variance == pytest.approx(expected_variance)
    assert result.degrees_of_freedom == pytest.approx(expected_df)


@pytest.mark.parametrize("occupancy", [(1, 2, 3), (2, 2, 2, 5)])
def test_compact_estimator_matches_seeded_dense_formula(
    occupancy: tuple[int, ...],
) -> None:
    """A scalar shortcut that diverges from the design matrix must fail on synthetic vectors."""
    rng = np.random.default_rng(20260926)
    values_array = rng.normal(size=sum(occupancy))
    values = tuple(float(item) for item in values_array)
    block_ids = tuple(
        block_id for block_id, block_count in enumerate(occupancy) for _ in range(block_count)
    )

    oracle_variance, oracle_df = _dense_oracle(values, block_ids)
    result = _cr2_moments(values, block_ids)

    assert values_array.shape == (sum(occupancy),)  # generated here; no repository data is loaded
    assert isinstance(result, CandidateMoments)
    assert math.isclose(result.cr2_variance, oracle_variance, rel_tol=1e-12, abs_tol=1e-14)
    assert math.isclose(result.degrees_of_freedom, oracle_df, rel_tol=1e-12, abs_tol=1e-14)
