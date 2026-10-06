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
    assert len(calls) == 1 and calls[0][0] == case
    assert set(calls[0][1]) == {"namespace", "_preflight_deadline"}
    assert calls[0][1]["namespace"] == runner.io.PREFLIGHT_NAMESPACE
    assert type(calls[0][1]["_preflight_deadline"]) is float
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
        bounds: dict[str, Any] = {
            "roles": {
                k: {"fixed": 1.0, "repetitive": v}
                for k, v in zip(("writer", "primary", "reviewer"), work[:3], strict=True)
            },
            "control_setup": 1.0,
            "control_residual": work[3],
        }
        operational = {
            **bounds,
            "control_retirement": 0.0,
            "control_probe": 0.0,
            "roles": {
                role: {"fixed": cost["fixed"], "repetitive": cost["repetitive"] * 16}
                for role, cost in bounds["roles"].items()
            },
            "control_residual": bounds["control_residual"] * 16,
        }
        row = {
            "refinement_bounds": bounds,
            "refined_projection": runner._refined_projection(bounds),
            "operational_bounds": operational,
            "operational_projection": runner._operational_projection(operational),
            "measurement_replicates": 16,
            "batch_projection": runner._batch_projection(operational, 16),
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
    with pytest.raises(runner.RunnerError, match="measurement_work"):
        runner._validate_stage_measurement(row, session._binding)
    row["operational_costs"] = runner.json.loads(runner.io.canonical_json(row["operational_costs"]))
    work = row["operational_costs"]["observation"]
    work["start"] = row["observation"]
    work["finished_monotonic"] = row["ended_monotonic"] - 0.0000005
    work["scans"] = [[work["finished_monotonic"]] * 2] * 2
    repeated = work["finished_monotonic"] - row["observation"]["ready_monotonic"]
    row["operational_costs"].update(
        repetitive_seconds=repeated, fixed_seconds=row["elapsed"] - repeated
    )
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
        started = runner.time.perf_counter()
        runner.time.sleep(0.1)
        result = original(*args, **kwargs)
        durations.append(runner.time.perf_counter() - started)
        return result

    monkeypatch.setattr(runner, "_guarded_hash", delayed)
    session = runner._reserve_test("scan-delay-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = session._measurements[0]
    assert durations and row["repetitive_seconds"] >= sum(durations)
    assert row["operational_costs"]["repetitive_seconds"] >= sum(durations)
    assert row["observation"]["ready_monotonic"] < row["ended_monotonic"] - sum(durations)


@pytest.mark.parametrize("point", ["before-ready", "start", "link"])
def test_parent_delay_is_charged_to_its_observed_interval(
    monkeypatch: pytest.MonkeyPatch,
    point: str,
) -> None:
    runner = runner_module()
    intervals: list[tuple[float, float]] = []

    def pause() -> None:
        begun = runner.time.perf_counter()
        runner.time.sleep(0.1)
        intervals.append((begun, runner.time.perf_counter()))

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


def test_operational_gate_does_not_repeat_owned_shutdown_but_repeats_scans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    original = runner.life._stop_process

    def retire(process: Any) -> Any:
        runner.time.sleep(0.2)
        return original(process)

    monkeypatch.setattr(runner.life, "_stop_process", retire)
    session = runner._reserve_test("operational-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = session._measurements[0]
    costs = row["operational_costs"]
    assert costs["fixed_seconds"] >= row["fixed_seconds"] + 0.2
    assert costs["repetitive_seconds"] < row["repetitive_seconds"]
    assert costs["fixed_seconds"] + costs["repetitive_seconds"] == row["elapsed"]
    assert costs["observation"]["counts"] == row["counts"]
    assert len(costs["observation"]["scans"]) == 2


@pytest.mark.parametrize(
    "fault", ["early-work", "malformed-work", "duplicate-work", "missing-work", "wrong-work-words"]
)
def test_invalid_work_marker_never_publishes_success(fault: str) -> None:
    runner = runner_module()
    session = runner._reserve_test("work-fault-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    with pytest.raises(runner.RunnerError):
        runner._run_owned_stage(session, root, "writer", "primary", _test_fault=fault)
    assert not (root / "phase-terminal.json").exists()
    assert (session.registry / "attempt-failure.json").exists()


@pytest.mark.parametrize("shift", [False, True])
def test_copied_or_shifted_work_observation_is_not_issued(shift: bool) -> None:
    runner = runner_module()
    session = runner._reserve_test("work-copy-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    token = runner._timed_owned_stage(session, root, "writer", "primary")
    changes = {"finished_monotonic": token.proof.work.finished_monotonic - 0.01} if shift else {}
    copied = runner.replace(token.proof.work, **changes)
    with pytest.raises(runner.RunnerError, match="parent_observation_issuer"):
        runner._check_parent_observation(session, root, runner.replace(token.proof, work=copied))


def test_operational_controls_mix_independent_worst_cases() -> None:
    runner = runner_module()
    base = {
        "roles": {
            role: {"fixed": 0.0, "repetitive": 0.1} for role in ("writer", "primary", "reviewer")
        },
        "control_setup": 0.0,
        "control_retirement": 0.0,
        "control_probe": 0.0,
        "control_residual": 0.0,
    }
    rows = [
        {**base, key: 100000.0} for key in ("control_setup", "control_retirement", "control_probe")
    ]
    assert all(runner._operational_projection(row)["eligible"] for row in rows)
    result = runner._group_operational(rows)
    assert result["projection"]["eligible"] is False
    assert all(
        result["bounds"][key] == 100000.0
        for key in ("control_setup", "control_retirement", "control_probe")
    )


@pytest.mark.parametrize("field", ["finished_monotonic", "scans"])
def test_favorable_work_receipt_cannot_override_saved_owned_proof(field: str) -> None:
    runner = runner_module()
    session = runner._reserve_test("work-forged-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    runner._timed_owned_stage(session, root, "writer", "primary")
    row = runner.json.loads(runner.io.canonical_json(session._measurements[0]))
    work = row["operational_costs"]["observation"]
    if field == "finished_monotonic":
        work[field] = row["observation"]["start_monotonic"]
    else:
        work[field] = [[work["finished_monotonic"]] * 2] * 2
    repeated = (
        work["finished_monotonic"]
        - row["observation"]["ready_monotonic"]
        + sum(right - left for left, right in work["scans"])
    )
    row["operational_costs"].update(
        repetitive_seconds=repeated, fixed_seconds=row["elapsed"] - repeated
    )
    path = root / "stage-timing-writer-primary.json"
    saved = runner.phase._read_record(root, path.name)
    path.write_bytes(runner.io.canonical_json({"utc": saved["utc"], **row}))
    with pytest.raises(runner.RunnerError, match="measurement_work_observation"):
        runner._validate_preflight_rows(
            session.registry,
            [row],
            session._binding,
            row["started_monotonic"] - 1.0,
            row["ended_monotonic"] + 1.0,
        )


@pytest.mark.parametrize("fault", ["exit-after-work", "missing-ack-after-work"])
def test_work_marker_alone_never_authorizes_completion(fault: str) -> None:
    runner = runner_module()
    session = runner._reserve_test("work-close-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development")
    with pytest.raises((runner.RunnerError, EOFError, OSError)):
        runner._run_owned_stage(session, root, "writer", "primary", _test_fault=fault)
    assert not (root / "phase-terminal.json").exists()
    assert (session.registry / "attempt-failure.json").exists()


def test_fixed_cost_issuance_failure_precedes_final_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    error = OSError("injected fixed cost issuance failure")

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise error

    monkeypatch.setattr(runner, "_issue_fixed_observation", fail)
    case = "cost-issue-" + runner.uuid.uuid4().hex
    with pytest.raises(OSError) as caught:
        runner._run_test_pipeline(case)
    assert caught.value is error
    root = runner.phase.TEST_ANCHOR / "attempts" / runner.hashlib.sha256(case.encode()).hexdigest()
    assert not (root / "attempt-result.json").exists()
    assert (root / "attempt-failure.json").exists()


def test_preflight_claim_measures_sixteen_complete_replicates() -> None:
    runner = runner_module()
    session = runner._reserve_test("batch-claim-" + runner.uuid.uuid4().hex)
    root = runner._claim_test_phase(session, "development", preflight=True)
    claim = runner.phase._read_record(root, "phase-claim.json")
    plan = runner.phase._claim_plan(claim)
    assert plan.namespace == runner.io.PREFLIGHT_NAMESPACE
    assert plan.replicates == 16
    assert (plan.paths, plan.metrics, plan.payload_bytes) == (160, 448, 3703872)
    assert runner.io.PHASE_REPLICATES == {"development": 8192, "validation": 32768}


def test_runner_and_service_use_one_high_resolution_clock_without_global_patch() -> None:
    import ast
    import inspect
    import time

    from scripts.research import signal_calendar_score_runner_service as service

    runner = runner_module()
    for module in (runner, service):
        source = inspect.getsource(module)
        tree = ast.parse(source)
        calls = [
            node.func.attr
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "time"
        ]
        assert "monotonic" not in calls
        assert "perf_counter" in calls
    assert time.monotonic.__name__ == "monotonic"
    assert time.get_clock_info("perf_counter").monotonic is True


def test_batch_projection_charges_every_unknown_repeated_cost_per_sixteen_sets() -> None:
    runner = runner_module()
    bounds = {
        "roles": {
            role: {"fixed": 1.0, "repetitive": 8.0} for role in ("writer", "primary", "reviewer")
        },
        "control_setup": 1.0,
        "control_retirement": 1.0,
        "control_probe": 1.0,
        "control_residual": 16.0,
    }
    assert runner._operational_projection(bounds)["eligible"] is False
    result = runner._batch_projection(bounds, 16)
    assert result["eligible"] is True
    assert result["phases"]["validation"]["writer"]["projected_seconds"] == 32770.0
    assert result["session_projected_seconds"] == 188434.0


@pytest.mark.parametrize("replicates", [True, 1, 15, 17, 0, -16, 16.0])
def test_batch_projection_refuses_unbound_or_nondivisible_measurement_count(
    replicates: object,
) -> None:
    runner = runner_module()
    bounds = {
        "roles": {
            role: {"fixed": 1.0, "repetitive": 8.0} for role in ("writer", "primary", "reviewer")
        },
        "control_setup": 1.0,
        "control_retirement": 1.0,
        "control_probe": 1.0,
        "control_residual": 16.0,
    }
    with pytest.raises(runner.RunnerError, match="measurement_replicates"):
        runner._batch_projection(bounds, replicates)


def test_preflight_deadline_is_absolute_and_cannot_reset_on_adoption() -> None:
    runner = runner_module()
    deadline = runner.time.perf_counter() + 0.2
    session = runner._reserve_test(
        "deadline-" + runner.uuid.uuid4().hex, preflight_deadline=deadline
    )
    record = runner.phase._read_record(session.registry, "attempt-reserved.json")
    adopted = runner._adopt_reviewer_view(session.registry)
    assert record["preflight_deadline"] == adopted._preflight_deadline == deadline
    assert 0 < runner._remaining_preflight(deadline, 600.0) <= 0.2
    adopted._preflight_deadline += 1.0
    with pytest.raises(runner.RunnerError, match="preflight_deadline"):
        adopted._check()


def test_expired_preflight_deadline_refuses_before_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    calls: list[Any] = []
    monkeypatch.setattr(runner.mp, "get_context", lambda *args: calls.append(args))
    with pytest.raises(runner.RunnerError, match="preflight_deadline"):
        runner._launch_pipeline(
            "expired-" + runner.uuid.uuid4().hex,
            namespace=runner.io.PREFLIGHT_NAMESPACE,
            _preflight_deadline=runner.time.perf_counter() - 0.01,
        )
    assert calls == []


@pytest.mark.parametrize("deadline", [True, float("inf"), float("nan")])
def test_preflight_deadline_refuses_unbounded_clock_values(deadline: object) -> None:
    runner = runner_module()
    with pytest.raises(runner.RunnerError, match="preflight_deadline"):
        runner._remaining_preflight(deadline, 600.0)


def test_late_preflight_pipeline_deadline_halts_before_tail_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    launched = False
    error = runner.RunnerError("preflight_deadline")

    def launch(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal launched
        launched = True
        return {}

    def remaining(*args: Any) -> float:
        if launched:
            raise error
        return 600.0

    monkeypatch.setattr(runner, "_ROLE", "reviewer")
    monkeypatch.setattr(runner, "_launch_pipeline", launch)
    monkeypatch.setattr(runner, "_remaining_preflight", remaining)
    with pytest.raises(runner.RunnerError) as caught:
        runner._measure_integrated_preflight("late-tail-" + runner.uuid.uuid4().hex)
    assert launched
    assert caught.value is error


def test_disk_probe_deadline_halts_at_original_flush_cadence() -> None:
    runner = runner_module()
    root = runner.phase.TEST_ANCHOR / "preflights" / ("probe-tail-" + runner.uuid.uuid4().hex)
    root.mkdir(parents=True)
    calls = 0
    error = runner.RunnerError("preflight_deadline")

    def guard() -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise error

    with pytest.raises(runner.RunnerError) as caught:
        runner._disk_probe(root, runner.phase.current_binding(), _guard=guard)
    assert caught.value is error
    assert calls == 2
    assert (root / "disk-probe.bin").stat().st_size == 16 << 20


def test_probe_hash_forwards_deadline_into_chunked_reader() -> None:
    runner = runner_module()
    root = runner.phase.TEST_ANCHOR / "preflights" / ("hash-tail-" + runner.uuid.uuid4().hex)
    root.mkdir(parents=True)
    (root / "tail.bin").write_bytes(b"deadline-tail")
    error = runner.RunnerError("preflight_deadline")

    def guard() -> None:
        raise error

    with pytest.raises(runner.RunnerError) as caught:
        runner._probe_hash(root, "tail.bin", 13, runner.phase.current_binding(), guard)
    assert caught.value is error
