"""Owned runner authority tests. No actual reservation, key or study hash."""

from __future__ import annotations

import importlib
import importlib.util
import uuid
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest


def runner_module() -> ModuleType:
    assert importlib.util.find_spec("scripts.research.signal_calendar_score_runner") is not None
    return importlib.import_module("scripts.research.signal_calendar_score_runner")


def case_id() -> str:
    return "test-" + uuid.uuid4().hex


def test_test_reservation_is_durable_once_and_constructor_is_not_authority() -> None:
    runner = runner_module()
    case = case_id()
    session = runner._reserve_test(case)
    assert session.state == "ATTEMPT_RESERVED"
    assert (session.registry / "attempt-reserved.json").exists()
    trial = runner.phase._read_record(session.registry, "attempt-trial.json")
    assert trial["origin"] == "operator/runner"
    assert trial["reservation_digest"] == runner.phase._hash(session._reservation)
    assert trial["evaluations_started"] == 0
    with pytest.raises(runner.RunnerError):
        runner._reserve_test(case)
    with pytest.raises(runner.RunnerError):
        runner._Session(case, object())
    with pytest.raises(AttributeError):
        session.state = "DEVELOPMENT_CLAIMED"


def test_partial_reservation_remains_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    case = case_id()
    original = runner.phase._record
    error = OSError("reservation close")

    def failed(root: Path, name: str, value: dict[str, Any]) -> str:
        result = original(root, name, value)
        if name == "attempt-reserved.json":
            raise error
        return cast(str, result)

    monkeypatch.setattr(runner.phase, "_record", failed)
    with pytest.raises(OSError) as caught:
        runner._reserve_test(case)
    assert caught.value is error
    with pytest.raises(runner.RunnerError):
        runner._reserve_test(case)


def test_coordinator_cannot_invoke_reviewer_launcher(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    called = []
    monkeypatch.setattr(runner, "_ROLE", "coordinator")
    monkeypatch.setattr(runner, "run_integrated_preflight", lambda *a: called.append(a))
    with pytest.raises(runner.RunnerError):
        runner.run_reviewed_study("0" * 64)
    assert called == []


def test_direct_worker_refuses_before_hash(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    calls = []
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *a: calls.append(a))
    with pytest.raises(runner.RunnerError):
        runner._phase_worker(None, None, None, None)
    assert calls == []


def test_owned_writer_and_verifier_publish_only_after_exit() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    completion = runner._run_owned_stage(session, root, "writer", "primary")
    assert completion.evidence.paths == 10
    assert (root / "phase-terminal.json").exists()
    assert completion.proof.exit_code == 0
    assert completion.proof.monitor_joined is True
    receipt = runner._run_owned_stage(session, root, "verifier", "primary")
    assert receipt.evidence.words == completion.evidence.words
    assert (root / "verified-primary.json").exists()
    assert session._child is None


def test_killed_writer_cannot_publish_complete_or_invent_residual() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    with pytest.raises((runner.RunnerError, runner.life.LifecycleError)):
        runner._run_owned_stage(session, root, "writer", "primary", _test_fault="hard-exit")
    assert session.state == "ERROR"
    assert not (root / "phase-terminal.json").exists()
    record = runner.phase._read_record(session.registry, "attempt-failure.json")
    assert record["active_residual"] == "UNKNOWN_INCOMPLETE"
    assert session._child is None


def test_failed_parent_final_guard_leaves_candidate_inert(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    original = runner._final_guard

    def refuse(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        raise runner.RunnerError("injected final guard")

    monkeypatch.setattr(runner, "_final_guard", refuse)
    with pytest.raises(runner.RunnerError):
        runner._run_owned_stage(session, root, "writer", "primary")
    assert not (root / "phase-terminal.json").exists()
    assert session.state == "ERROR"


def test_report_replacement_after_child_exit_refuses_publication(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    original = runner._final_guard
    altered: list[bool] = []

    def replace_report(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        if not altered:
            altered.append(True)
            path = root / "phase-report.json"
            value = runner.phase._read_record(root, path.name)
            value["counts"]["paths"] = 0
            path.write_bytes(runner.io.canonical_json(value))

    monkeypatch.setattr(runner, "_final_guard", replace_report)
    with pytest.raises(runner.RunnerError):
        runner._run_owned_stage(session, root, "writer", "primary")
    assert not (root / "phase-terminal.json").exists()
    assert session.state == "ERROR"


def test_parent_candidate_close_failure_cannot_publish_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    original = runner.phase._record
    error = OSError("parent candidate close")

    def close_failed(folder: Path, name: str, value: dict[str, Any], **kwargs: Any) -> str:
        digest = original(folder, name, value, **kwargs)
        if name == "phase-terminal-parent-candidate.json":
            raise error
        return cast(str, digest)

    monkeypatch.setattr(runner.phase, "_record", close_failed)
    with pytest.raises(OSError) as caught:
        runner._run_owned_stage(session, root, "writer", "primary")
    assert caught.value is error
    assert (root / "phase-terminal-parent-candidate.json").exists()
    assert not (root / "phase-terminal.json").exists()
    assert session.state == "ERROR"


def test_live_token_is_unusable_after_error() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    token = runner._run_owned_stage(session, root, "writer", "primary")
    session.fail(runner.RunnerError("terminal"))
    with pytest.raises(runner.RunnerError):
        session._token(token, type(token))


@pytest.mark.parametrize(
    "mode,state,transport_failure",
    [
        ("full", "FINAL_VERDICT", False),
        ("development-failed", "DEVELOPMENT_FAILED", False),
        ("coordinator-approval", "ERROR", False),
        ("second-release", "ERROR", False),
        ("coordinator-approval", "ERROR", True),
        ("second-release", "ERROR", True),
    ],
)
def test_real_separate_reviewer_pipeline(
    mode: str, state: str, transport_failure: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner = runner_module()
    if transport_failure:
        receive = runner._receive_owned

        def lost_terminal(*args: Any, **kwargs: Any) -> dict[str, Any]:
            event = receive(*args, **kwargs)
            if event.get("state") == "ERROR":
                raise runner.life.LifecycleError("authentication")
            return cast(dict[str, Any], event)

        monkeypatch.setattr(runner, "_receive_owned", lost_terminal)
    case = case_id()
    try:
        result = runner._run_test_pipeline(case, mode=mode)
    except runner.life.LifecycleError as error:
        if mode not in ("coordinator-approval", "second-release") or str(error) != "authentication":
            raise
        root = (
            runner.phase.TEST_ANCHOR / "attempts" / runner.hashlib.sha256(case.encode()).hexdigest()
        )
        reserved = runner.phase._read_record(root, "attempt-reserved.json")
        failure = runner.phase._read_record(root, "service-failure.json")
        registration = runner.phase._read_record(root, "attempt-registration.json")
        attempt = runner.phase._read_record(root, "attempt-failure.json")
        assert attempt["case"] == reserved["case"] == case
        assert attempt["session_id"] == reserved["session_id"]
        assert attempt["source_binding"] == reserved["source_binding"]
        assert attempt["state"] == failure["state"] == "ERROR"
        assert failure["error"] == (
            "coordinator_action" if mode == "coordinator-approval" else "release_once"
        )
        assert failure["source_binding"] == reserved["source_binding"]
        assert registration["source_binding"] == reserved["source_binding"]
        assert registration["session_id"] == reserved["session_id"]
        for peer in ("coordinator", "helper"):
            assert not runner.life.ProcessIdentity(**registration[peer]).alive()
        for name in (
            "validation",
            "attempt-result-candidate.json",
            "attempt-result.json",
        ):
            assert not (root / name).exists()
        if mode == "coordinator-approval":
            assert not (root / "development-reviewer-approved.json").exists()
            assert not (root / "validation-released.json").exists()
        else:
            released = runner.phase._read_record(root, "validation-released.json")
            approved = runner.phase._read_record(root, "development-reviewer-approved.json")
            sealed = runner.phase._read_record(root, "validation-sealed.json")
            assert released["session_id"] == reserved["session_id"]
            assert released["source_binding"] == reserved["source_binding"]
            assert released["commitment"] == sealed["commitment"]
            assert released["approval_digest"] == runner.phase._hash(
                (root / "development-reviewer-approved.json").read_bytes()
            )
            assert released["evidence"] == approved["evidence"]
        return
    assert result["state"] == state
    assert result["namespace"] == runner.io.TEST_NAMESPACE
    assert result["study_permission"] is False
    assert result["children_exited"] is True
    if mode == "coordinator-approval":
        assert result["failure_stage"] == mode
        assert result["failure_reason"] == "coordinator_action"
        assert result["release_transfers"] == 0
    if mode == "second-release":
        assert result["failure_stage"] == mode
        assert result["failure_reason"] == "release_once"
        assert result["release_transfers"] == 1
    if state == "FINAL_VERDICT":
        assert result["development_paths"] == result["validation_paths"] == 10
        assert result["development_metrics"] == result["validation_metrics"] == 28


def test_direct_service_entry_refuses_before_study_key(monkeypatch: pytest.MonkeyPatch) -> None:
    assert (
        importlib.util.find_spec("scripts.research.signal_calendar_score_runner_service")
        is not None
    )
    service = importlib.import_module("scripts.research.signal_calendar_score_runner_service")
    calls: list[int] = []
    monkeypatch.setattr(service, "_new_study_key", lambda: calls.append(1))
    with pytest.raises(service.runner.RunnerError):
        service.run_reviewer_service(None, None, None)
    assert calls == []


def test_reservation_guards_anchor_before_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    error = OSError("ancestor reparse")
    created: list[Path] = []

    def refuse(path: Path, *args: Any, **kwargs: Any) -> Path:
        raise error

    monkeypatch.setattr(runner.io, "_guard_path", refuse)
    monkeypatch.setattr(Path, "mkdir", lambda self, *a, **kw: created.append(self))
    with pytest.raises(OSError) as caught:
        runner._reserve_test(case_id())
    assert caught.value is error
    assert created == []


def test_invalid_same_session_stage_is_terminal() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    with pytest.raises(runner.RunnerError):
        runner._run_owned_stage(session, root, "invalid", "primary")
    assert session.state == "ERROR"


def test_invalid_token_terminalizes_issued_session() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    with pytest.raises(runner.RunnerError):
        session._token(object(), runner._StageToken)
    assert session.state == "ERROR"


def test_completion_snapshot_follows_publication_scans(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    original = runner._guarded_hash
    ends: list[float] = []

    def slow_scan(*args: Any, **kwargs: Any) -> str:
        result = original(*args, **kwargs)
        runner.time.sleep(0.04)
        ends.append(runner.time.monotonic())
        return cast(str, result)

    monkeypatch.setattr(runner, "_guarded_hash", slow_scan)
    token = runner._run_owned_stage(session, root, "writer", "primary")
    assert session._stage_context is not None
    assert ends and token.proof.elapsed >= ends[-1] - session._stage_context[2]
    terminal = runner.phase._read_record(root, "phase-terminal.json")
    assert terminal["completion"]["elapsed"] == token.proof.elapsed


@pytest.mark.parametrize("artifact", ["verified-reviewer.json", "phase-payload.bin"])
def test_replacement_after_owned_review_cannot_approve(
    monkeypatch: pytest.MonkeyPatch, artifact: str
) -> None:
    runner = runner_module()
    original = runner._run_owned_stage
    altered: list[Path] = []

    def replace_after_review(*args: Any, **kwargs: Any) -> Any:
        token = original(*args, **kwargs)
        if args[2:] == ("verifier", "reviewer") and not altered:
            root = args[1]
            path = root / artifact
            altered.append(path)
            if artifact == "verified-reviewer.json":
                value = runner.phase._read_record(root, artifact)
                value["completion"]["elapsed"] += 0.001
                path.write_bytes(runner.io.canonical_json(value))
            else:
                data = path.read_bytes()
                path.write_bytes(bytes([data[0] ^ 1]) + data[1:])
        return token

    monkeypatch.setattr(runner, "_run_owned_stage", replace_after_review)
    if artifact == "verified-reviewer.json":
        with pytest.raises(runner.RunnerError, match="live_review_binding"):
            runner._run_test_pipeline(case_id())
    else:
        result = runner._run_test_pipeline(case_id())
        assert result["state"] == "ERROR"
        assert result["release_transfers"] == 0
        assert result["failure_reason"] in ("artifact_hash", "coordinator_error")
    assert altered


def test_failure_closes_owned_frame_endpoint_without_masking_original() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    left, right = runner.mp.get_context("spawn").Pipe()
    peer = runner.life.ProcessIdentity.current()
    session._channel = runner.channels.FrameChannel(
        left, bytes(32), "coordinator", session._session_id, "0" * 64, peer, peer, session._binding
    )
    original = OSError("primary")
    try:
        session.fail(original)
        assert left.closed
        assert session.state == "ERROR"
    finally:
        left.close()
        right.close()


def test_private_actual_capability_rejects_unregistered_worker_before_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    claim = runner.phase._read_bytes(root / "phase-claim.json", root, runner.io.MAX_RECORD)
    calls: list[int] = []
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *args: calls.append(1))
    with pytest.raises(runner.RunnerError):
        runner.phase._issue_worker_capability(root, claim, object())
    assert calls == []


def test_owned_test_replay_checks_completion_before_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    runner._run_owned_stage(session, root, "writer", "primary")
    path = root / "phase-terminal.json"
    terminal = runner.phase._read_record(root, path.name)
    terminal["completion"] = {"unowned": True}
    path.write_bytes(runner.io.canonical_json(terminal))
    called: list[int] = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        called.append(1)
        raise AssertionError("reference reached")

    monkeypatch.setattr(runner.phase.reference, "_claimed_reference_path", forbidden)
    with pytest.raises(runner.RunnerError, match="completion_schema"):
        runner.phase.verify_phase(
            root,
            runner.phase._hash(
                runner.phase._read_bytes(root / "phase-claim.json", root, runner.io.MAX_RECORD)
            ),
            session._binding,
            "primary",
            lambda counts: None,
        )
    assert called == []


def cleanup_fixture() -> tuple[Any, Path, Any, Any]:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    runner._run_owned_stage(session, root, "writer", "primary")
    primary = runner._run_owned_stage(session, root, "verifier", "primary")
    independent = runner._run_owned_stage(session, root, "verifier", "reviewer")
    review = runner._test_review_token(session, root, independent)
    session._state = runner.life.State.FINAL_VERDICT  # Explicit private TEST control decision.
    return session, root, primary, review


def test_cleanup_requires_two_live_checks_and_deletes_only_raw() -> None:
    runner = runner_module()
    session, root, primary, review = cleanup_fixture()
    compact = {p.name: p.read_bytes() for p in root.iterdir() if p.name != "phase-payload.bin"}
    runner._cleanup_phase(session, root, primary, review)
    assert not (root / "phase-payload.bin").exists()
    assert all((root / name).read_bytes() == data for name, data in compact.items())
    assert runner.phase._read_record(root, "phase-cleanup-complete.json")["raw_status"] == "ABSENT"
    with pytest.raises(runner.RunnerError):
        runner._cleanup_phase(session, root, primary, review)


@pytest.mark.parametrize("which", ["primary", "reviewer"])
def test_cleanup_refuses_identical_copied_token(which: str) -> None:
    from dataclasses import replace

    runner = runner_module()
    session, root, primary, review = cleanup_fixture()
    if which == "primary":
        primary = replace(primary)
    else:
        review = replace(review)
    with pytest.raises(runner.RunnerError, match="token_issuer"):
        runner._cleanup_phase(session, root, primary, review)
    assert (root / "phase-payload.bin").exists()
    assert session.state == "ERROR"
    assert not (root / "phase-cleanup-complete.json").exists()


def test_cleanup_post_unlink_receipt_failure_is_honest_and_terminal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session, root, primary, review = cleanup_fixture()
    original = runner.phase._record
    error = OSError("absence receipt close")

    def deny(folder: Path, name: str, value: dict[str, Any], **kwargs: Any) -> str:
        if name == "phase-cleanup-complete-candidate.json":
            assert not (folder / "phase-payload.bin").exists()
            original(folder, name, value, **kwargs)
            raise error
        return cast(str, original(folder, name, value, **kwargs))

    monkeypatch.setattr(runner.phase, "_record", deny)
    with pytest.raises(OSError) as caught:
        runner._cleanup_phase(session, root, primary, review)
    assert caught.value is error
    assert not (root / "phase-payload.bin").exists()
    assert not (root / "phase-cleanup-complete.json").exists()
    assert session.state == "ERROR"
    assert runner.phase._read_record(root, "phase-cleanup-error.json")["raw_status"] == "ABSENT"
    with pytest.raises(runner.RunnerError):
        runner._cleanup_phase(session, root, primary, review)


def test_wrong_session_stage_root_is_refused_before_spawn(monkeypatch: pytest.MonkeyPatch) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    other = runner._reserve_test(case_id())
    root = runner._claim_test_phase(other, "development")
    called: list[int] = []
    monkeypatch.setattr(runner.mp.context.SpawnProcess, "start", lambda self: called.append(1))
    with pytest.raises(runner.RunnerError, match="stage_root"):
        runner._run_owned_stage(session, root, "writer", "primary")
    assert session.state == "ERROR"
    assert other.state == "DEVELOPMENT_CLAIMED"
    assert not (root / "phase-payload.bin").exists()
    assert called == []


def test_cleanup_foreign_root_error_never_writes_to_foreign_attempt() -> None:
    runner = runner_module()
    session, root, primary, review = cleanup_fixture()
    other = runner._reserve_test(case_id())
    foreign = runner._claim_test_phase(other, "development")
    before = {p.name: p.read_bytes() for p in foreign.iterdir()}
    with pytest.raises(runner.RunnerError):
        runner._cleanup_phase(session, foreign, primary, review)
    assert {p.name: p.read_bytes() for p in foreign.iterdir()} == before
    assert (root / "phase-payload.bin").exists()
    assert session.state == "ERROR"


def test_actual_registry_and_combined_disk_requirement_are_fixed() -> None:
    runner = runner_module()
    assert (
        runner._actual_registry()
        == runner.io.EXPERIMENT_ROOT / "attempts" / runner.io.PROTOCOL_SHA256
    )
    assert runner._required_initial_free() == 34345762816


def test_saved_readiness_cannot_authorize_actual_reservation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    created: list[Path] = []
    monkeypatch.setattr(Path, "mkdir", lambda self, *args, **kwargs: created.append(self))
    with pytest.raises(runner.RunnerError, match="readiness_issuer"):
        runner._check_readiness(
            {"eligible": True, "source": runner.phase.current_binding().manifest_digest}
        )
    assert created == []


def test_actual_reservation_requires_authenticated_coordinator_registration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    created: list[Path] = []
    monkeypatch.setattr(Path, "mkdir", lambda self, *args, **kwargs: created.append(self))
    with pytest.raises(runner.RunnerError, match="coordinator_issuer"):
        runner._reserve_actual(object())
    assert created == []


def test_test_session_cannot_claim_actual_phase_before_key_or_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    called: list[int] = []
    monkeypatch.setattr(runner.secrets, "token_bytes", lambda *args: called.append(1))
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *args: called.append(1))
    with pytest.raises(runner.RunnerError, match="actual_session"):
        runner._claim_actual_phase(session, "development", bytes(32), "0" * 64)
    assert called == []


def test_coordinator_late_close_cannot_publish_overall_success() -> None:
    runner = runner_module()
    case = case_id()
    with pytest.raises(runner.RunnerError, match="process_exit"):
        runner._run_test_pipeline(case, mode="late-close")
    root = runner.phase.TEST_ANCHOR / "attempts" / runner.hashlib.sha256(case.encode()).hexdigest()
    assert (root / "attempt-result-candidate.json").exists()
    assert (root / "attempt-failure.json").exists()
    assert not (root / "attempt-result.json").exists()


def test_launcher_final_guard_error_is_durable_and_never_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    original = OSError("parent final guard")
    roots: list[Path] = []

    def refuse(session: Any, result: Any, tokens: Any) -> None:
        roots.append(session.registry)
        raise original

    monkeypatch.setattr(runner, "_final_pipeline_guard", refuse)
    with pytest.raises(OSError) as caught:
        runner._run_test_pipeline(case_id())
    assert caught.value is original
    assert roots and (roots[0] / "attempt-failure.json").exists()
    assert not (roots[0] / "attempt-result.json").exists()


def saved_actual_envelopes(monkeypatch: pytest.MonkeyPatch) -> tuple[Any, Path, dict[str, Any]]:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = session.registry
    monkeypatch.setattr(runner, "_actual_registry", lambda: root)
    monkeypatch.setattr(runner.life.ProcessIdentity, "alive", lambda self: True)
    peers = {
        k: {"pid": i, "creation_time_ns": i * 1000}
        for k, i in (("coordinator", 101), ("reviewer", 102), ("helper", 103))
    }
    reservation = runner.phase._read_record(root, "attempt-reserved.json")
    reservation.update(
        {
            "schema": 1,
            "state": "ATTEMPT_RESERVED",
            "scope": "ARTIFICIAL_RESEARCH_ONLY",
            "namespace": runner.io.EXPERIMENT_NAMESPACE,
            "case": runner.io.PROTOCOL_SHA256,
            "attempt_id": runner.io.PROTOCOL_SHA256,
            "owner": peers["coordinator"],
            "reviewer": peers["reviewer"],
            "combined_free_required": runner._required_initial_free(),
            "observed_free": runner._required_initial_free(),
        }
    )
    blob = runner.io.canonical_json(reservation)
    (root / "attempt-reserved.json").write_bytes(blob)
    trial = runner.phase._read_record(root, "attempt-trial.json")
    trial.update(
        namespace=reservation["namespace"],
        attempt_id=reservation["attempt_id"],
        reservation_digest=runner.phase._hash(blob),
    )
    (root / "attempt-trial.json").write_bytes(runner.io.canonical_json(trial))
    registration = {
        "utc": runner.phase._utc(),
        "schema": 1,
        "state": "COORDINATOR_REGISTERED",
        "namespace": runner.io.EXPERIMENT_NAMESPACE,
        "attempt_id": runner.io.PROTOCOL_SHA256,
        "session_id": session._session_id,
        **peers,
        "source_binding": runner.asdict(session._binding),
        "reservation_digest": runner.phase._hash(blob),
        "source_review_digest": session._binding.manifest_digest,
    }
    (root / "attempt-registration.json").write_bytes(runner.io.canonical_json(registration))
    return runner, root, registration


@pytest.mark.parametrize(
    "field,value", [("state", "CLAIMED"), ("schema", True), ("scope", "different"), ("extra", 1)]
)
def test_rehashed_actual_reservation_schema_refused_before_stream(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    runner, root, registration = saved_actual_envelopes(monkeypatch)
    source = runner.phase.current_binding()
    assert runner._read_actual_registration(root, source) == registration
    reservation = runner.phase._read_record(root, "attempt-reserved.json")
    reservation[field] = value
    blob = runner.io.canonical_json(reservation)
    (root / "attempt-reserved.json").write_bytes(blob)
    registration["reservation_digest"] = runner.phase._hash(blob)
    (root / "attempt-registration.json").write_bytes(runner.io.canonical_json(registration))
    calls: list[int] = []
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *args: calls.append(1))
    with pytest.raises(runner.RunnerError, match="reservation_"):
        runner._read_actual_registration(root, source)
    assert calls == []


@pytest.mark.parametrize(
    "field,value", [("schema", True), ("extra", 1), ("source_binding", {}), ("helper", {})]
)
def test_actual_seal_envelope_refused_before_stream(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    runner, root, registration = saved_actual_envelopes(monkeypatch)
    source = runner.phase.current_binding()
    sealed = {
        "utc": runner.phase._utc(),
        "schema": 1,
        "state": "VALIDATION_KEY_SEALED",
        "namespace": runner.io.EXPERIMENT_NAMESPACE,
        "scope": "ARTIFICIAL_RESEARCH_ONLY",
        "commitment": "2" * 64,
        "session_id": registration["session_id"],
        "source_binding": runner.asdict(source),
        "helper": registration["helper"],
    }
    claim = {
        "phase": "development",
        "attempt_id": runner.io.PROTOCOL_SHA256,
        "session_id": registration["session_id"],
        "coordinator": registration["coordinator"],
        "seed_commitment": "1" * 64,
    }
    (root / "validation-sealed.json").write_bytes(runner.io.canonical_json(sealed))
    owner = runner.life.ProcessIdentity(**registration["coordinator"])
    runner._validate_actual_claim_impl(root / "development", claim, owner)
    sealed[field] = value
    (root / "validation-sealed.json").write_bytes(runner.io.canonical_json(sealed))
    calls: list[int] = []
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *args: calls.append(1))
    with pytest.raises(runner.RunnerError, match="seal_binding"):
        runner._validate_actual_claim_impl(root / "development", claim, owner)
    assert calls == []


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema", True),
        ("extra", 1),
        ("source_binding", {}),
        ("helper", {}),
        ("approval_digest", "0" * 64),
    ],
)
def test_rehashed_release_requires_exact_current_approval(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    runner, root, registration = saved_actual_envelopes(monkeypatch)
    source = runner.phase.current_binding()
    sealed = {
        "utc": runner.phase._utc(),
        "schema": 1,
        "state": "VALIDATION_KEY_SEALED",
        "namespace": runner.io.EXPERIMENT_NAMESPACE,
        "scope": "ARTIFICIAL_RESEARCH_ONLY",
        "commitment": "2" * 64,
        "session_id": registration["session_id"],
        "source_binding": runner.asdict(source),
        "helper": registration["helper"],
    }
    (root / "validation-sealed.json").write_bytes(runner.io.canonical_json(sealed))
    development = root / "development"
    development.mkdir()
    runner.phase._record(
        development, "phase-claim.json", {"root": "1" * 64, "seed_commitment": "1" * 64}
    )
    from scripts.research import signal_calendar_score_runner_service as service

    evidence = {"phase": "development", "decision": "PASS", "source": runner.asdict(source)}
    monkeypatch.setattr(service, "_evidence_check", lambda *args, **kwargs: evidence)
    approval = {
        "utc": runner.phase._utc(),
        "schema": 1,
        "state": "REVIEW_APPROVED",
        "scope": "ARTIFICIAL_RESEARCH_ONLY",
        "action": "approve-development",
        "evidence": evidence,
        "control_decision": "PASS",
        "source_review_digest": source.manifest_digest,
        "reviewer": registration["reviewer"],
        "helper": registration["helper"],
    }
    runner.phase._record(root, "development-reviewer-approved.json", approval)
    released = {
        "utc": runner.phase._utc(),
        "schema": 1,
        "state": "VALIDATION_AUTHORIZED",
        "scope": "ARTIFICIAL_RESEARCH_ONLY",
        "session_id": registration["session_id"],
        "source_binding": runner.asdict(source),
        "evidence": evidence,
        "approval_digest": runner.phase._hash(
            runner.phase._read_bytes(
                root / "development-reviewer-approved.json", root, runner.io.MAX_RECORD
            )
        ),
        "commitment": "2" * 64,
        "helper": registration["helper"],
    }
    runner.phase._record(root, "validation-released.json", released)
    claim = {
        "phase": "validation",
        "attempt_id": runner.io.PROTOCOL_SHA256,
        "session_id": registration["session_id"],
        "coordinator": registration["coordinator"],
        "seed_commitment": "2" * 64,
        "root": "2" * 64,
    }
    owner = runner.life.ProcessIdentity(**registration["coordinator"])
    runner._validate_actual_claim_impl(root / "validation", claim, owner)
    released[field] = value
    (root / "validation-released.json").write_bytes(runner.io.canonical_json(released))
    with pytest.raises(runner.RunnerError, match="release_binding"):
        runner._validate_actual_claim_impl(root / "validation", claim, owner)


def coordinator_without_bootstrap(request: Any, control: Any) -> None:
    runner = runner_module()
    vars(runner)["CONTROL_ALLOWANCE"] = 0.5
    runner._run_coordinator(request, control)


def test_coordinator_bootstrap_has_independent_deadline() -> None:
    runner = runner_module()
    context = runner.mp.get_context("spawn")
    request, child_request = context.Pipe()
    control, child_control = context.Pipe()
    child = context.Process(
        target=coordinator_without_bootstrap, args=(child_request, child_control)
    )
    try:
        child.start()
        child_request.close()
        child_control.close()
        child.join(4)
        assert not child.is_alive(), "coordinator blocked without independent watchdog"
        assert child.exitcode == 74
    finally:
        runner.life._shutdown(
            [
                lambda: runner.life._stop_process(child),
                request.close,
                control.close,
                child_request.close,
                child_control.close,
            ],
            None,
        )


def test_actual_replay_permit_requires_owned_worker_before_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    claim = runner.phase._read_bytes(root / "phase-claim.json", root, runner.io.MAX_RECORD)
    calls: list[int] = []
    monkeypatch.setattr(runner.io, "_counter_digest", lambda *args: calls.append(1))
    with pytest.raises(runner.RunnerError, match="worker_issuer"):
        runner.phase._issue_replay_permit(root, claim, object())
    assert calls == []


@pytest.mark.parametrize("peer", ["coordinator", "helper"])
def test_owned_review_stops_when_registered_peer_dies(
    monkeypatch: pytest.MonkeyPatch,
    peer: str,
) -> None:
    runner = runner_module()
    original = runner._resource_snapshot
    killed: list[Any] = []

    def snapshot(root: Path, *args: Any, **kwargs: Any) -> Any:
        session = next(s for s in runner._SESSIONS.values() if s.registry == root.parent)
        if session._stage_context[3] == "reviewer" and not killed:
            record = runner.phase._read_record(
                session.registry,
                "attempt-reserved.json" if peer == "coordinator" else "validation-sealed.json",
            )
            identity = runner.channels._parse_identity(
                record["owner" if peer == "coordinator" else "helper"]
            )
            assert identity.alive()
            killed.append(session)
            runner.psutil.Process(identity.pid).terminate()
        return original(root, *args, **kwargs)

    monkeypatch.setattr(runner, "_resource_snapshot", snapshot)
    try:
        runner._run_test_pipeline(case_id())
    except (runner.io.StudyError, OSError, EOFError):
        pass
    assert killed
    session = killed[0]
    assert session.state == "ERROR"
    assert session._child is None
    assert not (session.registry / "development" / "verified-reviewer.json").exists()
    assert not (session.registry / "validation-released.json").exists()
    assert not (session.registry / "attempt-result.json").exists()


def test_launcher_adoption_failure_is_durable_without_loading_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    error = OSError("adoption source failed")
    roots: list[Path] = []

    def refuse(root: Path) -> Any:
        roots.append(root)
        raise error

    monkeypatch.setattr(runner, "_adopt_reviewer_view", refuse)
    with pytest.raises(OSError) as caught:
        runner._run_test_pipeline(case_id())
    assert caught.value is error
    assert roots and (roots[0] / "attempt-reserved.json").exists()
    assert (roots[0] / "attempt-failure.json").exists()
    assert not (roots[0] / "validation-sealed.json").exists()


def test_stage_pipe_setup_failure_closes_every_created_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    error = OSError("second pipe creation")
    closed: list[int] = []

    class Endpoint:
        def __init__(self, number: int) -> None:
            self.number = number

        def close(self) -> None:
            closed.append(self.number)
            if self.number == 0:
                raise OSError("secondary close")

    class Context:
        def __init__(self) -> None:
            self.calls = 0

        def Pipe(self, **kwargs: Any) -> Any:
            self.calls += 1
            if self.calls == 2:
                raise error
            return Endpoint(0), Endpoint(1)

    monkeypatch.setattr(runner.mp, "get_context", lambda method: Context())
    with pytest.raises(OSError) as caught:
        runner._run_owned_stage(session, root, "writer", "primary")
    assert caught.value is error
    assert closed == [0, 1]
    assert session.state == "ERROR"


def test_partial_control_frame_has_short_bound_with_long_stage_wait(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    release = runner.threading.Event()

    class Connection:
        def poll(self, timeout: float) -> bool:
            return True

        def close(self) -> None:
            release.set()

    class Peer:
        def alive(self) -> bool:
            return True

    class Channel:
        connection = Connection()
        remote = Peer()

        def receive(self) -> Any:
            release.wait(3)
            raise EOFError("partial frame")

    class Process:
        exitcode = None

    stopped: list[Any] = []
    monkeypatch.setattr(runner.life, "_stop_process", lambda process: stopped.append(process))
    monkeypatch.setattr(runner, "CONTROL_ALLOWANCE", 0.05)
    with pytest.raises(runner.RunnerError, match="partial_frame_deadline"):
        runner._receive_owned(Channel(), Process(), 2.0, runner.phase.current_binding())
    assert stopped and release.is_set()


def _reject_unowned_service_registry(request: Any, approval: Any, bootstrap: Any) -> None:
    service = importlib.import_module("scripts.research.signal_calendar_score_runner_service")
    try:
        service.run_reviewer_service(request, approval, bootstrap)
    except BaseException as error:
        assert str(error) == "path_escape"
    else:
        raise AssertionError("unowned registry accepted")
    finally:
        request.close()
        approval.close()
        bootstrap.close()


def test_service_refusal_never_persists_to_unowned_registry(tmp_path: Path) -> None:
    runner = runner_module()
    context = runner.mp.get_context("spawn")
    request, owned_request = context.Pipe()
    approval, owned_approval = context.Pipe()
    bootstrap, owned_bootstrap = context.Pipe()
    child = context.Process(
        target=_reject_unowned_service_registry,
        args=(owned_request, owned_approval, owned_bootstrap),
    )
    child.start()
    try:
        owner = runner.life.ProcessIdentity.current()
        peer = runner.life.ProcessIdentity(
            child.pid, round(runner.psutil.Process(child.pid).create_time() * 1e9)
        )
        source = runner.phase.current_binding()
        bootstrap.send_bytes(
            runner.io.canonical_json(
                {
                    "utc": runner.phase._utc(),
                    "registry": str(tmp_path),
                    "coordinator": runner.asdict(owner),
                    "reviewer": runner.asdict(owner),
                    "helper": runner.asdict(peer),
                    "source_binding": runner.asdict(source),
                    "source_review_digest": source.manifest_digest,
                    "session_id": "a" * 64,
                    "challenge": "b" * 64,
                    "coordinator_secret": "c" * 64,
                    "reviewer_secret": "d" * 64,
                    "namespace": runner.io.TEST_NAMESPACE,
                }
            )
        )
        child.join(10)
        assert child.exitcode == 0
        assert not (tmp_path / "service-failure.json").exists()
    finally:
        runner.life._shutdown(
            [
                lambda: runner.life._stop_process(child),
                request.close,
                owned_request.close,
                approval.close,
                owned_approval.close,
                bootstrap.close,
                owned_bootstrap.close,
            ],
            None,
        )


@pytest.mark.parametrize("fault", ["malformed-ready", "duplicate-ready", "missing-ready"])
def test_ready_refusal_is_terminal_before_any_phase_payload(
    monkeypatch: pytest.MonkeyPatch,
    fault: str,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    original = runner._stage_limit
    if fault == "missing-ready":
        monkeypatch.setattr(runner, "_stage_limit", lambda *a: 1.5)
    with pytest.raises((runner.RunnerError, runner.life.LifecycleError)):
        runner._run_owned_stage(session, root, "writer", "primary", _test_fault=fault)
    assert session.state == "ERROR"
    assert not (root / "phase-payload.bin").exists()
    assert not (root / "phase-index.jsonl").exists()
    assert not (root / "phase-terminal.json").exists()
    assert session._child is None
    monkeypatch.setattr(runner, "_stage_limit", original)


def test_parent_start_refusal_preserves_error_and_never_starts_data_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    error = OSError("START send denied")

    def refuse(*args: Any) -> None:
        raise error

    monkeypatch.setattr(runner, "_send_stage_start", refuse)
    with pytest.raises(OSError) as caught:
        runner._run_owned_stage(session, root, "writer", "primary")
    assert caught.value is error
    assert session.state == "ERROR"
    assert not (root / "phase-payload.bin").exists()
    assert not (root / "phase-terminal.json").exists()
    assert session._child is None


def test_delayed_duplicate_start_is_refused_during_data_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runner = runner_module()
    original = runner._send_stage_start

    def duplicate(channel: Any, body: Any) -> None:
        original(channel, body)
        runner.time.sleep(0.1)
        original(channel, body)

    monkeypatch.setattr(runner, "_send_stage_start", duplicate)
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    with pytest.raises(runner.RunnerError):
        runner._run_owned_stage(session, root, "writer", "primary")
    assert session.state == "ERROR"
    assert not (root / "phase-terminal.json").exists()


def test_ready_after_finished_heartbeat_cannot_publish_success() -> None:
    runner = runner_module()
    session = runner._reserve_test(case_id())
    root = runner._claim_test_phase(session, "development")
    with pytest.raises(runner.RunnerError, match="duplicate_ready"):
        runner._run_owned_stage(session, root, "writer", "primary", _test_fault="late-ready")
    assert session.state == "ERROR"
    assert not (root / "phase-terminal.json").exists()
