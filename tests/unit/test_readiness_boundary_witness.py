"""Focused witness for exact canonical-calendar metadata boundaries."""

from dataclasses import replace
from pathlib import Path
from types import TracebackType
from typing import BinaryIO

import pytest
from tests.unit import test_timed_runner as helpers

from icarus.engine.data_readiness import BundlePreflight
from icarus.engine.timed_evaluation import _stable_card_bytes
from icarus.engine.timed_runner import (
    AssembledTimedInputs,
    GuardedTimedRunner,
    InputUnavailable,
    RunnerError,
    assemble_timed_inputs,
)


def test_calendar_metadata_cannot_extend_one_closed_day_before_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[BundlePreflight] = []

    def capture(value: BundlePreflight) -> AssembledTimedInputs:
        captured.append(value)
        return assemble_timed_inputs(value)

    monkeypatch.setattr(helpers, "assemble_timed_inputs", capture)
    helpers.test_all_seven_artifacts_assemble_one_causal_panel_and_timed_fixture()
    preflight = captured[0]
    calendar = next(item for item in preflight.artifacts if item.role == "session_calendar")
    assert calendar.metadata["coverage_start"] == "2020-01-02T00:00:00Z"
    extended = replace(
        calendar,
        metadata={**calendar.metadata, "coverage_start": "2020-01-01T00:00:00Z"},
    )
    invalid = replace(
        preflight,
        artifacts=tuple(
            extended if item.role == "session_calendar" else item
            for item in preflight.artifacts
        ),
    )

    with pytest.raises(InputUnavailable, match=r"^CALENDAR_COVERAGE_BOUNDARY$"):
        assemble_timed_inputs(invalid)


def test_invented_authorization_refuses_before_ledger_or_decode() -> None:
    events: list[str] = []
    authorization = replace(helpers._authorization(), invented=True)

    with pytest.raises(RunnerError, match=r"^INVENTED_AUTHORIZATION$"):
        GuardedTimedRunner(helpers._Ledger(events)).run(
            authorization,
            helpers._binding(),
            (helpers._plan("one", "signal", None),),
            lambda: events.append("decode"),
            lambda *_: (),
        )

    assert events == []


def test_strategy_card_capture_requests_one_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = tmp_path / "card.yaml"
    card.write_bytes(b"invented")
    original_open = Path.open
    requested: list[int] = []

    class Spy:
        def __init__(self, handle: BinaryIO) -> None:
            self.handle = handle

        def __enter__(self) -> "Spy":
            self.handle.__enter__()
            return self

        def __exit__(
            self,
            exc_type: type[BaseException] | None,
            exc: BaseException | None,
            traceback: TracebackType | None,
        ) -> None:
            self.handle.__exit__(exc_type, exc, traceback)

        def fileno(self) -> int:
            return self.handle.fileno()

        def read(self, size: int = -1) -> bytes:
            requested.append(size)
            return self.handle.read(size)

    raw = original_open(card, "rb")

    def spy_open(*_args: object, **_kwargs: object) -> Spy:
        return Spy(raw)

    monkeypatch.setattr(Path, "open", spy_open)
    assert _stable_card_bytes(card) == b"invented"
    assert requested == [1_000_001]
