"""Real PostgreSQL proofs for atomic counted-trial persistence.

These tests refuse to guess a DSN.  The caller must provide an isolated synthetic database via
``ICARUS_TRIAL_TEST_PG_DSN``.  Every test migrates a unique schema, including child processes.
"""

from __future__ import annotations

import json
import multiprocessing
import os
import time
import uuid
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import DatabaseError, SQLAlchemyError

from icarus.state.trial_ledger import (
    EvaluationReservation,
    LegacyPortfolioLedger,
    PostgresTrialLedger,
    TrialBatchReservation,
    TrialEvaluationResult,
    TrialIdentityConflict,
    TrialKind,
    TrialLedgerCorruption,
    TrialLedgerNotActivated,
    TrialLedgerUnavailable,
    TrialOrigin,
    TrialReservationAuthorization,
    read_legacy_portfolio_ledger,
)

pytestmark = pytest.mark.integration


def _schema_dsn(dsn: str, schema: str) -> str:
    parts = urlsplit(dsn)
    query = dict(parse_qsl(parts.query))
    query["options"] = f"-csearch_path={schema}"
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


@pytest.fixture
def isolated_trial_db(repo_root: Path) -> Iterator[tuple[Engine, str, str]]:
    admin_dsn = os.environ.get("ICARUS_TRIAL_TEST_PG_DSN")
    if admin_dsn is None:
        pytest.skip("set ICARUS_TRIAL_TEST_PG_DSN to an isolated synthetic PostgreSQL database")
    schema = f"trial_{uuid.uuid4().hex}"
    admin = create_engine(admin_dsn)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    scoped_dsn = _schema_dsn(admin_dsn, schema)
    previous = os.environ.get("ICARUS_PG_DSN")
    os.environ["ICARUS_PG_DSN"] = scoped_dsn
    try:
        config = Config(str(repo_root / "alembic.ini"))
        command.upgrade(config, "head")
        engine = create_engine(scoped_dsn)
        yield engine, scoped_dsn, schema
        engine.dispose()
    finally:
        if previous is None:
            os.environ.pop("ICARUS_PG_DSN", None)
        else:
            os.environ["ICARUS_PG_DSN"] = previous
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _legacy_empty() -> LegacyPortfolioLedger:
    return LegacyPortfolioLedger(schema=1, sha256="0" * 64, trials=())


class _CommitThenRaiseContext:
    def __init__(self, context: Any) -> None:
        self._context = context

    def __enter__(self) -> Any:
        return self._context.__enter__()

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        suppressed = bool(self._context.__exit__(exc_type, exc, traceback))
        if exc_type is None:
            raise SQLAlchemyError("synthetic lost commit acknowledgement")
        return suppressed


class _CommitThenRaiseEngine:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def begin(self) -> _CommitThenRaiseContext:
        return _CommitThenRaiseContext(self._engine.begin())


class _FailingExecuteConnection:
    def __init__(self, connection: Any, fail_at: int) -> None:
        self._connection = connection
        self._fail_at = fail_at
        self._calls = 0

    def execute(self, *args: object, **kwargs: object) -> Any:
        self._calls += 1
        if self._calls == self._fail_at:
            raise SQLAlchemyError("synthetic mid-import failure")
        return self._connection.execute(*args, **kwargs)


class _FailingBeginContext:
    def __init__(self, context: Any, fail_at: int) -> None:
        self._context = context
        self._fail_at = fail_at

    def __enter__(self) -> _FailingExecuteConnection:
        return _FailingExecuteConnection(self._context.__enter__(), self._fail_at)

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> bool:
        return bool(self._context.__exit__(exc_type, exc, traceback))


class _FailingExecuteEngine:
    def __init__(self, engine: Engine, fail_at: int) -> None:
        self._engine = engine
        self._fail_at = fail_at

    def begin(self) -> _FailingBeginContext:
        return _FailingBeginContext(self._engine.begin(), self._fail_at)


def _batch(run_group_id: uuid.UUID | None = None) -> TrialBatchReservation:
    start = datetime(2020, 1, 1, tzinfo=UTC)
    return TrialBatchReservation(
        run_group_id=run_group_id or uuid.uuid4(),
        origin=TrialOrigin.OPERATOR,
        strategy_name="synthetic-probe",
        strategy_version=1,
        strategy_sha256="a" * 64,
        panel_sha256="b" * 64,
        config_sha256="c" * 64,
        primitives=("close",),
        evaluations=(
            EvaluationReservation(
                0,
                TrialKind.SIGNAL_FULL,
                None,
                0,
                10,
                start,
                start + timedelta(days=9),
                "continuous_full_development_v1",
            ),
            EvaluationReservation(
                1,
                TrialKind.SIGNAL_FOLD,
                0,
                2,
                5,
                start + timedelta(days=2),
                start + timedelta(days=4),
                "fresh_signal_simulator_per_fold_v1",
            ),
            EvaluationReservation(
                2,
                TrialKind.SIGNAL_FOLD,
                1,
                6,
                9,
                start + timedelta(days=6),
                start + timedelta(days=8),
                "fresh_signal_simulator_per_fold_v1",
            ),
        ),
    )


def _results() -> tuple[TrialEvaluationResult, ...]:
    return tuple(
        TrialEvaluationResult(i, kind, None, None, 10 + i, {"filled": 10 + i})
        for i, kind in enumerate(
            (TrialKind.SIGNAL_FULL, TrialKind.SIGNAL_FOLD, TrialKind.SIGNAL_FOLD)
        )
    )


def test_reservation_retry_recovers_but_never_reauthorizes(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    batch = _batch()

    first = ledger.reserve(batch)
    retry = ledger.reserve(batch)

    assert first.newly_created is True
    assert first.authorization is TrialReservationAuthorization.NEW_EVALUATION
    assert retry.newly_created is False
    assert retry.authorization is TrialReservationAuthorization.RECOVERY_ONLY
    assert first.evaluation_ids == retry.evaluation_ids
    assert ledger.lifetime_count() == 3


def test_reservation_commit_ack_loss_recovers_count_without_authorization(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    batch = _batch()
    ambiguous = PostgresTrialLedger(cast(Engine, _CommitThenRaiseEngine(engine)))

    with pytest.raises(TrialLedgerUnavailable, match="reservation failed"):
        ambiguous.reserve(batch)
    recovered = ledger.reserve(batch)

    assert recovered.authorization is TrialReservationAuthorization.RECOVERY_ONLY
    assert recovered.newly_created is False
    assert ledger.lifetime_count() == 3


def test_reservation_requires_activation_and_persists_exact_n_plus_one_geometry(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    with pytest.raises(TrialLedgerNotActivated):
        ledger.reserve(_batch())
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())

    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT ordinal,kind,fold_index,start_index,end_index_exclusive,reset_identity "
                "FROM trial_evaluations WHERE run_group_id=:run_group_id ORDER BY ordinal"
            ),
            {"run_group_id": receipt.run_group_id},
        ).all()
    assert [tuple(row) for row in rows] == [
        (0, "signal_full", None, 0, 10, "continuous_full_development_v1"),
        (1, "signal_fold", 0, 2, 5, "fresh_signal_simulator_per_fold_v1"),
        (2, "signal_fold", 1, 6, 9, "fresh_signal_simulator_per_fold_v1"),
    ]


def test_mixed_legacy_import_preserves_absence_payload_order_and_is_idempotent(
    isolated_trial_db: tuple[Engine, str, str], tmp_path: Path
) -> None:
    engine, _, _ = isolated_trial_db
    source = tmp_path / "legacy.json"
    rows = [
        {
            "at": "2026-08-07T10:00:00+00:00",
            "strategy": "old",
            "version": 1,
            "origin": "operator",
            "primitives": ["close"],
            "oos_sharpe": 0.25,
            "oos_trades": 4,
            "folds": 2,
        },
        {
            "at": "2026-08-08T10:00:00+00:00",
            "strategy": "new",
            "version": 2,
            "origin": "operator",
            "primitives": ["close", "sma"],
            "oos_sharpe": 0.5,
            "oos_sharpe_after_tax": None,
            "oos_trades": 7,
            "folds": 3,
        },
    ]
    source.write_text(json.dumps({"schema": 1, "trials": rows}), encoding="utf-8")
    legacy = read_legacy_portfolio_ledger(source)
    ledger = PostgresTrialLedger(engine)

    first = ledger.import_legacy_and_activate(legacy)
    retry = ledger.import_legacy_and_activate(legacy)

    assert first == retry
    assert first.lifetime_trial_count == 2
    with engine.connect() as conn:
        stored = conn.execute(
            text(
                "SELECT b.source,b.strategy_name,r.oos_sharpe_after_tax,r.payload "
                "FROM trial_batches b JOIN trial_evaluations e USING (run_group_id) "
                "JOIN trial_results r USING (evaluation_id) ORDER BY b.reserved_at"
            )
        ).all()
    assert stored[0] == ("legacy_json_v1", "old", None, rows[0])
    assert stored[1] == ("legacy_json_v1", "new", None, rows[1])
    with pytest.raises(TrialIdentityConflict):
        ledger.import_legacy_and_activate(replace(legacy, sha256="f" * 64))


def test_mid_import_failure_rolls_back_activation_and_every_legacy_row(
    isolated_trial_db: tuple[Engine, str, str], tmp_path: Path
) -> None:
    engine, _, _ = isolated_trial_db
    source = tmp_path / "legacy.json"
    source.write_text(
        json.dumps(
            {
                "schema": 1,
                "trials": [
                    {
                        "at": "2026-08-07T10:00:00+00:00",
                        "strategy": "rollback-proof",
                        "version": 1,
                        "origin": "operator",
                        "primitives": ["close"],
                        "oos_sharpe": 0.25,
                        "oos_trades": 4,
                        "folds": 2,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    legacy = read_legacy_portfolio_ledger(source)
    failing = PostgresTrialLedger(cast(Engine, _FailingExecuteEngine(engine, fail_at=5)))

    with pytest.raises(TrialLedgerUnavailable, match="activation failed"):
        failing.import_legacy_and_activate(legacy)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_ledger_activation")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM trial_batches")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM trial_evaluations")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM trial_results")).scalar_one() == 0


def test_same_identity_with_changed_payload_refuses(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    batch = _batch()
    ledger.reserve(batch)
    with pytest.raises(TrialIdentityConflict):
        ledger.reserve(replace(batch, strategy_name="changed"))


def test_complete_is_atomic_idempotent_and_exact(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())

    terminal = ledger.complete(receipt, _results())
    retry = ledger.complete(receipt, _results())

    assert terminal == retry
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_results")).scalar_one() == 3
        assert (
            conn.execute(text("SELECT state FROM trial_batch_terminals")).scalar_one()
            == "completed"
        )


def test_completion_commit_ack_loss_recovers_full_terminal_without_reevaluation(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())
    ambiguous = PostgresTrialLedger(cast(Engine, _CommitThenRaiseEngine(engine)))

    with pytest.raises(TrialLedgerUnavailable, match="completion failed"):
        ambiguous.complete(receipt, _results())
    terminal = ledger.complete(receipt, _results())

    assert terminal.state.value == "completed"
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_results")).scalar_one() == 3
        assert conn.execute(text("SELECT count(*) FROM trial_batch_terminals")).scalar_one() == 1


def test_completion_retry_verifies_each_persisted_result_not_only_terminal_digest(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    clean = ledger.reserve(_batch())
    expected_terminal = ledger.complete(clean, _results())
    assert expected_terminal.results_sha256 is not None

    forged = ledger.reserve(_batch())
    with engine.begin() as conn:
        for identifier in forged.evaluation_ids:
            conn.execute(
                text(
                    "INSERT INTO trial_results "
                    "(evaluation_id,result_sha256,observation_count,payload) "
                    "VALUES (:evaluation_id,:digest,999,CAST(:payload AS jsonb))"
                ),
                {
                    "evaluation_id": identifier,
                    "digest": "f" * 64,
                    "payload": json.dumps({"forged_metric": 9.99}),
                },
            )
        conn.execute(
            text(
                "INSERT INTO trial_batch_terminals "
                "(run_group_id,state,results_sha256) VALUES (:run_group_id,'completed',:digest)"
            ),
            {"run_group_id": forged.run_group_id, "digest": expected_terminal.results_sha256},
        )

    with pytest.raises(TrialLedgerCorruption, match="persisted trial result"):
        ledger.complete(forged, _results())


def test_direct_partial_result_without_completed_terminal_cannot_commit(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())
    with pytest.raises(DatabaseError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO trial_results "
                "(evaluation_id,result_sha256,observation_count,payload) "
                "VALUES (:evaluation_id,:digest,1,'{}'::jsonb)"
            ),
            {"evaluation_id": receipt.evaluation_ids[0], "digest": "d" * 64},
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_results")).scalar_one() == 0


def test_direct_partial_completed_batch_rolls_back_results_and_terminal(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())
    with pytest.raises(DatabaseError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO trial_results "
                "(evaluation_id,result_sha256,observation_count,payload) "
                "VALUES (:evaluation_id,:digest,1,'{}'::jsonb)"
            ),
            {"evaluation_id": receipt.evaluation_ids[0], "digest": "d" * 64},
        )
        conn.execute(
            text(
                "INSERT INTO trial_batch_terminals (run_group_id,state,results_sha256) "
                "VALUES (:run_group_id,'completed',:digest)"
            ),
            {"run_group_id": receipt.run_group_id, "digest": "e" * 64},
        )
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_results")).scalar_one() == 0
        assert conn.execute(text("SELECT count(*) FROM trial_batch_terminals")).scalar_one() == 0


def test_direct_batch_with_omitted_fold_cannot_commit(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    PostgresTrialLedger(engine).import_legacy_and_activate(_legacy_empty())
    run_group_id = uuid.uuid4()
    start = datetime(2020, 1, 1, tzinfo=UTC)
    with pytest.raises(DatabaseError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO trial_batches "
                "(run_group_id,reservation_sha256,origin,source,strategy_name,strategy_version,"
                "strategy_sha256,panel_sha256,config_sha256,primitives,expected_evaluations) "
                "VALUES (:run_group_id,:digest,'operator','native','omitted-fold',1,:digest,"
                ":digest,:digest,'[]'::jsonb,3)"
            ),
            {"run_group_id": run_group_id, "digest": "e" * 64},
        )
        for ordinal, kind, fold_index in ((0, "signal_full", None), (1, "signal_fold", 0)):
            conn.execute(
                text(
                    "INSERT INTO trial_evaluations "
                    "(evaluation_id,run_group_id,ordinal,kind,fold_index,start_index,"
                    "end_index_exclusive,start_ts,end_ts,reset_identity) VALUES "
                    "(:evaluation_id,:run_group_id,:ordinal,:kind,:fold_index,0,1,:start,:start,"
                    ":reset_identity)"
                ),
                {
                    "evaluation_id": uuid.uuid4(),
                    "run_group_id": run_group_id,
                    "ordinal": ordinal,
                    "kind": kind,
                    "fold_index": fold_index,
                    "start": start,
                    "reset_identity": "omitted-fold-proof",
                },
            )
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM trial_batches WHERE run_group_id=:run_group_id"),
                {"run_group_id": run_group_id},
            ).scalar_one()
            == 0
        )


def test_failed_batch_counts_and_cannot_receive_results(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())
    ledger.fail(receipt, failure_code="EVALUATION_FAILED")
    assert ledger.lifetime_count() == 3
    with pytest.raises(DatabaseError), engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO trial_results "
                "(evaluation_id,result_sha256,observation_count,payload) "
                "VALUES (:evaluation_id,:digest,1,'{}'::jsonb)"
            ),
            {"evaluation_id": receipt.evaluation_ids[0], "digest": "d" * 64},
        )


def test_append_only_tables_reject_update_delete_and_truncate(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, _, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    ledger.reserve(_batch())
    for sql in (
        "UPDATE trial_batches SET strategy_name='x'",
        "DELETE FROM trial_evaluations",
        "TRUNCATE trial_batches CASCADE",
    ):
        with pytest.raises(DatabaseError), engine.begin() as conn:
            conn.execute(text(sql))


def _concurrent_reserve(scoped_dsn: str, batch: TrialBatchReservation) -> str:
    engine = create_engine(scoped_dsn)
    try:
        return PostgresTrialLedger(engine).reserve(batch).authorization.value
    finally:
        engine.dispose()


def _concurrent_complete(
    scoped_dsn: str,
    receipt: Any,
    results: tuple[TrialEvaluationResult, ...],
) -> str:
    engine = create_engine(scoped_dsn)
    try:
        try:
            return PostgresTrialLedger(engine).complete(receipt, results).state.value
        except TrialIdentityConflict:
            return "identity_conflict"
    finally:
        engine.dispose()


def _reserve_then_crash(scoped_dsn: str, batch: TrialBatchReservation, marker: str) -> None:
    engine = create_engine(scoped_dsn)
    PostgresTrialLedger(engine).reserve(batch)
    Path(marker).write_text("reservation-acknowledged", encoding="utf-8")
    os._exit(17)


def _insert_uncommitted_then_wait(scoped_dsn: str, run_group_id: str, marker: str) -> None:
    engine = create_engine(scoped_dsn)
    connection = engine.connect()
    connection.begin()
    connection.execute(
        text(
            "INSERT INTO trial_batches "
            "(run_group_id,reservation_sha256,origin,source,strategy_name,strategy_version,"
            "strategy_sha256,panel_sha256,config_sha256,primitives,expected_evaluations) "
            "VALUES (:run_group_id,:digest,'operator','native','uncommitted',1,:digest,:digest,"
            ":digest,'[]'::jsonb,1)"
        ),
        {"run_group_id": run_group_id, "digest": "e" * 64},
    )
    Path(marker).write_text("inserted-not-committed", encoding="utf-8")
    while True:
        time.sleep(0.05)


def test_concurrent_same_id_has_one_authorization(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    batch = _batch()
    with ProcessPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(_concurrent_reserve, (scoped_dsn, scoped_dsn), (batch, batch)))
    assert sorted(outcomes) == ["new_evaluation", "recovery_only"]
    assert ledger.lifetime_count() == 3


def test_concurrent_distinct_ids_both_count_and_same_completion_is_idempotent(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    first = _batch()
    second = _batch()
    with ProcessPoolExecutor(max_workers=2) as pool:
        authorizations = list(
            pool.map(_concurrent_reserve, (scoped_dsn, scoped_dsn), (first, second))
        )
    assert authorizations == ["new_evaluation", "new_evaluation"]
    assert ledger.lifetime_count() == 6

    receipt = ledger.reserve(_batch())
    with ProcessPoolExecutor(max_workers=2) as pool:
        terminals = list(
            pool.map(
                _concurrent_complete,
                (scoped_dsn, scoped_dsn),
                (receipt, receipt),
                (_results(), _results()),
            )
        )
    assert terminals == ["completed", "completed"]
    assert ledger.lifetime_count() == 9


def test_concurrent_conflicting_completions_allow_exactly_one_result_body(
    isolated_trial_db: tuple[Engine, str, str],
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    receipt = ledger.reserve(_batch())
    changed = tuple(
        replace(result, observation_count=result.observation_count + 1) for result in _results()
    )
    with ProcessPoolExecutor(max_workers=2) as pool:
        outcomes = list(
            pool.map(
                _concurrent_complete,
                (scoped_dsn, scoped_dsn),
                (receipt, receipt),
                (_results(), changed),
            )
        )
    assert sorted(outcomes) == ["completed", "identity_conflict"]


def test_committed_reservation_survives_process_crash_without_completion(
    isolated_trial_db: tuple[Engine, str, str], tmp_path: Path
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    marker = tmp_path / "reserved.txt"
    process = multiprocessing.get_context("spawn").Process(
        target=_reserve_then_crash,
        args=(scoped_dsn, _batch(), str(marker)),
    )
    process.start()
    process.join(20)
    assert process.exitcode == 17
    assert marker.read_text(encoding="utf-8") == "reservation-acknowledged"
    assert ledger.lifetime_count() == 3
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM trial_batch_terminals")).scalar_one() == 0


def test_process_killed_before_commit_leaves_no_counted_rows(
    isolated_trial_db: tuple[Engine, str, str], tmp_path: Path
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    run_group_id = uuid.uuid4()
    marker = tmp_path / "uncommitted.txt"
    process = multiprocessing.get_context("spawn").Process(
        target=_insert_uncommitted_then_wait,
        args=(scoped_dsn, str(run_group_id), str(marker)),
    )
    process.start()
    deadline = time.monotonic() + 10
    while not marker.exists() and time.monotonic() < deadline:
        time.sleep(0.05)
    assert marker.exists()
    process.terminate()
    process.join(10)
    assert process.exitcode is not None
    with engine.connect() as conn:
        assert (
            conn.execute(
                text("SELECT count(*) FROM trial_batches WHERE run_group_id=:run_group_id"),
                {"run_group_id": run_group_id},
            ).scalar_one()
            == 0
        )
    assert ledger.lifetime_count() == 0


def test_downgrade_refuses_to_destroy_activated_history(
    isolated_trial_db: tuple[Engine, str, str], repo_root: Path
) -> None:
    engine, scoped_dsn, _ = isolated_trial_db
    ledger = PostgresTrialLedger(engine)
    ledger.import_legacy_and_activate(_legacy_empty())
    ledger.reserve(_batch())
    previous = os.environ.get("ICARUS_PG_DSN")
    os.environ["ICARUS_PG_DSN"] = scoped_dsn
    try:
        with pytest.raises(Exception, match=r"refuses|trial"):
            command.downgrade(Config(str(repo_root / "alembic.ini")), "base")
    finally:
        if previous is None:
            os.environ.pop("ICARUS_PG_DSN", None)
        else:
            os.environ["ICARUS_PG_DSN"] = previous
