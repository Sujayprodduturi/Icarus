"""Audit-log writer (task 0.12, PRD §19).

Every decision/order/fill/veto/halt/strategy-diff/hypothesis/verdict is appended here. The
table is append-only at the DB level (trigger in the migration), so this module only ever
INSERTs. Payloads are scrubbed of secrets before storage (defense in depth with the log scrub).
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Connection, insert

from icarus.common.logging import scrub_secrets
from icarus.state.models import AuditLog


def record_audit(
    conn: Connection,
    event_type: str,
    payload: dict[str, Any],
    *,
    correlation_id: str | None = None,
) -> None:
    """Append one audit event. Caller owns the transaction (so it commits with related state)."""
    safe_payload = scrub_secrets(None, "audit", dict(payload))
    conn.execute(
        insert(AuditLog).values(
            event_type=event_type,
            correlation_id=correlation_id,
            payload=safe_payload,
        )
    )
