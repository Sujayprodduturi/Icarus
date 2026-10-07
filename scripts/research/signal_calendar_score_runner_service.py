"""Reviewer-owned full-runner sealing service; authenticated bytes only."""

from __future__ import annotations

import hashlib
import multiprocessing as mp
import os
import secrets
import stat
import threading
import time
from dataclasses import asdict
from multiprocessing.connection import _ConnectionBase as Connection
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_lifecycle_service as channels
from scripts.research import signal_calendar_score_phase as phase
from scripts.research import signal_calendar_score_runner as runner
from scripts.research import signal_calendar_score_study as io


def _new_study_key() -> bytes:
    return secrets.token_bytes(32)


def _identity(value: Any) -> life.ProcessIdentity:
    if not life.ProcessIdentity.valid_fields(value):
        raise runner.RunnerError("peer_identity")
    return life.ProcessIdentity(**value)


def _evidence_check(
    registry: Path,
    name: str,
    binding: phase.SourceBinding,
    guard: Any = None,
    *,
    _scan_payload: bool = True,
) -> dict[str, Any]:
    if name not in io.PHASE_REPLICATES:
        raise runner.RunnerError("phase")
    root = registry / name
    claim = phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
    plan, _value = phase.validate_claim(root, claim, binding)
    terminal_blob = phase._read_bytes(root / "phase-terminal.json", root, io.MAX_RECORD)
    terminal = phase._decode(terminal_blob)
    expected_state = (
        "COMPLETE" if plan.namespace == io.EXPERIMENT_NAMESPACE else "TEST_PHASE_COMPLETE"
    )
    if terminal.get("state") != expected_state:
        raise runner.RunnerError("completion")
    runner._validate_completion(root, claim, terminal)
    receipt_digests: dict[str, str] = {}
    for role in ("primary", "reviewer"):
        blob = phase._read_bytes(root / f"verified-{role}.json", root, io.MAX_RECORD)
        record = phase._decode(blob)
        expected = {
            "utc": record["utc"],
            "schema": 1,
            "state": "VERIFIED" if plan.namespace == io.EXPERIMENT_NAMESPACE else "TEST_VERIFIED",
            "role": role,
            "binding": terminal["binding"],
            "decision": terminal["decision"],
            "counts": terminal["counts"],
            "payload_digest": terminal["payload_digest"],
            "index_digest": terminal["index_digest"],
            "report_digest": terminal["report_digest"],
            "terminal_digest": phase._hash(terminal_blob),
            "summary_digest": phase._hash(
                io.canonical_json(phase._read_record(root, "phase-report.json")["summary"])
            ),
            "verifier": record["verifier"],
            "completion": record["completion"],
        }
        if blob != io.canonical_json(expected):
            raise runner.RunnerError("receipt_binding")
        proof = record["completion"]
        if (
            type(proof) is not dict
            or set(proof) != set(runner._StageProof.__dataclass_fields__)
            or (
                proof["kind"] != "verifier"
                or proof["role"] != role
                or type(proof["exit_code"]) is not int
                or proof["exit_code"] != 0
                or proof["durable_ack"] is not True
                or proof["monitor_joined"] is not True
                or io.canonical_json(proof["child"]) != io.canonical_json(record["verifier"])
            )
        ):
            raise runner.RunnerError("receipt_completion")
        receipt_digests[role] = phase._hash(blob)
    # The helper checks the exact saved evidence set. It does not repeat the math
    # which the two separately owned verifier processes have already completed.
    report_blob = phase._read_bytes(root / "phase-report.json", root, io.MAX_RECORD)
    report = phase._decode(report_blob)
    if phase._hash(report_blob) != terminal["report_digest"] or (
        io.canonical_json(report["binding"]) != io.canonical_json(terminal["binding"])
        or io.canonical_json(report["counts"]) != io.canonical_json(terminal["counts"])
        or report["decision"] != terminal["decision"]
        or (
            terminal["counts"]["paths"],
            terminal["counts"]["metrics"],
            terminal["counts"]["payload_bytes"],
        )
        != (plan.paths, plan.metrics, plan.payload_bytes)
    ):
        raise runner.RunnerError("report_binding")
    if _scan_payload and (
        _hash_checked(
            root, "phase-payload.bin", plan.payload_bytes, plan.payload_bytes, binding, guard
        )
        != terminal["payload_digest"]
        or (
            _hash_checked(
                root,
                "phase-index.jsonl",
                plan.paths * plan.metadata_cap + io.MAX_RECORD,
                None,
                binding,
                guard,
            )
            != terminal["index_digest"]
        )
    ):
        raise runner.RunnerError("artifact_hash")
    phase._storage(root, plan, plan.payload_bytes, (root / "phase-index.jsonl").stat().st_size)
    return {
        "phase": name,
        "binding": terminal["binding"],
        "counts": terminal["counts"],
        "decision": terminal["decision"],
        "payload_digest": terminal["payload_digest"],
        "index_digest": terminal["index_digest"],
        "report_digest": terminal["report_digest"],
        "terminal_digest": phase._hash(terminal_blob),
        "primary_receipt_digest": receipt_digests["primary"],
        "reviewer_receipt_digest": receipt_digests["reviewer"],
    }


def run_reviewer_service(
    request_connection: Connection | None,
    approval_connection: Connection | None,
    bootstrap_connection: Connection | None,
) -> None:
    if request_connection is None or approval_connection is None or bootstrap_connection is None:
        raise runner.RunnerError("unowned_service")
    stopped = threading.Event()
    failure: BaseException | None = None
    registry: Path | None = None
    reservation: bytes | None = None
    started = time.perf_counter()
    parent = mp.parent_process()
    if parent is None or parent.pid is None:
        raise runner.RunnerError("service_parent")
    parent_identity = life.ProcessIdentity.capture(int(parent.pid))

    def bootstrap_guard() -> None:
        if time.perf_counter() - started > 600.0:
            raise runner.RunnerError("bootstrap_deadline")

    check: list[Any] = [bootstrap_guard]
    receive_deadline: list[float | None] = [None]

    def watchdog() -> None:
        while not stopped.wait(0.25):
            try:
                if (
                    not parent_identity.alive()
                    or time.perf_counter() - started > runner.SESSION_LIMIT
                ):
                    raise runner.RunnerError("service_lifetime")
                check[0]()
            except BaseException as error:
                if registry is not None:
                    try:
                        phase._record(
                            registry,
                            "service-failure.json",
                            {
                                "schema": 1,
                                "state": "ERROR",
                                "error": str(error),
                                "source_binding": asdict(binding),
                            },
                        )
                    except BaseException:
                        pass
                os._exit(74)

    monitor = threading.Thread(target=watchdog, daemon=False)
    monitor.start()
    key: bytes | None = None
    try:
        blob = bootstrap_connection.recv_bytes(io.MAX_RECORD)
        boot = phase._decode(blob)
        required = {
            "utc",
            "registry",
            "coordinator",
            "reviewer",
            "helper",
            "source_binding",
            "source_review_digest",
            "session_id",
            "challenge",
            "coordinator_secret",
            "reviewer_secret",
            "namespace",
        }
        if set(boot) != required:
            raise runner.RunnerError("service_bootstrap")
        binding = phase.current_binding()
        helper = life.ProcessIdentity.current()
        coordinator, reviewer = _identity(boot["coordinator"]), _identity(boot["reviewer"])
        if (
            reviewer != parent_identity
            or _identity(boot["helper"]) != helper
            or (
                io.canonical_json(boot["source_binding"]) != io.canonical_json(asdict(binding))
                or boot["source_review_digest"] != binding.manifest_digest
            )
        ):
            raise runner.RunnerError("service_owner")
        requested_registry = Path(boot["registry"])
        actual = boot["namespace"] == io.EXPERIMENT_NAMESPACE
        if boot["namespace"] not in (io.TEST_NAMESPACE, io.EXPERIMENT_NAMESPACE):
            raise runner.RunnerError("service_namespace")
        if actual:
            registration = runner._read_actual_registration(requested_registry, binding)
            expected_peers = {
                "coordinator": asdict(coordinator),
                "reviewer": asdict(reviewer),
                "helper": asdict(helper),
            }
            if io.canonical_json({k: registration[k] for k in expected_peers}) != io.canonical_json(
                expected_peers
            ):
                raise runner.RunnerError("service_registration")
        else:
            io._guard_path(requested_registry, phase.TEST_ANCHOR / "attempts", existing=True)
            if requested_registry.parent != phase.TEST_ANCHOR / "attempts":
                raise runner.RunnerError("service_anchor")
        registry = requested_registry
        reservation = phase._read_bytes(registry / "attempt-reserved.json", registry, io.MAX_RECORD)
        reserved = phase._decode(reservation)
        preflight_deadline = reserved.get("preflight_deadline")
        runner._remaining_preflight(preflight_deadline, runner.CONTROL_ALLOWANCE)
        if (
            reserved["namespace"] != boot["namespace"]
            or reserved["session_id"] != boot["session_id"]
            or (
                io.canonical_json(reserved["owner"]) != io.canonical_json(asdict(coordinator))
                or io.canonical_json(reserved["source_binding"])
                != io.canonical_json(asdict(binding))
            )
        ):
            raise runner.RunnerError("service_reservation")
        secret = bytes.fromhex(boot["coordinator_secret"])
        review_secret = bytes.fromhex(boot["reviewer_secret"])
        if len(secret) != 32 or len(review_secret) != 32 or secret == review_secret:
            raise runner.RunnerError("service_secret")
        coordinate = channels.FrameChannel(
            request_connection,
            secret,
            "coordinator",
            boot["session_id"],
            boot["challenge"],
            helper,
            coordinator,
            binding,
        )
        review = channels.FrameChannel(
            approval_connection,
            review_secret,
            "reviewer",
            boot["session_id"],
            boot["challenge"],
            helper,
            reviewer,
            binding,
        )

        def guard() -> None:
            if receive_deadline[0] is not None and time.perf_counter() > receive_deadline[0]:
                raise runner.RunnerError("service_control_deadline")
            if (
                not coordinator.alive()
                or not reviewer.alive()
                or phase.current_binding() != binding
            ):
                raise runner.RunnerError("service_lifetime")
            if io._guard_path(registry / "attempt-failure.json", registry).exists():
                raise runner.RunnerError("coordinator_error")
            if (
                phase._read_bytes(registry / "attempt-reserved.json", registry, io.MAX_RECORD)
                != reservation
            ):
                raise runner.RunnerError("reservation_drift")
            if (
                psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
                or psutil.disk_usage(str(registry)).free < io.FREE_RESERVE
            ):
                raise runner.RunnerError("service_resources")
            anchor = reserved["session_started_monotonic"] if actual else started
            runner._remaining_preflight(preflight_deadline, runner.CONTROL_ALLOWANCE)
            if type(anchor) is not float or not 0 <= time.perf_counter() - anchor <= (
                runner.SESSION_LIMIT
                if actual
                else (runner.CONTROL_ALLOWANCE if preflight_deadline is not None else 90.0)
            ):
                raise runner.RunnerError("test_service_deadline")

        check[0] = guard
        guard()
        key = _new_study_key() if actual else bytes([2]) * 32
        if type(key) is not bytes or len(key) != 32:
            raise runner.RunnerError("study_key")
        commitment = hashlib.sha256(key).hexdigest()
        sealed = released = False
        approved: dict[str, Any] | None = None
        validation_approved: dict[str, Any] | None = None
        while True:
            guard()
            if approval_connection.poll(0):
                receive_deadline[0] = time.perf_counter() + runner.CONTROL_ALLOWANCE
                request = review.receive()
                receive_deadline[0] = None
                if set(request) != {
                    "action",
                    "evidence",
                    "source_review_digest",
                    "control_decision",
                } or (
                    request["action"] not in ("approve-development", "approve-validation")
                    or request["source_review_digest"] != binding.manifest_digest
                    or not sealed
                    or request["control_decision"]
                    not in (("PASS", "FAILED") if actual else ("TEST_PASS", "TEST_FAILED"))
                ):
                    raise runner.RunnerError("reviewer_action")
                name = request["action"].removeprefix("approve-")
                if (name == "development" and (approved is not None or released)) or (
                    name == "validation" and (validation_approved is not None or not released)
                ):
                    raise runner.RunnerError("reviewer_order")
                evidence = _evidence_check(registry, name, binding, guard)
                if actual and request["control_decision"] != evidence["decision"]:
                    raise runner.RunnerError("reviewer_decision")
                for role, peer in (("primary", coordinator), ("reviewer", reviewer)):
                    receipt = phase._read_record(registry / name, f"verified-{role}.json")
                    if io.canonical_json(receipt["completion"]["owner"]) != io.canonical_json(
                        asdict(peer)
                    ):
                        raise runner.RunnerError("reviewer_owner")
                if io.canonical_json(request["evidence"]) != io.canonical_json(evidence):
                    raise runner.RunnerError("reviewer_binding")
                body = {
                    **request,
                    "reviewer": asdict(reviewer),
                    "helper": asdict(helper),
                    "scope": "ARTIFICIAL_RESEARCH_ONLY" if actual else "UNAVAILABLE_TEST_ONLY",
                    "state": "REVIEW_APPROVED",
                    "schema": 1,
                }
                digest = phase._record(registry, name + "-reviewer-approved.json", body)
                result = {**body, "approval_digest": digest}
                if name == "development":
                    approved = result
                else:
                    validation_approved = result
                review.send({"state": "APPROVED", "approval_digest": digest})
            if request_connection.poll(0.1):
                receive_deadline[0] = time.perf_counter() + runner.CONTROL_ALLOWANCE
                request = coordinate.receive()
                receive_deadline[0] = None
                action = request.get("action")
                if action == "seal" and set(request) == {"action"} and not sealed:
                    phase._record(
                        registry,
                        "validation-sealed.json",
                        {
                            "schema": 1,
                            "state": "VALIDATION_KEY_SEALED",
                            "namespace": boot["namespace"],
                            "scope": "ARTIFICIAL_RESEARCH_ONLY"
                            if actual
                            else "UNAVAILABLE_TEST_ONLY",
                            "commitment": commitment,
                            "session_id": boot["session_id"],
                            "source_binding": asdict(binding),
                            "helper": asdict(helper),
                        },
                    )
                    sealed = True
                    coordinate.send({"state": "SEALED", "commitment": commitment})
                elif action == "status" and set(request) == {"action", "phase"}:
                    selected = (
                        approved if request["phase"] == "development" else validation_approved
                    )
                    coordinate.send(
                        {"state": "APPROVED" if selected else "PENDING", "approval": selected}
                    )
                elif action == "release" and set(request) == {
                    "action",
                    "evidence",
                    "approval_digest",
                }:
                    if (
                        not sealed
                        or released
                        or approved is None
                        or approved["control_decision"] != ("PASS" if actual else "TEST_PASS")
                    ):
                        raise runner.RunnerError("release_once")
                    current = _evidence_check(registry, "development", binding, guard)
                    if io.canonical_json(request["evidence"]) != io.canonical_json(current) or (
                        request["approval_digest"] != approved["approval_digest"]
                        or io.canonical_json(current) != io.canonical_json(approved["evidence"])
                    ):
                        raise runner.RunnerError("release_binding")
                    phase._record(
                        registry,
                        "validation-released.json",
                        {
                            "schema": 1,
                            "state": "VALIDATION_AUTHORIZED",
                            "scope": "ARTIFICIAL_RESEARCH_ONLY"
                            if actual
                            else "UNAVAILABLE_TEST_ONLY",
                            "session_id": boot["session_id"],
                            "source_binding": asdict(binding),
                            "evidence": current,
                            "approval_digest": approved["approval_digest"],
                            "commitment": commitment,
                            "helper": asdict(helper),
                        },
                    )
                    if key is None:
                        raise runner.RunnerError("release_once")
                    released = True
                    coordinate.send(
                        {
                            "state": "VALIDATION_AUTHORIZED",
                            "key": key.hex(),
                            "commitment": commitment,
                        }
                    )
                    key = None
                elif action == "finish" and set(request) == {"action"}:
                    if (
                        approved is None
                        or (released and validation_approved is None)
                        or (
                            not released
                            and approved["control_decision"]
                            != ("FAILED" if actual else "TEST_FAILED")
                        )
                    ):
                        raise runner.RunnerError("finish_order")
                    coordinate.send({"state": "CLOSED"})
                    return
                else:
                    raise runner.RunnerError("coordinator_action")
    except BaseException as error:
        failure = error
        if registry is not None:
            try:
                phase._record(
                    registry,
                    "service-failure.json",
                    {
                        "schema": 1,
                        "state": "ERROR",
                        "error": str(error),
                        "source_binding": asdict(binding),
                    },
                )
            except BaseException as secondary:
                error.add_note(f"Service evidence: {type(secondary).__name__}")
        raise
    finally:
        key = None
        life._shutdown(
            [
                stopped.set,
                request_connection.close,
                approval_connection.close,
                bootstrap_connection.close,
                lambda: life._join_thread(monitor),
            ],
            failure,
        )


def _hash_checked(
    root: Path,
    name: str,
    cap: int,
    exact_size: int | None,
    binding: phase.SourceBinding,
    guard: Any = None,
) -> str:
    path = io._guard_path(root / name, root, existing=True)
    before = path.stat()
    if (
        not stat.S_ISREG(before.st_mode)
        or before.st_size > cap
        or (exact_size is not None and before.st_size != exact_size)
    ):
        raise runner.RunnerError("artifact_size")

    def check() -> None:
        if (
            phase.current_binding() != binding
            or psutil.disk_usage(str(root)).free < io.FREE_RESERVE
            or (psutil.Process().memory_info().rss > io.PARENT_RSS_CAP)
        ):
            raise runner.RunnerError("artifact_resources")
        if guard is not None:
            guard()

    check()
    digest, total, sampled = hashlib.sha256(), 0, time.perf_counter()
    with path.open("rb") as stream:
        if phase._identity(os.fstat(stream.fileno())) != phase._identity(before):
            raise runner.RunnerError("artifact_drift")
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > before.st_size:
                raise runner.RunnerError("artifact_growth")
            digest.update(chunk)
            if time.perf_counter() - sampled >= 0.25:
                check()
                sampled = time.perf_counter()
    if total != before.st_size or phase._identity(path.stat()) != phase._identity(before):
        raise runner.RunnerError("artifact_drift")
    check()
    return digest.hexdigest()
