"""Owned full-runner coordinator; saved records never grant live authority."""

from __future__ import annotations

import hashlib
import json
import math
import multiprocessing as mp
import os
import re
import secrets
import stat
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from itertools import pairwise
from multiprocessing.connection import _ConnectionBase as Connection
from pathlib import Path
from typing import Any, cast

import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_lifecycle_service as channels
from scripts.research import signal_calendar_score_phase as phase
from scripts.research import signal_calendar_score_study as io

SESSION_LIMIT = 295800.0
CONTROL_ALLOWANCE = 600.0
# Python 3.12 perf_counter is system-wide on Windows since 3.10; verified 2026-10-06.
# https://docs.python.org/3.12/library/time.html#time.perf_counter
_PREFLIGHT_REPLICATES = 16
_ROLE = "reviewer"
_ISSUER = object()
_SESSIONS: dict[int, _Session] = {}


class RunnerError(io.StudyError):
    """An owned stage failed, without manufacturing permission."""


class _Session:
    def __init__(self, case: str, issuer: object) -> None:
        if issuer is not _ISSUER:
            raise RunnerError("session_issuer")
        self._case = case
        self._state = life.State.READY
        self._owner = life.ProcessIdentity.current()
        self._binding = phase.current_binding()
        self._session_id = uuid.uuid4().hex + uuid.uuid4().hex
        self._registry = phase.TEST_ANCHOR / "attempts" / hashlib.sha256(case.encode()).hexdigest()
        self._namespace = io.TEST_NAMESPACE
        self._started = time.perf_counter()
        self._session_anchor = self._started
        self._capture = (
            self._case,
            self._owner,
            self._binding,
            self._session_id,
            self._registry,
            self._namespace,
        )
        self._reservation = b""
        self._channel: Any = None
        self._child: Any = None
        self._tokens: dict[int, object] = {}
        self._cleanup_attempted: set[Path] = set()
        self._observed: bytes | None = None
        self._stage_context: tuple[Path, str, float, str] | None = None
        self._control_deadline = self._started + CONTROL_ALLOWANCE
        self._peers: tuple[life.ProcessIdentity, ...] = ()
        self._retired_peers = False
        self._closing_helper: life.ProcessIdentity | None = None
        self._approval_receipts: dict[str, str] = {}
        self._measurements: list[dict[str, Any]] = []
        self._active_stage_deadline: float | None = None
        self._scan_intervals: list[tuple[float, float]] = []
        self._preflight_deadline: float | None = None
        self._preflight_deadline_anchor: float | None = None

    @property
    def state(self) -> life.State:
        return self._state

    @property
    def registry(self) -> Path:
        return self._registry

    def _check(self, expected: life.State | None = None) -> None:
        if _SESSIONS.get(id(self)) is not self:
            raise RunnerError("session_issuer")
        if self._state == life.State.ERROR:
            raise RunnerError("terminal_error")
        if self._preflight_deadline != self._preflight_deadline_anchor or (
            self._preflight_deadline is not None and time.perf_counter() > self._preflight_deadline
        ):
            raise RunnerError("preflight_deadline")
        if self._capture != (
            self._case,
            self._owner,
            self._binding,
            self._session_id,
            self._registry,
            self._namespace,
        ):
            raise RunnerError("session_drift")
        if (
            self._owner != life.ProcessIdentity.current()
            or phase.current_binding() != self._binding
        ):
            raise RunnerError("source_or_owner")
        if (
            self._started != self._session_anchor
            or not 0 <= time.perf_counter() - self._session_anchor <= SESSION_LIMIT
        ):
            raise RunnerError("session_deadline")
        if not self._retired_peers and any(
            not p.alive() for p in self._peers if p != self._closing_helper
        ):
            raise RunnerError("active_peer_dead")
        if self._reservation and any(
            io._guard_path(self.registry / name, self.registry).exists()
            for name in ("attempt-failure.json", "service-failure.json")
        ):
            raise RunnerError("attempt_error")
        if (
            self._active_stage_deadline is not None
            and time.perf_counter() > self._active_stage_deadline
        ):
            raise RunnerError("stage_deadline")
        if expected is not None and self._state != expected:
            raise RunnerError("state")
        if (
            self._reservation
            and phase._read_bytes(
                self._registry / "attempt-reserved.json", self._registry, io.MAX_RECORD
            )
            != self._reservation
        ):
            raise RunnerError("reservation_drift")

    def fail(self, original: BaseException, *, residual: str = "UNKNOWN_INCOMPLETE") -> None:
        self._state = life.State.ERROR
        case, owner, binding, session_id, registry, namespace = self._capture
        try:
            phase._record(
                registry,
                "attempt-failure.json",
                {
                    "schema": 1,
                    "state": "ERROR",
                    "namespace": namespace,
                    "case": case,
                    "owner": asdict(owner),
                    "source_binding": asdict(binding),
                    "session_id": session_id,
                    "error": f"{type(original).__name__}:{original}",
                    "active_residual": residual,
                    "last_observed": json.loads(self._observed)
                    if self._observed is not None
                    else None,
                    "observation_authority": "LOWER_BOUND_NOT_FINAL",
                },
            )
        except BaseException as secondary:
            original.add_note(f"Failure evidence: {type(secondary).__name__}")
        actions = [self._channel.connection.close] if self._channel is not None else []
        life._shutdown(actions, original)

    def _token(self, token: object, kind: type[object]) -> None:
        try:
            self._check()
            if type(token) is not kind or self._tokens.get(id(token)) is not token:
                raise RunnerError("token_issuer")
        except BaseException as error:
            if _SESSIONS.get(id(self)) is self:
                self.fail(error)
            raise


def _set_preflight_deadline(session: _Session, deadline: float | None) -> None:
    if deadline is not None:
        _remaining_preflight(deadline, CONTROL_ALLOWANCE)
    session._preflight_deadline = session._preflight_deadline_anchor = deadline


def _remaining_preflight(deadline: float | None, local: float) -> float:
    if deadline is None:
        return local
    if type(deadline) is not float or not math.isfinite(deadline):
        raise RunnerError("preflight_deadline")
    remaining = deadline - time.perf_counter()
    if not 0 < remaining <= CONTROL_ALLOWANCE:
        raise RunnerError("preflight_deadline")
    return min(local, remaining)


def _reserve_test(
    case: str,
    *,
    reviewer: life.ProcessIdentity | None = None,
    preflight_deadline: float | None = None,
) -> _Session:
    if type(case) is not str or re.fullmatch("[a-z0-9_-]{1,64}", case) is None:
        raise RunnerError("test_case")
    io._guard_path(phase.TEST_ANCHOR, io.PROJECT)
    session = _Session(case, _ISSUER)
    _set_preflight_deadline(session, preflight_deadline)
    registry = session.registry
    phase.TEST_ANCHOR.mkdir(parents=True, exist_ok=True)
    attempts = phase.TEST_ANCHOR / "attempts"
    io._guard_path(attempts, phase.TEST_ANCHOR)
    attempts.mkdir(exist_ok=True)
    io._guard_path(registry, attempts)
    try:
        registry.mkdir()
    except FileExistsError as error:
        raise RunnerError("attempt_exhausted") from error
    _SESSIONS[id(session)] = session
    try:
        reservation_deadline = (
            {} if preflight_deadline is None else {"preflight_deadline": preflight_deadline}
        )
        phase._record(
            registry,
            "attempt-reserved.json",
            {
                "schema": 1,
                "state": "ATTEMPT_RESERVED",
                "scope": "UNAVAILABLE_TEST_ONLY",
                "namespace": io.TEST_NAMESPACE,
                "case": case,
                "attempt_id": registry.name,
                "session_id": session._session_id,
                "owner": asdict(session._owner),
                "reviewer": asdict(session._owner if reviewer is None else reviewer),
                "combined_free_required": _required_initial_free(),
                "observed_free": psutil.disk_usage(str(registry)).free,
                "source_binding": asdict(session._binding),
                "manifest": phase.phase_manifest().payload,
                "phase_counts": {p: list(io.phase_totals(p)) for p in io.PHASE_REPLICATES},
                "worker_seconds": dict(io.PHASE_DEADLINES),
                "verifier_seconds": io.load_operational_resources().effective_verifier_seconds,
                "session_seconds": SESSION_LIMIT,
                "session_started_monotonic": session._session_anchor,
                "phase_seed": None,
                **reservation_deadline,
            },
        )
        session._reservation = phase._read_bytes(
            registry / "attempt-reserved.json", registry, io.MAX_RECORD
        )
        _record_trial(session)
        session._state = life.State.ATTEMPT_RESERVED
        return session
    except BaseException as error:
        session.fail(error)
        raise


def run_reviewed_study(reviewed_manifest: str) -> dict[str, object]:
    if _ROLE != "reviewer":
        raise RunnerError("reviewer_role")
    if (
        type(reviewed_manifest) is not str
        or reviewed_manifest != phase.current_binding().manifest_digest
    ):
        raise RunnerError("reviewed_source")
    return _run_actual_after_readiness(reviewed_manifest)


def _run_actual_after_readiness(reviewed_manifest: str) -> dict[str, object]:
    readiness = _collect_readiness(reviewed_manifest)
    if type(readiness) is dict:
        return readiness
    _check_readiness(readiness)
    if phase.current_binding().manifest_digest != reviewed_manifest:
        raise RunnerError("reviewed_source")
    return _launch_pipeline(
        io.PROTOCOL_SHA256, mode="actual", namespace=io.EXPERIMENT_NAMESPACE, readiness=readiness
    )


def run_integrated_preflight(case_id: str) -> dict[str, object]:
    if type(case_id) is not str or re.fullmatch("[A-Za-z0-9_-]{1,64}", case_id) is None:
        raise RunnerError("preflight_case")
    return _measure_integrated_preflight(case_id)


def _phase_worker(
    bootstrap: Connection | None,
    completion: Connection | None,
    heartbeat: Connection | None,
    owner: life.ProcessIdentity | None,
) -> None:
    if bootstrap is None or completion is None or heartbeat is None or owner is None:
        raise RunnerError("unowned_worker")
    _owned_worker(bootstrap, completion, heartbeat, owner)


@dataclass(frozen=True, slots=True)
class _StageProof:
    owner: life.ProcessIdentity
    child: life.ProcessIdentity
    exit_code: int
    monitor_joined: bool
    durable_ack: bool
    kind: str
    role: str
    elapsed: float
    samples: bytes
    observation: _ParentObservation
    work: _WorkObservation


@dataclass(frozen=True, slots=True)
class _StageToken:
    evidence: phase.PhaseEvidence
    proof: _StageProof


@dataclass(frozen=True, slots=True)
class _WorkerRegistration:
    owner: life.ProcessIdentity
    worker: life.ProcessIdentity
    claim_digest: str
    root: Path
    source: phase.SourceBinding


_WORKERS: dict[int, _WorkerRegistration] = {}


def _claim_test_phase(session: _Session, name: str, *, preflight: bool = False) -> Path:
    session._check()
    if session._namespace != io.TEST_NAMESPACE or name not in io.PHASE_REPLICATES:
        raise RunnerError("test_domain")
    root = session.registry / name
    io._guard_path(root, session.registry)
    root.mkdir()
    phase._prepare_test_claim(
        root,
        phase._test_plan(name, _PREFLIGHT_REPLICATES if preflight else 1, preflight=preflight),
        attempt_id=session.registry.name,
        session_id=session._session_id,
    )
    session._state = (
        life.State.DEVELOPMENT_CLAIMED if name == "development" else life.State.VALIDATION_CLAIMED
    )
    return root


def _validate_worker_registration(marker: object, root: Path, claim: bytes) -> None:
    registered = _WORKERS.get(id(marker))
    if type(marker) is not _WorkerRegistration or registered is not marker:
        raise RunnerError("worker_issuer")
    if (
        marker.worker != life.ProcessIdentity.current()
        or not marker.owner.alive()
        or marker.claim_digest != phase._hash(claim)
        or marker.root != root
        or marker.source != phase.current_binding()
    ):
        raise RunnerError("worker_binding")
    plan, value = phase.validate_claim(root, claim, marker.source)
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        _validate_actual_claim(root, value, marker.owner)
    elif io._guard_path(root.parent / "attempt-registration.json", root.parent).exists():
        _validate_fixture_authority(root, value, marker.source)


def _validate_actual_claim(root: Path, value: dict[str, Any], owner: life.ProcessIdentity) -> None:
    _validate_actual_claim_impl(root, value, owner)


def _worker_bootstrap(
    connection: Connection, owner: life.ProcessIdentity
) -> tuple[dict[str, Any], channels.FrameChannel]:
    parent = mp.parent_process()
    if parent is None or parent.pid != owner.pid or not owner.alive():
        raise RunnerError("worker_parent")
    blob = connection.recv_bytes(io.MAX_RECORD)
    value = json.loads(blob)
    required = {"secret", "session_id", "challenge", "binding", "owner", "child"}
    if type(value) is not dict or set(value) != required or io.canonical_json(value) != blob:
        raise RunnerError("worker_bootstrap")
    worker = life.ProcessIdentity.current()
    binding = phase.current_binding()
    expected = {
        "binding": asdict(binding),
        "owner": asdict(owner),
        "child": asdict(worker),
    }
    if io.canonical_json({k: value[k] for k in expected}) != io.canonical_json(expected):
        raise RunnerError("worker_bootstrap")
    secret = value["secret"]
    if type(secret) is not str or re.fullmatch("[0-9a-f]{64}", secret) is None:
        raise RunnerError("worker_bootstrap")
    channel = channels.FrameChannel(
        connection,
        bytes.fromhex(secret),
        "coordinator",
        value["session_id"],
        value["challenge"],
        worker,
        owner,
        binding,
    )
    return channel.receive(), channel


_STARTUP_REASONS = frozenset(
    {
        "unknown",
        "transport",
        "authentication",
        "worker_parent",
        "worker_bootstrap",
        "worker_claim",
        "worker_owner",
        "test_domain",
        "ready_barrier",
        "start_barrier",
        "start_owner_or_source",
        "peer_exit",
        "ready_deadline",
        "receive_deadline_or_source",
    }
)
_STARTUP_CAP = 4096


def _startup_reason(error: BaseException) -> str:
    if type(error) in (RunnerError, life.LifecycleError) and len(error.args) == 1:
        reason = error.args[0]
        if type(reason) is str and reason in _STARTUP_REASONS:
            return reason
    if isinstance(error, (OSError, EOFError)):
        return "transport"
    return "unknown"


def _send_startup_error(
    connection: Connection, owner: life.ProcessIdentity, error: BaseException
) -> None:
    blob = io.canonical_json(
        {
            "schema": 1,
            "state": "STARTUP_ERROR",
            "reason": _startup_reason(error),
            "owner": asdict(owner),
            "worker": asdict(life.ProcessIdentity.current()),
            "source": phase.current_binding().manifest_digest,
        }
    )
    if len(blob) + 4 > _STARTUP_CAP:
        raise RunnerError("startup_hint_cap")
    connection.send_bytes(blob)


def _record_startup_error(
    session: _Session,
    root: Path,
    kind: str,
    role: str,
    process: Any,
    worker: life.ProcessIdentity | None,
    connection: Connection,
    error: BaseException,
    counts: phase.Progress,
) -> None:
    # Read only after owned stop/join and sender close: even a partial frame
    # cannot block teardown. This hint is never a receipt or success authority.
    status, hint = "MISSING", None
    if process.pid is not None and process.exitcode is not None and worker is not None:
        try:
            try:
                pending = connection.poll(0)
            except BrokenPipeError:
                # An empty closed Windows pipe has no hint; receive errors stay invalid.
                pending = False
            if pending:
                blob = connection.recv_bytes(_STARTUP_CAP)
                status = "INVALID"
                value = json.loads(blob)
                if type(value) is dict and type(value.get("reason")) is str:
                    reason = value["reason"]
                    expected = {
                        "schema": 1,
                        "state": "STARTUP_ERROR",
                        "reason": reason,
                        "owner": asdict(session._owner),
                        "worker": asdict(worker),
                        "source": session._binding.manifest_digest,
                    }
                    if reason in _STARTUP_REASONS and blob == io.canonical_json(expected):
                        status, hint = "AVAILABLE", reason
        except EOFError:
            pass
        except (OSError, ValueError, TypeError):
            status = "INVALID"
    phase._record(
        root,
        f"{kind}-{role}-startup-failure.json",
        {
            "schema": 1,
            "state": "ERROR",
            "stage": "STARTUP_BEFORE_WORK_AUTHORITY",
            "kind": kind,
            "role": role,
            "owner": asdict(session._owner),
            "worker": asdict(worker) if worker else None,
            "source_binding": asdict(session._binding),
            "session_id": session._session_id,
            "primary_reason": _startup_reason(error),
            "hint_status": status,
            "worker_hint": hint,
            "child_exit": process.exitcode,
            "last_observed": asdict(counts),
            "active_residual": "UNKNOWN_INCOMPLETE",
            "diagnostic_authority": "UNTRUSTED_HINT_ONLY",
            "ts": phase._utc(),
        },
    )


def _owned_worker(
    bootstrap: Connection,
    completion: Connection,
    heartbeat: Connection,
    owner: life.ProcessIdentity,
) -> None:
    global _ROLE
    _ROLE = "worker"
    stopped = threading.Event()
    stage_started = threading.Event()
    heartbeat_lock = threading.Lock()
    monitor: threading.Thread | None = None
    failure: BaseException | None = None
    errors: list[BaseException] = []
    snapshot = [phase.Progress(0, 0, 0, 0, 0)]
    try:
        boot, _channel = _worker_bootstrap(bootstrap, owner)
        required = {"root", "claim_digest", "kind", "role", "test_fault"}
        if (
            set(boot) != required
            or boot["kind"] not in ("writer", "verifier")
            or boot["role"] not in ("primary", "reviewer")
        ):
            raise RunnerError("worker_bootstrap")
        root = Path(boot["root"])
        claim = phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
        binding = phase.current_binding()
        plan, value = phase.validate_claim(root, claim, binding)
        if phase._hash(claim) != boot["claim_digest"]:
            raise RunnerError("worker_claim")
        if value["coordinator"] != asdict(owner) and boot["kind"] == "writer":
            raise RunnerError("worker_owner")
        if boot["test_fault"] is not None and plan.namespace == io.EXPERIMENT_NAMESPACE:
            raise RunnerError("test_domain")
        marker = _WorkerRegistration(
            owner, life.ProcessIdentity.current(), boot["claim_digest"], root, binding
        )
        _WORKERS[id(marker)] = marker
        _validate_worker_registration(marker, root, claim)
        if boot["test_fault"] == "hard-exit":
            os._exit(73)

        def beat() -> None:
            sequence = 0
            try:
                while not stopped.is_set():
                    if plan.namespace == io.PREFLIGHT_NAMESPACE:
                        deadline = phase._read_record(root.parent, "attempt-reserved.json").get(
                            "preflight_deadline"
                        )
                        if deadline is None:
                            raise RunnerError("preflight_deadline")
                        _remaining_preflight(deadline, CONTROL_ALLOWANCE)
                    if not owner.alive() or phase.current_binding() != binding:
                        raise RunnerError("worker_lifetime")
                    if stage_started.is_set():
                        _check_worker_bootstrap(_channel)
                    with heartbeat_lock:
                        if stopped.is_set():
                            break
                        heartbeat.send_bytes(
                            io.canonical_json(
                                {
                                    "schema": 1,
                                    "sequence": sequence,
                                    "state": "ACTIVE",
                                    "worker": asdict(marker.worker),
                                    "source": binding.manifest_digest,
                                    "counts": asdict(snapshot[0]),
                                }
                            )
                        )
                    sequence += 1
                    stopped.wait(0.25)
            except BaseException as error:
                errors.append(error)

        def progress(counts: phase.Progress) -> None:
            _check_worker_bootstrap(_channel)
            snapshot[0] = counts
            if errors:
                raise errors[0]
            if not owner.alive() or phase.current_binding() != binding:
                raise RunnerError("worker_lifetime")

        monitor = threading.Thread(target=beat, daemon=False)
        monitor.start()
        _wait_for_stage_start(_channel, marker, boot["kind"], boot["role"], boot["test_fault"])
        stage_started.set()
        if boot["test_fault"] == "early-work":
            with heartbeat_lock:
                heartbeat.send_bytes(
                    io.canonical_json(
                        {
                            "schema": 1,
                            "state": "WORK_FINISHED",
                            "worker": asdict(marker.worker),
                            "source": binding.manifest_digest,
                            "counts": asdict(snapshot[0]),
                        }
                    )
                )
        if boot["kind"] == "writer":
            if plan.namespace != io.EXPERIMENT_NAMESPACE:
                _validate_worker_registration(marker, root, claim)
            capability = (
                phase._test_capability(root, claim)
                if plan.namespace != io.EXPERIMENT_NAMESPACE
                else phase._issue_worker_capability(root, claim, marker)
            )
            evidence = phase.write_phase(root, claim, capability, progress)
        else:
            evidence = phase.verify_phase(
                root,
                boot["claim_digest"],
                binding,
                boot["role"],
                progress,
                _worker_marker=marker,
            )
        stopped.set()
        with heartbeat_lock:
            work: dict[str, Any] = {
                "schema": 1,
                "state": "WORK_FINISHED",
                "worker": asdict(marker.worker),
                "source": binding.manifest_digest,
                "counts": asdict(snapshot[0]),
            }
            if boot["test_fault"] == "malformed-work":
                work["counts"]["active_words"] = 1
            if boot["test_fault"] == "wrong-work-words":
                work["counts"]["words"] -= 1
            if boot["test_fault"] != "missing-work":
                heartbeat.send_bytes(io.canonical_json(work))
            if boot["test_fault"] == "duplicate-work":
                heartbeat.send_bytes(io.canonical_json(work))
        if boot["test_fault"] == "exit-after-work":
            os._exit(73)
        life._join_thread(monitor)
        if errors:
            raise errors[0]
        progress(snapshot[0])
        heartbeat.send_bytes(
            io.canonical_json(
                {
                    "schema": 1,
                    "state": "DURABLE_FINISHED",
                    "worker": asdict(marker.worker),
                    "source": binding.manifest_digest,
                    "counts": asdict(snapshot[0]),
                }
            )
        )
        if boot["test_fault"] == "late-ready":
            time.sleep(0.3)
            _channel.send(
                _barrier_body(
                    "READY",
                    marker.owner,
                    marker.worker,
                    binding,
                    root,
                    marker.claim_digest,
                    boot["kind"],
                    boot["role"],
                )
            )
        # Retire the bootstrap channel before issuing the durable-close ACK.
        _check_worker_bootstrap(_channel)
        bootstrap.close()
        if boot["test_fault"] == "missing-ack-after-work":
            completion.close()
            return
        completion.send_bytes(
            io.canonical_json(
                {
                    "schema": 1,
                    "state": "DURABLE_FINISHED",
                    "claim_digest": boot["claim_digest"],
                    "kind": boot["kind"],
                    "role": boot["role"],
                    "worker": asdict(marker.worker),
                    "evidence": _evidence_dict(evidence),
                }
            )
        )
    except BaseException as error:
        failure = error
        if not stage_started.is_set():
            try:
                _send_startup_error(completion, owner, error)
            except BaseException:
                error.add_note("Startup diagnostic unavailable")
        raise
    finally:
        actions: list[Callable[[], Any]] = [stopped.set]
        if monitor is not None and monitor.ident is not None:
            actions.append(lambda: life._join_thread(monitor))
        actions.extend([bootstrap.close, completion.close, heartbeat.close])
        life._shutdown(actions, failure)


def _evidence_dict(evidence: phase.PhaseEvidence) -> dict[str, Any]:
    return {
        "binding": json.loads(evidence.binding),
        "summary": json.loads(evidence.summary),
        "decision": evidence.decision,
        "paths": evidence.paths,
        "metrics": evidence.metrics,
        "words": evidence.words,
        "payload_bytes": evidence.payload_bytes,
        "payload_digest": evidence.payload_digest,
        "index_digest": evidence.index_digest,
        "report_digest": evidence.report_digest,
        "terminal_digest": evidence.terminal_digest,
        "receipt_digest": evidence.receipt_digest,
    }


def _evidence_from(value: dict[str, Any]) -> phase.PhaseEvidence:
    required = set(phase.PhaseEvidence.__dataclass_fields__)
    if type(value) is not dict or set(value) != required:
        raise RunnerError("evidence_schema")
    if any(
        type(value[k]) is not int or value[k] < 0
        for k in ("paths", "metrics", "words", "payload_bytes")
    ):
        raise RunnerError("evidence_schema")
    for name in ("payload_digest", "index_digest", "report_digest", "terminal_digest"):
        if type(value[name]) is not str or re.fullmatch("[0-9a-f]{64}", value[name]) is None:
            raise RunnerError("evidence_schema")
    receipt = value["receipt_digest"]
    if type(receipt) is not str or (receipt and re.fullmatch("[0-9a-f]{64}", receipt) is None):
        raise RunnerError("evidence_schema")
    return phase.PhaseEvidence(
        io.canonical_json(value["binding"]),
        io.canonical_json(value["summary"]),
        value["decision"],
        value["paths"],
        value["metrics"],
        value["words"],
        value["payload_bytes"],
        value["payload_digest"],
        value["index_digest"],
        value["report_digest"],
        value["terminal_digest"],
        receipt,
    )


def _stage_limit(plan: phase.PhasePlan, kind: str) -> float:
    if plan.namespace == io.PREFLIGHT_NAMESPACE:
        return CONTROL_ALLOWANCE
    if plan.namespace != io.EXPERIMENT_NAMESPACE:
        return 15.0
    return (
        io.PHASE_DEADLINES[plan.phase]
        if kind == "writer"
        else float(io.load_operational_resources().effective_verifier_seconds)
    )


def _resource_snapshot(
    root: Path, started: float, pid: int, deadline: float, heartbeat: float
) -> tuple[int, int, int, float]:
    now = time.perf_counter()
    parent_rss = psutil.Process().memory_info().rss
    try:
        worker_process = psutil.Process(pid)
        tree_rss = worker_process.memory_info().rss + sum(
            child.memory_info().rss
            for child in worker_process.children(recursive=True)
            if child.is_running()
        )
    except psutil.NoSuchProcess:
        tree_rss = 0
    free = psutil.disk_usage(str(root)).free
    age = now - heartbeat
    if (
        now - started > deadline
        or parent_rss > io.PARENT_RSS_CAP
        or tree_rss > io.WORKER_RSS_CAP
        or free < io.FREE_RESERVE
        or age > 30.0
    ):
        raise RunnerError("resource_or_heartbeat")
    return parent_rss, tree_rss, free, age


def _final_guard(session: _Session, root: Path, claim: bytes, plan: phase.PhasePlan) -> None:
    session._check()
    phase.validate_claim(root, claim, session._binding)
    raw = root / "phase-payload.bin"
    index = root / "phase-index.jsonl"
    phase._storage(root, plan, raw.stat().st_size, index.stat().st_size)
    if session._stage_context is not None:
        stage_root, kind, started, _ = session._stage_context
        if stage_root != root or (
            time.perf_counter() - started > _stage_limit(plan, kind)
            or psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
            or psutil.disk_usage(str(root)).free < io.FREE_RESERVE
        ):
            raise RunnerError("final_resources")


def _run_owned_stage(
    session: _Session,
    root: Path,
    kind: str,
    role: str,
    *,
    _test_fault: str | None = None,
) -> _StageToken:
    started = time.perf_counter()
    try:
        session._check()
        if kind not in ("writer", "verifier") or role not in ("primary", "reviewer"):
            raise RunnerError("stage")
        if root.parent != session.registry or root.name not in io.PHASE_REPLICATES:
            raise RunnerError("stage_root")
        claim = phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
        plan, _value = phase.validate_claim(root, claim, session._binding)
        if _test_fault is not None and plan.namespace == io.EXPERIMENT_NAMESPACE:
            raise RunnerError("test_domain")
    except BaseException as error:
        if _SESSIONS.get(id(session)) is session:
            session.fail(error)
        raise
    session._stage_context = (root, kind, started, role)
    session._scan_intervals = []
    session._active_stage_deadline = started + _remaining_preflight(
        session._preflight_deadline, _stage_limit(plan, kind)
    )
    process, endpoints = _create_stage_process(session)
    parent_boot, child_boot, parent_ack, child_ack, parent_beat, child_beat = endpoints
    monitor: threading.Thread | None = None
    errors: list[BaseException] = []
    last = [started]
    finished = [False]
    work_finished: list[float | None] = [None]
    work_counts: list[phase.Progress | None] = [None]
    received = [False]
    barrier_started = [False]
    observation: _ParentObservation | None = None
    last_counts = [phase.Progress(0, 0, 0, 0, 0)]
    failure: BaseException | None = None
    samples = {
        "count": 0,
        "parent_rss_peak": 0,
        "tree_rss_peak": 0,
        "free_min": 1 << 64,
        "heartbeat_age_max": 0.0,
    }
    ack: bytes | None = None
    worker: life.ProcessIdentity | None = None
    try:
        process.start()
        session._child = process
        worker = _process_identity(process)
        child_boot.close()
        child_ack.close()
        child_beat.close()
        secret = secrets.token_bytes(32)
        challenge = secrets.token_hex(32)
        parent_boot.send_bytes(
            io.canonical_json(
                {
                    "secret": secret.hex(),
                    "session_id": session._session_id,
                    "challenge": challenge,
                    "binding": asdict(session._binding),
                    "owner": asdict(session._owner),
                    "child": asdict(worker),
                }
            )
        )
        channel = channels.FrameChannel(
            parent_boot,
            secret,
            "coordinator",
            session._session_id,
            challenge,
            session._owner,
            worker,
            session._binding,
        )
        channel.send(
            {
                "root": str(root),
                "claim_digest": phase._hash(claim),
                "kind": kind,
                "role": role,
                "test_fault": _test_fault,
            }
        )

        def watch() -> None:
            sequence = 0
            try:
                while True:
                    blob = parent_beat.recv_bytes(io.MAX_RECORD)
                    frame = json.loads(blob)
                    if type(frame) is not dict or io.canonical_json(frame) != blob:
                        raise RunnerError("heartbeat_schema")
                    expected = {
                        "schema": 1,
                        "worker": asdict(worker),
                        "source": session._binding.manifest_digest,
                        "state": frame.get("state"),
                        "counts": frame.get("counts"),
                    }
                    if finished[0]:
                        raise RunnerError("heartbeat_after_finished")
                    if frame.get("state") == "ACTIVE":
                        if work_finished[0] is not None:
                            raise RunnerError("heartbeat_after_work")
                        expected["sequence"] = sequence
                        sequence += 1
                    elif frame.get("state") == "WORK_FINISHED":
                        if work_finished[0] is not None:
                            raise RunnerError("duplicate_work")
                    elif frame.get("state") == "DURABLE_FINISHED":
                        if work_finished[0] is None:
                            raise RunnerError("missing_work")
                        finished[0] = True
                    else:
                        raise RunnerError("heartbeat_schema")
                    if io.canonical_json(frame) != io.canonical_json(expected):
                        raise RunnerError("heartbeat_schema")
                    counts = frame["counts"]
                    if (
                        type(counts) is not dict
                        or set(counts) != set(phase.Progress.__dataclass_fields__)
                        or any(type(v) is not int or not 0 <= v < 1 << 64 for v in counts.values())
                    ):
                        raise RunnerError("heartbeat_schema")
                    previous = asdict(last_counts[0])
                    if any(
                        counts[k] < previous[k]
                        for k in ("paths", "metrics", "words", "payload_bytes")
                    ):
                        raise RunnerError("heartbeat_regression")
                    if (
                        counts["paths"] == previous["paths"]
                        and counts["active_words"] < previous["active_words"]
                    ):
                        raise RunnerError("heartbeat_regression")
                    last_counts[0] = phase.Progress(**counts)
                    last[0] = time.perf_counter()
                    if frame["state"] == "WORK_FINISHED":
                        if not barrier_started[0] or (
                            counts["paths"],
                            counts["metrics"],
                            counts["payload_bytes"],
                            counts["active_words"],
                        ) != (plan.paths, plan.metrics, plan.payload_bytes, 0):
                            raise RunnerError("work_counts_or_barrier")
                        work_finished[0] = last[0]
                        work_counts[0] = last_counts[0]
                    session._observed = io.canonical_json(
                        {
                            "phase": plan.phase,
                            "kind": kind,
                            "role": role,
                            "child": asdict(worker),
                            "counts": counts,
                            "observed_monotonic": last[0],
                            "state": frame["state"],
                        }
                    )
                    received[0] = True
                    if barrier_started[0]:
                        try:
                            if parent_boot.poll(0):
                                parent_boot.recv_bytes(io.MAX_RECORD)
                                raise RunnerError("duplicate_ready")
                        except (EOFError, BrokenPipeError):
                            # Expected closure is accepted only together with
                            # the separately checked finished frame and exit0.
                            pass
            except EOFError:
                if not finished[0]:
                    errors.append(RunnerError("heartbeat_lost"))
            except BaseException as error:
                errors.append(error)

        monitor = threading.Thread(target=watch, daemon=False)
        monitor.start()
        observation = _start_stage(
            session, root, claim, plan, kind, role, process, channel, worker, started
        )
        barrier_started[0] = True
        limit = _stage_limit(plan, kind)
        while process.is_alive():
            session._check()
            if errors:
                raise errors[0]
            snapshot = _resource_snapshot(root, started, worker.pid, limit, last[0])
            samples["count"] += 1
            samples["parent_rss_peak"] = max(samples["parent_rss_peak"], snapshot[0])
            samples["tree_rss_peak"] = max(samples["tree_rss_peak"], snapshot[1])
            samples["free_min"] = min(samples["free_min"], snapshot[2])
            samples["heartbeat_age_max"] = max(samples["heartbeat_age_max"], snapshot[3])
            process.join(timeout=0.25)
        process.join()
        if process.exitcode != 0:
            raise RunnerError("child_exit")
        if monitor is None:
            raise RunnerError("monitor")
        life._join_thread(monitor)
        if errors:
            raise errors[0]
        _retire_parent_bootstrap(parent_boot, session, started, limit)
        if not received[0] or not finished[0]:
            raise RunnerError("heartbeat_lost")
        if not parent_ack.poll(1.0):
            raise RunnerError("missing_ack")
        ack = parent_ack.recv_bytes(io.MAX_RECORD)
        if time.perf_counter() - started > limit:
            raise RunnerError("deadline")
    except BaseException as error:
        failure = error
    finally:
        actions: list[Callable[[], Any]] = []
        if process.pid is not None:
            actions.append(lambda: life._stop_process(process))
        if failure is not None and observation is None:
            original: BaseException = failure

            def record_startup() -> None:
                _record_startup_error(
                    session, root, kind, role, process, worker, parent_ack, original, last_counts[0]
                )

            actions.extend([child_ack.close, record_startup])
        actions.extend(
            [
                parent_boot.close,
                child_boot.close,
                parent_ack.close,
                child_ack.close,
                parent_beat.close,
                child_beat.close,
            ]
        )
        if monitor is not None and monitor.ident is not None:
            actions.append(lambda: life._join_thread(monitor))
        try:
            life._shutdown(actions, failure)
        except BaseException as error:
            failure = error
        session._child = None
    if failure is not None:
        session.fail(failure)
        raise failure
    try:
        if ack is None or worker is None or observation is None or work_finished[0] is None:
            raise RunnerError("ack")
        parsed = json.loads(ack)
        evidence = _evidence_from(parsed["evidence"])
        expected = {
            "schema": 1,
            "state": "DURABLE_FINISHED",
            "claim_digest": phase._hash(claim),
            "kind": kind,
            "role": role,
            "worker": asdict(worker),
            "evidence": _evidence_dict(evidence),
        }
        if ack != io.canonical_json(expected):
            raise RunnerError("ack")
        if (evidence.paths, evidence.metrics, evidence.payload_bytes) != (
            plan.paths,
            plan.metrics,
            plan.payload_bytes,
        ):
            raise RunnerError("completion_counts")
        expected_final = phase.Progress(
            evidence.paths, evidence.metrics, evidence.words, evidence.payload_bytes, 0
        )
        captured_work = work_counts[0]
        if (
            captured_work is None
            or last_counts[0] != expected_final
            or captured_work != expected_final
        ):
            raise RunnerError("heartbeat_final_counts")
        _final_guard(session, root, claim, plan)
        proof = _StageProof(
            session._owner,
            worker,
            0,
            True,
            True,
            kind,
            role,
            time.perf_counter() - started,
            io.canonical_json(samples),
            observation,
            _issue_work_observation(observation, work_finished[0], captured_work, ()),
        )
        _check_parent_observation(session, root, proof)
        token = _publish_stage(session, root, claim, plan, evidence, proof)
        session._active_stage_deadline = None
        return token
    except BaseException as error:
        session.fail(error)
        raise


def _publish_stage(
    session: _Session,
    root: Path,
    claim: bytes,
    plan: phase.PhasePlan,
    evidence: phase.PhaseEvidence,
    proof: _StageProof,
) -> _StageToken:
    name = "phase-terminal" if proof.kind == "writer" else f"verified-{proof.role}"
    source = root / (name + "-candidate.json")
    candidate = phase._read_bytes(source, root, io.MAX_RECORD)
    expected_digest = (
        evidence.terminal_digest if proof.kind == "writer" else evidence.receipt_digest
    )
    if phase._hash(candidate) != expected_digest:
        raise RunnerError("candidate_drift")
    value = phase._decode(candidate)
    _candidate_guard(session, root, claim, plan, evidence, proof, value)
    if session._stage_context is None:
        raise RunnerError("stage_context")
    samples = json.loads(proof.samples)
    samples["count"] += 1
    samples["parent_rss_peak"] = max(samples["parent_rss_peak"], psutil.Process().memory_info().rss)
    samples["free_min"] = min(samples["free_min"], psutil.disk_usage(str(root)).free)
    _final_guard(session, root, claim, plan)
    # This cutoff includes supervised shutdown and all artifact scans. The small
    # accounting record's own persistence/link is included by the outer stage clock.
    proof = replace(
        proof,
        elapsed=time.perf_counter() - session._stage_context[2],
        samples=io.canonical_json(samples),
        work=_issue_work_observation(
            proof.observation,
            proof.work.finished_monotonic,
            proof.work.counts,
            tuple(session._scan_intervals),
        ),
    )
    proof_value = {**asdict(proof), "samples": samples}
    value.update(
        state="COMPLETE" if plan.namespace == io.EXPERIMENT_NAMESPACE else "TEST_PHASE_COMPLETE",
        completion=proof_value,
    )
    if proof.kind == "verifier":
        value["state"] = (
            "VERIFIED" if plan.namespace == io.EXPERIMENT_NAMESPACE else "TEST_VERIFIED"
        )
    parent_name = name + "-parent-candidate.json"
    phase._record(root, parent_name, value, plan=plan)
    parent_candidate = phase._read_bytes(root / parent_name, root, io.MAX_RECORD)
    if parent_candidate != io.canonical_json(value):
        raise RunnerError("candidate_drift")
    _final_guard(session, root, claim, plan)
    phase._storage(
        root,
        plan,
        plan.payload_bytes,
        (root / "phase-index.jsonl").stat().st_size,
        added_control=len(parent_candidate),
    )
    if proof.kind == "writer":
        evidence = phase.PhaseEvidence(
            evidence.binding,
            evidence.summary,
            evidence.decision,
            evidence.paths,
            evidence.metrics,
            evidence.words,
            evidence.payload_bytes,
            evidence.payload_digest,
            evidence.index_digest,
            evidence.report_digest,
            phase._hash(parent_candidate),
        )
    else:
        evidence = phase.PhaseEvidence(
            evidence.binding,
            evidence.summary,
            evidence.decision,
            evidence.paths,
            evidence.metrics,
            evidence.words,
            evidence.payload_bytes,
            evidence.payload_digest,
            evidence.index_digest,
            evidence.report_digest,
            evidence.terminal_digest,
            phase._hash(parent_candidate),
        )
    token = _StageToken(evidence, proof)
    session._tokens[id(token)] = token
    destination = io._guard_path(root / (name + ".json"), root)
    os.link(root / parent_name, destination, follow_symlinks=False)
    return token


def _guarded_hash(
    session: _Session,
    root: Path,
    claim: bytes,
    plan: phase.PhasePlan,
    name: str,
    expected_size: int | None = None,
) -> str:
    path = io._guard_path(root / name, root, existing=True)
    before = path.stat()
    if not stat.S_ISREG(before.st_mode) or (
        expected_size is not None and before.st_size != expected_size
    ):
        raise RunnerError("artifact_size")
    cap = (
        plan.payload_bytes
        if name == "phase-payload.bin"
        else plan.paths * plan.metadata_cap + io.MAX_RECORD
    )
    if before.st_size > cap:
        raise RunnerError("artifact_cap")
    hasher = hashlib.sha256()
    total = 0
    checked = time.perf_counter()
    with path.open("rb") as stream:
        if phase._identity(os.fstat(stream.fileno())) != phase._identity(before):
            raise RunnerError("file_drift")
        while chunk := stream.read(64 * 1024):
            total += len(chunk)
            if total > before.st_size:
                raise RunnerError("file_growth")
            hasher.update(chunk)
            if time.perf_counter() - checked >= 0.25:
                _final_guard(session, root, claim, plan)
                checked = time.perf_counter()
    if total != before.st_size or phase._identity(path.stat()) != phase._identity(before):
        raise RunnerError("file_drift")
    return hasher.hexdigest()


def _costed_hash(*args: Any, **kwargs: Any) -> str:
    session = cast(_Session, args[0])
    begun = time.perf_counter()
    try:
        return _guarded_hash(*args, **kwargs)
    finally:
        session._scan_intervals.append((begun, time.perf_counter()))


def _candidate_guard(
    session: _Session,
    root: Path,
    claim_bytes: bytes,
    plan: phase.PhasePlan,
    evidence: phase.PhaseEvidence,
    proof: _StageProof,
    candidate: dict[str, Any],
) -> None:
    claim = phase._decode(claim_bytes)
    binding = phase._binding(claim, phase._hash(claim_bytes))
    counts = asdict(
        phase.Progress(evidence.paths, evidence.metrics, evidence.words, evidence.payload_bytes, 0)
    )
    if evidence.binding != io.canonical_json(binding):
        raise RunnerError("evidence_binding")
    if evidence.decision != (
        "UNAVAILABLE_TEST_ONLY" if plan.namespace != io.EXPERIMENT_NAMESPACE else evidence.decision
    ) or evidence.decision not in ("PASS", "FAILED", "UNAVAILABLE_TEST_ONLY"):
        raise RunnerError("evidence_decision")
    report_blob = phase._read_bytes(root / "phase-report.json", root, io.MAX_RECORD)
    report = phase._decode(report_blob)
    expected_report = {
        "utc": report["utc"],
        "schema": 1,
        "scope": plan.scope,
        "binding": binding,
        "summary": json.loads(evidence.summary),
        "decision": evidence.decision,
        "counts": counts,
        "payload_digest": evidence.payload_digest,
        "index_digest": evidence.index_digest,
    }
    if (
        report_blob != io.canonical_json(expected_report)
        or phase._hash(report_blob) != evidence.report_digest
    ):
        raise RunnerError("report_drift")
    if _costed_hash(
        session, root, claim_bytes, plan, "phase-payload.bin", plan.payload_bytes
    ) != evidence.payload_digest or (
        _costed_hash(session, root, claim_bytes, plan, "phase-index.jsonl") != evidence.index_digest
    ):
        raise RunnerError("payload_or_index_drift")
    expected: dict[str, Any] = {
        "utc": candidate["utc"],
        "schema": 1,
        "binding": binding,
        "decision": evidence.decision,
        "counts": counts,
        "payload_digest": evidence.payload_digest,
        "index_digest": evidence.index_digest,
        "report_digest": evidence.report_digest,
    }
    if proof.kind == "writer":
        expected.update(state="PHASE_OUTPUT_CANDIDATE", worker=asdict(proof.child))
    else:
        terminal = phase._read_bytes(root / "phase-terminal.json", root, io.MAX_RECORD)
        if phase._hash(terminal) != evidence.terminal_digest:
            raise RunnerError("terminal_drift")
        expected.update(
            state="VERIFICATION_CANDIDATE",
            role=proof.role,
            terminal_digest=evidence.terminal_digest,
            summary_digest=phase._hash(evidence.summary),
            verifier=asdict(proof.child),
        )
    if io.canonical_json(candidate) != io.canonical_json(expected):
        raise RunnerError("candidate_schema")
    _final_guard(session, root, claim_bytes, plan)


def _validate_completion(root: Path, claim: bytes, terminal: dict[str, Any]) -> None:
    plan, value = phase.validate_claim(root, claim, phase.current_binding())
    proof = terminal.get("completion")
    required = set(_StageProof.__dataclass_fields__)
    if type(proof) is not dict or set(proof) != required:
        raise RunnerError("completion_schema")
    if (
        proof["kind"] != "writer"
        or proof["role"] != "primary"
        or (
            type(proof["exit_code"]) is not int
            or proof["exit_code"] != 0
            or proof["monitor_joined"] is not True
            or proof["durable_ack"] is not True
        )
    ):
        raise RunnerError("completion_proof")
    if io.canonical_json(proof["owner"]) != io.canonical_json(value["coordinator"]) or (
        io.canonical_json(proof["child"]) != io.canonical_json(terminal["worker"])
    ):
        raise RunnerError("completion_owner")
    for identity in (proof["owner"], proof["child"]):
        if not life.ProcessIdentity.valid_fields(identity):
            raise RunnerError("completion_owner")
    elapsed = proof["elapsed"]
    if type(elapsed) is not float or not 0 <= elapsed <= io.PHASE_DEADLINES[plan.phase]:
        raise RunnerError("completion_resources")
    sample = proof["samples"]
    if (
        type(sample) is not dict
        or set(sample)
        != {
            "count",
            "parent_rss_peak",
            "tree_rss_peak",
            "free_min",
            "heartbeat_age_max",
        }
        or any(
            type(sample[k]) is not int or sample[k] < 0
            for k in ("count", "parent_rss_peak", "tree_rss_peak", "free_min")
        )
    ):
        raise RunnerError("completion_resources")
    if (
        sample["count"] < 1
        or sample["parent_rss_peak"] > io.PARENT_RSS_CAP
        or sample["tree_rss_peak"] > io.WORKER_RSS_CAP
        or sample["free_min"] < io.FREE_RESERVE
        or type(sample["heartbeat_age_max"]) is not float
        or not 0 <= sample["heartbeat_age_max"] <= 30.0
    ):
        raise RunnerError("completion_resources")


def _process_identity(process: Any) -> life.ProcessIdentity:
    if process.pid is None:
        raise RunnerError("process_not_started")
    return life.ProcessIdentity.capture(process.pid)


def _bootstrap_owned(
    connection: Connection, process: Any, session_id: str, payload: dict[str, Any]
) -> channels.FrameChannel:
    owner, child = life.ProcessIdentity.current(), _process_identity(process)
    binding = phase.current_binding()
    secret, challenge = secrets.token_bytes(32), secrets.token_hex(32)
    connection.send_bytes(
        io.canonical_json(
            {
                "secret": secret.hex(),
                "session_id": session_id,
                "challenge": challenge,
                "binding": asdict(binding),
                "owner": asdict(owner),
                "child": asdict(child),
            }
        )
    )
    channel = channels.FrameChannel(
        connection, secret, "coordinator", session_id, challenge, owner, child, binding
    )
    channel.send(payload)
    return channel


def _receive_owned(
    channel: channels.FrameChannel,
    process: Any,
    deadline: float,
    binding: phase.SourceBinding,
    *,
    _guard: Callable[[], None] | None = None,
) -> dict[str, Any]:
    result: list[dict[str, Any]] = []
    errors: list[BaseException] = []
    finished = threading.Event()
    failure: BaseException | None = None
    started = time.perf_counter()
    packet_started: list[float | None] = [None]

    def receive() -> None:
        try:
            while not channel.connection.poll(0.25):
                if finished.is_set():
                    return
            packet_started[0] = time.perf_counter()
            result.append(channel.receive())
        except BaseException as error:
            errors.append(error)
        finally:
            finished.set()

    reader = threading.Thread(target=receive, daemon=False)
    reader.start()
    try:
        while not finished.wait(0.25):
            if _guard is not None:
                _guard()
            if (
                packet_started[0] is not None
                and time.perf_counter() - packet_started[0] > CONTROL_ALLOWANCE
            ):
                raise RunnerError("partial_frame_deadline")
            if time.perf_counter() - started > deadline or phase.current_binding() != binding:
                raise RunnerError("receive_deadline_or_source")
            if (
                psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
                or psutil.disk_usage(str(io.PROJECT)).free < io.FREE_RESERVE
            ):
                raise RunnerError("receive_resources")
            if not channel.remote.alive() or process.exitcode is not None:
                raise RunnerError("peer_exit")
        if errors:
            raise errors[0]
        if len(result) != 1:
            raise RunnerError("receive")
        return result[0]
    except BaseException as error:
        failure = error
        raise
    finally:
        actions: list[Callable[[], Any]] = []
        if not finished.is_set():
            actions.extend([lambda: life._stop_process(process), channel.connection.close])
        actions.append(lambda: life._join_thread(reader))
        life._shutdown(actions, failure)


def _adopt_reviewer_view(registry: Path) -> _Session:
    if _ROLE != "reviewer":
        raise RunnerError("reviewer_role")
    actual = registry == _actual_registry()
    io._guard_path(
        registry,
        io.EXPERIMENT_ROOT / "attempts" if actual else phase.TEST_ANCHOR / "attempts",
        existing=True,
    )
    reserved = phase._read_record(registry, "attempt-reserved.json")
    namespace = io.EXPERIMENT_NAMESPACE if actual else io.TEST_NAMESPACE
    if reserved["namespace"] != namespace:
        raise RunnerError("reviewer_namespace")
    session = _Session(reserved["case"], _ISSUER)
    _set_preflight_deadline(session, reserved.get("preflight_deadline"))
    expected_root = _actual_registry() if actual else session.registry
    if (
        registry != expected_root
        or io.canonical_json(reserved["source_binding"])
        != io.canonical_json(asdict(session._binding))
        or (
            actual
            and io.canonical_json(reserved["reviewer"]) != io.canonical_json(asdict(session._owner))
        )
    ):
        raise RunnerError("reviewer_view")
    session._registry, session._namespace = registry, namespace
    session._session_id = reserved["session_id"]
    if (
        type(reserved["session_started_monotonic"]) is not float
        or not 0 <= time.perf_counter() - reserved["session_started_monotonic"] <= SESSION_LIMIT
    ):
        raise RunnerError("reservation_clock")
    session._started = session._session_anchor = reserved["session_started_monotonic"]
    session._capture = (
        session._case,
        session._owner,
        session._binding,
        session._session_id,
        session._registry,
        session._namespace,
    )
    session._reservation = phase._read_bytes(
        registry / "attempt-reserved.json", registry, io.MAX_RECORD
    )
    session._state = life.State.ATTEMPT_RESERVED
    _SESSIONS[id(session)] = session
    session._check()
    return session


def _coordinator_request(session: _Session, body: dict[str, Any]) -> dict[str, Any]:
    try:
        session._check()
        if session._channel is None or not session._channel.remote.alive():
            raise RunnerError("helper_dead")
        session._control_deadline = time.perf_counter() + CONTROL_ALLOWANCE
        session._channel.send(body)
        # The coordinator has its own watchdog, independent of the helper.
        reply = cast(dict[str, Any], session._channel.receive())
        if body == {"action": "finish"} and reply == {"state": "CLOSED"}:
            # The launcher still requires actual owned exit0 before publication.
            session._closing_helper = session._channel.remote
        session._check()
        return reply
    except BaseException as error:
        session.fail(error)
        raise


def _run_coordinator(
    request_connection: Connection | None, bootstrap_connection: Connection | None
) -> None:
    global _ROLE
    _ROLE = "coordinator"
    if request_connection is None or bootstrap_connection is None:
        raise RunnerError("unowned_coordinator")
    parent = mp.parent_process()
    if parent is None or parent.pid is None:
        raise RunnerError("coordinator_parent")
    parent_identity = life.ProcessIdentity.capture(int(parent.pid))
    session: _Session | None = None
    control: channels.FrameChannel | None = None
    failure: BaseException | None = None
    transfers = 0
    stage = "bootstrap"
    stopped = threading.Event()
    started = time.perf_counter()
    source = phase.current_binding()

    def watchdog() -> None:
        while not stopped.wait(0.25):
            try:
                if not parent_identity.alive() or phase.current_binding() != source:
                    raise RunnerError("coordinator_lifetime_or_source")
                if (
                    psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
                    or psutil.disk_usage(str(io.PROJECT)).free < io.FREE_RESERVE
                ):
                    raise RunnerError("coordinator_resources")
                deadline = (
                    session._control_deadline
                    if session is not None
                    else started + CONTROL_ALLOWANCE
                )
                if time.perf_counter() > deadline:
                    raise RunnerError("coordinator_control_deadline")
                if session is not None:
                    session._check()
            except BaseException as error:
                if session is not None:
                    session.fail(error)
                os._exit(74)

    monitor = threading.Thread(target=watchdog, daemon=False)
    monitor.start()
    try:
        boot, control = _worker_bootstrap(bootstrap_connection, parent_identity)
        expected_boot = {"case", "mode", "namespace", "source_review_digest"}
        if boot.get("namespace") == io.PREFLIGHT_NAMESPACE:
            expected_boot.add("preflight_deadline")
        if set(boot) != expected_boot or (
            boot["namespace"]
            not in (io.TEST_NAMESPACE, io.PREFLIGHT_NAMESPACE, io.EXPERIMENT_NAMESPACE)
            or boot["source_review_digest"] != phase.current_binding().manifest_digest
        ):
            raise RunnerError("coordinator_bootstrap")
        actual = boot["namespace"] == io.EXPERIMENT_NAMESPACE
        if actual:
            if boot["mode"] != "actual" or boot["case"] != io.PROTOCOL_SHA256:
                raise RunnerError("actual_mode")
            marker = _CoordinatorRegistration(
                life.ProcessIdentity.current(),
                parent_identity,
                phase.current_binding(),
                boot["source_review_digest"],
            )
            _COORDINATORS[id(marker)] = marker
            session = _reserve_actual(marker)
        else:
            if boot["mode"] not in (
                "full",
                "development-failed",
                "coordinator-approval",
                "second-release",
                "late-close",
            ):
                raise RunnerError("test_mode")
            session = _reserve_test(
                boot["case"],
                reviewer=parent_identity,
                preflight_deadline=boot.get("preflight_deadline"),
            )
        control.send(
            {
                "state": "RESERVED",
                "registry": str(session.registry),
                "session_id": session._session_id,
                "reservation_digest": phase._hash(session._reservation),
            }
        )
        peers = _receive_coordinator_control(session, control, CONTROL_ALLOWANCE)
        if set(peers) != {"helper", "coordinator_secret", "challenge"}:
            raise RunnerError("coordinator_peers")
        helper = channels._parse_identity(peers["helper"])
        if not helper.alive():
            raise RunnerError("helper_dead")
        session._channel = channels.FrameChannel(
            request_connection,
            bytes.fromhex(peers["coordinator_secret"]),
            "coordinator",
            session._session_id,
            peers["challenge"],
            session._owner,
            helper,
            session._binding,
        )
        session._peers = (parent_identity, helper)
        reply = _coordinator_request(session, {"action": "seal"})
        if (
            set(reply) != {"state", "commitment"}
            or reply["state"] != "SEALED"
            or type(reply["commitment"]) is not str
            or re.fullmatch("[a-f0-9]{64}", reply["commitment"]) is None
            or (not actual and reply["commitment"] != hashlib.sha256(bytes([2]) * 32).hexdigest())
        ):
            raise RunnerError("seal_reply")
        session._state = life.State.VALIDATION_KEY_SEALED
        sealed_commitment = reply["commitment"]
        development_key = secrets.token_bytes(32) if actual else bytes(32)
        if actual and phase._hash(development_key) == sealed_commitment:
            raise RunnerError("phase_seed_distinct")
        validation_key: bytes | None = None
        checks: dict[str, tuple[_StageToken, _ReviewToken]] = {}
        totals: dict[str, Any] = {}
        from scripts.research import signal_calendar_score_runner_service as service

        for name in ("development", "validation"):
            session._control_deadline = session._started + SESSION_LIMIT
            stage = name
            if actual:
                key = development_key if name == "development" else validation_key
                if key is None:
                    raise RunnerError("validation_sealed")
                root = _claim_actual_phase(session, name, key, phase._hash(key))
            else:
                root = _claim_test_phase(
                    session, name, preflight=boot["namespace"] == io.PREFLIGHT_NAMESPACE
                )
            complete = _timed_owned_stage(session, root, "writer", "primary")
            session._state = (
                life.State.DEVELOPMENT_COMPLETE
                if name == "development"
                else life.State.VALIDATION_COMPLETE
            )
            primary = _timed_owned_stage(session, root, "verifier", "primary")
            session._token(complete, _StageToken)
            session._token(primary, _StageToken)
            session._state = (
                life.State.DEVELOPMENT_VERIFIED
                if name == "development"
                else life.State.VALIDATION_VERIFIED
            )
            control.send({"state": "REVIEW_REQUIRED", "phase": name, "root": str(root)})
            session._control_deadline = time.perf_counter() + (
                io.load_operational_resources().effective_verifier_seconds + CONTROL_ALLOWANCE
                if actual
                else (CONTROL_ALLOWANCE if boot["namespace"] == io.PREFLIGHT_NAMESPACE else 30.0)
            )
            response = _receive_coordinator_control(
                session,
                control,
                io.load_operational_resources().effective_verifier_seconds + CONTROL_ALLOWANCE
                if actual
                else (CONTROL_ALLOWANCE if boot["namespace"] == io.PREFLIGHT_NAMESPACE else 30.0),
            )
            if (
                set(response) != {"state", "phase", "timing"}
                or response["state"] != "REVIEW_FINISHED"
                or response["phase"] != name
            ):
                raise RunnerError("reviewer_response")
            _validate_stage_measurement(response["timing"], session._binding)
            if response["timing"]["phase"] != name or response["timing"]["role"] != "reviewer":
                raise RunnerError("reviewer_timing")
            session._measurements.append(response["timing"])
            evidence = service._evidence_check(session.registry, name, session._binding)
            decision = (
                evidence["decision"]
                if actual
                else (
                    "TEST_FAILED"
                    if boot["mode"] == "development-failed" and name == "development"
                    else "TEST_PASS"
                )
            )
            approval_payload = {
                "action": "approve-" + name,
                "evidence": evidence,
                "source_review_digest": session._binding.manifest_digest,
                "control_decision": decision,
            }
            if boot["mode"] == "coordinator-approval" and name == "development":
                stage = "coordinator-approval"
                _coordinator_request(session, approval_payload)
                raise RunnerError("forbidden_approval_accepted")
            control.send({"state": "APPROVAL_REQUESTED", "phase": name, "decision": decision})
            session._control_deadline = time.perf_counter() + CONTROL_ALLOWANCE
            if _receive_coordinator_control(session, control, CONTROL_ALLOWANCE) != {
                "state": "APPROVED",
                "phase": name,
            }:
                raise RunnerError("reviewer_response")
            status = _coordinator_request(session, {"action": "status", "phase": name})
            approval = status.get("approval")
            if (
                status.get("state") != "APPROVED"
                or type(approval) is not dict
                or (
                    io.canonical_json(approval["evidence"]) != io.canonical_json(evidence)
                    or approval["source_review_digest"] != session._binding.manifest_digest
                    or approval["control_decision"] != decision
                )
            ):
                raise RunnerError("approval_binding")
            review_token = _review_token_from_owned_reply(
                session, root, primary, approval, parent_identity
            )
            checks[name] = (primary, review_token)
            totals[name + "_paths"], totals[name + "_metrics"] = (
                complete.evidence.paths,
                complete.evidence.metrics,
            )
            if name == "development":
                if decision in ("TEST_FAILED", "FAILED"):
                    session._state = life.State.DEVELOPMENT_FAILED
                    break
                request = {
                    "action": "release",
                    "evidence": evidence,
                    "approval_digest": approval["approval_digest"],
                }
                released = _coordinator_request(session, request)
                if set(released) != {"state", "key", "commitment"} or (
                    released["state"] != "VALIDATION_AUTHORIZED"
                    or released["commitment"] != sealed_commitment
                    or type(released["key"]) is not str
                    or re.fullmatch("[a-f0-9]{64}", released["key"]) is None
                ):
                    raise RunnerError("release_reply")
                validation_key = bytes.fromhex(released["key"])
                if phase._hash(validation_key) != sealed_commitment or (
                    actual and validation_key == development_key
                ):
                    raise RunnerError("phase_seed_distinct")
                transfers += 1
                session._state = life.State.VALIDATION_AUTHORIZED
                if boot["mode"] == "second-release":
                    stage = "second-release"
                    _coordinator_request(session, request)
                    transfers += 1
                    raise RunnerError("second_release_accepted")
            else:
                session._state = life.State.FINAL_VERDICT
        if actual:
            for name, (primary_check, review_check) in checks.items():
                _cleanup_phase(session, session.registry / name, primary_check, review_check)
        if _coordinator_request(session, {"action": "finish"}) != {"state": "CLOSED"}:
            raise RunnerError("finish_reply")
        result = {
            "state": session.state.value,
            "namespace": boot["namespace"],
            "study_permission": False,
            "sampling_executed": actual,
            "release_transfers": transfers,
            "stage_timings": session._measurements,
            **totals,
        }
        phase._record(
            session.registry,
            "attempt-result-candidate.json",
            {
                "schema": 1,
                "scope": "ARTIFICIAL_RESEARCH_ONLY" if actual else "UNAVAILABLE_TEST_ONLY",
                **result,
                "source_binding": asdict(session._binding),
                "session_id": session._session_id,
            },
        )
        control.send(result)
    except BaseException as error:
        failure = error
        if session is None and control is not None:
            try:
                control.send({"state": "BOOTSTRAP_ERROR", "error": str(error)})
            except BaseException as secondary:
                error.add_note(f"Bootstrap result: {type(secondary).__name__}")
        stopped.set()
        if session is not None:
            session.fail(error)
            reason = str(error)
            try:
                reason = phase._read_record(session.registry, "service-failure.json")["error"]
            except (io.StudyError, OSError):
                pass
            if control is not None:
                try:
                    control.send(
                        {
                            "state": "ERROR",
                            "namespace": session._namespace,
                            "study_permission": False,
                            "failure_stage": stage,
                            "failure_reason": reason,
                            "release_transfers": transfers,
                        }
                    )
                except BaseException as secondary:
                    error.add_note(f"Control result: {type(secondary).__name__}")
        raise
    finally:

        def close_request() -> None:
            request_connection.close()
            if session is not None and boot["mode"] == "late-close":
                raise OSError("coordinator late close")

        try:
            life._shutdown(
                [
                    stopped.set,
                    close_request,
                    bootstrap_connection.close,
                    lambda: life._join_thread(monitor),
                ],
                failure,
            )
        except BaseException as error:
            if session is not None:
                session.fail(error)
            raise


def _launch_pipeline(
    case: str,
    *,
    mode: str = "full",
    namespace: str = io.TEST_NAMESPACE,
    readiness: object | None = None,
    _preflight_deadline: float | None = None,
) -> dict[str, object]:
    if _ROLE != "reviewer":
        raise RunnerError("reviewer_role")
    actual = namespace == io.EXPERIMENT_NAMESPACE
    if namespace == io.PREFLIGHT_NAMESPACE:
        if _preflight_deadline is None:
            raise RunnerError("preflight_deadline")
        _remaining_preflight(_preflight_deadline, CONTROL_ALLOWANCE)
    elif _preflight_deadline is not None:
        raise RunnerError("preflight_deadline_namespace")
    if actual:
        _check_readiness(readiness)
        _READINESS_CONSUMED.add(id(readiness))
        if mode != "actual":
            raise RunnerError("actual_mode")
    elif namespace not in (io.TEST_NAMESPACE, io.PREFLIGHT_NAMESPACE) or mode not in (
        "full",
        "development-failed",
        "coordinator-approval",
        "second-release",
        "late-close",
    ):
        raise RunnerError("test_mode")
    from scripts.research import signal_calendar_score_runner_service as service

    context = mp.get_context("spawn")
    coord_request, helper_request = context.Pipe(duplex=True)
    reviewer_approval, helper_approval = context.Pipe(duplex=True)
    parent_control, coord_control = context.Pipe(duplex=True)
    parent_boot, helper_boot = context.Pipe(duplex=True)
    coordinator = context.Process(target=_run_coordinator, args=(coord_request, coord_control))
    helper = context.Process(
        target=service.run_reviewer_service, args=(helper_request, helper_approval, helper_boot)
    )
    failure: BaseException | None = None
    result: dict[str, Any] | None = None
    binding = phase.current_binding()
    review_tokens: dict[str, _StageToken] = {}
    session: _Session | None = None
    captured_registry: Path | None = None
    retirement_started: float | None = None

    def preflight_guard() -> None:
        if _preflight_deadline is not None:
            _remaining_preflight(_preflight_deadline, CONTROL_ALLOWANCE)

    try:
        if actual and (
            cast(_Readiness, readiness).source != binding or phase.current_binding() != binding
        ):
            raise RunnerError("readiness_source")
        coordinator.start()
        coord_request.close()
        coord_control.close()
        control = _bootstrap_owned(
            parent_control,
            coordinator,
            secrets.token_hex(32),
            {
                "case": case,
                "mode": mode,
                "namespace": namespace,
                "source_review_digest": binding.manifest_digest,
                **(
                    {"preflight_deadline": _preflight_deadline}
                    if namespace == io.PREFLIGHT_NAMESPACE
                    else {}
                ),
            },
        )
        ready = _receive_owned(
            control,
            coordinator,
            _remaining_preflight(_preflight_deadline, CONTROL_ALLOWANCE if actual else 15.0),
            binding,
            _guard=preflight_guard,
        )
        if (
            set(ready) != {"state", "registry", "session_id", "reservation_digest"}
            or ready["state"] != "RESERVED"
        ):
            raise RunnerError(f"reservation_reply:{ready}")
        registry = Path(ready["registry"])
        expected_registry = (
            _actual_registry()
            if actual
            else phase.TEST_ANCHOR / "attempts" / hashlib.sha256(case.encode()).hexdigest()
        )
        if registry != expected_registry:
            raise RunnerError("reservation_root")
        captured_registry = registry
        session = _adopt_reviewer_view(registry)
        if (
            session._session_id != ready["session_id"]
            or phase._hash(session._reservation) != ready["reservation_digest"]
        ):
            raise RunnerError("reservation_binding")
        helper.start()
        helper_request.close()
        helper_approval.close()
        helper_boot.close()
        helper_identity, coordinator_identity = (
            _process_identity(helper),
            _process_identity(coordinator),
        )
        session._peers = (coordinator_identity, helper_identity)
        secret, review_secret, challenge = (
            secrets.token_bytes(32),
            secrets.token_bytes(32),
            secrets.token_hex(32),
        )
        phase._record(
            registry,
            "attempt-registration.json",
            {
                "schema": 1,
                "state": "COORDINATOR_REGISTERED",
                "namespace": io.EXPERIMENT_NAMESPACE if actual else io.TEST_NAMESPACE,
                "attempt_id": io.PROTOCOL_SHA256 if actual else registry.name,
                "session_id": session._session_id,
                "coordinator": asdict(coordinator_identity),
                "reviewer": asdict(session._owner),
                "helper": asdict(helper_identity),
                "source_binding": asdict(binding),
                "reservation_digest": phase._hash(session._reservation),
                "source_review_digest": binding.manifest_digest,
            },
        )
        parent_boot.send_bytes(
            io.canonical_json(
                {
                    "utc": phase._utc(),
                    "registry": str(registry),
                    "coordinator": asdict(coordinator_identity),
                    "reviewer": asdict(session._owner),
                    "helper": asdict(helper_identity),
                    "source_binding": asdict(binding),
                    "source_review_digest": binding.manifest_digest,
                    "session_id": session._session_id,
                    "challenge": challenge,
                    "coordinator_secret": secret.hex(),
                    "reviewer_secret": review_secret.hex(),
                    "namespace": io.EXPERIMENT_NAMESPACE if actual else io.TEST_NAMESPACE,
                }
            )
        )
        review = channels.FrameChannel(
            reviewer_approval,
            review_secret,
            "reviewer",
            session._session_id,
            challenge,
            session._owner,
            helper_identity,
            binding,
        )
        control.send(
            {
                "helper": asdict(helper_identity),
                "coordinator_secret": secret.hex(),
                "challenge": challenge,
            }
        )
        while True:
            event = _receive_owned(
                control,
                coordinator,
                (
                    io.PHASE_DEADLINES["validation"]
                    + io.load_operational_resources().effective_verifier_seconds
                    + 600.0
                )
                if actual
                else (CONTROL_ALLOWANCE if namespace == io.PREFLIGHT_NAMESPACE else 30.0),
                binding,
                _guard=preflight_guard,
            )
            if event.get("state") == "REVIEW_REQUIRED":
                name = event.get("phase")
                if name not in io.PHASE_REPLICATES or event.get("root") != str(registry / name):
                    raise RunnerError("reviewer_path")
                token = _timed_owned_stage(session, registry / name, "verifier", "reviewer")
                session._token(token, _StageToken)
                review_tokens[name] = token
                control.send(
                    {"state": "REVIEW_FINISHED", "phase": name, "timing": session._measurements[-1]}
                )
            elif event.get("state") == "APPROVAL_REQUESTED":
                name = event.get("phase")
                if name not in io.PHASE_REPLICATES:
                    raise RunnerError("reviewer_phase")
                expected_decision = (
                    review_tokens[name].evidence.decision
                    if actual
                    else (
                        "TEST_FAILED"
                        if mode == "development-failed" and name == "development"
                        else "TEST_PASS"
                    )
                )
                if event != {
                    "state": "APPROVAL_REQUESTED",
                    "phase": name,
                    "decision": expected_decision,
                }:
                    raise RunnerError("reviewer_decision")
                evidence = service._evidence_check(registry, name, binding)
                _check_live_review(session, review_tokens.get(name), evidence)
                review.send(
                    {
                        "action": "approve-" + name,
                        "evidence": evidence,
                        "source_review_digest": binding.manifest_digest,
                        "control_decision": expected_decision,
                    }
                )
                approved = _receive_owned(
                    review, helper, 600.0 if actual else 15.0, binding, _guard=preflight_guard
                )
                if set(approved) != {"state", "approval_digest"} or approved["state"] != "APPROVED":
                    raise RunnerError("reviewer_reply")
                if (
                    type(approved["approval_digest"]) is not str
                    or re.fullmatch("[a-f0-9]{64}", approved["approval_digest"]) is None
                ):
                    raise RunnerError("reviewer_reply")
                session._approval_receipts[name] = approved["approval_digest"]
                control.send({"state": "APPROVED", "phase": name})
            elif event.get("state") in ("FINAL_VERDICT", "DEVELOPMENT_FAILED", "ERROR"):
                result = event
                retirement_started = time.perf_counter()
                break
            else:
                raise RunnerError("coordinator_result")
        coordinator.join(timeout=_remaining_preflight(_preflight_deadline, 5.0))
        helper.join(timeout=_remaining_preflight(_preflight_deadline, 5.0))
        if coordinator.is_alive() or helper.is_alive():
            raise RunnerError("process_shutdown")
        if result["state"] != "ERROR" and (coordinator.exitcode != 0 or helper.exitcode != 0):
            raise RunnerError("process_exit")
        if result["state"] != "ERROR":
            session._retired_peers = True
        result["children_exited"] = True
        result["registry"] = str(registry)
    except BaseException as error:
        failure = error
        if session is not None:
            session.fail(error)
        elif captured_registry is not None:
            try:
                phase._record(
                    captured_registry,
                    "attempt-failure.json",
                    {
                        "schema": 1,
                        "state": "ERROR",
                        "source_binding": asdict(binding),
                        "namespace": namespace,
                        "error": f"{type(error).__name__}:{error}",
                        "residual": "UNKNOWN_INCOMPLETE",
                        "study_permission": False,
                    },
                )
            except BaseException as secondary:
                error.add_note(f"Launcher evidence: {type(secondary).__name__}")
        raise
    finally:
        try:
            life._shutdown(
                [
                    lambda: life._stop_process(coordinator),
                    lambda: life._stop_process(helper),
                    coord_request.close,
                    helper_request.close,
                    reviewer_approval.close,
                    helper_approval.close,
                    parent_control.close,
                    coord_control.close,
                    parent_boot.close,
                    helper_boot.close,
                ],
                failure,
            )
        except BaseException as error:
            if session is not None:
                session.fail(error)
            raise
    assert result is not None and session is not None
    retirement_ended = time.perf_counter()
    if result["state"] == "ERROR":
        return result
    try:
        _final_pipeline_guard(session, result, review_tokens)
        candidate = phase._read_bytes(
            session.registry / "attempt-result-candidate.json", session.registry, io.MAX_RECORD
        )
        phase._record(session.registry, "attempt-result-prepared.json", phase._decode(candidate))
        prepared = session.registry / "attempt-result-prepared.json"
        if phase._read_bytes(prepared, session.registry, io.MAX_RECORD) != candidate:
            raise RunnerError("overall_candidate_changed")
        _final_pipeline_guard(session, result, review_tokens)
        # The exclusive publication is the last fallible success operation.
        assert retirement_started is not None
        fixed = _issue_fixed_observation(
            session._binding,
            case,
            str(session.registry),
            "pipeline-retirement",
            retirement_started,
            retirement_ended,
        )
        _PIPELINE_COSTS[case] = fixed
        os.link(prepared, session.registry / "attempt-result.json", follow_symlinks=False)
        return result
    except BaseException as error:
        session.fail(error)
        raise


def _check_live_review(
    session: _Session, token: _StageToken | None, evidence: dict[str, Any]
) -> None:
    session._token(token, _StageToken)
    if token is None or token.proof.kind != "verifier" or token.proof.role != "reviewer":
        raise RunnerError("live_review")
    owned = token.evidence
    expected = {
        "binding": json.loads(owned.binding),
        "decision": owned.decision,
        "counts": asdict(
            phase.Progress(owned.paths, owned.metrics, owned.words, owned.payload_bytes, 0)
        ),
        "payload_digest": owned.payload_digest,
        "index_digest": owned.index_digest,
        "report_digest": owned.report_digest,
        "terminal_digest": owned.terminal_digest,
        "reviewer_receipt_digest": owned.receipt_digest,
    }
    if io.canonical_json({k: evidence[k] for k in expected}) != io.canonical_json(expected):
        raise RunnerError("live_review_binding")


@dataclass(frozen=True, slots=True)
class _ReviewToken:
    evidence: bytes
    approval: bytes
    owner: life.ProcessIdentity
    reviewer: life.ProcessIdentity
    helper: life.ProcessIdentity | None
    scope: str


def _test_review_token(session: _Session, root: Path, token: _StageToken) -> _ReviewToken:
    if session._namespace != io.TEST_NAMESPACE:
        raise RunnerError("test_domain")
    from scripts.research import signal_calendar_score_runner_service as service

    session._check()
    current = service._evidence_check(session.registry, root.name, session._binding)
    _check_live_review(session, token, current)
    review = _ReviewToken(
        io.canonical_json(current), b"", session._owner, session._owner, None, "PRIVATE_TEST_REVIEW"
    )
    session._tokens[id(review)] = review
    return review


def _check_primary(session: _Session, token: _StageToken, current: dict[str, Any]) -> None:
    session._token(token, _StageToken)
    if token.proof.kind != "verifier" or token.proof.role != "primary":
        raise RunnerError("primary_token")
    evidence = token.evidence
    expected = {
        "binding": json.loads(evidence.binding),
        "decision": evidence.decision,
        "counts": asdict(
            phase.Progress(
                evidence.paths, evidence.metrics, evidence.words, evidence.payload_bytes, 0
            )
        ),
        "payload_digest": evidence.payload_digest,
        "index_digest": evidence.index_digest,
        "report_digest": evidence.report_digest,
        "terminal_digest": evidence.terminal_digest,
        "primary_receipt_digest": evidence.receipt_digest,
    }
    if io.canonical_json({k: current[k] for k in expected}) != io.canonical_json(expected):
        raise RunnerError("primary_binding")


def _cleanup_phase(
    session: _Session, root: Path, primary: _StageToken, review: _ReviewToken
) -> None:
    from scripts.research import signal_calendar_score_runner_service as service

    if _SESSIONS.get(id(session)) is not session:
        raise RunnerError("session_issuer")
    captured_registry, captured_binding = session._capture[4], session._capture[2]
    error_root = (
        root
        if root.parent == captured_registry and root.name in io.PHASE_REPLICATES
        else captured_registry
    )
    raw = root / "phase-payload.bin"
    attempted = session._cleanup_attempted
    error_status = "UNKNOWN"
    try:
        session._check()
        if session.state not in (life.State.FINAL_VERDICT, life.State.DEVELOPMENT_FAILED):
            raise RunnerError("cleanup_state")
        if (
            root in attempted
            or root.parent != session.registry
            or root.name not in io.PHASE_REPLICATES
        ):
            raise RunnerError("cleanup_once_or_root")
        attempted.add(root)
        session._token(primary, _StageToken)
        session._token(review, _ReviewToken)
        current = service._evidence_check(session.registry, root.name, session._binding)
        _check_primary(session, primary, current)
        if review.owner != session._owner or review.evidence != io.canonical_json(current):
            raise RunnerError("review_binding")
        if review.helper is None:
            if session._namespace != io.TEST_NAMESPACE or review.scope != "PRIVATE_TEST_REVIEW":
                raise RunnerError("review_issuer")
        elif not review.helper.alive() or not review.reviewer.alive():
            raise RunnerError("review_lifetime")
        claim = phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
        plan, _value = phase.validate_claim(root, claim, session._binding)
        guarded = io._guard_path(raw, root, existing=True)
        before = guarded.stat()
        identity = phase._identity(before)
        intent = {
            "schema": 1,
            "state": "CLEANUP_INTENT",
            "scope": plan.scope,
            "binding": current["binding"],
            "raw_name": raw.name,
            "raw_digest": current["payload_digest"],
            "raw_identity": list(identity),
            "primary_receipt_digest": current["primary_receipt_digest"],
            "reviewer_receipt_digest": current["reviewer_receipt_digest"],
            "approval_digest": phase._hash(review.approval) if review.approval else None,
        }
        phase._record(root, "phase-cleanup-intent.json", intent, plan=plan)
        if service._hash_checked(
            root, raw.name, plan.payload_bytes, plan.payload_bytes, session._binding, session._check
        ) != current["payload_digest"] or (phase._identity(guarded.stat()) != identity):
            raise RunnerError("cleanup_raw_drift")
        session._check()
        io._guard_path(raw, root, existing=True).unlink()
        error_status = "ABSENT"
        if io._guard_path(raw, root).exists():
            raise RunnerError("cleanup_absence")
        complete = {
            "schema": 1,
            "state": "CLEANUP_COMPLETE",
            "scope": plan.scope,
            "binding": current["binding"],
            "raw_name": raw.name,
            "raw_digest": current["payload_digest"],
            "raw_status": "ABSENT",
            "intent_digest": phase._hash(
                phase._read_bytes(root / "phase-cleanup-intent.json", root, io.MAX_RECORD)
            ),
        }
        name = "phase-cleanup-complete-candidate.json"
        phase._record(root, name, complete, plan=plan)
        blob = phase._read_bytes(root / name, root, io.MAX_RECORD)
        parsed = phase._decode(blob)
        if blob != io.canonical_json({"utc": parsed["utc"], **complete}):
            raise RunnerError("cleanup_candidate_drift")
        session._check()
        phase._storage(
            root, plan, 0, (root / "phase-index.jsonl").stat().st_size, added_control=len(blob)
        )
        if io._guard_path(raw, root).exists():
            raise RunnerError("cleanup_absence")
        destination = io._guard_path(root / "phase-cleanup-complete.json", root)
        os.link(root / name, destination, follow_symlinks=False)
    except BaseException as error:
        try:
            if error_status != "ABSENT":
                error_status = "PRESENT" if io._guard_path(raw, root).exists() else "ABSENT"
            phase._record(
                error_root,
                "phase-cleanup-error.json",
                {
                    "schema": 1,
                    "state": "ERROR",
                    "raw_name": raw.name,
                    "raw_status": error_status,
                    "error": f"{type(error).__name__}:{error}",
                    "source_binding": asdict(captured_binding),
                },
            )
        except BaseException as secondary:
            error.add_note(f"Cleanup evidence: {type(secondary).__name__}")
        session.fail(error)
        raise


@dataclass(frozen=True, slots=True)
class _CoordinatorRegistration:
    coordinator: life.ProcessIdentity
    reviewer: life.ProcessIdentity
    source: phase.SourceBinding
    reviewed_manifest: str


@dataclass(frozen=True, slots=True)
class _Readiness:
    owner: life.ProcessIdentity
    source: phase.SourceBinding
    cases: tuple[str, str, str]
    measurements: bytes
    group_projection: bytes = b""


_COORDINATORS: dict[int, _CoordinatorRegistration] = {}
_READINESS: dict[int, _Readiness] = {}
_READINESS_CONSUMED: set[int] = set()


def _actual_registry() -> Path:
    return io.EXPERIMENT_ROOT / "attempts" / io.PROTOCOL_SHA256


def _required_initial_free() -> int:
    return io.FREE_RESERVE + sum(io.PHASE_BOUNDED_ESTIMATES.values()) + 2 * io.PATH_METADATA_CAP


def _check_readiness(token: object) -> _Readiness:
    if (
        type(token) is not _Readiness
        or _READINESS.get(id(token)) is not token
        or id(token) in _READINESS_CONSUMED
    ):
        raise RunnerError("readiness_issuer")
    if token.owner != life.ProcessIdentity.current() or token.source != phase.current_binding():
        raise RunnerError("readiness_owner_or_source")
    if (
        len(set(token.cases)) != 3
        or psutil.disk_usage(str(io.PROJECT)).free < _required_initial_free()
    ):
        raise RunnerError("readiness_resources")
    _validate_readiness_measurements(token)
    return token


def _reserve_actual(marker: object) -> _Session:
    registered = _COORDINATORS.get(id(marker))
    if type(marker) is not _CoordinatorRegistration or registered is not marker:
        raise RunnerError("coordinator_issuer")
    if (
        _ROLE != "coordinator"
        or marker.coordinator != life.ProcessIdentity.current()
        or (
            not marker.reviewer.alive()
            or marker.source != phase.current_binding()
            or marker.reviewed_manifest != marker.source.manifest_digest
        )
    ):
        raise RunnerError("coordinator_registration")
    if psutil.disk_usage(str(io.PROJECT)).free < _required_initial_free():
        raise RunnerError("combined_disk_reserve")
    session = _Session(io.PROTOCOL_SHA256, _ISSUER)
    session._registry, session._namespace = _actual_registry(), io.EXPERIMENT_NAMESPACE
    session._capture = (
        session._case,
        session._owner,
        session._binding,
        session._session_id,
        session._registry,
        session._namespace,
    )
    io._guard_path(io.EXPERIMENT_ROOT, io.PROJECT)
    io.EXPERIMENT_ROOT.mkdir(parents=True, exist_ok=True)
    attempts = io.EXPERIMENT_ROOT / "attempts"
    io._guard_path(attempts, io.EXPERIMENT_ROOT)
    attempts.mkdir(exist_ok=True)
    registry = io._guard_path(_actual_registry(), attempts)
    try:
        registry.mkdir()
    except FileExistsError as error:
        raise RunnerError("attempt_exhausted") from error
    _SESSIONS[id(session)] = session
    try:
        manifest = phase.phase_manifest()
        if manifest.digest != marker.source.manifest_digest:
            raise RunnerError("source_drift")
        phase._record(
            registry,
            "attempt-reserved.json",
            {
                "schema": 1,
                "state": "ATTEMPT_RESERVED",
                "scope": "ARTIFICIAL_RESEARCH_ONLY",
                "namespace": io.EXPERIMENT_NAMESPACE,
                "case": io.PROTOCOL_SHA256,
                "attempt_id": io.PROTOCOL_SHA256,
                "session_id": session._session_id,
                "owner": asdict(session._owner),
                "reviewer": asdict(marker.reviewer),
                "source_binding": asdict(session._binding),
                "manifest": manifest.payload,
                "phase_counts": {p: list(io.phase_totals(p)) for p in io.PHASE_REPLICATES},
                "worker_seconds": dict(io.PHASE_DEADLINES),
                "verifier_seconds": io.load_operational_resources().effective_verifier_seconds,
                "session_seconds": SESSION_LIMIT,
                "session_started_monotonic": session._session_anchor,
                "phase_seed": None,
                "combined_free_required": _required_initial_free(),
                "observed_free": psutil.disk_usage(str(registry)).free,
            },
        )
        session._reservation = phase._read_bytes(
            registry / "attempt-reserved.json", registry, io.MAX_RECORD
        )
        _record_trial(session)
        session._state = life.State.ATTEMPT_RESERVED
        return session
    except BaseException as error:
        session.fail(error)
        raise


def _claim_actual_phase(session: _Session, name: str, key: bytes, commitment: str) -> Path:
    if _SESSIONS.get(id(session)) is not session or session._namespace != io.EXPERIMENT_NAMESPACE:
        raise RunnerError("actual_session")
    try:
        session._check(
            life.State.VALIDATION_KEY_SEALED
            if name == "development"
            else life.State.VALIDATION_AUTHORIZED
        )
        if (
            name not in io.PHASE_REPLICATES
            or type(key) is not bytes
            or len(key) != 32
            or (type(commitment) is not str or phase._hash(key) != commitment)
        ):
            raise RunnerError("phase_seed")
        plan = phase.actual_plan(name)
        if (
            psutil.disk_usage(str(session.registry)).free
            < io.FREE_RESERVE + io.PHASE_BOUNDED_ESTIMATES[name] + io.PATH_METADATA_CAP
        ):
            raise RunnerError("phase_disk_reserve")
        root = io._guard_path(session.registry / name, session.registry)
        root.mkdir()
        manifest = phase.phase_manifest()
        if manifest.digest != session._binding.manifest_digest:
            raise RunnerError("source_drift")
        claim = {
            "schema": 1,
            "utc": phase._utc(),
            "coordinator": asdict(session._owner),
            "scope": plan.scope,
            "namespace": plan.namespace,
            "phase": name,
            "plan": asdict(plan),
            "source_binding": asdict(session._binding),
            "manifest": manifest.payload,
            "attempt_id": io.PROTOCOL_SHA256,
            "session_id": session._session_id,
            "root": key.hex(),
            "seed_commitment": commitment,
            "origin": "operator/runner",
        }
        phase._record(root, "phase-claim.json", claim, plan=plan)
        session._check()
        session._state = (
            life.State.DEVELOPMENT_CLAIMED
            if name == "development"
            else life.State.VALIDATION_CLAIMED
        )
        return root
    except BaseException as error:
        session.fail(error)
        raise


def _read_actual_registration(
    registry: Path, source: phase.SourceBinding, *, _fixture: bool = False
) -> dict[str, Any]:
    if (_fixture and registry.parent != phase.TEST_ANCHOR / "attempts") or (
        not _fixture and registry != _actual_registry()
    ):
        raise RunnerError("actual_root")
    reservation_blob = phase._read_bytes(
        registry / "attempt-reserved.json", registry, io.MAX_RECORD
    )
    reservation = phase._decode(reservation_blob)
    original_reservation_digest = phase._hash(reservation_blob)
    original_reservation = dict(reservation)
    if _fixture:
        _remaining_preflight(reservation.pop("preflight_deadline", None), CONTROL_ALLOWANCE)
        if (
            reservation["namespace"] != io.TEST_NAMESPACE
            or reservation["attempt_id"] != registry.name
        ):
            raise RunnerError("fixture_registration")
        # Read-only namespace shadow exercises the same consuming schema/cost.
        # It issues no marker, stream capability or experimental identity.
        reservation.update(
            namespace=io.EXPERIMENT_NAMESPACE,
            scope="ARTIFICIAL_RESEARCH_ONLY",
            case=io.PROTOCOL_SHA256,
            attempt_id=io.PROTOCOL_SHA256,
        )
        reservation_blob = io.canonical_json(reservation)
    expected_reservation_keys = {
        "utc",
        "schema",
        "state",
        "scope",
        "namespace",
        "case",
        "attempt_id",
        "session_id",
        "owner",
        "reviewer",
        "source_binding",
        "manifest",
        "phase_counts",
        "worker_seconds",
        "verifier_seconds",
        "session_seconds",
        "session_started_monotonic",
        "phase_seed",
        "combined_free_required",
        "observed_free",
    }
    if (
        set(reservation) != expected_reservation_keys
        or type(reservation["schema"]) is not int
        or (
            reservation["schema"] != 1
            or reservation["state"] != "ATTEMPT_RESERVED"
            or reservation["scope"] != "ARTIFICIAL_RESEARCH_ONLY"
            or reservation["case"] != io.PROTOCOL_SHA256
            or type(reservation["session_id"]) is not str
            or re.fullmatch("[a-f0-9]{64}", reservation["session_id"]) is None
            or type(reservation["combined_free_required"]) is not int
            or reservation["combined_free_required"] != _required_initial_free()
            or type(reservation["observed_free"]) is not int
            or reservation["observed_free"] < reservation["combined_free_required"]
            or type(reservation["session_started_monotonic"]) is not float
            or not 0
            <= time.perf_counter() - reservation["session_started_monotonic"]
            <= SESSION_LIMIT
        )
    ):
        raise RunnerError("reservation_schema")
    _validate_trial(registry, original_reservation, original_reservation_digest)
    registration = phase._read_record(registry, "attempt-registration.json")
    if _fixture:
        if (
            registration["namespace"] != io.TEST_NAMESPACE
            or registration["attempt_id"] != registry.name
            or registration["reservation_digest"] != original_reservation_digest
        ):
            raise RunnerError("fixture_registration")
        registration.update(
            namespace=io.EXPERIMENT_NAMESPACE,
            attempt_id=io.PROTOCOL_SHA256,
            reservation_digest=phase._hash(reservation_blob),
        )
    expected_keys = {
        "schema",
        "utc",
        "state",
        "namespace",
        "attempt_id",
        "session_id",
        "coordinator",
        "reviewer",
        "helper",
        "source_binding",
        "reservation_digest",
        "source_review_digest",
    }
    if (
        set(registration) != expected_keys
        or type(registration["schema"]) is not int
        or (
            registration["schema"] != 1
            or registration["state"] != "COORDINATOR_REGISTERED"
            or registration["namespace"] != io.EXPERIMENT_NAMESPACE
            or registration["attempt_id"] != io.PROTOCOL_SHA256
            or registration["reservation_digest"] != phase._hash(reservation_blob)
            or registration["session_id"] != reservation["session_id"]
            or registration["source_review_digest"] != source.manifest_digest
            or io.canonical_json(registration["source_binding"])
            != io.canonical_json(asdict(source))
            or io.canonical_json(registration["coordinator"])
            != io.canonical_json(reservation["owner"])
            or io.canonical_json(registration["reviewer"])
            != io.canonical_json(reservation["reviewer"])
        )
    ):
        raise RunnerError("registration_binding")
    if (
        len({io.canonical_json(registration[k]) for k in ("coordinator", "reviewer", "helper")})
        != 3
    ):
        raise RunnerError("registration_distinct")
    for key in ("coordinator", "reviewer", "helper"):
        if not channels._parse_identity(registration[key]).alive():
            raise RunnerError("registration_lifetime")
    if io._guard_path(registry / "attempt-failure.json", registry).exists() or (
        io._guard_path(registry / "service-failure.json", registry).exists()
    ):
        raise RunnerError("attempt_error")
    if reservation["namespace"] != io.EXPERIMENT_NAMESPACE or (
        reservation["attempt_id"] != io.PROTOCOL_SHA256
        or reservation["phase_seed"] is not None
        or io.canonical_json(reservation["phase_counts"])
        != io.canonical_json({p: list(io.phase_totals(p)) for p in io.PHASE_REPLICATES})
        or io.canonical_json(reservation["worker_seconds"])
        != io.canonical_json(dict(io.PHASE_DEADLINES))
        or type(reservation["verifier_seconds"]) is not int
        or reservation["verifier_seconds"]
        != io.load_operational_resources().effective_verifier_seconds
        or type(reservation["session_seconds"]) is not float
        or reservation["session_seconds"] != SESSION_LIMIT
        or io.canonical_json(reservation["source_binding"]) != io.canonical_json(asdict(source))
        or io.canonical_json(reservation["manifest"])
        != io.canonical_json(phase.phase_manifest().payload)
    ):
        raise RunnerError("reservation_binding")
    return registration


def _validate_actual_claim_impl(
    root: Path, value: dict[str, Any], owner: life.ProcessIdentity, *, _fixture: bool = False
) -> None:
    registration = _read_actual_registration(
        root.parent, phase.current_binding(), _fixture=_fixture
    )
    expected_registry = root.parent if _fixture else _actual_registry()
    expected_attempt = root.parent.name if _fixture else io.PROTOCOL_SHA256
    scope = "UNAVAILABLE_TEST_ONLY" if _fixture else "ARTIFICIAL_RESEARCH_ONLY"
    if (
        root != expected_registry / value["phase"]
        or value["attempt_id"] != expected_attempt
        or (
            value["session_id"] != registration["session_id"]
            or io.canonical_json(value["coordinator"])
            != io.canonical_json(registration["coordinator"])
            or asdict(owner) not in (registration["coordinator"], registration["reviewer"])
        )
    ):
        raise RunnerError("phase_registration")
    sealed = phase._read_record(root.parent, "validation-sealed.json")
    expected_seal = {
        "utc": sealed["utc"],
        "schema": 1,
        "state": "VALIDATION_KEY_SEALED",
        "namespace": io.TEST_NAMESPACE if _fixture else io.EXPERIMENT_NAMESPACE,
        "scope": scope,
        "session_id": registration["session_id"],
        "source_binding": asdict(phase.current_binding()),
        "helper": registration["helper"],
        "commitment": sealed.get("commitment"),
    }
    if io.canonical_json(sealed) != io.canonical_json(expected_seal) or (
        type(sealed.get("commitment")) is not str
        or re.fullmatch("[a-f0-9]{64}", sealed["commitment"]) is None
    ):
        raise RunnerError("seal_binding")
    if value["phase"] == "validation":
        from scripts.research import signal_calendar_score_runner_service as service

        source = phase.current_binding()
        evidence = service._evidence_check(root.parent, "development", source, _scan_payload=False)
        approval_blob = phase._read_bytes(
            root.parent / "development-reviewer-approved.json", root.parent, io.MAX_RECORD
        )
        approval = phase._decode(approval_blob)
        expected_approval = {
            "utc": approval["utc"],
            "schema": 1,
            "state": "REVIEW_APPROVED",
            "scope": scope,
            "action": "approve-development",
            "evidence": evidence,
            "control_decision": "TEST_PASS" if _fixture else "PASS",
            "source_review_digest": source.manifest_digest,
            "reviewer": registration["reviewer"],
            "helper": registration["helper"],
        }
        released = phase._read_record(root.parent, "validation-released.json")
        expected_release = {
            "utc": released["utc"],
            "schema": 1,
            "state": "VALIDATION_AUTHORIZED",
            "scope": scope,
            "session_id": registration["session_id"],
            "source_binding": asdict(source),
            "evidence": evidence,
            "approval_digest": phase._hash(approval_blob),
            "commitment": sealed["commitment"],
            "helper": registration["helper"],
        }
        if io.canonical_json(approval) != io.canonical_json(expected_approval) or (
            io.canonical_json(released) != io.canonical_json(expected_release)
            or (not _fixture and evidence["decision"] != "PASS")
            or sealed["commitment"] != value["seed_commitment"]
        ):
            raise RunnerError("release_binding")
        development = phase._read_record(root.parent / "development", "phase-claim.json")
        if (
            development["root"] == value["root"]
            or development["seed_commitment"] == value["seed_commitment"]
        ):
            raise RunnerError("phase_seed_distinct")
    elif value["seed_commitment"] == sealed["commitment"]:
        raise RunnerError("phase_seed_distinct")


def _run_test_pipeline(case: str, *, mode: str = "full") -> dict[str, object]:
    return _launch_pipeline(case, mode=mode)


def _review_token_from_owned_reply(
    session: _Session,
    root: Path,
    primary: _StageToken,
    approval: dict[str, Any],
    reviewer: life.ProcessIdentity,
) -> _ReviewToken:
    from scripts.research import signal_calendar_score_runner_service as service

    session._check()
    if session._channel is None or not session._channel.remote.alive() or not reviewer.alive():
        raise RunnerError("review_lifetime")
    current = service._evidence_check(session.registry, root.name, session._binding)
    _check_primary(session, primary, current)
    expected = {
        "action": "approve-" + root.name,
        "evidence": current,
        "source_review_digest": session._binding.manifest_digest,
        "control_decision": current["decision"]
        if session._namespace == io.EXPERIMENT_NAMESPACE
        else approval.get("control_decision"),
        "reviewer": asdict(reviewer),
        "helper": asdict(session._channel.remote),
        "scope": "ARTIFICIAL_RESEARCH_ONLY"
        if session._namespace == io.EXPERIMENT_NAMESPACE
        else "UNAVAILABLE_TEST_ONLY",
        "state": "REVIEW_APPROVED",
        "schema": 1,
    }
    if set(approval) != set(expected) | {"approval_digest"} or (
        io.canonical_json({k: approval[k] for k in expected}) != io.canonical_json(expected)
    ):
        raise RunnerError("review_reply")
    blob = phase._read_bytes(
        session.registry / (root.name + "-reviewer-approved.json"), session.registry, io.MAX_RECORD
    )
    if phase._hash(blob) != approval["approval_digest"]:
        raise RunnerError("review_receipt")
    token = _ReviewToken(
        io.canonical_json(current),
        io.canonical_json(approval),
        session._owner,
        reviewer,
        session._channel.remote,
        expected["scope"],
    )
    session._tokens[id(token)] = token
    return token


def _final_pipeline_guard(
    session: _Session, result: dict[str, Any], tokens: dict[str, _StageToken]
) -> None:
    session._check()
    candidate = phase._read_record(session.registry, "attempt-result-candidate.json")
    expected = {k: v for k, v in result.items() if k not in ("registry", "children_exited")}
    expected.update(
        {
            "schema": 1,
            "scope": "ARTIFICIAL_RESEARCH_ONLY"
            if session._namespace == io.EXPERIMENT_NAMESPACE
            else "UNAVAILABLE_TEST_ONLY",
            "source_binding": asdict(session._binding),
            "session_id": session._session_id,
            "utc": candidate["utc"],
        }
    )
    if io.canonical_json(candidate) != io.canonical_json(expected):
        raise RunnerError("overall_result_binding")
    expected_phases = (
        {"development"}
        if result["state"] == "DEVELOPMENT_FAILED"
        else {"development", "validation"}
    )
    if (
        result["state"] not in ("FINAL_VERDICT", "DEVELOPMENT_FAILED")
        or set(tokens) != expected_phases
        or set(session._approval_receipts) != expected_phases
    ):
        raise RunnerError("overall_result_state")
    from scripts.research import signal_calendar_score_runner_service as service

    for name, token in tokens.items():
        session._token(token, _StageToken)
        root = session.registry / name
        claim_blob = phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
        plan, _claim = phase.validate_claim(root, claim_blob, session._binding)
        if phase._hash(claim_blob) != json.loads(token.evidence.binding)["claim_digest"] or (
            io.canonical_json([result.get(name + "_paths"), result.get(name + "_metrics")])
            != io.canonical_json([plan.paths, plan.metrics])
        ):
            raise RunnerError("overall_phase_counts_or_claim")
        current = service._evidence_check(
            session.registry, name, session._binding, session._check, _scan_payload=False
        )
        _check_live_review(session, token, current)
        approval_blob = phase._read_bytes(
            root.parent / (name + "-reviewer-approved.json"), root.parent, io.MAX_RECORD
        )
        approval = phase._decode(approval_blob)
        if phase._hash(approval_blob) != session._approval_receipts[name] or io.canonical_json(
            approval["evidence"]
        ) != io.canonical_json(current):
            raise RunnerError("overall_approval_changed")
        index_size = (root / "phase-index.jsonl").stat().st_size
        if (
            service._hash_checked(
                root,
                "phase-index.jsonl",
                plan.paths * plan.metadata_cap + io.MAX_RECORD,
                index_size,
                session._binding,
                session._check,
            )
            != token.evidence.index_digest
        ):
            raise RunnerError("overall_index_changed")
        for filename, digest in (
            ("phase-terminal.json", token.evidence.terminal_digest),
            ("phase-report.json", token.evidence.report_digest),
            ("verified-reviewer.json", token.evidence.receipt_digest),
        ):
            if phase._hash(phase._read_bytes(root / filename, root, io.MAX_RECORD)) != digest:
                raise RunnerError("overall_evidence_changed")
        if session._namespace == io.EXPERIMENT_NAMESPACE:
            cleaned = phase._read_record(root, "phase-cleanup-complete.json")
            intent_blob = phase._read_bytes(root / "phase-cleanup-intent.json", root, io.MAX_RECORD)
            expected_cleanup = {
                "utc": cleaned["utc"],
                "schema": 1,
                "state": "CLEANUP_COMPLETE",
                "scope": plan.scope,
                "binding": current["binding"],
                "raw_name": "phase-payload.bin",
                "raw_digest": current["payload_digest"],
                "raw_status": "ABSENT",
                "intent_digest": phase._hash(intent_blob),
            }
            if (root / "phase-payload.bin").exists() or io.canonical_json(
                cleaned
            ) != io.canonical_json(expected_cleanup):
                raise RunnerError("overall_cleanup")
    if (
        psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
        or psutil.disk_usage(str(session.registry)).free < io.FREE_RESERVE
    ):
        raise RunnerError("overall_resources")
    session._check()


def _timed_owned_stage(session: _Session, root: Path, kind: str, role: str) -> _StageToken:
    started = time.perf_counter()
    try:
        token = _run_owned_stage(session, root, kind, role)
        _check_parent_observation(session, root, token.proof)
        ended = time.perf_counter()
        value = {
            "schema": 1,
            "phase": root.name,
            "kind": kind,
            "role": role,
            "started_monotonic": started,
            "ended_monotonic": ended,
            "elapsed": ended - started,
            "fixed_seconds": token.proof.observation.ready_monotonic - started,
            "repetitive_seconds": ended - token.proof.observation.ready_monotonic,
            "observation": asdict(token.proof.observation),
            "operational_costs": _operational_stage_costs(token.proof, started, ended),
            "source_binding": asdict(session._binding),
            "counts": asdict(
                phase.Progress(
                    token.evidence.paths,
                    token.evidence.metrics,
                    token.evidence.words,
                    token.evidence.payload_bytes,
                    0,
                )
            ),
            "samples": json.loads(token.proof.samples),
            "accounting_persistence_excluded": True,
        }
        if value["elapsed"] > _stage_limit(
            phase._claim_plan(phase._read_record(root, "phase-claim.json")), kind
        ):
            raise RunnerError("outer_stage_deadline")
        _validate_stage_measurement(value, session._binding)
        phase._record(
            root,
            f"stage-timing-{kind}-{role}.json",
            value,
            plan=phase._claim_plan(phase._read_record(root, "phase-claim.json")),
        )
        session._measurements.append(value)
        return token
    except BaseException as error:
        session.fail(error)
        raise


def _validate_stage_measurement(value: Any, source: phase.SourceBinding) -> None:
    keys = {
        "schema",
        "phase",
        "kind",
        "role",
        "started_monotonic",
        "ended_monotonic",
        "elapsed",
        "fixed_seconds",
        "repetitive_seconds",
        "observation",
        "operational_costs",
        "source_binding",
        "counts",
        "samples",
        "accounting_persistence_excluded",
    }
    if (
        type(value) is not dict
        or set(value) != keys
        or type(value["schema"]) is not int
        or value["schema"] != 1
    ):
        raise RunnerError("measurement_schema")
    if value["phase"] not in io.PHASE_REPLICATES or (value["kind"], value["role"]) not in (
        ("writer", "primary"),
        ("verifier", "primary"),
        ("verifier", "reviewer"),
    ):
        raise RunnerError("measurement_role")
    if any(
        type(value[k]) is not float or not math.isfinite(value[k]) or value[k] < 0
        for k in ("started_monotonic", "ended_monotonic", "elapsed")
    ) or (
        value["ended_monotonic"] - value["started_monotonic"] != value["elapsed"]
        or value["elapsed"] <= 0
        or value["accounting_persistence_excluded"] is not True
        or io.canonical_json(value["source_binding"]) != io.canonical_json(asdict(source))
    ):
        raise RunnerError("measurement_clock_or_source")
    _validate_observation_clock(value, source)
    _validate_operational_stage_costs(value)
    counts = value["counts"]
    if (
        type(counts) is not dict
        or set(counts) != set(phase.Progress.__dataclass_fields__)
        or any(type(v) is not int or not 0 <= v < 1 << 64 for v in counts.values())
        or counts["active_words"] != 0
    ):
        raise RunnerError("measurement_counts")
    sample = value["samples"]
    if (
        type(sample) is not dict
        or set(sample)
        != {"count", "parent_rss_peak", "tree_rss_peak", "free_min", "heartbeat_age_max"}
        or (
            any(
                type(sample[k]) is not int or sample[k] < 0
                for k in ("count", "parent_rss_peak", "tree_rss_peak", "free_min")
            )
            or sample["count"] < 1
            or sample["parent_rss_peak"] > io.PARENT_RSS_CAP
            or sample["tree_rss_peak"] > io.WORKER_RSS_CAP
            or sample["free_min"] < io.FREE_RESERVE
            or type(sample["heartbeat_age_max"]) is not float
            or not 0 <= sample["heartbeat_age_max"] <= 30.0
        )
    ):
        raise RunnerError("measurement_samples")


def _integrated_projection(stages: dict[str, float], whole_seconds: float) -> dict[str, Any]:
    if (
        type(stages) is not dict
        or set(stages) != {"writer", "primary", "reviewer"}
        or any(type(v) is not float or not math.isfinite(v) or v <= 0 for v in stages.values())
        or (
            type(whole_seconds) is not float
            or not math.isfinite(whole_seconds)
            or whole_seconds <= 0
        )
    ):
        raise RunnerError("measurement")
    resources = io.load_operational_resources()
    resource_blob = phase._read_bytes(io.RESOURCE_PATH, io.RESOURCE_PATH.parent, 16384)
    if phase._hash(resource_blob) != resources.resource_contract_sha256:
        raise RunnerError("measurement_resource_drift")
    prior_seconds = json.loads(resource_blob)["history"][1]["verifier_seconds"]
    phases: dict[str, Any] = {}
    eligible = True
    for name, replicates in io.PHASE_REPLICATES.items():
        phases[name] = {}
        for role, seconds in stages.items():
            projected = 2 * seconds * replicates
            comparisons = resources.compare(projected, projected)
            admitted = (
                projected <= io.PHASE_DEADLINES[name]
                if role == "writer"
                else comparisons["effective_" + name + "_eligible"]
            )
            phases[name][role] = {
                "projected_seconds": projected,
                "budget_ok": admitted,
                "legacy_12h": comparisons["legacy_" + name + "_eligible"],
                "prior_14h": projected <= prior_seconds,
                "effective_16h": comparisons["effective_" + name + "_eligible"],
            }
            eligible = eligible and admitted
    session_seconds = 2 * whole_seconds * sum(io.PHASE_REPLICATES.values())
    return {
        "eligible": eligible and session_seconds <= SESSION_LIMIT,
        "phases": phases,
        "session_projected_seconds": session_seconds,
        "session_budget_ok": session_seconds <= SESSION_LIMIT,
        "timing_model": "ALL_REPEATED_2X_NO_SUBTRACTION",
        "operational_resources": resources.binding(),
    }


@dataclass(frozen=True, slots=True)
class _PreflightMeasurement:
    owner: life.ProcessIdentity
    source: phase.SourceBinding
    case: str
    result: bytes


_PREFLIGHT_MEASUREMENTS: dict[str, _PreflightMeasurement] = {}


def _collect_readiness(reviewed_manifest: str) -> _Readiness | dict[str, Any]:
    if _ROLE != "reviewer" or reviewed_manifest != phase.current_binding().manifest_digest:
        raise RunnerError("reviewed_source")
    source = phase.current_binding()
    rows: list[dict[str, Any]] = []
    cases = tuple("ready-" + uuid.uuid4().hex for _ in range(3))
    for case in cases:
        run_integrated_preflight(case)
        live = _PREFLIGHT_MEASUREMENTS.get(case)
        if live is None or live.owner != life.ProcessIdentity.current() or live.source != source:
            raise RunnerError("measurement_issuer")
        rows.append(json.loads(live.result))
    if phase.current_binding() != source:
        raise RunnerError("readiness_source")
    if any(row.get("measurement_replicates") != _PREFLIGHT_REPLICATES for row in rows):
        raise RunnerError("measurement_replicates")
    group = _group_batch([row["operational_bounds"] for row in rows])
    if group["projection"]["eligible"] is not True:
        return {
            "state": "UNDRAWN_READINESS_BLOCKER",
            "namespace": io.PREFLIGHT_NAMESPACE,
            "study_permission": False,
            "attempt_reserved": False,
            "cases": list(cases),
            "source_binding": asdict(source),
            "reason": "ALL_THREE_GLOBAL_CONSERVATIVE_GATES_REQUIRED",
            "measurements": rows,
            "group_refinement": group,
            "historical_group_refinement": _group_refinement(
                [row["refinement_bounds"] for row in rows]
            ),
        }
    token = _Readiness(
        life.ProcessIdentity.current(),
        source,
        cast(tuple[str, str, str], cases),
        io.canonical_json(rows),
        io.canonical_json(group),
    )
    _READINESS[id(token)] = token
    return token


def _disk_probe(
    root: Path, binding: phase.SourceBinding, *, _guard: Callable[[], None] | None = None
) -> dict[str, Any]:
    if _guard is not None:
        _guard()
    io._guard_path(root, phase.TEST_ANCHOR / "preflights", existing=True)
    size = 32 << 20
    path = io._guard_path(root / "disk-probe.bin", root)
    started = time.perf_counter()
    block = hashlib.sha256(b"calendar-score-runner-PREFLIGHT-disk-probe").digest() * 2048
    digest = hashlib.sha256()
    stream = io._open_exclusive(path)
    failure: BaseException | None = None
    try:
        for offset in range(0, size, len(block)):
            io._write_all(stream, block)
            digest.update(block)
            if (offset + len(block)) % (16 << 20) == 0:
                if _guard is not None:
                    _guard()
                stream.flush()
                os.fsync(stream.fileno())
                if _guard is not None:
                    _guard()
                if phase.current_binding() != binding:
                    raise RunnerError("probe_source")
        stream.flush()
        os.fsync(stream.fileno())
    except BaseException as error:
        failure = error
        raise
    finally:
        life._shutdown([stream.close], failure)
    before = io._guard_path(path, root, existing=True).stat()
    for _ in range(2):
        if _probe_hash(root, path.name, size, binding, _guard) != digest.hexdigest():
            raise RunnerError("probe_digest")
    if phase._identity(path.stat()) != phase._identity(before):
        raise RunnerError("probe_drift")
    # Probe bytes are independently rehashed twice; phase raw remains retained.
    if _guard is not None:
        _guard()
    path.unlink()
    if path.exists():
        raise RunnerError("probe_cleanup")
    if _guard is not None:
        _guard()
    return {
        "bytes": size,
        "sha256": digest.hexdigest(),
        "elapsed": time.perf_counter() - started,
        "raw_status": "ABSENT",
    }


def _probe_hash(
    root: Path,
    name: str,
    size: int,
    source: phase.SourceBinding,
    guard: Callable[[], None] | None = None,
) -> str:
    from scripts.research import signal_calendar_score_runner_service as service

    return service._hash_checked(root, name, size, size, source, guard)


def _validate_fixture_authority(
    root: Path, value: dict[str, Any], source: phase.SourceBinding
) -> None:
    if (
        value["namespace"] not in (io.TEST_NAMESPACE, io.PREFLIGHT_NAMESPACE)
        or root.parent.parent != phase.TEST_ANCHOR / "attempts"
    ):
        raise RunnerError("fixture_authority")
    if source != phase.current_binding():
        raise RunnerError("fixture_source")
    shadow = dict(value)
    if value["phase"] == "validation":
        # Only the metadata identity is the fixed TEST control key. The payload
        # remains the public-zero-key TEST/PREFLIGHT stream declared in its claim.
        shadow["root"] = bytes([2]).hex() * 32
        shadow["seed_commitment"] = phase._hash(bytes([2]) * 32)
    _validate_actual_claim_impl(
        root, shadow, channels._parse_identity(value["coordinator"]), _fixture=True
    )


def _measure_integrated_preflight(case: str) -> dict[str, Any]:
    if _ROLE != "reviewer":
        raise RunnerError("reviewer_role")
    started = time.perf_counter()

    def outer_guard() -> None:
        _remaining_preflight(started + CONTROL_ALLOWANCE, CONTROL_ALLOWANCE)

    outer_guard()
    source = phase.current_binding()
    anchor = io._guard_path(phase.TEST_ANCHOR, io.PROJECT)
    anchor.mkdir(parents=True, exist_ok=True)
    parent = io._guard_path(anchor / "preflights", anchor)
    parent.mkdir(exist_ok=True)
    root = io._guard_path(parent / hashlib.sha256(case.encode()).hexdigest(), parent)
    try:
        root.mkdir()
    except FileExistsError as error:
        raise RunnerError("preflight_exhausted") from error
    try:
        manifest = phase.phase_manifest()
        if manifest.digest != source.manifest_digest:
            raise RunnerError("measurement_source")
        phase._record(
            root,
            "preflight-source-manifest.json",
            {
                "schema": 1,
                "source_binding": asdict(source),
                "manifest": manifest.payload,
            },
        )
        pipeline = _launch_pipeline(
            case, namespace=io.PREFLIGHT_NAMESPACE, _preflight_deadline=started + CONTROL_ALLOWANCE
        )
        outer_guard()
        if pipeline["state"] != "FINAL_VERDICT" or pipeline["study_permission"] is not False:
            raise RunnerError("measurement_pipeline")
        timings = pipeline["stage_timings"]
        if type(timings) is not list or len(timings) != 6:
            raise RunnerError("measurement_stages")
        stage_seconds = {"writer": 0.0, "primary": 0.0, "reviewer": 0.0}
        observed: set[tuple[str, str, str]] = set()
        for row in timings:
            _validate_stage_measurement(row, source)
            identity = row["phase"], row["kind"], row["role"]
            if identity in observed or io.canonical_json(row["counts"]) != io.canonical_json(
                asdict(phase.Progress(160, 448, 22223232, 3703872, 0))
            ):
                raise RunnerError("measurement_geometry_or_counts")
            observed.add(identity)
            role = "writer" if row["kind"] == "writer" else row["role"]
            stage_seconds[role] = max(stage_seconds[role], row["elapsed"])
        expected = {
            (p, k, r)
            for p in io.PHASE_REPLICATES
            for k, r in (("writer", "primary"), ("verifier", "primary"), ("verifier", "reviewer"))
        }
        if observed != expected:
            raise RunnerError("measurement_stages")
        if type(pipeline["registry"]) is not str:
            raise RunnerError("measurement_registry")
        registry = Path(pipeline["registry"])
        if registry != phase.TEST_ANCHOR / "attempts" / hashlib.sha256(case.encode()).hexdigest():
            raise RunnerError("measurement_registry")
        reservation = phase._read_record(registry, "attempt-reserved.json")
        if reservation["case"] != case or io.canonical_json(
            reservation["source_binding"]
        ) != io.canonical_json(asdict(source)):
            raise RunnerError("measurement_reservation")
        phase_rows: dict[str, Any] = {}
        from scripts.research import signal_calendar_score_runner_service as service

        for name in io.PHASE_REPLICATES:
            outer_guard()
            phase_root = registry / name
            claim = phase._read_record(phase_root, "phase-claim.json")
            plan = phase._claim_plan(claim)
            if (
                plan.namespace != io.PREFLIGHT_NAMESPACE
                or plan.replicates != _PREFLIGHT_REPLICATES
                or plan.geometries != phase.GEOMETRIES
                or claim["root"] != "0" * 64
            ):
                raise RunnerError("measurement_identity")
            index_blob = phase._read_bytes(
                phase_root / "phase-index.jsonl",
                phase_root,
                plan.paths * plan.metadata_cap + io.MAX_RECORD,
            )
            outer_guard()
            lines = index_blob.splitlines(keepends=True)
            if len(lines) != plan.paths + 1 or max(map(len, lines)) > io.PATH_METADATA_CAP:
                raise RunnerError("measurement_metadata")
            # Full helper/control evidence checks and two immediate raw scans
            # measure the terminal cleanup work without deleting retained paths.
            outer_guard()
            evidence = service._evidence_check(registry, name, source, outer_guard)
            for _ in range(2):
                if (
                    service._hash_checked(
                        phase_root,
                        "phase-payload.bin",
                        plan.payload_bytes,
                        plan.payload_bytes,
                        source,
                        outer_guard,
                    )
                    != evidence["payload_digest"]
                ):
                    raise RunnerError("measurement_raw")
                outer_guard()
            phase._record(
                phase_root,
                "preflight-cleanup-scan-candidate.json",
                {
                    "schema": 1,
                    "state": "READ_ONLY_CLEANUP_COST",
                    "scope": "UNAVAILABLE_TEST_ONLY",
                    "evidence": evidence,
                    "source_binding": asdict(source),
                },
                plan=plan,
            )
            outer_guard()
            phase_rows[name] = {
                "evidence": evidence,
                "index_bytes": len(index_blob),
                "max_metadata_bytes": max(map(len, lines)),
                "raw_status": "RETAINED",
            }
        probe_started = time.perf_counter()
        probe = _disk_probe(root, source, _guard=outer_guard)
        outer_guard()
        probe_ended = time.perf_counter()
        fixed_observations = (
            _PIPELINE_COSTS[case],
            _issue_fixed_observation(
                source, case, str(root), "disk-probe", probe_started, probe_ended
            ),
        )
        for fixed_observation in fixed_observations:
            _check_fixed_observation(fixed_observation, source, case)
        if fixed_observations[0].root != str(registry):
            raise RunnerError("fixed_observation_root")
        _validate_preflight_rows(registry, timings, source, started, time.perf_counter())
        if phase.current_binding() != source or time.perf_counter() - started > 600.0:
            raise RunnerError("measurement_final_guard")
        parent_rss = psutil.Process().memory_info().rss
        free = psutil.disk_usage(str(root)).free
        if parent_rss > io.PARENT_RSS_CAP or free < _required_initial_free():
            raise RunnerError("measurement_resources")
        ended = time.perf_counter()
        refinement = _account_refinement(timings, started, ended)
        operational_controls = [asdict(value) for value in fixed_observations]
        operational = _account_operational(timings, started, ended, operational_controls)
        result = {
            "schema": 1,
            "state": "INTEGRATED_PREFLIGHT_COMPLETE",
            "namespace": io.PREFLIGHT_NAMESPACE,
            "scope": "UNAVAILABLE_TEST_ONLY",
            "study_permission": False,
            "attempt_reserved": False,
            "case_id": case,
            "registry": str(registry),
            "source_binding": asdict(source),
            "started_monotonic": started,
            "ended_monotonic": ended,
            "whole_seconds": ended - started,
            "stage_timings": timings,
            "stage_seconds": stage_seconds,
            "phase_evidence": phase_rows,
            "disk_probe": probe,
            "final_resources": {"parent_rss": parent_rss, "free": free},
            "projection": _integrated_projection(stage_seconds, ended - started),
            "refinement_bounds": refinement,
            "refined_projection": _refined_projection(refinement),
            "operational_controls": operational_controls,
            "operational_bounds": operational,
            "operational_projection": _operational_projection(operational),
            "measurement_replicates": _PREFLIGHT_REPLICATES,
            "batch_projection": _batch_projection(operational, _PREFLIGHT_REPLICATES),
            "accounting_clock": _accounting_clock_binding(),
            "accounting_persistence_excluded": True,
            "raw_replay": "RETAINED_FOR_DUAL_EXTERNAL_CHECK",
            "authority_cost_scope": "READ_ONLY_TEST_NAMESPACE_SHADOWS_NO_ISSUANCE",
            "control_key": "FIXED_TEST_02_METADATA_ONLY",
            "payload_key": "PUBLIC_ZERO_PREFLIGHT",
            "observed_free_is_real": True,
        }
        phase._record(root, "preflight-result-candidate.json", result)
        blob = phase._read_bytes(root / "preflight-result-candidate.json", root, io.MAX_RECORD)
        if (
            blob != io.canonical_json({"utc": phase._decode(blob)["utc"], **result})
            or phase.current_binding() != source
        ):
            raise RunnerError("measurement_candidate_changed")
        live = _PreflightMeasurement(
            life.ProcessIdentity.current(), source, case, io.canonical_json(result)
        )
        if (
            psutil.Process().memory_info().rss > io.PARENT_RSS_CAP
            or psutil.disk_usage(str(root)).free < _required_initial_free()
            or time.perf_counter() - started > 600.0
        ):
            raise RunnerError("measurement_final_resources")
        _PREFLIGHT_MEASUREMENTS[case] = live
        os.link(
            root / "preflight-result-candidate.json",
            root / "preflight-result.json",
            follow_symlinks=False,
        )
        return result
    except BaseException as error:
        _PREFLIGHT_MEASUREMENTS.pop(case, None)
        try:
            phase._record(
                root,
                "preflight-failure.json",
                {
                    "schema": 1,
                    "state": "ERROR",
                    "scope": "UNAVAILABLE_TEST_ONLY",
                    "source_binding": asdict(source),
                    "error": f"{type(error).__name__}:{error}",
                    "attempt_reserved": False,
                },
            )
        except BaseException as secondary:
            error.add_note(f"Preflight evidence: {type(secondary).__name__}")
        raise


def _validate_preflight_rows(
    registry: Path,
    timings: list[dict[str, Any]],
    source: phase.SourceBinding,
    started: float,
    ended: float,
) -> None:
    reservation = phase._read_record(registry, "attempt-reserved.json")
    intervals: list[tuple[float, float]] = []
    for row in timings:
        _validate_stage_measurement(row, source)
        root = registry / row["phase"]
        saved = phase._read_record(root, f"stage-timing-{row['kind']}-{row['role']}.json")
        if io.canonical_json(saved) != io.canonical_json({"utc": saved["utc"], **row}):
            raise RunnerError("measurement_saved_timing")
        claim = phase._read_record(root, "phase-claim.json")
        if claim["session_id"] != reservation["session_id"] or claim["attempt_id"] != registry.name:
            raise RunnerError("measurement_session")
        record = phase._read_record(
            root,
            "phase-terminal.json" if row["kind"] == "writer" else f"verified-{row['role']}.json",
        )
        proof = record["completion"]
        owner = reservation["reviewer"] if row["role"] == "reviewer" else reservation["owner"]
        child = record["worker"] if row["kind"] == "writer" else record["verifier"]
        if (
            type(proof) is not dict
            or set(proof) != set(_StageProof.__dataclass_fields__)
            or (
                proof["kind"] != row["kind"]
                or proof["role"] != row["role"]
                or type(proof["elapsed"]) is not float
                or not 0 <= proof["elapsed"] <= row["elapsed"]
                or type(proof["exit_code"]) is not int
                or proof["exit_code"] != 0
                or proof["monitor_joined"] is not True
                or proof["durable_ack"] is not True
            )
        ):
            raise RunnerError("measurement_owned_proof")
        if io.canonical_json(proof["observation"]) != io.canonical_json(row["observation"]):
            raise RunnerError("measurement_parent_observation")
        if io.canonical_json(proof["work"]) != io.canonical_json(
            row["operational_costs"]["observation"]
        ):
            raise RunnerError("measurement_work_observation")
        observation = row["observation"]
        if (
            observation["root"] != str(root)
            or observation["session_id"] != reservation["session_id"]
            or observation["claim_digest"] != phase._hash(io.canonical_json(claim))
        ):
            raise RunnerError("measurement_parent_binding")
        if io.canonical_json(observation["owner"]) != io.canonical_json(owner) or (
            io.canonical_json(observation["child"]) != io.canonical_json(child)
        ):
            raise RunnerError("measurement_parent_binding")
        if io.canonical_json(proof["owner"]) != io.canonical_json(owner) or (
            io.canonical_json(proof["child"]) != io.canonical_json(child)
            or io.canonical_json(proof["samples"]) != io.canonical_json(row["samples"])
            or io.canonical_json(record["counts"]) != io.canonical_json(row["counts"])
        ):
            raise RunnerError("measurement_owned_binding")
        if not started <= row["started_monotonic"] < row["ended_monotonic"] <= ended:
            raise RunnerError("measurement_containment")
        intervals.append((row["started_monotonic"], row["ended_monotonic"]))
    intervals.sort()
    if any(left[1] > right[0] for left, right in pairwise(intervals)):
        raise RunnerError("measurement_overlap")


def _create_stage_process(session: _Session) -> tuple[Any, tuple[Connection, ...]]:
    endpoints: list[Connection] = []
    try:
        context = mp.get_context("spawn")
        for duplex in (True, False, False):
            endpoints.extend(context.Pipe(duplex=duplex))
        process = context.Process(
            target=_phase_worker, args=(endpoints[1], endpoints[3], endpoints[5], session._owner)
        )
        return process, tuple(endpoints)
    except BaseException as error:
        life._shutdown([endpoint.close for endpoint in endpoints], error)
        session.fail(error)
        raise


def _receive_coordinator_control(
    session: _Session, control: channels.FrameChannel, idle_seconds: float
) -> dict[str, Any]:
    session._control_deadline = time.perf_counter() + _remaining_preflight(
        session._preflight_deadline, idle_seconds
    )
    while not control.connection.poll(0.25):
        session._check()
    # Idle reviewer time may be long; an arrived incomplete frame gets only the
    # finite control allowance, enforced by the independent coordinator watchdog.
    session._control_deadline = time.perf_counter() + _remaining_preflight(
        session._preflight_deadline, CONTROL_ALLOWANCE
    )
    return control.receive()


def _record_trial(session: _Session) -> None:
    phase._record(
        session.registry,
        "attempt-trial.json",
        {
            "schema": 1,
            "state": "TRIAL_RESERVED",
            "origin": "operator/runner",
            "namespace": session._namespace,
            "attempt_id": session.registry.name,
            "session_id": session._session_id,
            "source_binding": asdict(session._binding),
            "reservation_digest": phase._hash(session._reservation),
            "evaluations_started": 0,
            "phase_counts": {p: list(io.phase_totals(p)) for p in io.PHASE_REPLICATES},
        },
    )


def _validate_readiness_measurements(token: _Readiness) -> None:
    try:
        rows = json.loads(token.measurements)
        if (
            type(rows) is not list
            or len(rows) != 3
            or io.canonical_json(rows) != token.measurements
        ):
            raise RunnerError("readiness_measurements")
        for case, row in zip(token.cases, rows, strict=True):
            live = _PREFLIGHT_MEASUREMENTS.get(case)
            if (
                live is None
                or live.owner != token.owner
                or live.source != token.source
                or live.case != case
                or live.result != io.canonical_json(row)
            ):
                raise RunnerError("readiness_measurements")
            expected = _integrated_projection(row["stage_seconds"], row["whole_seconds"])
            if (
                row["case_id"] != case
                or row["state"] != "INTEGRATED_PREFLIGHT_COMPLETE"
                or row["namespace"] != io.PREFLIGHT_NAMESPACE
                or row["attempt_reserved"] is not False
                or row["study_permission"] is not False
                or io.canonical_json(row["source_binding"])
                != io.canonical_json(asdict(token.source))
                or io.canonical_json(row["projection"]) != io.canonical_json(expected)
            ):
                raise RunnerError("readiness_measurements")
            bounds = _account_refinement(
                row["stage_timings"], row["started_monotonic"], row["ended_monotonic"]
            )
            if io.canonical_json(bounds) != io.canonical_json(
                row["refinement_bounds"]
            ) or io.canonical_json(_refined_projection(bounds)) != io.canonical_json(
                row["refined_projection"]
            ):
                raise RunnerError("readiness_measurements")
            operational = _account_operational(
                row["stage_timings"],
                row["started_monotonic"],
                row["ended_monotonic"],
                row["operational_controls"],
            )
            if io.canonical_json(operational) != io.canonical_json(row["operational_bounds"]) or (
                io.canonical_json(_operational_projection(operational))
                != io.canonical_json(row["operational_projection"])
            ):
                raise RunnerError("readiness_measurements")
            if type(row["measurement_replicates"]) is not int or (
                row["measurement_replicates"] != _PREFLIGHT_REPLICATES
                or io.canonical_json(row["batch_projection"])
                != io.canonical_json(_batch_projection(operational, row["measurement_replicates"]))
                or io.canonical_json(row["accounting_clock"])
                != io.canonical_json(_accounting_clock_binding())
            ):
                raise RunnerError("readiness_measurements")
        group = _group_batch([row["operational_bounds"] for row in rows])
        if (
            io.canonical_json(group) != token.group_projection
            or group["projection"]["eligible"] is not True
        ):
            raise RunnerError("readiness_global_group")
    except (KeyError, TypeError, ValueError) as error:
        raise RunnerError("readiness_measurements") from error


def _validate_trial(registry: Path, reservation: dict[str, Any], digest: str) -> None:
    trial = phase._read_record(registry, "attempt-trial.json")
    expected = {
        "utc": trial["utc"],
        "schema": 1,
        "state": "TRIAL_RESERVED",
        "origin": "operator/runner",
        "namespace": reservation["namespace"],
        "attempt_id": reservation["attempt_id"],
        "session_id": reservation["session_id"],
        "source_binding": reservation["source_binding"],
        "reservation_digest": digest,
        "evaluations_started": 0,
        "phase_counts": reservation["phase_counts"],
    }
    if io.canonical_json(trial) != io.canonical_json(expected):
        raise RunnerError("trial_binding")


@dataclass(frozen=True, slots=True)
class _ParentObservation:
    owner: life.ProcessIdentity
    child: life.ProcessIdentity
    source: phase.SourceBinding
    root: str
    session_id: str
    claim_digest: str
    kind: str
    role: str
    entry_monotonic: float
    ready_monotonic: float
    start_monotonic: float
    ready_counts: tuple[int, int, int, int, int]


_OBSERVATIONS: dict[int, _ParentObservation] = {}


@dataclass(frozen=True, slots=True)
class _WorkObservation:
    start: _ParentObservation
    finished_monotonic: float
    counts: phase.Progress
    scans: tuple[tuple[float, float], ...]


_WORK_OBSERVATIONS: dict[int, _WorkObservation] = {}


@dataclass(frozen=True, slots=True)
class _FixedObservation:
    owner: life.ProcessIdentity
    source: phase.SourceBinding
    case: str
    root: str
    kind: str
    started_monotonic: float
    ended_monotonic: float


_FIXED_OBSERVATIONS: dict[int, _FixedObservation] = {}
_PIPELINE_COSTS: dict[str, _FixedObservation] = {}


def _issue_fixed_observation(
    source: phase.SourceBinding,
    case: str,
    root: str,
    kind: str,
    started: float,
    ended: float,
) -> _FixedObservation:
    value = _FixedObservation(
        life.ProcessIdentity.current(), source, case, root, kind, started, ended
    )
    _FIXED_OBSERVATIONS[id(value)] = value
    return value


def _check_fixed_observation(
    value: _FixedObservation, source: phase.SourceBinding, case: str
) -> None:
    if _FIXED_OBSERVATIONS.get(id(value)) is not value or (
        value.owner != life.ProcessIdentity.current()
        or value.source != source
        or value.case != case
        or value.kind not in ("pipeline-retirement", "disk-probe")
        or not 0 <= value.started_monotonic < value.ended_monotonic <= time.perf_counter()
    ):
        raise RunnerError("fixed_observation_issuer")


def _issue_work_observation(
    start: _ParentObservation,
    finished: float,
    counts: phase.Progress,
    scans: tuple[tuple[float, float], ...],
) -> _WorkObservation:
    value = _WorkObservation(start, finished, counts, scans)
    _WORK_OBSERVATIONS[id(value)] = value
    return value


def _barrier_body(
    state: str,
    owner: life.ProcessIdentity,
    child: life.ProcessIdentity,
    source: phase.SourceBinding,
    root: Path,
    digest: str,
    kind: str,
    role: str,
) -> dict[str, Any]:
    return {
        "schema": 1,
        "state": state,
        "owner": asdict(owner),
        "child": asdict(child),
        "source_binding": asdict(source),
        "root": str(root),
        "claim_digest": digest,
        "kind": kind,
        "role": role,
        "counts": asdict(phase.Progress(0, 0, 0, 0, 0)),
    }


def _wait_for_stage_start(
    channel: channels.FrameChannel, marker: _WorkerRegistration, kind: str, role: str, fault: object
) -> None:
    ready = _barrier_body(
        "READY",
        marker.owner,
        marker.worker,
        marker.source,
        marker.root,
        marker.claim_digest,
        kind,
        role,
    )
    if fault == "setup-delay":
        time.sleep(0.2)
    if fault == "malformed-ready":
        ready["counts"]["active_words"] = 1
    if fault == "missing-ready":
        time.sleep(60.0)
    channel.send(ready)
    if fault == "duplicate-ready":
        channel.send(ready)
    expected = {**ready, "state": "START", "counts": asdict(phase.Progress(0, 0, 0, 0, 0))}
    received = channel.receive()
    if io.canonical_json(received) != io.canonical_json(expected):
        raise RunnerError("start_barrier")
    if not marker.owner.alive() or phase.current_binding() != marker.source:
        raise RunnerError("start_owner_or_source")
    if channel.connection.poll(0):
        raise RunnerError("duplicate_start")
    if fault == "work-delay":
        time.sleep(0.2)


def _check_worker_bootstrap(channel: channels.FrameChannel) -> None:
    if channel.connection.poll(0):
        raise RunnerError("duplicate_start")


def _retire_parent_bootstrap(
    connection: Connection, session: _Session, started: float, limit: float
) -> None:
    # Only called after exit0 and monitor join: no concurrent pipe reader remains.
    # EOF is the required retirement proof; any queued byte is a second barrier.
    while True:
        session._check()
        remaining = limit - (time.perf_counter() - started)
        if remaining <= 0:
            raise RunnerError("deadline")
        try:
            if not connection.poll(min(0.05, remaining)):
                continue
            connection.recv_bytes(io.MAX_RECORD)
        except EOFError:
            return
        except BrokenPipeError as error:
            # Windows poll reports closed named pipes as WinError 109.
            # This is accepted only after captured exit0 and monitor join.
            if getattr(error, "winerror", None) != 109:
                raise
            return
        raise RunnerError("duplicate_ready")


def _send_stage_start(channel: channels.FrameChannel, body: dict[str, Any]) -> None:
    channel.send(body)


def _start_stage(
    session: _Session,
    root: Path,
    claim: bytes,
    plan: phase.PhasePlan,
    kind: str,
    role: str,
    process: Any,
    channel: channels.FrameChannel,
    worker: life.ProcessIdentity,
    entry: float,
) -> _ParentObservation:
    remaining = _stage_limit(plan, kind) - (time.perf_counter() - entry)
    if remaining <= 0:
        raise RunnerError("ready_deadline")
    body = _receive_owned(
        channel, process, min(CONTROL_ALLOWANCE, remaining), session._binding, _guard=session._check
    )
    ready = time.perf_counter()
    expected = _barrier_body(
        "READY", session._owner, worker, session._binding, root, phase._hash(claim), kind, role
    )
    if io.canonical_json(body) != io.canonical_json(expected):
        raise RunnerError("ready_barrier")
    if channel.connection.poll(0):
        raise RunnerError("duplicate_ready")
    session._check()
    if time.perf_counter() - entry > _stage_limit(plan, kind):
        raise RunnerError("ready_deadline")
    start = time.perf_counter()
    _send_stage_start(channel, {**expected, "state": "START"})
    observation = _ParentObservation(
        session._owner,
        worker,
        session._binding,
        str(root),
        session._session_id,
        phase._hash(claim),
        kind,
        role,
        entry,
        ready,
        start,
        (0, 0, 0, 0, 0),
    )
    _OBSERVATIONS[id(observation)] = observation
    return observation


def _check_parent_observation(session: _Session, root: Path, proof: _StageProof) -> None:
    value = proof.observation
    if (
        _WORK_OBSERVATIONS.get(id(proof.work)) is not proof.work
        or proof.work.start is not value
        or not value.start_monotonic <= proof.work.finished_monotonic <= time.perf_counter()
        or _OBSERVATIONS.get(id(value)) is not value
        or value.owner != life.ProcessIdentity.current()
        or value.owner != proof.owner
        or value.child != proof.child
        or value.source != session._binding
        or value.root != str(root)
        or value.session_id != session._session_id
        or value.kind != proof.kind
        or value.role != proof.role
        or value.claim_digest
        != phase._hash(phase._read_bytes(root / "phase-claim.json", root, io.MAX_RECORD))
        or value.ready_counts != (0, 0, 0, 0, 0)
    ):
        raise RunnerError("parent_observation_issuer")


def _validate_observation_clock(row: dict[str, Any], source: phase.SourceBinding) -> None:
    value = row["observation"]
    if type(value) is not dict or set(value) != set(_ParentObservation.__dataclass_fields__):
        raise RunnerError("measurement_observation")
    for identity in ("owner", "child"):
        part = value[identity]
        if (
            type(part) is not dict
            or set(part) != {"pid", "creation_time_ns"}
            or any(type(v) is not int or v <= 0 for v in part.values())
        ):
            raise RunnerError("measurement_observation")
    for key in ("session_id", "claim_digest"):
        if type(value[key]) is not str or re.fullmatch("[a-f0-9]{64}", value[key]) is None:
            raise RunnerError("measurement_observation")
    if (
        type(value["root"]) is not str
        or value["kind"] != row["kind"]
        or value["role"] != row["role"]
        or io.canonical_json(value["source"]) != io.canonical_json(asdict(source))
        or io.canonical_json(value["ready_counts"]) != io.canonical_json([0, 0, 0, 0, 0])
    ):
        raise RunnerError("measurement_observation")
    for part, keys in (
        (value, ("entry_monotonic", "ready_monotonic", "start_monotonic")),
        (row, ("fixed_seconds", "repetitive_seconds")),
    ):
        if any(
            type(part[k]) is not float or not math.isfinite(part[k]) or part[k] < 0 for k in keys
        ):
            raise RunnerError("measurement_observation_clock")
    if (
        not row["started_monotonic"]
        <= value["entry_monotonic"]
        <= value["ready_monotonic"]
        <= value["start_monotonic"]
        < row["ended_monotonic"]
        or row["fixed_seconds"] != value["ready_monotonic"] - row["started_monotonic"]
        or row["repetitive_seconds"] != row["ended_monotonic"] - value["ready_monotonic"]
        or row["fixed_seconds"] + row["repetitive_seconds"] != row["elapsed"]
    ):
        raise RunnerError("measurement_observation_clock")


def _operational_stage_costs(proof: _StageProof, started: float, ended: float) -> dict[str, Any]:
    if _WORK_OBSERVATIONS.get(id(proof.work)) is not proof.work:
        raise RunnerError("work_observation_issuer")
    work = proof.work
    repetitive = (
        work.finished_monotonic
        - work.start.ready_monotonic
        + sum(right - left for left, right in work.scans)
    )
    return {
        "fixed_seconds": ended - started - repetitive,
        "repetitive_seconds": repetitive,
        "observation": asdict(work),
    }


def _validate_operational_stage_costs(row: dict[str, Any]) -> None:
    value = row["operational_costs"]
    if type(value) is not dict or set(value) != {
        "fixed_seconds",
        "repetitive_seconds",
        "observation",
    }:
        raise RunnerError("measurement_work_schema")
    work = value["observation"]
    if type(work) is not dict or set(work) != set(_WorkObservation.__dataclass_fields__):
        raise RunnerError("measurement_work_schema")
    if io.canonical_json(work["start"]) != io.canonical_json(row["observation"]):
        raise RunnerError("measurement_work_binding")
    finished = work["finished_monotonic"]
    if (
        type(finished) is not float
        or not math.isfinite(finished)
        or not (row["observation"]["start_monotonic"] <= finished < row["ended_monotonic"])
        or io.canonical_json(work["counts"]) != io.canonical_json(row["counts"])
    ):
        raise RunnerError("measurement_work_clock_or_counts")
    scans = work["scans"]
    if type(scans) not in (tuple, list) or len(scans) != 2:
        raise RunnerError("measurement_work_scans")
    for span in scans:
        if (
            type(span) not in (tuple, list)
            or len(span) != 2
            or any(type(v) is not float or not math.isfinite(v) for v in span)
            or not finished <= span[0] <= span[1] <= row["ended_monotonic"]
        ):
            raise RunnerError("measurement_work_scans")
    if scans[0][1] > scans[1][0]:
        raise RunnerError("measurement_work_scans")
    repetitive = (
        finished
        - row["observation"]["ready_monotonic"]
        + sum(right - left for left, right in scans)
    )
    if any(
        type(value[k]) is not float or not math.isfinite(value[k]) or value[k] < 0
        for k in ("fixed_seconds", "repetitive_seconds")
    ) or (
        value["repetitive_seconds"] != repetitive
        or value["fixed_seconds"] != row["elapsed"] - repetitive
        or value["fixed_seconds"] + repetitive != row["elapsed"]
    ):
        raise RunnerError("measurement_work_accounting")


def _validate_refinement_bounds(value: Any) -> None:
    if type(value) is not dict or set(value) != {"roles", "control_setup", "control_residual"}:
        raise RunnerError("refinement_bounds")
    if type(value["roles"]) is not dict or set(value["roles"]) != {"writer", "primary", "reviewer"}:
        raise RunnerError("refinement_bounds")
    scalars = [value["control_setup"], value["control_residual"]]
    for row in value["roles"].values():
        if type(row) is not dict or set(row) != {"fixed", "repetitive"}:
            raise RunnerError("refinement_bounds")
        scalars.extend(row.values())
        if type(row["repetitive"]) is not float or row["repetitive"] <= 0:
            raise RunnerError("refinement_bounds")
    if any(type(v) is not float or not math.isfinite(v) or v < 0 for v in scalars):
        raise RunnerError("refinement_bounds")


def _refined_projection(bounds: dict[str, Any]) -> dict[str, Any]:
    _validate_refinement_bounds(bounds)
    resources = io.load_operational_resources()
    resource_blob = phase._read_bytes(io.RESOURCE_PATH, io.RESOURCE_PATH.parent, 16384)
    if phase._hash(resource_blob) != resources.resource_contract_sha256:
        raise RunnerError("measurement_resource_drift")
    prior_seconds = json.loads(resource_blob)["history"][1]["verifier_seconds"]
    phases: dict[str, Any] = {}
    eligible = True
    for name, replicates in io.PHASE_REPLICATES.items():
        phases[name] = {}
        for role, cost in bounds["roles"].items():
            projected = 2 * (cost["fixed"] + replicates * cost["repetitive"])
            comparisons = resources.compare(projected, projected)
            admitted = (
                projected <= io.PHASE_DEADLINES[name]
                if role == "writer"
                else comparisons["effective_" + name + "_eligible"]
            )
            phases[name][role] = {
                "projected_seconds": projected,
                "budget_ok": admitted,
                "legacy_12h": comparisons["legacy_" + name + "_eligible"],
                "prior_14h": projected <= prior_seconds,
                "effective_16h": comparisons["effective_" + name + "_eligible"],
            }
            eligible = eligible and admitted
    session = 2 * (
        bounds["control_setup"]
        + sum(
            cost["fixed"] + replicates * cost["repetitive"]
            for replicates in io.PHASE_REPLICATES.values()
            for cost in bounds["roles"].values()
        )
        + max(io.PHASE_REPLICATES.values()) * bounds["control_residual"]
    )
    return {
        "eligible": eligible and session <= SESSION_LIMIT,
        "phases": phases,
        "session_projected_seconds": session,
        "session_budget_ok": session <= SESSION_LIMIT,
        "timing_model": "PARENT_READY_FIXED_ALL_POST_READY_REPEATED_2X",
        "operational_resources": resources.binding(),
    }


def _group_refinement(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if type(rows) is not list or len(rows) != 3:
        raise RunnerError("refinement_three_required")
    for value in rows:
        _validate_refinement_bounds(value)
    bounds = {
        "roles": {
            role: {k: max(row["roles"][role][k] for row in rows) for k in ("fixed", "repetitive")}
            for role in ("writer", "primary", "reviewer")
        },
        "control_setup": max(row["control_setup"] for row in rows),
        "control_residual": max(row["control_residual"] for row in rows),
    }
    return {"bounds": bounds, "projection": _refined_projection(bounds)}


def _account_refinement(
    timings: list[dict[str, Any]], started: float, ended: float
) -> dict[str, Any]:
    if (
        type(timings) is not list
        or len(timings) != 6
        or type(started) is not float
        or type(ended) is not float
        or not math.isfinite(started)
        or not math.isfinite(ended)
        or not started < ended
    ):
        raise RunnerError("refinement_intervals")
    expected = {
        (p, k, r)
        for p in io.PHASE_REPLICATES
        for k, r in (("writer", "primary"), ("verifier", "primary"), ("verifier", "reviewer"))
    }
    observed: set[tuple[str, str, str]] = set()
    for row in timings:
        keys = (
            "started_monotonic",
            "ended_monotonic",
            "elapsed",
            "fixed_seconds",
            "repetitive_seconds",
        )
        if (
            type(row) is not dict
            or any(
                k not in row or type(row[k]) is not float or not math.isfinite(row[k]) or row[k] < 0
                for k in keys
            )
            or any(k not in row for k in ("phase", "kind", "role"))
            or row["ended_monotonic"] - row["started_monotonic"] != row["elapsed"]
            or row["fixed_seconds"] + row["repetitive_seconds"] != row["elapsed"]
        ):
            raise RunnerError("refinement_intervals")
        observed.add((row["phase"], row["kind"], row["role"]))
    if observed != expected:
        raise RunnerError("refinement_intervals")
    intervals = sorted((row["started_monotonic"], row["ended_monotonic"]) for row in timings)
    if any(not started <= left < right <= ended for left, right in intervals) or any(
        left[1] > right[0] for left, right in pairwise(intervals)
    ):
        raise RunnerError("refinement_intervals")
    setup = intervals[0][0] - started
    owned = sum(row["elapsed"] for row in timings)
    residual = ended - started - setup - owned
    bounds = {
        "roles": {
            role: {
                "fixed": max(
                    row["fixed_seconds"]
                    for row in timings
                    if ("writer" if row["kind"] == "writer" else row["role"]) == role
                ),
                "repetitive": max(
                    row["repetitive_seconds"]
                    for row in timings
                    if ("writer" if row["kind"] == "writer" else row["role"]) == role
                ),
            }
            for role in ("writer", "primary", "reviewer")
        },
        "control_setup": setup,
        "control_residual": residual,
    }
    _validate_refinement_bounds(bounds)
    return bounds


def _account_operational(
    timings: list[dict[str, Any]],
    started: float,
    ended: float,
    controls: list[dict[str, Any]],
) -> dict[str, Any]:
    historical = _account_refinement(timings, started, ended)
    if (
        type(controls) is not list
        or len(controls) != 2
        or {row.get("kind") for row in controls if type(row) is dict}
        != {"pipeline-retirement", "disk-probe"}
    ):
        raise RunnerError("operational_control_intervals")
    intervals: list[tuple[float, float]] = []
    case = controls[0].get("case")
    if type(case) is not str or re.fullmatch("[A-Za-z0-9_-]{1,64}", case) is None:
        raise RunnerError("operational_control_binding")
    roots = {
        "pipeline-retirement": phase.TEST_ANCHOR
        / "attempts"
        / hashlib.sha256(case.encode()).hexdigest(),
        "disk-probe": phase.TEST_ANCHOR / "preflights" / hashlib.sha256(case.encode()).hexdigest(),
    }
    reviewer_owner = next(
        row["observation"]["owner"] for row in timings if row["role"] == "reviewer"
    )
    for row in controls:
        if type(row) is not dict or set(row) != set(_FixedObservation.__dataclass_fields__):
            raise RunnerError("operational_control_intervals")
        left, right = row["started_monotonic"], row["ended_monotonic"]
        if (
            row["case"] != case
            or row["root"] != str(roots[row["kind"]])
            or (
                io.canonical_json(row["source"]) != io.canonical_json(timings[0]["source_binding"])
                or io.canonical_json(row["owner"]) != io.canonical_json(reviewer_owner)
            )
        ):
            raise RunnerError("operational_control_binding")
        if (
            any(type(v) is not float or not math.isfinite(v) for v in (left, right))
            or not (max(stage["ended_monotonic"] for stage in timings) <= left < right <= ended)
            or any(
                left < stage["ended_monotonic"] and right > stage["started_monotonic"]
                for stage in timings
            )
        ):
            raise RunnerError("operational_control_intervals")
        intervals.append((left, right))
    intervals.sort()
    if intervals[0][1] > intervals[1][0]:
        raise RunnerError("operational_control_intervals")
    fixed_controls = sum(right - left for left, right in intervals)
    residual = historical["control_residual"] - fixed_controls
    for row in timings:
        _validate_operational_stage_costs(row)
    bounds = {
        "roles": {
            role: {
                key: max(
                    row["operational_costs"][key + "_seconds"]
                    for row in timings
                    if ("writer" if row["kind"] == "writer" else row["role"]) == role
                )
                for key in ("fixed", "repetitive")
            }
            for role in ("writer", "primary", "reviewer")
        },
        "control_setup": historical["control_setup"],
        "control_retirement": next(
            row["ended_monotonic"] - row["started_monotonic"]
            for row in controls
            if row["kind"] == "pipeline-retirement"
        ),
        "control_probe": next(
            row["ended_monotonic"] - row["started_monotonic"]
            for row in controls
            if row["kind"] == "disk-probe"
        ),
        "control_residual": residual,
    }
    _validate_operational_bounds(bounds)
    return bounds


def _operational_projection(bounds: dict[str, Any]) -> dict[str, Any]:
    _validate_operational_bounds(bounds)
    combined = {
        "roles": bounds["roles"],
        "control_setup": bounds["control_setup"]
        + bounds["control_retirement"]
        + bounds["control_probe"],
        "control_residual": bounds["control_residual"],
    }
    result = _refined_projection(combined)
    result["timing_model"] = "OWNED_WORK_SCANS_REPEATED_FIXED_RETIREMENT_PROBE_2X"
    return result


def _group_operational(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if type(rows) is not list or len(rows) != 3:
        raise RunnerError("refinement_three_required")
    for row in rows:
        _validate_operational_bounds(row)
    bounds = {
        "roles": {
            role: {
                key: max(row["roles"][role][key] for row in rows) for key in ("fixed", "repetitive")
            }
            for role in ("writer", "primary", "reviewer")
        },
        **{
            key: max(row[key] for row in rows)
            for key in ("control_setup", "control_retirement", "control_probe", "control_residual")
        },
    }
    return {"bounds": bounds, "projection": _operational_projection(bounds)}


def _validate_operational_bounds(bounds: Any) -> None:
    if (
        type(bounds) is not dict
        or set(bounds)
        != {"roles", "control_setup", "control_retirement", "control_probe", "control_residual"}
        or any(
            type(bounds[key]) is not float or not math.isfinite(bounds[key]) or bounds[key] < 0
            for key in ("control_retirement", "control_probe")
        )
    ):
        raise RunnerError("operational_bounds")
    _validate_refinement_bounds(
        {key: bounds[key] for key in ("roles", "control_setup", "control_residual")}
    )


def _accounting_clock_binding() -> dict[str, Any]:
    clock = time.get_clock_info("perf_counter")
    return {
        "name": "perf_counter",
        "implementation": clock.implementation,
        "resolution": clock.resolution,
        "monotonic": clock.monotonic,
        "adjustable": clock.adjustable,
    }


def _batch_projection(bounds: dict[str, Any], replicates: int) -> dict[str, Any]:
    _validate_operational_bounds(bounds)
    if (
        type(replicates) is not int
        or replicates != _PREFLIGHT_REPLICATES
        or any(count % replicates for count in io.PHASE_REPLICATES.values())
    ):
        raise RunnerError("measurement_replicates")
    scaled = {
        **bounds,
        "roles": {
            role: {"fixed": row["fixed"], "repetitive": row["repetitive"] / replicates}
            for role, row in bounds["roles"].items()
        },
        "control_residual": bounds["control_residual"] / replicates,
    }
    result = _operational_projection(scaled)
    result["timing_model"] = "SIXTEEN_COMPLETE_SETS_ALL_UNKNOWN_REPEATED_2X"
    result["measurement_replicates"] = replicates
    return result


def _group_batch(rows: list[dict[str, Any]]) -> dict[str, Any]:
    group = _group_operational(rows)
    return {
        "bounds": group["bounds"],
        "projection": _batch_projection(group["bounds"], _PREFLIGHT_REPLICATES),
    }
