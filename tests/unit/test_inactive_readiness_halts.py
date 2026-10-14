"""Invented witnesses for inactive cells and point-in-time availability halts."""

import json
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pytest
from tests.unit import test_timed_runner as assembly_helpers
from tests.unit import test_timed_strategy_management as helpers

from icarus.common.config import load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.data_readiness import BundlePreflight
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.timed_runner import AssembledTimedInputs, InputUnavailable, assemble_timed_inputs
from icarus.engine.timed_simulation import (
    Refinement,
    TimedFixture,
    TimedRefusal,
    TimedRun,
    timed_fixture_digest,
)
from icarus.strategy.dsl import Bars, Panel


def _run_inactive(*, holding: bool) -> TimedRun:
    original = helpers.fixture(("AAA", "BBB"), days=3, source_start=252)
    daily = helpers.panel(original)
    inactive = frozenset({("AAA", 254)} if holding else {("AAA", 252)})
    raw = tuple(
        Refinement(
            item.symbol,
            tuple(row for row in item.bars if (item.symbol, row.session_index) not in inactive),
        )
        for item in original.refinements
    )
    source = replace(original.source, sha256=timed_fixture_digest(original.sessions, raw, inactive))
    sessions = tuple(replace(session, source=source) for session in original.sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(row, source=source, opening=helpers.bound_opening(row, source))
                for row in item.bars
            ),
        )
        for item in raw
    )
    fixture = TimedFixture(sessions, refinements, source, inactive)
    assert source.sha256 == timed_fixture_digest(sessions, refinements, inactive)
    assert all(session.source == source for session in sessions)
    assert all(
        row.source == source and row.opening is not None and row.opening.source == source
        for item in refinements
        for row in item.bars
    )
    bars: dict[str, Bars] = {}
    tradable: dict[str, Any] = {}
    signals: dict[str, Any] = {}
    stops: dict[str, Any] = {}
    for symbol, observed in zip(daily.symbols, daily.bars, strict=True):
        absent = np.array([(symbol, session.index) in inactive for session in sessions])
        columns = [
            getattr(observed, name).copy() for name in ("open", "high", "low", "close", "volume")
        ]
        for column in columns:
            column[absent] = np.nan
        bars[symbol] = Bars(observed.ts, *columns)
        tradable[symbol] = ~absent
        signals[symbol] = np.zeros(3)
        stops[symbol] = np.full(3, 5.0)
        signals[symbol][absent] = np.nan
        stops[symbol][absent] = np.nan
    if holding:
        signals["AAA"][0] = 1.0
    goal = load_goal()
    simulator = PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=3,
    )
    return simulator.run_time_resolved(
        helpers.card("baseline_buy_and_hold"),
        Panel.build(bars, tradable),
        signals,
        stops,
        fixture=fixture,
        source_indices=tuple(session.index for session in sessions),
        starting_equity=Decimal("10000"),
    )


def test_mixed_inactive_and_active_session_preserves_cash_without_fills() -> None:
    result = _run_inactive(holding=False)
    assert result.valid and result.refusal is None
    assert result.cash == result.realized_equity == result.final_equity == Decimal("10000")
    assert not result.trades and not result.attempts


def test_held_ten_shares_disappearing_into_inactive_cell_halts_without_exit() -> None:
    result = _run_inactive(holding=True)
    assert not result.valid and result.refusal is not None
    assert result.refusal.reason is TimedRefusal.MISSING_REFINEMENT
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.original_quantity == trade.remaining_quantity == 10
    assert not trade.exits
    assert result.cash is result.realized_equity is result.final_equity is None


def test_pit_available_fifteen_minutes_after_indexed_event_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[BundlePreflight] = []

    def capture(value: BundlePreflight) -> AssembledTimedInputs:
        captured.append(value)
        return assemble_timed_inputs(value)

    # Reuse the existing seven-artifact invented fixture without editing its owner.
    monkeypatch.setattr(assembly_helpers, "assemble_timed_inputs", capture)
    assembly_helpers.test_all_seven_artifacts_assemble_one_causal_panel_and_timed_fixture()
    preflight = captured[0]
    pit = next(item for item in preflight.artifacts if item.role == "pit_universe")
    rows = [json.loads(line) for line in pit.payload.splitlines()]
    event = datetime.fromisoformat(rows[0]["event_ts"])
    later = event + timedelta(minutes=15)
    assert event.date() == later.date()
    assert datetime.fromisoformat(pit.metadata["coverage_start"]) <= later
    assert later <= datetime.fromisoformat(pit.metadata["coverage_end"])
    rows[0]["available_ts"] = later.isoformat().replace("+00:00", "Z")
    changed = assembly_helpers._captured("pit_universe", assembly_helpers._lines(*rows))
    invalid = replace(
        preflight,
        artifacts=tuple(
            changed if item.role == "pit_universe" else item for item in preflight.artifacts
        ),
    )
    with pytest.raises(InputUnavailable, match=r"^PIT_IDENTITY$"):
        assemble_timed_inputs(invalid)


def test_cross_date_equity_session_refuses_before_reinterpreting_split() -> None:
    from icarus.engine.timed_runner import parse_calendar_jsonl

    row = {
        "schema_version": 1,
        "record_id": "invented-cross-date",
        "revision": "r1",
        "source_index": 0,
        "session_date": "2023-01-01",
        "state": "special",
        "open_ts": "2022-12-31T18:31:00Z",
        "close_ts": "2022-12-31T18:46:00Z",
    }
    with pytest.raises(InputUnavailable, match="CALENDAR_DATE_TIME"):
        parse_calendar_jsonl(json.dumps(row).encode())
