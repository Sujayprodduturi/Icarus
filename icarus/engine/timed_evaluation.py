"""Seven-card timed evaluation behind the counted-trial reservation barrier."""

from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from icarus.common.config import LOCKBOX_START, GoalConfig
from icarus.engine.backtest import Window, slice_panel
from icarus.engine.benchmark_match import (
    BenchmarkObservation,
    ExitFragment,
    FixtureIdentity,
    FragmentStatus,
    MatchingPolicy,
    ObservationIndex,
    ObservationState,
    SyntheticTrade,
    Timing,
    match_benchmark,
)
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.runner import evaluate_once
from icarus.engine.signaltest import SignalSimulator
from icarus.engine.source_pair import BoundPairQualification, daily_projection_digest
from icarus.engine.timed_runner import (
    AssembledTimedInputs,
    EvaluationOutcome,
    EvaluationPlan,
)
from icarus.engine.timed_simulation import (
    Refinement,
    TimedFixture,
    TimedFixtureIndex,
    TimedRun,
    TimedTrade,
    index_timed_fixture,
    timed_fixture_digest,
)
from icarus.state.trial_ledger import EvaluationReservation, TrialKind
from icarus.strategy.dsl import StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry

CAPITALS = (100_000, 1_000_000)


@dataclass(frozen=True, slots=True)
class StrategySpec:
    path: Path
    sha256: str
    candidate: StrategyCandidate


@dataclass(frozen=True, slots=True)
class EvaluationClock:
    source_indices: tuple[int, ...]
    open_times: tuple[datetime, ...]

    def __post_init__(self) -> None:
        if (
            not self.source_indices
            or len(self.source_indices) != len(self.open_times)
            or any(
                b != a + 1
                for a, b in zip(self.source_indices, self.source_indices[1:], strict=False)
            )
            or any(value.tzinfo is not UTC for value in self.open_times)
            or any(b <= a for a, b in zip(self.open_times, self.open_times[1:], strict=False))
        ):
            raise ValueError("evaluation clock must be a contiguous ordered UTC session axis")


@dataclass(slots=True)
class CataloguePayload:
    assembled: AssembledTimedInputs
    card_identity: tuple[tuple[str, str], ...]
    timed_index: TimedFixtureIndex
    benchmark_index: ObservationIndex
    benchmark_identity: FixtureIdentity
    _columns: dict[str, object] = field(default_factory=dict, repr=False)
    _fixtures: dict[tuple[int, int], TimedFixture] = field(default_factory=dict, repr=False)
    column_evaluations: int = 0

    @classmethod
    def from_assembled(
        cls, assembled: AssembledTimedInputs, cards: tuple[StrategySpec, ...]
    ) -> CataloguePayload:
        if not isinstance(assembled, AssembledTimedInputs):
            raise TypeError("assembled input must be typed")
        fixture = assembled.fixture
        expected_fixture_digest = timed_fixture_digest(
            fixture.sessions,
            fixture.refinements,
            fixture.inactive,
            None
            if fixture.pair_qualification is None
            else fixture.pair_qualification.qualification.document_sha256,
        )
        if fixture.source.sha256 != expected_fixture_digest:
            raise ValueError("fixture source digest does not bind inactive cells and rows")
        source = assembled.nifty_source
        if source is None:
            raise ValueError("Nifty observations require an explicit pinned source declaration")
        if any(item.revision != source.version for item in assembled.nifty):
            raise ValueError("Nifty observation revision differs from its pinned source")
        identity = FixtureIdentity(
            "NIFTY 50",
            source.version,
            "PRICE_INDEX",
            source.artifact_id,
            source.sha256,
        )
        rows = tuple(
            BenchmarkObservation(
                identity,
                item.record_id,
                item.event_ts,
                item.available_ts,
                item.price,
                ObservationState.OBSERVED if item.observed else ObservationState.STALE,
            )
            for item in assembled.nifty
        )
        return cls(
            assembled,
            tuple((item.candidate.name, item.sha256) for item in cards),
            index_timed_fixture(assembled.fixture),
            ObservationIndex(rows),
            identity,
        )


def load_strategy_catalogue(paths: tuple[Path, ...], goal: GoalConfig) -> tuple[StrategySpec, ...]:
    if type(paths) is not tuple or len(paths) not in (1, 7) or len(set(paths)) != len(paths):
        raise ValueError(
            "catalogue must contain one test card or the seven unique production cards"
        )
    registry = default_registry()
    values: list[StrategySpec] = []
    for path in paths:
        before = _stable_card_bytes(path)
        candidate = parse_strategy(
            before.decode("utf-8"), registry=registry, max_risk_r=goal.risk.per_trade_risk_r
        )
        values.append(StrategySpec(path, hashlib.sha256(before).hexdigest(), candidate))
    if len({item.candidate.name for item in values}) != len(values):
        raise ValueError("strategy names must be unique")
    return tuple(values)


def _stable_card_bytes(path: Path) -> bytes:
    try:
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("strategy card must be a regular file")
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            value = handle.read(1_000_001)
            after_open = os.fstat(handle.fileno())
        after = path.stat()
    except OSError as exc:
        raise ValueError("strategy card cannot be captured") from exc

    def identity(item: os.stat_result) -> tuple[int, int, int, int]:
        return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns

    if (
        len(value) > 1_000_000
        or not stat.S_ISREG(opened.st_mode)
        or identity(before) != identity(opened)
        or identity(opened) != identity(after_open)
        or identity(after_open) != identity(after)
    ):
        raise ValueError("strategy card bytes changed or exceed the bounded schema")
    return value


def _clock_windows(clock: EvaluationClock, goal: GoalConfig) -> tuple[Window, ...]:
    dates = tuple(value.date() for value in clock.open_times)
    if any(day >= LOCKBOX_START for day in dates):
        raise ValueError("whole source clock reaches lockbox")
    development = tuple(
        i
        for i, day in enumerate(dates)
        if goal.data_split.walk_forward_start <= day <= goal.data_split.walk_forward_end
    )
    if not development:
        raise ValueError("clock contains no walk-forward sessions")
    train = int(goal.backtest.min_train_years * 252)
    test = int(goal.backtest.test_window_years * 252)
    step = int(goal.backtest.step_years * 252)
    seam = goal.backtest.seam_sessions
    start = development[0] + train + seam
    last = development[-1] + 1
    values: list[Window] = []
    while start + test <= last:
        values.append(Window(development[0], start - seam, start, start + test, seam))
        start += step
    if not values:
        raise ValueError("clock is too short for configured walk-forward geometry")
    return tuple(values)


def _development_bounds(clock: EvaluationClock, goal: GoalConfig) -> tuple[int, int]:
    positions = tuple(
        position
        for position, value in enumerate(clock.open_times)
        if goal.data_split.walk_forward_start <= value.date() <= goal.data_split.walk_forward_end
    )
    if not positions:
        raise ValueError("clock contains no walk-forward sessions")
    return positions[0], positions[-1] + 1


def _reservation(
    ordinal: int,
    kind: TrialKind,
    fold: int | None,
    start: int,
    end: int,
    clock: EvaluationClock,
    reset: str,
) -> EvaluationReservation:
    return EvaluationReservation(
        ordinal,
        kind,
        fold,
        clock.source_indices[start],
        clock.source_indices[end - 1] + 1,
        clock.open_times[start],
        clock.open_times[end - 1],
        reset,
    )


def build_evaluation_plans(
    cards: tuple[StrategySpec, ...], clock: EvaluationClock, goal: GoalConfig
) -> tuple[EvaluationPlan, ...]:
    if not isinstance(clock, EvaluationClock):
        raise TypeError("plans require a price-free EvaluationClock")
    windows = _clock_windows(clock, goal)
    full_start, full_end = _development_bounds(clock, goal)
    plans: list[EvaluationPlan] = []
    for card in cards:
        signal = (
            _reservation(
                0,
                TrialKind.SIGNAL_FULL,
                None,
                full_start,
                full_end,
                clock,
                "continuous_full_development_v1",
            ),
            *(
                _reservation(
                    position + 1,
                    TrialKind.SIGNAL_FOLD,
                    position,
                    window.test_start,
                    window.test_end,
                    clock,
                    "fresh_signal_simulator_per_fold_v1",
                )
                for position, window in enumerate(windows)
            ),
        )
        plans.append(
            EvaluationPlan(
                card.candidate.name,
                card.candidate.version,
                card.sha256,
                "signal",
                None,
                signal,
                tuple(sorted(card.candidate.primitives_used())),
            )
        )
        for capital in CAPITALS:
            plans.append(
                EvaluationPlan(
                    card.candidate.name,
                    card.candidate.version,
                    card.sha256,
                    "portfolio",
                    capital,
                    (
                        _reservation(
                            0,
                            TrialKind.PORTFOLIO,
                            None,
                            full_start,
                            full_end,
                            clock,
                            "walk_forward_portfolio_v1",
                        ),
                    ),
                    tuple(sorted(card.candidate.primitives_used())),
                )
            )
    return tuple(plans)


def _slice_fixture(
    fixture: TimedFixture, index: TimedFixtureIndex, start: int, end: int
) -> TimedFixture:
    source_start = fixture.sessions[start].index
    source_end = fixture.sessions[end - 1].index
    sessions = fixture.sessions[start:end]
    inactive = frozenset(cell for cell in fixture.inactive if source_start <= cell[1] <= source_end)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                row
                for session in range(source_start, source_end + 1)
                for row in index.by_symbol_session[item.symbol].get(session, ())
            ),
        )
        for item in fixture.refinements
    )
    source = replace(
        fixture.source,
        sha256=timed_fixture_digest(
            sessions,
            refinements,
            inactive,
            None
            if fixture.pair_qualification is None
            else fixture.pair_qualification.qualification.document_sha256,
        ),
    )
    sessions = tuple(replace(item, source=source) for item in sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(
                    row,
                    source=source,
                    opening=(None if row.opening is None else replace(row.opening, source=source)),
                )
                for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, refinements, source, inactive, fixture.pair_qualification)


def _trade_benchmark(
    trade: TimedTrade, payload: CataloguePayload, policy: MatchingPolicy
) -> dict[str, object]:
    converted = SyntheticTrade(
        trade.original_quantity,
        trade.entry.timing,
        tuple(
            ExitFragment(
                f"{position}",
                leg.quantity,
                leg.timing,
                FragmentStatus.EXECUTED,
                leg.raw_bar_ts,
                leg.raw_bar_ts,
            )
            for position, leg in enumerate(trade.exits)
        ),
    )
    result = match_benchmark(
        converted,
        payload.benchmark_index.observations,
        payload.benchmark_identity,
        policy,
        payload.benchmark_index,
    )
    return {
        "source_identity": {
            "benchmark_id": payload.benchmark_identity.benchmark_id,
            "benchmark_version": payload.benchmark_identity.benchmark_version,
            "price_basis": payload.benchmark_identity.price_basis,
            "artifact_id": payload.benchmark_identity.artifact_id,
            "artifact_sha256": payload.benchmark_identity.artifact_sha256,
        },
        "return": None if result.benchmark_return is None else str(result.benchmark_return),
        "matched_exit_quantity": result.matched_exit_quantity,
        "trade_refusals": [item.value for item in result.trade_refusals],
        "legs": [
            {
                "id": leg.leg_id,
                "refusal": None if leg.refusal is None else leg.refusal.value,
                "record_id": leg.observation_record_id,
                "event_ts": (
                    None
                    if leg.observation_event_ts is None
                    else leg.observation_event_ts.isoformat()
                ),
                "available_ts": (
                    None
                    if leg.observation_available_ts is None
                    else leg.observation_available_ts.isoformat()
                ),
                "age_seconds": (
                    None if leg.observation_age is None else leg.observation_age.total_seconds()
                ),
            }
            for leg in result.legs
        ],
    }


def _summary(
    run: TimedRun,
    payload: CataloguePayload,
    policy: MatchingPolicy,
    plan: EvaluationPlan,
    reservation: EvaluationReservation,
) -> dict[str, object]:
    def charges(value: object) -> dict[str, str]:
        return {
            name: str(getattr(value, name))
            for name in (
                "turnover",
                "brokerage",
                "stt",
                "exchange_txn",
                "sebi_fee",
                "gst",
                "stamp_duty",
                "dp_charge",
            )
        }

    def timing(value: Timing) -> dict[str, object]:
        event = value.event_ts
        start = value.interval_start
        end = value.interval_end
        return {
            "precision": value.precision.value,
            "event_ts": None if event is None else event.isoformat(),
            "interval_start": None if start is None else start.isoformat(),
            "interval_end": None if end is None else end.isoformat(),
        }

    def realized_net(trade: TimedTrade) -> str:
        return str(
            sum(
                (
                    leg.price * leg.quantity
                    - leg.charges.total
                    - (
                        Decimal(0)
                        if leg.allocated_entry_charges is None
                        else leg.allocated_entry_charges.total
                    )
                    - trade.entry.price * leg.quantity
                    for leg in trade.exits
                ),
                Decimal(0),
            )
        )

    return {
        "card": plan.card,
        "card_version": plan.card_version,
        "card_sha256": plan.card_sha256,
        "mode": plan.mode,
        "capital": plan.capital,
        "reservation": {
            "ordinal": reservation.ordinal,
            "kind": reservation.kind.value,
            "fold_index": reservation.fold_index,
            "start_index": reservation.start_index,
            "end_index_exclusive": reservation.end_index_exclusive,
            "start_ts": None if reservation.start_ts is None else reservation.start_ts.isoformat(),
            "end_ts": None if reservation.end_ts is None else reservation.end_ts.isoformat(),
            "reset_identity": reservation.reset_identity,
        },
        "pre_tax_diagnostic": True,
        "promotion_available": False,
        "alpha_available": False,
        "run_valid": run.valid,
        "refusal": None if run.refusal is None else run.refusal.reason.value,
        "trade_count": len(run.trades),
        "entry_count": sum(1 for item in run.attempts if item.cause.value == "entry"),
        "exit_count": sum(1 for item in run.attempts if item.cause.value != "entry"),
        "rebalance_events": len(run.rebalance_events),
        "remaining_positions": sum(item.remaining_quantity > 0 for item in run.trades),
        "cash": None if run.cash is None else str(run.cash),
        "realized_equity": None if run.realized_equity is None else str(run.realized_equity),
        "final_equity": None if run.final_equity is None else str(run.final_equity),
        "daily_equity": [
            {"source_index": source, "ts": ts.isoformat(), "equity": str(equity)}
            for source, ts, equity in run.daily_equity
        ],
        "trades": [
            {
                "symbol": trade.signal_id.symbol,
                "decision_source_index": trade.signal_id.decision_index,
                "decision_ts": trade.signal_id.decision_ts.isoformat(),
                "intended_quantity": trade.intended_quantity,
                "original_quantity": trade.original_quantity,
                "remaining_quantity": trade.remaining_quantity,
                "realized_net_pnl_before_tax": realized_net(trade),
                "entry": {
                    "source_index": trade.entry.source_index,
                    "ts": trade.entry.raw_bar_ts.isoformat(),
                    "quantity": trade.entry.quantity,
                    "price": str(trade.entry.price),
                    "charges": charges(trade.entry.charges),
                    "timing": timing(trade.entry.timing),
                },
                "exits": [
                    {
                        "cause": leg.cause.value,
                        "source_index": leg.source_index,
                        "ts": leg.raw_bar_ts.isoformat(),
                        "recognition_ts": leg.recognition_ts.isoformat(),
                        "quantity": leg.quantity,
                        "price": str(leg.price),
                        "charges": charges(leg.charges),
                        "allocated_entry_charges": (
                            None
                            if leg.allocated_entry_charges is None
                            else charges(leg.allocated_entry_charges)
                        ),
                        "timing": timing(leg.timing),
                    }
                    for leg in trade.exits
                ],
                "remaining_entry_charges": charges(trade.remaining_entry_charges),
            }
            for trade in run.trades
        ],
        "benchmark": [_trade_benchmark(item, payload, policy) for item in run.trades],
    }


class TimedCatalogueEvaluator:
    def __init__(
        self,
        cards: tuple[StrategySpec, ...],
        goal: GoalConfig,
        matching_policy: MatchingPolicy,
    ) -> None:
        self._cards = {item.candidate.name: item for item in cards}
        self._goal = goal
        self._registry = default_registry()
        self._policy = matching_policy

    def evaluate(self, plan: EvaluationPlan, payload: object) -> tuple[EvaluationOutcome, ...]:
        if not isinstance(payload, CataloguePayload):
            raise TypeError("payload must be CataloguePayload")
        bound_pair = payload.assembled.fixture.pair_qualification
        if bound_pair is not None and bound_pair.daily_projection_sha256 != daily_projection_digest(
            payload.assembled.panel, payload.assembled.source_indices
        ):
            raise ValueError("qualified daily projection changed after assembly")
        card = self._cards.get(plan.card)
        if (
            card is None
            or card.sha256 != plan.card_sha256
            or card.candidate.version != plan.card_version
            or tuple((item.candidate.name, item.sha256) for item in self._cards.values())
            != payload.card_identity
        ):
            raise ValueError("catalogue identity mismatch")
        if (
            tuple(item.index for item in payload.assembled.fixture.sessions)
            != payload.assembled.source_indices
        ):
            raise ValueError("decoded source axis differs from reserved clock")
        columns = payload._columns.get(card.candidate.name)
        if columns is None:
            columns = evaluate_once(
                card.candidate,
                payload.assembled.panel,
                self._registry,
                source_indices=payload.assembled.source_indices,
            )
            payload._columns[card.candidate.name] = columns
            payload.column_evaluations += 1
        offset = payload.assembled.source_indices[0]

        def one(item: EvaluationReservation, capital: int | None) -> TimedRun:
            assert item.start_index is not None and item.end_index_exclusive is not None
            start, end = item.start_index - offset, item.end_index_exclusive - offset
            if (
                start < 0
                or end > len(payload.assembled.fixture.sessions)
                or item.start_ts != payload.assembled.fixture.sessions[start].open_ts
                or item.end_ts != payload.assembled.fixture.sessions[end - 1].open_ts
            ):
                raise ValueError("decoded session clock differs from reserved geometry")
            panel = slice_panel(payload.assembled.panel, start, end)
            signals, stops, ranks, exits, pulses = columns.slice(start, end)  # type: ignore[attr-defined]
            fixture = payload._fixtures.get((start, end))
            if fixture is None:
                fixture = _slice_fixture(payload.assembled.fixture, payload.timed_index, start, end)
                payload._fixtures[(start, end)] = fixture
            if fixture.pair_qualification is not None:
                fixture = replace(
                    fixture,
                    pair_qualification=BoundPairQualification(
                        fixture.pair_qualification.qualification,
                        daily_projection_digest(panel, payload.assembled.source_indices[start:end]),
                    ),
                )
            costs = CostModel(self._goal.costs)
            fills = FillModel(self._goal.execution_realism)
            stale = self._goal.backtest.stale_position_sessions
            if capital is None:
                simulator = SignalSimulator(
                    notional_inr=Decimal(self._goal.signal_test.notional_inr),
                    costs=costs,
                    fills=fills,
                    stale_after_sessions=stale,
                )
                return simulator.run_time_resolved(
                    card.candidate,
                    panel,
                    signals,
                    stops,
                    fixture=fixture,
                    source_indices=payload.assembled.source_indices[start:end],
                    ranks=ranks,
                    exit_signals=exits,
                    rebalance_pulses=pulses,
                )
            portfolio = PortfolioSimulator(
                risk=self._goal.risk,
                costs=costs,
                fills=fills,
                stale_after_sessions=stale,
            )
            return portfolio.run_time_resolved(
                card.candidate,
                panel,
                signals,
                stops,
                fixture=fixture,
                source_indices=payload.assembled.source_indices[start:end],
                starting_equity=Decimal(capital),
                ranks=ranks,
                exit_signals=exits,
                rebalance_pulses=pulses,
            )

        if plan.mode == "signal":
            runs = tuple(one(item, None) for item in plan.evaluations)
            return tuple(
                EvaluationOutcome(
                    _summary(run, payload, self._policy, plan, reservation), len(run.trades)
                )
                for run, reservation in zip(runs, plan.evaluations, strict=True)
            )
        clock = EvaluationClock(
            payload.assembled.source_indices,
            tuple(item.open_ts for item in payload.assembled.fixture.sessions),
        )
        windows = _clock_windows(clock, self._goal)
        capital = plan.capital
        assert capital is not None
        fold_reservations = tuple(
            _reservation(
                0,
                TrialKind.PORTFOLIO,
                None,
                window.test_start,
                window.test_end,
                clock,
                "walk_forward_portfolio_v1",
            )
            for window in windows
        )
        runs = tuple(one(reservation, capital) for reservation in fold_reservations)
        summary = {
            "card": plan.card,
            "card_version": plan.card_version,
            "card_sha256": plan.card_sha256,
            "mode": plan.mode,
            "capital": plan.capital,
            "reservation": {
                "ordinal": plan.evaluations[0].ordinal,
                "kind": plan.evaluations[0].kind.value,
                "fold_index": plan.evaluations[0].fold_index,
                "start_index": plan.evaluations[0].start_index,
                "end_index_exclusive": plan.evaluations[0].end_index_exclusive,
                "start_ts": (
                    None
                    if plan.evaluations[0].start_ts is None
                    else plan.evaluations[0].start_ts.isoformat()
                ),
                "end_ts": (
                    None
                    if plan.evaluations[0].end_ts is None
                    else plan.evaluations[0].end_ts.isoformat()
                ),
                "reset_identity": plan.evaluations[0].reset_identity,
            },
            "pre_tax_diagnostic": True,
            "promotion_available": False,
            "alpha_available": False,
            "book_reset_each_fold": True,
            "folds": [
                _summary(run, payload, self._policy, plan, reservation)
                for run, reservation in zip(runs, fold_reservations, strict=True)
            ],
            "run_valid": all(run.valid for run in runs),
        }
        return (EvaluationOutcome(summary, sum(len(run.trades) for run in runs)),)


__all__ = [
    "CAPITALS",
    "CataloguePayload",
    "EvaluationClock",
    "StrategySpec",
    "TimedCatalogueEvaluator",
    "build_evaluation_plans",
    "load_strategy_catalogue",
]
