"""Focused witness for exact canonical-calendar metadata boundaries."""

from dataclasses import replace

import pytest
from tests.unit import test_timed_runner as helpers

from icarus.engine.data_readiness import BundlePreflight
from icarus.engine.timed_runner import AssembledTimedInputs, InputUnavailable, assemble_timed_inputs


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
