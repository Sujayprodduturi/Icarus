"""Public dual-book timing integration on a fully declared invented daily/M15 axis."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest
from scripts.research.synthetic_benchmark_match import (
    BenchmarkObservation,
    FixtureIdentity,
    ObservationState,
    Precision,
)

from icarus.common.config import load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel, SimBar
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.signaltest import SignalSimulator
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

START = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
STEP = timedelta(minutes=15)


@pytest.fixture
def m() -> ModuleType:
    try:
        return import_module("icarus.engine.timed_simulation")
    except ModuleNotFoundError:
        pytest.fail("shared public timing book is not implemented")


def make(m: ModuleType, symbols: tuple[str, ...] = ("S0",), days: int = 4) -> Any:
    source = m.SourceDeclaration("invented-panel", "v1", "a" * 64)
    sessions = tuple(
        m.Session(252 + d, START + timedelta(days=d), START + timedelta(days=d) + 2 * STEP, source)
        for d in range(days)
    )
    series = tuple(
        m.Refinement(
            s,
            tuple(
                m.ReplayBar(
                    session.index,
                    SimBar(
                        session.open_ts + k * STEP,
                        *(Decimal(x) for x in ("100", "101", "99", "100", "10000")),
                    ),
                    session.open_ts + (k + 1) * STEP,
                    m.OpeningLiquidity(Decimal("10000"), session.open_ts + k * STEP, source),
                    source,
                )
                for session in sessions
                for k in range(2)
            ),
        )
        for s in symbols
    )
    return bind(m, sessions, series)


def bind(m: ModuleType, sessions: Any, series: Any) -> Any:
    source = replace(sessions[0].source, sha256=m.timed_fixture_digest(sessions, series))
    sessions = tuple(replace(s, source=source) for s in sessions)
    series = tuple(
        m.Refinement(
            r.symbol,
            tuple(
                replace(
                    b,
                    source=source,
                    opening=None if b.opening is None else replace(b.opening, source=source),
                )
                for b in r.bars
            ),
        )
        for r in series
    )
    return m.TimedFixture(sessions, series, source)


def change(
    m: ModuleType, fixture: Any, symbol: str, at: int, proxy: str | None = "10000", **values: str
) -> Any:
    series = []
    for r in fixture.refinements:
        if r.symbol != symbol:
            series.append(r)
            continue
        row = r.bars[at]
        raw = replace(row.bar, **{key: Decimal(value) for key, value in values.items()})
        opening = None if proxy is None else replace(row.opening, quantity=Decimal(proxy))
        series.append(
            m.Refinement(
                symbol, (*r.bars[:at], replace(row, bar=raw, opening=opening), *r.bars[at + 1 :])
            )
        )
    return bind(m, fixture.sessions, tuple(series))


def panel(fixture: Any) -> Panel:
    dates = np.array(
        [np.datetime64(s.open_ts.replace(tzinfo=None), "ns") for s in fixture.sessions]
    )
    data = {}
    for r in fixture.refinements:
        grouped = [r.bars[2 * i : 2 * i + 2] for i in range(len(fixture.sessions))]
        data[r.symbol] = Bars(
            dates,
            np.array([float(rows[0].bar.open) for rows in grouped]),
            np.array([float(max(b.bar.high for b in rows)) for rows in grouped]),
            np.array([float(min(b.bar.low for b in rows)) for rows in grouped]),
            np.array([float(rows[-1].bar.close) for rows in grouped]),
            np.array([float(sum(b.bar.volume for b in rows)) for rows in grouped]),
        )
    return Panel.build(data, {s: np.ones(len(dates), dtype=np.bool_) for s in data})


def strategy(card: str = "baseline_buy_and_hold") -> Any:
    return parse_strategy(
        Path(f"strategies/{card}.yaml").read_text(), registry=default_registry(), max_risk_r=0.005
    )


def simulate(
    m: ModuleType,
    mode: str,
    fixture: Any,
    signals: Any,
    *,
    capital: str = "10000",
    card: str = "baseline_buy_and_hold",
    stop: float = 5.0,
    risk: Any = None,
    candidate: Any = None,
    ranks: Any = None,
    daily: Any = None,
) -> Any:
    goal = load_goal()
    common: dict[str, Any] = dict(
        costs=CostModel(goal.costs), fills=FillModel(goal.execution_realism), stale_after_sessions=3
    )
    simulator: Any = (
        SignalSimulator(notional_inr=Decimal("1000"), **common)
        if mode == "signal"
        else (PortfolioSimulator(risk=risk or goal.risk, **common))
    )
    columns = {s: np.array(v, dtype=np.float64) for s, v in signals.items()}
    stops = {s: np.full(len(fixture.sessions), stop) for s in signals}
    kwargs: dict[str, Any] = dict(
        fixture=fixture, source_indices=tuple(s.index for s in fixture.sessions), ranks=ranks
    )
    if mode == "portfolio":
        kwargs["starting_equity"] = Decimal(capital)
    return simulator.run_time_resolved(
        candidate or strategy(card), daily or panel(fixture), columns, stops, **kwargs
    )


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_actual_m15_exit_changes_next_signal_inventory(m: ModuleType, mode: str) -> None:
    fixture = change(m, make(m), "S0", 3, open="94", high="94", low="93", close="94")
    run = simulate(m, mode, fixture, {"S0": [1, 1, 0, 0]})
    assert run.valid and len(run.trades) == 2
    assert [t.entry.source_index for t in run.trades] == [253, 254]
    assert run.trades[0].exits[0].timing.precision is Precision.EVENT_RESOLVED
    assert run.trades[0].signal_id.decision_index == 252
    assert run.trades[0].decision_available_ts == fixture.sessions[0].close_ts
    assert run.trades[1].remaining_quantity > 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_future_volume_invalidates_whole_run_without_resizing_open_batch(
    m: ModuleType, mode: str
) -> None:
    fixture = make(m)
    normal = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]})
    bad = change(m, fixture, "S0", 2, volume="1")
    invalid = simulate(m, mode, bad, {"S0": [1, 0, 0, 0]})
    assert not invalid.valid and invalid.final_equity is None
    assert invalid.refusal.reason is m.TimedRefusal.LIQUIDITY_UNAVAILABLE
    assert invalid.trades[0].original_quantity == normal.trades[0].original_quantity
    assert invalid.trades[0].entry.price == normal.trades[0].entry.price


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
@pytest.mark.parametrize(
    ("card", "message"),
    [
        ("donchian_55_20", "evaluated exit columns"),
        ("defensive_low_vol_252_q63", "whole-source pulse columns"),
    ],
)
def test_management_cards_require_declared_columns_before_fills(
    m: ModuleType, mode: str, card: str, message: str, monkeypatch: Any
) -> None:
    def forbidden(*args: Any) -> Any:
        pytest.fail("unsupported timed rule reached FillModel")

    monkeypatch.setattr(FillModel, "execute", forbidden)
    with pytest.raises(ValueError, match=message):
        simulate(m, mode, make(m), {"S0": [1, 0, 0, 0]}, card=card)


def test_missing_refinement_keeps_universe_and_all_signal_identities(m: ModuleType) -> None:
    fixture = make(m, ("S0", "S1"))
    daily = panel(fixture)
    broken = replace(fixture, refinements=fixture.refinements[:1])
    run = simulate(m, "signal", broken, {"S0": [1, 0, 0, 0], "S1": [1, 0, 0, 0]}, daily=daily)
    assert not run.valid and run.symbols == ("S0", "S1")
    assert len(run.dispositions) == 2
    assert all(d.reason is m.Disposition.UNAVAILABLE for d in run.dispositions)


def test_partial_entry_cost_and_real_portfolio_cash(m: ModuleType) -> None:
    fixture = change(m, make(m), "S0", 2, proxy="100", volume="1000")
    run = simulate(m, "portfolio", fixture, {"S0": [1, 0, 0, 0]})
    trade = run.trades[0]
    assert trade.original_quantity == 5
    assert run.cash == Decimal("10000") - trade.entry.price * 5 - trade.entry.charges.total
    assert run.final_equity == run.cash + Decimal(100) * 5


def test_real_matcher_adapter_requires_containing_run_validity(m: ModuleType) -> None:
    fixture = change(m, make(m), "S0", 3, open="94", high="94", low="93", close="94")
    fixture = change(m, fixture, "S0", 4, volume="1")
    run = simulate(m, "signal", fixture, {"S0": [1, 1, 0, 0]})
    assert run.trades[0].remaining_quantity == 0 and not run.valid
    helper = import_module("scripts.research.synthetic_execution_replay")
    identity = FixtureIdentity("invented", "v1", "PRICE_INDEX", "index", "b" * 64)
    observations = tuple(
        BenchmarkObservation(identity, str(i), ts, ts, Fraction(value), ObservationState.OBSERVED)
        for i, (ts, value) in enumerate(
            [
                (run.trades[0].entry.timing.event_ts, 100),
                (run.trades[0].exits[0].timing.event_ts, 102),
            ]
        )
    )
    outcome = helper.match_timed_trade(run, run.trades[0].signal_id, observations, identity)
    assert outcome.benchmark_return is None and outcome.run_unavailable


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_old_open_exit_new_entry_share_symbol_budget(m: ModuleType, mode: str) -> None:
    fixture = change(m, make(m), "S0", 4, proxy="220", open="94", high="94", low="93", close="94")
    run = simulate(m, mode, fixture, {"S0": [1, 1, 0, 0]})
    assert run.valid and len(run.trades) == 2
    fills = [
        a.fill.filled_quantity for a in run.attempts if a.bar_ts == fixture.sessions[2].open_ts
    ]
    assert sum(fills) == 11
    assert run.trades[1].original_quantity == (2 if mode == "signal" else 1)
    assert run.trades[0].remaining_quantity == 0


def test_future_intrabar_low_cannot_free_same_open_portfolio_slot(m: ModuleType) -> None:
    fixture = make(m, ("S0", "S1"))
    signals = {"S0": [1, 0, 0, 0], "S1": [0, 1, 0, 0]}
    risk = load_goal().risk.model_copy(update={"max_open_positions": 1})
    clean = simulate(m, "portfolio", fixture, signals, risk=risk)
    stopped = simulate(m, "portfolio", change(m, fixture, "S0", 4, low="94"), signals, risk=risk)
    assert clean.valid and stopped.valid
    for run in (clean, stopped):
        assert len(run.trades) == 1
        assert (
            next(d for d in run.dispositions if d.signal_id.symbol == "S1").reason
            is m.Disposition.NO_SLOT
        )
    assert stopped.trades[0].remaining_quantity == 0
    assert stopped.trades[0].exits[0].timing.precision is Precision.BAR_RESOLVED


def test_actual_open_exit_releases_portfolio_slot_and_cash(m: ModuleType) -> None:
    fixture = change(m, make(m, ("S0", "S1")), "S0", 4, open="94", high="94", low="93", close="94")
    risk = load_goal().risk.model_copy(update={"max_open_positions": 1})
    run = simulate(m, "portfolio", fixture, {"S0": [1, 0, 0, 0], "S1": [0, 1, 0, 0]}, risk=risk)
    assert run.valid and [t.signal_id.symbol for t in run.trades] == ["S0", "S1"]
    first, second = run.trades
    assert first.remaining_quantity == 0
    assert second.original_quantity == 9  # realized loss/fees reduce the next risk budget
    expected_cash = (
        Decimal(10000) - first.entry.price * first.original_quantity - first.entry.charges.total
    )
    expected_cash += sum(e.price * e.quantity - e.charges.total for e in first.exits)
    expected_cash -= second.entry.price * second.original_quantity + second.entry.charges.total
    assert run.cash == expected_cash


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_native_intrabar_stop_partial_latches_after_rebound(m: ModuleType, mode: str) -> None:
    fixture = change(m, make(m), "S0", 3, proxy="40", volume="1000", low="94")
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]})
    assert run.valid
    trade = run.trades[0]
    assert (
        trade.exits[0].quantity == 2 and trade.exits[0].timing.precision is Precision.BAR_RESOLVED
    )
    assert trade.exits[1].timing.precision is Precision.EVENT_RESOLVED
    assert trade.exits[1].price > trade.exits[0].price
    assert sum(e.quantity for e in trade.exits) == trade.original_quantity


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_session_timer_does_not_advance_per_m15_bar(m: ModuleType, mode: str) -> None:
    from icarus.strategy.dsl import ExitRule

    candidate = strategy().model_copy(
        update={"exits": (*strategy().exits, ExitRule(rule="time_stop", literals={"bars": 2}))}
    )
    fixture = make(m)
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]}, candidate=candidate)
    assert run.valid and run.trades[0].exits[0].raw_bar_ts == fixture.sessions[2].open_ts


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_entry_activation_order_invalidates_without_protective_sale(
    m: ModuleType, mode: str
) -> None:
    run = simulate(m, mode, change(m, make(m), "S0", 2, low="94"), {"S0": [1, 0, 0, 0]})
    assert not run.valid and run.refusal.reason is m.TimedRefusal.PATH_ORDER_UNAVAILABLE
    assert run.trades[0].remaining_quantity == run.trades[0].original_quantity
    assert not run.trades[0].exits and len(run.attempts) == 1


def test_ranked_risk_and_whole_share_refusals_are_actual_book_decisions(m: ModuleType) -> None:
    fixture = make(m, ("S0", "S1"))
    signals = {s: [1, 0, 0, 0] for s in ("S0", "S1")}
    risk = load_goal().risk.model_copy(update={"max_open_positions": 1})
    ranks = {"S0": np.ones(4), "S1": np.full(4, 2.0)}
    run = simulate(m, "portfolio", fixture, signals, risk=risk, ranks=ranks)
    assert [t.signal_id.symbol for t in run.trades] == ["S1"]
    tiny = simulate(m, "portfolio", make(m), {"S0": [1, 0, 0, 0]}, capital="100")
    assert tiny.dispositions[0].reason is m.Disposition.ROUNDS_TO_ZERO
    cap = simulate(m, "portfolio", make(m), {"S0": [1, 0, 0, 0]}, capital="100", stop=0.1)
    assert cap.dispositions[0].reason is m.Disposition.CONCENTRATION_CAP


def test_handbuilt_excess_risk_and_trailing_refuse_before_any_fill(
    m: ModuleType, monkeypatch: Any
) -> None:
    from icarus.strategy.dsl import ExitRule

    def forbidden(*args: Any) -> Any:
        pytest.fail("unsupported risk/exit reached FillModel")

    monkeypatch.setattr(FillModel, "execute", forbidden)
    candidate = strategy().model_copy(
        update={"sizing": strategy().sizing.model_copy(update={"risk_r": 0.006})}
    )
    run = simulate(m, "portfolio", make(m), {"S0": [1, 0, 0, 0]}, candidate=candidate)
    assert run.refusal.reason is m.TimedRefusal.EXCESS_RISK
    candidate = strategy().model_copy(
        update={
            "exits": (
                ExitRule(rule="trailing_stop_atr", literals={"atr_mult": 3, "atr_period": 14}),
            )
        }
    )
    run = simulate(m, "signal", make(m), {"S0": [1, 0, 0, 0]}, candidate=candidate)
    assert run.refusal.reason is m.TimedRefusal.UNSUPPORTED_TRAILING


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_daily_aggregation_mismatch_refuses_without_timeline_repair(
    m: ModuleType, mode: str
) -> None:
    fixture = make(m)
    daily = panel(fixture)
    daily.bars[0].close[1] = 100.5
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]}, daily=daily)
    assert not run.valid and not run.trades
    assert run.refusal.reason is m.TimedRefusal.AGGREGATION


def test_valid_event_match_calls_real_hook_and_incomplete_trade_returns_none(
    m: ModuleType, monkeypatch: Any
) -> None:
    fixture = change(m, make(m), "S0", 3, open="94", high="94", low="93", close="94")
    run = simulate(m, "signal", fixture, {"S0": [1, 1, 0, 0]})
    helper = import_module("scripts.research.synthetic_execution_replay")
    identity = FixtureIdentity("invented", "v1", "PRICE_INDEX", "index", "b" * 64)
    trade = run.trades[0]
    observations = tuple(
        BenchmarkObservation(identity, str(i), ts, ts, Fraction(value), ObservationState.OBSERVED)
        for i, (ts, value) in enumerate(
            [(trade.entry.timing.event_ts, 100), (trade.exits[0].timing.event_ts, 102)]
        )
    )
    called: list[Any] = []
    original = helper.match_benchmark

    def observe(*args: Any) -> Any:
        called.append(args[0])
        return original(*args)

    monkeypatch.setattr(helper, "match_benchmark", observe)
    outcome = helper.match_timed_trade(run, trade.signal_id, observations, identity)
    assert outcome.benchmark_return == Fraction(1, 50) and len(called) == 1
    incomplete = helper.match_timed_trade(run, run.trades[1].signal_id, observations, identity)
    assert incomplete.benchmark_return is None and len(called) == 2


def test_fill_config_accessor_cannot_mutate_active_model() -> None:
    from pydantic import ValidationError

    fills = FillModel(load_goal().execution_realism)
    view = fills.execution_config
    with pytest.raises(ValidationError):
        view.__setattr__("model_partial_fills", False)
    assert fills.execution_config.model_partial_fills


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
@pytest.mark.parametrize("stop", [50.0, 1.05])
def test_nonpositive_gap_protective_stop_vetoes_before_fill_or_charge(
    m: ModuleType, mode: str, stop: float, monkeypatch: Any
) -> None:
    fixture = change(m, make(m), "S0", 2, open="1", high="1", low="1", close="1")

    def forbidden(*args: Any) -> Any:
        pytest.fail("invalid protection must precede FillModel")

    monkeypatch.setattr(FillModel, "execute", forbidden)
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]}, stop=stop)
    assert run.valid and not run.trades and not run.attempts
    assert run.dispositions[0].reason is m.Disposition.NO_STOP_DISTANCE


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_nan_decision_is_explicit_unavailable_not_false(m: ModuleType, mode: str) -> None:
    run = simulate(m, mode, make(m), {"S0": [float("nan"), 1, 0, 0]})
    assert not run.valid and run.refusal.reason is m.TimedRefusal.UNAVAILABLE_SIGNAL
    assert run.refusal.source_indices == (252,)
    assert not run.trades and run.dispositions[0].reason is m.Disposition.UNAVAILABLE


@pytest.mark.parametrize(
    "capital", [Decimal("NaN"), Decimal("Infinity"), Decimal(-1), Decimal(0), 10000, True]
)
def test_malformed_timed_starting_capital_rejected_even_without_signals(
    m: ModuleType, capital: Any
) -> None:
    goal = load_goal()
    simulator = PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=3,
    )
    fixture = make(m)
    with pytest.raises((TypeError, ValueError)):
        simulator.run_time_resolved(
            strategy(),
            panel(fixture),
            {"S0": np.zeros(4)},
            {"S0": np.full(4, 5.0)},
            fixture=fixture,
            source_indices=(252, 253, 254, 255),
            starting_equity=capital,
        )


def test_typed_inventory_and_invalid_run_fields_refuse_forgery(m: ModuleType) -> None:
    run = simulate(m, "signal", make(m), {"S0": [1, 0, 0, 0]})
    trade = run.trades[0]
    with pytest.raises((TypeError, ValueError)):
        replace(trade, original_quantity=True)
    with pytest.raises((TypeError, ValueError)):
        replace(trade.entry, source_index=True)
    with pytest.raises((TypeError, ValueError)):
        replace(trade, remaining_quantity=0)
    refusal = m.RunRefusal(m.TimedRefusal.LIQUIDITY_UNAVAILABLE, ("S0",), (253,))
    with pytest.raises((TypeError, ValueError)):
        replace(run, refusal=refusal, final_equity=Decimal(10000))


def test_three_nonterminating_allocations_conserve_original_fee_components_exactly(
    m: ModuleType,
) -> None:
    from dataclasses import fields

    fixture = change(m, make(m), "S0", 3, proxy="60", open="94", high="94", low="93", close="94")
    fixture = change(m, fixture, "S0", 4, proxy="60")
    fixture = change(m, fixture, "S0", 5, proxy="60")
    run = simulate(m, "signal", fixture, {"S0": [1, 0, 0, 0]})
    trade = run.trades[0]
    assert [e.quantity for e in trade.exits] == [3, 3, 3]
    for component in fields(trade.entry.charges):
        actual = sum(
            (Fraction(getattr(e.allocated_entry_charges, component.name)) for e in trade.exits),
            Fraction(0),
        )
        assert actual == Fraction(getattr(trade.entry.charges, component.name))
        assert getattr(trade.remaining_entry_charges, component.name) == 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_real_evaluate_once_daily_columns_drive_public_timed_entry(
    m: ModuleType, mode: str
) -> None:
    from icarus.engine.runner import evaluate_once

    fixture = make(m)
    daily = panel(fixture)
    candidate = strategy()
    columns = evaluate_once(
        candidate, daily, default_registry(), source_indices=(252, 253, 254, 255)
    )
    goal = load_goal()
    common: dict[str, Any] = dict(
        costs=CostModel(goal.costs), fills=FillModel(goal.execution_realism), stale_after_sessions=3
    )
    simulator: Any = (
        SignalSimulator(notional_inr=Decimal(1000), **common)
        if mode == "signal"
        else (PortfolioSimulator(risk=goal.risk, **common))
    )
    kwargs: dict[str, Any] = dict(
        fixture=fixture, source_indices=columns.source_indices, ranks=columns.ranks
    )
    if mode == "portfolio":
        kwargs["starting_equity"] = Decimal(10000)
    run = simulator.run_time_resolved(candidate, daily, columns.signals, columns.stops, **kwargs)
    assert run.valid and len(run.trades) == 1
    assert run.trades[0].signal_id.decision_index == 252
    assert run.trades[0].entry.source_index == 253
    assert run.trades[0].original_quantity == (9 if mode == "signal" else 1)


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_intraday_strategy_clock_is_explicitly_unsupported(m: ModuleType, mode: str) -> None:
    from icarus.strategy.dsl import Timeframe

    candidate = strategy().model_copy(update={"timeframe": Timeframe.M15})
    run = simulate(m, mode, make(m), {"S0": [1, 0, 0, 0]}, candidate=candidate)
    assert not run.valid and run.refusal.reason is m.TimedRefusal.UNSUPPORTED_CLOCK


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_both_trigger_order_and_late_proxy_refuse_whole_book(m: ModuleType, mode: str) -> None:
    from icarus.strategy.dsl import ExitRule

    candidate = strategy().model_copy(
        update={
            "exits": (*strategy().exits, ExitRule(rule="take_profit_r", literals={"r_multiple": 1}))
        }
    )
    fixture = change(m, make(m), "S0", 3, low="94", high="106")
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]}, candidate=candidate)
    assert not run.valid and run.refusal.reason is m.TimedRefusal.ORDER_UNAVAILABLE
    fixture = make(m)
    row = fixture.refinements[0].bars[2]
    rows = (
        *fixture.refinements[0].bars[:2],
        replace(row, opening=replace(row.opening, available_ts=row.bar.ts + timedelta(seconds=1))),
        *fixture.refinements[0].bars[3:],
    )
    fixture = bind(m, fixture.sessions, (m.Refinement("S0", rows),))
    run = simulate(m, mode, fixture, {"S0": [1, 0, 0, 0]})
    assert not run.valid and run.refusal.reason is m.TimedRefusal.LATE_OPENING_LIQUIDITY


def test_heat_limit_and_invalid_cash_never_become_an_admission(m: ModuleType) -> None:
    fixture = make(m, ("S0", "S1"))
    risk = load_goal().risk.model_copy(update={"max_portfolio_heat": 0.005})
    run = simulate(m, "portfolio", fixture, {s: [1, 0, 0, 0] for s in ("S0", "S1")}, risk=risk)
    assert run.valid and len(run.trades) == 1
    assert run.dispositions[1].reason is m.Disposition.HEAT_CAP


def test_cash_refusal_includes_acquisition_fees_and_does_not_resize(m: ModuleType) -> None:
    symbols = ("S0", "S1", "S2", "S3")
    fixture = make(m, symbols)
    series = tuple(
        m.Refinement(
            r.symbol, tuple(replace(b, bar=replace(b.bar, low=Decimal(100))) for b in r.bars)
        )
        for r in fixture.refinements
    )
    fixture = bind(m, fixture.sessions, series)
    run = simulate(
        m, "portfolio", fixture, {s: [1, 0, 0, 0] for s in symbols}, capital="400.2", stop=0.1
    )
    assert run.valid and len(run.trades) == 3
    assert all(t.original_quantity == 1 for t in run.trades)
    assert run.dispositions[-1].reason is m.Disposition.INSUFFICIENT_CASH
    assert run.cash >= 0


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_declared_crypto_universe_refuses_even_without_signals(
    m: ModuleType, mode: str, monkeypatch: Any
) -> None:
    candidate = strategy().model_copy(update={"universe": "crypto_liquid"})

    def forbidden(*args: Any) -> Any:
        pytest.fail("unsupported declared universe reached execution")

    monkeypatch.setattr(FillModel, "execute", forbidden)
    run = simulate(m, mode, make(m), {"S0": [0, 0, 0, 0]}, candidate=candidate)
    assert not run.valid and run.refusal.reason is m.TimedRefusal.UNSUPPORTED_UNIVERSE


@pytest.mark.parametrize("ineligible", ["held", "not_tradable"])
def test_ineligible_ranked_signal_cannot_change_cash_constrained_fallback(
    m: ModuleType, ineligible: str
) -> None:
    symbols = ("A0", "A1", "S0", "S1", "S2")
    fixture = make(m, symbols)
    series = tuple(
        m.Refinement(
            r.symbol, tuple(replace(b, bar=replace(b.bar, low=Decimal(100))) for b in r.bars)
        )
        for r in fixture.refinements
    )
    fixture = bind(m, fixture.sessions, series)
    signals = {
        "A0": [1, 0, 0, 0],
        "A1": [1, 0, 0, 0],
        "S0": [0, 1, 0, 0],
        "S1": [0, 1, 0, 0],
        "S2": [0, 0, 0, 0],
    }
    ranks = {
        s: np.full(4, rank, dtype=np.float64)
        for s, rank in zip(symbols, (10, 0, 1, 2, 20), strict=True)
    }
    baseline = simulate(m, "portfolio", fixture, signals, capital="400.2", stop=0.1, ranks=ranks)
    daily = panel(fixture)
    if ineligible == "held":
        signals["A0"][1] = 1
    else:
        signals["S2"][1] = 1
        daily.tradable[daily.index_of("S2"), 1] = False
    run = simulate(
        m, "portfolio", fixture, signals, capital="400.2", stop=0.1, ranks=ranks, daily=daily
    )
    assert run.valid and baseline.valid
    assert [t.signal_id.symbol for t in run.trades] == ["A0", "A1", "S0"]
    assert [t.signal_id.symbol for t in baseline.trades] == [t.signal_id.symbol for t in run.trades]
    assert run.cash == baseline.cash
