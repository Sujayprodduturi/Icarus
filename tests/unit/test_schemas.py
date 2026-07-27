"""Tests for the message schema base + version policy (task 0.16b, PRD §39.2)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from icarus.common.schemas import (
    Msg,
    SchemaError,
    check_compatible,
    new_correlation_id,
    utc_now,
)


class _Sample(Msg):
    SCHEMA_VERSION = "1.0"
    payload: str


def test_msg_stamps_defaults() -> None:
    m = _Sample(payload="hi")
    assert m.schema_version == "1.0"
    assert m.ts.tzinfo is not None  # tz-aware
    assert m.correlation_id  # non-empty uuid


def test_ts_must_be_tz_aware() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        _Sample(payload="x", ts=datetime(2026, 1, 1))  # naive


def test_naive_ts_rejected_but_aware_accepted() -> None:
    aware = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))  # IST
    m = _Sample(payload="x", ts=aware)
    assert m.ts.tzinfo is UTC  # normalized to UTC


# --- schema-version policy (§39.2) ---------------------------------------------------
def test_minor_bump_is_additive_no_halt() -> None:
    # Consumer speaks 1.0; a 1.3 message (same major) must NOT raise.
    check_compatible(local="1.0", incoming="1.3")


def test_older_minor_also_compatible() -> None:
    check_compatible(local="1.5", incoming="1.0")


def test_major_mismatch_raises_schema_error() -> None:
    with pytest.raises(SchemaError):
        check_compatible(local="1.0", incoming="2.0")


def test_ensure_compatible_on_received_message() -> None:
    m = _Sample(payload="x", schema_version="2.0")  # simulate a wire message from a newer major
    with pytest.raises(SchemaError):
        m.ensure_compatible()


def test_malformed_version_raises() -> None:
    with pytest.raises(SchemaError):
        check_compatible(local="1.0", incoming="garbage")


def test_helpers() -> None:
    assert utc_now().tzinfo is UTC
    assert new_correlation_id() != new_correlation_id()
