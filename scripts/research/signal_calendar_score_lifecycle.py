"""Fixed-test lifecycle authority; experimental sampling remains unavailable."""

from __future__ import annotations

import hashlib
import json
import multiprocessing as mp
import os
import re
import stat
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from multiprocessing.connection import _ConnectionBase as Connection
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_score_study as io

_FIXTURE_ANCHOR = io.PROJECT / "var/verification/2026-10-05/calendar-score-lifecycle"
FIXTURE_PATHS = (("P1", 2048, 0),)
MAX_RECORD = io.MAX_RECORD
EXTRA_SOURCES = (
    "scripts/research/signal_calendar_score_lifecycle.py",
    "scripts/research/signal_calendar_score_lifecycle_service.py",
    "tests/unit/test_signal_calendar_score_lifecycle_research.py",
    "docs/plans/2026-10-05-calendar-score-lifecycle-authority.md",
)


class LifecycleError(RuntimeError):
    """A fixture authority contract failed."""


class State(StrEnum):
    READY = "READY"
    ATTEMPT_RESERVED = "ATTEMPT_RESERVED"
    VALIDATION_KEY_SEALED = "VALIDATION_KEY_SEALED"
    DEVELOPMENT_CLAIMED = "DEVELOPMENT_CLAIMED"
    DEVELOPMENT_COMPLETE = "DEVELOPMENT_COMPLETE"
    DEVELOPMENT_VERIFIED = "DEVELOPMENT_VERIFIED"
    REVIEW_APPROVED = "REVIEW_APPROVED"
    VALIDATION_AUTHORIZED = "VALIDATION_AUTHORIZED"
    VALIDATION_CLAIMED = "VALIDATION_CLAIMED"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    VALIDATION_VERIFIED = "VALIDATION_VERIFIED"
    FINAL_VERDICT = "FINAL_VERDICT"
    DEVELOPMENT_FAILED = "DEVELOPMENT_FAILED"
    ERROR = "ERROR"


@dataclass(frozen=True, slots=True)
class ProcessIdentity:
    pid: int
    creation_time_ns: int

    @classmethod
    def current(cls) -> ProcessIdentity:
        return cls(os.getpid(), round(psutil.Process().create_time() * 1_000_000_000))

    def alive(self) -> bool:
        try:
            if type(self.pid) is not int or type(self.creation_time_ns) is not int:
                return False
            process = psutil.Process(self.pid)
            return (
                round(process.create_time() * 1_000_000_000) == self.creation_time_ns
                and process.is_running()
                and process.status() not in (psutil.STATUS_ZOMBIE, psutil.STATUS_DEAD)
            )
        except psutil.Error:
            return False


@dataclass(frozen=True, slots=True)
class SourceBinding:
    protocol_digest: str
    manifest_digest: str
    resource_id: str
    resource_digest: str


def extended_manifest() -> io.Manifest:
    original = io.source_manifest()
    paths = {name: io.PROJECT / name for name in (*io.SOURCE_PATHS, *EXTRA_SOURCES)}
    manifest = io.manifest_for_paths(
        paths, protocol_hash=io.PROTOCOL_SHA256, scope="deterministic_test_fixture"
    )
    io.verify_manifest(manifest, paths, protocol_hash=io.PROTOCOL_SHA256)
    if original.payload["protocol_sha256"] != io.PROTOCOL_SHA256:
        raise LifecycleError("source_drift")
    return manifest


def current_binding() -> SourceBinding:
    manifest = extended_manifest()
    resources = io.load_operational_resources()
    return SourceBinding(
        io.PROTOCOL_SHA256,
        manifest.digest,
        resources.resource_contract_id,
        resources.resource_contract_sha256,
    )


@dataclass(frozen=True, slots=True)
class FixtureDomain:
    case_id: str
    namespace: str = io.TEST_NAMESPACE

    def __post_init__(self) -> None:
        if type(self.namespace) is not str or self.namespace != io.TEST_NAMESPACE:
            raise LifecycleError("test_domain")
        if type(self.case_id) is not str or re.fullmatch(r"[a-z0-9_-]{1,64}", self.case_id) is None:
            raise LifecycleError("fixture_case")

    @property
    def domain_id(self) -> str:
        return hashlib.sha256((self.namespace + "\0" + self.case_id).encode()).hexdigest()


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _regular(path: Path, root: Path) -> Path:
    guarded = io._guard_path(path, root, existing=True)
    if not stat.S_ISREG(guarded.stat().st_mode):
        raise LifecycleError("nonregular")
    return guarded


def read_record(path: Path, root: Path) -> dict[str, Any]:
    guarded = _regular(path, root)
    before = guarded.stat()
    with guarded.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        blob = stream.read(MAX_RECORD + 1)
    after = guarded.stat()

    def identity(info: os.stat_result) -> tuple[int, int, int, int]:
        return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns

    if identity(before) != identity(opened) or identity(before) != identity(after):
        raise LifecycleError("record_identity")
    if len(blob) > MAX_RECORD:
        raise LifecycleError("record_cap")
    value = json.loads(blob)
    if type(value) is not dict or io.canonical_json(value) != blob:
        raise LifecycleError("canonical_record")
    digest = value.pop("record_digest", None)
    if type(digest) is not str or digest != _digest(io.canonical_json(value)):
        raise LifecycleError("record_digest")
    expected = {
        "schema",
        "scope",
        "study_permission",
        "namespace",
        "state",
        "attempt_id",
        "session_id",
        "domain_id",
        "owner",
        "source_binding",
        "utc",
        "seed_commitment",
        "body",
    }
    if (
        set(value) != expected
        or type(value["schema"]) is not int
        or value["schema"] != 1
        or value["scope"] != "test_fixture"
        or value["study_permission"] is not False
        or value["namespace"] != io.TEST_NAMESPACE
        or type(value["state"]) is not str
        or value["state"]
        not in {s.value for s in State}
        | {"CLEANUP_INTENT", "CLEANUP_COMPLETE", "CLEANUP_ERROR", "RELEASE_ONCE"}
        or type(value["body"]) is not dict
    ):
        raise LifecycleError("record_schema")
    for field in ("attempt_id", "session_id", "domain_id"):
        if type(value[field]) is not str or re.fullmatch(r"[0-9a-f]{64}", value[field]) is None:
            raise LifecycleError("record_schema")
    owner, binding = value["owner"], value["source_binding"]
    if (
        type(owner) is not dict
        or set(owner) != {"pid", "creation_time_ns"}
        or any(type(v) is not int or v <= 0 for v in owner.values())
        or type(binding) is not dict
        or set(binding) != set(SourceBinding.__dataclass_fields__)
        or any(type(v) is not str for v in binding.values())
    ):
        raise LifecycleError("record_schema")
    for field in ("protocol_digest", "manifest_digest", "resource_digest"):
        if re.fullmatch(r"[0-9a-f]{64}", binding[field]) is None:
            raise LifecycleError("record_schema")
    stamp = value["utc"]
    if type(stamp) is not str or len(stamp) != 20:
        raise LifecycleError("record_schema")
    parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    if parsed.tzinfo != UTC or parsed.isoformat(timespec="seconds").replace("+00:00", "Z") != stamp:
        raise LifecycleError("record_schema")
    commitment = value["seed_commitment"]
    if commitment is not None and (
        type(commitment) is not str or re.fullmatch(r"[0-9a-f]{64}", commitment) is None
    ):
        raise LifecycleError("record_schema")
    return value


_ISSUER = object()
_LIVE: dict[str, LiveSession] = {}


class LiveSession:
    def __init__(
        self,
        domain: FixtureDomain,
        binding: SourceBinding,
        registry: Path,
        *,
        _issuer: object = None,
    ) -> None:
        if _issuer is not _ISSUER:
            raise LifecycleError("session_issuer")
        self.domain, self.binding, self.registry = domain, binding, registry
        self._reservation_digest: str | None = None
        self.owner = ProcessIdentity.current()
        self.session_id = _digest(uuid.uuid4().bytes)
        self.attempt_id = _digest((domain.domain_id + self.session_id).encode())
        self._state = State.READY
        self._state_record: tuple[Path, str] | None = None
        self._setup_handles()
        self.seed_commitment: str | None = None
        self._failure_registry = registry
        self._failure_domain_id = domain.domain_id
        self._failure_base = io.canonical_json(self._envelope("ATTEMPT_RESERVED", {}))

    @property
    def state(self) -> State:
        return self._state

    @property
    def evidence_root(self) -> Path:
        return self.registry / (
            "validation-evidence"
            if self.state
            in (
                State.VALIDATION_CLAIMED,
                State.VALIDATION_COMPLETE,
                State.VALIDATION_VERIFIED,
                State.FINAL_VERDICT,
            )
            else "evidence"
        )

    def _setup_handles(self) -> None:
        self._issued: list[object] = []
        self._child: Any = None
        self._manifest_bytes = b""
        self._child_capture: tuple[Any, ...] | None = None
        self._child_errors: list[BaseException] | None = None
        self._child_heartbeat: list[float] | None = None
        self._child_started: float | None = None
        self._client: Any = None
        self._coordinator_connection: Connection | None = None
        self._validation_approval: Any = None
        self._cleanup_started: set[str] = set()

    def _check(self, expected: State | None = None) -> None:
        session_id = getattr(self, "session_id", None)
        if type(session_id) is not str or _LIVE.get(session_id) is not self:
            raise LifecycleError("session_issuer")
        if self.state is State.ERROR:
            raise LifecycleError("terminal_state")
        if self.registry != _FIXTURE_ANCHOR / "attempts" / self.domain.domain_id:
            raise LifecycleError("registry_identity")
        reservation = read_record(self.registry / "attempt-reserved.json", self.registry)
        if _digest(io.canonical_json(reservation)) != self._reservation_digest:
            raise LifecycleError("reservation_drift")
        expected_reservation = {
            "attempt_id": self.attempt_id,
            "session_id": self.session_id,
            "domain_id": self.domain.domain_id,
            "owner": asdict(self.owner),
            "source_binding": asdict(self.binding),
            "state": "ATTEMPT_RESERVED",
            "seed_commitment": None,
            "body": {
                "future_replicates": dict(io.PHASE_REPLICATES),
                "future_worker_seconds": [21600, 43200],
                "resources": io.load_operational_resources().binding(),
                "extended_manifest": json.loads(self._manifest_bytes),
            },
        }
        if io.canonical_json(
            {k: reservation[k] for k in expected_reservation}
        ) != io.canonical_json(expected_reservation):
            raise LifecycleError("reservation_binding")
        if self._state_record is not None:
            state_path, state_digest = self._state_record
            current = read_record(state_path, self.registry)
            if (
                _digest(io.canonical_json(current)) != state_digest
                or current["state"] != self.state.value
            ):
                raise LifecycleError("transition_record")
        if self.owner != ProcessIdentity.current() or not self.owner.alive():
            raise LifecycleError("session_owner")
        if expected is not None and self.state is not expected:
            raise LifecycleError("transition")
        if (
            self.state is not State.FINAL_VERDICT
            and self._client is not None
            and not self._client.peer.alive()
        ):
            raise LifecycleError("service_dead")
        if current_binding() != self.binding:
            raise LifecycleError("source_drift")

    def _envelope(self, state: str, body: dict[str, object]) -> dict[str, object]:
        value: dict[str, object] = {
            "schema": 1,
            "scope": "test_fixture",
            "study_permission": False,
            "namespace": io.TEST_NAMESPACE,
            "state": state,
            "attempt_id": self.attempt_id,
            "session_id": self.session_id,
            "domain_id": self.domain.domain_id,
            "owner": asdict(self.owner),
            "source_binding": asdict(self.binding),
            "utc": datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "seed_commitment": self.seed_commitment,
            "body": body,
        }
        return {**value, "record_digest": _digest(io.canonical_json(value))}

    def _record(self, name: str, state: str, body: dict[str, object]) -> str:
        candidate = self.registry / (name + ".pending")
        envelope = self._envelope(state, body)
        io._exclusive_record(candidate, envelope, root=self.registry)
        actual = read_record(candidate, self.registry)
        if io.canonical_json(actual) != io.canonical_json(
            {k: v for k, v in envelope.items() if k != "record_digest"}
        ):
            raise LifecycleError("candidate_drift")
        state_digest = _digest(io.canonical_json(actual))
        self._check()
        destination = io._guard_path(self.registry / name, self.registry)
        os.link(candidate, destination, follow_symlinks=False)
        return state_digest

    def _advance(self, before: State, after: State, body: dict[str, object]) -> None:
        try:
            self._check(before)
            state_path = self.registry / (after.value.lower() + ".json")
            state_digest = self._record(after.value.lower() + ".json", after.value, body)
            self._state_record = (state_path, state_digest)
            self._state = after
        except BaseException as error:
            self.fail(error)
            raise

    def complete_development(self, token: CompletionToken) -> None:
        self._token(token, CompletionToken)
        self._advance(State.DEVELOPMENT_CLAIMED, State.DEVELOPMENT_COMPLETE, asdict(token.proof))

    def verify_development(self, token: VerificationToken) -> None:
        self._token(token, VerificationToken)
        self._advance(
            State.DEVELOPMENT_COMPLETE,
            State.DEVELOPMENT_VERIFIED,
            {"receipt_digest": token.receipt_digest, "evidence": asdict(token.evidence)},
        )

    def _token(self, token: object, expected: type[object]) -> None:
        if type(token) is not expected or not any(token is issued for issued in self._issued):
            error = LifecycleError("token_issuer")
            self.fail(error)
            raise error

    def accept_reviewer_response(self, frame: bytes) -> ReviewerApprovalToken:
        try:
            validation = self.state is State.VALIDATION_VERIFIED
            self._check(State.VALIDATION_VERIFIED if validation else State.DEVELOPMENT_VERIFIED)
            if self._client is None or frame is not self._client._last_reply:
                raise LifecycleError("approval_issuer")
            value = json.loads(frame)
            if (
                io.canonical_json(value) != frame
                or set(value) != {"state", "approval"}
                or value["state"] != "APPROVED"
            ):
                raise LifecycleError("approval_state")
            approval_path = self.registry / (
                "validation-reviewer-approved.json" if validation else "reviewer-approved.json"
            )
            approved = read_record(approval_path, self.registry)
            approval = value["approval"]
            if type(approval) is not dict or io.canonical_json(
                {k: v for k, v in approval.items() if k != "approval_digest"}
            ) != io.canonical_json(approved["body"]):
                raise LifecycleError("approval_binding")
            digest = io._hash_file(approval_path)
            if approval["approval_digest"] != digest:
                raise LifecycleError("approval_digest")
            token = ReviewerApprovalToken(digest, json.dumps(approved["body"], sort_keys=True))
            if validation:
                self._record(
                    "validation-review-accepted.json",
                    State.VALIDATION_VERIFIED.value,
                    {"approval_digest": digest},
                )
                self._validation_approval = token
            else:
                self._advance(
                    State.DEVELOPMENT_VERIFIED, State.REVIEW_APPROVED, {"approval_digest": digest}
                )
            self._issued.append(token)
            return token
        except BaseException as error:
            self.fail(error)
            raise

    def authorize_validation(self, approval: ReviewerApprovalToken) -> bytes:
        try:
            self._token(approval, ReviewerApprovalToken)
            self._check(State.REVIEW_APPROVED)
            body = json.loads(approval.body)
            value = self._client.request(
                {
                    "action": "release",
                    "evidence": body["evidence"],
                    "primary_receipt_digest": body["primary_receipt_digest"],
                }
            )
            key = bytes.fromhex(value.get("key", ""))
            expected = {
                "state": "RELEASED",
                "key": (bytes([2]) * 32).hex(),
                "commitment": self.seed_commitment,
            }
            if (
                io.canonical_json(value) != io.canonical_json(expected)
                or len(key) != 32
                or key == bytes([1]) * 32
                or _digest(key) != self.seed_commitment
            ):
                raise LifecycleError("release_binding")
            self._advance(
                State.REVIEW_APPROVED,
                State.VALIDATION_AUTHORIZED,
                {"commitment": self.seed_commitment, "approval_digest": approval.approval_digest},
            )
            return key
        except BaseException as error:
            self.fail(error)
            raise

    def claim_validation(self) -> None:
        self._advance(
            State.VALIDATION_AUTHORIZED,
            State.VALIDATION_CLAIMED,
            {
                "fixed_key_commitment": self.seed_commitment,
                "expected_paths": [list(p) for p in FIXTURE_PATHS],
            },
        )

    def complete_validation(self, token: CompletionToken) -> None:
        self._token(token, CompletionToken)
        if token.proof.evidence.phase != "validation_fixture":
            self.fail(LifecycleError("phase_binding"))
            raise LifecycleError("phase_binding")
        self._advance(State.VALIDATION_CLAIMED, State.VALIDATION_COMPLETE, asdict(token.proof))

    def verify_validation(self, token: VerificationToken) -> None:
        self._token(token, VerificationToken)
        if token.evidence.phase != "validation_fixture":
            self.fail(LifecycleError("phase_binding"))
            raise LifecycleError("phase_binding")
        self._advance(
            State.VALIDATION_COMPLETE,
            State.VALIDATION_VERIFIED,
            {"receipt_digest": token.receipt_digest, "evidence": asdict(token.evidence)},
        )

    def finish_fixture(self) -> None:
        from scripts.research.signal_calendar_score_lifecycle_service import _receipt

        try:
            self._check(State.VALIDATION_VERIFIED)
            self._token(self._validation_approval, ReviewerApprovalToken)
            assert self._validation_approval is not None
            approval = self._validation_approval
            body = json.loads(approval.body)
            evidence, _ = _artifact_fields(
                self.evidence_root,
                self.attempt_id,
                self.session_id,
                self.domain.domain_id,
                phase="validation_fixture",
            )
            path = self.registry / "validation-reviewer-approved.json"
            approved = read_record(path, self.registry)
            if (
                io.canonical_json(body["evidence"]) != io.canonical_json(asdict(evidence))
                or _receipt(self.evidence_root, "verified-primary.json", evidence)
                != body["primary_receipt_digest"]
                or _receipt(self.evidence_root, "verified-reviewer.json", evidence)
                != body["independent_receipt_digest"]
                or io._hash_file(path) != approval.approval_digest
                or io.canonical_json(approved["body"]) != io.canonical_json(body)
                or body["source_review_digest"] != self.binding.manifest_digest
                or body["decision"] != "FIXTURE_ACCEPTED"
            ):
                raise LifecycleError("final_binding")
            self._advance(
                State.VALIDATION_VERIFIED,
                State.FINAL_VERDICT,
                {
                    "decision": "FIXTURE_ACCEPTED",
                    "study_permission": False,
                    "approval_digest": approval.approval_digest,
                    "evidence": asdict(evidence),
                    "primary_receipt_digest": body["primary_receipt_digest"],
                    "independent_receipt_digest": body["independent_receipt_digest"],
                },
            )
        except BaseException as error:
            self.fail(error)
            raise

    def claim_development(self) -> None:
        self._advance(
            State.VALIDATION_KEY_SEALED,
            State.DEVELOPMENT_CLAIMED,
            {"fixed_key": "01" * 32, "expected_paths": [list(p) for p in FIXTURE_PATHS]},
        )

    def _failure_envelope(self, state: str, body: dict[str, object]) -> dict[str, Any]:
        value: dict[str, Any] = json.loads(self._failure_base)
        value.pop("record_digest")
        value.update(
            state=state,
            body=body,
            utc=datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z"),
        )
        return {**value, "record_digest": _digest(io.canonical_json(value))}

    def _guard_failure_registry(self) -> Path:
        registry = self._failure_registry
        if registry != _FIXTURE_ANCHOR / "attempts" / self._failure_domain_id:
            raise LifecycleError("registry_identity")
        return io._guard_path(registry, _FIXTURE_ANCHOR, existing=True)

    def fail(self, error: BaseException) -> None:
        self._state = State.ERROR
        try:
            registry = self._guard_failure_registry()
            if not (registry / "failure.json").exists():
                io._exclusive_record(
                    registry / "failure.json",
                    self._failure_envelope(
                        "ERROR", {"reason": type(error).__name__, "detail": str(error)[:1024]}
                    ),
                    root=registry,
                )
        except BaseException as secondary:
            error.add_note("Failure evidence: " + type(secondary).__name__)
        finally:
            try:
                connection = self._coordinator_connection
                if connection is not None:
                    connection.close()
            except BaseException as secondary:
                error.add_note("Authority shutdown: " + type(secondary).__name__)


def reserve_fixture(domain: FixtureDomain, binding: SourceBinding) -> LiveSession:
    if type(domain) is not FixtureDomain or type(binding) is not SourceBinding:
        raise LifecycleError("test_domain")
    if binding != current_binding():
        raise LifecycleError("source_drift")
    anchor = _FIXTURE_ANCHOR
    io._guard_reparse_chain(anchor)
    if not anchor.is_dir():
        raise LifecycleError("fixture_anchor")
    attempts = io._guard_path(anchor / "attempts", anchor)
    attempts.mkdir(exist_ok=True)
    registry = io._guard_path(attempts / domain.domain_id, anchor)
    try:
        registry.mkdir()
    except FileExistsError as error:
        raise LifecycleError("exhausted") from error
    session = LiveSession(domain, binding, registry, _issuer=_ISSUER)
    try:
        manifest = extended_manifest()
        if manifest.digest != binding.manifest_digest:
            raise LifecycleError("source_drift")
        session._manifest_bytes = io.canonical_json(manifest.payload)
        io._exclusive_record(
            registry / "attempt-reserved.json",
            session._envelope(
                "ATTEMPT_RESERVED",
                {
                    "future_replicates": dict(io.PHASE_REPLICATES),
                    "future_worker_seconds": [21600, 43200],
                    "resources": io.load_operational_resources().binding(),
                    "extended_manifest": manifest.payload,
                },
            ),
            root=registry,
        )
        session._reservation_digest = _digest(
            io.canonical_json(read_record(registry / "attempt-reserved.json", registry))
        )
        _LIVE[session.session_id] = session
        session._check()
        session._state_record = (registry / "attempt-reserved.json", session._reservation_digest)
        session._state = State.ATTEMPT_RESERVED
        return session
    except BaseException as error:
        session.fail(error)
        raise


@dataclass(frozen=True, slots=True)
class EvidenceBinding:
    attempt_id: str
    session_id: str
    domain_id: str
    phase: str
    seed_commitment: str
    payload_digest: str
    index_digest: str
    results_digest: str
    terminal_digest: str


@dataclass(frozen=True, slots=True)
class CompletionProof:
    child: ProcessIdentity
    exit_code: int
    evidence: EvidenceBinding
    paths: int
    metrics: int
    words: int
    payload_bytes: int


@dataclass(frozen=True, slots=True)
class CompletionToken:
    proof: CompletionProof


@dataclass(frozen=True, slots=True)
class VerificationToken:
    evidence: EvidenceBinding
    receipt_digest: str


@dataclass(frozen=True, slots=True)
class ChildHandle:
    process: Any
    connection: Connection
    heartbeat: Connection
    started: float
    _stopped: threading.Event
    monitor: threading.Thread
    errors: tuple[BaseException, ...]
    identity: ProcessIdentity | None = None
    joined: bool = False
    last_heartbeat: float | None = None

    @property
    def stopped(self) -> bool:
        return self._stopped.is_set()


FIXTURE_TIMEOUT = 15.0


def _artifact_evidence(session: LiveSession) -> tuple[EvidenceBinding, dict[str, Any]]:
    return _artifact_fields(
        session.evidence_root,
        session.attempt_id,
        session.session_id,
        session.domain.domain_id,
        phase="validation_fixture"
        if session.evidence_root.name == "validation-evidence"
        else "test_fixture",
    )


def _artifact_fields(
    root: Path, attempt_id: str, session_id: str, domain_id: str, *, phase: str = "test_fixture"
) -> tuple[EvidenceBinding, dict[str, Any]]:
    from scripts.research import signal_calendar_score_verify as verify

    terminal = verify._load(root, "fixture-terminal.json")
    claim = verify._load(root, "fixture-claim.json")
    manifest, payload = verify.current_manifest()
    expected_claim = {
        "schema": 1,
        "scope": verify.SCOPE,
        "namespace": io.TEST_NAMESPACE,
        "phase": "test_fixture",
        "root": "0" * 64,
        "paths": [list(p) for p in FIXTURE_PATHS],
        "protocol_digest": io.PROTOCOL_SHA256,
        "source_manifest_digest": manifest,
        "manifest": payload,
    }
    if io.canonical_json(claim) != io.canonical_json(expected_claim):
        raise LifecycleError("fixture_claim")
    expected_terminal_keys = {
        "schema",
        "scope",
        "state",
        "claim_digest",
        "payload_digest",
        "index_digest",
        "report_digest",
        "paths",
        "metrics",
        "words",
        "payload_bytes",
    }
    if (
        set(terminal) != expected_terminal_keys
        or type(terminal["schema"]) is not int
        or terminal["schema"] != 1
        or terminal["scope"] != verify.SCOPE
    ):
        raise LifecycleError("fixture_terminal")
    claim_digest = io._hash_file(_regular(root / "fixture-claim.json", root))
    index = list(
        io.read_canonical_records(
            _regular(root / "fixture-index.jsonl", root), total_cap=8192, record_cap=8192
        )
    )
    if len(index) != 1:
        raise LifecycleError("fixture_index")
    row = index[0]
    expected_header = {
        "schema": 1,
        "phase": "test_fixture",
        "profile_id": "P1",
        "n": 2048,
        "replicate": 0,
        "offset": 0,
        "size": 2050,
        "words": 12300,
        "claim_digest": claim_digest,
    }
    if set(row) != set(expected_header) | {"payload_sha256", "results"} or io.canonical_json(
        {k: row[k] for k in expected_header}
    ) != io.canonical_json(expected_header):
        raise LifecycleError("fixture_index")
    _check_result_schema(row["results"])
    summary = verify._cells()
    verify._accumulate(summary, "P1", row["results"])
    report = verify._load(root, "fixture-report.json")
    expected_report = {
        "schema": 1,
        "scope": verify.SCOPE,
        "summary": summary,
        "claim_digest": claim_digest,
        "payload_digest": row["payload_sha256"],
        "index_digest": io._hash_file(root / "fixture-index.jsonl"),
    }
    if io.canonical_json(report) != io.canonical_json(expected_report):
        raise LifecycleError("fixture_report")
    if terminal["claim_digest"] != claim_digest:
        raise LifecycleError("fixture_terminal")
    if (
        claim["namespace"] != io.TEST_NAMESPACE
        or claim["phase"] != "test_fixture"
        or io.canonical_json(claim["paths"]) != io.canonical_json([list(p) for p in FIXTURE_PATHS])
        or terminal["state"] != "FIXTURE_COMPLETE"
        or any(type(terminal[k]) is not int for k in ("paths", "metrics", "words", "payload_bytes"))
        or (terminal["paths"], terminal["metrics"], terminal["words"], terminal["payload_bytes"])
        != (1, 3, 12300, 2050)
    ):
        raise LifecycleError("fixture_terminal")
    digests: dict[str, str] = {}
    for name in (
        "fixture-payload.bin",
        "fixture-index.jsonl",
        "fixture-report.json",
        "fixture-terminal.json",
    ):
        path = _regular(root / name, root)
        digests[name] = (
            _raw_snapshot(path, root)[1] if name == "fixture-payload.bin" else io._hash_file(path)
        )
    if (
        terminal["payload_digest"] != digests["fixture-payload.bin"]
        or terminal["index_digest"] != digests["fixture-index.jsonl"]
        or terminal["report_digest"] != digests["fixture-report.json"]
    ):
        raise LifecycleError("fixture_digest")
    evidence = EvidenceBinding(
        attempt_id,
        session_id,
        domain_id,
        phase,
        _digest(bytes([2 if phase == "validation_fixture" else 1]) * 32),
        digests["fixture-payload.bin"],
        digests["fixture-index.jsonl"],
        digests["fixture-report.json"],
        digests["fixture-terminal.json"],
    )
    return evidence, terminal


def _fixture_job(
    root: Path, binding: SourceBinding, completion: Connection, heartbeat: Connection, mode: str
) -> None:
    from scripts.research import signal_calendar_score_verify as verify

    stopped = threading.Event()
    errors: list[BaseException] = []

    def beat() -> None:
        try:
            while not stopped.is_set():
                heartbeat.send_bytes(b"heartbeat")
                stopped.wait(0.1)
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=beat, daemon=False)
    failure: BaseException | None = None
    try:
        thread.start()
        if current_binding() != binding:
            raise LifecycleError("source_drift")
        if mode == "write":
            verify.write_fixture(root, paths=FIXTURE_PATHS, namespace=io.TEST_NAMESPACE)
        elif mode in ("verify", "review"):
            verify.verify_fixture(
                root,
                expected_manifest=verify.current_manifest()[0],
                expected_paths=FIXTURE_PATHS,
                receipt_name="verified-primary.json"
                if mode == "verify"
                else "verified-reviewer.json",
            )
        else:
            raise LifecycleError("fixture_mode")
        stopped.set()
        thread.join(2)
        if thread.is_alive() or errors:
            raise LifecycleError("heartbeat_join")
        if current_binding() != binding:
            raise LifecycleError("source_drift")
        completion.send_bytes(
            io.canonical_json(
                {
                    "schema": 1,
                    "state": "DURABLY_CLOSED",
                    "owner": asdict(ProcessIdentity.current()),
                    "source_binding": asdict(binding),
                    "expected_paths": [list(p) for p in FIXTURE_PATHS],
                }
            )
        )
    except BaseException as error:
        failure = error
        raise
    finally:
        _shutdown(
            [
                stopped.set,
                lambda: _join_thread(thread) if thread.ident is not None else None,
                completion.close,
                heartbeat.close,
            ],
            failure,
        )


def launch_fixture_child(session: LiveSession) -> ChildHandle:
    expected = (
        State.VALIDATION_CLAIMED
        if session.state is State.VALIDATION_CLAIMED
        else State.DEVELOPMENT_CLAIMED
    )
    return _launch_owned_child(session, _fixture_writer, expected)


def _fixture_writer(
    root: Path, binding: SourceBinding, completion: Connection, heartbeat: Connection
) -> None:
    _fixture_job(root, binding, completion, heartbeat, "write")


def _fixture_verifier(
    root: Path, binding: SourceBinding, completion: Connection, heartbeat: Connection
) -> None:
    _fixture_job(root, binding, completion, heartbeat, "verify")


def _launch_owned_child(session: LiveSession, target: Any, expected: State) -> ChildHandle:
    process = None
    connections: list[Connection] = []
    try:
        session._check(expected)
        if session._child is not None and not session._child.joined:
            raise LifecycleError("child_once")
        context = mp.get_context("spawn")
        parent, child = context.Pipe(duplex=False)
        beat_parent, beat_child = context.Pipe(duplex=False)
        connections = [parent, child, beat_parent, beat_child]
        process = context.Process(
            target=target, args=(session.evidence_root, session.binding, child, beat_child)
        )
        process.start()
        assert process.pid is not None
        child.close()
        beat_child.close()
        stopped = threading.Event()
        errors: list[BaseException] = []
        started = time.monotonic()

        last_heartbeat = [started]

        def monitor() -> None:
            last = started
            try:
                while not stopped.wait(0.1):
                    try:
                        if beat_parent.poll():
                            if beat_parent.recv_bytes(32) != b"heartbeat":
                                raise LifecycleError("heartbeat_schema")
                            last = time.monotonic()
                            last_heartbeat[0] = last
                    except (EOFError, BrokenPipeError):
                        if process.is_alive() and not parent.poll():
                            raise LifecycleError("heartbeat_eof") from None
                        break
                    _fixture_resources(session.registry, started, int(process.pid or 0), last)
            except BaseException as error:
                errors.append(error)

        thread = threading.Thread(target=monitor, daemon=False)
        handle = ChildHandle(process, parent, beat_parent, started, stopped, thread, ())
        object.__setattr__(
            handle,
            "identity",
            ProcessIdentity(
                process.pid, round(psutil.Process(process.pid).create_time() * 1_000_000_000)
            ),
        )
        object.__setattr__(handle, "last_heartbeat", started)
        session._child_errors = errors
        session._child_heartbeat = last_heartbeat
        session._child_started = started
        session._child = handle
        session._child_capture = (process, handle.identity, parent, beat_parent, thread, stopped)
        thread.start()
        return handle
    except BaseException as error:
        _shutdown(
            [lambda: _stop_process(process), *[connection.close for connection in connections]],
            error,
        )
        session.fail(error)
        raise


def _fixture_resources(root: Path, started: float, pid: int, heartbeat: float) -> None:
    if time.monotonic() - started > FIXTURE_TIMEOUT:
        raise LifecycleError("fixture_timeout")
    if time.monotonic() - heartbeat > 30:
        raise LifecycleError("heartbeat_timeout")
    if psutil.Process().memory_info().rss > 512 * 1024**2:
        raise LifecycleError("parent_rss")
    try:
        child = psutil.Process(pid)
        rss = sum(p.memory_info().rss for p in [child, *child.children(recursive=True)])
    except psutil.NoSuchProcess:
        rss = 0
    if rss > 2 * 1024**3 or psutil.disk_usage(str(root)).free < 20 * 1024**3:
        raise LifecycleError("fixture_resource")


def stop_fixture_child(child: ChildHandle) -> None:
    _shutdown(
        [
            child._stopped.set,
            lambda: _stop_process(child.process),
            lambda: _join_thread(child.monitor) if child.monitor.ident is not None else None,
            child.connection.close,
            child.heartbeat.close,
        ],
        None,
    )


def supervise_fixture_child(session: LiveSession, child: object) -> CompletionToken:
    expected = (
        State.VALIDATION_CLAIMED
        if session.state is State.VALIDATION_CLAIMED
        else State.DEVELOPMENT_CLAIMED
    )
    return _supervise_owned_child(session, child, expected)


def _supervise_owned_child(
    session: LiveSession, child: object, expected_state: State
) -> CompletionToken:
    try:
        if type(child) is not ChildHandle or session._child is not child or child.joined:
            raise LifecycleError("child_issuer")
        captured = (
            child.process,
            child.identity,
            child.connection,
            child.heartbeat,
            child.monitor,
            child._stopped,
        )
        if captured != session._child_capture:
            raise LifecycleError("child_issuer")
        session._check(expected_state)
        errors, last_heartbeat, started = (
            session._child_errors,
            session._child_heartbeat,
            session._child_started,
        )
        if child.identity is None or errors is None or last_heartbeat is None or started is None:
            raise LifecycleError("child_issuer")
        while child.process.is_alive():
            child.process.join(0.1)
            if errors:
                raise errors[0]
            _fixture_resources(session.registry, started, child.process.pid, last_heartbeat[0])
        child._stopped.set()
        child.monitor.join(3)
        object.__setattr__(child, "joined", True)
        if child.monitor.is_alive() or errors:
            raise LifecycleError("heartbeat_join")
        if child.process.exitcode != 0:
            raise LifecycleError("child_exit")
        if not child.connection.poll(1):
            raise LifecycleError("completion_ack")
        ack_blob = _bounded_receive(child.connection, session.registry, started)
        ack = json.loads(ack_blob)
        if io.canonical_json(ack) != ack_blob:
            raise LifecycleError("completion_ack")
        expected = {
            "schema": 1,
            "state": "DURABLY_CLOSED",
            "owner": asdict(child.identity),
            "source_binding": asdict(session.binding),
            "expected_paths": [list(p) for p in FIXTURE_PATHS],
        }
        if io.canonical_json(ack) != io.canonical_json(expected):
            raise LifecycleError("completion_ack")
        child.connection.close()
        child.heartbeat.close()
        session._check(expected_state)
        _fixture_resources(session.registry, started, child.process.pid, last_heartbeat[0])
        evidence, terminal = _artifact_evidence(session)
        token = CompletionToken(
            CompletionProof(
                child.identity,
                child.process.exitcode,
                evidence,
                terminal["paths"],
                terminal["metrics"],
                terminal["words"],
                terminal["payload_bytes"],
            )
        )
        session._issued.append(token)
        return token
    except BaseException as error:
        session.fail(error)
        saved_capture = session._child_capture
        if saved_capture is not None:
            process, _, connection, heartbeat, monitor, stopped = saved_capture
            stopped.set()
            _shutdown(
                [
                    lambda: _stop_process(process),
                    lambda: _join_thread(monitor),
                    connection.close,
                    heartbeat.close,
                ],
                error,
            )
        raise


def verify_fixture_evidence(session: LiveSession, completion: CompletionToken) -> VerificationToken:
    try:
        session._token(completion, CompletionToken)
        expected = (
            State.VALIDATION_COMPLETE
            if session.state is State.VALIDATION_COMPLETE
            else State.DEVELOPMENT_COMPLETE
        )
        session._check(expected)
        evidence, _ = _artifact_evidence(session)
        if evidence != completion.proof.evidence:
            raise LifecycleError("completion_binding")
        child = _launch_owned_child(session, _fixture_verifier, expected)
        failure: BaseException | None = None
        try:
            _supervise_owned_child(session, child, expected)
        except BaseException as error:
            failure = error
            raise
        finally:
            _shutdown([lambda: stop_fixture_child(child)], failure)
        session._check()
        token = VerificationToken(
            evidence, io._hash_file(session.evidence_root / "verified-primary.json")
        )
        session._issued.append(token)
        return token
    except BaseException as error:
        session.fail(error)
        raise


@dataclass(frozen=True, slots=True)
class ReviewerApprovalToken:
    approval_digest: str
    body: str


def _receive_once(connection: Connection, output: Connection) -> None:
    try:
        blob = connection.recv_bytes(8192)
        output.send_bytes(io.canonical_json({"ok": True, "blob": blob.hex()}))
    except BaseException:
        output.send_bytes(io.canonical_json({"ok": False}))
    finally:
        connection.close()
        output.close()


def _bounded_receive(connection: Connection, root: Path, started: float) -> bytes:
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    reader = context.Process(target=_receive_once, args=(connection, sender))
    failure: BaseException | None = None
    try:
        reader.start()
        assert reader.pid is not None
        sender.close()
        while reader.is_alive():
            reader.join(0.1)
            _fixture_resources(root, started, reader.pid, time.monotonic())
        if reader.exitcode != 0 or not receiver.poll(0.1):
            raise LifecycleError("completion_ack")
        blob = receiver.recv_bytes(32768)
        value = json.loads(blob)
        if (
            type(value) is not dict
            or io.canonical_json(value) != blob
            or (
                set(value) != {"ok", "blob"}
                or value["ok"] is not True
                or type(value["blob"]) is not str
                or len(value["blob"]) > 16384
            )
        ):
            raise LifecycleError("completion_ack")
        return bytes.fromhex(value["blob"])
    except BaseException as error:
        failure = error
        raise
    finally:
        _shutdown([lambda: _stop_process(reader), receiver.close, sender.close], failure)


def verify_saved_fixture_bounded(root: Path) -> None:
    """Readonly TEST verification with no session or sampling token issuer."""
    from scripts.research import signal_calendar_score_verify as verify

    io._guard_path(root, _FIXTURE_ANCHOR, existing=True)
    claim = verify._load(root, "fixture-claim.json")
    if claim["namespace"] != io.TEST_NAMESPACE or io.canonical_json(
        claim["paths"]
    ) != io.canonical_json([list(p) for p in FIXTURE_PATHS]):
        raise LifecycleError("test_domain")
    binding = current_binding()
    context = mp.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    beat_receiver, beat_sender = context.Pipe(duplex=False)
    process = context.Process(
        target=_fixture_job, args=(root, binding, sender, beat_sender, "review")
    )
    errors: list[BaseException] = []
    stopped = threading.Event()
    started = time.monotonic()
    last = [started]
    failure: BaseException | None = None

    def monitor() -> None:
        try:
            while not stopped.wait(0.1):
                try:
                    if beat_receiver.poll():
                        if beat_receiver.recv_bytes(32) != b"heartbeat":
                            raise LifecycleError("heartbeat_schema")
                        last[0] = time.monotonic()
                except (EOFError, BrokenPipeError):
                    if process.is_alive() and not receiver.poll():
                        raise LifecycleError("heartbeat_eof") from None
                    break
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=monitor, daemon=False)
    try:
        process.start()
        assert process.pid is not None
        identity = ProcessIdentity(
            process.pid, round(psutil.Process(process.pid).create_time() * 1_000_000_000)
        )
        sender.close()
        beat_sender.close()
        thread.start()
        while process.is_alive():
            process.join(0.1)
            _fixture_resources(root, started, process.pid, last[0])
            if errors:
                raise errors[0]
        stopped.set()
        thread.join(3)
        if process.exitcode != 0 or thread.is_alive() or errors:
            raise LifecycleError("reviewer_exit")
        ack_blob = _bounded_receive(receiver, root, started)
        expected = {
            "schema": 1,
            "state": "DURABLY_CLOSED",
            "owner": asdict(identity),
            "source_binding": asdict(binding),
            "expected_paths": [list(p) for p in FIXTURE_PATHS],
        }
        if ack_blob != io.canonical_json(expected):
            raise LifecycleError("completion_ack")
        _fixture_resources(root, started, process.pid, last[0])
        if current_binding() != binding:
            raise LifecycleError("source_drift")
    except BaseException as error:
        failure = error
        raise
    finally:
        stopped.set()
        actions = [
            lambda: _stop_process(process),
            lambda: _join_thread(thread) if thread.ident is not None else None,
            receiver.close,
            sender.close,
            beat_receiver.close,
            beat_sender.close,
        ]
        _shutdown(actions, failure)


def _stop_process(process: Any) -> None:
    if process is None or process.pid is None:
        return
    if process.is_alive():
        process.terminate()
    process.join(3)
    if process.is_alive():
        process.kill()
        process.join(3)
    if process.is_alive():
        raise LifecycleError("shutdown_failed")


def _join_thread(thread: threading.Thread) -> None:
    thread.join(3)
    if thread.is_alive():
        raise LifecycleError("heartbeat_join")


def _shutdown(actions: list[Any], failure: BaseException | None) -> None:
    first = failure
    for action in actions:
        try:
            action()
        except BaseException as error:
            if first is None:
                first = error
            else:
                first.add_note("Owned shutdown: " + type(error).__name__)
    if failure is None and first is not None:
        raise first


def _check_result_schema(rows: Any) -> None:
    from math import gcd

    fields = {
        "metric",
        "truth",
        "total",
        "count",
        "arithmetic",
        "precision",
        "reason",
        "lower",
        "upper",
        "covered",
        "lower_miss",
        "upper_miss",
        "detected",
    }
    if type(rows) is not list or len(rows) != 3:
        raise LifecycleError("fixture_results")
    for row, metric in zip(rows, ("raw", "win", "synthetic_excess"), strict=True):
        if (
            type(row) is not dict
            or set(row) != fields
            or row["metric"] != metric
            or type(row["count"]) is not int
            or not 0 <= row["count"] <= 4096
            or type(row["reason"]) is not str
            or len(row["reason"]) > 512
            or any(
                type(row[k]) is not bool
                for k in (
                    "arithmetic",
                    "precision",
                    "covered",
                    "lower_miss",
                    "upper_miss",
                    "detected",
                )
            )
        ):
            raise LifecycleError("fixture_results")
        for key in ("truth", "total", "lower", "upper"):
            value = row[key]
            if value is None and key in ("lower", "upper"):
                continue
            if (
                type(value) is not list
                or len(value) != 2
                or any(type(v) is not int or v.bit_length() > 2048 for v in value)
                or value[1] <= 0
                or gcd(value[0], value[1]) != 1
            ):
                raise LifecycleError("fixture_results")


@dataclass(frozen=True, slots=True)
class CleanupReceipt:
    phase: str
    raw_sha256: str
    payload_bytes: int
    state: str


def _raw_snapshot(path: Path, root: Path) -> tuple[tuple[int, int, int, int], str]:
    guarded = _regular(path, root)
    before = guarded.stat()
    if before.st_size != 2050:
        raise LifecycleError("raw_size")
    identity = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    digest = hashlib.sha256()
    with guarded.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns) != identity:
            raise LifecycleError("raw_identity")
        blob = stream.read(2051)
        if len(blob) != 2050 or stream.read(1):
            raise LifecycleError("raw_size")
        digest.update(blob)
    after = guarded.stat()
    if (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) != identity:
        raise LifecycleError("raw_identity")
    return identity, digest.hexdigest()


def cleanup_fixture_raw(
    session: LiveSession, primary: VerificationToken, reviewer: ReviewerApprovalToken
) -> CleanupReceipt:
    from scripts.research.signal_calendar_score_lifecycle_service import _receipt

    phase = "unknown"
    raw: Path | None = None
    try:
        session._check(State.FINAL_VERDICT)
        session._token(primary, VerificationToken)
        session._token(reviewer, ReviewerApprovalToken)
        phase = primary.evidence.phase
        if phase not in ("test_fixture", "validation_fixture"):
            raise LifecycleError("cleanup_phase")
        prefix = "validation" if phase == "validation_fixture" else "development"
        if phase in session._cleanup_started:
            raise LifecycleError("cleanup_once")
        approval = json.loads(reviewer.body)
        if io.canonical_json(approval["evidence"]) != io.canonical_json(asdict(primary.evidence)):
            raise LifecycleError("cleanup_binding")
        root = session.registry / ("validation-evidence" if prefix == "validation" else "evidence")
        evidence, _ = _artifact_fields(
            root, session.attempt_id, session.session_id, session.domain.domain_id, phase=phase
        )
        if evidence != primary.evidence:
            raise LifecycleError("cleanup_binding")
        primary_digest = _receipt(root, "verified-primary.json", evidence)
        independent_digest = _receipt(root, "verified-reviewer.json", evidence)
        if (
            primary_digest != primary.receipt_digest
            or primary_digest != approval["primary_receipt_digest"]
            or independent_digest != approval["independent_receipt_digest"]
            or approval["source_review_digest"] != session.binding.manifest_digest
            or approval["decision"] != "FIXTURE_ACCEPTED"
        ):
            raise LifecycleError("cleanup_binding")
        review_path = session.registry / (
            "validation-reviewer-approved.json"
            if prefix == "validation"
            else "reviewer-approved.json"
        )
        review_record = read_record(review_path, session.registry)
        if io._hash_file(review_path) != reviewer.approval_digest or io.canonical_json(
            review_record["body"]
        ) != io.canonical_json(approval):
            raise LifecycleError("cleanup_binding")
        raw = root / "fixture-payload.bin"
        identity, digest = _raw_snapshot(raw, root)
        if digest != evidence.payload_digest:
            raise LifecycleError("raw_digest")
        body: dict[str, object] = {
            "phase": phase,
            "raw_sha256": digest,
            "raw_identity": list(identity),
            "payload_bytes": 2050,
            "primary_receipt_digest": primary_digest,
            "reviewer_approval_digest": reviewer.approval_digest,
            "independent_receipt_digest": independent_digest,
            "evidence": asdict(evidence),
        }
        session._cleanup_started.add(phase)
        session._record("cleanup-" + prefix + "-intent.json", "CLEANUP_INTENT", body)
        if _raw_snapshot(raw, root) != (identity, digest):
            raise LifecycleError("raw_identity")
        session._check(State.FINAL_VERDICT)
        raw.unlink()
        io._guard_path(raw, root)
        if raw.exists():
            raise LifecycleError("cleanup_absence")
        session._record("cleanup-" + prefix + "-complete.json", "CLEANUP_COMPLETE", body)
        return CleanupReceipt(phase, digest, 2050, "CLEANUP_COMPLETE")
    except BaseException as error:
        session.fail(error)
        try:
            prefix = "validation" if phase == "validation_fixture" else "development"
            raw_status = "unknown" if raw is None else ("remaining" if raw.exists() else "absent")
            registry = session._guard_failure_registry()
            io._exclusive_record(
                registry / ("cleanup-" + prefix + "-error.json"),
                session._failure_envelope(
                    "CLEANUP_ERROR",
                    {"phase": phase, "raw_status": raw_status, "reason": type(error).__name__},
                ),
                root=registry,
            )
        except BaseException as secondary:
            error.add_note("Cleanup evidence: " + type(secondary).__name__)
        raise
