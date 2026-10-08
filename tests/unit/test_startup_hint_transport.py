"""A broken empty poll is absence; a broken receive is an invalid hint."""

from __future__ import annotations

from multiprocessing.connection import _ConnectionBase as Connection
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_phase as phase
from scripts.research import signal_calendar_score_runner as runner


@pytest.mark.parametrize("broken_operation,expected", [("poll", "MISSING"), ("recv", "INVALID")])
def test_broken_startup_hint_is_classified_without_granting_authority(
    broken_operation: str, expected: str
) -> None:
    class Hint:
        def poll(self, _timeout: float) -> bool:
            if broken_operation == "poll":
                raise BrokenPipeError("empty peer closed")
            return True

        def recv_bytes(self, _maximum: int) -> bytes:
            raise BrokenPipeError("receive stopped after a frame was indicated")

    session = runner._reserve_test("test-hint-transport-" + uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    identity = life.ProcessIdentity.current()
    runner._record_startup_error(
        session,
        root,
        "writer",
        "primary",
        SimpleNamespace(pid=identity.pid, exitcode=73),
        identity,
        cast(Connection, Hint()),
        BrokenPipeError("bootstrap stopped"),
        phase.Progress(0, 0, 0, 0, 0),
    )
    record = phase._read_record(root, "writer-primary-startup-failure.json")
    assert record["hint_status"] == expected
    assert record["worker_hint"] is None
    assert record["state"] == "ERROR"
    assert record["diagnostic_authority"] == "UNTRUSTED_HINT_ONLY"
    assert record["active_residual"] == "UNKNOWN_INCOMPLETE"
    assert not (root / "phase-terminal.json").exists()
    assert not (root / "verified-primary.json").exists()
