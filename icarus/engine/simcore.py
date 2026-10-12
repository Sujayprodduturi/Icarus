"""Pure exit mechanics shared by portfolio and signal simulators.

The two simulators must use one exit ladder or their comparison measures code drift rather than
portfolio constraints.  This module owns only that shared, mode-agnostic behavior; book accounting
and write-off policy remain with each simulator.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Protocol
from uuid import NAMESPACE_URL, UUID, uuid5

import numpy as np

from icarus.common.types import OrderSide
from icarus.engine.fills import Intent, OrderKind, SimBar

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    import numpy.typing as npt

    from icarus.strategy.dsl import ExitRule, Panel, StrategyCandidate

    Column = npt.NDArray[np.float64]


class ExitReason(enum.StrEnum):
    """Why a position closed. Kept because "what killed this strategy" is the first question the
    metric sheet has to answer, and a bare P&L cannot say."""

    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit"
    TIME_STOP = "time_stop"
    OPPOSITE_SIGNAL = "opposite_signal"
    REBALANCE = "rebalance"
    END_OF_DATA = "end_of_data"
    STALE_MARK = "stale_mark"
    """The symbol stopped printing bars while the position was open, so it was written off at the
    last price it ever traded at (finding F4).

    A separate reason rather than folding into ``END_OF_DATA`` because these two are not equally
    trustworthy. An ``END_OF_DATA`` exit happened against a real bar at a price somebody quoted; a
    ``STALE_MARK`` exit is an **assumption** — nobody was there to sell to. Blending them would put
    a made-up price into the same column as a measured one, and the metric sheet could not tell the
    operator how much of the P&L rests on the made-up half."""


@dataclass(frozen=True, slots=True)
class SignalId:
    """Stable identity of one emitted entry signal in full-source coordinates.

    A fold-local index, run identifier, simulator mode, and notional are deliberately absent: the
    same market decision must join to the same observation wherever it is viewed.  UUID v5 makes
    that identity portable without replacing the typed provenance fields that explain it.
    """

    strategy_id: str
    strategy_version: int
    symbol: str
    decision_ts: datetime
    decision_index: int
    uuid: UUID = field(init=False)

    def __post_init__(self) -> None:
        for name, value in (
            ("strategy_id", self.strategy_id),
            ("symbol", self.symbol),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"SignalId.{name} must be a nonempty string")
        if type(self.strategy_version) is not int or self.strategy_version <= 0:
            raise ValueError("SignalId.strategy_version must be a positive whole number")
        if not isinstance(self.decision_ts, datetime):
            raise TypeError("SignalId.decision_ts must be a datetime")
        if self.decision_ts.tzinfo is not UTC:
            raise ValueError("SignalId.decision_ts must use datetime.UTC")
        if type(self.decision_index) is not int or self.decision_index < 0:
            raise ValueError("SignalId.decision_index must be a nonnegative whole index")

        canonical = json.dumps(
            [
                self.strategy_id,
                self.strategy_version,
                self.symbol,
                self.decision_ts.astimezone(UTC).isoformat(timespec="microseconds"),
                self.decision_index,
            ],
            ensure_ascii=True,
            separators=(",", ":"),
        )
        object.__setattr__(self, "uuid", uuid5(NAMESPACE_URL, f"icarus:signal:{canonical}"))


@dataclass(frozen=True, slots=True)
class ManagementExitEvent:
    symbol: str
    decision_ts: datetime
    decision_index: int
    first_execution_index: int
    reason: ExitReason


def management_intent(
    pending: ManagementExitEvent | None, quantity: int, ts: datetime, source_index: int
) -> tuple[Intent | None, ExitReason | None]:
    if pending is None or source_index < pending.first_execution_index or ts <= pending.decision_ts:
        return None, None
    return Intent(
        OrderSide.SELL, OrderKind.MARKETABLE_LIMIT, quantity, pending.decision_ts
    ), pending.reason


class AdmissionRefusal(enum.StrEnum):
    EXECUTION_ORDER_UNAVAILABLE = "execution_order_unavailable"


class RebalanceStatus(enum.StrEnum):
    VALID = "valid"
    COHORT_UNAVAILABLE = "cohort_unavailable"
    CARDINALITY_MISMATCH = "cardinality_mismatch"


@dataclass(frozen=True, slots=True)
class RebalanceEvent:
    decision_ts: datetime
    decision_index: int
    first_execution_index: int
    status: RebalanceStatus
    candidates: tuple[str, ...] = ()
    retained: tuple[str, ...] = ()
    holdings_after: tuple[str, ...] = ()
    pending_admissions: tuple[str, ...] = ()
    admission_refusal: AdmissionRefusal | None = None


def rebalance_decision(
    strategy: StrategyCandidate,
    panel: Panel,
    signals: Mapping[str, Column],
    ranks: Mapping[str, Column] | None,
    local: int,
    source_index: int,
    holdings: Sequence[str],
    pending_symbols: Sequence[str] = (),
) -> RebalanceEvent:
    from icarus.strategy.dsl import Call

    if not isinstance(strategy.entry, Call) or "n" not in strategy.entry.literals:
        raise ValueError("rebalance requires a cross-sectional fixed-count entry")
    count = int(strategy.entry.literals["n"])
    minimum = int(strategy.entry.literals["min_symbols"])
    eligible = [
        s
        for s in panel.symbols
        if panel.tradable[panel.index_of(s), local]
        and np.isfinite(signals[s][local])
        and ranks is not None
        and np.isfinite(ranks[s][local])
    ]
    selected = tuple(s for s in eligible if signals[s][local] == 1.0)
    status = (
        RebalanceStatus.COHORT_UNAVAILABLE
        if len(eligible) < minimum
        else RebalanceStatus.CARDINALITY_MISMATCH
        if len(selected) != count
        else RebalanceStatus.VALID
    )
    target = selected if status is RebalanceStatus.VALID else ()
    return RebalanceEvent(
        _ts_at(panel, local),
        source_index,
        source_index + 1,
        status,
        target,
        tuple(sorted((set(holdings) & set(target)) - set(pending_symbols))),
        tuple(sorted(holdings)),
        tuple(s for s in target if s not in holdings),
    )


def rebalance_grid(
    strategy: StrategyCandidate, source: Sequence[int]
) -> npt.NDArray[np.bool_] | None:
    from icarus.engine.backtest import longest_lookback

    if strategy.rebalance is None:
        return None
    lookback = longest_lookback(strategy)
    return np.array(
        [index >= lookback and index % strategy.rebalance.every_sessions == 0 for index in source],
        dtype=np.bool_,
    )


def validate_consumer_columns(
    strategy: StrategyCandidate,
    panel: Panel,
    exit_signals: Mapping[str, Column] | None,
    pulses: npt.NDArray[np.bool_] | None,
    source: Sequence[int],
) -> None:
    if any(rule.rule == "opposite_signal" and rule.event is None for rule in strategy.exits):
        raise ValueError("opposite_signal requires a declared event")
    if any(rule.rule == "opposite_signal" for rule in strategy.exits) and exit_signals is None:
        raise ValueError("opposite_signal requires evaluated exit columns")
    if exit_signals is not None:
        if set(exit_signals) != set(panel.symbols):
            raise ValueError("exit signals must exactly match panel symbols")
        for column in exit_signals.values():
            if np.asarray(column).shape != (len(panel),) or not np.all(
                np.isnan(column) | (column == 0) | (column == 1)
            ):
                raise ValueError("exit signals must be aligned 0/1/NaN columns")
    if strategy.rebalance is not None and pulses is None:
        raise ValueError("rebalance requires whole-source pulse columns")
    if pulses is not None and (
        np.asarray(pulses).shape != (len(panel),) or pulses.dtype != np.bool_
    ):
        raise ValueError("rebalance pulses must be aligned boolean columns")
    expected = rebalance_grid(strategy, source)
    if expected is not None and (pulses is None or not np.array_equal(pulses, expected)):
        raise ValueError("rebalance pulses must match the declared whole-source grid")


class _ExitPosition(Protocol):
    """Only the mutable position state the shared exit ladder is allowed to depend on."""

    quantity: int
    entry_price: Decimal
    decided_at: datetime
    stop_price: Decimal
    take_profit: Decimal | None
    time_stop_bars: int | None
    trailing: bool
    bars_held: int
    peak_close: Decimal


def _dec(value: float) -> Decimal:
    """Bars are float64 because whole-series arithmetic wants that; money is Decimal.

    ``str`` rather than ``Decimal(float)`` on purpose: the latter carries the full binary
    expansion, so a price of 100.1 becomes 100.099999999999994315658…, and that difference
    reappears as a paisa the contract note disagrees about.
    """
    return Decimal(str(value))


def _ts_at(panel: Panel, t: int) -> datetime:
    """Bar ``t``'s timestamp as a tz-aware UTC datetime."""
    naive: datetime = panel.ts[t].astype("datetime64[us]").item()
    return naive.replace(tzinfo=UTC)


def _sim_bar(panel: Panel, index: int, t: int, ts: datetime) -> SimBar | None:
    """One bar in the money type, or ``None`` where the symbol had no session."""
    bars = panel.bars[index]
    values = (bars.open[t], bars.high[t], bars.low[t], bars.close[t], bars.volume[t])
    if not all(np.isfinite(v) for v in values):
        return None
    price = [_dec(float(v)) for v in values]
    return SimBar(
        ts=ts, open=price[0], high=price[1], low=price[2], close=price[3], volume=price[4]
    )


def _last_traded_close(panel: Panel, index: int, t: int) -> tuple[Decimal, int]:
    """The most recent finite close at or before ``t``, plus its local bar index."""
    finite = np.flatnonzero(np.isfinite(panel.bars[index].close[: t + 1]))
    if finite.size == 0:
        raise ValueError(
            f"cannot write off {panel.symbols[index]}: it has printed no close at or before bar "
            f"{t}, so the book holds a position that could not have been opened"
        )
    at = int(finite[-1])
    return _dec(float(panel.bars[index].close[at])), at


def _exit_intent(
    position: _ExitPosition, bar: SimBar, ts: datetime, *, final: bool
) -> tuple[Intent | None, ExitReason | None]:
    """The first exit that applies, checked worst-case first.

    Order matters and is deliberately pessimistic: when a bar's range spans both the stop and
    the target, daily data cannot say which came first, so the **stop** is taken. Choosing the
    target instead would hand the strategy the good half of every ambiguous bar, which is the
    touch-equals-fill bias arriving through the exit door.

    **Every exit is dated to the bar that decided the entry, not to today and not to the fill
    bar**, and the distinction is load-bearing. A protective stop is a *resting order sitting
    at the broker* — invariant #16 requires every open position to carry one — so it was
    decided at the same moment the entry was, one session before the fill. Next-bar execution
    constrains *decisions*, not the intra-bar triggering of an order already resting.

    Dating exits to the current bar would force the engine to wait a day before honouring its
    own stop, inventing a day of unprotected loss. Dating them to ``entry_ts`` — the fill bar —
    was the original mistake: it made a stop unable to execute on the very session the position
    opened, so a trade that gapped through its stop on day one could never be stopped out. That
    is a real outcome, and always a loss, so suppressing it flattered every result. ``ts`` is
    still passed so the caller's bar is available; it is deliberately not the decision time.
    """
    decided = position.decided_at
    if final:
        return (
            Intent(OrderSide.SELL, OrderKind.MARKETABLE_LIMIT, position.quantity, decided),
            ExitReason.END_OF_DATA,
        )
    if bar.low <= position.stop_price:
        reason = (
            ExitReason.TRAILING_STOP
            if position.stop_price > position.entry_price
            else ExitReason.STOP_LOSS
        )
        return (
            Intent(
                OrderSide.SELL,
                OrderKind.STOP,
                position.quantity,
                decided,
                limit_price=position.stop_price,
            ),
            reason,
        )
    if position.take_profit is not None and bar.high > position.take_profit:
        return (
            Intent(
                OrderSide.SELL,
                OrderKind.RESTING_LIMIT,
                position.quantity,
                decided,
                limit_price=position.take_profit,
            ),
            ExitReason.TAKE_PROFIT,
        )
    if position.time_stop_bars is not None and position.bars_held >= position.time_stop_bars:
        # A time stop is a decision, not a resting order — the strategy chose in advance to be
        # out after N bars, and the exit is a market-hours order at the next opportunity. It is
        # checked last because both price exits would have triggered intra-bar, before the
        # close that makes the bar count tick over.
        return (
            Intent(OrderSide.SELL, OrderKind.MARKETABLE_LIMIT, position.quantity, decided),
            ExitReason.TIME_STOP,
        )
    return None, None


def admission_order_unavailable(
    position: _ExitPosition, bar: SimBar | None, *, final: bool
) -> bool:
    """Refuse using a whole-bar release to fund a queued fill at that bar's open.

    Inspect pre-bar state, before close/ATR trailing updates or fills. Already-decided marketable
    exits and genuine gap stops may release capacity through real fills. An intrabar stop/target,
    an unavailable bar, or a close-dependent trail cannot establish opening capacity.
    """
    if bar is None or position.trailing:
        return True
    if final:
        return False
    if bar.low <= position.stop_price:
        return bar.open > position.stop_price
    return position.take_profit is not None and bar.high > position.take_profit


def _trail_stop(position: _ExitPosition, distance: float) -> None:
    """Ratchet a trailing stop up behind the peak close. It never moves down.

    ``distance`` is the same per-share stop distance column the position was sized from, so
    the trail and the original stop are one number and cannot drift apart.

    A stop that could loosen is not a stop. Letting it fall back as volatility rose would make
    an already-protected position unprotected again, and the risk the trade was sized on would
    stop describing the loss it can actually take.
    """
    if not position.trailing or not np.isfinite(distance) or distance <= 0:
        return
    candidate = position.peak_close - _dec(distance)
    if candidate > position.stop_price:
        position.stop_price = candidate


@dataclass(frozen=True, slots=True)
class ExitPlan:
    """Every exit rule a strategy declared, resolved into what the simulator must actually do.

    **This exists because the simulator used to honour one rule out of six and say nothing.**
    ``take_profit_r``, ``take_profit_pct`` and ``time_stop`` parsed, validated, and were then
    dropped on the floor; ``trailing_stop_atr`` was installed as a *fixed* stop that never
    trailed. So a strategy file declaring a 3R target and a 20-bar time stop was simulated as
    buy-and-hold-until-stopped — a materially different strategy from the one pre-registered, and
    invariant #25 is worth nothing if the artefact and the thing measured are not the same.

    :meth:`of` therefore **refuses** any rule it does not implement rather than ignoring it. A new
    exit word added to the DSL now breaks the backtest loudly instead of quietly changing what a
    strategy means.
    """

    take_profit_r: float | None = None
    take_profit_pct: float | None = None
    time_stop_bars: int | None = None
    trailing: bool = False

    @classmethod
    def of(cls, exits: Sequence[ExitRule]) -> ExitPlan:
        known = {"stop_loss_atr", "stop_loss_pct", "trailing_stop_atr", "opposite_signal"}
        plan = cls()
        for rule in exits:
            if rule.rule in known:
                plan = replace(plan, trailing=plan.trailing or rule.rule == "trailing_stop_atr")
            elif rule.rule == "take_profit_r":
                plan = replace(plan, take_profit_r=float(rule.literals["r_multiple"]))
            elif rule.rule == "take_profit_pct":
                plan = replace(plan, take_profit_pct=float(rule.literals["pct"]))
            elif rule.rule == "time_stop":
                plan = replace(plan, time_stop_bars=int(rule.literals["bars"]))
            else:
                raise ValueError(
                    f"the portfolio simulator cannot honour the exit rule {rule.rule!r}. It parses "
                    f"in the DSL but nothing here implements it, so a strategy declaring it would "
                    f"be simulated as a different strategy than the one written down. Implement it "
                    f"or remove it from EXIT_RULES — never run past it."
                )
        return plan

    def target_for(self, entry_price: Decimal, risk_per_share: Decimal) -> Decimal | None:
        """The take-profit level, or ``None``. The **nearer** target wins if both are declared."""
        levels = [
            entry_price + _dec(self.take_profit_r) * risk_per_share
            if self.take_profit_r is not None
            else None,
            entry_price * (Decimal(1) + _dec(self.take_profit_pct))
            if self.take_profit_pct is not None
            else None,
        ]
        present = [level for level in levels if level is not None]
        return min(present) if present else None


def stop_distance_from_exits(exits: Sequence[ExitRule], *, atr: Column, close: Column) -> Column:
    """Rupees of risk per share, from whichever protective exit the strategy declared.

    Derived from the strategy rather than configured, because the stop *is* the risk unit: position
    size is the risk budget divided by this number, so a simulator using its own stop would size
    every position for a trade the strategy never described.
    """
    for rule in exits:
        if rule.rule == "stop_loss_atr":
            return float(rule.literals["atr_mult"]) * atr
        if rule.rule == "trailing_stop_atr":
            return float(rule.literals["atr_mult"]) * atr
        if rule.rule == "stop_loss_pct":
            return float(rule.literals["pct"]) * close
    raise ValueError(
        "strategy declares no protective exit — the DSL rejects that at parse time, so reaching "
        "here means an unvalidated candidate was handed to the simulator"
    )


__all__ = [
    "ExitPlan",
    "ExitReason",
    "SignalId",
    "_last_traded_close",
    "_sim_bar",
    "_ts_at",
    "stop_distance_from_exits",
]
