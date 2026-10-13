"""Shared causal M15 books on declared synthetic daily columns, never a live path."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields, replace
from datetime import datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from hashlib import sha256
from itertools import pairwise

import numpy as np
import numpy.typing as npt

from icarus.common.config import Risk
from icarus.common.types import OrderSide
from icarus.engine.costmodel import Charges, CostModel, DeliveryFeeContext, Segment
from icarus.engine.entry_accounting import (
    charge_difference,
    entry_outlay,
    scaled_charges,
    whole_shares,
)
from icarus.engine.fills import FillModel, FillResult, Intent, OrderKind
from icarus.engine.simcore import (
    ExitPlan,
    ExitReason,
    ManagementExitEvent,
    RebalanceEvent,
    RebalanceStatus,
    SignalId,
    _ts_at,
    rebalance_decision,
    validate_consumer_columns,
)
from icarus.engine.timed_execution import (
    ExitCause,
    ReplayRefusal,
    Selection,
    _cap,
    _fill,
    _proxy_refusal,
    select_end,
    select_open,
)
from icarus.engine.timing import (
    OpeningLiquidity as OpeningLiquidity,
)
from icarus.engine.timing import (
    Precision,
    Timing,
    _integer,
    _money,
    _utc,
    fixture_digest,
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
from icarus.strategy.dsl import Panel, StrategyCandidate, Timeframe

Column = npt.NDArray[np.float64]

SCOPE = "SYNTHETIC_TIMED_BOOK_NOT_MARKET_EVIDENCE"


class TimedRefusal(StrEnum):
    UNSUPPORTED_MANAGEMENT = "unsupported_opposite_signal"
    UNSUPPORTED_REBALANCE = "unsupported_rebalance"
    UNSUPPORTED_TRAILING = "unsupported_trailing"
    UNSUPPORTED_SIZING = "unsupported_sizing"
    EXCESS_RISK = "per_trade_risk_above_goal"
    MISSING_REFINEMENT = "missing_or_conflicting_refinement"
    SOURCE_MISMATCH = "incompatible_source_or_fixture_hash"
    AGGREGATION = "daily_m15_aggregation_mismatch"
    LIQUIDITY_UNAVAILABLE = "opening_candidate_unsupported_by_realized_volume"
    MISSING_OPENING_LIQUIDITY = "missing_opening_liquidity"
    LATE_OPENING_LIQUIDITY = "late_opening_liquidity"
    PATH_ORDER_UNAVAILABLE = "protective_activation_path_order_unavailable"
    ORDER_UNAVAILABLE = "stop_target_order_unavailable"
    UNAVAILABLE_SIGNAL = "missing_daily_decision"
    MISSING_MANAGEMENT_DECISION = "missing_management_decision"
    UNSUPPORTED_CLOCK = "unsupported_intraday_strategy_clock"
    UNSUPPORTED_UNIVERSE = "unsupported_non_equity_universe"


class Disposition(StrEnum):
    ACCEPTED = "accepted"
    ALREADY_HELD = "already_held"
    NO_SLOT = "no_slot"
    NO_STOP_DISTANCE = "no_stop_distance"
    NO_NEXT_SESSION = "no_eligible_next_session"
    NOT_TRADABLE = "not_tradable"
    ENTRY_NOT_FILLED = "entry_not_filled"
    ROUNDS_TO_ZERO = "rounds_to_zero"
    CONCENTRATION_CAP = "concentration_cap"
    HEAT_CAP = "heat_cap"
    INSUFFICIENT_CASH = "insufficient_cash"
    UNAVAILABLE = "run_unavailable"


@dataclass(frozen=True, slots=True)
class Refinement:
    symbol: str
    bars: tuple[ReplayBar, ...]

    def __post_init__(self) -> None:
        if type(self.symbol) is not str or not self.symbol.strip():
            raise ValueError("refinement symbol must be nonempty")
        if type(self.bars) is not tuple or any(not isinstance(b, ReplayBar) for b in self.bars):
            raise TypeError("refinement bars must be immutable typed records")


@dataclass(frozen=True, slots=True)
class TimedFixture:
    sessions: tuple[Session, ...]
    refinements: tuple[Refinement, ...]
    source: SourceDeclaration

    def __post_init__(self) -> None:
        if type(self.sessions) is not tuple or any(
            not isinstance(s, Session) for s in self.sessions
        ):
            raise TypeError("fixture sessions must be immutable typed records")
        if type(self.refinements) is not tuple or any(
            not isinstance(r, Refinement) for r in self.refinements
        ):
            raise TypeError("fixture refinements must be immutable typed records")
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("fixture needs a source declaration")


def timed_fixture_digest(sessions: tuple[Session, ...], refinements: tuple[Refinement, ...]) -> str:
    payload = [(r.symbol, fixture_digest(sessions, r.bars)) for r in refinements]
    return sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True, slots=True)
class SignalDisposition:
    signal_id: SignalId
    reason: Disposition


@dataclass(frozen=True, slots=True)
class RunRefusal:
    reason: TimedRefusal
    symbols: tuple[str, ...]
    source_indices: tuple[int, ...]
    bar_ts: datetime | None = None


@dataclass(frozen=True, slots=True)
class TimedLeg:
    cause: ExitCause
    source_index: int
    raw_bar_ts: datetime
    timing: Timing
    recognition_ts: datetime
    quantity: int
    price: Decimal
    charges: Charges
    allocated_entry_charges: Charges | None
    convention: str

    def __post_init__(self) -> None:
        _integer(self.source_index, zero=True)
        _integer(self.quantity)
        _money(self.price)
        _utc(self.raw_bar_ts)
        _utc(self.recognition_ts)
        if not isinstance(self.cause, ExitCause) or not isinstance(self.timing, Timing):
            raise TypeError("timed leg requires declared cause/precision")
        if not isinstance(self.charges, Charges):
            raise TypeError("timed leg requires itemized charges")
        if self.charges.turnover != self.quantity * self.price:
            raise ValueError("execution charges must match actual turnover")
        for item in (self.charges, self.allocated_entry_charges):
            if item is not None:
                if not isinstance(item, Charges):
                    raise TypeError("allocation must be itemized charges")
                for component in fields(item):
                    _money(getattr(item, component.name), zero=True)
        if self.timing.precision is Precision.EVENT_RESOLVED:
            if (
                self.timing.event_ts != self.raw_bar_ts
                or self.recognition_ts != self.raw_bar_ts
                or (self.convention != "MODEL_OPEN_EVENT")
            ):
                raise ValueError("opening event fields contradict modeled time")
        elif self.timing.precision is Precision.BAR_RESOLVED:
            if (
                self.timing.event_ts is not None
                or self.timing.interval_start != self.raw_bar_ts
                or (self.timing.interval_end != self.recognition_ts)
                or (self.convention != "UNRESOLVED_BAR_INTERVAL")
            ):
                raise ValueError("interval fields must not invent an exact fill")
        else:
            raise ValueError("execution cannot use a daily session label")


@dataclass(frozen=True, slots=True)
class TimedTrade:
    signal_id: SignalId
    decision_available_ts: datetime
    intended_quantity: int
    original_quantity: int
    entry: TimedLeg
    exits: tuple[TimedLeg, ...]
    remaining_quantity: int
    remaining_entry_charges: Charges

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId) or not isinstance(self.entry, TimedLeg):
            raise TypeError("timed trade requires original identity and typed entry")
        _utc(self.decision_available_ts)
        _integer(self.intended_quantity)
        _integer(self.original_quantity)
        _integer(self.remaining_quantity, zero=True)
        if type(self.exits) is not tuple or any(not isinstance(e, TimedLeg) for e in self.exits):
            raise TypeError("exit legs must be an immutable tuple")
        if (
            self.entry.cause is not ExitCause.ENTRY
            or self.entry.source_index <= self.signal_id.decision_index
            or (self.entry.raw_bar_ts <= self.decision_available_ts)
        ):
            raise ValueError("entry must follow original daily decision availability")
        if self.original_quantity != self.entry.quantity or (
            sum(e.quantity for e in self.exits) + self.remaining_quantity != self.original_quantity
        ):
            raise ValueError("timed trade inventory must conserve original filled quantity")
        if self.remaining_quantity < 0 or self.original_quantity <= 0:
            raise ValueError("timed trade quantities must be positive/nonnegative")
        previous = self.entry.recognition_ts
        for exit_leg in self.exits:
            if (
                exit_leg.cause is ExitCause.ENTRY
                or exit_leg.recognition_ts < previous
                or (exit_leg.source_index < self.entry.source_index)
            ):
                raise ValueError("exit legs must follow the entry and prior executions")
            previous = exit_leg.recognition_ts
        if not isinstance(self.remaining_entry_charges, Charges):
            raise TypeError("remaining acquisition costs must be itemized")
        for component in fields(self.entry.charges):
            residual = getattr(self.remaining_entry_charges, component.name)
            _money(residual, zero=True)
            allocated = sum(
                (Fraction(getattr(e.allocated_entry_charges, component.name)) for e in self.exits),
                Fraction(0),
            )
            if allocated + Fraction(residual) != Fraction(
                getattr(self.entry.charges, component.name)
            ):
                raise ValueError("original acquisition charges must conserve every component")


@dataclass(frozen=True, slots=True)
class TimedAttempt:
    signal_id: SignalId
    cause: ExitCause
    source_index: int
    bar_ts: datetime
    fill: FillResult
    opening: bool


@dataclass(frozen=True, slots=True)
class TimedRun:
    mode: str
    symbols: tuple[str, ...]
    source_indices: tuple[int, ...]
    trades: tuple[TimedTrade, ...]
    dispositions: tuple[SignalDisposition, ...]
    attempts: tuple[TimedAttempt, ...]
    refusal: RunRefusal | None
    cash: Decimal | None
    realized_equity: Decimal | None
    final_equity: Decimal | None
    daily_equity: tuple[tuple[int, datetime, Decimal], ...]
    provisional_cash: Decimal | None
    prior_cash: Decimal | None
    management_exit_events: tuple[ManagementExitEvent, ...]
    rebalance_events: tuple[RebalanceEvent, ...]
    scope: str = field(default=SCOPE, init=False)

    def __post_init__(self) -> None:
        if self.refusal is not None and any(
            x is not None for x in (self.cash, self.realized_equity, self.final_equity)
        ):
            raise ValueError("an unavailable run cannot expose valid monetary results")
        trade_ids = [t.signal_id for t in self.trades]
        disposition_ids = [d.signal_id for d in self.dispositions]
        if len(set(trade_ids)) != len(trade_ids) or len(set(disposition_ids)) != len(
            disposition_ids
        ):
            raise ValueError("timed signal accounting must be unique")
        accepted = {d.signal_id for d in self.dispositions if d.reason is Disposition.ACCEPTED}
        if accepted != set(trade_ids):
            raise ValueError("every accepted identity must have exactly one timed trade")

    @property
    def valid(self) -> bool:
        return self.refusal is None


@dataclass(slots=True)
class _Holding:
    signal_id: SignalId
    available: datetime
    intended: int
    entry: TimedLeg
    quantity: int
    remaining_charges: Charges
    stop: Decimal
    distance: Decimal
    target: Decimal | None
    timer: int | None
    activated: datetime
    latched: bool = False
    pending_exit: ManagementExitEvent | None = None
    exits: list[TimedLeg] = field(default_factory=list)

    def snapshot(self) -> TimedTrade:
        return TimedTrade(
            self.signal_id,
            self.available,
            self.intended,
            self.entry.quantity,
            self.entry,
            tuple(self.exits),
            self.quantity,
            self.remaining_charges,
        )


def _preflight(
    strategy: StrategyCandidate,
    panel: Panel,
    signals: Mapping[str, Column],
    stops: Mapping[str, Column],
    ranks: Mapping[str, Column] | None,
    fixture: TimedFixture,
    source: tuple[int, ...],
    risk: Risk | None,
    exit_signals: Mapping[str, Column] | None,
    rebalance_pulses: npt.NDArray[np.bool_] | None,
) -> RunRefusal | None:
    def refuse(reason: TimedRefusal, symbols: tuple[str, ...] = panel.symbols) -> RunRefusal:
        return RunRefusal(reason, symbols, source)

    if strategy.timeframe is not Timeframe.DAILY:
        return refuse(TimedRefusal.UNSUPPORTED_CLOCK)
    if strategy.universe != "nse_liquid":
        return refuse(TimedRefusal.UNSUPPORTED_UNIVERSE)
    if any(r.rule == "trailing_stop_atr" for r in strategy.exits):
        return refuse(TimedRefusal.UNSUPPORTED_TRAILING)
    if strategy.sizing.weighting != "equal_weight" or strategy.sizing.vol_target_pct is not None:
        return refuse(TimedRefusal.UNSUPPORTED_SIZING)
    if risk is not None and strategy.sizing.risk_r > risk.per_trade_risk_r:
        return refuse(TimedRefusal.EXCESS_RISK)
    ExitPlan.of(strategy.exits)
    validate_consumer_columns(strategy, panel, exit_signals, rebalance_pulses, source)
    if (
        len(source) != len(panel)
        or any(type(i) is not int or i < 0 for i in source)
        or any(b != a + 1 for a, b in pairwise(source))
    ):
        raise ValueError("source indices must be contiguous full-source panel coordinates")
    if (
        set(signals) != set(panel.symbols)
        or set(stops) != set(panel.symbols)
        or (ranks is not None and set(ranks) != set(panel.symbols))
    ):
        raise ValueError("columns must preserve the exact panel universe")
    for symbol in panel.symbols:
        for column in (
            signals[symbol],
            stops[symbol],
            *(() if ranks is None else (ranks[symbol],)),
        ):
            if column.shape != (len(panel),):
                raise ValueError("daily column shape mismatch")
        missing = tuple(source[i] for i, x in enumerate(signals[symbol]) if np.isnan(x))
        if missing and strategy.rebalance is None:
            return RunRefusal(TimedRefusal.UNAVAILABLE_SIGNAL, (symbol,), missing)
        if any(
            (not np.isnan(x) and not np.isfinite(x)) or (np.isfinite(x) and x not in (0, 1))
            for x in signals[symbol]
        ):
            raise ValueError("entry columns must be finite binary daily decisions")
        if (
            strategy.rebalance is not None
            and ranks is not None
            and any(np.isinf(x) for x in ranks[symbol])
        ):
            raise ValueError("rank columns cannot contain infinity")
    sessions = fixture.sessions
    if (
        len(sessions) != len(source)
        or tuple(s.index for s in sessions) != source
        or any(s.open_ts != _ts_at(panel, i) for i, s in enumerate(sessions))
        or any(b.open_ts <= a.close_ts for a, b in pairwise(sessions))
    ):
        return refuse(TimedRefusal.MISSING_REFINEMENT)
    if tuple(r.symbol for r in fixture.refinements) != panel.symbols:
        return refuse(TimedRefusal.MISSING_REFINEMENT)
    expected = tuple(
        (
            s.index,
            s.open_ts + k * timedelta(minutes=15),
            s.open_ts + (k + 1) * timedelta(minutes=15),
        )
        for s in sessions
        for k in range((s.close_ts - s.open_ts) // timedelta(minutes=15))
    )
    for i, r in enumerate(fixture.refinements):
        if tuple((b.session_index, b.bar.ts, b.end_ts) for b in r.bars) != expected:
            return refuse(TimedRefusal.MISSING_REFINEMENT, (r.symbol,))
        for local, session in enumerate(sessions):
            rows = tuple(b for b in r.bars if b.session_index == session.index)
            actual = (
                rows[0].bar.open,
                max(b.bar.high for b in rows),
                min(b.bar.low for b in rows),
                rows[-1].bar.close,
                sum((b.bar.volume for b in rows), Decimal(0)),
            )
            daily = panel.bars[i]
            wanted = tuple(
                Decimal(str(float(getattr(daily, name)[local])))
                for name in ("open", "high", "low", "close", "volume")
            )
            if actual != wanted:
                return refuse(TimedRefusal.AGGREGATION, (r.symbol,))
    if (
        any(s.source != fixture.source for s in sessions)
        or any(
            b.source != fixture.source
            or (b.opening is not None and b.opening.source != fixture.source)
            for r in fixture.refinements
            for b in r.bars
        )
        or (timed_fixture_digest(sessions, fixture.refinements) != fixture.source.sha256)
    ):
        return refuse(TimedRefusal.SOURCE_MISMATCH)
    return None


def run_timed(
    strategy: StrategyCandidate,
    panel: Panel,
    signals: Mapping[str, Column],
    stops: Mapping[str, Column],
    *,
    fixture: TimedFixture,
    source_indices: Sequence[int],
    fills: FillModel,
    costs: CostModel,
    notional: Decimal | None = None,
    risk: Risk | None = None,
    starting_equity: Decimal | None = None,
    exit_signals: Mapping[str, Column] | None = None,
    ranks: Mapping[str, Column] | None = None,
    rebalance_pulses: npt.NDArray[np.bool_] | None = None,
) -> TimedRun:
    """Serialize one common event loop; mode changes sizing/accounting, never execution."""
    mode = "portfolio" if risk is not None else "signal"
    if risk is not None:
        if starting_equity is None:
            raise ValueError("portfolio requires starting capital")
        _money(starting_equity)
    elif notional is None:
        raise ValueError("signal mode requires intended notional")
    else:
        _money(notional)
    source = tuple(source_indices)
    refusal = _preflight(
        strategy,
        panel,
        signals,
        stops,
        ranks,
        fixture,
        source,
        risk,
        exit_signals,
        rebalance_pulses,
    )
    plan = ExitPlan.of(strategy.exits)
    has_opposite = any(rule.rule == "opposite_signal" for rule in strategy.exits)
    config = fills.execution_config
    latency = timedelta(milliseconds=config.latency_ms)
    positions: dict[str, _Holding] = {}
    history: list[_Holding] = []
    attempts: list[TimedAttempt] = []
    decisions: dict[SignalId, Disposition | None] = (
        {}
        if strategy.rebalance is not None
        else {
            SignalId(strategy.name, strategy.version, s, _ts_at(panel, i), source[i]): None
            for i in range(len(panel))
            for s in panel.symbols
            if signals[s][i] == 1
        }
    )
    cash = realized = starting_equity if risk is not None else None
    prior_cash = cash
    marks: list[tuple[int, datetime, Decimal]] = []
    fees = DeliveryFeeContext()
    queued: list[tuple[SignalId, int, datetime]] = []
    management_events: list[ManagementExitEvent] = []
    rebalance_events: list[RebalanceEvent] = []
    completed_rebalances: set[int] = set()
    daily_by_source = {s: i for i, s in enumerate(source)}

    def failed() -> bool:
        return refusal is not None

    def fail(reason: TimedRefusal | ReplayRefusal, symbol: str, row: ReplayBar) -> None:
        nonlocal refusal
        refusal = RunRefusal(
            TimedRefusal(reason.value), (symbol,), (row.session_index,), row.bar.ts
        )

    def record_exit(
        symbol: str, row: ReplayBar, selection: Selection, *, opening: bool, used: dict[str, int]
    ) -> None:
        nonlocal cash, realized
        holding = positions[symbol]
        assert selection.cause is not None
        proxy = _proxy_refusal(row)
        if proxy is not None:
            fail(proxy, symbol, row)
            return
        holding.latched = holding.latched or selection.latched
        management = selection.cause in (
            ExitCause.OPPOSITE_SIGNAL,
            ExitCause.REBALANCE,
        )
        available = (
            holding.pending_exit.decision_ts
            if management and holding.pending_exit is not None
            else holding.available
        )
        intent = Intent(
            OrderSide.SELL, selection.kind, holding.quantity, available, selection.limit
        )
        fill = _fill(intent, row, fills, config, opening=opening, used=used[symbol])
        attempts.append(
            TimedAttempt(
                holding.signal_id, selection.cause, row.session_index, row.bar.ts, fill, opening
            )
        )
        if not fill.filled:
            return
        assert fill.price is not None
        recognized = row.bar.ts if opening else row.end_ts
        charge = fees.executed_sell_charges(
            costs,
            Segment.EQUITY_DELIVERY,
            fill.price,
            Decimal(fill.filled_quantity),
            symbol=symbol,
            executed_at=recognized,
            scope="timed-book" if risk is not None else holding.signal_id,
        )
        allocated = (
            holding.remaining_charges
            if fill.filled_quantity == holding.quantity
            else (
                scaled_charges(
                    holding.entry.charges,
                    Decimal(fill.filled_quantity) / Decimal(holding.entry.quantity),
                )
            )
        )
        holding.remaining_charges = charge_difference(holding.remaining_charges, allocated)
        timing = (
            Timing(Precision.EVENT_RESOLVED, row.bar.ts)
            if opening
            else Timing(Precision.BAR_RESOLVED, interval_start=row.bar.ts, interval_end=row.end_ts)
        )
        leg = TimedLeg(
            selection.cause,
            row.session_index,
            row.bar.ts,
            timing,
            recognized,
            fill.filled_quantity,
            fill.price,
            charge,
            allocated,
            "MODEL_OPEN_EVENT" if opening else "UNRESOLVED_BAR_INTERVAL",
        )
        holding.exits.append(leg)
        holding.quantity -= fill.filled_quantity
        used[symbol] += fill.filled_quantity
        if cash is not None and realized is not None:
            cash += fill.price * fill.filled_quantity - charge.total
            realized += (
                (fill.price - holding.entry.price) * fill.filled_quantity
                - allocated.total
                - charge.total
            )
        if not holding.quantity:
            del positions[symbol]

    for local, session in enumerate(fixture.sessions if refusal is None else ()):
        rows = {
            r.symbol: tuple(b for b in r.bars if b.session_index == session.index)
            for r in fixture.refinements
        }
        for bar_local in range(len(rows[panel.symbols[0]])):
            at = {s: rows[s][bar_local] for s in panel.symbols}
            used = {s: 0 for s in panel.symbols}
            exited: set[SignalId] = set()
            prior_cash = cash
            for symbol in tuple(sorted(positions)):
                h = positions[symbol]
                row = at[symbol]
                timer = h.timer is not None and session.index - h.entry.source_index + 1 >= h.timer
                selected = select_open(
                    row, h.stop, latched=h.latched, activated=h.activated, timer_due=timer
                )
                if (
                    selected.cause is None
                    and h.pending_exit is not None
                    and session.index >= h.pending_exit.first_execution_index
                    and row.bar.ts >= h.pending_exit.decision_ts + latency
                ):
                    selected = Selection(ExitCause(h.pending_exit.reason.value))
                if selected.cause is not None:
                    exited.add(h.signal_id)
                    record_exit(symbol, row, selected, opening=True, used=used)
                if failed():
                    break
            if failed():
                break
            eligible = [
                q
                for q in queued
                if source[local] == q[0].decision_index + 1
                and session.open_ts + bar_local * timedelta(minutes=15) >= q[2] + latency
            ]
            for q in eligible:
                queued.remove(q)
            candidates = []
            for q in eligible:
                signal, decision_local, _ = q
                if not panel.tradable[panel.index_of(signal.symbol), decision_local]:
                    decisions[signal] = Disposition.NOT_TRADABLE
                elif signal.symbol in positions:
                    decisions[signal] = Disposition.ALREADY_HELD
                else:
                    candidates.append(q)
            eligible = candidates
            free_slots = None if risk is None else risk.max_open_positions - len(positions)
            if ranks is not None and free_slots is not None and len(eligible) > free_slots > 0:
                eligible.sort(
                    key=lambda q: (
                        -float(ranks[q[0].symbol][q[1]])
                        if np.isfinite(ranks[q[0].symbol][q[1]])
                        else float("inf"),
                        q[0].symbol,
                    )
                )
            for signal, decision_local, available in eligible:
                symbol, row = signal.symbol, at[signal.symbol]
                reason = None
                raw_distance = stops[symbol][decision_local]
                if risk is not None and len(positions) >= risk.max_open_positions:
                    reason = Disposition.NO_SLOT
                elif not np.isfinite(raw_distance) or raw_distance <= 0:
                    reason = Disposition.NO_STOP_DISTANCE
                if reason is not None:
                    decisions[signal] = reason
                    continue
                proxy = _proxy_refusal(row)
                if proxy is not None:
                    fail(proxy, symbol, row)
                    break
                distance = Decimal(str(float(raw_distance)))
                price = fills.marketable_price(row.bar.open, side=OrderSide.BUY)
                if price - distance <= 0:
                    decisions[signal] = Disposition.NO_STOP_DISTANCE
                    continue
                if risk is None:
                    assert notional is not None
                    quantity = whole_shares(notional, price)
                else:
                    assert realized is not None
                    quantity = whole_shares(
                        Decimal(str(strategy.sizing.risk_r)) * realized, distance
                    )
                    if quantity <= 0:
                        decisions[signal] = Disposition.ROUNDS_TO_ZERO
                        continue
                    affordable = whole_shares(
                        Decimal(str(risk.max_position_pct_of_equity)) * realized, price
                    )
                    if affordable <= 0:
                        decisions[signal] = Disposition.CONCENTRATION_CAP
                        continue
                    quantity = min(quantity, affordable)
                    if (
                        sum((h.distance * h.quantity for h in positions.values()), Decimal(0))
                        + (quantity * distance)
                        > Decimal(str(risk.max_portfolio_heat)) * realized
                    ):
                        decisions[signal] = Disposition.HEAT_CAP
                        continue
                if quantity <= 0:
                    decisions[signal] = Disposition.ROUNDS_TO_ZERO
                    continue
                fill = _fill(
                    Intent(OrderSide.BUY, OrderKind.MARKETABLE_LIMIT, quantity, available),
                    row,
                    fills,
                    config,
                    opening=True,
                    used=used[symbol],
                )
                attempts.append(
                    TimedAttempt(signal, ExitCause.ENTRY, session.index, row.bar.ts, fill, True)
                )
                if not fill.filled:
                    decisions[signal] = Disposition.ENTRY_NOT_FILLED
                    continue
                assert fill.price is not None
                charge = costs.charges(
                    Segment.EQUITY_DELIVERY,
                    OrderSide.BUY,
                    fill.price,
                    Decimal(fill.filled_quantity),
                )
                if risk is not None:
                    assert cash is not None and realized is not None
                    outlay = entry_outlay(fill.price, fill.filled_quantity, charge)
                    if outlay > cash:
                        decisions[signal] = Disposition.INSUFFICIENT_CASH
                        continue
                    cash -= outlay
                    assert cash >= 0 and len(positions) < risk.max_open_positions
                    assert fill.price * fill.filled_quantity <= (
                        Decimal(str(risk.max_position_pct_of_equity)) * realized
                    )
                leg = TimedLeg(
                    ExitCause.ENTRY,
                    session.index,
                    row.bar.ts,
                    Timing(Precision.EVENT_RESOLVED, row.bar.ts),
                    row.bar.ts,
                    fill.filled_quantity,
                    fill.price,
                    charge,
                    None,
                    "MODEL_OPEN_EVENT",
                )
                h = _Holding(
                    signal,
                    available,
                    quantity,
                    leg,
                    fill.filled_quantity,
                    charge,
                    fill.price - distance,
                    distance,
                    plan.target_for(fill.price, distance),
                    plan.time_stop_bars,
                    row.bar.ts + latency,
                )
                positions[symbol] = h
                history.append(h)
                used[symbol] += fill.filled_quantity
                decisions[signal] = Disposition.ACCEPTED
                if risk is not None:
                    assert realized is not None
                    assert sum(
                        (p.distance * p.quantity for p in positions.values()), Decimal(0)
                    ) <= (Decimal(str(risk.max_portfolio_heat)) * realized)
            if failed():
                break
            # Reconcile the complete opening batch only after every causal admission decision.
            for symbol in panel.symbols:
                if used[symbol] > _cap(at[symbol].bar.volume, config):
                    fail(TimedRefusal.LIQUIDITY_UNAVAILABLE, symbol, at[symbol])
                    break
            if failed():
                break
            for event_at, event in enumerate(rebalance_events):
                if (
                    event.decision_index in completed_rebalances
                    or event.first_execution_index != session.index
                ):
                    continue
                if event.pending_admissions and not all(
                    any(
                        identity.symbol == symbol
                        and identity.decision_index == event.decision_index
                        and outcome is not None
                        for identity, outcome in decisions.items()
                    )
                    for symbol in event.pending_admissions
                ):
                    continue
                rebalance_events[event_at] = replace(
                    event,
                    holdings_after=tuple(sorted(positions)),
                    pending_admissions=tuple(
                        symbol
                        for symbol in event.pending_admissions
                        if not any(
                            identity.symbol == symbol
                            and identity.decision_index == event.decision_index
                            and outcome is Disposition.ACCEPTED
                            for identity, outcome in decisions.items()
                        )
                    ),
                )
                completed_rebalances.add(event.decision_index)
            for symbol in tuple(sorted(positions)):
                h = positions[symbol]
                if h.signal_id in exited:
                    continue
                selected = select_end(at[symbol], h.stop, h.target, activated=h.activated)
                if selected.refusal is not None:
                    fail(selected.refusal, symbol, at[symbol])
                    break
                if selected.cause is not None:
                    record_exit(symbol, at[symbol], selected, opening=False, used=used)
                if failed():
                    break
            if failed():
                break
        if failed():
            break
        if cash is not None:
            equity = cash + sum(
                (
                    Decimal(str(float(panel.bars[panel.index_of(s)].close[local]))) * h.quantity
                    for s, h in positions.items()
                ),
                Decimal(0),
            )
            marks.append((session.index, session.close_ts, equity))
        if strategy.rebalance is None:
            for signal in decisions:
                if signal.decision_index == session.index:
                    if local + 1 == len(source):
                        decisions[signal] = Disposition.NO_NEXT_SESSION
                    else:
                        queued.append((signal, daily_by_source[session.index], session.close_ts))
        if has_opposite and exit_signals is not None:
            for symbol, holding in tuple(positions.items()):
                value = exit_signals[symbol][local]
                if np.isnan(value):
                    refusal = RunRefusal(
                        TimedRefusal.MISSING_MANAGEMENT_DECISION,
                        (symbol,),
                        (session.index,),
                        session.close_ts,
                    )
                    break
                if value == 1 and holding.pending_exit is None:
                    pending = ManagementExitEvent(
                        symbol,
                        session.close_ts,
                        session.index,
                        session.index + 1,
                        ExitReason.OPPOSITE_SIGNAL,
                    )
                    holding.pending_exit = pending
                    management_events.append(pending)
        if failed():
            break
        if (
            refusal is None
            and strategy.rebalance is not None
            and rebalance_pulses is not None
            and rebalance_pulses[local]
        ):
            event = rebalance_decision(
                strategy,
                panel,
                signals,
                ranks,
                local,
                session.index,
                tuple(positions),
                tuple(symbol for symbol, h in positions.items() if h.pending_exit is not None),
            )
            event = replace(event, decision_ts=session.close_ts)
            rebalance_events.append(event)
            if event.status is RebalanceStatus.VALID:
                for symbol, holding in positions.items():
                    if symbol not in event.candidates and holding.pending_exit is None:
                        pending = ManagementExitEvent(
                            symbol,
                            session.close_ts,
                            session.index,
                            session.index + 1,
                            ExitReason.REBALANCE,
                        )
                        holding.pending_exit = pending
                        management_events.append(pending)
                for symbol in event.retained:
                    identity = SignalId(
                        strategy.name, strategy.version, symbol, session.open_ts, session.index
                    )
                    decisions[identity] = Disposition.ALREADY_HELD
                for symbol in event.pending_admissions:
                    identity = SignalId(
                        strategy.name, strategy.version, symbol, session.open_ts, session.index
                    )
                    decisions[identity] = None
                    if local + 1 == len(source):
                        decisions[identity] = Disposition.NO_NEXT_SESSION
                    else:
                        queued.append((identity, local, session.close_ts))
        for q in tuple(queued):
            if q[0].decision_index + 1 <= session.index:
                decisions[q[0]] = Disposition.NO_NEXT_SESSION
                queued.remove(q)
    outcomes = tuple(
        SignalDisposition(s, r if r is not None else Disposition.UNAVAILABLE)
        for s, r in decisions.items()
    )
    return TimedRun(
        mode,
        panel.symbols,
        source,
        tuple(h.snapshot() for h in history),
        outcomes,
        tuple(attempts),
        refusal,
        cash if refusal is None else None,
        realized if refusal is None else None,
        marks[-1][2] if marks and refusal is None else None,
        tuple(marks),
        cash if refusal is not None else None,
        prior_cash,
        tuple(management_events),
        tuple(rebalance_events),
    )
