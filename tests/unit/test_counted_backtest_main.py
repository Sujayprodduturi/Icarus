"""The public command must keep every result behind the counted-save barrier."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import pytest
from scripts import run_backtest
from tests.unit.test_runner import STRATEGY, _column_panel

from icarus.common.config import GoalConfig, load_goal
from icarus.engine.runner import BacktestResult
from icarus.state.trial_ledger import (
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialBatchTerminal,
    TrialEvaluationResult,
    TrialIdentityConflict,
    TrialLedgerUnavailable,
    TrialReservationAuthorization,
    TrialTerminalState,
)
from icarus.strategy.dsl import Panel, Registry, StrategyCandidate, parse_strategy

SENTINEL = "UNSAVED_OUTCOME_SENTINEL"


class LedgerProbe:
    def __init__(self) -> None:
        self.batches: list[TrialBatchReservation] = []
        self.failures: list[str] = []
        self.completions = 0
        self.reserve_error = False
        self.complete_error = False
        self.recovery_only = False

    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt:
        if self.reserve_error:
            raise TrialLedgerUnavailable("reservation unavailable")
        self.batches.append(batch)
        return TrialBatchReceipt(
            batch.run_group_id,
            "a" * 64,
            (batch.run_group_id,),
            len(self.batches),
            not self.recovery_only,
            TrialReservationAuthorization.RECOVERY_ONLY
            if self.recovery_only
            else TrialReservationAuthorization.NEW_EVALUATION,
        )

    def complete(
        self, receipt: TrialBatchReceipt, _rows: tuple[TrialEvaluationResult, ...]
    ) -> TrialBatchTerminal:
        self.completions += 1
        if self.complete_error:
            raise TrialLedgerUnavailable("completion unavailable")
        return TrialBatchTerminal(
            receipt.run_group_id, TrialTerminalState.COMPLETED, "b" * 64, None
        )

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> TrialBatchTerminal:
        self.failures.append(failure_code)
        return TrialBatchTerminal(
            receipt.run_group_id, TrialTerminalState.FAILED, None, failure_code
        )

    def lifetime_count(self) -> int:
        return len(self.batches)


@dataclass
class MainHarness:
    ledger: LedgerProbe
    goal_path: Path
    panel_path: Path
    strategy_path: Path
    output_path: Path
    goal: GoalConfig
    panel: Panel
    evaluations: list[dict[str, object]]
    sheets: list[list[BacktestResult]]
    logs: list[tuple[str, dict[str, object]]]


@pytest.fixture
def main_harness(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> MainHarness:
    goal_path = tmp_path / "goal.yaml"
    goal_path.write_bytes((repo_root / "goal.yaml").read_bytes())
    panel_path = tmp_path / "synthetic-panel.npz"
    panel_path.write_bytes(b"synthetic-panel-loader-fixture")
    strategy_path = tmp_path / "synthetic-strategy.yaml"
    strategy_path.write_text(STRATEGY, encoding="utf-8")
    output_path = tmp_path / "results.json"
    ledger = LedgerProbe()
    harness = MainHarness(
        ledger,
        goal_path,
        panel_path,
        strategy_path,
        output_path,
        load_goal(goal_path),
        _column_panel(size=8),
        [],
        [],
        [],
    )

    class EngineProbe:
        def dispose(self) -> None:
            pass

    class LogProbe:
        def info(self, event: str, **fields: object) -> None:
            harness.logs.append((event, fields))

    def evaluate(*_args: object, **kwargs: object) -> BacktestResult:
        assert ledger.batches, "evaluation started before reservation"
        assert kwargs["ledger"] is None, "canonical command used the legacy JSON writer"
        harness.evaluations.append(kwargs)
        return BacktestResult(SENTINEL)

    def print_sheet(results: list[BacktestResult], _goal: object) -> None:
        harness.sheets.append(results)

    monkeypatch.setattr(run_backtest, "GOAL", goal_path)
    monkeypatch.setattr(run_backtest, "load_panel", lambda _path: harness.panel)
    monkeypatch.setattr(run_backtest, "create_engine", lambda _dsn: EngineProbe())
    monkeypatch.setattr(run_backtest, "PostgresTrialLedger", lambda _engine: ledger)
    monkeypatch.setattr(run_backtest, "run_walk_forward", evaluate)
    monkeypatch.setattr(run_backtest, "_print_sheet", print_sheet)
    monkeypatch.setattr(run_backtest, "log", LogProbe())
    monkeypatch.setenv("ICARUS_PG_DSN", "synthetic-fixture-dsn-never-connected")
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_backtest", str(strategy_path), "--panel", str(panel_path), "--out", str(output_path)],
    )
    return harness


def _assert_no_release(harness: MainHarness, capture: pytest.CaptureFixture[str]) -> None:
    captured = capture.readouterr()
    assert not harness.output_path.exists()
    assert harness.sheets == []
    assert captured.out == captured.err == ""
    assert SENTINEL not in repr(harness.logs)


def test_main_reservation_outage_never_evaluates_or_releases(
    main_harness: MainHarness, capsys: pytest.CaptureFixture[str]
) -> None:
    main_harness.ledger.reserve_error = True
    with pytest.raises(TrialLedgerUnavailable, match="reservation"):
        run_backtest.main()
    assert main_harness.evaluations == []
    _assert_no_release(main_harness, capsys)


def test_main_recovery_receipt_never_evaluates_or_releases(
    main_harness: MainHarness, capsys: pytest.CaptureFixture[str]
) -> None:
    main_harness.ledger.recovery_only = True
    with pytest.raises(TrialIdentityConflict, match="recovery"):
        run_backtest.main()
    assert main_harness.evaluations == []
    _assert_no_release(main_harness, capsys)


def test_main_completion_outage_releases_no_sheet_or_artifact(
    main_harness: MainHarness, capsys: pytest.CaptureFixture[str]
) -> None:
    main_harness.ledger.complete_error = True
    with pytest.raises(TrialLedgerUnavailable, match="completion"):
        run_backtest.main()
    assert len(main_harness.evaluations) == 1
    assert main_harness.ledger.completions == 2
    _assert_no_release(main_harness, capsys)


def test_main_identical_operator_reruns_are_fresh_counted_attempts(
    main_harness: MainHarness, capsys: pytest.CaptureFixture[str]
) -> None:
    assert run_backtest.main() == 0
    assert run_backtest.main() == 0
    first, second = main_harness.ledger.batches
    assert first.run_group_id != second.run_group_id
    assert first.strategy_sha256 == second.strategy_sha256
    assert first.panel_sha256 == second.panel_sha256
    assert first.config_sha256 == second.config_sha256
    assert main_harness.ledger.lifetime_count() == 2
    assert len(main_harness.evaluations) == len(main_harness.sheets) == 2
    assert main_harness.output_path.exists()
    assert "lifetime trials on the ledger: 2" in capsys.readouterr().out


def test_main_evaluation_failure_records_failed_without_exposing_outcome(
    main_harness: MainHarness,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_evaluation(*_args: object, **_kwargs: object) -> BacktestResult:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(run_backtest, "run_walk_forward", fail_evaluation)
    with pytest.raises(RuntimeError, match="evaluation failed") as caught:
        run_backtest.main()
    assert main_harness.ledger.failures == ["EVALUATION_FAILED"]
    assert main_harness.ledger.lifetime_count() == 1
    assert SENTINEL not in str(caught.value)
    _assert_no_release(main_harness, capsys)


@pytest.mark.parametrize("input_name", ["goal", "panel", "strategy"])
def test_main_changed_input_refuses_before_reservation(
    main_harness: MainHarness,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    input_name: str,
) -> None:
    if input_name == "goal":

        def change_goal(path: Path) -> GoalConfig:
            goal = load_goal(path)
            path.write_bytes(path.read_bytes() + b"\n# changed during load\n")
            return goal

        monkeypatch.setattr(run_backtest, "load_goal", change_goal)
    elif input_name == "panel":

        def change_panel(path: Path) -> Panel:
            path.write_bytes(b"replacement-panel")
            return main_harness.panel

        monkeypatch.setattr(run_backtest, "load_panel", change_panel)
    else:

        def change_strategy(
            text: str,
            *,
            registry: Registry,
            max_risk_r: float,
            available_feeds: frozenset[str] = frozenset(),
        ) -> StrategyCandidate:
            strategy = parse_strategy(
                text,
                registry=registry,
                max_risk_r=max_risk_r,
                available_feeds=available_feeds,
            )
            path = main_harness.strategy_path
            path.write_bytes(path.read_bytes() + b"\n# changed during load\n")
            return strategy

        monkeypatch.setattr(run_backtest, "parse_strategy", change_strategy)
    with pytest.raises(SystemExit, match="changed while it was being loaded"):
        run_backtest.main()
    assert main_harness.ledger.batches == []
    assert main_harness.evaluations == []
    _assert_no_release(main_harness, capsys)
