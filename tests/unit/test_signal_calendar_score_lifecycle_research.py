from pathlib import Path
from typing import Any, cast

import psutil  # type: ignore[import-untyped]
import pytest
from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_study as study


@pytest.fixture
def anchor(tmp_path: Path, monkeypatch: Any) -> Path:
    monkeypatch.setattr(life, "_FIXTURE_ANCHOR", tmp_path)
    return tmp_path


def test_reservation_is_fixed_exclusive_before_any_key(anchor: Path) -> None:
    domain = life.FixtureDomain("once")
    session = life.reserve_fixture(domain, life.current_binding())
    assert session.state is life.State.ATTEMPT_RESERVED
    record = life.read_record(session.registry / "attempt-reserved.json", session.registry)
    assert record["state"] == "ATTEMPT_RESERVED"
    assert record["study_permission"] is False
    assert record["seed_commitment"] is None
    with pytest.raises(life.LifecycleError, match="exhausted"):
        life.reserve_fixture(life.FixtureDomain("once"), life.current_binding())


@pytest.mark.parametrize("case", ["", "../escape", "x" * 65, True, 1])
def test_invalid_domain_never_reserves(anchor: Path, case: Any) -> None:
    with pytest.raises(life.LifecycleError):
        life.FixtureDomain(case)
    assert list(anchor.iterdir()) == []


def test_experimental_domain_always_refuses(anchor: Path) -> None:
    with pytest.raises(life.LifecycleError, match="test_domain"):
        life.FixtureDomain("actual", namespace=study.EXPERIMENT_NAMESPACE)
    assert list(anchor.iterdir()) == []


def test_failed_durable_reservation_remains_exhausted(anchor: Path, monkeypatch: Any) -> None:
    original = study._exclusive_record
    error = OSError("actual bytes then durability failed")

    def failed(*args: Any, **kwargs: Any) -> None:
        original(*args, **kwargs)
        raise error

    monkeypatch.setattr(study, "_exclusive_record", failed)
    with pytest.raises(OSError) as caught:
        life.reserve_fixture(life.FixtureDomain("durability"), life.current_binding())
    assert caught.value is error
    monkeypatch.setattr(study, "_exclusive_record", original)
    with pytest.raises(life.LifecycleError, match="exhausted"):
        life.reserve_fixture(life.FixtureDomain("durability"), life.current_binding())


def test_saved_reservation_cannot_restore_live_state(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("saved"), life.current_binding())
    with pytest.raises(life.LifecycleError, match="transition"):
        session.claim_development()
    session.fail(life.LifecycleError("fixture stopped"))
    assert session.state is life.State.ERROR
    with pytest.raises(life.LifecycleError):
        session.claim_development()


def test_postwrite_candidate_corruption_never_publishes(anchor: Path, monkeypatch: Any) -> None:
    session = life.reserve_fixture(life.FixtureDomain("candidate"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    original = study._exclusive_record

    def corrupt(path: Path, *args: Any, **kwargs: Any) -> None:
        original(path, *args, **kwargs)
        if path.name.endswith(".pending"):
            path.write_bytes(b"{}\n")

    monkeypatch.setattr(study, "_exclusive_record", corrupt)
    with pytest.raises(life.LifecycleError):
        session.claim_development()
    assert session.state is life.State.ERROR
    assert not (session.registry / "development_claimed.json").exists()


def test_invalid_transition_terminalizes_live_session(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("terminal"), life.current_binding())
    with pytest.raises(life.LifecycleError, match="transition"):
        session.claim_development()
    assert session.state is life.State.ERROR


def test_direct_live_session_constructor_never_issues(anchor: Path) -> None:
    with pytest.raises(life.LifecycleError, match="session_issuer"):
        life.LiveSession(life.FixtureDomain("forged"), life.current_binding(), anchor / "outside")


def test_unregistered_copy_cannot_operate(anchor: Path) -> None:
    import copy

    session = life.reserve_fixture(life.FixtureDomain("copy"), life.current_binding())
    forged = copy.copy(session)
    with pytest.raises(life.LifecycleError, match="session_issuer"):
        forged.claim_development()


def test_authenticated_channel_exact_types_and_sequences() -> None:
    import multiprocessing as mp

    from scripts.research import signal_calendar_score_lifecycle_service as service

    left, right = mp.get_context("spawn").Pipe()
    identity = life.ProcessIdentity.current()
    binding = life.current_binding()
    try:
        a = service.FrameChannel(
            left, b"a" * 32, "coordinator", "b" * 64, "c" * 64, identity, identity, binding
        )
        b = service.FrameChannel(
            right, b"a" * 32, "coordinator", "b" * 64, "c" * 64, identity, identity, binding
        )
        a.send({"action": "status"})
        assert b.receive() == {"action": "status"}
        a.send({"action": "status"})
        assert b.receive() == {"action": "status"}
    finally:
        left.close()
        right.close()


def test_channel_wrong_role_cannot_authenticate() -> None:
    import multiprocessing as mp

    from scripts.research import signal_calendar_score_lifecycle_service as service

    left, right = mp.get_context("spawn").Pipe()
    identity = life.ProcessIdentity.current()
    binding = life.current_binding()
    try:
        a = service.FrameChannel(
            left, b"a" * 32, "coordinator", "b" * 64, "c" * 64, identity, identity, binding
        )
        b = service.FrameChannel(
            right, b"d" * 32, "reviewer", "b" * 64, "c" * 64, identity, identity, binding
        )
        a.send({"action": "approve"})
        with pytest.raises(life.LifecycleError, match="authentication"):
            b.receive()
    finally:
        left.close()
        right.close()


def test_owned_child_completion_and_verification(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("child"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    child = life.launch_fixture_child(session)
    try:
        completion = life.supervise_fixture_child(session, child)
        assert completion.proof.paths == 1
        assert completion.proof.metrics == 3
        assert completion.proof.words == 12300
        session.complete_development(completion)
        verification = life.verify_fixture_evidence(session, completion)
        session.verify_development(verification)
        assert session.state is life.State.DEVELOPMENT_VERIFIED
        assert (session.evidence_root / "fixture-payload.bin").stat().st_size == 2050
    finally:
        life.stop_fixture_child(child)


def test_unregistered_child_is_refused(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("wrong-child"), life.current_binding())
    with pytest.raises(life.LifecycleError, match="child_issuer"):
        life.supervise_fixture_child(session, object())
    assert session.state is life.State.ERROR


def test_mutated_attempt_identity_never_claims(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("identity"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.attempt_id = "f" * 64
    with pytest.raises(life.LifecycleError, match="reservation_binding"):
        session.claim_development()
    assert session.state is life.State.ERROR
    assert not (session.registry / "development_claimed.json").exists()


def fixture_coordinator(
    anchor_path: str, case: str, control: Any, channel: Any, secret: bytes, mode: str
) -> None:
    import json
    from dataclasses import asdict

    from scripts.research import signal_calendar_score_lifecycle_service as service

    life._FIXTURE_ANCHOR = Path(anchor_path)
    session = life.reserve_fixture(life.FixtureDomain(case), life.current_binding())
    control.send_bytes(
        study.canonical_json(
            {
                "registry": str(session.registry),
                "owner": asdict(session.owner),
                "session_id": session.session_id,
                "attempt_id": session.attempt_id,
                "domain_id": session.domain.domain_id,
                "source_binding": asdict(session.binding),
            }
        )
    )
    child = None
    try:
        bootstrap = json.loads(control.recv_bytes(4096))
        client = service.CoordinatorClient(session, channel, secret, bootstrap)
        client.seal()
        if mode == "forge":
            client.request({"action": "approve"})
        else:
            session.claim_development()
            child = life.launch_fixture_child(session)
            completion = life.supervise_fixture_child(session, child)
            session.complete_development(completion)
            verification = life.verify_fixture_evidence(session, completion)
            session.verify_development(verification)
            control.send_bytes(study.canonical_json({"ready": str(session.evidence_root)}))
            message = control.recv_bytes(4096)
            if mode == "valid-forge":
                client.request({"action": "approve", **json.loads(message)})
            approval = session.accept_reviewer_response(client.status_frame())
            if mode == "copy-release":
                from dataclasses import replace

                approval = replace(approval)
            if mode == "failed-persist-release":
                body = json.loads(approval.body)
                original_record = study._exclusive_record

                def deny_failure(path: Path, *args: Any, **kwargs: Any) -> None:
                    if path.name == "failure.json":
                        raise OSError("failure persistence denied")
                    original_record(path, *args, **kwargs)

                study._exclusive_record = deny_failure
                session.fail(life.LifecycleError("local failure"))
                client.channel.send(
                    {
                        "action": "release",
                        "evidence": body["evidence"],
                        "primary_receipt_digest": body["primary_receipt_digest"],
                    }
                )
                reply = client.channel.receive()
                control.send_bytes(
                    study.canonical_json(
                        {"released_after_failure": reply.get("state") == "RELEASED"}
                    )
                )
                return
            if mode == "failed-release":
                body = json.loads(approval.body)
                session.fail(life.LifecycleError("local failure"))
                client.request(
                    {
                        "action": "release",
                        "evidence": body["evidence"],
                        "primary_receipt_digest": body["primary_receipt_digest"],
                    }
                )
                control.send_bytes(study.canonical_json({"released_after_failure": True}))
                return
            key = session.authorize_validation(approval)
            assert key == bytes([2]) * 32
            if mode == "replay":
                body = json.loads(approval.body)
                client.request(
                    {
                        "action": "release",
                        "evidence": body["evidence"],
                        "primary_receipt_digest": body["primary_receipt_digest"],
                    }
                )
            session.claim_validation()
            control.send_bytes(
                study.canonical_json({"released": True, "registry": str(session.registry)})
            )
            if mode in ("full", "final-drift") or mode.startswith("cleanup"):
                child = life.launch_fixture_child(session)
                completed = life.supervise_fixture_child(session, child)
                session.complete_validation(completed)
                verified = life.verify_fixture_evidence(session, completed)
                session.verify_validation(verified)
                control.send_bytes(
                    study.canonical_json({"validation_ready": str(session.evidence_root)})
                )
                control.recv_bytes(64)
                validation_review = session.accept_reviewer_response(
                    client.status_frame(validation=True)
                )
                if mode == "final-drift":
                    path = session.evidence_root / "verified-primary.json"
                    path.write_bytes(b"{}\n")
                session.finish_fixture()
                client.close()
                if mode.startswith("cleanup"):
                    if mode == "cleanup-unlink":
                        original_unlink = Path.unlink

                        def failed_unlink(path: Path, *args: Any, **kwargs: Any) -> None:
                            if path.name == "fixture-payload.bin":
                                raise OSError("unlink denied")
                            original_unlink(path, *args, **kwargs)

                        pytest.MonkeyPatch().setattr(Path, "unlink", failed_unlink)
                    if mode == "cleanup-after-unlink":
                        original_record = study._exclusive_record
                        denied = OSError("completion receipt denied")

                        def deny_completion(path: Path, *args: Any, **kwargs: Any) -> None:
                            if path.name.startswith("cleanup-validation-complete.json"):
                                raise denied
                            original_record(path, *args, **kwargs)

                        pytest.MonkeyPatch().setattr(study, "_exclusive_record", deny_completion)
                        try:
                            life.cleanup_fixture_raw(session, verified, validation_review)
                        except OSError as error:
                            assert error is denied
                            with pytest.raises(life.LifecycleError, match="terminal_state"):
                                life.cleanup_fixture_raw(session, verified, validation_review)
                            control.send_bytes(
                                study.canonical_json(
                                    {
                                        "error": type(error).__name__,
                                        "detail": str(error),
                                        "state": session.state.value,
                                        "retry_terminal": True,
                                    }
                                )
                            )
                            return
                        raise AssertionError("cleanup succeeded after receipt denial")
                    if mode == "cleanup-copy-reviewer":
                        from dataclasses import replace

                        validation_review = replace(validation_review)
                    if mode == "cleanup-copy-primary":
                        from dataclasses import replace

                        verified = replace(verified)
                    life.cleanup_fixture_raw(session, verified, validation_review)
                    life.cleanup_fixture_raw(session, verification, approval)
                control.send_bytes(
                    study.canonical_json(
                        {"final": session.state.value, "registry": str(session.registry)}
                    )
                )
    except BaseException as error:
        session.fail(error)
        control.send_bytes(
            study.canonical_json({"error": type(error).__name__, "detail": str(error)})
        )
    finally:
        if child is not None:
            life.stop_fixture_child(child)
        channel.close()
        control.close()


def run_fixture_demo(case: str, anchor_path: Path, *, mode: str = "pass") -> dict[str, Any]:
    import json
    import multiprocessing as mp
    import secrets
    from dataclasses import asdict

    from scripts.research import signal_calendar_score_lifecycle_service as service
    from scripts.research import signal_calendar_score_verify as verify

    context = mp.get_context("spawn")
    control, coordinator_control = context.Pipe()
    coordinator_channel, service_coordinator = context.Pipe()
    reviewer_channel, service_reviewer = context.Pipe()
    bootstrap, service_bootstrap = context.Pipe()
    secret, reviewer_secret, challenge = (
        secrets.token_bytes(32),
        secrets.token_bytes(32),
        secrets.token_hex(32),
    )
    coordinator = context.Process(
        target=fixture_coordinator,
        args=(str(anchor_path), case, coordinator_control, coordinator_channel, secret, mode),
    )
    helper = None
    try:
        coordinator.start()
        coordinator_control.close()
        coordinator_channel.close()
        assert control.poll(10)
        reservation = json.loads(control.recv_bytes(4096))
        registry = Path(reservation["registry"])
        record = life.read_record(registry / "attempt-reserved.json", registry)
        if mode == "bad-reservation":
            record["body"]["future_replicates"]["validation"] = 1
            record["record_digest"] = life._digest(study.canonical_json(record))
            (registry / "attempt-reserved.json").write_bytes(study.canonical_json(record))
        helper = context.Process(
            target=fixture_reviewer_target,
            args=(anchor_path, service_coordinator, service_reviewer, service_bootstrap),
        )
        helper.start()
        assert helper.pid is not None
        service_coordinator.close()
        service_reviewer.close()
        service_bootstrap.close()
        peer = life.ProcessIdentity(
            helper.pid,
            round(__import__("psutil").Process(helper.pid).create_time() * 1_000_000_000),
        )
        parent = life.ProcessIdentity.current()
        boot = {
            **reservation,
            "case_id": case,
            "anchor": str(anchor_path),
            "challenge": challenge,
            "coordinator_secret": secret.hex(),
            "reviewer_secret": reviewer_secret.hex(),
            "reviewer": asdict(parent),
            "helper": asdict(peer),
        }
        bootstrap.send_bytes(study.canonical_json(boot))
        control.send_bytes(study.canonical_json({"helper": asdict(peer), "challenge": challenge}))
        if mode == "forge":
            assert control.poll(10)
            return cast(dict[str, Any], json.loads(control.recv_bytes(4096)))
        assert control.poll(10)
        ready = json.loads(control.recv_bytes(4096))
        if "error" in ready:
            return cast(dict[str, Any], ready)
        root = Path(ready["ready"])
        if mode == "helper-death":
            helper.kill()
            helper.join(3)
            control.send_bytes(b"checked")
            assert control.poll(10)
            return cast(dict[str, Any], json.loads(control.recv_bytes(4096)))
        if mode == "coordinator-death":
            coordinator.kill()
            coordinator.join(3)
            helper.join(3)
            assert not helper.is_alive()
            return {"peer_failure": True, "registry": str(registry)}
        life.verify_saved_fixture_bounded(root)
        reviewer = service.FrameChannel(
            reviewer_channel,
            reviewer_secret,
            "reviewer",
            reservation["session_id"],
            challenge,
            parent,
            peer,
            life.current_binding(),
        )
        evidence, _ = life._artifact_fields(
            root, reservation["attempt_id"], reservation["session_id"], reservation["domain_id"]
        )
        check = {
            "evidence": asdict(evidence),
            "primary_receipt_digest": study._hash_file(root / "verified-primary.json"),
            "independent_receipt_digest": study._hash_file(root / "verified-reviewer.json"),
            "source_review_digest": life.current_binding().manifest_digest,
            "decision": "FIXTURE_ACCEPTED",
        }
        if mode == "changed_check":
            path = root / "verified-reviewer.json"
            record = verify._unseal(json.loads(path.read_bytes()))
            record["seconds"] += 0.001
            path.write_bytes(verify.canonical(verify._seal(record)))
        if mode == "valid-forge":
            control.send_bytes(study.canonical_json(check))
            assert control.poll(10)
            return cast(dict[str, Any], json.loads(control.recv_bytes(4096)))
        reviewer.send({"action": "approve", **check})
        assert reviewer_channel.poll(10)
        approved = reviewer.receive()
        assert approved["state"] == "APPROVED"
        control.send_bytes(b"checked")
        assert control.poll(10)
        result = json.loads(control.recv_bytes(4096))
        if (mode in ("full", "final-drift") or mode.startswith("cleanup")) and result.get(
            "released"
        ):
            assert control.poll(10)
            ready = json.loads(control.recv_bytes(4096))
            if "error" in ready:
                return cast(dict[str, Any], ready)
            root = Path(ready["validation_ready"])
            life.verify_saved_fixture_bounded(root)
            evidence, _ = life._artifact_fields(
                root,
                reservation["attempt_id"],
                reservation["session_id"],
                reservation["domain_id"],
                phase="validation_fixture",
            )
            reviewer.send(
                {
                    "action": "approve-validation",
                    "evidence": asdict(evidence),
                    "primary_receipt_digest": study._hash_file(root / "verified-primary.json"),
                    "independent_receipt_digest": study._hash_file(root / "verified-reviewer.json"),
                    "source_review_digest": life.current_binding().manifest_digest,
                    "decision": "FIXTURE_ACCEPTED",
                }
            )
            assert reviewer_channel.poll(10)
            assert reviewer.receive()["state"] == "APPROVED"
            control.send_bytes(b"checked")
            assert control.poll(10)
            return cast(dict[str, Any], json.loads(control.recv_bytes(4096)))
        return cast(dict[str, Any], result)
    finally:
        for process in (coordinator, helper):
            if process is not None and process.pid is not None:
                process.join(2)
                if process.is_alive():
                    process.terminate()
                    process.join(3)
        for connection in (
            control,
            coordinator_control,
            coordinator_channel,
            service_coordinator,
            reviewer_channel,
            service_reviewer,
            bootstrap,
            service_bootstrap,
        ):
            connection.close()


def test_real_reviewer_process_release_once(anchor: Path) -> None:
    result = run_fixture_demo("real", anchor)
    assert result.get("released") is True, result
    registry = Path(result["registry"])
    assert (registry / "reviewer-approved.json").exists()
    assert (registry / "release-once.json").exists()
    assert (registry / "validation_claimed.json").exists()
    assert not list(registry.glob("*secret*"))


def test_coordinator_authenticated_self_approval_is_refused(anchor: Path) -> None:
    result = run_fixture_demo("forger", anchor, mode="forge")
    assert result.get("error") == "LifecycleError", result


def test_primary_verification_runs_in_separate_bounded_child(
    anchor: Path, monkeypatch: Any
) -> None:
    from scripts.research import signal_calendar_score_verify as verify

    session = life.reserve_fixture(life.FixtureDomain("verify-child"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    child = life.launch_fixture_child(session)
    try:
        completion = life.supervise_fixture_child(session, child)
        session.complete_development(completion)

        def inline_forbidden(*args: Any, **kwargs: Any) -> Any:
            raise AssertionError("verification ran in coordinator")

        monkeypatch.setattr(verify, "verify_fixture", inline_forbidden)
        token = life.verify_fixture_evidence(session, completion)
        assert token.receipt_digest
    finally:
        life.stop_fixture_child(child)


def sleeping_fixture_writer(*args: Any) -> None:
    import time

    time.sleep(10)


def test_foreign_child_refusal_does_not_terminate_other_owner(
    anchor: Path, monkeypatch: Any
) -> None:
    owner = life.reserve_fixture(life.FixtureDomain("owner"), life.current_binding())
    owner._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    owner.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)
    child = life.launch_fixture_child(owner)
    intruder = life.reserve_fixture(life.FixtureDomain("intruder"), life.current_binding())
    try:
        with pytest.raises(life.LifecycleError, match="child_issuer"):
            life.supervise_fixture_child(intruder, child)
        assert child.process.is_alive()
    finally:
        life.stop_fixture_child(child)


def test_startup_failure_stops_only_started_child(anchor: Path, monkeypatch: Any) -> None:
    import multiprocessing as mp

    session = life.reserve_fixture(life.FixtureDomain("startup"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    context = mp.get_context("spawn")
    started: list[Any] = []

    class Context:
        Pipe = staticmethod(context.Pipe)

        @staticmethod
        def Process(*args: Any, **kwargs: Any) -> Any:
            process = context.Process(*args, **kwargs)
            started.append(process)
            return process

    error = OSError("monitor startup")
    monkeypatch.setattr(mp, "get_context", lambda *args: Context())
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)

    def failed_start(*args: Any) -> None:
        raise error

    monkeypatch.setattr(__import__("threading").Thread, "start", failed_start)
    try:
        with pytest.raises(OSError) as caught:
            life.launch_fixture_child(session)
        assert caught.value is error
        assert len(started) == 1
        assert not started[0].is_alive()
    finally:
        for process in started:
            if process.is_alive():
                process.terminate()
                process.join(3)


def test_owned_child_handle_process_is_readonly(anchor: Path, monkeypatch: Any) -> None:
    from dataclasses import FrozenInstanceError

    session = life.reserve_fixture(life.FixtureDomain("readonly-child"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)
    child = life.launch_fixture_child(session)
    original = child.process
    try:
        with pytest.raises(FrozenInstanceError):
            pytest.MonkeyPatch().setattr(child, "process", object())
    finally:
        object.__setattr__(child, "process", original)
        life.stop_fixture_child(child)


def test_rehashed_receipt_after_reviewer_check_never_approves(anchor: Path) -> None:
    with pytest.raises(life.LifecycleError):
        run_fixture_demo("changed-check", anchor, mode="changed_check")
    registry = anchor / "attempts" / life.FixtureDomain("changed-check").domain_id
    assert not (registry / "release-once.json").exists()


def fixture_reviewer_target(anchor_path: Path, *args: Any) -> None:
    from scripts.research import signal_calendar_score_lifecycle_service as service

    life._FIXTURE_ANCHOR = anchor_path
    service.run_fixture_reviewer(*args)


def test_fixed_fixture_validation_completes_without_study_authority(anchor: Path) -> None:
    result = run_fixture_demo("full", anchor, mode="full")
    assert result.get("final") == "FINAL_VERDICT", result
    record = life.read_record(
        Path(result["registry"]) / "final_verdict.json", Path(result["registry"])
    )
    assert record["body"]["decision"] == "FIXTURE_ACCEPTED"
    assert record["study_permission"] is False


def stalled_fixture_reviewer(anchor_path: Path, *args: Any) -> None:
    from scripts.research import signal_calendar_score_lifecycle_service as service

    life._FIXTURE_ANCHOR = anchor_path
    life.FIXTURE_TIMEOUT = 0.5
    service.run_fixture_reviewer(*args)


def test_service_watchdog_bounds_stalled_bootstrap(anchor: Path) -> None:
    import multiprocessing as mp

    context = mp.get_context("spawn")
    pairs = [context.Pipe() for _ in range(3)]
    process = context.Process(
        target=stalled_fixture_reviewer, args=(anchor, *(pair[1] for pair in pairs))
    )
    try:
        process.start()
        for pair in pairs:
            pair[1].close()
        process.join(3)
        assert not process.is_alive()
    finally:
        if process.is_alive():
            process.terminate()
            process.join(3)
        for pair in pairs:
            for connection in pair:
                connection.close()


def test_malformed_seal_reply_terminalizes(anchor: Path, monkeypatch: Any) -> None:
    from scripts.research import signal_calendar_score_lifecycle_service as service

    session = life.reserve_fixture(life.FixtureDomain("bad-seal"), life.current_binding())
    client = object.__new__(service.CoordinatorClient)
    client.session = session
    monkeypatch.setattr(client, "request", lambda body: {"state": "WRONG"})
    with pytest.raises(life.LifecycleError):
        client.seal()
    assert session.state is life.State.ERROR


def test_completion_receive_has_owned_deadline(anchor: Path, monkeypatch: Any) -> None:
    import multiprocessing as mp
    import time

    reader, held_writer = mp.get_context("spawn").Pipe(duplex=False)
    monkeypatch.setattr(life, "FIXTURE_TIMEOUT", 0.3)
    try:
        with pytest.raises(life.LifecycleError, match="fixture_timeout"):
            life._bounded_receive(reader, anchor, time.monotonic())
    finally:
        reader.close()
        held_writer.close()


def test_reviewer_verification_is_bounded_separate_process(anchor: Path, monkeypatch: Any) -> None:
    from scripts.research import signal_calendar_score_verify as verify

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("reviewer verification ran in launcher")

    monkeypatch.setattr(verify, "verify_fixture", forbidden)
    result = run_fixture_demo("reviewer-child", anchor)
    assert result.get("released") is True, result


def test_rehashed_report_schema_drift_never_mints_completion(anchor: Path) -> None:
    import json

    from scripts.research import signal_calendar_score_verify as verify

    session = life.reserve_fixture(life.FixtureDomain("report-schema"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    child = life.launch_fixture_child(session)
    try:
        child.process.join(10)
        assert child.process.exitcode == 0
        report = session.evidence_root / "fixture-report.json"
        value = verify._unseal(json.loads(report.read_bytes()))
        value["unexpected"] = 1
        report.write_bytes(verify.canonical(verify._seal(value)))
        terminal = session.evidence_root / "fixture-terminal.json"
        value = verify._unseal(json.loads(terminal.read_bytes()))
        value["report_digest"] = study._hash_file(report)
        terminal.write_bytes(verify.canonical(verify._seal(value)))
        with pytest.raises(life.LifecycleError, match="fixture_report"):
            life.supervise_fixture_child(session, child)
        assert session.state is life.State.ERROR
    finally:
        life.stop_fixture_child(child)


def test_valid_complete_approval_on_coordinator_channel_is_refused(anchor: Path) -> None:
    result = run_fixture_demo("valid-forge", anchor, mode="valid-forge")
    assert result.get("error") == "LifecycleError", result
    registry = anchor / "attempts" / life.FixtureDomain("valid-forge").domain_id
    assert not (registry / "reviewer-approved.json").exists()
    assert not (registry / "release-once.json").exists()


def test_actual_second_release_with_fresh_authenticated_frame_is_refused(anchor: Path) -> None:
    result = run_fixture_demo("replay", anchor, mode="replay")
    assert result.get("error") == "LifecycleError", result
    registry = anchor / "attempts" / life.FixtureDomain("replay").domain_id
    assert (registry / "release-once.json").exists()
    assert not (registry / "validation_claimed.json").exists()


def test_dual_verified_cleanup_deletes_only_raw(anchor: Path) -> None:
    result = run_fixture_demo("cleanup", anchor, mode="cleanup")
    assert result.get("final") == "FINAL_VERDICT", result
    registry = Path(result["registry"])
    for name in ("evidence", "validation-evidence"):
        root = registry / name
        assert not (root / "fixture-payload.bin").exists()
        for retained in (
            "fixture-index.jsonl",
            "fixture-report.json",
            "fixture-terminal.json",
            "verified-primary.json",
            "verified-reviewer.json",
        ):
            assert (root / retained).is_file()
    assert (registry / "cleanup-validation-complete.json").exists()
    assert (registry / "cleanup-development-complete.json").exists()


def test_cleanup_unlink_failure_keeps_raw_and_no_success(anchor: Path) -> None:
    result = run_fixture_demo("cleanup-denied", anchor, mode="cleanup-unlink")
    assert result.get("error") == "OSError", result
    registry = anchor / "attempts" / life.FixtureDomain("cleanup-denied").domain_id
    assert (registry / "validation-evidence/fixture-payload.bin").exists()
    assert not (registry / "cleanup-validation-complete.json").exists()
    assert (registry / "cleanup-validation-error.json").exists()


def test_premature_finalization_terminalizes(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("premature-final"), life.current_binding())
    with pytest.raises(life.LifecycleError):
        session.finish_fixture()
    assert session.state is life.State.ERROR


def test_finalization_rechecks_current_approved_evidence(anchor: Path) -> None:
    result = run_fixture_demo("final-drift", anchor, mode="final-drift")
    assert "error" in result
    registry = anchor / "attempts" / life.FixtureDomain("final-drift").domain_id
    assert not (registry / "final_verdict.json").exists()


@pytest.mark.parametrize("copied", ["reviewer", "primary"])
def test_cleanup_refuses_identity_copies_of_genuine_tokens(anchor: Path, copied: str) -> None:
    case = "copy-" + copied
    result = run_fixture_demo(case, anchor, mode="cleanup-copy-" + copied)
    assert result["detail"] == "token_issuer"
    registry = anchor / "attempts" / life.FixtureDomain(case).domain_id
    assert (registry / "validation-evidence/fixture-payload.bin").exists()
    assert not (registry / "cleanup-validation-intent.json").exists()


def test_process_swapped_handle_never_stops_rejected_process(
    anchor: Path, monkeypatch: Any
) -> None:
    session = life.reserve_fixture(life.FixtureDomain("swapped-process"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)
    child = life.launch_fixture_child(session)
    actual = child.process
    calls: list[str] = []

    class RejectedProcess:
        pid = 1

        def is_alive(self) -> bool:
            return False

        def join(self, timeout: float) -> None:
            calls.append("join")

    object.__setattr__(child, "process", RejectedProcess())
    try:
        with pytest.raises(life.LifecycleError, match="child_issuer"):
            life.supervise_fixture_child(session, child)
        assert calls == []
        assert not actual.is_alive()
        assert not child.monitor.is_alive()
    finally:
        object.__setattr__(child, "process", actual)
        life.stop_fixture_child(child)


def test_reservation_retains_complete_extended_source_manifest(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("full-manifest"), life.current_binding())
    record = life.read_record(session.registry / "attempt-reserved.json", session.registry)
    payload = record["body"]["extended_manifest"]
    assert life._digest(study.canonical_json(payload)) == session.binding.manifest_digest
    assert set(life.EXTRA_SOURCES) <= set(payload["sources"])


@pytest.mark.parametrize("mode", ["helper-death", "coordinator-death"])
def test_actual_peer_death_discards_authority(anchor: Path, mode: str) -> None:
    result = run_fixture_demo(mode, anchor, mode=mode)
    assert "error" in result or result.get("peer_failure") is True
    registry = anchor / "attempts" / life.FixtureDomain(mode).domain_id
    assert not (registry / "release-once.json").exists()
    assert not (registry / "reviewer-approved.json").exists()
    assert (
        registry / ("failure.json" if mode == "helper-death" else "service-failure.json")
    ).exists()
    with pytest.raises(life.LifecycleError, match="exhausted"):
        life.reserve_fixture(life.FixtureDomain(mode), life.current_binding())


def test_partial_reservation_write_consumes_case_without_success(
    anchor: Path, monkeypatch: Any
) -> None:
    error = OSError("partial before durability")

    def partial(path: Path, *args: Any, **kwargs: Any) -> None:
        with path.open("xb") as stream:
            stream.write(b"{")
        raise error

    monkeypatch.setattr(study, "_exclusive_record", partial)
    with pytest.raises(OSError) as caught:
        life.reserve_fixture(life.FixtureDomain("partial"), life.current_binding())
    assert caught.value is error
    registry = anchor / "attempts" / life.FixtureDomain("partial").domain_id
    assert (registry / "attempt-reserved.json").read_bytes() == b"{"
    with pytest.raises(life.LifecycleError, match="exhausted"):
        life.reserve_fixture(life.FixtureDomain("partial"), life.current_binding())


def test_ack_error_survives_owned_shutdown_error(anchor: Path, monkeypatch: Any) -> None:
    import multiprocessing as mp
    import time

    reader, held_writer = mp.get_context("spawn").Pipe(duplex=False)
    error = life.LifecycleError("ack sentinel")
    original = life._stop_process

    def guard(*args: Any) -> None:
        raise error

    def stop(process: Any) -> None:
        original(process)
        raise OSError("secondary stop")

    monkeypatch.setattr(life, "_fixture_resources", guard)
    monkeypatch.setattr(life, "_stop_process", stop)
    try:
        with pytest.raises(life.LifecycleError) as caught:
            life._bounded_receive(reader, anchor, time.monotonic())
        assert caught.value is error
        assert any("Owned shutdown" in note for note in error.__notes__)
    finally:
        reader.close()
        held_writer.close()


def test_verification_error_survives_owned_stop_error(anchor: Path, monkeypatch: Any) -> None:
    session = life.reserve_fixture(life.FixtureDomain("verify-stop"), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    child = life.launch_fixture_child(session)
    completion = life.supervise_fixture_child(session, child)
    session.complete_development(completion)
    error = life.LifecycleError("verification sentinel")

    def failed(*args: Any) -> Any:
        raise error

    def stop(*args: Any) -> None:
        raise OSError("secondary stop")

    monkeypatch.setattr(life, "_launch_owned_child", lambda *args: child)
    monkeypatch.setattr(life, "_supervise_owned_child", failed)
    monkeypatch.setattr(life, "stop_fixture_child", stop)
    with pytest.raises(life.LifecycleError) as caught:
        life.verify_fixture_evidence(session, completion)
    assert caught.value is error
    assert session.state is life.State.ERROR
    assert any("Owned shutdown" in note for note in error.__notes__)


def test_raw_size_refuses_before_hash_stream(anchor: Path) -> None:
    raw = anchor / "fixture-payload.bin"
    raw.write_bytes(b"x" * 2051)
    with pytest.raises(life.LifecycleError, match="raw_size"):
        life._raw_snapshot(raw, anchor)


def test_copied_genuine_approval_cannot_release_validation_key(anchor: Path) -> None:
    result = run_fixture_demo("copied-release", anchor, mode="copy-release")
    assert result["detail"] == "token_issuer"
    registry = anchor / "attempts" / life.FixtureDomain("copied-release").domain_id
    assert (registry / "reviewer-approved.json").exists()
    assert not (registry / "release-once.json").exists()


def heartbeat_closed_fixture_writer(
    root: Path, binding: Any, completion: Any, heartbeat: Any
) -> None:
    import time

    heartbeat.close()
    time.sleep(3)
    completion.close()


def duplicate_ack_fixture_writer(root: Path, binding: Any, completion: Any, heartbeat: Any) -> None:
    class Proxy:
        def send_bytes(self, blob: bytes) -> None:
            completion.send_bytes(blob.replace(b'"schema":1', b'"schema":1,"schema":1'))

        def close(self) -> None:
            completion.close()

    life._fixture_job(root, binding, cast(Any, Proxy()), heartbeat, "write")


@pytest.mark.parametrize("writer", [heartbeat_closed_fixture_writer, duplicate_ack_fixture_writer])
def test_lost_heartbeat_or_noncanonical_ack_never_completes(
    anchor: Path, monkeypatch: Any, writer: Any
) -> None:
    session = life.reserve_fixture(life.FixtureDomain(writer.__name__), life.current_binding())
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", writer)
    child = life.launch_fixture_child(session)
    try:
        with pytest.raises(life.LifecycleError):
            life.supervise_fixture_child(session, child)
        assert session.state is life.State.ERROR
        assert not child.process.is_alive()
        assert not child.monitor.is_alive()
        assert not (session.registry / "development_complete.json").exists()
    finally:
        life.stop_fixture_child(child)


def test_helper_independently_rejects_rehashed_reservation_body(anchor: Path) -> None:
    result = run_fixture_demo("bad-reservation", anchor, mode="bad-reservation")
    assert "error" in result
    registry = anchor / "attempts" / life.FixtureDomain("bad-reservation").domain_id
    failure = life.read_record(registry / "service-failure.json", registry)
    assert failure["body"]["detail"] == "reservation_binding"
    assert not (registry / "key-sealed.json").exists()


def test_failure_uses_captured_registry_and_identifiers(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("captured-failure"), life.current_binding())
    original = session.registry
    attempt = session.attempt_id
    substitute = anchor / "substitute"
    substitute.mkdir()
    session.registry = substitute
    session.attempt_id = "mutated"
    with pytest.raises(life.LifecycleError):
        session.claim_development()
    assert not (substitute / "failure.json").exists()
    record = life.read_record(original / "failure.json", original)
    assert record["attempt_id"] == attempt
    assert record["state"] == "ERROR"


@pytest.mark.parametrize("fact", ["errors", "heartbeat"])
def test_owned_supervision_facts_are_not_public_mutable_lists(
    anchor: Path, monkeypatch: Any, fact: str
) -> None:
    session = life.reserve_fixture(
        life.FixtureDomain("private-fact-" + fact), life.current_binding()
    )
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)
    child = life.launch_fixture_child(session)
    try:
        if fact == "errors":
            with pytest.raises(AttributeError):
                cast(Any, child.errors).clear()
        else:
            with pytest.raises(TypeError):
                cast(Any, child.last_heartbeat)[0] = float("inf")
    finally:
        life.stop_fixture_child(child)


def test_public_handle_cannot_stop_owned_monitor(anchor: Path, monkeypatch: Any) -> None:
    session = life.reserve_fixture(
        life.FixtureDomain("private-monitor-stop"), life.current_binding()
    )
    session._advance(
        life.State.ATTEMPT_RESERVED, life.State.VALIDATION_KEY_SEALED, {"isolated_state_test": True}
    )
    session.claim_development()
    monkeypatch.setattr(life, "_fixture_writer", sleeping_fixture_writer)
    child = life.launch_fixture_child(session)
    try:
        with pytest.raises(AttributeError):
            cast(Any, child.stopped).set()
        assert child.monitor.is_alive()
    finally:
        life.stop_fixture_child(child)


def test_local_failure_revokes_already_approved_channel_authority(anchor: Path) -> None:
    result = run_fixture_demo("failed-release", anchor, mode="failed-release")
    assert "error" in result
    registry = anchor / "attempts" / life.FixtureDomain("failed-release").domain_id
    assert (registry / "reviewer-approved.json").exists()
    assert not (registry / "release-once.json").exists()
    failed = life.read_record(registry / "service-failure.json", registry)
    assert failed["state"] == "ERROR"
    assert failed["body"]["reason"] in {"LifecycleError", "OSError", "EOFError", "BrokenPipeError"}


def test_failure_persistence_error_still_closes_owned_authority_channel(anchor: Path) -> None:
    result = run_fixture_demo("failed-persist", anchor, mode="failed-persist-release")
    assert "error" in result
    registry = anchor / "attempts" / life.FixtureDomain("failed-persist").domain_id
    assert (registry / "reviewer-approved.json").exists()
    assert not (registry / "release-once.json").exists()
    assert not (registry / "failure.json").exists()
    assert (registry / "service-failure.json").exists()


def test_empty_unissued_session_object_refuses_without_masking(anchor: Path) -> None:
    forged = object.__new__(life.LiveSession)
    with pytest.raises(life.LifecycleError, match="session_issuer"):
        forged.claim_development()
    assert list(anchor.iterdir()) == []


def test_authority_close_failure_preserves_original_transition_error(anchor: Path) -> None:
    session = life.reserve_fixture(life.FixtureDomain("close-note"), life.current_binding())

    class FailedClose:
        def close(self) -> None:
            raise OSError("owned close error")

    session._coordinator_connection = cast(Any, FailedClose())
    with pytest.raises(life.LifecycleError, match="transition") as caught:
        session.claim_development()
    assert any("Authority shutdown" in note for note in caught.value.__notes__)
    assert session.state is life.State.ERROR


def test_malformed_client_bootstrap_terminalizes_and_closes_transferred_endpoint(
    anchor: Path,
) -> None:
    import multiprocessing as mp

    from scripts.research import signal_calendar_score_lifecycle_service as service

    session = life.reserve_fixture(life.FixtureDomain("client-bootstrap"), life.current_binding())
    owned, remote = mp.get_context("spawn").Pipe()
    try:
        with pytest.raises(life.LifecycleError):
            service.CoordinatorClient(
                session, owned, bytes([3]) * 32, {"helper": {"pid": True, "creation_time_ns": 1}}
            )
        assert session.state is life.State.ERROR
        assert owned.closed
        assert (session.registry / "failure.json").exists()
    finally:
        owned.close()
        remote.close()


@pytest.mark.parametrize("mode", ["write", "verify"])
def test_fixture_original_failure_survives_both_close_faults(
    anchor: Path, monkeypatch: Any, mode: str
) -> None:
    from scripts.research import signal_calendar_score_verify as verify

    original = RuntimeError("fixture original")
    closed: list[str] = []

    class Endpoint:
        def __init__(self, name: str) -> None:
            self.name = name

        def send_bytes(self, value: bytes) -> None:
            pass

        def close(self) -> None:
            closed.append(self.name)
            raise OSError("close " + self.name)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise original

    monkeypatch.setattr(verify, "write_fixture", fail)
    monkeypatch.setattr(verify, "verify_fixture", fail)
    with pytest.raises(RuntimeError) as caught:
        life._fixture_job(
            anchor,
            life.current_binding(),
            cast(Any, Endpoint("completion")),
            cast(Any, Endpoint("heartbeat")),
            mode,
        )
    assert caught.value is original
    assert closed == ["completion", "heartbeat"]
    assert len(original.__notes__) == 2


def test_service_original_failure_retained_and_all_endpoints_closed(
    anchor: Path, monkeypatch: Any
) -> None:
    from scripts.research import signal_calendar_score_lifecycle_service as service

    original = RuntimeError("bootstrap original")
    closed: list[str] = []
    captured: list[BaseException] = []

    class Endpoint:
        def __init__(self, name: str) -> None:
            self.name = name

        def recv_bytes(self, maximum: int) -> bytes:
            raise original

        def close(self) -> None:
            closed.append(self.name)
            if self.name != "bootstrap":
                raise OSError("close " + self.name)

    monkeypatch.setattr(
        service, "_service_failure", lambda root, reservation, error: captured.append(error)
    )
    service.run_fixture_reviewer(
        cast(Any, Endpoint("coordinator")),
        cast(Any, Endpoint("approval")),
        cast(Any, Endpoint("bootstrap")),
    )
    assert captured == [original]
    assert closed == ["coordinator", "approval", "bootstrap"]
    assert len(original.__notes__) == 2


def test_post_unlink_completion_failure_records_absence_and_refuses_retry(anchor: Path) -> None:
    result = run_fixture_demo("cleanup-post-unlink", anchor, mode="cleanup-after-unlink")
    assert result == {
        "error": "OSError",
        "detail": "completion receipt denied",
        "state": "ERROR",
        "retry_terminal": True,
    }
    registry = anchor / "attempts" / life.FixtureDomain("cleanup-post-unlink").domain_id
    assert not (registry / "validation-evidence/fixture-payload.bin").exists()
    assert (registry / "evidence/fixture-payload.bin").exists()
    assert (registry / "cleanup-validation-intent.json").exists()
    assert not (registry / "cleanup-validation-complete.json").exists()
    error = life.read_record(registry / "cleanup-validation-error.json", registry)
    assert error["state"] == "CLEANUP_ERROR"
    assert error["body"]["raw_status"] == "absent"
    assert (registry / "failure.json").exists()


@pytest.mark.parametrize(
    "status,ctime,running,expected",
    [
        (psutil.STATUS_ZOMBIE, 1.0, True, False),
        (psutil.STATUS_DEAD, 1.0, True, False),
        (psutil.STATUS_RUNNING, 1.0, True, True),
        (psutil.STATUS_SLEEPING, 1.0, True, True),
        (psutil.STATUS_RUNNING, 2.0, True, False),
        (psutil.STATUS_RUNNING, 1.0, False, False),
    ],
)
def test_peer_identity_rejects_unreaped_dead_process(
    monkeypatch: Any, status: str, ctime: float, running: bool, expected: bool
) -> None:
    class Process:
        def create_time(self) -> float:
            return ctime

        def is_running(self) -> bool:
            return running

        def status(self) -> str:
            return status

    monkeypatch.setattr(psutil, "Process", lambda pid: Process())
    assert life.ProcessIdentity(123, 1_000_000_000).alive() is expected


@pytest.mark.parametrize("error", [psutil.NoSuchProcess(123), psutil.AccessDenied(123)])
def test_peer_identity_status_failure_is_not_alive(monkeypatch: Any, error: Exception) -> None:
    class Process:
        def create_time(self) -> float:
            return 1.0

        def is_running(self) -> bool:
            return True

        def status(self) -> str:
            raise error

    monkeypatch.setattr(psutil, "Process", lambda pid: Process())
    assert life.ProcessIdentity(123, 1_000_000_000).alive() is False
