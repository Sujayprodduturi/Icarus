"""Integration: audit writer appends + scrubs secrets (task 0.12)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

from icarus.state.audit import record_audit

pytestmark = pytest.mark.integration


def _table_exists(engine: Engine) -> bool:
    with engine.connect() as conn:
        return bool(conn.execute(text("SELECT to_regclass('public.audit_log')")).scalar())


def test_record_audit_appends_and_scrubs(pg_engine: Engine) -> None:
    if not _table_exists(pg_engine):
        pytest.skip("migrations not applied")
    # audit_log is append-only (no cleanup possible) -> unique correlation id per run.
    corr = f"corr-{uuid.uuid4()}"
    with pg_engine.begin() as conn:
        record_audit(
            conn,
            "order_placed",
            {"symbol": "INFY", "api_secret": "leak_me"},
            correlation_id=corr,
        )
    with pg_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_type, payload FROM audit_log WHERE correlation_id = :c"),
            {"c": corr},
        ).one()
    assert row.event_type == "order_placed"
    assert row.payload["symbol"] == "INFY"
    assert row.payload["api_secret"] == "***REDACTED***"  # scrubbed before storage
