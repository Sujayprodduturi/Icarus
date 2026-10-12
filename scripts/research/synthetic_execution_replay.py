"""One preset invented stock trade; declared timing is never market certification."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from itertools import pairwise

from scripts.research.synthetic_benchmark_match import (
    BenchmarkMatch,
    BenchmarkObservation,
    ExitFragment,
    FixtureIdentity,
    FragmentStatus,
    Precision,
    SyntheticTrade,
    Timing,
    match_benchmark,
)

from icarus.common.config import ExecutionRealism
from icarus.common.types import OrderSide
from icarus.engine.costmodel import Charges, CostModel, DeliveryFeeContext, Segment
from icarus.engine.fills import FillModel, FillResult, Intent, OrderKind
from icarus.engine.simcore import SignalId
from icarus.engine.timed_execution import (
    ExitCause as ExitCause,
)
from icarus.engine.timed_execution import (
    ReplayRefusal as ReplayRefusal,
)
from icarus.engine.timed_execution import (
    _cap,
    _fill,
    _proxy_refusal,
    select_end,
    select_open,
)
from icarus.engine.timed_simulation import TimedRun
from icarus.engine.timing import (
    OpeningLiquidity as OpeningLiquidity,
)
from icarus.engine.timing import (
    ReplayBar as ReplayBar,
)
from icarus.engine.timing import (
    Session as Session,
)
from icarus.engine.timing import (
    SourceDeclaration as SourceDeclaration,
)
from icarus.engine.timing import (
    _integer,
    _money,
    _utc,
)
from icarus.engine.timing import (
    fixture_digest as fixture_digest,
)

STEP = timedelta(minutes=15)
SCOPE = "SYNTHETIC_PRESET_TRADE_NOT_PORTFOLIO_OR_MARKET_EVIDENCE"


class ReplayStatus(StrEnum):
    NO_ENTRY = "no_entry"
    OPEN = "residual_inventory_open"
    COMPLETE = "fully_executed"
    REFUSED = "replay_refused"


@dataclass(frozen=True, slots=True)
class ReplayRequest:
    signal_id: SignalId
    decision_available_ts: datetime
    quantity: int
    stop_price: Decimal
    target_price: Decimal | None = None
    time_stop_sessions: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId):
            raise TypeError("request requires original daily SignalId")
        _utc(self.decision_available_ts)
        _integer(self.quantity)
        _money(self.stop_price)
        if self.target_price is not None:
            _money(self.target_price)
            if self.target_price <= self.stop_price:
                raise ValueError("target must exceed stop")
        if self.time_stop_sessions is not None:
            _integer(self.time_stop_sessions)


@dataclass(frozen=True, slots=True)
class ReplayAttempt:
    reason: ExitCause
    session_index: int
    raw_bar_ts: datetime
    timing: Timing
    recognition_ts: datetime
    convention: str
    fill: FillResult
    charges: Charges | None


@dataclass(frozen=True, slots=True)
class RejectedOpening:
    """Provisional proxy candidate rejected offline, never an accepted sale or charge."""

    session_index: int
    raw_bar_ts: datetime
    candidate: FillResult
    realized_capacity: int


@dataclass(frozen=True, slots=True)
class ReplayTrace:
    signal_id: SignalId
    source: SourceDeclaration
    requested_quantity: int
    original_quantity: int
    remaining_quantity: int
    attempts: tuple[ReplayAttempt, ...]
    status: ReplayStatus
    refusal: ReplayRefusal | None
    rejected_opening: RejectedOpening | None = None
    scope: str = field(default=SCOPE, init=False)

    @property
    def entry(self) -> ReplayAttempt | None:
        return next(
            (a for a in self.attempts if a.reason is ExitCause.ENTRY and a.fill.filled), None
        )

    @property
    def exits(self) -> tuple[ReplayAttempt, ...]:
        return tuple(a for a in self.attempts if a.reason is not ExitCause.ENTRY and a.fill.filled)


@dataclass(frozen=True, slots=True)
class ReplayComparison:
    trace: ReplayTrace
    benchmark: BenchmarkMatch | None


@dataclass(frozen=True, slots=True)
class TimedBenchmark:
    benchmark_return: Fraction | None
    match: BenchmarkMatch | None
    run_unavailable: bool


def match_timed_trade(
    run: TimedRun,
    signal_id: SignalId,
    observations: tuple[BenchmarkObservation, ...],
    expected_benchmark: FixtureIdentity,
) -> TimedBenchmark:
    """The containing run is mandatory: a later whole-run refusal invalidates every trade."""
    if not isinstance(run, TimedRun) or not isinstance(signal_id, SignalId):
        raise TypeError("matching requires the containing timed run and SignalId")
    trade = next((t for t in run.trades if t.signal_id == signal_id), None)
    if trade is None:
        raise ValueError("signal is not an accepted trade in this run")
    if not run.valid:
        return TimedBenchmark(None, None, True)
    exits = tuple(
        ExitFragment(
            str(i),
            e.quantity,
            e.timing,
            FragmentStatus.EXECUTED,
            e.recognition_ts,
            e.recognition_ts,
        )
        for i, e in enumerate(trade.exits)
    )
    matched = match_benchmark(
        SyntheticTrade(trade.original_quantity, trade.entry.timing, exits),
        observations,
        expected_benchmark,
    )
    return TimedBenchmark(matched.benchmark_return, matched, False)


def _preflight(
    request: ReplayRequest,
    sessions: tuple[Session, ...],
    bars: tuple[ReplayBar, ...],
    source: SourceDeclaration,
) -> ReplayRefusal | None:
    if not isinstance(request, ReplayRequest) or not isinstance(source, SourceDeclaration):
        raise TypeError("request/source must be typed declarations")
    for rows, cls in ((sessions, Session), (bars, ReplayBar)):
        if type(rows) is not tuple or any(not isinstance(row, cls) for row in rows):
            raise TypeError("session/bar inputs must be immutable typed tuples")
    if not sessions or any(
        b.index != a.index + 1 or b.open_ts <= a.close_ts for a, b in pairwise(sessions)
    ):
        return ReplayRefusal.MISSING_REFINEMENT
    decision = sessions[0]
    if (
        decision.index != request.signal_id.decision_index
        or decision.open_ts != request.signal_id.decision_ts
        or request.decision_available_ts < decision.close_ts
    ):
        return ReplayRefusal.INVALID_DECISION
    expected = tuple(
        (s.index, s.open_ts + k * STEP, s.open_ts + (k + 1) * STEP)
        for s in sessions[1:]
        for k in range((s.close_ts - s.open_ts) // STEP)
    )
    if not expected or tuple((b.session_index, b.bar.ts, b.end_ts) for b in bars) != expected:
        return ReplayRefusal.MISSING_REFINEMENT
    if (
        any(s.source != source for s in sessions)
        or any(
            b.source != source or (b.opening is not None and b.opening.source != source)
            for b in bars
        )
        or fixture_digest(sessions, bars) != source.sha256
    ):
        return ReplayRefusal.SOURCE_MISMATCH
    return None


def _attempt(
    reason: ExitCause,
    row: ReplayBar,
    fill: FillResult,
    costs: CostModel,
    fees: DeliveryFeeContext,
    signal: SignalId,
    *,
    opening: bool,
) -> ReplayAttempt:
    recognized = row.bar.ts if opening else row.end_ts
    timing = (
        Timing(Precision.EVENT_RESOLVED, row.bar.ts)
        if opening
        else Timing(Precision.BAR_RESOLVED, interval_start=row.bar.ts, interval_end=row.end_ts)
    )
    charges = None
    if fill.filled:
        assert fill.price is not None
        quantity = Decimal(fill.filled_quantity)
        charges = (
            costs.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, fill.price, quantity)
            if (reason is ExitCause.ENTRY)
            else fees.executed_sell_charges(
                costs,
                Segment.EQUITY_DELIVERY,
                fill.price,
                quantity,
                symbol=signal.symbol,
                executed_at=recognized,
                scope=signal,
            )
        )
    return ReplayAttempt(
        reason,
        row.session_index,
        row.bar.ts,
        timing,
        recognized,
        "MODEL_OPEN_EVENT" if opening else "UNRESOLVED_BAR_INTERVAL",
        fill,
        charges,
    )


def replay_trade(
    request: ReplayRequest,
    sessions: tuple[Session, ...],
    bars: tuple[ReplayBar, ...],
    source: SourceDeclaration,
    *,
    execution: ExecutionRealism,
    costs: CostModel,
) -> ReplayTrace:
    """Replay one caller-sized synthetic trade, preserving inventory on every refusal."""
    refusal = _preflight(request, sessions, bars, source)
    if not isinstance(execution, ExecutionRealism) or not isinstance(costs, CostModel):
        raise TypeError("replay needs execution config and CostModel")
    attempts: list[ReplayAttempt] = []
    original = remaining = 0
    entry_session = -1
    activated: datetime | None = None
    rejected_opening = None
    latched = False
    model, fees = FillModel(execution), DeliveryFeeContext()
    eligible = request.decision_available_ts + timedelta(milliseconds=execution.latency_ms)
    for row in bars if refusal is None else ():
        ts = row.bar.ts
        if original == 0:
            if row.session_index != sessions[1].index:
                break
            if ts < eligible:
                continue
            refusal = _proxy_refusal(row)
            if refusal is not None:
                break
            intent = Intent(
                OrderSide.BUY,
                OrderKind.MARKETABLE_LIMIT,
                request.quantity,
                request.decision_available_ts,
            )
            fill = _fill(intent, row, model, execution, opening=True)
            if fill.filled_quantity > _cap(row.bar.volume, execution):
                refusal = ReplayRefusal.LIQUIDITY_UNAVAILABLE
                rejected_opening = RejectedOpening(
                    row.session_index, ts, fill, _cap(row.bar.volume, execution)
                )
                break
            attempts.append(
                _attempt(ExitCause.ENTRY, row, fill, costs, fees, request.signal_id, opening=True)
            )
            if not fill.filled:
                break
            original = remaining = fill.filled_quantity
            entry_session = row.session_index
            activated = ts + timedelta(milliseconds=execution.latency_ms)
            selected = select_end(
                row, request.stop_price, request.target_price, activated=activated
            )
            if selected.refusal is not None:
                refusal = selected.refusal
                break
            continue
        assert activated is not None
        selected = select_open(
            row,
            request.stop_price,
            latched=latched,
            activated=activated,
            timer_due=request.time_stop_sessions is not None
            and row.session_index - entry_session + 1 >= request.time_stop_sessions,
        )
        opening = selected.cause is not None
        if not opening:
            selected = select_end(
                row, request.stop_price, request.target_price, activated=activated
            )
        if selected.refusal is not None:
            refusal = selected.refusal
            break
        if selected.cause is None:
            continue
        cause, kind, limit = selected.cause, selected.kind, selected.limit
        latched = latched or selected.latched
        refusal = _proxy_refusal(row)
        if refusal is not None:
            break
        intent = Intent(OrderSide.SELL, kind, remaining, request.decision_available_ts, limit)
        fill = _fill(intent, row, model, execution, opening=opening)
        # At most one accepted fill per bar: entry-bar protection refuses ordering,
        # and carried exits select one branch. No second call can reuse this capacity.
        if opening and fill.filled_quantity > _cap(row.bar.volume, execution):
            refusal = ReplayRefusal.LIQUIDITY_UNAVAILABLE
            rejected_opening = RejectedOpening(
                row.session_index, ts, fill, _cap(row.bar.volume, execution)
            )
            break
        attempts.append(_attempt(cause, row, fill, costs, fees, request.signal_id, opening=opening))
        remaining -= fill.filled_quantity
        if remaining == 0:
            break
    status = (
        ReplayStatus.REFUSED
        if refusal is not None
        else (
            ReplayStatus.COMPLETE
            if original and not remaining
            else ReplayStatus.OPEN
            if original
            else ReplayStatus.NO_ENTRY
        )
    )
    if not attempts and refusal is None:
        refusal, status = ReplayRefusal.NO_ELIGIBLE_OPEN, ReplayStatus.REFUSED
    return ReplayTrace(
        request.signal_id,
        source,
        request.quantity,
        original,
        remaining,
        tuple(attempts),
        status,
        refusal,
        rejected_opening,
    )


def replay_and_match(
    request: ReplayRequest,
    sessions: tuple[Session, ...],
    bars: tuple[ReplayBar, ...],
    source: SourceDeclaration,
    *,
    execution: ExecutionRealism,
    costs: CostModel,
    observations: tuple[BenchmarkObservation, ...],
    expected_benchmark: FixtureIdentity,
) -> ReplayComparison:
    """Route actual execution branches/quantities to the existing whole-trade matcher."""
    trace = replay_trade(request, sessions, bars, source, execution=execution, costs=costs)
    entry = trace.entry
    if entry is None:
        return ReplayComparison(trace, None)
    exits = tuple(
        ExitFragment(
            str(i),
            a.fill.filled_quantity,
            a.timing,
            FragmentStatus.EXECUTED,
            a.recognition_ts,
            a.recognition_ts,
        )
        for i, a in enumerate(trace.exits)
    )
    trade = SyntheticTrade(trace.original_quantity, entry.timing, exits)
    return ReplayComparison(trace, match_benchmark(trade, observations, expected_benchmark))
