"""Pure, development-only Bartlett fixed-b uncertainty; no product authority."""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from math import fsum, isfinite, sqrt


class RefusalReason(StrEnum):
    EMPTY = "empty"
    INVALID_INPUT = "invalid_input"
    INVALID_GEOMETRY = "invalid_geometry"
    INVALID_BLOCK_ID = "invalid_block_id"
    TOO_FEW_OBSERVATIONS = "too_few_observations"
    TOO_FEW_OCCUPIED_BLOCKS = "too_few_occupied_blocks"
    TOO_FEW_GRID_BLOCKS = "too_few_grid_blocks"
    TOO_LARGE_GRID = "too_large_grid"
    NONFINITE = "nonfinite"
    ZERO_VARIANCE = "zero_variance"
    NEGATIVE_VARIANCE = "negative_variance"


@dataclass(frozen=True, slots=True)
class Refusal:
    reason: RefusalReason


@dataclass(frozen=True, slots=True)
class Estimate:
    mean: float
    variance: float
    critical: float
    lower: float
    upper: float
    grid_blocks: int
    occupied_blocks: int
    bandwidth: int


def estimate(
    values: Sequence[float],
    block_ids: Sequence[int],
    *,
    first_block: int,
    last_block: int,
) -> Estimate | Refusal:
    """Estimate a trade-weighted mean on a caller-certified complete block grid."""
    if type(first_block) is not int or type(last_block) is not int:
        return Refusal(RefusalReason.INVALID_GEOMETRY)
    if last_block < first_block:
        return Refusal(RefusalReason.INVALID_GEOMETRY)
    grid_blocks = last_block - first_block + 1
    if grid_blocks < 8:
        return Refusal(RefusalReason.TOO_FEW_GRID_BLOCKS)
    if grid_blocks > 4096:
        return Refusal(RefusalReason.TOO_LARGE_GRID)
    n = len(values)
    if n != len(block_ids):
        return Refusal(RefusalReason.INVALID_INPUT)
    if n == 0:
        return Refusal(RefusalReason.EMPTY)
    if n < 2:
        return Refusal(RefusalReason.TOO_FEW_OBSERVATIONS)
    if any(type(g) is not int or not first_block <= g <= last_block for g in block_ids):
        return Refusal(RefusalReason.INVALID_BLOCK_ID)
    if any(isinstance(v, bool) or not isinstance(v, (float, int)) for v in values):
        return Refusal(RefusalReason.INVALID_INPUT)
    try:
        if not all(isfinite(v) for v in values):
            return Refusal(RefusalReason.NONFINITE)
        groups: list[list[float]] = [[] for _ in range(grid_blocks)]
        for value, block in zip(values, block_ids, strict=True):
            groups[block - first_block].append(value)
        occupied_blocks = sum(bool(group) for group in groups)
        if occupied_blocks < 2:
            return Refusal(RefusalReason.TOO_FEW_OCCUPIED_BLOCKS)
        mean = fsum(values) / n
        # Exact constant observations have zero variance even if fsum/n rounds.
        if all(value == values[0] for value in values):
            return Refusal(RefusalReason.ZERO_VARIANCE)
        scores = [fsum(group) - len(group) * mean for group in groups]
        if not isfinite(mean) or not all(isfinite(s) for s in scores):
            return Refusal(RefusalReason.NONFINITE)
        bandwidth = grid_blocks // 4
        b = bandwidth / grid_blocks
        if not 0.02 <= b <= 1.0:
            return Refusal(RefusalReason.INVALID_GEOMETRY)
        terms = [fsum(s * s for s in scores)]
        for lag in range(1, bandwidth):
            covariance = fsum(scores[g] * scores[g - lag] for g in range(lag, grid_blocks))
            terms.append(2.0 * (1.0 - lag / bandwidth) * covariance)
        variance = fsum(terms) / n**2
        if not isfinite(variance):
            return Refusal(RefusalReason.NONFINITE)
        if variance == 0:
            return Refusal(RefusalReason.ZERO_VARIANCE)
        if variance < 0:
            return Refusal(RefusalReason.NEGATIVE_VARIANCE)
        # Kiefer/Vogelsang Table I, 97.5% cubic; checked 2026-09-30.
        # https://kiefer.economics.cornell.edu/newasym2.pdf
        critical = 1.96 + 2.9694 * b + 0.4160 * b**2 - 0.5324 * b**3
        half_width = critical * sqrt(variance)
        lower, upper = mean - half_width, mean + half_width
        if not all(isfinite(v) for v in (critical, half_width, lower, upper)):
            return Refusal(RefusalReason.NONFINITE)
    except (OverflowError, ValueError):
        return Refusal(RefusalReason.NONFINITE)
    return Estimate(
        mean,
        variance,
        critical,
        lower,
        upper,
        grid_blocks,
        occupied_blocks,
        bandwidth,
    )
