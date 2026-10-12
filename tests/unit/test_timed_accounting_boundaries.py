"""Independent accounting boundaries for the declared synthetic timed lane."""

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from pathlib import Path
from types import ModuleType
from typing import Any

import numpy as np
import pytest

from icarus.common.config import load_goal
from icarus.engine.costmodel import Charges, CostModel
from icarus.engine.fills import FillModel, SimBar
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.signaltest import SignalSimulator
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

_OPEN = datetime(2024, 1, 2, 3, 45, tzinfo=UTC)
_BAR = timedelta(minutes=15)
_SESSION_STEP = timedelta(minutes=45)
_SYMBOL = "ACCOUNTING_SYNTHETIC"
_STARTING_EQUITY = Decimal("4000")


@pytest.fixture
def m() -> ModuleType:
    return import_module("icarus.engine.timed_simulation")


def _bound_fixture(m: ModuleType, *, leave_residual_open: bool) -> Any:
    """Declare three invented, non-overlapping sessions on one IST date."""
    placeholder = m.SourceDeclaration("invented-accounting-boundary", "v1", "0" * 64)
    sessions = tuple(
        m.Session(
            900 + offset,
            _OPEN + offset * _SESSION_STEP,
            _OPEN + offset * _SESSION_STEP + 2 * _BAR,
            placeholder,
        )
        for offset in range(3)
    )

    # Session 0 emits signal A. Session 1 admits seven shares, then the stop can
    # sell only two. Session 2 either cannot fill the latched residual, or closes
    # it before admitting signal B and stopping B later in the same invented day.
    rows = (
        (("100", "100", "100", "100", "1000"), "1000"),
        (("100", "100", "100", "100", "1000"), "1000"),
        (("100", "100", "100", "100", "1000"), "140"),
        (("100", "100", "98", "100", "40"), "40"),
        (("120", "120", "120", "120", "0"), "0")
        if leave_residual_open
        else (("100", "100", "100", "100", "1000"), "1000"),
        (("120", "120", "120", "120", "0"), "0")
        if leave_residual_open
        else (("100", "100", "98", "100", "1000"), "1000"),
    )
    bars = []
    for bar_number, (ohlcv, opening_quantity) in enumerate(rows):
        session = sessions[bar_number // 2]
        bar_ts = session.open_ts + (bar_number % 2) * _BAR
        open_, high, low, close, volume = (Decimal(value) for value in ohlcv)
        bars.append(
            m.ReplayBar(
                session.index,
                SimBar(bar_ts, open_, high, low, close, volume),
                bar_ts + _BAR,
                m.OpeningLiquidity(Decimal(opening_quantity), bar_ts, placeholder),
                placeholder,
            )
        )
    refinements = (m.Refinement(_SYMBOL, tuple(bars)),)
    source = replace(
        placeholder,
        sha256=m.timed_fixture_digest(sessions, refinements),
    )
    rebound_sessions = tuple(replace(session, source=source) for session in sessions)
    rebound_bars = tuple(
        replace(
            row,
            source=source,
            opening=replace(row.opening, source=source),
        )
        for row in bars
    )
    return m.TimedFixture(
        rebound_sessions,
        (m.Refinement(_SYMBOL, rebound_bars),),
        source,
    )


def _panel(fixture: Any) -> Panel:
    dates = np.array(
        [np.datetime64(session.open_ts.replace(tzinfo=None), "ns") for session in fixture.sessions]
    )
    bars = fixture.refinements[0].bars
    grouped = tuple(bars[offset : offset + 2] for offset in range(0, len(bars), 2))
    daily = Bars(
        dates,
        np.array([float(rows[0].bar.open) for rows in grouped]),
        np.array([float(max(row.bar.high for row in rows)) for rows in grouped]),
        np.array([float(min(row.bar.low for row in rows)) for rows in grouped]),
        np.array([float(rows[-1].bar.close) for rows in grouped]),
        np.array([float(sum((row.bar.volume for row in rows), Decimal(0))) for rows in grouped]),
    )
    return Panel.build({_SYMBOL: daily}, {_SYMBOL: np.ones(3, dtype=np.bool_)})


def _strategy() -> Any:
    return parse_strategy(
        Path("strategies/baseline_buy_and_hold.yaml").read_text(),
        registry=default_registry(),
        max_risk_r=0.005,
    )


def _run(m: ModuleType, fixture: Any, *, mode: str, signals: list[int]) -> Any:
    goal = load_goal()
    common: dict[str, Any] = {
        "costs": CostModel(goal.costs),
        "fills": FillModel(goal.execution_realism),
        "stale_after_sessions": 3,
    }
    simulator: Any
    if mode == "portfolio":
        simulator = PortfolioSimulator(risk=goal.risk, **common)
    else:
        simulator = SignalSimulator(notional_inr=Decimal("1000"), **common)
    kwargs: dict[str, Any] = {}
    if mode == "portfolio":
        kwargs["starting_equity"] = _STARTING_EQUITY
    return simulator.run_time_resolved(
        _strategy(),
        _panel(fixture),
        {_SYMBOL: np.array(signals, dtype=np.float64)},
        {_SYMBOL: np.ones(3, dtype=np.float64)},
        fixture=fixture,
        source_indices=tuple(session.index for session in fixture.sessions),
        **kwargs,
    )


def _component(charges: Charges, name: str) -> Decimal:
    value = getattr(charges, name)
    assert isinstance(value, Decimal)
    return value


def test_partial_exit_conserves_entry_charges_cash_and_open_mark(m: ModuleType) -> None:
    run = _run(m, _bound_fixture(m, leave_residual_open=True), mode="portfolio", signals=[1, 0, 0])

    assert run.valid and len(run.trades) == 1
    trade = run.trades[0]
    assert (trade.original_quantity, [leg.quantity for leg in trade.exits]) == (7, [2])
    assert trade.remaining_quantity == 5
    allocation = trade.exits[0].allocated_entry_charges
    assert allocation is not None
    for component in fields(Charges):
        allocated = _component(allocation, component.name)
        original = _component(trade.entry.charges, component.name)
        remaining = _component(trade.remaining_entry_charges, component.name)
        assert allocated == original * Decimal(2) / Decimal(7)
        assert allocated + remaining == original

    exit_leg = trade.exits[0]
    expected_cash = (
        _STARTING_EQUITY
        - trade.entry.price * 7
        - trade.entry.charges.total
        + exit_leg.price * 2
        - exit_leg.charges.total
    )
    expected_realized = (
        _STARTING_EQUITY
        + (exit_leg.price - trade.entry.price) * 2
        - allocation.total
        - exit_leg.charges.total
    )
    assert run.cash == expected_cash
    assert run.realized_equity == expected_realized
    assert run.cash == expected_realized - (
        trade.entry.price * 5 + trade.remaining_entry_charges.total
    )
    assert run.final_equity == run.cash + Decimal(120) * 5
    assert (
        expected_realized + (Decimal(120) - trade.entry.price) * 5 - run.final_equity
        == trade.remaining_entry_charges.total
    )


def test_delivery_fee_scope_is_book_wide_but_signal_ids_are_independent(m: ModuleType) -> None:
    fixture = _bound_fixture(m, leave_residual_open=False)
    portfolio = _run(m, fixture, mode="portfolio", signals=[1, 1, 0])
    standalone = _run(m, fixture, mode="signal", signals=[1, 1, 0])

    assert portfolio.valid and standalone.valid
    assert len(portfolio.trades) == len(standalone.trades) == 2
    assert portfolio.trades[0].signal_id != portfolio.trades[1].signal_id
    assert [leg.quantity for leg in portfolio.trades[0].exits] == [2, 5]
    assert all(trade.remaining_quantity == 0 for trade in portfolio.trades)

    portfolio_dp = [
        sum((leg.charges.dp_charge for leg in trade.exits), Decimal(0))
        for trade in portfolio.trades
    ]
    standalone_dp = [
        sum((leg.charges.dp_charge for leg in trade.exits), Decimal(0))
        for trade in standalone.trades
    ]
    assert portfolio_dp == [Decimal("15.34"), Decimal(0)]
    assert standalone_dp == [Decimal("15.34"), Decimal("15.34")]

    expected_cash = _STARTING_EQUITY
    for trade in portfolio.trades:
        expected_cash -= trade.entry.price * trade.entry.quantity + trade.entry.charges.total
        expected_cash += sum(
            (leg.price * leg.quantity - leg.charges.total for leg in trade.exits),
            Decimal(0),
        )
    assert portfolio.cash == portfolio.realized_equity == portfolio.final_equity == expected_cash
