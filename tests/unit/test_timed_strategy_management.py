"""Timed opposite-signal and rebalance management on invented M15 bars."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest

from icarus.common.config import load_goal
from icarus.common.types import OrderSide
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel, Intent, SimBar
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.runner import evaluate_once
from icarus.engine.signaltest import SignalSimulator
from icarus.engine.simcore import RebalanceStatus
from icarus.engine.timed_execution import ExitCause
from icarus.engine.timed_simulation import (
    OpeningLiquidity,
    Refinement,
    ReplayBar,
    Session,
    SourceDeclaration,
    TimedFixture,
    timed_fixture_digest,
)
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

START = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
STEP = timedelta(minutes=15)


def bound_opening(row: ReplayBar, source: SourceDeclaration) -> OpeningLiquidity:
    assert row.opening is not None
    return replace(row.opening, source=source)


def zero_opening(row: ReplayBar) -> OpeningLiquidity:
    assert row.opening is not None
    return replace(row.opening, quantity=Decimal(0))


def fixture(symbols: tuple[str, ...], *, days: int = 4, source_start: int = 252) -> TimedFixture:
    source = SourceDeclaration("invented-management", "v1", "a" * 64)
    sessions = tuple(
        Session(
            source_start + day,
            START + timedelta(days=day),
            START + timedelta(days=day) + 2 * STEP,
            source,
        )
        for day in range(days)
    )
    refinements = tuple(
        Refinement(
            symbol,
            tuple(
                ReplayBar(
                    session.index,
                    SimBar(
                        session.open_ts + bar * STEP,
                        *(Decimal(value) for value in ("100", "101", "99", "100", "10000")),
                    ),
                    session.open_ts + (bar + 1) * STEP,
                    OpeningLiquidity(Decimal("10000"), session.open_ts + bar * STEP, source),
                    source,
                )
                for session in sessions
                for bar in range(2)
            ),
        )
        for symbol in symbols
    )
    digest = timed_fixture_digest(sessions, refinements)
    bound = replace(source, sha256=digest)
    sessions = tuple(replace(session, source=bound) for session in sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=bound, opening=bound_opening(row, bound)) for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, refinements, bound)


def priced_fixture(closes: np.ndarray[Any, np.dtype[np.float64]]) -> TimedFixture:
    value = fixture(("S0",), days=len(closes), source_start=0)
    rows = []
    for local, session in enumerate(value.sessions):
        price = Decimal(str(float(closes[local])))
        for bar in range(2):
            ts = session.open_ts + bar * STEP
            rows.append(
                ReplayBar(
                    session.index,
                    SimBar(ts, price, price + 1, price - 1, price, Decimal("10000")),
                    ts + STEP,
                    OpeningLiquidity(Decimal("10000"), ts, value.source),
                    value.source,
                )
            )
    raw = (Refinement("S0", tuple(rows)),)
    digest = timed_fixture_digest(value.sessions, raw)
    source = replace(value.source, sha256=digest)
    sessions = tuple(replace(session, source=source) for session in value.sessions)
    refinements = (
        Refinement(
            "S0",
            tuple(replace(row, source=source, opening=bound_opening(row, source)) for row in rows),
        ),
    )
    return TimedFixture(sessions, refinements, source)


def slice_fixture(value: TimedFixture, start: int) -> TimedFixture:
    sessions = value.sessions[start:]
    refinements = tuple(
        Refinement(item.symbol, item.bars[2 * start :]) for item in value.refinements
    )
    digest = timed_fixture_digest(sessions, refinements)
    source = replace(value.source, sha256=digest)
    sessions = tuple(replace(session, source=source) for session in sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=source, opening=bound_opening(row, source)) for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, refinements, source)


def low_vol_fixture(size: int = 254) -> TimedFixture:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = fixture(symbols, days=size, source_start=0)
    signs = np.where(np.arange(size) % 2 == 0, 1.0, -1.0)
    paths = {
        symbol: 100.0 * np.cumprod(1.0 + signs * (index + 1) * 0.00005)
        for index, symbol in enumerate(symbols)
    }
    refinements = []
    for item in value.refinements:
        rows = []
        for local, session in enumerate(value.sessions):
            price = Decimal(str(float(paths[item.symbol][local])))
            for bar in range(2):
                ts = session.open_ts + bar * STEP
                rows.append(
                    ReplayBar(
                        session.index,
                        SimBar(ts, price, price + 2, price - 2, price, Decimal("10000")),
                        ts + STEP,
                        OpeningLiquidity(Decimal("10000"), ts, value.source),
                        value.source,
                    )
                )
        refinements.append(Refinement(item.symbol, tuple(rows)))
    digest = timed_fixture_digest(value.sessions, tuple(refinements))
    source = replace(value.source, sha256=digest)
    sessions = tuple(replace(session, source=source) for session in value.sessions)
    bound = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=source, opening=bound_opening(row, source)) for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, bound, source)


def panel(value: TimedFixture) -> Panel:
    dates = np.array([np.datetime64(s.open_ts.replace(tzinfo=None), "ns") for s in value.sessions])
    data = {}
    for item in value.refinements:
        grouped = [item.bars[2 * i : 2 * i + 2] for i in range(len(value.sessions))]
        data[item.symbol] = Bars(
            dates,
            np.array([float(rows[0].bar.open) for rows in grouped]),
            np.array([float(max(row.bar.high for row in rows)) for rows in grouped]),
            np.array([float(min(row.bar.low for row in rows)) for rows in grouped]),
            np.array([float(rows[-1].bar.close) for rows in grouped]),
            np.array([float(sum(row.bar.volume for row in rows)) for rows in grouped]),
        )
    return Panel.build(data, {symbol: np.ones(len(dates), dtype=np.bool_) for symbol in data})


def change(
    value: TimedFixture,
    symbol: str,
    row_at: int,
    *,
    proxy: str | None = "10000",
    **bar_values: str,
) -> TimedFixture:
    refinements = []
    for item in value.refinements:
        if item.symbol != symbol:
            refinements.append(item)
            continue
        row = item.bars[row_at]
        bar = replace(
            cast(Any, row.bar), **{name: Decimal(raw) for name, raw in bar_values.items()}
        )
        assert row.opening is not None
        opening = None if proxy is None else replace(row.opening, quantity=Decimal(proxy))
        refinements.append(
            Refinement(
                symbol,
                (
                    *item.bars[:row_at],
                    replace(row, bar=bar, opening=opening),
                    *item.bars[row_at + 1 :],
                ),
            )
        )
    sessions = value.sessions
    digest = timed_fixture_digest(sessions, tuple(refinements))
    bound = replace(value.source, sha256=digest)
    sessions = tuple(replace(session, source=bound) for session in sessions)
    refinements = [
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=bound, opening=bound_opening(row, bound)) for row in item.bars
            ),
        )
        for item in refinements
    ]
    return TimedFixture(sessions, tuple(refinements), bound)


def suppress_opening_after(
    value: TimedFixture, symbol: str, first_source_index: int
) -> TimedFixture:
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(
                    row,
                    opening=zero_opening(row),
                )
                if item.symbol == symbol and row.session_index >= first_source_index
                else row
                for row in item.bars
            ),
        )
        for item in value.refinements
    )
    digest = timed_fixture_digest(value.sessions, refinements)
    source = replace(value.source, sha256=digest)
    sessions = tuple(replace(session, source=source) for session in value.sessions)
    bound = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=source, opening=bound_opening(row, source)) for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, bound, source)


def card(name: str) -> Any:
    return parse_strategy(
        Path(f"strategies/{name}.yaml").read_text(), registry=default_registry(), max_risk_r=0.005
    )


def run(
    mode: str,
    value: TimedFixture,
    candidate: Any,
    signals: dict[str, np.ndarray[Any, np.dtype[np.float64]]],
    *,
    exits: dict[str, np.ndarray[Any, np.dtype[np.float64]]] | None = None,
    ranks: dict[str, np.ndarray[Any, np.dtype[np.float64]]] | None = None,
    pulses: np.ndarray[Any, np.dtype[np.bool_]] | None = None,
    capital: Decimal = Decimal("10000"),
    stop_columns: dict[str, np.ndarray[Any, np.dtype[np.float64]]] | None = None,
    latency_ms: int | None = None,
) -> Any:
    goal = load_goal()
    execution = (
        goal.execution_realism
        if latency_ms is None
        else goal.execution_realism.model_copy(update={"latency_ms": latency_ms})
    )
    simulator: Any = (
        SignalSimulator(
            notional_inr=Decimal("1000"),
            costs=CostModel(goal.costs),
            fills=FillModel(execution),
            stale_after_sessions=3,
        )
        if mode == "signal"
        else PortfolioSimulator(
            risk=goal.risk,
            costs=CostModel(goal.costs),
            fills=FillModel(execution),
            stale_after_sessions=3,
        )
    )
    kwargs: dict[str, Any] = dict(
        fixture=value,
        source_indices=tuple(s.index for s in value.sessions),
        exit_signals=exits,
        ranks=ranks,
        rebalance_pulses=pulses,
    )
    if mode == "portfolio":
        kwargs["starting_equity"] = capital
    stops = stop_columns or {symbol: np.full(len(value.sessions), 5.0) for symbol in signals}
    return simulator.run_time_resolved(candidate, panel(value), signals, stops, **kwargs)


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_opposite_decision_uses_close_then_sticky_next_session_open(mode: str) -> None:
    value = fixture(("S0",))
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, 1.0, 1.0, 0.0])},
    )
    assert result.valid
    assert result.trades[0].signal_id.decision_ts == value.sessions[0].open_ts
    assert result.management_exit_events[0].decision_ts == value.sessions[1].close_ts
    assert result.trades[0].exits[0].source_index == 254
    assert result.trades[0].exits[0].cause is ExitCause.OPPOSITE_SIGNAL


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_held_nan_opposite_decision_refuses_but_warmup_nan_does_not(mode: str) -> None:
    value = fixture(("S0",))
    candidate = card("donchian_55_20")
    warmup = run(
        mode,
        value,
        candidate,
        {"S0": np.array([0.0, 1.0, 0.0, 0.0])},
        exits={"S0": np.array([np.nan, 0.0, 0.0, 0.0])},
    )
    assert warmup.valid
    missing = run(
        mode,
        value,
        candidate,
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, np.nan, 0.0, 0.0])},
    )
    assert not missing.valid
    assert missing.refusal.reason.value == "missing_management_decision"
    assert missing.trades and missing.trades[0].remaining_quantity > 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_held_nan_halts_before_any_next_session_execution(mode: str) -> None:
    value = change(fixture(("S0",)), "S0", 4, open="94", high="94", low="93", close="94")
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, np.nan, 0.0, 0.0])},
    )
    assert not result.valid and result.refusal.reason.value == "missing_management_decision"
    assert [attempt.cause for attempt in result.attempts] == [ExitCause.ENTRY]
    assert not result.trades[0].exits
    assert result.trades[0].remaining_quantity == result.trades[0].original_quantity


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_low_vol_source_grid_selects_30_and_admits_from_31_name_cohort(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = fixture(symbols)
    candidate = card("defensive_low_vol_252_q63")
    signals = {
        symbol: np.array([1.0 if i < 30 else 0.0, 0.0, 0.0, 0.0])
        for i, symbol in enumerate(symbols)
    }
    ranks = {symbol: np.full(4, float(31 - i)) for i, symbol in enumerate(symbols)}
    result = run(
        mode,
        value,
        candidate,
        signals,
        ranks=ranks,
        pulses=np.array([True, False, False, False], dtype=np.bool_),
    )
    assert result.valid
    assert result.rebalance_events[0].status is RebalanceStatus.VALID
    assert len(result.rebalance_events[0].candidates) == 30
    assert len(result.trades) == (30 if mode == "signal" else 4)
    assert all(trade.entry.source_index == 253 for trade in result.trades)


def test_declared_management_columns_are_required_and_grid_cannot_restart() -> None:
    value = fixture(("S0",))
    signals = {"S0": np.zeros(4)}
    with pytest.raises(ValueError, match="evaluated exit columns"):
        run("signal", value, card("donchian_55_20"), signals)
    symbols = tuple(f"S{i:02d}" for i in range(31))
    low = fixture(symbols)
    low_signals = {symbol: np.zeros(4) for symbol in symbols}
    ranks = {symbol: np.ones(4) for symbol in symbols}
    with pytest.raises(ValueError, match="whole-source grid"):
        run(
            "signal",
            low,
            card("defensive_low_vol_252_q63"),
            low_signals,
            ranks=ranks,
            pulses=np.array([False, True, False, False], dtype=np.bool_),
        )


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_sticky_partial_opposite_keeps_one_origin_and_terminal_inventory(mode: str) -> None:
    value = fixture(("S0",))
    for row_at in range(4, 8):
        value = change(value, "S0", row_at, proxy="20")
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, 1.0, 1.0, 1.0])},
        capital=Decimal("100000"),
    )
    trade = result.trades[0]
    assert result.valid and len(result.management_exit_events) == 1
    assert [leg.quantity for leg in trade.exits] == [1, 1, 1, 1]
    assert trade.remaining_quantity == trade.original_quantity - 4
    assert all(leg.cause is ExitCause.OPPOSITE_SIGNAL for leg in trade.exits)


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_stop_precedes_pending_management_at_same_open(mode: str) -> None:
    value = change(fixture(("S0",)), "S0", 4, open="94", high="94", low="93", close="94")
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, 1.0, 0.0, 0.0])},
    )
    assert result.valid
    assert result.trades[0].exits[0].cause is ExitCause.STOP


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_extra_consumer_columns_do_not_manage_an_undeclared_card(mode: str) -> None:
    value = fixture(("S0",))
    result = run(
        mode,
        value,
        card("baseline_buy_and_hold"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.ones(4)},
        pulses=np.array([True, False, False, False], dtype=np.bool_),
    )
    assert result.valid and not result.management_exit_events and not result.rebalance_events
    assert result.trades[0].remaining_quantity == result.trades[0].original_quantity


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_terminal_rebalance_records_retain_drop_and_no_next_admission(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = fixture(symbols, days=64)
    signals = {symbol: np.zeros(64) for symbol in symbols}
    for index, symbol in enumerate(symbols):
        signals[symbol][0] = float(index < 30)
        signals[symbol][63] = float(index > 0)
    ranks = {symbol: np.full(64, float(31 - i)) for i, symbol in enumerate(symbols)}
    pulses = np.zeros(64, dtype=np.bool_)
    pulses[[0, 63]] = True
    result = run(
        mode,
        value,
        card("defensive_low_vol_252_q63"),
        signals,
        ranks=ranks,
        pulses=pulses,
        capital=Decimal("100000"),
    )
    final = result.rebalance_events[-1]
    assert result.valid and final.decision_index == 315
    assert "S00" not in final.candidates and "S30" in final.pending_admissions
    assert any(
        event.symbol == "S00" and event.decision_index == 315
        for event in result.management_exit_events
    )
    s30 = next(d for d in result.dispositions if d.signal_id.symbol == "S30")
    assert s30.reason.value == "no_eligible_next_session"
    assert next(t for t in result.trades if t.signal_id.symbol == "S00").remaining_quantity > 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_actual_donchian_evaluation_drives_timed_opposite_lane(mode: str) -> None:
    closes = np.full(80, 100.0)
    closes[55:75] = 110.0
    closes[75:] = np.array([99.0, 98.99, 98.99, 98.99, 98.99])
    value = priced_fixture(closes)
    for day in range(42, 55):
        for bar in range(2):
            value = change(value, "S0", 2 * day + bar, high="104", low="96")
    candidate = card("donchian_55_20")
    columns = evaluate_once(
        candidate,
        panel(value),
        default_registry(),
        source_indices=tuple(range(80)),
    )
    assert columns.exit_signals is not None
    value = slice_fixture(value, 55)
    result = run(
        mode,
        value,
        candidate,
        {symbol: values[55:] for symbol, values in columns.signals.items()},
        exits={symbol: values[55:] for symbol, values in columns.exit_signals.items()},
        ranks=(
            None
            if columns.ranks is None
            else {symbol: values[55:] for symbol, values in columns.ranks.items()}
        ),
        pulses=(None if columns.rebalance_pulses is None else columns.rebalance_pulses[55:]),
        capital=Decimal("100000"),
        stop_columns={symbol: values[55:] for symbol, values in columns.stops.items()},
    )
    assert result.valid and result.management_exit_events
    assert any(
        leg.cause is ExitCause.OPPOSITE_SIGNAL for trade in result.trades for leg in trade.exits
    )


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_actual_low_vol_evaluation_uses_full_252_grid_and_31_names(mode: str) -> None:
    value = low_vol_fixture()
    candidate = card("defensive_low_vol_252_q63")
    columns = evaluate_once(
        candidate,
        panel(value),
        default_registry(),
        source_indices=tuple(range(254)),
    )
    assert columns.rebalance_pulses is not None and columns.rebalance_pulses[252]
    result = run(
        mode,
        value,
        candidate,
        columns.signals,
        ranks=columns.ranks,
        pulses=columns.rebalance_pulses,
        capital=Decimal("100000"),
        stop_columns=columns.stops,
    )
    assert result.valid and result.rebalance_events[0].decision_index == 252
    assert result.rebalance_events[0].status is RebalanceStatus.VALID
    assert len(result.rebalance_events[0].candidates) == 30


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_management_latency_skips_first_open_but_not_second(mode: str) -> None:
    value = fixture(("S0",))
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, 1.0, 0.0, 0.0])},
        latency_ms=(23 * 60 + 40) * 60 * 1000,
        capital=Decimal("100000"),
    )
    exit_leg = result.trades[0].exits[0]
    assert result.valid and exit_leg.cause is ExitCause.OPPOSITE_SIGNAL
    assert exit_leg.raw_bar_ts == value.sessions[2].open_ts + STEP


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_management_order_carries_its_own_close_availability(
    mode: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Intent] = []
    original = FillModel.execute

    def observe(model: FillModel, intent: Intent, bar: SimBar) -> Any:
        if intent.side is OrderSide.SELL:
            seen.append(intent)
        return original(model, intent, bar)

    monkeypatch.setattr(FillModel, "execute", observe)
    value = fixture(("S0",))
    result = run(
        mode,
        value,
        card("donchian_55_20"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0])},
        exits={"S0": np.array([0.0, 1.0, 0.0, 0.0])},
    )
    assert result.valid and seen[0].decided_at == value.sessions[1].close_ts


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_unavailable_later_cohort_preserves_existing_book(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = fixture(symbols, days=64)
    signals = {symbol: np.zeros(64) for symbol in symbols}
    for index, symbol in enumerate(symbols):
        signals[symbol][0] = float(index < 30)
        signals[symbol][63] = np.nan
    ranks = {symbol: np.full(64, float(31 - i)) for i, symbol in enumerate(symbols)}
    pulses = np.zeros(64, dtype=np.bool_)
    pulses[[0, 63]] = True
    result = run(
        mode,
        value,
        card("defensive_low_vol_252_q63"),
        signals,
        ranks=ranks,
        pulses=pulses,
        capital=Decimal("100000"),
    )
    before = set(result.rebalance_events[0].holdings_after)
    final = result.rebalance_events[-1]
    assert result.valid and final.status is RebalanceStatus.COHORT_UNAVAILABLE
    assert set(final.holdings_after) == before
    assert not result.management_exit_events


def test_fixed_card_keeps_nonfinite_rank_fallback_policy() -> None:
    value = fixture(("S0", "S1"))
    result = run(
        "portfolio",
        value,
        card("baseline_buy_and_hold"),
        {"S0": np.array([1.0, 0.0, 0.0, 0.0]), "S1": np.array([1.0, 0.0, 0.0, 0.0])},
        ranks={"S0": np.full(4, np.inf), "S1": np.full(4, 1.0)},
    )
    assert result.valid and result.trades


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_rebalance_holdings_snapshot_is_after_open_batch_before_intrabar_exit(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = change(fixture(symbols), "S00", 3, low="94")
    signals = {
        symbol: np.array([float(index < 30), 0.0, 0.0, 0.0]) for index, symbol in enumerate(symbols)
    }
    ranks = {symbol: np.full(4, float(31 - index)) for index, symbol in enumerate(symbols)}
    result = run(
        mode,
        value,
        card("defensive_low_vol_252_q63"),
        signals,
        ranks=ranks,
        pulses=np.array([True, False, False, False], dtype=np.bool_),
        capital=Decimal("100000"),
    )
    assert result.valid and "S00" in result.rebalance_events[0].holdings_after
    s00 = next(trade for trade in result.trades if trade.signal_id.symbol == "S00")
    assert s00.remaining_quantity == 0 and s00.exits[0].cause is ExitCause.STOP


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_returning_target_does_not_resurrect_pending_rebalance_sale(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = suppress_opening_after(fixture(symbols, days=127), "S00", 316)
    signals = {symbol: np.zeros(127) for symbol in symbols}
    for index, symbol in enumerate(symbols):
        signals[symbol][0] = float(index < 30)
        signals[symbol][63] = float(index > 0)
        signals[symbol][126] = float(index < 30)
    ranks = {symbol: np.full(127, float(31 - index)) for index, symbol in enumerate(symbols)}
    pulses = np.zeros(127, dtype=np.bool_)
    pulses[[0, 63, 126]] = True
    result = run(
        mode,
        value,
        card("defensive_low_vol_252_q63"),
        signals,
        ranks=ranks,
        pulses=pulses,
        capital=Decimal("100000"),
    )
    final = result.rebalance_events[-1]
    s00_events = [event for event in result.management_exit_events if event.symbol == "S00"]
    assert result.valid and len(s00_events) == 1 and s00_events[0].decision_index == 315
    assert "S00" not in final.retained and "S00" not in final.pending_admissions
    assert next(t for t in result.trades if t.signal_id.symbol == "S00").remaining_quantity > 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_rebalance_admission_expires_after_immediate_next_session(mode: str) -> None:
    symbols = tuple(f"S{i:02d}" for i in range(31))
    value = fixture(symbols)
    signals = {
        symbol: np.array([float(index < 30), 0.0, 0.0, 0.0]) for index, symbol in enumerate(symbols)
    }
    ranks = {symbol: np.full(4, float(31 - index)) for index, symbol in enumerate(symbols)}
    result = run(
        mode,
        value,
        card("defensive_low_vol_252_q63"),
        signals,
        ranks=ranks,
        pulses=np.array([True, False, False, False], dtype=np.bool_),
        latency_ms=24 * 60 * 60 * 1000,
        capital=Decimal("100000"),
    )
    assert result.valid and not result.trades
    assert all(d.reason.value == "no_eligible_next_session" for d in result.dispositions)
    assert not any(a.cause is ExitCause.ENTRY for a in result.attempts)
