"""One preset invented stock trade; declared timing is never market certification."""

import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum
from hashlib import sha256
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

from icarus.common.calendar import IST
from icarus.common.config import ExecutionRealism
from icarus.common.types import OrderSide
from icarus.engine.costmodel import Charges, CostModel, DeliveryFeeContext, Segment
from icarus.engine.fills import FillModel, FillResult, Intent, NoFillReason, OrderKind, SimBar
from icarus.engine.simcore import SignalId

STEP = timedelta(minutes=15)
SCOPE = "SYNTHETIC_PRESET_TRADE_NOT_PORTFOLIO_OR_MARKET_EVIDENCE"


class ReplayRefusal(StrEnum):
    MISSING_REFINEMENT = "missing_or_conflicting_refinement"
    SOURCE_MISMATCH = "incompatible_source_or_fixture_hash"
    INVALID_DECISION = "decision_session_or_availability_mismatch"
    NO_ELIGIBLE_OPEN = "no_eligible_next_session_open"
    MISSING_OPENING_LIQUIDITY = "missing_opening_liquidity"
    LATE_OPENING_LIQUIDITY = "late_opening_liquidity"
    LIQUIDITY_UNAVAILABLE = "opening_candidate_unsupported_by_realized_volume"
    PATH_ORDER_UNAVAILABLE = "protective_activation_path_order_unavailable"
    ORDER_UNAVAILABLE = "stop_target_order_unavailable"


class ReplayStatus(StrEnum):
    NO_ENTRY = "no_entry"
    OPEN = "residual_inventory_open"
    COMPLETE = "fully_executed"
    REFUSED = "replay_refused"


class ExitCause(StrEnum):
    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    TIME_STOP = "time_stop"


def _utc(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is not UTC:
        raise ValueError("fixture times must use datetime.UTC")


def _integer(value: int, *, zero: bool = False) -> None:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError("expected a whole quantity/index, excluding bool")


def _money(value: Decimal, *, zero: bool = False) -> None:
    if type(value) is not Decimal or not value.is_finite() or (value < 0 if zero else value <= 0):
        raise ValueError("expected finite Decimal money/volume")


def _window(start: datetime, end: datetime) -> None:
    _utc(start)
    _utc(end)
    if end <= start or start.astimezone(IST).date() != end.astimezone(IST).date():
        raise ValueError("window must be ordered within one IST date")


@dataclass(frozen=True, slots=True)
class SourceDeclaration:
    """Expected fixture identity/hash declaration, not authenticated source evidence."""

    artifact_id: str
    version: str
    sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if any(type(s) is not str or not s.strip() for s in (self.artifact_id, self.version)):
            raise ValueError("source identity/version must be nonempty strings")
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.sha256)
        ):
            raise ValueError("source SHA256 must be lowercase hex")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("only integer schema1 is supported")


@dataclass(frozen=True, slots=True)
class Session:
    index: int
    open_ts: datetime
    close_ts: datetime
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _integer(self.index, zero=True)
        _window(self.open_ts, self.close_ts)
        if (self.close_ts - self.open_ts) % STEP:
            raise ValueError("declared session must partition into exact M15 bars")
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("session requires a source declaration")


@dataclass(frozen=True, slots=True)
class OpeningLiquidity:
    quantity: Decimal
    available_ts: datetime
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _money(self.quantity, zero=True)
        _utc(self.available_ts)
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("opening proxy requires a source declaration")


@dataclass(frozen=True, slots=True)
class ReplayBar:
    session_index: int
    bar: SimBar
    end_ts: datetime
    opening: OpeningLiquidity | None
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _integer(self.session_index, zero=True)
        if not isinstance(self.bar, SimBar):
            raise TypeError("replay bar requires SimBar")
        _window(self.bar.ts, self.end_ts)
        if self.end_ts - self.bar.ts != STEP:
            raise ValueError("only exact M15 intervals are supported")
        for price in (self.bar.open, self.bar.high, self.bar.low, self.bar.close):
            _money(price)
        _money(self.bar.volume, zero=True)
        if (
            not self.bar.low
            <= min(self.bar.open, self.bar.close)
            <= max(self.bar.open, self.bar.close)
            <= self.bar.high
        ):
            raise ValueError("OHLC range is inconsistent")
        if self.opening is not None and not isinstance(self.opening, OpeningLiquidity):
            raise TypeError("opening proxy must be a typed declaration or None")
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("bar requires a source declaration")


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


def fixture_digest(sessions: tuple[Session, ...], bars: tuple[ReplayBar, ...]) -> str:
    """Bind actual fixture values, excluding circular identity/hash declarations."""
    payload = [
        [(s.index, s.open_ts.isoformat(), s.close_ts.isoformat()) for s in sessions],
        [
            (
                b.session_index,
                b.bar.ts.isoformat(),
                b.end_ts.isoformat(),
                *(str(v) for v in (b.bar.open, b.bar.high, b.bar.low, b.bar.close, b.bar.volume)),
                None
                if b.opening is None
                else (str(b.opening.quantity), b.opening.available_ts.isoformat()),
            )
            for b in bars
        ],
    ]
    return sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


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


def _proxy_refusal(row: ReplayBar) -> ReplayRefusal | None:
    if row.opening is None:
        return ReplayRefusal.MISSING_OPENING_LIQUIDITY
    if row.opening.available_ts > row.bar.ts:
        return ReplayRefusal.LATE_OPENING_LIQUIDITY
    return None


def _cap(volume: Decimal, execution: ExecutionRealism) -> int:
    return int(
        (volume * Decimal(str(execution.max_participation_of_depth))).to_integral_value(
            rounding=ROUND_DOWN
        )
    )


def _fill(
    intent: Intent, row: ReplayBar, model: FillModel, execution: ExecutionRealism, *, opening: bool
) -> FillResult:
    assert row.opening is not None
    raw = model.execute(
        intent, replace(row.bar, volume=row.opening.quantity) if opening else row.bar
    )
    allowance = _cap(row.opening.quantity, execution)
    if not opening:
        allowance = min(allowance, _cap(row.bar.volume, execution))
    if raw.filled and (
        allowance <= 0 or (not execution.model_partial_fills and allowance < intent.quantity)
    ):
        return FillResult(0, intent.quantity, None, NoFillReason.TOO_LARGE_FOR_BAR, None)
    if raw.filled and raw.filled_quantity > allowance:
        return FillResult(allowance, intent.quantity, raw.price, None, raw.ts)
    return raw


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
            if row.bar.low <= request.stop_price or (
                request.target_price is not None and row.bar.high > request.target_price
            ):
                refusal = ReplayRefusal.PATH_ORDER_UNAVAILABLE
                break
            continue
        assert activated is not None
        stop = row.bar.low <= request.stop_price
        target = request.target_price is not None and row.bar.high > request.target_price
        if ts < activated:
            if stop or target:
                refusal = ReplayRefusal.PATH_ORDER_UNAVAILABLE
                break
            continue
        opening = True
        kind = OrderKind.MARKETABLE_LIMIT
        limit = None
        if latched or row.bar.open <= request.stop_price:
            cause = ExitCause.STOP
            if not latched:
                kind, limit = OrderKind.STOP, request.stop_price
            latched = True
        elif request.time_stop_sessions is not None and (
            row.session_index - entry_session + 1 >= request.time_stop_sessions
        ):
            cause = ExitCause.TIME_STOP
        elif stop and target:
            refusal = ReplayRefusal.ORDER_UNAVAILABLE
            break
        elif stop:
            cause, kind, limit, opening = ExitCause.STOP, OrderKind.STOP, request.stop_price, False
            latched = True
        elif target:
            cause, kind, limit, opening = (
                ExitCause.TARGET,
                OrderKind.RESTING_LIMIT,
                request.target_price,
                False,
            )
        else:
            continue
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
