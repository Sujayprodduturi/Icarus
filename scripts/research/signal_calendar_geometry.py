"""Exact finite-window diagnosis for a constructed independent-innovation score.

This toy covariance oracle provides no confidence interval or market eligibility.
Innovations are centered, independent, and have a common declared variance.
"""

from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise

Rational = int | Fraction
_MAX_BITS = 256
_MAX_FILTER = 64
_MAX_N = 256


class GeometryError(ValueError):
    """The declared toy model, finite geometry or rational input is invalid."""


@dataclass(frozen=True, slots=True)
class LinearScore:
    """Z_t = sum_j coefficients[j] * epsilon_(t-j)."""

    coefficients: tuple[Rational, ...]
    innovation_variance: Rational


@dataclass(frozen=True, slots=True)
class GeometryResult:
    autocovariances: tuple[Fraction, ...]
    full_root_variance: Fraction
    centered_block_variances: tuple[Fraction, ...]
    adjacent_centered_block_covariances: tuple[Fraction, ...]


@dataclass(frozen=True, slots=True)
class RatioIdentity:
    observed_difference: Fraction
    centered_score_difference: Fraction
    count_weight: Fraction


def _rational(value: Rational) -> Fraction:
    if type(value) is int:
        if value.bit_length() > _MAX_BITS:
            raise GeometryError("rational input exceeds the 256-bit bound")
        return Fraction(value)
    if type(value) is Fraction:
        if max(value.numerator.bit_length(), value.denominator.bit_length()) > _MAX_BITS:
            raise GeometryError("rational input exceeds the 256-bit bound")
        return value
    raise GeometryError("inputs must be exact integers or Fractions")


def diagnose(score: LinearScore, *, n: int, b: int) -> GeometryResult:
    """Return exact root variances and adjacent centered-block covariances.

    Blocks start at every integer from zero through n-b. Centering uses the
    full calendar sum: (sum_block Z - (b/n)*sum_full Z)/sqrt(b).
    Input scalars have at most 256 numerator/denominator bits; the bounded
    filter and geometry also bound exact intermediate arithmetic growth.
    """
    if type(n) is not int or type(b) is not int or not 1 <= b <= n <= _MAX_N:
        raise GeometryError("require exact integers 1 <= b <= n <= 256")
    if type(score) is not LinearScore:
        raise GeometryError("a LinearScore declaration is required")
    if type(score.coefficients) is not tuple or not 1 <= len(score.coefficients) <= _MAX_FILTER:
        raise GeometryError("require a nonempty coefficient tuple of length at most 64")
    coefficients = tuple(_rational(value) for value in score.coefficients)
    variance = _rational(score.innovation_variance)
    if variance < 0:
        raise GeometryError("innovation variance must be nonnegative")
    length = len(coefficients)
    gamma = tuple(
        variance
        * sum(
            (coefficients[j] * coefficients[j + lag] for j in range(length - lag)),
            Fraction(0),
        )
        for lag in range(length)
    )

    def covariance(lag: int) -> Fraction:
        return gamma[lag] if lag < length else Fraction(0)

    def sum_variance(size: int) -> Fraction:
        return size * gamma[0] + 2 * sum(
            ((size - lag) * gamma[lag] for lag in range(1, min(size, length))),
            Fraction(0),
        )

    full_variance = sum_variance(n)
    block_variance = sum_variance(b)
    # The full-sum covariance of date t is gamma0 plus its left and right lags.
    lag_prefix = [Fraction(0)]
    for lag in range(1, n):
        lag_prefix.append(lag_prefix[-1] + covariance(lag))
    row_prefix = [Fraction(0)]
    for t in range(n):
        row_prefix.append(row_prefix[-1] + gamma[0] + lag_prefix[t] + lag_prefix[n - 1 - t])
    block_full = tuple(row_prefix[start + b] - row_prefix[start] for start in range(n - b + 1))
    weight = Fraction(b, n)
    centering_variance = weight * weight * full_variance
    centered = tuple(
        (block_variance - 2 * weight * cross + centering_variance) / b for cross in block_full
    )
    # Two adjacent block sums differ only at their first/last dates.
    adjacent_block = block_variance - gamma[0] + covariance(b)
    adjacent = tuple(
        (adjacent_block - weight * (left + right) + centering_variance) / b
        for left, right in pairwise(block_full)
    )
    return GeometryResult(gamma, full_variance / n, centered, adjacent)


def ratio_centering(
    *,
    block_total: Rational,
    full_total: Rational,
    block_count: int,
    full_count: int,
    theta: Rational,
) -> RatioIdentity:
    """Expose exact ratio centering with observed count weights, for any theta.

    Totals can be signed; counts require 0 < block_count <= full_count. This
    algebraic identity has no distributional or target-authentication premise.
    """
    if type(block_count) is not int or type(full_count) is not int:
        raise GeometryError("counts must be exact integers")
    _rational(block_count)
    _rational(full_count)
    if not 0 < block_count <= full_count:
        raise GeometryError("require 0 < block_count <= full_count")
    block_value = _rational(block_total)
    full_value = _rational(full_total)
    target = _rational(theta)
    weight = Fraction(block_count, full_count)
    score_block = block_value - target * block_count
    score_full = full_value - target * full_count
    return RatioIdentity(
        block_value / block_count - full_value / full_count,
        (score_block - weight * score_full) / block_count,
        weight,
    )
