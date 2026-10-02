"""Exact summary evaluator for the frozen synthetic finite-law manifest only.

The reference calculator and full-record builder stay unchanged. Validated atom
arrays imply their complete next-session identities and footprints; compaction
never changes the full-support resource gate or makes a market eligibility claim.
No RNG, I/O, fitted parameters or general real-data adapter is present.
"""

from dataclasses import dataclass
from decimal import DecimalException
from fractions import Fraction
from functools import cache
from itertools import accumulate
from math import lcm
from typing import Any

from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_uncertainty as calendar
from scripts.research import signal_moment_uncertainty as numeric


@dataclass(frozen=True, slots=True)
class _Coefficients:
    scale: int
    base: int
    previous: int
    forward: int
    low: int
    high: int
    jumps: tuple[tuple[Fraction, int], ...]
    benchmark_constant: int
    benchmark_previous: int
    benchmark_forward: int


@cache
def _coefficients(identifier: str) -> _Coefficients:
    item = laws.profile(identifier)
    values = (
        item.delta - item.a / 3,
        item.a,
        item.gamma / item.hold,
        item.volatility_low,
        item.volatility_high,
        laws.BENCHMARK_CONSTANT,
        laws.BENCHMARK_PREVIOUS,
        laws.BENCHMARK_FORWARD / item.hold,
        *(jump for jump, _ in item.jump_atoms),
    )
    scale = lcm(*(value.denominator for value in values))
    units = tuple(value.numerator * (scale // value.denominator) for value in values)
    return _Coefficients(
        scale,
        units[0],
        units[1],
        units[2],
        units[3],
        units[4],
        tuple((jump, unit) for (jump, _), unit in zip(item.jump_atoms, units[8:], strict=True)),
        units[5],
        units[6],
        units[7],
    )


def _refusal(
    truth: laws.TargetTruth, reason: calendar.Reason, raw_mean: Fraction | None, count: int
) -> dict[str, Any]:
    return {
        "metric": truth.metric.value,
        "truth": str(truth.theta),
        "reason": reason.value,
        "precision": False,
        "lower": None,
        "upper": None,
        "raw_mean": str(raw_mean),
        "count": count,
    }


def _summary(
    truth: laws.TargetTruth,
    prefix: tuple[int, ...],
    count_prefix: tuple[int, ...],
    scale: int,
    raw_mean: Fraction,
    n: int,
    b: int,
) -> dict[str, Any]:
    count = count_prefix[-1]
    total = Fraction(prefix[-1], scale)
    mean = Fraction(prefix[-1], scale * count)
    try:
        block_counts = tuple(count_prefix[j + b] - count_prefix[j] for j in range(n - b + 1))
        if any(c == 0 for c in block_counts):
            return _refusal(truth, calendar.Reason.ZERO_COUNT_SLICE, raw_mean, count)
        # Subtract the full mean before ranking; sqrt(b) is a shared positive factor.
        deviations = sorted(
            Fraction(prefix[j + b] - prefix[j], scale * c) - mean
            for j, c in enumerate(block_counts)
        )
        if deviations[0] == deviations[-1]:
            return _refusal(truth, calendar.Reason.DEGENERATE_ROOTS, raw_mean, count)
        q = len(deviations)
        lo_dev = deviations[(q + 39) // 40 - 1]
        hi_dev = deviations[(39 * q + 39) // 40 - 1]
        if lo_dev == hi_dev:
            return _refusal(truth, calendar.Reason.DEGENERATE_QUANTILES, raw_mean, count)
        lower, upper, _, _, math_width, display_width = calendar._endpoints(
            mean, (lo_dev, hi_dev), b, n
        )
        width = Fraction(1, 5) if truth.metric is calendar.Metric.WIN else Fraction(1, 50)
        precision = max(Fraction(math_width), Fraction(display_width)) <= width
        return {
            "metric": truth.metric.value,
            "truth": str(truth.theta),
            "reason": "" if precision else calendar.Reason.INSUFFICIENT_PRECISION.value,
            "precision": precision,
            "lower": str(lower),
            "upper": str(upper),
            "mean": str(mean),
            "sum": str(total),
            "count": count,
            "width_math": str(math_width),
            "width_display": str(display_width),
        }
    except calendar._Invalid as error:
        return _refusal(truth, error.reason, raw_mean, count)
    except numeric._Invalid as error:
        return _refusal(truth, calendar.Reason(error.reason.value), raw_mean, count)
    except (DecimalException, OverflowError):
        return _refusal(truth, calendar.Reason.NUMERICAL_RESOLUTION, raw_mean, count)


def evaluate(family: laws.PathFamily, path: laws.InnovationPath) -> list[dict[str, Any]]:
    """Produce the same semantic evidence rows as full-record reference evaluation.

    Fixed rational coefficients share one exact LCM denominator. Integer session
    sums and counts preserve every filled trade, including strict raw-win ties.
    Complete footprint admissibility follows the fixed law/resource preflight,
    not an observed maximum or omitted source event.
    """
    item = laws.profile(family.profile_id)
    bounds = laws.resource_bounds(family.profile_id, family.n)
    if not bounds.eligible:
        raise laws.LawError(laws.LawReason.RESOURCE_LIMIT)
    if family.n not in ((128,) if item.identifier in ("E+", "E-") else (64, 128)):
        raise laws.LawError(laws.LawReason.INVALID_SPAN)
    laws._path(item, family.n, path, bounds)
    coefficients = _coefficients(item.identifier)
    jumps = dict(coefficients.jumps)
    n = family.n
    w = -bounds.first_index
    s_prefix = (0, *accumulate(path.s))
    q_prefix = (0, *accumulate(path.q))
    counts = [0] * n
    raw = [0] * n
    wins = [0] * n
    paired = [0] * n
    for t in range(n):
        index = t + w
        previous = path.s[index - 1]
        count = int(path.g[index]) * (1 + int(previous == 1))
        counts[t] = count
        if not count:
            continue
        forward = s_prefix[index + item.hold] - s_prefix[index]
        high = q_prefix[index] - q_prefix[index - item.volatility_memory] > 0
        volatility = coefficients.high if high else coefficients.low
        common = (
            coefficients.base
            + coefficients.previous * previous
            + coefficients.forward * forward
            + jumps[path.j[index]]
        )
        benchmark = (
            coefficients.benchmark_constant
            + coefficients.benchmark_previous * previous
            + coefficients.benchmark_forward * forward
        )
        for epsilon in (
            (path.epsilon1[index], path.epsilon2[index]) if count == 2 else (path.epsilon1[index],)
        ):
            value = common + volatility * epsilon
            raw[t] += value
            wins[t] += int(value > 0)
            paired[t] += value - benchmark
    count_prefix = (0, *accumulate(counts))
    truths = laws.analytical_truths(item.identifier)
    if count_prefix[-1] == 0:
        return [_refusal(truth, calendar.Reason.ZERO_FULL_COUNT, None, 0) for truth in truths]
    raw_mean = Fraction(sum(raw), coefficients.scale * count_prefix[-1])
    prefixes = {
        calendar.Metric.RAW: ((0, *accumulate(raw)), coefficients.scale),
        calendar.Metric.WIN: ((0, *accumulate(wins)), 1),
        calendar.Metric.SYNTHETIC_EXCESS: ((0, *accumulate(paired)), coefficients.scale),
    }
    return [
        _summary(
            truth,
            prefixes[truth.metric][0],
            count_prefix,
            prefixes[truth.metric][1],
            raw_mean,
            n,
            bounds.block_size,
        )
        for truth in truths
    ]
