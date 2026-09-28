"""Same-process counted runner sequencing without drawing reserved streams."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any, cast

import pytest
import scripts.signal_calibration as calibration


class _Context:
    def __init__(self, phase: str, events: list[str], *, close_fails: bool = False) -> None:
        self.phase = phase
        self.paths = SimpleNamespace(as_claim_record=lambda: {"result": f"{phase}.json"})
        self.events = events
        self.closed = False
        self.close_fails = close_fails

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.events.append(f"close:{self.phase}")
        if self.close_fails:
            raise calibration.ManifestError("close failed")


@pytest.mark.parametrize(
    ("calibration_verdict", "validation_verdict"),
    [("FAILED", None), ("PASSED", "FAILED"), ("PASSED", "PASSED")],
)
def test_runner_sequences_only_verified_complete_phases(
    monkeypatch: pytest.MonkeyPatch, calibration_verdict: str, validation_verdict: str | None
) -> None:
    events: list[str] = []
    first = _Context("calibration", events)
    second = _Context("validation", events)
    manifest: dict[str, Any] = {}

    def begin_calibration(*args: Any) -> _Context:
        events.append("begin:calibration")
        return first

    monkeypatch.setattr(calibration, "_begin_linux_phase", begin_calibration)
    monkeypatch.setattr(
        calibration,
        "_write_phase_result",
        lambda context, unused: events.append(f"write:{context.phase}"),
    )

    def complete(context: _Context, unused: Any) -> Any:
        events.append(f"complete:{context.phase}")
        verdict = calibration_verdict if context.phase == "calibration" else validation_verdict
        return SimpleNamespace(phase_verdict=verdict, attempt_id=context.phase)

    def begin_validation(context: _Context, completion: Any, unused: Any) -> _Context:
        events.append("begin:validation")
        context.close()
        return second

    monkeypatch.setattr(calibration, "_complete_phase", complete)
    monkeypatch.setattr(calibration, "_begin_validation_phase", begin_validation)
    report = calibration._run_counted_phases(manifest, cast(Any, object()), cast(Any, object()))
    if calibration_verdict == "FAILED":
        assert events == [
            "begin:calibration",
            "write:calibration",
            "complete:calibration",
            "close:calibration",
        ]
        assert report["validation"] is None
    else:
        assert events == [
            "begin:calibration",
            "write:calibration",
            "complete:calibration",
            "begin:validation",
            "close:calibration",
            "write:validation",
            "complete:validation",
            "close:validation",
        ]
        assert report["validation"]["verdict"] == validation_verdict
    assert report["calibration"]["verdict"] == calibration_verdict


@pytest.mark.parametrize("failure", ["write", "complete", "validation"])
def test_runner_failure_never_reports_or_continues(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    events: list[str] = []
    first = _Context("calibration", events)
    monkeypatch.setattr(calibration, "_begin_linux_phase", lambda *args: first)

    def write(context: _Context, unused: Any) -> None:
        events.append(f"write:{context.phase}")
        if failure == "write":
            raise calibration.ManifestError("writer failed")

    def complete(context: _Context, unused: Any) -> Any:
        events.append("complete")
        if failure == "complete":
            raise calibration.ManifestError("completion failed")
        return SimpleNamespace(phase_verdict="PASSED", attempt_id="calibration")

    def validation(context: _Context, completion: Any, unused: Any) -> Any:
        events.append("validation")
        raise calibration.ManifestError("handoff failed")

    monkeypatch.setattr(calibration, "_write_phase_result", write)
    monkeypatch.setattr(calibration, "_complete_phase", complete)
    monkeypatch.setattr(calibration, "_begin_validation_phase", validation)
    with pytest.raises(calibration.ManifestError):
        calibration._run_counted_phases({}, cast(Any, object()), cast(Any, object()))
    assert first.closed
    assert events == (
        ["write:calibration", "close:calibration"]
        if failure == "write"
        else ["write:calibration", "complete", "close:calibration"]
        if failure == "complete"
        else ["write:calibration", "complete", "validation", "close:calibration"]
    )


def test_runner_close_failure_is_not_success(monkeypatch: pytest.MonkeyPatch) -> None:
    first = _Context("calibration", [], close_fails=True)
    monkeypatch.setattr(calibration, "_begin_linux_phase", lambda *args: first)
    monkeypatch.setattr(calibration, "_write_phase_result", lambda *args: None)
    monkeypatch.setattr(
        calibration,
        "_complete_phase",
        lambda *args: SimpleNamespace(phase_verdict="FAILED", attempt_id="calibration"),
    )
    with pytest.raises(calibration.ManifestError, match="close failed"):
        calibration._run_counted_phases({}, cast(Any, object()), cast(Any, object()))


@pytest.mark.parametrize("failure", ["write", "complete", "close"])
def test_runner_validation_failure_closes_and_never_reports(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    events: list[str] = []
    first = _Context("calibration", events)
    second = _Context("validation", events, close_fails=failure == "close")
    monkeypatch.setattr(calibration, "_begin_linux_phase", lambda *args: first)

    def begin_validation(
        context: _Context, unused_completion: Any, unused_manifest: Any
    ) -> _Context:
        events.append("begin:validation")
        context.close()
        return second

    def write(context: _Context, unused: Any) -> None:
        events.append(f"write:{context.phase}")
        if context.phase == "validation" and failure == "write":
            raise calibration.ManifestError("validation writer failed")

    def complete(context: _Context, unused: Any) -> Any:
        events.append(f"complete:{context.phase}")
        if context.phase == "validation" and failure == "complete":
            raise calibration.ManifestError("validation completion failed")
        return SimpleNamespace(phase_verdict="PASSED", attempt_id=context.phase)

    monkeypatch.setattr(calibration, "_begin_validation_phase", begin_validation)
    monkeypatch.setattr(calibration, "_write_phase_result", write)
    monkeypatch.setattr(calibration, "_complete_phase", complete)
    with pytest.raises(calibration.ManifestError):
        calibration._run_counted_phases({}, cast(Any, object()), cast(Any, object()))
    assert first.closed and second.closed
    assert events == [
        "write:calibration",
        "complete:calibration",
        "begin:validation",
        "close:calibration",
        "write:validation",
        *([] if failure == "write" else ["complete:validation"]),
        "close:validation",
    ]


def test_cli_refuses_windows_before_manifest_or_rng(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["signal_calibration", "run-counted"])
    monkeypatch.setattr(calibration, "_platform_name", lambda: "win32")
    monkeypatch.setattr(calibration, "load_manifest", lambda: pytest.fail("manifest read"))
    assert calibration._cli() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "native Linux" in captured.err


@pytest.mark.parametrize(
    "args", [["--phase", "validation"], ["--seed", "1"], ["--floor", "1"], ["evidence.json"]]
)
def test_cli_refuses_caller_selected_evidence(
    monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["signal_calibration", "run-counted", *args])
    monkeypatch.setattr(calibration, "load_manifest", lambda: pytest.fail("manifest read"))
    with pytest.raises(SystemExit) as exc:
        calibration._cli()
    assert exc.value.code == 2


def test_cli_reports_only_after_runner_success(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["signal_calibration", "run-counted"])
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    manifest = calibration.load_manifest()
    monkeypatch.setattr(calibration, "load_manifest", lambda: manifest)
    monkeypatch.setattr(calibration, "preflight_manifest", lambda unused: {})
    monkeypatch.setattr(calibration, "_NativeLinuxOps", lambda: object())
    monkeypatch.setattr(
        calibration, "_run_counted_phases", lambda *args: {"calibration": {"verdict": "FAILED"}}
    )
    assert calibration._cli() == 0
    captured = capsys.readouterr()
    assert captured.out == '{"calibration":{"verdict":"FAILED"}}\n'
    assert captured.err == ""


def test_cli_operational_failure_has_no_report(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", ["signal_calibration", "run-counted"])
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    manifest = calibration.load_manifest()
    monkeypatch.setattr(calibration, "load_manifest", lambda: manifest)
    monkeypatch.setattr(calibration, "preflight_manifest", lambda unused: {})
    monkeypatch.setattr(calibration, "_NativeLinuxOps", lambda: object())

    def fail(*args: Any) -> Any:
        raise calibration.ManifestError("review mismatch")

    monkeypatch.setattr(calibration, "_run_counted_phases", fail)
    assert calibration._cli() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "review mismatch" in captured.err
