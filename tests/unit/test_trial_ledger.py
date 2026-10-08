"""Counted-trial contracts: malformed or ambiguous evidence must fail before persistence."""

from __future__ import annotations

import json
import traceback
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from icarus.state.trial_ledger import (
    EvaluationReservation,
    PostgresTrialLedger,
    TrialBatchReservation,
    TrialEvaluationResult,
    TrialKind,
    TrialLedgerUnavailable,
    TrialOrigin,
    canonical_reservation_sha256,
    read_legacy_portfolio_ledger,
)


def _evaluation(
    ordinal: int,
    kind: TrialKind,
    *,
    fold_index: int | None,
    start: int,
    end: int,
    reset: str,
) -> EvaluationReservation:
    return EvaluationReservation(
        ordinal=ordinal,
        kind=kind,
        fold_index=fold_index,
        start_index=start,
        end_index_exclusive=end,
        start_ts=datetime(2020, 1, 1 + start, tzinfo=UTC),
        end_ts=datetime(2020, 1, end, tzinfo=UTC),
        reset_identity=reset,
    )


def signal_batch() -> TrialBatchReservation:
    return TrialBatchReservation(
        run_group_id=UUID("11111111-1111-4111-8111-111111111111"),
        origin=TrialOrigin.OPERATOR,
        strategy_name="probe",
        strategy_version=2,
        strategy_sha256="a" * 64,
        panel_sha256="b" * 64,
        config_sha256="c" * 64,
        primitives=("close", "sma"),
        evaluations=(
            _evaluation(
                0,
                TrialKind.SIGNAL_FULL,
                fold_index=None,
                start=0,
                end=10,
                reset="continuous_full_development_v1",
            ),
            _evaluation(
                1,
                TrialKind.SIGNAL_FOLD,
                fold_index=0,
                start=2,
                end=5,
                reset="fresh_signal_simulator_per_fold_v1",
            ),
            _evaluation(
                2,
                TrialKind.SIGNAL_FOLD,
                fold_index=1,
                start=6,
                end=9,
                reset="fresh_signal_simulator_per_fold_v1",
            ),
        ),
    )


def test_signal_batch_hash_is_stable_and_binds_every_evaluation() -> None:
    batch = signal_batch()
    assert canonical_reservation_sha256(batch) == canonical_reservation_sha256(batch)
    changed = TrialBatchReservation(
        run_group_id=batch.run_group_id,
        origin=batch.origin,
        strategy_name=batch.strategy_name,
        strategy_version=batch.strategy_version,
        strategy_sha256=batch.strategy_sha256,
        panel_sha256=batch.panel_sha256,
        config_sha256=batch.config_sha256,
        primitives=batch.primitives,
        evaluations=batch.evaluations[:-1],
    )
    assert canonical_reservation_sha256(changed) != canonical_reservation_sha256(batch)


def test_fold_index_must_equal_ordinal_minus_one() -> None:
    batch = signal_batch()
    bad_fold = _evaluation(
        2,
        TrialKind.SIGNAL_FOLD,
        fold_index=0,
        start=6,
        end=9,
        reset="fresh_signal_simulator_per_fold_v1",
    )
    with pytest.raises(ValueError, match="fold_index"):
        TrialBatchReservation(
            run_group_id=batch.run_group_id,
            origin=batch.origin,
            strategy_name=batch.strategy_name,
            strategy_version=batch.strategy_version,
            strategy_sha256=batch.strategy_sha256,
            panel_sha256=batch.panel_sha256,
            config_sha256=batch.config_sha256,
            primitives=batch.primitives,
            evaluations=(batch.evaluations[0], batch.evaluations[1], bad_fold),
        )


def test_signal_batch_rejects_temporally_overlapping_folds_even_if_indices_are_disjoint() -> None:
    batch = signal_batch()
    first = batch.evaluations[1]
    bad_second = replace(
        batch.evaluations[2],
        start_ts=first.start_ts,
        end_ts=first.end_ts,
    )
    with pytest.raises(ValueError, match="temporally ordered and non-overlapping"):
        replace(batch, evaluations=(batch.evaluations[0], first, bad_second))


def test_signal_result_cannot_fabricate_a_sharpe() -> None:
    with pytest.raises(ValueError, match="Sharpe"):
        TrialEvaluationResult(
            ordinal=0,
            kind=TrialKind.SIGNAL_FULL,
            oos_sharpe=Decimal("1.2"),
            oos_sharpe_after_tax=None,
            observation_count=10,
            payload={"filled": 10},
        )


def test_non_finite_or_overlarge_decimal_is_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        TrialEvaluationResult(
            ordinal=0,
            kind=TrialKind.PORTFOLIO,
            oos_sharpe=Decimal("NaN"),
            oos_sharpe_after_tax=None,
            observation_count=1,
            payload={},
        )
    with pytest.raises(ValueError, match="precision"):
        TrialEvaluationResult(
            ordinal=0,
            kind=TrialKind.PORTFOLIO,
            oos_sharpe=Decimal("1" * 129),
            oos_sharpe_after_tax=None,
            observation_count=1,
            payload={},
        )


def test_legacy_reader_preserves_missing_after_tax_as_absent(tmp_path: Path) -> None:
    path = tmp_path / "trials.json"
    old = {
        "at": "2026-08-07T10:00:00+00:00",
        "strategy": "old",
        "version": 1,
        "origin": "operator",
        "primitives": ["close"],
        "oos_sharpe": 0.5,
        "oos_trades": 12,
        "folds": 3,
    }
    new = dict(old, strategy="new", oos_sharpe_after_tax=None)
    raw = {"schema": 1, "trials": [old, new]}
    path.write_text(json.dumps(raw), encoding="utf-8")

    ledger = read_legacy_portfolio_ledger(path)

    assert len(ledger.trials) == 2
    assert ledger.trials[0].after_tax_field_present is False
    assert "oos_sharpe_after_tax" not in ledger.trials[0].original_payload
    assert ledger.trials[1].after_tax_field_present is True
    assert ledger.trials[1].oos_sharpe_after_tax is None


def test_corrupt_legacy_ledger_refuses_instead_of_becoming_empty(tmp_path: Path) -> None:
    path = tmp_path / "trials.json"
    path.write_text('{"schema":99,"trials":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        read_legacy_portfolio_ledger(path)

    path.write_text('{"schema":true,"trials":[]}', encoding="utf-8")
    with pytest.raises(ValueError, match="schema"):
        read_legacy_portfolio_ledger(path)


def test_public_reserve_rejects_legacy_source_before_database_access() -> None:
    accessed = False

    class ForbiddenEngine:
        def begin(self) -> object:
            nonlocal accessed
            accessed = True
            raise AssertionError("legacy source reached public database reservation")

    legacy = replace(
        signal_batch(),
        source="legacy_json_v1",
        strategy_sha256=None,
        panel_sha256=None,
        config_sha256=None,
    )
    ledger = PostgresTrialLedger(cast(Engine, ForbiddenEngine()))
    with pytest.raises(ValueError, match="native"):
        ledger.reserve(legacy)
    assert accessed is False


def test_rendered_datastore_failure_suppresses_raw_sql_and_metric_payload() -> None:
    sentinel = "SECRET_DSN_AND_SHARPE_9_99"

    class BrokenEngine:
        def begin(self) -> object:
            raise SQLAlchemyError(sentinel)

    ledger = PostgresTrialLedger(cast(Engine, BrokenEngine()))
    with pytest.raises(TrialLedgerUnavailable) as caught:
        ledger.reserve(signal_batch())

    rendered = "".join(traceback.format_exception(caught.value))
    assert rendered.endswith(
        "icarus.state.trial_ledger.TrialLedgerUnavailable: trial ledger reservation failed\n"
    )
    assert "BrokenEngine" not in rendered
    assert sentinel not in rendered
