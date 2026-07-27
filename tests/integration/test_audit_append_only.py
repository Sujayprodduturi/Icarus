"""Integration: the audit_log append-only guarantee (task 0.4 AC, PRD §19).

Needs a real Postgres with migrations applied (the trigger is DB-level). Marked `integration`.
Run: bring up compose, `alembic upgrade head`, then `pytest -m integration`.
"""

from __future__ import annotations

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import DatabaseError

pytestmark = pytest.mark.integration


def _has_audit_table(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('public.audit_log')")).scalar())


def test_insert_allowed(pg_engine: Engine) -> None:
    if not _has_audit_table(pg_engine):
        pytest.skip("migrations not applied; run `alembic upgrade head`")
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (event_type, payload) VALUES ('test_insert', '{}'::jsonb)")
        )


def test_update_blocked(pg_engine: Engine) -> None:
    if not _has_audit_table(pg_engine):
        pytest.skip("migrations not applied")
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (event_type, payload) VALUES ('to_update', '{}'::jsonb)")
        )
    with pytest.raises(DatabaseError, match="append-only"), pg_engine.begin() as conn:
        conn.execute(text("UPDATE audit_log SET event_type='x' WHERE event_type='to_update'"))


def test_delete_blocked(pg_engine: Engine) -> None:
    if not _has_audit_table(pg_engine):
        pytest.skip("migrations not applied")
    with pg_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO audit_log (event_type, payload) VALUES ('to_delete', '{}'::jsonb)")
        )
    with pytest.raises(DatabaseError, match="append-only"), pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM audit_log WHERE event_type='to_delete'"))
