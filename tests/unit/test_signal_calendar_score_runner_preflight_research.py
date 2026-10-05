"""No experimental reservation or cold benchmark is run by these gate tests."""

from __future__ import annotations

import importlib
from typing import Any

import pytest


def runner_module() -> Any:
    return importlib.import_module("scripts.research.signal_calendar_score_runner")


def test_integrated_projection_retains_old_and_effective_gates() -> None:
    runner = runner_module()
    row = runner._integrated_projection({"writer": 0.25, "primary": 0.75, "reviewer": 0.75}, 3.55)
    assert row["eligible"] is True
    assert row["phases"]["validation"]["primary"]["projected_seconds"] == 49152.0
    assert row["phases"]["validation"]["primary"]["legacy_12h"] is False
    assert row["phases"]["validation"]["primary"]["prior_14h"] is True
    assert row["phases"]["validation"]["primary"]["effective_16h"] is True


@pytest.mark.parametrize("value", [True, -1.0, float("nan"), float("inf"), 0])
def test_integrated_projection_refuses_invalid_measurements(value: object) -> None:
    runner = runner_module()
    with pytest.raises(runner.RunnerError, match="measurement"):
        runner._integrated_projection({"writer": value, "primary": 0.5, "reviewer": 0.5}, 2.0)


def test_any_slow_verifier_blocks_undrawn_readiness() -> None:
    runner = runner_module()
    row = runner._integrated_projection({"writer": 0.25, "primary": 0.5, "reviewer": 0.9}, 3.0)
    assert row["eligible"] is False
    assert row["phases"]["validation"]["reviewer"]["effective_16h"] is False


def test_actual_entry_uses_fresh_readiness_and_never_saved_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    calls: list[str] = []

    def blocked(pin: str) -> object:
        calls.append(pin)
        raise runner.RunnerError("undrawn_readiness_blocker")

    monkeypatch.setattr(runner, "_collect_readiness", blocked)
    launched: list[int] = []
    monkeypatch.setattr(runner, "_launch_pipeline", lambda *args, **kwargs: launched.append(1))
    pin = runner.phase.current_binding().manifest_digest
    with pytest.raises(runner.RunnerError, match="undrawn_readiness_blocker"):
        runner.run_reviewed_study(pin)
    assert calls == [pin]
    assert launched == []


def test_preflight_rejects_unbounded_case_before_pipeline(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    called: list[int] = []
    monkeypatch.setattr(runner, "_launch_pipeline", lambda *args, **kwargs: called.append(1))
    with pytest.raises(runner.RunnerError, match="preflight_case"):
        runner.run_integrated_preflight("../" + "x" * 100)
    assert called == []


def test_public_preflight_stops_in_fixture_route_on_original_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    error = OSError("fixture stopped before generation")
    calls: list[Any] = []

    def stop(case: str, **kwargs: Any) -> Any:
        calls.append((case, kwargs))
        raise error

    monkeypatch.setattr(runner, "_launch_pipeline", stop)
    case = "preflight-test-" + runner.uuid.uuid4().hex
    with pytest.raises(OSError) as caught:
        runner.run_integrated_preflight(case)
    assert caught.value is error
    assert calls == [(case, {"namespace": runner.io.PREFLIGHT_NAMESPACE})]
    root = (
        runner.phase.TEST_ANCHOR / "preflights" / runner.hashlib.sha256(case.encode()).hexdigest()
    )
    assert (root / "preflight-failure.json").exists()
    assert not (root / "preflight-result.json").exists()
    assert case not in runner._PREFLIGHT_MEASUREMENTS


def test_rehashed_favorable_stage_clock_cannot_override_owned_proof() -> None:
    runner = runner_module()
    session = runner._reserve_test("clock-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    token = runner._timed_owned_stage(session, root, "writer", "primary")
    row = dict(session._measurements[0])
    runner._validate_preflight_rows(
        session.registry,
        [row],
        session._binding,
        row["started_monotonic"] - 1.0,
        row["ended_monotonic"] + 1.0,
    )
    assert token.proof.elapsed > 0.000001
    row["elapsed"] = 0.000001
    row["ended_monotonic"] = row["started_monotonic"] + row["elapsed"]
    row["elapsed"] = row["ended_monotonic"] - row["started_monotonic"]
    path = root / "stage-timing-writer-primary.json"
    saved = runner.phase._read_record(root, path.name)
    path.write_bytes(runner.io.canonical_json({"utc": saved["utc"], **row}))
    with pytest.raises(runner.RunnerError, match=r"measurement_(owned_proof|observation_clock)"):
        runner._validate_preflight_rows(
            session.registry,
            [row],
            session._binding,
            row["started_monotonic"] - 1.0,
            row["ended_monotonic"] + 1.0,
        )


def test_registered_readiness_rejects_favorable_unissued_measurements() -> None:
    runner = runner_module()
    source = runner.phase.current_binding()
    cases = ("ready-forged-a", "ready-forged-b", "ready-forged-c")
    token = runner._Readiness(
        runner.life.ProcessIdentity.current(),
        source,
        cases,
        runner.io.canonical_json([{"projection": {"eligible": True}}] * 3),
    )
    runner._READINESS[id(token)] = token
    try:
        with pytest.raises(runner.RunnerError, match="readiness_measurements"):
            runner._check_readiness(token)
    finally:
        runner._READINESS.pop(id(token), None)


def test_owned_stage_reports_parent_observed_startup_and_repeated_work() -> None:
    runner = runner_module()
    session = runner._reserve_test("barrier-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = session._measurements[0]
    assert row["fixed_seconds"] > 0
    assert row["repetitive_seconds"] > 0
    assert row["observation"]["ready_monotonic"] <= row["observation"]["start_monotonic"]
    assert row["fixed_seconds"] == row["observation"]["ready_monotonic"] - row["started_monotonic"]
    assert (
        row["repetitive_seconds"] == row["ended_monotonic"] - row["observation"]["ready_monotonic"]
    )


def test_mixed_local_refinement_passes_do_not_admit_global_group() -> None:
    runner = runner_module()

    def bounds(work: tuple[float, float, float], residual: float) -> dict[str, Any]:
        return {
            "roles": {
                k: {"fixed": 1.0, "repetitive": v}
                for k, v in zip(("writer", "primary", "reviewer"), work, strict=True)
            },
            "control_setup": 1.0,
            "control_residual": residual,
        }

    rows = [
        bounds((0.65, 0.87, 0.87), 0.0),
        bounds((0.1, 0.1, 0.1), 3.5),
        bounds((0.1, 0.1, 0.1), 3.4),
    ]
    assert all(runner._refined_projection(row)["eligible"] is True for row in rows)
    mixed = runner._group_refinement(rows)
    assert mixed["projection"]["eligible"] is False
    assert mixed["bounds"]["roles"]["writer"]["repetitive"] == 0.65
    assert mixed["bounds"]["control_residual"] == 3.5


@pytest.mark.parametrize("value", [True, -1.0, float("nan"), float("inf"), 1])
def test_refinement_refuses_inexact_or_invalid_bounds(value: object) -> None:
    runner = runner_module()
    row = {
        "roles": {k: {"fixed": 1.0, "repetitive": 0.5} for k in ("writer", "primary", "reviewer")},
        "control_setup": 1.0,
        "control_residual": value,
    }
    with pytest.raises(runner.RunnerError, match="refinement_bounds"):
        runner._refined_projection(row)


def test_three_local_passes_cannot_create_readiness_when_group_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    source = runner.phase.current_binding()
    costs = [(0.65, 0.87, 0.87, 0.0), (0.1, 0.1, 0.1, 3.5), (0.1, 0.1, 0.1, 3.4)]

    def fixture(case: str) -> dict[str, Any]:
        work = costs.pop(0)
        bounds = {
            "roles": {
                k: {"fixed": 1.0, "repetitive": v}
                for k, v in zip(("writer", "primary", "reviewer"), work[:3], strict=True)
            },
            "control_setup": 1.0,
            "control_residual": work[3],
        }
        row = {
            "refinement_bounds": bounds,
            "refined_projection": runner._refined_projection(bounds),
        }
        assert row["refined_projection"]["eligible"] is True
        runner._PREFLIGHT_MEASUREMENTS[case] = runner._PreflightMeasurement(
            runner.life.ProcessIdentity.current(), source, case, runner.io.canonical_json(row)
        )
        return row

    monkeypatch.setattr(runner, "run_integrated_preflight", fixture)
    launched: list[int] = []
    monkeypatch.setattr(runner, "_launch_pipeline", lambda *a, **k: launched.append(1))
    result = runner.run_reviewed_study(source.manifest_digest)
    assert result["state"] == "UNDRAWN_READINESS_BLOCKER"
    assert result["group_refinement"]["projection"]["eligible"] is False
    assert launched == []
    assert result["attempt_reserved"] is False


def test_copied_parent_observation_is_not_live_timing_authority() -> None:
    runner = runner_module()
    session = runner._reserve_test("observer-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    token = runner._timed_owned_stage(session, root, "writer", "primary")
    copied = runner.replace(token.proof.observation)
    assert copied == token.proof.observation
    assert copied is not token.proof.observation
    with pytest.raises(runner.RunnerError, match="parent_observation_issuer"):
        runner._check_parent_observation(
            session, root, runner.replace(token.proof, observation=copied)
        )


def test_rehashed_favorable_ready_cannot_override_parent_observation() -> None:
    runner = runner_module()
    session = runner._reserve_test("ready-clock-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = dict(session._measurements[0])
    row["observation"] = dict(row["observation"])
    row["observation"]["ready_monotonic"] = row["ended_monotonic"] - 0.000001
    row["observation"]["start_monotonic"] = row["observation"]["ready_monotonic"]
    row["fixed_seconds"] = row["observation"]["ready_monotonic"] - row["started_monotonic"]
    row["repetitive_seconds"] = row["ended_monotonic"] - row["observation"]["ready_monotonic"]
    runner._validate_stage_measurement(row, session._binding)
    path = root / "stage-timing-writer-primary.json"
    saved = runner.phase._read_record(root, path.name)
    path.write_bytes(runner.io.canonical_json({"utc": saved["utc"], **row}))
    with pytest.raises(runner.RunnerError, match="measurement_parent_observation"):
        runner._validate_preflight_rows(
            session.registry,
            [row],
            session._binding,
            row["started_monotonic"] - 1.0,
            row["ended_monotonic"] + 1.0,
        )


def test_post_ready_parent_scan_delay_remains_repetitive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    original = runner._guarded_hash
    durations: list[float] = []

    def delayed(*args: Any, **kwargs: Any) -> Any:
        started = runner.time.monotonic()
        runner.time.sleep(0.1)
        result = original(*args, **kwargs)
        durations.append(runner.time.monotonic() - started)
        return result

    monkeypatch.setattr(runner, "_guarded_hash", delayed)
    session = runner._reserve_test("scan-delay-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = session._measurements[0]
    assert durations and row["repetitive_seconds"] >= sum(durations)
    assert row["observation"]["ready_monotonic"] < row["ended_monotonic"] - sum(durations)


@pytest.mark.parametrize("point", ["before-ready", "start", "link"])
def test_parent_delay_is_charged_to_its_observed_interval(
    monkeypatch: pytest.MonkeyPatch,
    point: str,
) -> None:
    runner = runner_module()
    intervals: list[tuple[float, float]] = []

    def pause() -> None:
        begun = runner.time.monotonic()
        runner.time.sleep(0.1)
        intervals.append((begun, runner.time.monotonic()))

    if point == "before-ready":
        original = runner._receive_owned

        def ready(*args: Any, **kwargs: Any) -> Any:
            body = original(*args, **kwargs)
            if body["state"] == "READY":
                pause()
            return body

        monkeypatch.setattr(runner, "_receive_owned", ready)
    elif point == "start":
        original = runner._send_stage_start

        def start(*args: Any, **kwargs: Any) -> Any:
            pause()
            return original(*args, **kwargs)

        monkeypatch.setattr(runner, "_send_stage_start", start)
    else:
        original = runner.os.link

        def link(*args: Any, **kwargs: Any) -> Any:
            pause()
            return original(*args, **kwargs)

        monkeypatch.setattr(runner.os, "link", link)
    session = runner._reserve_test("parent-delay-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = session._measurements[0]
    assert len(intervals) == 1
    begun, ended = intervals[0]
    ready_time = row["observation"]["ready_monotonic"]
    if point == "before-ready":
        assert row["started_monotonic"] <= begun < ended <= ready_time
        assert row["fixed_seconds"] >= ended - begun
    else:
        assert ready_time <= begun < ended <= row["ended_monotonic"]
        assert row["repetitive_seconds"] >= ended - begun


@pytest.mark.parametrize("field", ["elapsed", "fixed_seconds", "started_monotonic"])
def test_accounting_refuses_inconsistent_or_inexact_intervals(field: str) -> None:
    runner = runner_module()
    timings: list[dict[str, Any]] = []
    for phase in runner.io.PHASE_REPLICATES:
        for kind, role in (
            ("writer", "primary"),
            ("verifier", "primary"),
            ("verifier", "reviewer"),
        ):
            begin = float(len(timings) + 1)
            timings.append(
                {
                    "phase": phase,
                    "kind": kind,
                    "role": role,
                    "started_monotonic": begin,
                    "ended_monotonic": begin + 1.0,
                    "elapsed": 1.0,
                    "fixed_seconds": 0.5,
                    "repetitive_seconds": 0.5,
                }
            )
    assert runner._account_refinement(timings, 0.0, 7.0)["control_residual"] == 0.0
    timings[0][field] = True
    with pytest.raises(runner.RunnerError, match="refinement_intervals"):
        runner._account_refinement(timings, 0.0, 7.0)
