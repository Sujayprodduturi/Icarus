"""One-shot Linux launcher and non-authoritative monitor for the v3 artificial study."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from scripts.research import signal_calendar_score_phase as phase
from scripts.research import signal_calendar_score_study as io

PROJECT = io.PROJECT
MAX_COMPACT_RECORD = 256 * 1024
EXTERNAL_WALL_SECONDS = 301_200
ALLOWED_IMAGE_ENV = frozenset(
    {
        "PATH",
        "LANG",
        "GPG_KEY",
        "PYTHON_VERSION",
        "PYTHON_SHA256",
        "UV_PROJECT_ENVIRONMENT",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONUNBUFFERED",
    }
)
IMAGE_HEAD_LABEL = "org.icarus.commit"
IMAGE_MANIFEST_LABEL = "org.icarus.reviewed-manifest"
IMAGE_PROTOCOL_LABEL = "org.icarus.protocol"
IMAGE_SOURCES_LABEL = "org.icarus.sources-digest"
IMAGE_DATA_OWNER_LABEL = "org.icarus.data-owner"
_NAME = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}")
_HEX64 = re.compile(r"[a-f0-9]{64}")
_HEX40 = re.compile(r"[a-f0-9]{40}")


class LaunchError(RuntimeError):
    """A fail-closed launcher contract refusal."""


Run = Callable[..., Any]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _uid() -> int:
    function = cast(Callable[[], int], os.__dict__.get("getuid", lambda: -1))
    value = function()
    if type(value) is not int:
        raise LaunchError("uid")
    return value


def _gid() -> int:
    function = cast(Callable[[], int], os.__dict__.get("getgid", lambda: -1))
    value = function()
    if type(value) is not int:
        raise LaunchError("gid")
    return value


def _is_linux() -> bool:
    return sys.platform == "linux"


def _linux_data_volume_check() -> None:
    try:
        rows = Path("/proc/self/mountinfo").read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise LaunchError("mountinfo") from error
    matches = [row for row in rows if len(row.split()) > 5 and row.split()[4] == "/work/var"]
    if len(matches) != 1:
        raise LaunchError("data_mount")
    left, separator, right = matches[0].partition(" - ")
    options = left.split()[5].split(",")
    filesystem = right.split()[0] if separator and right.split() else ""
    if filesystem != "ext4" or "rw" not in options:
        raise LaunchError("data_filesystem")
    for path in (Path("/work/var"), Path("/work/var/home"), Path("/work/var/tmp")):
        try:
            status = path.stat()
        except OSError as error:
            raise LaunchError("data_directory") from error
        if status.st_uid != 1000 or status.st_gid != 1000 or not os.access(path, os.W_OK):
            raise LaunchError("data_ownership")


def _source_names() -> tuple[str, ...]:
    names = (*io.SOURCE_PATHS, *phase.EXTRA_SOURCES)
    if any(type(name) is not str or not name for name in names):
        raise LaunchError("source_allowlist")
    return tuple(sorted(set(names)))


def _read_json(path: Path, cap: int = MAX_COMPACT_RECORD) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > cap:
        raise LaunchError("bounded_record")
    try:
        value = json.loads(path.read_bytes())
    except (OSError, ValueError, UnicodeError) as error:
        raise LaunchError("record_json") from error
    if type(value) is not dict:
        raise LaunchError("record_schema")
    return value


def _record(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(value, sort_keys=True, indent=2).encode("utf-8")
    if len(blob) > MAX_COMPACT_RECORD:
        raise LaunchError("record_cap")
    try:
        with path.open("xb") as stream:
            stream.write(blob)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError as error:
        raise LaunchError("record_exists") from error


def _result(command: list[str], *, run: Run, **kwargs: object) -> Any:
    kwargs.setdefault("timeout", 30.0)
    return run(command, text=True, capture_output=True, **kwargs)


def _json_command(command: list[str], *, run: Run) -> Any:
    completed = _result(command, run=run)
    if completed.returncode != 0:
        raise LaunchError("inspection_failed")
    try:
        return json.loads(completed.stdout)
    except (TypeError, ValueError) as error:
        raise LaunchError("inspection_json") from error


def _validate_freeze(
    path: Path,
    *,
    image: str,
    head: str,
    reviewed_manifest: str,
    protocol_sha256: str,
    project: Path,
) -> tuple[dict[str, Any], bytes]:
    blob = path.read_bytes()
    if len(blob) > MAX_COMPACT_RECORD:
        raise LaunchError("freeze_cap")
    try:
        freeze = json.loads(blob)
    except (ValueError, UnicodeError) as error:
        raise LaunchError("freeze_json") from error
    expected_head = {
        "schema": 1,
        "scope": "ARTIFICIAL_RESEARCH_LAUNCH_FREEZE_NO_AUTHORITY",
        "protocol_sha256": protocol_sha256,
        "reviewed_manifest": reviewed_manifest,
        "head": head,
        "image": image,
    }
    if type(freeze) is not dict or set(freeze) != set(expected_head) | {"manifest"}:
        raise LaunchError("freeze_contract")
    if any(freeze[key] != value for key, value in expected_head.items()):
        raise LaunchError("freeze_contract")
    manifest = freeze.get("manifest")
    if type(manifest) is not dict:
        raise LaunchError("freeze_contract")
    sources = manifest.get("sources")
    names = _source_names()
    if type(sources) is not dict or set(sources) != set(names):
        raise LaunchError("freeze_contract")
    for name in names:
        digest = sources.get(name)
        target = project / name
        if type(digest) is not str or _HEX64.fullmatch(digest) is None or not target.is_file():
            raise LaunchError("freeze_contract")
        if _digest(target.read_bytes()) != digest:
            raise LaunchError("source_drift")
    paths = {name: project / name for name in names}
    try:
        io.verify_manifest(
            io.Manifest(manifest, reviewed_manifest),
            paths,
            protocol_hash=protocol_sha256,
        )
    except (io.StudyError, KeyError, TypeError, ValueError) as error:
        raise LaunchError("freeze_manifest") from error
    return freeze, blob


def _reserve(
    project: Path,
    *,
    protocol_sha256: str,
    image: str,
    head: str,
    reviewed_manifest: str,
    container_name: str,
    volume_name: str,
) -> Path:
    parent = project / "var/research/calendar_score_v3/linux-launch-reservations"
    parent.mkdir(parents=True, exist_ok=True)
    marker = parent / f"{protocol_sha256}.json"
    value = {
        "schema": 1,
        "scope": "HOST_LAUNCH_BOOKKEEPING_ONLY_NO_STUDY_AUTHORITY",
        "protocol_sha256": protocol_sha256,
        "reviewed_manifest": reviewed_manifest,
        "image": image,
        "head": head,
        "container_name": container_name,
        "volume_name": volume_name,
        "reserved_at_utc": datetime.now(UTC).isoformat(),
        "reserved_at_monotonic": time.monotonic(),
        "retry_authority": False,
    }
    try:
        _record(marker, value)
    except LaunchError as error:
        if str(error) == "record_exists":
            raise LaunchError("protocol_consumed") from error
        raise
    if os.name != "nt":
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
    return marker


def _validate_image(
    image: str,
    *,
    head: str,
    reviewed_manifest: str,
    protocol_sha256: str,
    sources: Mapping[str, str],
    run: Run,
) -> None:
    rows = _json_command(["docker", "image", "inspect", image], run=run)
    if type(rows) is not list or len(rows) != 1 or type(rows[0]) is not dict:
        raise LaunchError("image_contract")
    row = rows[0]
    config = row.get("Config")
    if row.get("Id") != image or type(config) is not dict or config.get("User") != "1000:1000":
        raise LaunchError("image_contract")
    env = config.get("Env")
    labels = config.get("Labels")
    expected_labels = {
        IMAGE_HEAD_LABEL: head,
        IMAGE_MANIFEST_LABEL: reviewed_manifest,
        IMAGE_PROTOCOL_LABEL: protocol_sha256,
        IMAGE_SOURCES_LABEL: _digest(_canonical(sources)),
        IMAGE_DATA_OWNER_LABEL: "1000:1000",
    }
    if (
        type(env) is not list
        or {entry.partition("=")[0] for entry in env if type(entry) is str} != ALLOWED_IMAGE_ENV
        or len(env) != len(ALLOWED_IMAGE_ENV)
        or any(type(entry) is not str or "=" not in entry for entry in env)
        or config.get("WorkingDir") != "/work"
        or config.get("Entrypoint") not in (None, [])
        or type(labels) is not dict
        or any(labels.get(key) != value for key, value in expected_labels.items())
    ):
        raise LaunchError("image_contract")


def _validate_container(info: Any, *, image: str, volume_name: str) -> None:
    if type(info) is not list or len(info) != 1 or type(info[0]) is not dict:
        raise LaunchError("container_contract")
    row = info[0]
    host = row.get("HostConfig")
    config = row.get("Config")
    mounts = row.get("Mounts")
    if type(host) is not dict or type(config) is not dict or type(mounts) is not list:
        raise LaunchError("container_contract")
    expected_host = {
        "NetworkMode": "none",
        "ReadonlyRootfs": True,
        "CapDrop": ["ALL"],
        "Memory": 4 * 1024**3,
        "NanoCpus": 4_000_000_000,
        "SecurityOpt": ["no-new-privileges=true"],
    }
    expected_mount_fields = {
        "Type": "volume",
        "Name": volume_name,
        "Destination": "/work/var",
        "RW": True,
    }
    env = config.get("Env")
    env_values = (
        {
            entry.partition("=")[0]: entry.partition("=")[2]
            for entry in env
            if type(entry) is str and "=" in entry
        }
        if type(env) is list
        else {}
    )
    command = config.get("Cmd")
    restart = host.get("RestartPolicy")
    if (
        row.get("Image") != image
        or config.get("User") != "1000:1000"
        or type(env) is not list
        or set(env_values) != set(ALLOWED_IMAGE_ENV) | {"HOME", "TMPDIR"}
        or len(env) != len(env_values)
        or env_values.get("HOME") != "/work/var/home"
        or env_values.get("TMPDIR") != "/work/var/tmp"
        or config.get("WorkingDir") != "/work"
        or config.get("Entrypoint") not in (None, [])
        or command
        != [
            "python",
            "-m",
            "scripts.research.signal_calendar_score_launch",
            "inside",
            "--freeze=/work/var/reviewed-freeze.json",
        ]
        or any(host.get(key) != value for key, value in expected_host.items())
        or type(restart) is not dict
        or restart.get("Name") != "no"
        or restart.get("MaximumRetryCount") != 0
        or len(mounts) != 1
        or any(mounts[0].get(key) != value for key, value in expected_mount_fields.items())
    ):
        raise LaunchError("container_contract")


def _retained_failure(marker: Path, category: str) -> None:
    try:
        _record(
            marker.with_name(marker.stem + "-failure.json"),
            {
                "schema": 1,
                "classification": "HOST_LAUNCH_INCOMPLETE",
                "category": category,
                "qualification": False,
                "authority": False,
                "retry_authority": False,
            },
        )
    except BaseException as secondary:
        error = LaunchError(category)
        error.add_note(f"Failure record: {type(secondary).__name__}")
        raise error from None
    raise LaunchError(category)


def _validate_new_volume(value: Any, *, name: str, reserved_at: datetime) -> None:
    if type(value) is not list or len(value) != 1 or type(value[0]) is not dict:
        raise LaunchError("volume_contract")
    row = value[0]
    labels = row.get("Labels")
    try:
        created = datetime.fromisoformat(str(row.get("CreatedAt")).replace("Z", "+00:00"))
    except ValueError as error:
        raise LaunchError("volume_contract") from error
    if (
        row.get("Name") != name
        or labels != {"icarus.scope": "artificial-research-v3"}
        or created.tzinfo is None
        or created < reserved_at.replace(microsecond=0)
    ):
        raise LaunchError("volume_contract")


def _guard_launch_paths(project: Path, freeze_path: Path, evidence_dir: Path) -> tuple[Path, Path]:
    try:
        if project.resolve(strict=True) != io.PROJECT.resolve(strict=True):
            raise LaunchError("project_root")
        verification_root = project / "var/verification"
        verification_root.mkdir(parents=True, exist_ok=True)
        verification_root = io._guard_path(verification_root, project, existing=True)
        return (
            io._guard_path(freeze_path, verification_root, existing=True),
            io._guard_path(evidence_dir, verification_root),
        )
    except (OSError, io.StudyError) as error:
        raise LaunchError("launch_path") from error


def launch(
    *,
    image: str,
    head: str,
    reviewed_manifest: str,
    protocol_sha256: str,
    freeze_path: Path,
    container_name: str,
    volume_name: str,
    evidence_dir: Path,
    project: Path = PROJECT,
    run: Run = subprocess.run,
) -> dict[str, object]:
    guarded_freeze, guarded_evidence = _guard_launch_paths(project, freeze_path, evidence_dir)
    if (
        _HEX64.fullmatch(protocol_sha256) is None
        or _HEX64.fullmatch(reviewed_manifest) is None
        or _HEX40.fullmatch(head) is None
        or re.fullmatch(r"sha256:[a-f0-9]{64}", image) is None
        or any(_NAME.fullmatch(value) is None for value in (container_name, volume_name))
        or protocol_sha256 != io.PROTOCOL_SHA256
    ):
        raise LaunchError("launch_input")
    freeze, freeze_blob = _validate_freeze(
        guarded_freeze,
        image=image,
        head=head,
        reviewed_manifest=reviewed_manifest,
        protocol_sha256=protocol_sha256,
        project=project,
    )
    head_result = _result(["git", "rev-parse", "HEAD"], run=run, cwd=project)
    if head_result.returncode != 0 or head_result.stdout.strip() != head:
        raise LaunchError("committed_head")
    diff = _result(["git", "diff", "--quiet", "HEAD", "--", *_source_names()], run=run, cwd=project)
    if diff.returncode != 0:
        raise LaunchError("committed_sources")
    _validate_image(
        image,
        head=head,
        reviewed_manifest=reviewed_manifest,
        protocol_sha256=protocol_sha256,
        sources=freeze["manifest"]["sources"],
        run=run,
    )
    marker = _reserve(
        project,
        protocol_sha256=protocol_sha256,
        image=image,
        head=head,
        reviewed_manifest=reviewed_manifest,
        container_name=container_name,
        volume_name=volume_name,
    )
    inspected = _result(["docker", "volume", "inspect", volume_name], run=run)
    if inspected.returncode == 0:
        _retained_failure(marker, "volume_exists")
    if inspected.returncode != 1 or "no such volume" not in inspected.stderr.lower():
        _retained_failure(marker, "volume_inspection")
    created = _result(
        [
            "docker",
            "volume",
            "create",
            "--label",
            "icarus.scope=artificial-research-v3",
            volume_name,
        ],
        run=run,
    )
    if created.returncode != 0:
        _retained_failure(marker, "volume_create")
    reserved_at = datetime.fromisoformat(_read_json(marker)["reserved_at_utc"])
    try:
        _validate_new_volume(
            _json_command(["docker", "volume", "inspect", volume_name], run=run),
            name=volume_name,
            reserved_at=reserved_at,
        )
    except LaunchError as error:
        _retained_failure(marker, str(error))
    command = [
        "docker",
        "create",
        "--name",
        container_name,
        "--label",
        "icarus.scope=artificial-research-v3",
        "--restart",
        "no",
        "--network",
        "none",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges=true",
        "--read-only",
        "--cpus",
        "4",
        "--memory",
        "4g",
        "--env",
        "HOME=/work/var/home",
        "--env",
        "TMPDIR=/work/var/tmp",
        "--mount",
        f"type=volume,source={volume_name},target=/work/var",
        image,
        "python",
        "-m",
        "scripts.research.signal_calendar_score_launch",
        "inside",
        "--freeze=/work/var/reviewed-freeze.json",
    ]
    made = _result(command, run=run)
    if made.returncode != 0 or not made.stdout.strip():
        _retained_failure(marker, "container_create")
    container = made.stdout.strip()
    try:
        _validate_container(
            _json_command(["docker", "container", "inspect", container], run=run),
            image=image,
            volume_name=volume_name,
        )
    except LaunchError as error:
        _retained_failure(marker, str(error))
    inspection_parent = project / "var/verification/calendar-score-launch-inspection"
    inspection_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=inspection_parent) as temporary:
        target = Path(temporary)
        for name, digest in freeze["manifest"]["sources"].items():
            copied = _result(["docker", "cp", f"{container}:/work/{name}", str(target)], run=run)
            candidate = target / Path(name).name
            if (
                copied.returncode != 0
                or not candidate.is_file()
                or _digest(candidate.read_bytes()) != digest
            ):
                _retained_failure(marker, "image_source")
            candidate.unlink()
    copied_freeze = _result(
        ["docker", "cp", str(guarded_freeze), f"{container}:/work/var/reviewed-freeze.json"],
        run=run,
    )
    if copied_freeze.returncode != 0:
        _retained_failure(marker, "freeze_copy")
    guarded_evidence.mkdir(parents=True, exist_ok=False)
    contract_path = guarded_evidence / "contract.json"
    _record(
        contract_path,
        {
            "schema": 1,
            "scope": "HOST_LAUNCH_BOOKKEEPING_ONLY_NO_STUDY_AUTHORITY",
            "container": container,
            "container_name": container_name,
            "freeze": str(guarded_freeze),
            "volume": volume_name,
            "image": image,
            "head": head,
            "protocol_sha256": protocol_sha256,
            "reviewed_manifest": reviewed_manifest,
            "freeze_sha256": _digest(freeze_blob),
            "reservation": str(marker),
            "launch_utc": _read_json(marker)["reserved_at_utc"],
            "launch_monotonic": _read_json(marker)["reserved_at_monotonic"],
            "qualification": False,
            "authority": False,
        },
    )
    started = _result(["docker", "start", container], run=run)
    if started.returncode != 0:
        _retained_failure(marker, "container_start")
    return {
        "classification": "RUNNING_NON_AUTHORITATIVE",
        "contract": str(contract_path),
        "container": container,
        "volume": volume_name,
        "qualification": False,
        "authority": False,
    }


def _verify_completion(result: dict[str, object], registry: Path) -> bool:
    from scripts.research import signal_calendar_score_runner_service as service

    state = result.get("state")
    if state not in ("FINAL_VERDICT", "DEVELOPMENT_FAILED"):
        return False
    binding = phase.current_binding()
    attempt = phase._read_record(registry, "attempt-result.json")
    if (
        result.get("namespace") != io.EXPERIMENT_NAMESPACE
        or result.get("study_permission") is not False
        or result.get("sampling_executed") is not True
        or result.get("children_exited") is not True
        or attempt.get("source_binding") != asdict(binding)
        or attempt.get("namespace") != io.EXPERIMENT_NAMESPACE
        or attempt.get("study_permission") is not False
        or attempt.get("sampling_executed") is not True
        or result.get("release_transfers") != (1 if state == "FINAL_VERDICT" else 0)
    ):
        return False
    reserved = phase._read_record(registry, "attempt-reserved.json")
    registration = phase._read_record(registry, "attempt-registration.json")
    expected_attempt = {
        **{k: v for k, v in result.items() if k not in ("registry", "children_exited")},
        "schema": 1,
        "scope": "ARTIFICIAL_RESEARCH_ONLY",
        "source_binding": asdict(binding),
        "session_id": reserved.get("session_id"),
        "utc": attempt.get("utc"),
    }
    expected_registration = {
        "schema": 1,
        "utc": registration.get("utc"),
        "state": "COORDINATOR_REGISTERED",
        "namespace": io.EXPERIMENT_NAMESPACE,
        "attempt_id": io.PROTOCOL_SHA256,
        "session_id": reserved.get("session_id"),
        "coordinator": reserved.get("owner"),
        "reviewer": reserved.get("reviewer"),
        "helper": registration.get("helper"),
        "source_binding": asdict(binding),
        "reservation_digest": _digest(io.canonical_json(reserved)),
        "source_review_digest": binding.manifest_digest,
    }
    if (
        io.canonical_json(attempt) != io.canonical_json(expected_attempt)
        or io.canonical_json(registration) != io.canonical_json(expected_registration)
        or reserved.get("namespace") != io.EXPERIMENT_NAMESPACE
        or reserved.get("attempt_id") != io.PROTOCOL_SHA256
        or reserved.get("source_binding") != asdict(binding)
        or type(reserved.get("session_id")) is not str
        or len(
            {io.canonical_json(registration.get(k)) for k in ("coordinator", "reviewer", "helper")}
        )
        != 3
    ):
        return False
    expected = ("development", "validation") if state == "FINAL_VERDICT" else ("development",)
    for name in expected:
        evidence = service._evidence_check(registry, name, binding, _scan_payload=False)
        paths, metrics = io.phase_totals(name)
        if (
            result.get(name + "_paths") != paths
            or result.get(name + "_metrics") != metrics
            or evidence.get("decision")
            not in (
                ("PASS", "FAILED")
                if name == "validation"
                else (("FAILED",) if state == "DEVELOPMENT_FAILED" else ("PASS",))
            )
        ):
            return False
        approval = phase._read_record(registry, f"{name}-reviewer-approved.json")
        expected_approval = {
            "action": "approve-" + name,
            "evidence": evidence,
            "source_review_digest": binding.manifest_digest,
            "control_decision": evidence.get("decision"),
            "reviewer": registration["reviewer"],
            "helper": registration["helper"],
            "scope": "ARTIFICIAL_RESEARCH_ONLY",
            "state": "REVIEW_APPROVED",
            "schema": 1,
            "utc": approval.get("utc"),
        }
        evidence_binding = evidence.get("binding")
        if (
            io.canonical_json(approval) != io.canonical_json(expected_approval)
            or type(evidence_binding) is not dict
            or evidence_binding.get("session_id") != reserved["session_id"]
            or evidence_binding.get("attempt_id") != io.PROTOCOL_SHA256
        ):
            return False
    return True


def classify_outcome(
    result: dict[str, object] | None,
    *,
    exit_code: int,
    oom_killed: bool,
    bound_complete: bool,
) -> dict[str, object]:
    state = result.get("state") if type(result) is dict else None
    if oom_killed:
        classification = "OOM_INCOMPLETE"
    elif exit_code != 0:
        classification = "PROCESS_EXIT_INCOMPLETE"
    elif state is None:
        classification = "EMPTY_RESULT_INCOMPLETE"
    elif state == "ERROR":
        classification = "ERROR_INCOMPLETE"
    elif state == "UNDRAWN_READINESS_BLOCKER":
        classification = "UNDRAWN_READINESS_BLOCKER"
    elif not bound_complete:
        classification = "BINDING_MISMATCH_INCOMPLETE"
    elif state in ("FINAL_VERDICT", "DEVELOPMENT_FAILED"):
        classification = f"{state}_NON_AUTHORITATIVE"
    else:
        classification = "UNKNOWN_RESULT_INCOMPLETE"
    return {"classification": classification, "qualification": False, "authority": False}


def monitor_outcome(
    primary: Mapping[str, object], *, copy_returncodes: Mapping[str, int]
) -> dict[str, object]:
    return {**primary, "copy_error": any(code != 0 for code in copy_returncodes.values())}


def inside(
    freeze_path: Path,
    *,
    run_reviewed_study: Callable[[str], dict[str, object]] | None = None,
    filesystem_check: Callable[[], None] = _linux_data_volume_check,
) -> dict[str, object]:
    if not _is_linux() or _uid() != 1000 or _gid() != 1000:
        raise LaunchError("linux_identity")
    filesystem_check()
    try:
        data_root = io._guard_path(PROJECT / "var", PROJECT, existing=True)
        freeze_path = io._guard_path(freeze_path, data_root, existing=True)
    except io.StudyError as error:
        raise LaunchError("inside_path") from error
    freeze = _read_json(freeze_path)
    if set(freeze) != {
        "schema",
        "scope",
        "protocol_sha256",
        "reviewed_manifest",
        "head",
        "image",
        "manifest",
    }:
        raise LaunchError("freeze_contract")
    current = phase.phase_manifest()
    if (
        freeze.get("protocol_sha256") != io.PROTOCOL_SHA256
        or freeze.get("reviewed_manifest") != current.digest
        or freeze.get("manifest") != current.payload
        or set(freeze["manifest"]["sources"]) != set(_source_names())
    ):
        raise LaunchError("inside_binding")
    for name, digest in freeze["manifest"]["sources"].items():
        if _digest((PROJECT / name).read_bytes()) != digest:
            raise LaunchError("inside_source")
    output = PROJECT / f"var/verification/calendar-score-launcher/{io.PROTOCOL_SHA256}"
    output.mkdir(parents=True, exist_ok=False)
    _record(
        output / "started.json",
        {
            "schema": 1,
            "scope": "ARTIFICIAL_RESEARCH_ONLY",
            "protocol_sha256": io.PROTOCOL_SHA256,
            "reviewed_manifest": current.digest,
            "source_digest": _digest(_canonical(freeze["manifest"]["sources"])),
            "qualification": False,
            "authority": False,
        },
    )
    if run_reviewed_study is None:
        from scripts.research import signal_calendar_score_runner as runner

        run_reviewed_study = runner.run_reviewed_study
    try:
        result = run_reviewed_study(current.digest)
        public_keys = (
            "state",
            "namespace",
            "study_permission",
            "sampling_executed",
            "release_transfers",
            "children_exited",
            "development_paths",
            "development_metrics",
            "validation_paths",
            "validation_metrics",
        )
        public_result = {key: result[key] for key in public_keys if key in result}
        public_result.update(protocol_sha256=io.PROTOCOL_SHA256, reviewed_manifest=current.digest)
        if result.get("state") == "ERROR":
            stages = {
                "bootstrap",
                "development",
                "validation",
                "coordinator-approval",
                "second-release",
            }
            reasons = {
                "transport",
                "authentication",
                "coordinator_action",
                "release_once",
                "child_exit",
                "process_exit",
                "deadline",
                "heartbeat_lost",
                "source_drift",
                "worker_bootstrap",
            }
            stage = result.get("failure_stage")
            public_result["failure_stage"] = (
                stage if type(stage) is str and stage in stages else "unknown"
            )
            reason = result.get("failure_reason")
            public_result["failure_reason"] = (
                reason if type(reason) is str and reason in reasons else "unknown"
            )
        _record(output / "returned-result.json", public_result)
        registry_value = result.get("registry")
        complete = False
        if type(registry_value) is str:
            registry = Path(registry_value)
            try:
                expected_registry = io.EXPERIMENT_ROOT / "attempts" / io.PROTOCOL_SHA256
                guarded_registry = io._guard_path(registry, io.EXPERIMENT_ROOT, existing=True)
                if guarded_registry == expected_registry.resolve(strict=True):
                    complete = _verify_completion(result, guarded_registry)
            except (ValueError, OSError, RuntimeError, KeyError, TypeError):
                complete = False
        outcome = classify_outcome(result, exit_code=0, oom_killed=False, bound_complete=complete)
        _record(
            output / "outcome.json",
            {
                **outcome,
                "returned_state": result.get("state"),
                "protocol_sha256": io.PROTOCOL_SHA256,
                "reviewed_manifest": current.digest,
                "bound_complete": complete,
            },
        )
        return outcome
    except BaseException as error:
        try:
            _record(
                output / "launcher-error.json",
                {
                    "schema": 1,
                    "classification": "LAUNCHER_EXCEPTION_INCOMPLETE",
                    "error_category": type(error).__name__,
                    "qualification": False,
                    "authority": False,
                },
            )
        except BaseException as secondary:
            error.add_note(f"Launcher record: {type(secondary).__name__}")
        raise


def monitor(contract_path: Path, *, run: Run = subprocess.run) -> dict[str, object]:
    try:
        verification_root = io._guard_path(PROJECT / "var/verification", PROJECT, existing=True)
        contract_path = io._guard_path(contract_path, verification_root, existing=True)
    except io.StudyError as error:
        raise LaunchError("monitor_path") from error
    contract = _read_json(contract_path)
    verification_root = PROJECT / "var/verification"
    freeze_path = io._guard_path(Path(str(contract["freeze"])), verification_root, existing=True)
    freeze, freeze_blob = _validate_freeze(
        freeze_path,
        image=str(contract["image"]),
        head=str(contract["head"]),
        reviewed_manifest=str(contract["reviewed_manifest"]),
        protocol_sha256=str(contract["protocol_sha256"]),
        project=PROJECT,
    )
    marker_root = PROJECT / "var/research/calendar_score_v3/linux-launch-reservations"
    marker_path = io._guard_path(Path(str(contract["reservation"])), marker_root, existing=True)
    if marker_path != (marker_root / f"{io.PROTOCOL_SHA256}.json").resolve(strict=True):
        raise LaunchError("monitor_reservation")
    marker = _read_json(marker_path)
    pairs = {
        "image": "image",
        "head": "head",
        "protocol_sha256": "protocol_sha256",
        "reviewed_manifest": "reviewed_manifest",
        "container_name": "container_name",
        "volume": "volume_name",
    }
    if any(contract.get(k) != marker.get(v) for k, v in pairs.items()) or (
        contract.get("protocol_sha256") != io.PROTOCOL_SHA256
        or contract.get("freeze_sha256") != _digest(freeze_blob)
        or contract.get("launch_utc") != marker.get("reserved_at_utc")
        or contract.get("launch_monotonic") != marker.get("reserved_at_monotonic")
    ):
        raise LaunchError("monitor_reservation")
    container = contract.get("container")
    if type(container) is not str or _NAME.fullmatch(container) is None:
        raise LaunchError("monitor_contract")
    destination = contract_path.parent
    prior = sorted(destination.glob("status-*.json"))
    sequence = int(prior[-1].stem.rsplit("-", 1)[1]) + 1 if prior else 0
    info = _json_command(["docker", "container", "inspect", container], run=run)[0]
    _validate_container([info], image=str(contract["image"]), volume_name=str(contract["volume"]))
    if info.get("Id") != container or info.get("Name") != "/" + str(contract["container_name"]):
        raise LaunchError("monitor_identity")
    state = info.get("State")
    if type(state) is not dict:
        raise LaunchError("monitor_state")
    observed_utc = datetime.now(UTC)
    observed_monotonic = time.monotonic()
    utc_elapsed = (
        observed_utc - datetime.fromisoformat(str(contract["launch_utc"]))
    ).total_seconds()
    mono_elapsed = observed_monotonic - float(contract["launch_monotonic"])
    clock_discontinuity = utc_elapsed < 0 or mono_elapsed < 0
    elapsed = max(utc_elapsed, mono_elapsed, 0.0)
    contract_digest = _digest(contract_path.read_bytes())
    if prior:
        previous = _read_json(io._guard_path(prior[-1], destination, existing=True))
        if previous.get("contract_sha256") != contract_digest:
            raise LaunchError("monitor_clock_binding")
        previous_elapsed = float(previous["elapsed_seconds"])
        previous_monotonic = float(previous["monotonic"])
        previous_utc = datetime.fromisoformat(str(previous["utc"]))
        if not math.isfinite(previous_elapsed) or not math.isfinite(previous_monotonic):
            raise LaunchError("monitor_clock_schema")
        clock_discontinuity = (
            clock_discontinuity
            or previous.get("clock_discontinuity") is True
            or observed_utc < previous_utc
            or observed_monotonic < previous_monotonic
        )
        elapsed = max(elapsed, previous_elapsed)
    if not math.isfinite(elapsed) or not math.isfinite(observed_monotonic):
        raise LaunchError("monitor_clock_schema")
    _record(
        destination / f"status-{sequence:06d}.json",
        {
            "schema": 1,
            "utc": observed_utc.isoformat(),
            "monotonic": observed_monotonic,
            "contract_sha256": contract_digest,
            "elapsed_seconds": elapsed,
            "clock_discontinuity": clock_discontinuity,
            "state": state,
            "qualification": False,
            "authority": False,
        },
    )
    if state.get("Running") is True:
        if clock_discontinuity or elapsed >= EXTERNAL_WALL_SECONDS:
            stopped = _result(["docker", "stop", "--time", "10", container], run=run)
            if stopped.returncode != 0:
                raise LaunchError("timeout_stop")
        return {
            "classification": "CLOCK_DISCONTINUITY_INCOMPLETE"
            if clock_discontinuity
            else "RUNNING_NON_AUTHORITATIVE",
            "qualification": False,
            "authority": False,
        }
    copy_codes: dict[str, int] = {}
    remote_root = f"/work/var/verification/calendar-score-launcher/{contract['protocol_sha256']}"
    for name in ("started.json", "returned-result.json", "outcome.json", "launcher-error.json"):
        target = destination / ("copied-" + name)
        if target.exists():
            try:
                _read_json(io._guard_path(target, destination, existing=True))
                copy_codes[name] = 0
            except (LaunchError, io.StudyError, OSError):
                copy_codes[name] = -1
            continue
        try:
            copied = _result(
                ["docker", "cp", f"{container}:{remote_root}/{name}", str(target)], run=run
            )
        except (OSError, subprocess.TimeoutExpired):
            copy_codes[name] = -1
            continue
        copy_codes[name] = copied.returncode
        if copied.returncode == 0:
            try:
                _read_json(target)
            except LaunchError:
                copy_codes[name] = -1
    result_path = destination / "copied-returned-result.json"
    result = (
        _read_json(result_path)
        if result_path.exists() and copy_codes.get("returned-result.json") == 0
        else None
    )
    outcome_path = destination / "copied-outcome.json"
    bound_complete = False
    started_path = destination / "copied-started.json"
    if (
        result is not None
        and outcome_path.exists()
        and copy_codes.get("outcome.json") == 0
        and copy_codes.get("started.json") == 0
    ):
        copied_outcome = _read_json(outcome_path)
        copied_started = _read_json(started_path)
        bound_complete = (
            all(
                row.get("protocol_sha256") == contract.get("protocol_sha256")
                and row.get("reviewed_manifest") == contract.get("reviewed_manifest")
                for row in (copied_outcome, copied_started, result)
            )
            and copied_started.get("source_digest")
            == _digest(_canonical(freeze["manifest"]["sources"]))
            and copied_outcome.get("returned_state") == result.get("state")
            and result.get("namespace") == io.EXPERIMENT_NAMESPACE
            and result.get("sampling_executed") is True
            and result.get("study_permission") is False
            and result.get("children_exited") is True
            and copied_outcome.get("bound_complete") is True
        )
    if clock_discontinuity:
        bound_complete = False
    primary = classify_outcome(
        result,
        exit_code=int(state.get("ExitCode", -1)),
        oom_killed=state.get("OOMKilled") is True,
        bound_complete=bound_complete,
    )
    _record(destination / f"process-outcome-{sequence:06d}.json", primary)
    required = (
        {
            name: copy_codes[name]
            for name in ("started.json", "returned-result.json", "outcome.json")
        }
        if result is not None
        else {"launcher-error.json": copy_codes["launcher-error.json"]}
    )
    combined = monitor_outcome(primary, copy_returncodes=required)
    _record(destination / f"copy-outcome-{sequence:06d}.json", combined)
    return combined


def _main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    inside_parser = subparsers.add_parser("inside")
    inside_parser.add_argument("--freeze", type=Path, required=True)
    launch_parser = subparsers.add_parser("launch")
    launch_parser.add_argument("--image", required=True)
    launch_parser.add_argument("--head", required=True)
    launch_parser.add_argument("--reviewed-manifest", required=True)
    launch_parser.add_argument("--protocol", required=True)
    launch_parser.add_argument("--freeze", type=Path, required=True)
    launch_parser.add_argument("--name", required=True)
    launch_parser.add_argument("--volume", required=True)
    launch_parser.add_argument("--evidence-dir", type=Path, required=True)
    monitor_parser = subparsers.add_parser("monitor")
    monitor_parser.add_argument("--contract", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inside":
        result = inside(args.freeze)
        return (
            0
            if result["classification"]
            in {
                "FINAL_VERDICT_NON_AUTHORITATIVE",
                "DEVELOPMENT_FAILED_NON_AUTHORITATIVE",
                "UNDRAWN_READINESS_BLOCKER",
            }
            else 1
        )
    if args.command == "launch":
        launch(
            image=args.image,
            head=args.head,
            reviewed_manifest=args.reviewed_manifest,
            protocol_sha256=args.protocol,
            freeze_path=args.freeze,
            container_name=args.name,
            volume_name=args.volume,
            evidence_dir=args.evidence_dir,
        )
        return 0
    while monitor(args.contract)["classification"] == "RUNNING_NON_AUTHORITATIVE":
        time.sleep(60.0)
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
