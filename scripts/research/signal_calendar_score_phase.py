"""Bounded phase artifacts; public fixture and study authority stay separate."""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import stat
import weakref
from collections.abc import Callable, Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.research import signal_calendar_score_lifecycle as life
from scripts.research import signal_calendar_score_study as io
from scripts.research import signal_calendar_score_verify as reference


class PhaseError(io.StudyError):
    """A phase contract failed without granting authority."""


GEOMETRIES = tuple((s.profile_id, s.n, s.classes) for s in io.SPECS)
TEST_ANCHOR = io.PROJECT / "var/verification/2026-10-05/calendar-score-runner"


@dataclass(frozen=True, slots=True, weakref_slot=True)
class PhasePlan:
    namespace: str
    phase: str
    replicates: int
    geometries: tuple[tuple[str, int, int], ...]
    scope: str
    raw_cap: int
    metadata_cap: int
    overhead_cap: int

    @property
    def paths(self) -> int:
        return len(self.geometries) * self.replicates

    @property
    def metrics(self) -> int:
        return sum(len(io._metrics(io.spec(p))) for p, _, _ in self.geometries) * self.replicates

    @property
    def payload_bytes(self) -> int:
        return sum(io.source_length(io.spec(p)) for p, _, _ in self.geometries) * self.replicates


def actual_plan(phase: str) -> PhasePlan:
    if type(phase) is not str or phase not in io.PHASE_REPLICATES:
        raise PhaseError("phase")
    return PhasePlan(
        io.EXPERIMENT_NAMESPACE,
        phase,
        io.PHASE_REPLICATES[phase],
        GEOMETRIES,
        "ARTIFICIAL_PHASE",
        io.PHASE_CAPS[phase],
        io.PATH_METADATA_CAP,
        io.PHASE_RECORDS_CAP,
    )


_TEST_PLANS: weakref.WeakValueDictionary[int, PhasePlan] = weakref.WeakValueDictionary()


def _test_plan(phase: str, replicates: int = 1, *, preflight: bool = False) -> PhasePlan:
    if type(phase) is not str or phase not in io.PHASE_REPLICATES:
        raise PhaseError("phase")
    if type(replicates) is not int or not 1 <= replicates <= 32768:
        raise PhaseError("test_count")
    plan = PhasePlan(
        io.PREFLIGHT_NAMESPACE if preflight else io.TEST_NAMESPACE,
        phase,
        replicates,
        GEOMETRIES,
        "UNAVAILABLE_TEST_ONLY",
        io.PHASE_CAPS[phase],
        io.PATH_METADATA_CAP,
        io.PHASE_RECORDS_CAP,
    )
    _TEST_PLANS[id(plan)] = plan
    return plan


def _validate_plan(plan: PhasePlan) -> None:
    if (
        type(plan) is not PhasePlan
        or any(type(getattr(plan, name)) is not str for name in ("namespace", "phase", "scope"))
        or any(
            type(getattr(plan, name)) is not int or getattr(plan, name) <= 0
            for name in ("replicates", "raw_cap", "metadata_cap", "overhead_cap")
        )
    ):
        raise PhaseError("plan")
    if type(plan.geometries) is not tuple or any(
        type(row) is not tuple
        or len(row) != 3
        or type(row[0]) is not str
        or type(row[1]) is not int
        or type(row[2]) is not int
        for row in plan.geometries
    ):
        raise PhaseError("plan")
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        if io.canonical_json(asdict(plan)) != io.canonical_json(asdict(actual_plan(plan.phase))):
            raise PhaseError("plan")
    elif _TEST_PLANS.get(id(plan)) is not plan:
        raise PhaseError("test_plan_issuer")


def iter_paths(plan: PhasePlan) -> Iterator[tuple[str, int, int]]:
    _validate_plan(plan)
    for profile_id, n, _ in plan.geometries:
        for replicate in range(plan.replicates):
            yield profile_id, n, replicate


def _hash(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


SourceBinding = life.SourceBinding
EXTRA_SOURCES = (
    *life.EXTRA_SOURCES,
    "scripts/research/signal_calendar_score_phase.py",
    "tests/unit/test_signal_calendar_score_phase_research.py",
    "scripts/research/signal_calendar_score_runner.py",
    "scripts/research/signal_calendar_score_runner_service.py",
    "tests/unit/test_signal_calendar_score_runner_research.py",
    "tests/unit/test_signal_calendar_score_runner_preflight_research.py",
    "docs/plans/2026-10-05-calendar-score-full-runner.md",
    "docs/reviews/2026-10-05-calendar-score-full-runner-timing-refinement.md",
    "docs/plans/2026-10-06-runner-cost-accounting-amendment.md",
    "docs/plans/2026-10-06-runner-batch-measurement-amendment.md",
)


def phase_manifest() -> io.Manifest:
    paths = {p: io.PROJECT / p for p in (*io.SOURCE_PATHS, *EXTRA_SOURCES)}
    io._check_protocol_documents(paths)
    return io.manifest_for_paths(paths, protocol_hash=io.PROTOCOL_SHA256)


def current_binding() -> SourceBinding:
    manifest = phase_manifest()
    resources = manifest.payload["operational_resources"]
    return SourceBinding(
        io.PROTOCOL_SHA256,
        manifest.digest,
        resources["resource_contract_id"],
        resources["resource_contract_sha256"],
    )


def _identity(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_bytes(path: Path, root: Path, cap: int) -> bytes:
    guarded = io._guard_path(path, root, existing=True)
    before = guarded.stat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > cap:
        raise PhaseError("bounded_regular_read")
    with guarded.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        blob = stream.read(cap + 1)
    after = guarded.stat()
    if (
        len(blob) > cap
        or len(blob) != before.st_size
        or not (_identity(before) == _identity(opened) == _identity(after))
    ):
        raise PhaseError("file_drift")
    return blob


def _utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _check_utc(value: object) -> None:
    if type(value) is not str:
        raise PhaseError("utc")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if (
            stamp.tzinfo is None
            or stamp.utcoffset() != timedelta(0)
            or (stamp.isoformat(timespec="seconds").replace("+00:00", "Z") != value)
        ):
            raise PhaseError("utc")
    except ValueError as error:
        raise PhaseError("utc") from error


def _decode(blob: bytes) -> dict[str, Any]:
    try:
        value = json.loads(blob)
        if type(value) is not dict or io.canonical_json(value) != blob:
            raise PhaseError("noncanonical")
        _check_utc(value.get("utc"))
        return value
    except (ValueError, UnicodeError, TypeError) as error:
        raise PhaseError("noncanonical") from error


def _record(root: Path, name: str, value: dict[str, Any], *, plan: PhasePlan | None = None) -> str:
    value = {"utc": _utc(), **value}
    _check_utc(value["utc"])
    blob = io.canonical_json(value)
    if len(blob) > io.MAX_RECORD:
        raise PhaseError("record_cap")
    if plan is not None:
        raw = root / "phase-payload.bin"
        index = root / "phase-index.jsonl"
        _storage(
            root,
            plan,
            raw.stat().st_size if raw.exists() else 0,
            index.stat().st_size if index.exists() else 0,
            added_control=len(blob),
        )
    io._exclusive_record(root / name, value, root=root)
    return _hash(blob)


def _read_record(root: Path, name: str) -> dict[str, Any]:
    return _decode(_read_bytes(root / name, root, io.MAX_RECORD))


def _claim_plan(value: dict[str, Any]) -> PhasePlan:
    phase = value.get("phase")
    namespace = value.get("namespace")
    if type(phase) is not str:
        raise PhaseError("phase")
    if namespace == io.EXPERIMENT_NAMESPACE:
        plan = actual_plan(phase)
    elif type(namespace) is str and namespace in (io.TEST_NAMESPACE, io.PREFLIGHT_NAMESPACE):
        data = value.get("plan")
        if type(data) is not dict:
            raise PhaseError("plan")
        replicates = data.get("replicates")
        if type(replicates) is not int:
            raise PhaseError("test_count")
        plan = _test_plan(phase, replicates, preflight=namespace == io.PREFLIGHT_NAMESPACE)
    else:
        raise PhaseError("namespace")
    if io.canonical_json(value.get("plan")) != io.canonical_json(asdict(plan)):
        raise PhaseError("plan")
    return plan


def validate_claim(
    root: Path, claim: bytes, binding: SourceBinding
) -> tuple[PhasePlan, dict[str, Any]]:
    if type(claim) is not bytes or len(claim) > io.MAX_RECORD or type(binding) is not SourceBinding:
        raise PhaseError("claim")
    value = _decode(claim)
    plan = _claim_plan(value)
    required = {
        "schema",
        "utc",
        "coordinator",
        "scope",
        "namespace",
        "phase",
        "plan",
        "source_binding",
        "manifest",
        "attempt_id",
        "session_id",
        "root",
        "seed_commitment",
        "origin",
    }
    if set(value) != required or type(value["schema"]) is not int or value["schema"] != 1:
        raise PhaseError("claim_schema")
    coordinator = value["coordinator"]
    if not life.ProcessIdentity.valid_fields(coordinator):
        raise PhaseError("coordinator")
    if value["scope"] != plan.scope or value["origin"] != "operator/runner":
        raise PhaseError("claim_scope")
    for key in ("attempt_id", "session_id", "root", "seed_commitment"):
        v = value[key]
        if type(v) is not str or len(v) != 64 or any(c not in "0123456789abcdef" for c in v):
            raise PhaseError("claim_identity")
    if _hash(bytes.fromhex(value["root"])) != value["seed_commitment"]:
        raise PhaseError("seed_commitment")
    if plan.namespace != io.EXPERIMENT_NAMESPACE and value["root"] != "0" * 64:
        raise PhaseError("public_test_key")
    anchor = io.EXPERIMENT_ROOT / "attempts" / io.PROTOCOL_SHA256
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        if root != anchor / plan.phase or value["attempt_id"] != io.PROTOCOL_SHA256:
            raise PhaseError("actual_root")
    else:
        anchor = TEST_ANCHOR
    io._guard_path(root, anchor, existing=True)
    if _read_bytes(root / "phase-claim.json", root, io.MAX_RECORD) != claim:
        raise PhaseError("claim_drift")
    manifest = phase_manifest()
    expected_binding = SourceBinding(
        io.PROTOCOL_SHA256,
        manifest.digest,
        manifest.payload["operational_resources"]["resource_contract_id"],
        manifest.payload["operational_resources"]["resource_contract_sha256"],
    )
    if binding != expected_binding or (
        io.canonical_json(value["source_binding"]) != io.canonical_json(asdict(binding))
        or io.canonical_json(value["manifest"]) != io.canonical_json(manifest.payload)
    ):
        raise PhaseError("source_drift")
    return plan, value


def _prepare_test_claim(
    root: Path, plan: PhasePlan, *, attempt_id: str | None = None, session_id: str | None = None
) -> bytes:
    _validate_plan(plan)
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        raise PhaseError("test_domain")
    io._guard_path(root, TEST_ANCHOR, existing=True)
    manifest = phase_manifest()
    resources = manifest.payload["operational_resources"]
    binding = SourceBinding(
        io.PROTOCOL_SHA256,
        manifest.digest,
        resources["resource_contract_id"],
        resources["resource_contract_sha256"],
    )
    value = {
        "schema": 1,
        "utc": _utc(),
        "coordinator": asdict(life.ProcessIdentity.current()),
        "scope": plan.scope,
        "namespace": plan.namespace,
        "phase": plan.phase,
        "plan": asdict(plan),
        "source_binding": asdict(binding),
        "manifest": manifest.payload,
        "attempt_id": _hash(str(root).encode()) if attempt_id is None else attempt_id,
        "session_id": _hash(str(root).encode() + b"/session") if session_id is None else session_id,
        "root": "0" * 64,
        "seed_commitment": _hash(bytes(32)),
        "origin": "operator/runner",
    }
    _record(root, "phase-claim.json", value, plan=plan)
    return io.canonical_json(value)


@dataclass(frozen=True, slots=True)
class _PhaseCapability:
    claim_digest: str
    owner: life.ProcessIdentity


@dataclass(slots=True)
class _CapabilityState:
    capability: _PhaseCapability
    root: Path
    claim: bytes
    plan: PhasePlan
    binding: SourceBinding
    expected: Iterator[tuple[str, int, int]]
    valid: bool = True


_CAPABILITIES: dict[int, _CapabilityState] = {}


def _test_capability(root: Path, claim: bytes) -> _PhaseCapability:
    binding = current_binding()
    plan, _ = validate_claim(root, claim, binding)
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        raise PhaseError("test_domain")
    capability = _PhaseCapability(_hash(claim), life.ProcessIdentity.current())
    _CAPABILITIES[id(capability)] = _CapabilityState(
        capability, root, claim, plan, binding, iter_paths(plan)
    )
    return capability


def _capability(capability: object) -> _CapabilityState:
    state = _CAPABILITIES.get(id(capability))
    if state is None or state.capability is not capability or not state.valid:
        raise PhaseError("capability_issuer")
    if state.capability.owner != life.ProcessIdentity.current():
        state.valid = False
        raise PhaseError("capability_owner")
    return state


def _take_identity(capability: object, identity: tuple[str, int, int]) -> _CapabilityState:
    state = _capability(capability)
    try:
        validate_claim(state.root, state.claim, state.binding)
        if next(state.expected, None) != identity:
            raise PhaseError("stream_order")
        return state
    except BaseException:
        state.valid = False
        raise


def _revoke(capability: object) -> None:
    state = _CAPABILITIES.get(id(capability))
    if state is not None and state.capability is capability:
        state.valid = False


def _authorize_stream(capability: object, identity: dict[str, Any]) -> None:
    try:
        state = _capability(capability)
        plan, claim = state.plan, _decode(state.claim)
        required = {"namespace", "phase", "profile_id", "n", "replicate", "root"}
        if (
            set(identity) != required
            or any(type(identity[k]) is not str for k in ("namespace", "phase", "profile_id"))
            or type(identity["n"]) is not int
            or type(identity["replicate"]) is not int
        ):
            raise PhaseError("stream_identity")
        expected = {
            "namespace": plan.namespace,
            "phase": plan.phase
            if plan.namespace == io.EXPERIMENT_NAMESPACE
            else ("test_preflight" if plan.namespace == io.PREFLIGHT_NAMESPACE else "test_fixture"),
            "profile_id": identity["profile_id"],
            "n": identity["n"],
            "replicate": identity["replicate"],
            "root": bytes.fromhex(claim["root"]),
        }
        if type(identity["root"]) is not bytes or identity != expected:
            raise PhaseError("stream_identity")
        _take_identity(capability, (identity["profile_id"], identity["n"], identity["replicate"]))
    except BaseException:
        _revoke(capability)
        raise


@dataclass(frozen=True, slots=True)
class Progress:
    paths: int
    metrics: int
    words: int
    payload_bytes: int
    active_words: int


@dataclass(frozen=True, slots=True)
class PhaseEvidence:
    binding: bytes
    summary: bytes
    decision: str
    paths: int
    metrics: int
    words: int
    payload_bytes: int
    payload_digest: str
    index_digest: str
    report_digest: str
    terminal_digest: str
    receipt_digest: str = ""


def _binding(claim: dict[str, Any], claim_digest: str) -> dict[str, Any]:
    return {
        "source_binding": claim["source_binding"],
        "attempt_id": claim["attempt_id"],
        "session_id": claim["session_id"],
        "phase": claim["phase"],
        "seed_commitment": claim["seed_commitment"],
        "claim_digest": claim_digest,
    }


def _decision(plan: PhasePlan, summary: dict[str, Any]) -> str:
    decision = (
        "UNAVAILABLE_TEST_ONLY"
        if plan.namespace != io.EXPERIMENT_NAMESPACE
        else reference.phase_decision(summary, plan.phase)
    )
    summary["phase_verdict"] = decision
    return decision


def _failure(
    root: Path, claim: dict[str, Any], error: BaseException, counts: Progress, role: str
) -> None:
    try:
        _record(
            root,
            f"phase-{role}-failure.json",
            {
                "schema": 1,
                "state": "ERROR",
                "binding": _binding(claim, _hash(io.canonical_json(claim))),
                "error": f"{type(error).__name__}:{error}",
                "completed": asdict(counts),
                "active_residual": "COOPERATIVE_OBSERVED",
                "origin": "operator/runner",
            },
        )
    except BaseException as secondary:
        error.add_note(f"failure persistence: {secondary}")


def _storage(root: Path, plan: PhasePlan, raw: int, index: int, *, added_control: int = 0) -> None:
    _validate_plan(plan)
    compact = added_control
    for entry in root.iterdir():
        guarded = io._guard_path(entry, root, existing=True)
        info = guarded.stat()
        if not stat.S_ISREG(info.st_mode):
            raise PhaseError("nonregular")
        if entry.name not in ("phase-payload.bin", "phase-index.jsonl"):
            compact += info.st_size
    if compact > plan.overhead_cap or raw + index + compact > plan.raw_cap:
        raise PhaseError("phase_cap")


def write_phase(
    root: Path,
    claim: bytes,
    capability: object,
    progress: Callable[[Progress], None],
) -> PhaseEvidence:
    try:
        state = _capability(capability)
        if state.root != root or state.claim != claim:
            raise PhaseError("capability_claim")
        plan, value = validate_claim(root, claim, state.binding)
    except BaseException:
        _revoke(capability)
        raise
    claim_digest = _hash(claim)
    summary = reference._cells()
    counts = Progress(0, 0, 0, 0, 0)
    payload_stream: Any = None
    writer: io.CanonicalRecordWriter | None = None
    failure: BaseException | None = None
    stream: io.CounterStream | None = None
    payload_hasher = hashlib.sha256()
    try:
        _record(
            root,
            "phase-start.json",
            {
                "schema": 1,
                "state": "INERT_PHASE_STARTED",
                "binding": _binding(value, claim_digest),
                "worker": asdict(life.ProcessIdentity.current()),
                "counts": asdict(counts),
            },
            plan=plan,
        )
        _record(
            root,
            "phase-trial.json",
            {
                "schema": 1,
                "origin": "operator/runner",
                "binding": _binding(value, claim_digest),
                "planned_paths": plan.paths,
                "planned_metrics": plan.metrics,
                "observations": "phase-index.jsonl",
                "failure": "phase-writer-failure.json",
            },
            plan=plan,
        )
        payload_stream = io._open_exclusive(root / "phase-payload.bin")
        writer = io.CanonicalRecordWriter(
            root / "phase-index.jsonl",
            total_cap=plan.paths * plan.metadata_cap + io.MAX_RECORD,
            record_cap=plan.metadata_cap,
        )
        writer.write(
            {
                "schema": 1,
                "record_type": "HEADER",
                "claim_digest": claim_digest,
                "plan_digest": _hash(io.canonical_json(asdict(plan))),
            }
        )
        pending_bytes = pending_paths = 0
        for profile_id, n, replicate in iter_paths(plan):
            progress(counts)
            stream = io.CounterStream(
                namespace=plan.namespace,
                phase=plan.phase
                if plan.namespace == io.EXPERIMENT_NAMESPACE
                else (
                    "test_preflight" if plan.namespace == io.PREFLIGHT_NAMESPACE else "test_fixture"
                ),
                profile_id=profile_id,
                n=n,
                replicate=replicate,
                root=bytes.fromhex(value["root"]),
                _capability=capability,
            )
            item = io.spec(profile_id)

            def active(
                _: int, completed: Progress = counts, current: io.CounterStream | None = stream
            ) -> None:
                progress(
                    Progress(
                        completed.paths,
                        completed.metrics,
                        completed.words,
                        completed.payload_bytes,
                        current.words_consumed if current is not None else 0,
                    )
                )

            payload = io.generate_payload(item, stream, progress=active)
            result = io.evaluate_payload(item, payload)
            rows = io._pack_result(result)
            for row, calculated in zip(rows, result.rows, strict=True):
                row.update(
                    covered=calculated.covered,
                    lower_miss=calculated.lower_miss,
                    upper_miss=calculated.upper_miss,
                )
            _check_rows(profile_id, n, rows)
            validate_claim(root, claim, state.binding)
            row = {
                "schema": 1,
                "record_type": "PATH",
                "phase": plan.phase,
                "profile_id": profile_id,
                "n": n,
                "replicate": replicate,
                "offset": counts.payload_bytes,
                "size": len(payload),
                "payload_sha256": _hash(payload),
                "words": stream.words_consumed,
                "results": rows,
                "claim_digest": claim_digest,
            }
            encoded = io.canonical_json(row)
            if len(encoded) > plan.metadata_cap:
                raise PhaseError("path_metadata_cap")
            _storage(root, plan, counts.payload_bytes + len(payload), writer.total + len(encoded))
            io._write_all(payload_stream, payload)
            writer.write(row)
            payload_hasher.update(payload)
            reference._accumulate(summary, profile_id, rows)
            counts = Progress(
                counts.paths + 1,
                counts.metrics + len(rows),
                counts.words + stream.words_consumed,
                counts.payload_bytes + len(payload),
                0,
            )
            stream = None
            pending_bytes += len(payload)
            pending_paths += 1
            if pending_bytes >= io.SYNC_BYTES or pending_paths >= io.SYNC_PATHS:
                payload_stream.flush()
                os.fsync(payload_stream.fileno())
                writer.sync()
                pending_bytes = pending_paths = 0
            progress(counts)
        if (counts.paths, counts.metrics, counts.payload_bytes) != (
            plan.paths,
            plan.metrics,
            plan.payload_bytes,
        ):
            raise PhaseError("incomplete")
        payload_stream.flush()
        os.fsync(payload_stream.fileno())
    except BaseException as error:
        failure = error
    finally:
        state.valid = False
        if stream is not None:
            counts = Progress(
                counts.paths,
                counts.metrics,
                counts.words,
                counts.payload_bytes,
                stream.words_consumed,
            )
        try:
            life._shutdown([writer.close] if writer is not None else [], failure)
        except BaseException as error:
            failure = error
        try:
            life._shutdown([payload_stream.close] if payload_stream is not None else [], failure)
        except BaseException as error:
            failure = error
    if failure is not None:
        _failure(root, value, failure, counts, "writer")
        raise failure
    try:
        validate_claim(root, claim, state.binding)
        payload_digest = io._hash_file(
            root / "phase-payload.bin", expected_size=counts.payload_bytes
        )
        if payload_digest != payload_hasher.hexdigest():
            raise PhaseError("payload_drift")
        index_digest = io._hash_file(root / "phase-index.jsonl")
        decision = _decision(plan, summary)
        binding = _binding(value, claim_digest)
        report = {
            "schema": 1,
            "scope": plan.scope,
            "binding": binding,
            "summary": summary,
            "decision": decision,
            "counts": asdict(counts),
            "payload_digest": payload_digest,
            "index_digest": index_digest,
        }
        report_digest = _record(root, "phase-report.json", report, plan=plan)
        candidate = {
            "schema": 1,
            "state": "PHASE_OUTPUT_CANDIDATE",
            "binding": binding,
            "counts": asdict(counts),
            "decision": decision,
            "payload_digest": payload_digest,
            "index_digest": index_digest,
            "report_digest": report_digest,
            "worker": asdict(life.ProcessIdentity.current()),
        }
        _storage(root, plan, counts.payload_bytes, (root / "phase-index.jsonl").stat().st_size)
        terminal_digest = _record(root, "phase-terminal-candidate.json", candidate, plan=plan)
        return PhaseEvidence(
            io.canonical_json(binding),
            io.canonical_json(summary),
            decision,
            counts.paths,
            counts.metrics,
            counts.words,
            counts.payload_bytes,
            payload_digest,
            index_digest,
            report_digest,
            terminal_digest,
        )
    except BaseException as error:
        _failure(root, value, error, counts, "writer")
        raise


def _publish_test_terminal(root: Path, evidence: PhaseEvidence) -> None:
    claim = _read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
    plan, _ = validate_claim(root, claim, current_binding())
    if plan.namespace == io.EXPERIMENT_NAMESPACE:
        raise PhaseError("test_domain")
    candidate = _read_bytes(root / "phase-terminal-candidate.json", root, io.MAX_RECORD)
    if _hash(candidate) != evidence.terminal_digest:
        raise PhaseError("candidate_drift")
    value = _decode(candidate)
    value.update(
        state="TEST_PHASE_COMPLETE",
        completion={
            "owner": asdict(life.ProcessIdentity.current()),
            "scope": "PRIVATE_TEST_PUBLICATION",
        },
    )
    _record(root, "phase-terminal.json", value, plan=plan)


def verify_phase(
    root: Path,
    claim_digest: str,
    source_binding: SourceBinding,
    role: str,
    progress: Callable[[Progress], None],
    *,
    _worker_marker: object | None = None,
) -> PhaseEvidence:
    if type(role) is not str or role not in ("primary", "reviewer"):
        raise PhaseError("role")
    claim_bytes = _read_bytes(root / "phase-claim.json", root, io.MAX_RECORD)
    plan, claim = validate_claim(root, claim_bytes, source_binding)
    if _hash(claim_bytes) != claim_digest:
        raise PhaseError("claim_digest")
    counts = Progress(0, 0, 0, 0, 0)
    replay_permit = None
    try:
        if plan.namespace == io.EXPERIMENT_NAMESPACE or _worker_marker is not None:
            replay_permit = _issue_replay_permit(
                root,
                claim_bytes,
                _worker_marker,
                _fixture=plan.namespace != io.EXPERIMENT_NAMESPACE,
            )
        terminal_bytes = _read_bytes(root / "phase-terminal.json", root, io.MAX_RECORD)
        terminal = _decode(terminal_bytes)
        expected_state = (
            "COMPLETE" if plan.namespace == io.EXPERIMENT_NAMESPACE else "TEST_PHASE_COMPLETE"
        )
        if terminal.get("state") != expected_state:
            raise PhaseError("terminal")
        completion = terminal.get("completion")
        if type(completion) is not dict:
            raise PhaseError("completion")
        if (
            plan.namespace == io.EXPERIMENT_NAMESPACE
            or completion.get("scope") != "PRIVATE_TEST_PUBLICATION"
        ):
            runner = importlib.import_module("scripts.research.signal_calendar_score_runner")
            runner._validate_completion(root, claim_bytes, terminal)
        elif set(completion) != {"owner", "scope"} or completion["owner"] != claim["coordinator"]:
            raise PhaseError("completion")
        report_bytes = _read_bytes(root / "phase-report.json", root, io.MAX_RECORD)
        report = _decode(report_bytes)
        payload_path = io._guard_path(root / "phase-payload.bin", root, existing=True)
        before = payload_path.stat()
        if not stat.S_ISREG(before.st_mode) or before.st_size != plan.payload_bytes:
            raise PhaseError("payload_size")
        index_path = io._guard_path(root / "phase-index.jsonl", root, existing=True)
        index_before = index_path.stat()
        if not stat.S_ISREG(index_before.st_mode):
            raise PhaseError("nonregular")
        rows = iter(
            io.read_canonical_records(
                index_path,
                total_cap=plan.paths * plan.metadata_cap + io.MAX_RECORD,
                record_cap=plan.metadata_cap,
            )
        )
        expected_header = {
            "schema": 1,
            "record_type": "HEADER",
            "claim_digest": claim_digest,
            "plan_digest": _hash(io.canonical_json(asdict(plan))),
        }
        if io.canonical_json(next(rows, None)) != io.canonical_json(expected_header):
            raise PhaseError("index_header")
        reference.check_frozen_cutoffs()
        summary = reference._cells()
        hasher = hashlib.sha256()
        with payload_path.open("rb") as payload_stream:
            if _identity(os.fstat(payload_stream.fileno())) != _identity(before):
                raise PhaseError("file_drift")
            for profile_id, n, replicate in iter_paths(plan):
                progress(counts)
                validate_claim(root, claim_bytes, source_binding)
                length = io.source_length(io.spec(profile_id))
                row = next(rows, None)
                if row is None:
                    raise PhaseError("missing_index")
                expected_header = {
                    "schema": 1,
                    "record_type": "PATH",
                    "phase": plan.phase,
                    "profile_id": profile_id,
                    "n": n,
                    "replicate": replicate,
                    "offset": counts.payload_bytes,
                    "size": length,
                    "claim_digest": claim_digest,
                }
                if io.canonical_json(
                    {
                        k: v
                        for k, v in row.items()
                        if k not in ("results", "words", "payload_sha256")
                    }
                ) != io.canonical_json(expected_header):
                    raise PhaseError("ordered_identity")
                payload = payload_stream.read(length)
                if len(payload) != length:
                    raise PhaseError("truncated_payload")
                identity = {
                    "namespace": plan.namespace,
                    "phase": plan.phase
                    if plan.namespace == io.EXPERIMENT_NAMESPACE
                    else (
                        "test_preflight"
                        if plan.namespace == io.PREFLIGHT_NAMESPACE
                        else "test_fixture"
                    ),
                    "profile_id": profile_id,
                    "n": n,
                    "replicate": replicate,
                    "root": claim["root"],
                }
                calculated = reference._claimed_reference_path(
                    profile_id,
                    n,
                    payload,
                    identity,
                    root,
                    claim_bytes,
                    source_binding,
                    _permit=replay_permit,
                )
                _check_rows(profile_id, n, list(calculated.rows))
                expected_row = {
                    **expected_header,
                    "payload_sha256": _hash(payload),
                    "words": calculated.words,
                    "results": list(calculated.rows),
                }
                if io.canonical_json(row) != io.canonical_json(expected_row):
                    raise PhaseError("reference_mismatch")
                reference._accumulate(summary, profile_id, list(calculated.rows))
                hasher.update(payload)
                counts = Progress(
                    counts.paths + 1,
                    counts.metrics + len(calculated.rows),
                    counts.words + calculated.words,
                    counts.payload_bytes + length,
                    0,
                )
                progress(counts)
            if payload_stream.read(1) or next(rows, None) is not None:
                raise PhaseError("trailing_evidence")
        if _identity(payload_path.stat()) != _identity(before) or (
            _identity(index_path.stat()) != _identity(index_before)
        ):
            raise PhaseError("file_drift")
        payload_digest = hasher.hexdigest()
        index_digest = io._hash_file(index_path, expected_size=index_before.st_size)
        decision = _decision(plan, summary)
        binding = _binding(claim, claim_digest)
        expected_report = {
            "schema": 1,
            "utc": report["utc"],
            "scope": plan.scope,
            "binding": binding,
            "summary": summary,
            "decision": decision,
            "counts": asdict(counts),
            "payload_digest": payload_digest,
            "index_digest": index_digest,
        }
        if io.canonical_json(report) != io.canonical_json(expected_report):
            raise PhaseError("report")
        candidate = _read_record(root, "phase-terminal-candidate.json")
        expected_candidate = {
            "schema": 1,
            "utc": candidate["utc"],
            "state": "PHASE_OUTPUT_CANDIDATE",
            "binding": binding,
            "counts": asdict(counts),
            "decision": decision,
            "payload_digest": payload_digest,
            "index_digest": index_digest,
            "report_digest": _hash(report_bytes),
            "worker": candidate.get("worker"),
        }
        if io.canonical_json(candidate) != io.canonical_json(expected_candidate):
            raise PhaseError("terminal_candidate")
        expected_terminal = {
            **expected_candidate,
            "state": expected_state,
            "completion": completion,
        }
        if io.canonical_json(terminal) != io.canonical_json(expected_terminal):
            raise PhaseError("terminal")
        validate_claim(root, claim_bytes, source_binding)
        receipt = {
            "schema": 1,
            "state": "VERIFICATION_CANDIDATE",
            "role": role,
            "binding": binding,
            "decision": decision,
            "counts": asdict(counts),
            "payload_digest": payload_digest,
            "index_digest": index_digest,
            "report_digest": _hash(report_bytes),
            "terminal_digest": _hash(terminal_bytes),
            "summary_digest": _hash(io.canonical_json(summary)),
            "verifier": asdict(life.ProcessIdentity.current()),
        }
        _storage(root, plan, counts.payload_bytes, index_before.st_size)
        receipt_digest = _record(root, f"verified-{role}-candidate.json", receipt, plan=plan)
        return PhaseEvidence(
            io.canonical_json(binding),
            io.canonical_json(summary),
            decision,
            counts.paths,
            counts.metrics,
            counts.words,
            counts.payload_bytes,
            payload_digest,
            index_digest,
            _hash(report_bytes),
            _hash(terminal_bytes),
            receipt_digest,
        )
    except BaseException as error:
        _failure(root, claim, error, counts, role)
        raise


def _check_rows(profile_id: str, n: int, rows: list[dict[str, Any]]) -> None:
    from math import gcd

    metrics = tuple(metric.value for metric in io._metrics(io.spec(profile_id)))
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
    if type(rows) is not list or len(rows) != len(metrics):
        raise PhaseError("result_schema")
    for row, metric in zip(rows, metrics, strict=True):
        if type(row) is not dict or set(row) != fields or row["metric"] != metric:
            raise PhaseError("result_schema")
        if type(row["count"]) is not int or not 0 <= row["count"] <= 2 * n:
            raise PhaseError("result_count")
        if type(row["reason"]) is not str or len(row["reason"]) > 512:
            raise PhaseError("result_schema")
        for name in ("arithmetic", "precision", "covered", "lower_miss", "upper_miss", "detected"):
            if type(row[name]) is not bool:
                raise PhaseError("result_schema")
        for name in ("truth", "total", "lower", "upper"):
            pair = row[name]
            if pair is None and name in ("lower", "upper") and row["count"] == 0:
                continue
            if (
                type(pair) is not list
                or len(pair) != 2
                or any(type(v) is not int or v.bit_length() > 2048 for v in pair)
                or pair[1] <= 0
                or gcd(pair[0], pair[1]) != 1
            ):
                raise PhaseError("result_numeric")
        if row["arithmetic"] is not bool(row["count"]):
            raise PhaseError("result_arithmetic")
        if int(row["covered"]) + int(row["lower_miss"]) + int(row["upper_miss"]) != int(
            row["arithmetic"]
        ):
            raise PhaseError("result_partition")
        if profile_id != "L1" and (
            row["arithmetic"] is not True
            or row["precision"] is not True
            or row["count"] < n
            or row["reason"] != ""
        ):
            raise PhaseError("formal_refusal")
    if len({row["count"] for row in rows}) != 1:
        raise PhaseError("result_count")


def _issue_worker_capability(root: Path, claim: bytes, marker: object) -> _PhaseCapability:
    from scripts.research import signal_calendar_score_runner as runner

    runner._validate_worker_registration(marker, root, claim)
    binding = current_binding()
    plan, _claim = validate_claim(root, claim, binding)
    if plan.namespace != io.EXPERIMENT_NAMESPACE:
        raise PhaseError("actual_worker_namespace")
    capability = _PhaseCapability(_hash(claim), life.ProcessIdentity.current())
    _CAPABILITIES[id(capability)] = _CapabilityState(
        capability, root, claim, plan, binding, iter_paths(plan)
    )
    return capability


@dataclass(frozen=True, slots=True)
class _ReplayPermit:
    root: Path
    claim_digest: str
    owner: life.ProcessIdentity
    source: SourceBinding


_REPLAY_PERMITS: dict[int, _ReplayPermit] = {}
_FIXTURE_REPLAY_PERMITS: dict[int, _ReplayPermit] = {}


def _issue_replay_permit(
    root: Path, claim: bytes, marker: object, *, _fixture: bool = False
) -> _ReplayPermit:
    from scripts.research import signal_calendar_score_runner as runner

    runner._validate_worker_registration(marker, root, claim)
    source = current_binding()
    plan, _ = validate_claim(root, claim, source)
    allowed = (
        (io.TEST_NAMESPACE, io.PREFLIGHT_NAMESPACE) if _fixture else (io.EXPERIMENT_NAMESPACE,)
    )
    if plan.namespace not in allowed:
        raise PhaseError("actual_worker_namespace")
    token = _ReplayPermit(root, _hash(claim), life.ProcessIdentity.current(), source)
    permits = _FIXTURE_REPLAY_PERMITS if _fixture else _REPLAY_PERMITS
    permits[id(token)] = token
    return token


def _check_replay_permit(
    token: object, root: Path, claim: bytes, source: SourceBinding, *, _fixture: bool = False
) -> None:
    permits = _FIXTURE_REPLAY_PERMITS if _fixture else _REPLAY_PERMITS
    if (
        type(token) is not _ReplayPermit
        or permits.get(id(token)) is not token
        or (
            token.root != root
            or token.claim_digest != _hash(claim)
            or token.owner != life.ProcessIdentity.current()
            or token.source != source
        )
    ):
        raise PhaseError("replay_issuer")
