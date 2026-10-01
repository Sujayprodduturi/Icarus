"""Deterministic calendar ratio subsampling of invented whole-trade records.

Trusted model declarations are premises, not authenticated market certificates.
This uncalibrated asymptotic candidate never supplies eligible market confidence.
"""

from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Context, Decimal, DecimalException, localcontext
from enum import StrEnum
from fractions import Fraction
from typing import ClassVar

from scripts.research import signal_moment_uncertainty as numeric
from scripts.research.signal_bounded_uncertainty import Declaration as Declaration
from scripts.research.signal_bounded_uncertainty import Metric as Metric
from scripts.research.signal_bounded_uncertainty import Numeric as Numeric
from scripts.research.signal_bounded_uncertainty import Scope as Scope


class Accounting(StrEnum):
    UNKNOWN = "unknown"
    BEFORE_TAX_MODEL_COST = "before_tax_model_cost"


class Reason(StrEnum):
    INVALID_INPUT = "invalid_input"
    INVALID_AXIS = "invalid_axis"
    INVALID_RECORD = "invalid_record"
    INCOMPLETE_COHORT = "incomplete_cohort"
    REAL_DATA_FORBIDDEN = "real_data_forbidden"
    UNKNOWN_MODEL = "unknown_model"
    UNKNOWN_ACCOUNTING = "unknown_accounting"
    UNKNOWN_PRECISION = "unknown_precision"
    OUTCOME_DEPENDENT_SELECTION = "outcome_dependent_selection"
    UNAUTHORIZED_FOOTPRINT = "unauthorized_footprint"
    OUTSIDE_MODEL_FOOTPRINT = "outside_model_footprint"
    STALE_OUTCOME = "stale_outcome"
    TERMINAL_OUTCOME = "terminal_outcome"
    MISSING_BENCHMARK = "missing_benchmark"
    ZERO_FULL_COUNT = "zero_full_count"
    ZERO_COUNT_SLICE = "zero_count_slice"
    INVALID_BLOCK_SIZE = "invalid_block_size"
    DEGENERATE_ROOTS = "degenerate_roots"
    DEGENERATE_QUANTILES = "degenerate_quantiles"
    NONFINITE = "nonfinite"
    TECHNICAL_LIMIT = "technical_limit"
    NUMERICAL_RESOLUTION = "numerical_resolution"
    INSUFFICIENT_PRECISION = "insufficient_precision"


@dataclass(frozen=True, slots=True)
class TradeRecord:
    identifier: str
    symbol: str
    decision: int
    entry: int
    exits: tuple[int, ...]
    source_sessions: tuple[int, ...]
    recognition: int
    raw: Numeric
    benchmark_excess: Numeric | None = None
    benchmark_complete: Declaration = Declaration.UNKNOWN
    stale: bool = False
    terminal: bool = False


@dataclass(frozen=True, slots=True)
class CalendarSource:
    fixture: str
    provenance: str
    reset_identity: str
    core_sessions: tuple[int, ...]
    authorized_source_start: int
    authorized_source_end: int
    records: tuple[TradeRecord, ...]
    scope: Scope = Scope.SYNTHETIC_FIXTURE
    cohort_complete: Declaration = Declaration.UNKNOWN
    geometry: Declaration = Declaration.UNKNOWN
    accounting: Accounting = Accounting.UNKNOWN
    expected_core_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class CalendarModel:
    fixture: str
    provenance: str
    metric: Metric
    lookback_bound: int | None
    completion_bound: int | None
    stationarity: Declaration = Declaration.UNKNOWN
    strong_mixing: Declaration = Declaration.UNKNOWN
    finite_two_plus_delta: Declaration = Declaration.UNKNOWN
    summable_mixing: Declaration = Declaration.UNKNOWN
    positive_entry_intensity: Declaration = Declaration.UNKNOWN
    positive_long_run_variance: Declaration = Declaration.UNKNOWN
    finite_footprint: Declaration = Declaration.UNKNOWN
    shift_equivariance: Declaration = Declaration.UNKNOWN


@dataclass(frozen=True, slots=True)
class CalendarRequest:
    metric: Metric
    alpha: Numeric
    absolute_full_width: Numeric | None
    selection: Declaration = Declaration.UNKNOWN


class _ResearchOnly:
    authority: ClassVar[str] = "ASYMPTOTIC_CANDIDATE_UNCALIBRATED"
    market_eligible: ClassVar[bool] = False


@dataclass(frozen=True, slots=True)
class CalendarRefusal(_ResearchOnly):
    reason: Reason
    raw_mean: Fraction | None = None
    total_count: int = 0
    zero_count_slices: tuple[int, ...] = ()


@dataclass(frozen=True, slots=True)
class _Diagnostics(_ResearchOnly):
    mean: Fraction
    raw_mean: Fraction
    total_count: int
    total_sum: Fraction
    session_sums: tuple[Fraction, ...]
    session_counts: tuple[int, ...]
    core_trade_ids: tuple[str, ...]
    halo_only_trade_ids: tuple[str, ...]
    block_size: int
    block_counts: tuple[int, ...]
    block_means: tuple[Fraction, ...]
    block_trade_ids: tuple[tuple[str, ...], ...]
    block_halos: tuple[tuple[int, ...], ...]
    deviations: tuple[Fraction, ...]
    quantile_ranks: tuple[int, int]
    quantile_deviations: tuple[Fraction, Fraction]
    sqrt_ratio_lower: Decimal
    sqrt_ratio_upper: Decimal
    candidate_lower: Decimal
    candidate_upper: Decimal
    mathematical_width_upper: Decimal
    displayed_width_upper: Decimal
    desired_full_width: Fraction
    alpha: Fraction
    metric: Metric
    fixture: str
    source_provenance: str
    model_provenance: str
    reset_identity: str
    core_sessions: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class CalendarCandidate(_Diagnostics):
    pass


@dataclass(frozen=True, slots=True)
class CalendarInsufficientEvidence(_Diagnostics):
    reason: ClassVar[Reason] = Reason.INSUFFICIENT_PRECISION


Result = CalendarCandidate | CalendarInsufficientEvidence | CalendarRefusal
_MAX_ROWS = 4096
_MAX_FOOTPRINT = 4096
_MAX_TOTAL_FOOTPRINT = 65536
_MAX_EXPANDED_FOOTPRINT = 262144


class _Invalid(Exception):
    def __init__(self, reason: Reason) -> None:
        self.reason = reason


def _integer(value: object) -> bool:
    return type(value) is int and value.bit_length() <= 4096


def _footprint(record: TradeRecord) -> tuple[int, ...]:
    return (
        record.decision,
        record.entry,
        record.recognition,
        *record.exits,
        *record.source_sessions,
    )


def _source(
    source: CalendarSource,
) -> tuple[tuple[TradeRecord, ...], tuple[str, ...], tuple[Fraction, ...]]:
    if type(source) is not CalendarSource:
        raise _Invalid(Reason.INVALID_INPUT)
    if source.scope is not Scope.SYNTHETIC_FIXTURE:
        raise _Invalid(Reason.REAL_DATA_FORBIDDEN)
    if not all(
        numeric._text(v) for v in (source.fixture, source.provenance, source.reset_identity)
    ):
        raise _Invalid(Reason.INVALID_INPUT)
    if source.geometry is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(Reason.OUTCOME_DEPENDENT_SELECTION)
    if source.cohort_complete is not Declaration.FIXTURE_DECLARED:
        raise _Invalid(Reason.INCOMPLETE_COHORT)
    if type(source.core_sessions) is not tuple or not source.core_sessions:
        raise _Invalid(Reason.INVALID_AXIS)
    if type(source.records) is not tuple:
        raise _Invalid(Reason.INVALID_RECORD)
    if max(len(source.core_sessions), len(source.records)) > _MAX_ROWS:
        raise _Invalid(Reason.TECHNICAL_LIMIT)
    if not all(_integer(t) for t in source.core_sessions) or any(
        b != a + 1 for a, b in zip(source.core_sessions, source.core_sessions[1:], strict=False)
    ):
        raise _Invalid(Reason.INVALID_AXIS)
    if (
        not _integer(source.authorized_source_start)
        or not _integer(source.authorized_source_end)
        or not source.authorized_source_start
        <= source.core_sessions[0]
        <= source.core_sessions[-1]
        <= source.authorized_source_end
    ):
        raise _Invalid(Reason.UNAUTHORIZED_FOOTPRINT)
    total_footprint = 0
    for record in source.records:
        if (
            type(record) is not TradeRecord
            or type(record.exits) is not tuple
            or type(record.source_sessions) is not tuple
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        total_footprint += 3 + len(record.exits) + len(record.source_sessions)
        if total_footprint > _MAX_TOTAL_FOOTPRINT:
            raise _Invalid(Reason.TECHNICAL_LIMIT)
    identifiers: set[str] = set()
    raws: dict[str, Fraction] = {}
    for record in source.records:
        if (
            type(record) is not TradeRecord
            or not numeric._text(record.identifier)
            or not numeric._text(record.symbol)
            or record.identifier in identifiers
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        identifiers.add(record.identifier)
        if (
            type(record.exits) is not tuple
            or type(record.source_sessions) is not tuple
            or not record.exits
            or not record.source_sessions
            or type(record.stale) is not bool
            or type(record.terminal) is not bool
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        if len(record.exits) + len(record.source_sessions) > _MAX_FOOTPRINT:
            raise _Invalid(Reason.TECHNICAL_LIMIT)
        footprint = _footprint(record)
        if (
            not all(_integer(t) for t in footprint)
            or not record.decision
            < record.entry
            <= min(record.exits)
            <= max(record.exits)
            <= record.recognition
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        if len(set(record.exits)) != len(record.exits) or len(set(record.source_sessions)) != len(
            record.source_sessions
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        if record.exits != tuple(sorted(set(record.exits))) or record.source_sessions != tuple(
            sorted(set(record.source_sessions))
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        if not {record.decision, record.entry, record.recognition, *record.exits}.issubset(
            record.source_sessions
        ):
            raise _Invalid(Reason.INVALID_RECORD)
        if not all(
            source.authorized_source_start <= t <= source.authorized_source_end for t in footprint
        ):
            raise _Invalid(Reason.UNAUTHORIZED_FOOTPRINT)
        raws[record.identifier] = numeric._fraction(record.raw)
        if record.benchmark_excess is not None:
            numeric._fraction(record.benchmark_excess)
    core = tuple(
        sorted(
            (
                r
                for r in source.records
                if source.core_sessions[0] <= r.entry <= source.core_sessions[-1]
            ),
            key=lambda r: (r.entry, r.identifier),
        )
    )
    expected = source.expected_core_ids
    if type(expected) is tuple and len(expected) > _MAX_ROWS:
        raise _Invalid(Reason.TECHNICAL_LIMIT)
    if (
        type(expected) is not tuple
        or not all(numeric._text(v) for v in expected)
        or len(set(expected)) != len(expected)
        or set(expected) != {r.identifier for r in core}
    ):
        raise _Invalid(Reason.INCOMPLETE_COHORT)
    halo = tuple(sorted(r.identifier for r in source.records if r not in core))
    return core, halo, tuple(raws[r.identifier] for r in core)


def _model(source: CalendarSource, model: CalendarModel, metric: Metric) -> None:
    if type(model) is not CalendarModel:
        raise _Invalid(Reason.UNKNOWN_MODEL)
    declarations = (
        model.stationarity,
        model.strong_mixing,
        model.finite_two_plus_delta,
        model.summable_mixing,
        model.positive_entry_intensity,
        model.positive_long_run_variance,
        model.finite_footprint,
        model.shift_equivariance,
    )
    if (
        model.fixture != source.fixture
        or not numeric._text(model.provenance)
        or model.metric is not metric
        or any(v is not Declaration.FIXTURE_DECLARED for v in declarations)
    ):
        raise _Invalid(Reason.UNKNOWN_MODEL)
    if not _integer(model.lookback_bound) or not _integer(model.completion_bound):
        raise _Invalid(Reason.UNKNOWN_MODEL)
    assert isinstance(model.lookback_bound, int) and isinstance(model.completion_bound, int)
    if model.lookback_bound < 0 or model.completion_bound < 0:
        raise _Invalid(Reason.UNKNOWN_MODEL)
    for record in source.records:
        if (
            min(_footprint(record)) < record.entry - model.lookback_bound
            or max(_footprint(record)) > record.entry + model.completion_bound
        ):
            raise _Invalid(Reason.OUTSIDE_MODEL_FOOTPRINT)


def _block_size(n: int) -> int:
    lo, hi = 0, n
    while lo < hi:
        mid = (lo + hi) // 2
        if mid**3 >= n**2:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _endpoints(
    mean: Fraction, quantiles: tuple[Fraction, Fraction], b: int, n: int
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]:
    with localcontext(Context(prec=100, Emin=-999999, Emax=999999)) as context:
        square = Fraction(b, n)
        upper = numeric._sqrt_upper(square, context)
        lower = context.next_minus(upper)
        if lower < 0 or Fraction(lower) ** 2 > square or Fraction(upper) ** 2 < square:
            raise _Invalid(Reason.NUMERICAL_RESOLUTION)
    lo_deviation, hi_deviation = quantiles
    low = numeric._checked(
        mean - max(hi_deviation * Fraction(lower), hi_deviation * Fraction(upper))
    )
    high = numeric._checked(
        mean - min(lo_deviation * Fraction(lower), lo_deviation * Fraction(upper))
    )
    mathematical = numeric._checked((hi_deviation - lo_deviation) * Fraction(upper))
    # log10(2) < 30103/100000: size in decimal digits, not binary bits.
    bits = max(
        abs(v.numerator).bit_length() + v.denominator.bit_length()
        for v in (low, high, mathematical)
    )
    precision = 100 + (bits * 30103 + 99999) // 100000
    with localcontext(Context(prec=precision, Emin=-999999, Emax=999999)) as context:
        lo = numeric._decimal(low, context, ROUND_FLOOR)
        hi = numeric._decimal(high, context, ROUND_CEILING)
        math_width = numeric._decimal(mathematical, context, ROUND_CEILING)
        display_width = numeric._decimal(
            numeric._checked(Fraction(hi) - Fraction(lo)), context, ROUND_CEILING
        )
    if Fraction(lo) > low or Fraction(hi) < high or hi <= lo:
        raise _Invalid(Reason.NUMERICAL_RESOLUTION)
    return lo, hi, lower, upper, math_width, display_width


def estimate(source: CalendarSource, model: CalendarModel, request: CalendarRequest) -> Result:
    """Uncalibrated asymptotic candidate under explicit invented-law premises.

    Ratio root and inverse empirical-CDF convention, checked 2026-10-01:
    https://www3.stat.sinica.edu.tw/statistica/oldpdf/A11n49.pdf section4.
    No coverage conditional on emission or finite-sample guarantee is asserted.
    """
    raw_mean = None
    count = 0
    try:
        core, halo, raws = _source(source)
        count = len(core)
        if count == 0:
            raise _Invalid(Reason.ZERO_FULL_COUNT)
        raw_mean = numeric._checked(numeric._sum(raws) / count)
        if type(request) is not CalendarRequest or type(request.metric) is not Metric:
            raise _Invalid(Reason.INVALID_INPUT)
        if (
            request.metric is not Metric.RAW
            and request.metric is not Metric.WIN
            and request.metric is not Metric.SYNTHETIC_EXCESS
        ):
            raise _Invalid(Reason.INVALID_INPUT)
        if request.selection is not Declaration.FIXTURE_DECLARED:
            raise _Invalid(Reason.OUTCOME_DEPENDENT_SELECTION)
        if request.absolute_full_width is None:
            raise _Invalid(Reason.UNKNOWN_PRECISION)
        alpha = numeric._fraction(request.alpha)
        width = numeric._fraction(request.absolute_full_width)
        if alpha != Fraction(1, 20) or width <= 0:
            raise _Invalid(Reason.INVALID_INPUT)
        if source.accounting is not Accounting.BEFORE_TAX_MODEL_COST:
            raise _Invalid(Reason.UNKNOWN_ACCOUNTING)
        _model(source, model, request.metric)
        if any(record.stale for record in core):
            raise _Invalid(Reason.STALE_OUTCOME)
        if any(record.terminal for record in core):
            raise _Invalid(Reason.TERMINAL_OUTCOME)
        values = raws
        if request.metric is Metric.WIN:
            values = tuple(Fraction(raw > 0) for raw in raws)
        elif request.metric is Metric.SYNTHETIC_EXCESS:
            if any(
                record.benchmark_excess is None
                or record.benchmark_complete is not Declaration.FIXTURE_DECLARED
                for record in core
            ):
                raise _Invalid(Reason.MISSING_BENCHMARK)
            values = tuple(
                numeric._fraction(record.benchmark_excess)
                for record in core
                if record.benchmark_excess is not None
            )
        n = len(source.core_sessions)
        b = _block_size(n)
        if not 2 <= b < n:
            raise _Invalid(Reason.INVALID_BLOCK_SIZE)
        sums = [Fraction(0)] * n
        counts = [0] * n
        for record, value in zip(core, values, strict=True):
            index = record.entry - source.core_sessions[0]
            sums[index] = numeric._checked(sums[index] + value)
            counts[index] += 1
        total = numeric._sum(tuple(sums))
        mean = numeric._checked(total / count)
        block_counts = tuple(sum(counts[j : j + b]) for j in range(n - b + 1))
        zero = tuple(j for j, c in enumerate(block_counts) if c == 0)
        if zero:
            return CalendarRefusal(Reason.ZERO_COUNT_SLICE, raw_mean, count, zero)
        block_means = tuple(
            numeric._checked(numeric._sum(tuple(sums[j : j + b])) / c)
            for j, c in enumerate(block_counts)
        )
        deviations = tuple(numeric._checked(value - mean) for value in block_means)
        ordered = sorted(deviations)
        if ordered[0] == ordered[-1]:
            raise _Invalid(Reason.DEGENERATE_ROOTS)
        q = len(deviations)
        ranks = ((q + 39) // 40 - 1, (39 * q + 39) // 40 - 1)
        quantiles = (ordered[ranks[0]], ordered[ranks[1]])
        if quantiles[0] == quantiles[1]:
            raise _Invalid(Reason.DEGENERATE_QUANTILES)
        lo, hi, sqrt_lo, sqrt_hi, math_width, display_width = _endpoints(mean, quantiles, b, n)
        # Count each record's appearances before expanding per-block diagnostics.
        expanded = 0
        for record in core:
            index = record.entry - source.core_sessions[0]
            appearances = min(index, n - b) - max(0, index - b + 1) + 1
            expanded += appearances * (4 + len(record.exits) + len(record.source_sessions))
            if expanded > _MAX_EXPANDED_FOOTPRINT:
                raise _Invalid(Reason.TECHNICAL_LIMIT)
        selected = tuple(
            tuple(
                record
                for record in core
                if source.core_sessions[j] <= record.entry <= source.core_sessions[j + b - 1]
            )
            for j in range(n - b + 1)
        )
        block_ids = tuple(tuple(record.identifier for record in records) for records in selected)
        block_halos = tuple(
            tuple(
                sorted(
                    {
                        t
                        for record in records
                        for t in _footprint(record)
                        if not source.core_sessions[j] <= t <= source.core_sessions[j + b - 1]
                    }
                )
            )
            for j, records in enumerate(selected)
        )
        result_type: type[CalendarCandidate] | type[CalendarInsufficientEvidence] = (
            CalendarInsufficientEvidence
            if max(Fraction(math_width), Fraction(display_width)) > width
            else CalendarCandidate
        )
        return result_type(
            mean,
            raw_mean,
            count,
            total,
            tuple(sums),
            tuple(counts),
            tuple(record.identifier for record in core),
            halo,
            b,
            block_counts,
            block_means,
            block_ids,
            block_halos,
            deviations,
            ranks,
            quantiles,
            sqrt_lo,
            sqrt_hi,
            lo,
            hi,
            math_width,
            display_width,
            width,
            alpha,
            request.metric,
            source.fixture,
            source.provenance,
            model.provenance,
            source.reset_identity,
            source.core_sessions,
        )
    except _Invalid as error:
        return CalendarRefusal(error.reason, raw_mean, count)
    except numeric._Invalid as error:
        return CalendarRefusal(Reason(error.reason.value), raw_mean, count)
    except (DecimalException, OverflowError):
        return CalendarRefusal(Reason.NUMERICAL_RESOLUTION, raw_mean, count)
