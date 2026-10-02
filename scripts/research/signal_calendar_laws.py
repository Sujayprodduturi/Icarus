"""Frozen finite-innovation fixture laws; this module draws nothing and performs no I/O.

All fractions, costs and benchmark coefficients are invented research values.
No market-law, execution-fill or accepted calibration claim follows from a fixture.
"""

from dataclasses import dataclass, replace
from enum import StrEnum
from fractions import Fraction
from functools import cache
from math import comb

from scripts.research import signal_calendar_uncertainty as calendar
from scripts.research.signal_calendar_uncertainty import Metric as Metric


class LawReason(StrEnum):
    UNKNOWN_PROFILE = "unknown_profile"
    INVALID_SPAN = "invalid_span"
    INVALID_PATH = "invalid_path"
    INVALID_ATOM = "invalid_atom"
    RESOURCE_LIMIT = "resource_limit"
    DEGENERATE_TRUTH = "degenerate_truth"


class LawError(ValueError):
    def __init__(self, reason: LawReason) -> None:
        self.reason = reason
        super().__init__(reason.value)


@dataclass(frozen=True, slots=True)
class LawProfile:
    identifier: str
    a: Fraction
    gamma: Fraction
    hold: int
    volatility_memory: int
    volatility_low: Fraction
    volatility_high: Fraction
    p_volatility: Fraction
    jump_atoms: tuple[tuple[Fraction, Fraction], ...]
    p_gate: Fraction
    delta: Fraction = Fraction(0)


_ZERO = ((Fraction(0), Fraction(1)),)
_POSITIVE_JUMP = (
    (Fraction(8, 25), Fraction(1, 512)),
    (Fraction(-1, 100), Fraction(1, 16)),
    (Fraction(0), Fraction(479, 512)),
)
_BASE = LawProfile(
    "P1",
    Fraction(0),
    Fraction(1, 100),
    1,
    1,
    Fraction(1, 100),
    Fraction(1, 100),
    Fraction(1, 8),
    _ZERO,
    Fraction(1),
)
PROFILES: tuple[LawProfile, ...] = (
    _BASE,
    replace(_BASE, identifier="P2", a=Fraction(1, 100)),
    replace(_BASE, identifier="P3", a=Fraction(1, 100), gamma=Fraction(1, 25), hold=8),
    replace(
        _BASE,
        identifier="P4",
        a=Fraction(1, 100),
        volatility_memory=4,
        volatility_low=Fraction(1, 500),
        volatility_high=Fraction(1, 25),
    ),
    replace(_BASE, identifier="P5", a=Fraction(1, 100), jump_atoms=_POSITIVE_JUMP),
    replace(
        _BASE,
        identifier="P6",
        a=Fraction(1, 100),
        jump_atoms=tuple((-value, probability) for value, probability in _POSITIVE_JUMP),
    ),
    replace(
        _BASE,
        identifier="P7",
        a=Fraction(1, 100),
        gamma=Fraction(1, 25),
        hold=32,
        volatility_memory=8,
        volatility_low=Fraction(1, 500),
        volatility_high=Fraction(1, 25),
    ),
    replace(_BASE, identifier="L1", a=Fraction(1, 100), p_gate=Fraction(1, 50)),
    replace(_BASE, identifier="E+", delta=Fraction(1, 25)),
    replace(_BASE, identifier="E-", delta=Fraction(-1, 25)),
)
COST = Fraction(1, 1000)
BENCHMARK_CONSTANT = Fraction(3, 1000)
BENCHMARK_PREVIOUS = Fraction(3, 500)
BENCHMARK_FORWARD = Fraction(1, 100)
GENERATOR_VERSION = "finite-calendar-law/v1"


@dataclass(frozen=True, slots=True)
class PathFamily:
    profile_id: str
    n: int
    metrics: tuple[Metric, ...]
    formal: bool


@dataclass(frozen=True, slots=True)
class InnovationPath:
    first_index: int
    s: tuple[int, ...]
    q: tuple[bool, ...]
    g: tuple[bool, ...]
    j: tuple[Fraction, ...]
    epsilon1: tuple[int, ...]
    epsilon2: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class TargetTruth:
    metric: Metric
    theta: Fraction
    entry_intensity: Fraction
    lrv_lower_W: Fraction
    lrv_lower_ratio: Fraction
    proof: str = "INDEPENDENT_PER_TRADE_SIGN_CONDITIONAL_VARIANCE"


@dataclass(frozen=True, slots=True)
class ResourceBounds:
    rows: int
    total_footprint: int
    expanded_footprint: int
    block_size: int
    slices: int
    first_index: int
    last_index: int
    eligible: bool


@dataclass(frozen=True, slots=True)
class LawFixture:
    source: calendar.CalendarSource
    models: tuple[calendar.CalendarModel, ...]
    requests: tuple[calendar.CalendarRequest, ...]
    truths: tuple[TargetTruth, ...]


def profile(identifier: str) -> LawProfile:
    if type(identifier) is not str:
        raise LawError(LawReason.UNKNOWN_PROFILE)
    for item in PROFILES:
        if item.identifier == identifier:
            return item
    raise LawError(LawReason.UNKNOWN_PROFILE)


def _metrics(item: LawProfile) -> tuple[Metric, ...]:
    if item.identifier in ("E+", "E-"):
        return Metric.RAW, Metric.SYNTHETIC_EXCESS
    return Metric.RAW, Metric.WIN, Metric.SYNTHETIC_EXCESS


def path_families() -> tuple[PathFamily, ...]:
    return tuple(
        PathFamily(item.identifier, n, _metrics(item), item.identifier != "L1")
        for item in PROFILES
        for n in ((128,) if item.identifier in ("E+", "E-") else (64, 128))
    )


def resource_bounds(identifier: str, n: int) -> ResourceBounds:
    item = profile(identifier)
    if type(n) is not int or not 2 <= n <= 4096:
        raise LawError(LawReason.INVALID_SPAN)
    w = max(item.volatility_memory, 1)
    b = calendar._block_size(n)
    q = n - b + 1
    rows = 2 * n
    total = rows * (w + item.hold + 5)
    expanded = 2 * (w + item.hold + 6) * b * q
    eligible = 2 <= b < n and rows <= 4096 and total <= 65536 and expanded <= 262144
    return ResourceBounds(rows, total, expanded, b, q, -w, n - 1 + item.hold, eligible)


def sparse_emission_upper(n: int) -> Fraction:
    bounds = resource_bounds("L1", n)
    return 1 - Fraction(49, 50) ** bounds.block_size


@cache
def _analytical_truths(identifier: str) -> tuple[TargetTruth, ...]:
    """Exact E[A]/E[C], including strict-win atoms and positive LRV proof.

    Condition on all shared S,Q,G,J innovations. Distinct per-trade epsilon
    residuals are conditionally independent. Thus score-sum variance is >=
    n E[C V**2] for raw/excess, or n E[C*straddle]/4 for wins. Finite dependence
    gives the LRV limit; these are positive lower bounds, not fitted variances.
    """
    item = profile(identifier)
    intensity = Fraction(3, 2) * item.p_gate
    high_probability = 1 - (1 - item.p_volatility) ** item.volatility_memory
    # Collapse equal states and omit zero-probability atoms exactly.
    volatility_probabilities: dict[Fraction, Fraction] = {}
    for volatility, probability in (
        (item.volatility_low, 1 - high_probability),
        (item.volatility_high, high_probability),
    ):
        if probability:
            volatility_probabilities[volatility] = (
                volatility_probabilities.get(volatility, Fraction(0)) + probability
            )
    volatility_states = tuple(volatility_probabilities.items())
    variance_v = sum((probability * v**2 for v, probability in volatility_states), Fraction(0))
    win = Fraction(0)
    straddle = Fraction(0)
    for previous, selected_probability in ((-1, Fraction(1, 3)), (1, Fraction(2, 3))):
        for k in range(item.hold + 1):
            probability_f = Fraction(comb(item.hold, k), 2**item.hold)
            factor = Fraction(2 * k - item.hold, item.hold)
            for v, probability_v in volatility_states:
                for jump, probability_j in item.jump_atoms:
                    probability = (
                        selected_probability * probability_f * probability_v * probability_j
                    )
                    base = item.delta - item.a / 3 + item.a * previous + item.gamma * factor + jump
                    straddle += probability * int(-v < base <= v)
                    win += probability * Fraction(int(base - v > 0) + int(base + v > 0), 2)
    raw_lrv = intensity * variance_v
    win_lrv = intensity * straddle / 4
    values = (
        (Metric.RAW, item.delta, raw_lrv),
        (Metric.WIN, win, win_lrv),
        (
            Metric.SYNTHETIC_EXCESS,
            item.delta - BENCHMARK_CONSTANT - BENCHMARK_PREVIOUS / 3,
            raw_lrv,
        ),
    )
    truths = tuple(
        TargetTruth(metric, theta, intensity, lrv, lrv / intensity**2)
        for metric, theta, lrv in values
        if metric in _metrics(item)
    )
    if any(truth.lrv_lower_W <= 0 for truth in truths):
        raise LawError(LawReason.DEGENERATE_TRUTH)
    return truths


def analytical_truths(identifier: str) -> tuple[TargetTruth, ...]:
    """Validate a canonical profile identity before accessing the exact truth cache."""
    return _analytical_truths(profile(identifier).identifier)


def _path(item: LawProfile, n: int, innovations: InnovationPath, bounds: ResourceBounds) -> None:
    if (
        type(innovations) is not InnovationPath
        or type(innovations.first_index) is not int
        or innovations.first_index != bounds.first_index
    ):
        raise LawError(LawReason.INVALID_PATH)
    length = bounds.last_index - bounds.first_index + 1
    fields = (
        innovations.s,
        innovations.q,
        innovations.g,
        innovations.j,
        innovations.epsilon1,
        innovations.epsilon2,
    )
    if any(type(field) is not tuple or len(field) != length for field in fields):
        raise LawError(LawReason.INVALID_PATH)
    for values in (innovations.s, innovations.epsilon1, innovations.epsilon2):
        if any(type(value) is not int or value not in (-1, 1) for value in values):
            raise LawError(LawReason.INVALID_ATOM)
    if any(type(value) is not bool for value in (*innovations.q, *innovations.g)):
        raise LawError(LawReason.INVALID_ATOM)
    if item.p_gate == 1 and not all(innovations.g):
        raise LawError(LawReason.INVALID_ATOM)
    possible = {value for value, probability in item.jump_atoms if probability > 0}
    if any(type(value) is not Fraction or value not in possible for value in innovations.j):
        raise LawError(LawReason.INVALID_ATOM)


def build(identifier: str, n: int, innovations: InnovationPath) -> LawFixture:
    """Map validated atom arrays to completed records without any RNG or replay."""
    item = profile(identifier)
    bounds = resource_bounds(identifier, n)
    if not bounds.eligible:
        raise LawError(LawReason.RESOURCE_LIMIT)
    if n not in ((128,) if identifier in ("E+", "E-") else (64, 128)):
        raise LawError(LawReason.INVALID_SPAN)
    _path(item, n, innovations, bounds)
    w = -bounds.first_index
    declared = calendar.Declaration.FIXTURE_DECLARED
    # Build the entry schedule solely from pre-entry S and contemporaneous G;
    # outcomes, completion events and epsilon never select/drop a trade.
    schedule = tuple(
        (t, symbol)
        for t in range(n)
        for symbol in range(
            1, 1 + int(innovations.g[t + w]) * (1 + int(innovations.s[t + w - 1] == 1))
        )
    )
    expected = tuple(f"{identifier}:t{t}:s{symbol}" for t, symbol in schedule)
    records = []
    for (t, symbol), trade_id in zip(schedule, expected, strict=True):
        previous = innovations.s[t + w - 1]
        factor = Fraction(sum(innovations.s[t + w : t + w + item.hold]), item.hold)
        high = any(innovations.q[t + w - item.volatility_memory : t + w])
        volatility = item.volatility_high if high else item.volatility_low
        epsilon = (innovations.epsilon1 if symbol == 1 else innovations.epsilon2)[t + w]
        gross = (
            COST
            + item.delta
            - item.a / 3
            + item.a * previous
            + item.gamma * factor
            + volatility * epsilon
            + innovations.j[t + w]
        )
        raw = gross - COST
        benchmark = BENCHMARK_CONSTANT + BENCHMARK_PREVIOUS * previous + BENCHMARK_FORWARD * factor
        records.append(
            calendar.TradeRecord(
                trade_id,
                f"s{symbol}",
                t - 1,
                t,
                (t + item.hold,),
                tuple(range(t - w, t + item.hold + 1)),
                t + item.hold,
                raw,
                raw - benchmark,
                declared,
            )
        )
    fixture = f"{GENERATOR_VERSION}:{identifier}:n{n}"
    source = calendar.CalendarSource(
        fixture,
        f"{GENERATOR_VERSION}:{identifier}:whole-law",
        "stationary-completed-outcomes-no-halo-entrants",
        tuple(range(n)),
        bounds.first_index,
        bounds.last_index,
        tuple(records),
        cohort_complete=declared,
        geometry=declared,
        accounting=calendar.Accounting.BEFORE_TAX_MODEL_COST,
        expected_core_ids=expected,
    )
    truths = analytical_truths(identifier)
    models = tuple(
        calendar.CalendarModel(
            fixture,
            f"{GENERATOR_VERSION}:{identifier}:{truth.metric}:analytic-proof",
            truth.metric,
            w,
            item.hold,
            declared,
            declared,
            declared,
            declared,
            declared,
            declared,
            declared,
            declared,
        )
        for truth in truths
    )
    requests = tuple(
        calendar.CalendarRequest(
            truth.metric,
            Fraction(1, 20),
            Fraction(1, 5) if truth.metric is Metric.WIN else Fraction(1, 50),
            declared,
        )
        for truth in truths
    )
    return LawFixture(source, models, requests, truths)
