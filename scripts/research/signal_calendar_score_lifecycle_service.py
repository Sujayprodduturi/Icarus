"""Separate fixed-test reviewer service; no production seed capability."""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import asdict
from multiprocessing.connection import _ConnectionBase as Connection
from typing import Any

from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_study as io


class FrameChannel:
    """Authenticated canonical bytes, never an untrusted pickle."""

    def __init__(
        self,
        connection: Connection,
        secret: bytes,
        role: str,
        session_id: str,
        challenge: str,
        local: life.ProcessIdentity,
        remote: life.ProcessIdentity,
        binding: life.SourceBinding,
    ) -> None:
        if (
            type(secret) is not bytes
            or len(secret) != 32
            or role not in ("coordinator", "reviewer")
            or len(session_id) != 64
            or len(challenge) != 64
            or type(local) is not life.ProcessIdentity
            or type(remote) is not life.ProcessIdentity
            or type(binding) is not life.SourceBinding
        ):
            raise life.LifecycleError("channel_schema")
        self.connection, self._secret, self.role = connection, secret, role
        self.session_id, self.challenge, self.local, self.remote = (
            session_id,
            challenge,
            local,
            remote,
        )
        self.binding = binding
        self._sent = self._received = 0

    def send(self, body: dict[str, object]) -> None:
        value: dict[str, object] = {
            "schema": 1,
            "role": self.role,
            "sequence": self._sent,
            "session_id": self.session_id,
            "challenge": self.challenge,
            "sender": asdict(self.local),
            "receiver": asdict(self.remote),
            "source_binding": asdict(self.binding),
            "body": body,
        }
        value["mac"] = hmac.new(self._secret, io.canonical_json(value), hashlib.sha256).hexdigest()
        blob = io.canonical_json(value)
        if len(blob) > life.MAX_RECORD:
            raise life.LifecycleError("frame_cap")
        self.connection.send_bytes(blob)
        self._sent += 1

    def receive(self) -> dict[str, Any]:
        try:
            blob = self.connection.recv_bytes(life.MAX_RECORD)
            value = json.loads(blob)
            if type(value) is not dict or io.canonical_json(value) != blob:
                raise life.LifecycleError("authentication")
            mac = value.pop("mac", None)
            expected = hmac.new(self._secret, io.canonical_json(value), hashlib.sha256).hexdigest()
            if type(mac) is not str or not hmac.compare_digest(mac, expected):
                raise life.LifecycleError("authentication")
            head = {
                "schema": 1,
                "role": self.role,
                "sequence": self._received,
                "session_id": self.session_id,
                "challenge": self.challenge,
                "sender": asdict(self.remote),
                "receiver": asdict(self.local),
                "source_binding": asdict(self.binding),
            }
            if (
                set(value) != set(head) | {"body"}
                or type(value["body"]) is not dict
                or io.canonical_json({k: value[k] for k in head}) != io.canonical_json(head)
            ):
                raise life.LifecycleError("authentication")
            self._received += 1
            return value["body"]
        except (OSError, EOFError, ValueError, TypeError) as error:
            raise life.LifecycleError("authentication") from error


def _parse_identity(value: Any) -> life.ProcessIdentity:
    if (
        type(value) is not dict
        or set(value) != {"pid", "creation_time_ns"}
        or any(type(v) is not int or v <= 0 for v in value.values())
    ):
        raise life.LifecycleError("peer_identity")
    return life.ProcessIdentity(**value)


def _parse_binding(value: Any) -> life.SourceBinding:
    if type(value) is not dict or set(value) != set(life.SourceBinding.__dataclass_fields__):
        raise life.LifecycleError("source_binding")
    expected = life.current_binding()
    if io.canonical_json(value) != io.canonical_json(asdict(expected)):
        raise life.LifecycleError("source_drift")
    return expected


def _receipt(root: Any, name: str, evidence: life.EvidenceBinding) -> str:
    import math

    from scripts.research import signal_calendar_score_verify as verify

    value = verify._load(root, name)
    expected_keys = {
        "schema",
        "scope",
        "record_role",
        "publication_name",
        "binding",
        "paths",
        "metrics",
        "words",
        "payload_bytes",
        "seconds",
    }
    if (
        set(value) != expected_keys
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["scope"] != verify.SCOPE
        or value["record_role"] != "INERT_UNTIL_EXCLUSIVE_PUBLICATION"
        or value["publication_name"] != name
        or any(type(value[k]) is not int for k in ("paths", "metrics", "words", "payload_bytes"))
        or (value["paths"], value["metrics"], value["words"], value["payload_bytes"])
        != (1, 3, 12300, 2050)
        or type(value["seconds"]) is not float
        or not math.isfinite(value["seconds"])
        or not 0 <= value["seconds"] <= io.load_operational_resources().effective_verifier_seconds
    ):
        raise life.LifecycleError("verification_receipt")
    resources = io.load_operational_resources()
    claim_digest = io._hash_file(life._regular(root / "fixture-claim.json", root))
    binding = {
        "resource_contract_id": resources.resource_contract_id,
        "resource_contract_sha256": resources.resource_contract_sha256,
        "protocol_digest": io.PROTOCOL_SHA256,
        "source_manifest_digest": verify.current_manifest()[0],
        "attempt_id": "deterministic_fixture",
        "session_id": claim_digest,
        "phase": "test_fixture",
        "seed_commitment": life._digest(bytes(32)),
        "payload_digest": evidence.payload_digest,
        "index_digest": evidence.index_digest,
        "results_digest": evidence.index_digest,
        "terminal_digest": evidence.terminal_digest,
    }
    if io.canonical_json(value["binding"]) != io.canonical_json(binding):
        raise life.LifecycleError("verification_binding")
    return io._hash_file(life._regular(root / name, root))


def _service_record(
    registry: Any,
    reservation: dict[str, Any],
    name: str,
    state: str,
    body: dict[str, object],
    check: Any,
) -> str:
    import os
    from datetime import UTC, datetime

    value = {
        **reservation,
        "state": state,
        "seed_commitment": life._digest(bytes([2]) * 32),
        "utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "body": body,
    }
    digest = life._digest(io.canonical_json(value))
    candidate = registry / (name + ".pending")
    io._exclusive_record(candidate, {**value, "record_digest": digest}, root=registry)
    actual = life.read_record(candidate, registry)
    if io.canonical_json(actual) != io.canonical_json(value):
        raise life.LifecycleError("candidate_drift")
    check()
    destination = io._guard_path(registry / name, registry)
    full_digest = life._digest(io.canonical_json({**value, "record_digest": digest}))
    os.link(candidate, destination, follow_symlinks=False)
    return full_digest


def run_fixture_reviewer(
    coordinator_connection: Connection,
    approval_connection: Connection,
    bootstrap_connection: Connection,
) -> None:
    import time
    from pathlib import Path

    registry = None
    reservation = None
    key: bytes | None = None
    import os
    import threading

    import psutil  # type: ignore[import-untyped]

    creator = life.ProcessIdentity(
        os.getppid(), round(psutil.Process(os.getppid()).create_time() * 1_000_000_000)
    )
    entered = time.monotonic()
    stopped = threading.Event()
    watchdog_check: list[Any] = [None]

    def watchdog() -> None:
        try:
            while not stopped.wait(0.1):
                if not creator.alive() or time.monotonic() - entered > life.FIXTURE_TIMEOUT:
                    raise life.LifecycleError("service_watchdog")
                if watchdog_check[0] is not None:
                    watchdog_check[0]()
        except BaseException as error:
            _service_failure(registry, reservation, error)
            os._exit(1)

    guard = threading.Thread(target=watchdog, daemon=False)
    failure: BaseException | None = None
    try:
        guard.start()
        blob = bootstrap_connection.recv_bytes(4096)
        boot = json.loads(blob)
        fields = {
            "registry",
            "owner",
            "session_id",
            "attempt_id",
            "domain_id",
            "source_binding",
            "case_id",
            "anchor",
            "challenge",
            "coordinator_secret",
            "reviewer_secret",
            "reviewer",
            "helper",
        }
        if type(boot) is not dict or set(boot) != fields or io.canonical_json(boot) != blob:
            raise life.LifecycleError("bootstrap")
        coordinator = _parse_identity(boot["owner"])
        reviewer = _parse_identity(boot["reviewer"])
        helper = _parse_identity(boot["helper"])
        if (
            helper != life.ProcessIdentity.current()
            or coordinator == reviewer
            or reviewer != creator
        ):
            raise life.LifecycleError("peer_identity")
        binding = _parse_binding(boot["source_binding"])
        domain = life.FixtureDomain(boot["case_id"])
        registry = Path(boot["registry"])
        anchor = Path(boot["anchor"])
        if anchor != life._FIXTURE_ANCHOR or registry != anchor / "attempts" / domain.domain_id:
            raise life.LifecycleError("registry_identity")
        io._guard_path(registry, anchor, existing=True)
        reservation = life.read_record(registry / "attempt-reserved.json", registry)
        if (
            reservation["state"] != "ATTEMPT_RESERVED"
            or reservation["seed_commitment"] is not None
            or io.canonical_json(reservation["source_binding"])
            != io.canonical_json(asdict(binding))
            or io.canonical_json(reservation["owner"]) != io.canonical_json(asdict(coordinator))
            or any(reservation[k] != boot[k] for k in ("attempt_id", "session_id", "domain_id"))
            or io.canonical_json(reservation["body"])
            != io.canonical_json(
                {
                    "future_replicates": dict(io.PHASE_REPLICATES),
                    "future_worker_seconds": [21600, 43200],
                    "resources": io.load_operational_resources().binding(),
                    "extended_manifest": life.extended_manifest().payload,
                }
            )
        ):
            raise life.LifecycleError("reservation_binding")
        if io._guard_path(registry / "failure.json", registry).exists():
            raise life.LifecycleError("coordinator_error")
        coord_secret = bytes.fromhex(boot["coordinator_secret"])
        review_secret = bytes.fromhex(boot["reviewer_secret"])
        if len(coord_secret) != 32 or len(review_secret) != 32 or coord_secret == review_secret:
            raise life.LifecycleError("authentication")
        coordinate = FrameChannel(
            coordinator_connection,
            coord_secret,
            "coordinator",
            boot["session_id"],
            boot["challenge"],
            helper,
            coordinator,
            binding,
        )
        review = FrameChannel(
            approval_connection,
            review_secret,
            "reviewer",
            boot["session_id"],
            boot["challenge"],
            helper,
            reviewer,
            binding,
        )
        bootstrap_connection.close()
        key = bytes([2]) * 32
        commitment = life._digest(key)
        approved: dict[str, Any] | None = None
        validation_approved: dict[str, Any] | None = None
        sealed = released = False
        started = time.monotonic()

        def check() -> None:
            if io._guard_path(registry / "failure.json", registry).exists():
                raise life.LifecycleError("coordinator_error")
            if not coordinator.alive() or not reviewer.alive():
                raise life.LifecycleError("peer_dead")
            if life.current_binding() != binding:
                raise life.LifecycleError("source_drift")
            life._fixture_resources(registry, started, helper.pid, time.monotonic())
            current = life.read_record(registry / "attempt-reserved.json", registry)
            if io.canonical_json(current) != io.canonical_json(reservation):
                raise life.LifecycleError("reservation_drift")

        watchdog_check[0] = check

        def evidence_checks(validation: bool = False) -> tuple[life.EvidenceBinding, str, str]:
            evidence_root = registry / ("validation-evidence" if validation else "evidence")
            prefix = "validation" if validation else "development"
            evidence, _ = life._artifact_fields(
                evidence_root,
                boot["attempt_id"],
                boot["session_id"],
                boot["domain_id"],
                phase="validation_fixture" if validation else "test_fixture",
            )
            complete = life.read_record(registry / (prefix + "_complete.json"), registry)
            verified = life.read_record(registry / (prefix + "_verified.json"), registry)
            for record, state in (
                (complete, prefix.upper() + "_COMPLETE"),
                (verified, prefix.upper() + "_VERIFIED"),
            ):
                if record["state"] != state or any(
                    io.canonical_json(record[k]) != io.canonical_json(reservation[k])
                    for k in ("attempt_id", "session_id", "domain_id", "owner", "source_binding")
                ):
                    raise life.LifecycleError("evidence_binding")
            proof = complete["body"]
            if set(proof) != set(life.CompletionProof.__dataclass_fields__) or (
                io.canonical_json(proof["evidence"]) != io.canonical_json(asdict(evidence))
                or type(proof["exit_code"]) is not int
                or proof["exit_code"] != 0
                or any(
                    type(proof[k]) is not int
                    for k in ("paths", "metrics", "words", "payload_bytes")
                )
                or (proof["paths"], proof["metrics"], proof["words"], proof["payload_bytes"])
                != (1, 3, 12300, 2050)
            ):
                raise life.LifecycleError("completion_proof")
            _parse_identity(proof["child"])
            primary = _receipt(evidence_root, "verified-primary.json", evidence)
            independent = _receipt(evidence_root, "verified-reviewer.json", evidence)
            if io.canonical_json(verified["body"]) != io.canonical_json(
                {"evidence": asdict(evidence), "receipt_digest": primary}
            ):
                raise life.LifecycleError("primary_binding")
            return evidence, primary, independent

        while True:
            check()
            if approval_connection.poll(0):
                request = review.receive()
                validation = request.get("action") == "approve-validation"
                if set(request) != {
                    "action",
                    "evidence",
                    "primary_receipt_digest",
                    "independent_receipt_digest",
                    "decision",
                    "source_review_digest",
                } or (
                    request["action"] not in ("approve", "approve-validation")
                    or (validation_approved is not None if validation else approved is not None)
                    or not sealed
                    or (not released if validation else released)
                    or request["source_review_digest"] != binding.manifest_digest
                ):
                    raise life.LifecycleError("reviewer_action")
                evidence, primary, independent = evidence_checks(validation)
                expected_check = {
                    "action": "approve-validation" if validation else "approve",
                    "evidence": asdict(evidence),
                    "primary_receipt_digest": primary,
                    "independent_receipt_digest": independent,
                    "decision": "FIXTURE_ACCEPTED",
                    "source_review_digest": binding.manifest_digest,
                }
                if io.canonical_json(request) != io.canonical_json(expected_check):
                    raise life.LifecycleError("reviewer_binding")
                body: dict[str, object] = {
                    "evidence": asdict(evidence),
                    "primary_receipt_digest": primary,
                    "independent_receipt_digest": independent,
                    "source_review_digest": binding.manifest_digest,
                    "reviewer": asdict(reviewer),
                    "helper": asdict(helper),
                    "decision": "FIXTURE_ACCEPTED",
                }
                digest = _service_record(
                    registry,
                    reservation,
                    "validation-reviewer-approved.json" if validation else "reviewer-approved.json",
                    "REVIEW_APPROVED",
                    body,
                    check,
                )
                if validation:
                    validation_approved = {**body, "approval_digest": digest}
                else:
                    approved = {**body, "approval_digest": digest}
                review.send({"state": "APPROVED", "approval_digest": digest})
            if coordinator_connection.poll(0.1):
                request = coordinate.receive()
                action = request.get("action")
                if action == "seal" and set(request) == {"action"} and not sealed:
                    sealed = True
                    coordinate.send({"state": "SEALED", "commitment": commitment})
                elif action == "status" and set(request) == {"action"}:
                    coordinate.send(
                        {"state": "APPROVED" if approved else "SEALED", "approval": approved}
                    )
                elif action == "validation-status" and set(request) == {"action"}:
                    coordinate.send(
                        {
                            "state": "APPROVED" if validation_approved else "UNAVAILABLE",
                            "approval": validation_approved,
                        }
                    )
                elif action == "close" and set(request) == {"action"}:
                    if validation_approved is None or not released:
                        raise life.LifecycleError("close_state")
                    final = life.read_record(registry / "final_verdict.json", registry)
                    if (
                        final["state"] != "FINAL_VERDICT"
                        or final["body"].get("decision") != "FIXTURE_ACCEPTED"
                    ):
                        raise life.LifecycleError("close_state")
                    coordinate.send({"state": "CLOSED"})
                    break
                elif action == "release" and set(request) == {
                    "action",
                    "evidence",
                    "primary_receipt_digest",
                }:
                    if approved is None or not sealed or released or key is None:
                        raise life.LifecycleError("release_once")
                    evidence, primary, independent = evidence_checks()
                    expected = {
                        "action": "release",
                        "evidence": asdict(evidence),
                        "primary_receipt_digest": primary,
                    }
                    if io.canonical_json(request) != io.canonical_json(expected) or (
                        primary != approved["primary_receipt_digest"]
                        or independent != approved["independent_receipt_digest"]
                    ):
                        raise life.LifecycleError("release_binding")
                    released = True
                    _service_record(
                        registry,
                        reservation,
                        "release-once.json",
                        "RELEASE_ONCE",
                        {"commitment": commitment, "approval_digest": approved["approval_digest"]},
                        check,
                    )
                    released_key, key = key, None
                    coordinate.send(
                        {"state": "RELEASED", "key": released_key.hex(), "commitment": commitment}
                    )
                else:
                    raise life.LifecycleError("coordinator_action")
    except BaseException as error:
        failure = error
        key = None
        _service_failure(registry, reservation, error)
    finally:
        key = None
        life._shutdown(
            [
                stopped.set,
                lambda: life._join_thread(guard) if guard.ident is not None else None,
                coordinator_connection.close,
                approval_connection.close,
                bootstrap_connection.close,
            ],
            failure,
        )


class CoordinatorClient:
    def __init__(
        self,
        session: life.LiveSession,
        connection: Connection,
        secret: bytes,
        bootstrap: dict[str, Any],
    ) -> None:
        try:
            session._check(life.State.ATTEMPT_RESERVED)
            if session._client is not None:
                raise life.LifecycleError("client_once")
            session._coordinator_connection = connection
            self.session = session
            self.peer = _parse_identity(bootstrap["helper"])
            self.channel = FrameChannel(
                connection,
                secret,
                "coordinator",
                session.session_id,
                bootstrap["challenge"],
                session.owner,
                self.peer,
                session.binding,
            )
            self._last_reply: bytes | None = None
            session._client = self
        except BaseException as error:
            session.fail(error)
            raise

    def request(self, body: dict[str, object]) -> dict[str, Any]:
        try:
            self.session._check()
            if not self.peer.alive() or life.current_binding() != self.session.binding:
                raise life.LifecycleError("service_dead")
            self.channel.send(body)
            if not self.channel.connection.poll(10):
                raise life.LifecycleError("service_timeout")
            value = self.channel.receive()
            self._last_reply = io.canonical_json(value)
            return value
        except BaseException as error:
            self.session.fail(error)
            raise

    def seal(self) -> None:
        try:
            value = self.request({"action": "seal"})
            commitment = life._digest(bytes([2]) * 32)
            if io.canonical_json(value) != io.canonical_json(
                {"state": "SEALED", "commitment": commitment}
            ):
                raise life.LifecycleError("seal_binding")
            self.session.seed_commitment = commitment
            self.session._advance(
                life.State.ATTEMPT_RESERVED,
                life.State.VALIDATION_KEY_SEALED,
                {"commitment": commitment, "helper": asdict(self.peer)},
            )
        except BaseException as error:
            self.session.fail(error)
            raise

    def close(self) -> None:
        try:
            if self.request({"action": "close"}) != {"state": "CLOSED"}:
                raise life.LifecycleError("close_binding")
            self.channel.connection.close()
        except BaseException as error:
            self.session.fail(error)
            raise

    def status_frame(self, *, validation: bool = False) -> bytes:
        try:
            if type(validation) is not bool:
                raise life.LifecycleError("status_schema")
            value = self.request({"action": "validation-status" if validation else "status"})
            if set(value) != {"state", "approval"} or value["state"] not in (
                "APPROVED",
                "SEALED",
                "UNAVAILABLE",
            ):
                raise life.LifecycleError("status_schema")
            assert self._last_reply is not None
            return self._last_reply
        except BaseException as error:
            self.session.fail(error)
            raise


def _service_failure(registry: Any, reservation: Any, error: BaseException) -> None:
    if registry is None or reservation is None:
        return
    try:
        from datetime import UTC, datetime

        value = {
            **reservation,
            "state": "ERROR",
            "utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "body": {"reason": type(error).__name__, "detail": str(error)[:1024]},
        }
        io._exclusive_record(
            registry / "service-failure.json",
            {**value, "record_digest": life._digest(io.canonical_json(value))},
            root=registry,
        )
    except BaseException as secondary:
        error.add_note(type(secondary).__name__)
