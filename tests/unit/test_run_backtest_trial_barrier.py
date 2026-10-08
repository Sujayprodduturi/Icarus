"""The old JSON path and pre-commit metric logs cannot bypass counted persistence."""

from __future__ import annotations

import traceback
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from scripts import run_backtest
from tests.unit.test_runner import STRATEGY, _always_signal_strategy, _column_panel

from icarus.common.config import load_goal
from icarus.engine import runner
from icarus.engine.backtest import Window
from icarus.state.trial_ledger import (
    TrialBatchReceipt,
    TrialBatchTerminal,
    TrialLedgerUnavailable,
    TrialReservationAuthorization,
    TrialTerminalState,
)
from icarus.strategy.dsl import parse_strategy
from icarus.strategy.library import default_registry


def test_non_none_legacy_ledger_refuses_before_strategy_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    goal = load_goal()
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    evaluated = False

    def forbidden(*_args: object, **_kwargs: object) -> object:
        nonlocal evaluated
        evaluated = True
        raise AssertionError("evaluation crossed the ledger barrier")

    monkeypatch.setattr(runner, "evaluate_once", forbidden)
    with pytest.raises(Exception, match=r"Postgres|ledger"):
        runner.run_walk_forward(
            strategy,
            _column_panel(size=8),
            goal=goal,
            registry=default_registry(),
            ledger=tmp_path / "legacy.json",
        )
    assert evaluated is False


def test_fold_progress_log_contains_no_metric_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[str, dict[str, object]]] = []

    class CaptureLog:
        def info(self, event: str, **fields: Any) -> None:
            events.append((event, fields))

    monkeypatch.setattr(runner, "log", CaptureLog())
    monkeypatch.setattr(
        runner,
        "walk_forward_windows",
        lambda *_args: [Window(0, 2, 3, 7, seam_sessions=1)],
    )
    runner.run_walk_forward(
        _always_signal_strategy(),
        _column_panel(size=8),
        goal=load_goal(),
        registry=default_registry(),
        ledger=None,
    )

    fold_fields = next(fields for event, fields in events if event == "fold complete")
    assert fold_fields == {"fold": 0, "test": "2015-01-04..2015-01-07"}


def _receipt(authorization: TrialReservationAuthorization) -> TrialBatchReceipt:
    run_group_id = uuid4()
    return TrialBatchReceipt(
        run_group_id=run_group_id,
        reservation_sha256="a" * 64,
        evaluation_ids=(uuid4(),),
        lifetime_trial_count=1,
        newly_created=authorization is TrialReservationAuthorization.NEW_EVALUATION,
        authorization=authorization,
    )


def test_recovery_only_receipt_never_reauthorizes_portfolio_evaluation() -> None:
    receipt = _receipt(TrialReservationAuthorization.RECOVERY_ONLY)
    evaluated = False

    class Ledger:
        def reserve(self, _batch: object) -> TrialBatchReceipt:
            return receipt

    def evaluate() -> object:
        nonlocal evaluated
        evaluated = True
        raise AssertionError("recovery receipt crossed the evaluation barrier")

    with pytest.raises(Exception, match=r"recovery|authorize"):
        run_backtest._execute_counted_portfolio(
            cast(Any, Ledger()), cast(Any, object()), cast(Any, evaluate)
        )
    assert evaluated is False


def test_completion_ack_loss_recovers_terminal_without_reevaluation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt(TrialReservationAuthorization.NEW_EVALUATION)
    terminal = TrialBatchTerminal(
        receipt.run_group_id,
        TrialTerminalState.COMPLETED,
        "b" * 64,
        None,
    )
    result = runner.BacktestResult("synthetic")

    class Ledger:
        completions = 0

        def reserve(self, _batch: object) -> TrialBatchReceipt:
            return receipt

        def complete(self, _receipt: object, _results: object) -> TrialBatchTerminal:
            self.completions += 1
            if self.completions == 1:
                raise TrialLedgerUnavailable("completion acknowledgement lost")
            return terminal

    ledger = Ledger()
    evaluations = 0

    def evaluate() -> runner.BacktestResult:
        nonlocal evaluations
        evaluations += 1
        return result

    assert (
        run_backtest._execute_counted_portfolio(cast(Any, ledger), cast(Any, object()), evaluate)
        is result
    )
    assert evaluations == 1
    assert ledger.completions == 2
    assert capsys.readouterr() == ("", "")


def test_unverified_completion_exposes_no_result(
    capsys: pytest.CaptureFixture[str],
) -> None:
    receipt = _receipt(TrialReservationAuthorization.NEW_EVALUATION)
    result = runner.BacktestResult("secret-metric-result")

    class Ledger:
        def reserve(self, _batch: object) -> TrialBatchReceipt:
            return receipt

        def complete(self, _receipt: object, _results: object) -> TrialBatchTerminal:
            raise TrialLedgerUnavailable("datastore down")

    released: list[runner.BacktestResult] = []
    with pytest.raises(TrialLedgerUnavailable, match="datastore down"):
        released.append(
            run_backtest._execute_counted_portfolio(
                cast(Any, Ledger()), cast(Any, object()), lambda: result
            )
        )
    assert released == []
    assert capsys.readouterr() == ("", "")


@pytest.mark.parametrize("failure_stage", ["evaluate", "serialize"])
def test_evaluation_and_serialization_failures_are_counted_and_sanitized(
    failure_stage: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    receipt = _receipt(TrialReservationAuthorization.NEW_EVALUATION)
    sentinel = "SECRET_OUTCOME_SHARPE_9_99"
    failures: list[str] = []

    class Ledger:
        def reserve(self, _batch: object) -> TrialBatchReceipt:
            return receipt

        def fail(self, _receipt: object, *, failure_code: str) -> TrialBatchTerminal:
            failures.append(failure_code)
            return TrialBatchTerminal(
                receipt.run_group_id,
                TrialTerminalState.FAILED,
                None,
                failure_code,
            )

    def evaluate() -> runner.BacktestResult:
        if failure_stage == "evaluate":
            raise ValueError(sentinel)
        return runner.BacktestResult("synthetic")

    if failure_stage == "serialize":
        monkeypatch.setattr(
            run_backtest,
            "_portfolio_result",
            lambda _result: (_ for _ in ()).throw(ValueError(sentinel)),
        )

    with pytest.raises(RuntimeError) as caught:
        run_backtest._execute_counted_portfolio(cast(Any, Ledger()), cast(Any, object()), evaluate)
    rendered = "".join(traceback.format_exception(caught.value))
    assert failures == ["EVALUATION_FAILED"]
    assert sentinel not in rendered


def test_canonical_cli_has_no_legacy_json_ledger_calls() -> None:
    source = Path(run_backtest.__file__).read_text(encoding="utf-8")
    for forbidden in ("DEFAULT_TRIAL_LEDGER", "read_trials(", "record_trial("):
        assert forbidden not in source


def test_input_replacement_during_load_refuses_before_reservation(tmp_path: Path) -> None:
    source = tmp_path / "panel.npz"
    source.write_bytes(b"consumed-version")
    reserved = False

    def replacing_loader(path: Path) -> object:
        assert path == source
        source.write_bytes(b"replacement-version")
        return object()

    def reserve_probe() -> None:
        nonlocal reserved
        reserved = True

    with pytest.raises(SystemExit, match="changed while it was being loaded"):
        run_backtest._load_stable(source, replacing_loader)
        reserve_probe()
    assert reserved is False
