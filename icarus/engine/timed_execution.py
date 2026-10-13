"""Shared causal execution steps. FillModel owns every price and queue decision."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import StrEnum

from icarus.common.config import ExecutionRealism
from icarus.engine.fills import FillModel, FillResult, Intent, NoFillReason, OrderKind
from icarus.engine.timing import ReplayBar


@dataclass(frozen=True, slots=True)
class Selection:
    cause: ExitCause | None = None
    kind: OrderKind = OrderKind.MARKETABLE_LIMIT
    limit: Decimal | None = None
    latched: bool = False
    refusal: ReplayRefusal | None = None


def select_open(
    row: ReplayBar, stop: Decimal, *, latched: bool, activated: datetime, timer_due: bool
) -> Selection:
    """Only pre-open state and the opening price select an opening exit."""
    if row.bar.ts < activated:
        return Selection()
    if latched:
        return Selection(ExitCause.STOP, latched=True)
    if row.bar.open <= stop:
        return Selection(ExitCause.STOP, OrderKind.STOP, stop, True)
    if timer_due:
        return Selection(ExitCause.TIME_STOP)
    return Selection()


def select_end(
    row: ReplayBar, stop: Decimal, target: Decimal | None, *, activated: datetime
) -> Selection:
    """A candle supplies an interval, never an invented trigger sequence."""
    hit_stop = row.bar.low <= stop
    hit_target = target is not None and row.bar.high > target
    if row.bar.ts < activated:
        return (
            Selection(refusal=ReplayRefusal.PATH_ORDER_UNAVAILABLE)
            if (hit_stop or hit_target)
            else Selection()
        )
    if hit_stop and hit_target:
        return Selection(refusal=ReplayRefusal.ORDER_UNAVAILABLE)
    if hit_stop:
        return Selection(ExitCause.STOP, OrderKind.STOP, stop, True)
    if hit_target:
        return Selection(ExitCause.TARGET, OrderKind.RESTING_LIMIT, target)
    return Selection()


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


class ExitCause(StrEnum):
    ENTRY = "entry"
    STOP = "stop"
    TARGET = "target"
    TIME_STOP = "time_stop"
    OPPOSITE_SIGNAL = "opposite_signal"
    REBALANCE = "rebalance"


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
    intent: Intent,
    row: ReplayBar,
    model: FillModel,
    execution: ExecutionRealism,
    *,
    opening: bool,
    used: int = 0,
) -> FillResult:
    assert row.opening is not None
    raw = model.execute(
        intent, replace(row.bar, volume=row.opening.quantity) if opening else row.bar
    )
    allowance = _cap(row.opening.quantity, execution)
    if not opening:
        allowance = min(allowance, _cap(row.bar.volume, execution))
    allowance = max(0, allowance - used)
    if raw.filled and (
        allowance <= 0 or (not execution.model_partial_fills and allowance < intent.quantity)
    ):
        return FillResult(0, intent.quantity, None, NoFillReason.TOO_LARGE_FOR_BAR, None)
    if raw.filled and raw.filled_quantity > allowance:
        return FillResult(allowance, intent.quantity, raw.price, None, raw.ts)
    return raw
