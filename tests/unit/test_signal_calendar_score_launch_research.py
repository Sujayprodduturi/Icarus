from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from scripts.research import signal_calendar_score_launch as launch
from scripts.research import signal_calendar_score_phase as phase
from scripts.research import signal_calendar_score_runner_service as service
from scripts.research import signal_calendar_score_study as io

PROTOCOL = "a" * 64
MANIFEST = "b" * 64
HEAD = "c" * 40
IMAGE = "sha256:" + "d" * 64
SOURCE = "scripts/research/signal_calendar_score_launch.py"
SOURCE_DIGEST = hashlib.sha256(b"source").hexdigest()


def _freeze(path: Path, **changes: object) -> Path:
    value: dict[str, object] = {
        "schema": 1,
        "scope": "ARTIFICIAL_RESEARCH_LAUNCH_FREEZE_NO_AUTHORITY",
        "protocol_sha256": PROTOCOL,
        "reviewed_manifest": MANIFEST,
        "head": HEAD,
        "image": IMAGE,
        "manifest": {"protocol_sha256": PROTOCOL, "sources": {SOURCE: SOURCE_DIGEST}},
    }
    value.update(changes)
    path.write_text(json.dumps(value), encoding="utf-8")
    return path


def _patch_source_contract(monkeypatch: pytest.MonkeyPatch, project: Path) -> None:
    (project / SOURCE).parent.mkdir(parents=True, exist_ok=True)
    (project / SOURCE).write_bytes(b"source")
    monkeypatch.setattr(io, "SOURCE_PATHS", (SOURCE,))
    monkeypatch.setattr(phase, "EXTRA_SOURCES", ())
    monkeypatch.setattr(io, "PROJECT", project)
    monkeypatch.setattr(io, "PROTOCOL_SHA256", PROTOCOL)
    monkeypatch.setattr(io, "verify_manifest", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        launch, "_guard_launch_paths", lambda project, freeze, evidence: (freeze, evidence)
    )


class FakeRun:
    def __init__(
        self,
        *,
        source_blob: bytes = b"source",
        volume_exists: bool = False,
        image_fault: str | None = None,
        container_fault: str | None = None,
    ) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.source_blob = source_blob
        self.volume_exists = volume_exists
        self.volume_inspections = 0
        self.image_fault = image_fault
        self.container_fault = container_fault

    def __call__(self, command: list[str], **_: object) -> SimpleNamespace:
        row = tuple(command)
        self.calls.append(row)
        if row[:3] == ("git", "rev-parse", "HEAD"):
            return SimpleNamespace(returncode=0, stdout=HEAD + "\n", stderr="")
        if row[:3] == ("git", "diff", "--quiet"):
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if row[:3] == ("docker", "image", "inspect"):
            labels = {
                launch.IMAGE_HEAD_LABEL: HEAD,
                launch.IMAGE_MANIFEST_LABEL: MANIFEST,
                launch.IMAGE_PROTOCOL_LABEL: PROTOCOL,
                launch.IMAGE_SOURCES_LABEL: launch._digest(
                    launch._canonical({SOURCE: SOURCE_DIGEST})
                ),
                launch.IMAGE_DATA_OWNER_LABEL: "1000:1000",
            }
            payload: list[dict[str, Any]] = [
                {
                    "Id": IMAGE,
                    "Config": {
                        "User": "1000:1000",
                        "Env": [f"{name}=x" for name in sorted(launch.ALLOWED_IMAGE_ENV)],
                        "Labels": labels,
                        "WorkingDir": "/work",
                    },
                }
            ]
            if self.image_fault == "env":
                payload[0]["Config"]["Env"].append("BROKER_TOKEN=forbidden")
            elif self.image_fault == "head":
                payload[0]["Config"]["Labels"][launch.IMAGE_HEAD_LABEL] = "0" * 40
            elif self.image_fault == "owner":
                payload[0]["Config"]["Labels"][launch.IMAGE_DATA_OWNER_LABEL] = "0:0"
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if row[:3] == ("docker", "volume", "inspect"):
            self.volume_inspections += 1
            if self.volume_inspections > 1:
                payload = [
                    {
                        "Name": "new-volume",
                        "Labels": {"icarus.scope": "artificial-research-v3"},
                        "CreatedAt": "2100-01-01T00:00:00Z",
                    }
                ]
                return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
            return SimpleNamespace(
                returncode=0 if self.volume_exists else 1,
                stdout="[]",
                stderr="" if self.volume_exists else "No such volume",
            )
        if row[:3] == ("docker", "volume", "create"):
            return SimpleNamespace(returncode=0, stdout="volume\n", stderr="")
        if row[:2] == ("docker", "create"):
            return SimpleNamespace(returncode=0, stdout="container-id\n", stderr="")
        if row[:3] == ("docker", "container", "inspect"):
            container_payload: list[dict[str, Any]] = [
                {
                    "Id": "container-id",
                    "Name": "/new-container",
                    "Image": IMAGE,
                    "Config": {
                        "User": "1000:1000",
                        "Env": [
                            *[f"{name}=x" for name in sorted(launch.ALLOWED_IMAGE_ENV)],
                            "HOME=/work/var/home",
                            "TMPDIR=/work/var/tmp",
                        ],
                        "WorkingDir": "/work",
                        "Cmd": [
                            "python",
                            "-m",
                            "scripts.research.signal_calendar_score_launch",
                            "inside",
                            "--freeze=/work/var/reviewed-freeze.json",
                        ],
                    },
                    "HostConfig": {
                        "NetworkMode": "none",
                        "ReadonlyRootfs": True,
                        "CapDrop": ["ALL"],
                        "Memory": 4 * 1024**3,
                        "NanoCpus": 4_000_000_000,
                        "SecurityOpt": ["no-new-privileges=true"],
                        "RestartPolicy": {"Name": "no", "MaximumRetryCount": 0},
                    },
                    "Mounts": [
                        {
                            "Type": "volume",
                            "Name": "new-volume",
                            "Destination": "/work/var",
                            "RW": True,
                        }
                    ],
                }
            ]
            row_value = container_payload[0]
            host = row_value["HostConfig"]
            if self.container_fault == "network":
                host["NetworkMode"] = "bridge"
            elif self.container_fault == "restart":
                host["RestartPolicy"] = {"Name": "always", "MaximumRetryCount": 0}
            elif self.container_fault == "cpu":
                host["NanoCpus"] = 8_000_000_000
            elif self.container_fault == "memory":
                host["Memory"] = 8 * 1024**3
            elif self.container_fault == "mount":
                row_value["Mounts"][0]["Destination"] = "/work"
            elif self.container_fault == "command":
                row_value["Config"]["Cmd"] = ["python", "unsafe.py"]
            return SimpleNamespace(returncode=0, stdout=json.dumps(container_payload), stderr="")
        if row[:3] == ("docker", "cp", "container-id:/work/" + SOURCE):
            destination = Path(row[3]) / Path(SOURCE).name
            destination.write_bytes(self.source_blob)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        return SimpleNamespace(returncode=0, stdout="", stderr="")


def _launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fake: FakeRun) -> dict[str, object]:
    project = tmp_path / "project"
    _patch_source_contract(monkeypatch, project)
    verification = project / "var/verification"
    verification.mkdir(parents=True)
    return launch.launch(
        image=IMAGE,
        head=HEAD,
        reviewed_manifest=MANIFEST,
        protocol_sha256=PROTOCOL,
        freeze_path=_freeze(verification / "freeze.json"),
        container_name="new-container",
        volume_name="new-volume",
        evidence_dir=verification / "evidence",
        project=project,
        run=fake,
    )


def test_launch_reserves_before_mutation_and_starts_hardened_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRun()
    result = _launch(tmp_path, monkeypatch, fake)
    marker = (
        tmp_path
        / "project/var/research/calendar_score_v3/linux-launch-reservations"
        / f"{PROTOCOL}.json"
    )
    assert marker.is_file()
    assert result["classification"] == "RUNNING_NON_AUTHORITATIVE"
    create = next(row for row in fake.calls if row[:2] == ("docker", "create"))
    pairs = tuple(pairwise(create))
    assert ("--network", "none") in pairs
    assert ("--restart", "no") in pairs
    assert ("--cpus", "4") in pairs
    assert ("--memory", "4g") in pairs
    assert "type=volume,source=new-volume,target=/work/var" in create
    assert create[-5:] == (
        "python",
        "-m",
        "scripts.research.signal_calendar_score_launch",
        "inside",
        "--freeze=/work/var/reviewed-freeze.json",
    )
    assert fake.calls[-1] == ("docker", "start", "container-id")


@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("image", "sha256:" + "e" * 64),
        ("head", "f" * 40),
        ("reviewed_manifest", "1" * 64),
        ("protocol_sha256", "2" * 64),
        ("manifest", {}),
    ],
)
def test_wrong_frozen_contract_refuses_before_any_docker_call(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    bad: object,
) -> None:
    project = tmp_path / "project"
    _patch_source_contract(monkeypatch, project)
    verification = project / "var/verification"
    verification.mkdir(parents=True)
    fake = FakeRun()
    freeze = _freeze(verification / "freeze.json", **{field: bad})
    with pytest.raises(launch.LaunchError, match="freeze_contract"):
        launch.launch(
            image=IMAGE,
            head=HEAD,
            reviewed_manifest=MANIFEST,
            protocol_sha256=PROTOCOL,
            freeze_path=freeze,
            container_name="new-container",
            volume_name="new-volume",
            evidence_dir=verification / "evidence",
            project=project,
            run=fake,
        )
    assert fake.calls == []


@pytest.mark.parametrize("existing", [b"", b"partial"])
def test_any_existing_protocol_marker_is_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, existing: bytes
) -> None:
    project = tmp_path / "project"
    _patch_source_contract(monkeypatch, project)
    marker = (
        project / "var/research/calendar_score_v3/linux-launch-reservations" / f"{PROTOCOL}.json"
    )
    marker.parent.mkdir(parents=True)
    marker.write_bytes(existing)
    fake = FakeRun()
    with pytest.raises(launch.LaunchError, match="protocol_consumed"):
        _launch(tmp_path, monkeypatch, fake)
    assert not any(
        row[:3] == ("docker", "volume", "create")
        or row[:2] == ("docker", "create")
        or row[:2] == ("docker", "start")
        for row in fake.calls
    )


def test_existing_volume_is_retained_failure_after_reservation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRun(volume_exists=True)
    with pytest.raises(launch.LaunchError, match="volume_exists"):
        _launch(tmp_path, monkeypatch, fake)
    assert not any(row[:3] == ("docker", "volume", "create") for row in fake.calls)


def test_source_mismatch_never_starts_container(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = FakeRun(source_blob=b"changed")
    with pytest.raises(launch.LaunchError, match="image_source"):
        _launch(tmp_path, monkeypatch, fake)
    assert not any(row[:2] == ("docker", "start") for row in fake.calls)


@pytest.mark.parametrize("fault", ["env", "head", "owner"])
def test_wrong_image_contract_has_no_docker_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    fake = FakeRun(image_fault=fault)
    with pytest.raises(launch.LaunchError, match="image_contract"):
        _launch(tmp_path, monkeypatch, fake)
    assert not any(
        row[:3] == ("docker", "volume", "create")
        or row[:2] == ("docker", "create")
        or row[:2] == ("docker", "start")
        for row in fake.calls
    )


@pytest.mark.parametrize("fault", ["network", "restart", "cpu", "memory", "mount", "command"])
def test_wrong_created_container_is_never_started(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    fake = FakeRun(container_fault=fault)
    with pytest.raises(launch.LaunchError, match="container_contract"):
        _launch(tmp_path, monkeypatch, fake)
    assert not any(row[:2] == ("docker", "start") for row in fake.calls)


def test_source_allowlist_is_the_union_of_phase_closures(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(io, "SOURCE_PATHS", ("a", "b"))
    monkeypatch.setattr(phase, "EXTRA_SOURCES", ("b", "c"))
    assert launch._source_names() == ("a", "b", "c")


@pytest.mark.parametrize(
    ("state", "exit_code", "oom", "complete", "expected"),
    [
        ("FINAL_VERDICT", 0, False, True, "FINAL_VERDICT_NON_AUTHORITATIVE"),
        ("DEVELOPMENT_FAILED", 0, False, True, "DEVELOPMENT_FAILED_NON_AUTHORITATIVE"),
        ("ERROR", 0, False, False, "ERROR_INCOMPLETE"),
        (None, 0, False, False, "EMPTY_RESULT_INCOMPLETE"),
        ("FINAL_VERDICT", 1, False, True, "PROCESS_EXIT_INCOMPLETE"),
        ("FINAL_VERDICT", 137, True, True, "OOM_INCOMPLETE"),
        ("FINAL_VERDICT", 0, False, False, "BINDING_MISMATCH_INCOMPLETE"),
    ],
)
def test_outcome_classification_never_qualifies(
    state: str | None, exit_code: int, oom: bool, complete: bool, expected: str
) -> None:
    result: dict[str, object] | None = None if state is None else {"state": state}
    row = launch.classify_outcome(
        result, exit_code=exit_code, oom_killed=oom, bound_complete=complete
    )
    assert row == {"classification": expected, "qualification": False, "authority": False}


def test_inside_calls_only_public_runner_and_records_safe_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "inside"
    _patch_source_contract(monkeypatch, project)
    monkeypatch.setattr(launch, "PROJECT", project)
    monkeypatch.setattr(launch, "_uid", lambda: 1000)
    monkeypatch.setattr(launch, "_gid", lambda: 1000)
    monkeypatch.setattr(launch, "_is_linux", lambda: True)
    manifest = SimpleNamespace(
        payload={"protocol_sha256": PROTOCOL, "sources": {SOURCE: SOURCE_DIGEST}},
        digest=MANIFEST,
    )
    monkeypatch.setattr(phase, "phase_manifest", lambda: manifest)
    data_root = project / "var"
    data_root.mkdir(parents=True)
    freeze = _freeze(data_root / "freeze.json")
    monkeypatch.setattr(io, "_guard_path", lambda path, root, existing=False: path)

    class NamedFailure(RuntimeError):
        pass

    def fail(_: str) -> dict[str, object]:
        raise NamedFailure("secret must not be logged")

    with pytest.raises(NamedFailure):
        launch.inside(freeze, run_reviewed_study=fail, filesystem_check=lambda: None)
    record = json.loads(
        (
            project / f"var/verification/calendar-score-launcher/{PROTOCOL}/launcher-error.json"
        ).read_text()
    )
    assert record["error_category"] == "NamedFailure"
    assert "secret" not in json.dumps(record)
    assert record["qualification"] is False


def test_failed_copy_does_not_replace_primary_process_outcome(tmp_path: Path) -> None:
    primary = launch.classify_outcome(
        {"state": "ERROR"}, exit_code=1, oom_killed=False, bound_complete=False
    )
    combined = launch.monitor_outcome(primary, copy_returncodes={"outcome.json": 1})
    assert combined["classification"] == "PROCESS_EXIT_INCOMPLETE"
    assert combined["copy_error"] is True
    assert combined["qualification"] is False


@pytest.mark.parametrize(
    "damage",
    [
        None,
        "session_id",
        "scope",
        "development_paths",
        "action",
        "control_decision",
        "reviewer",
        "helper",
    ],
)
def test_final_completion_requires_actual_phase_dimensions_and_bound_approvals(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, damage: str | None
) -> None:
    binding = phase.SourceBinding(PROTOCOL, MANIFEST, "resources", "e" * 64)
    monkeypatch.setattr(phase, "current_binding", lambda: binding)
    monkeypatch.setattr(io, "EXPERIMENT_NAMESPACE", "icarus/calendar-score-research/v3")
    decisions = {"development": "PASS", "validation": "FAILED"}
    evidence: dict[str, dict[str, object]] = {
        name: {"phase": name, "decision": decision} for name, decision in decisions.items()
    }
    monkeypatch.setattr(
        service,
        "_evidence_check",
        lambda registry, name, source, _scan_payload=False: evidence[name],
    )
    result: dict[str, object] = {
        "state": "FINAL_VERDICT",
        "namespace": io.EXPERIMENT_NAMESPACE,
        "study_permission": False,
        "sampling_executed": True,
        "children_exited": True,
        "release_transfers": 1,
    }
    for name in decisions:
        result[name + "_paths"], result[name + "_metrics"] = io.phase_totals(name)
    attempt = {key: value for key, value in result.items() if key != "children_exited"}
    attempt.update(schema=1, scope="ARTIFICIAL_RESEARCH_ONLY", session_id="session", utc="utc")
    reserved: dict[str, object] = {
        "session_id": "session",
        "namespace": io.EXPERIMENT_NAMESPACE,
        "attempt_id": io.PROTOCOL_SHA256,
        "source_binding": {
            "protocol_digest": PROTOCOL,
            "manifest_digest": MANIFEST,
            "resource_id": "resources",
            "resource_digest": "e" * 64,
        },
        "owner": {"peer": "primary"},
        "reviewer": {"peer": "reviewer"},
    }
    registration = {
        "schema": 1,
        "utc": "utc",
        "state": "COORDINATOR_REGISTERED",
        "namespace": io.EXPERIMENT_NAMESPACE,
        "attempt_id": io.PROTOCOL_SHA256,
        "session_id": "session",
        "coordinator": reserved["owner"],
        "reviewer": reserved["reviewer"],
        "helper": {"peer": "helper"},
        "source_binding": reserved["source_binding"],
        "reservation_digest": launch._digest(io.canonical_json(reserved)),
        "source_review_digest": MANIFEST,
    }
    for row in evidence.values():
        row["binding"] = {"session_id": "session", "attempt_id": io.PROTOCOL_SHA256}
    approvals = {
        name: {
            "action": "approve-" + name,
            "control_decision": decisions[name],
            "schema": 1,
            "utc": "utc",
            "scope": "ARTIFICIAL_RESEARCH_ONLY",
            "state": "REVIEW_APPROVED",
            "source_review_digest": MANIFEST,
            "evidence": evidence[name],
            "reviewer": registration["reviewer"],
            "helper": registration["helper"],
        }
        for name in decisions
    }
    if damage in ("session_id", "scope", "development_paths"):
        attempt[damage] = "corrupt"
    elif damage is not None:
        approvals["development"][damage] = "corrupt"
    attempt["source_binding"] = {
        "protocol_digest": PROTOCOL,
        "manifest_digest": MANIFEST,
        "resource_id": "resources",
        "resource_digest": "e" * 64,
    }

    def read_record(root: Path, name: str) -> dict[str, object]:
        if name == "attempt-result.json":
            return attempt
        if name == "attempt-reserved.json":
            return reserved
        if name == "attempt-registration.json":
            return registration
        phase_name = name.removesuffix("-reviewer-approved.json")
        return approvals[phase_name]

    monkeypatch.setattr(phase, "_read_record", read_record)
    assert launch._verify_completion(result, tmp_path) is (damage is None)
    attempt["source_binding"] = {}
    assert launch._verify_completion(result, tmp_path) is False


def test_new_volume_accepts_docker_whole_second_creation_time() -> None:
    reserved = datetime.fromisoformat("2026-10-07T12:34:56.123456+00:00")
    info = [
        {
            "Name": "new-volume",
            "Labels": {"icarus.scope": "artificial-research-v3"},
            "CreatedAt": "2026-10-07T12:34:56Z",
        }
    ]
    launch._validate_new_volume(info, name="new-volume", reserved_at=reserved)
    info[0]["CreatedAt"] = "2026-10-07T12:34:55Z"
    with pytest.raises(launch.LaunchError, match="volume_contract"):
        launch._validate_new_volume(info, name="new-volume", reserved_at=reserved)


@pytest.mark.parametrize("kind", ["image", "container"])
def test_inherited_entrypoint_cannot_replace_reviewed_entry(kind: str) -> None:
    fake = FakeRun()

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        value = fake(command, **kwargs)
        rows = json.loads(value.stdout)
        rows[0]["Config"]["Entrypoint"] = ["unsafe.py"]
        value.stdout = json.dumps(rows)
        return value

    with pytest.raises(launch.LaunchError, match=kind + "_contract"):
        if kind == "image":
            launch._validate_image(
                IMAGE,
                head=HEAD,
                reviewed_manifest=MANIFEST,
                protocol_sha256=PROTOCOL,
                sources={SOURCE: SOURCE_DIGEST},
                run=run,
            )
        else:
            rows = json.loads(run(["docker", "container", "inspect", "container-id"]).stdout)
            launch._validate_container(rows, image=IMAGE, volume_name="new-volume")


@pytest.mark.parametrize(
    "mode",
    [
        "final",
        "oom",
        "copy-failed",
        "copy-timeout",
        "stale-copy",
        "timeout",
        "clock-reset",
        "utc-regression",
        "prior-cap",
    ],
)
def test_monitor_real_control_flow_preserves_outcomes(
    mode: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRun()
    row = _launch(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(launch, "PROJECT", io.PROJECT)
    contract_path = Path(str(row["contract"]))
    contract = json.loads(contract_path.read_bytes())
    # Fixed clocks and real launcher reservation; no Docker process is invoked.
    anchor = float(contract["launch_monotonic"])
    monkeypatch.setattr(
        time,
        "monotonic",
        lambda: anchor + (301201 if mode == "timeout" else (-1 if mode == "clock-reset" else 1)),
    )
    if mode in ("utc-regression", "prior-cap"):
        launch._record(
            contract_path.parent / "status-000000.json",
            {
                "schema": 1,
                "contract_sha256": launch._digest(contract_path.read_bytes()),
                "utc": (
                    datetime.now(UTC) + timedelta(seconds=10 if mode == "utc-regression" else -1)
                ).isoformat(),
                "monotonic": anchor,
                "elapsed_seconds": 301201 if mode == "prior-cap" else 0,
                "clock_discontinuity": False,
            },
        )
    calls: list[list[str]] = []

    def run(command: list[str], **kwargs: object) -> SimpleNamespace:
        calls.append(command)
        if command[:3] == ["docker", "container", "inspect"]:
            value = fake(command, **kwargs)
            rows = json.loads(value.stdout)
            rows[0]["State"] = {
                "Running": mode in ("timeout", "clock-reset", "utc-regression", "prior-cap"),
                "ExitCode": 137 if mode == "oom" else 0,
                "OOMKilled": mode == "oom",
            }
            value.stdout = json.dumps(rows)
            return value
        if command[:2] == ["docker", "stop"]:
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        assert command[:2] == ["docker", "cp"]
        name = command[2].rsplit("/", 1)[1]
        target = Path(command[3])
        if mode == "copy-timeout":
            raise subprocess.TimeoutExpired(command, 30)
        if mode == "copy-failed" or name == "launcher-error.json":
            return SimpleNamespace(returncode=1, stdout="", stderr="not present")
        payload: dict[str, object] = {"protocol_sha256": PROTOCOL, "reviewed_manifest": MANIFEST}
        if name == "started.json":
            payload["source_digest"] = launch._digest(launch._canonical({SOURCE: SOURCE_DIGEST}))
        elif name == "returned-result.json":
            payload.update(
                {
                    "state": "FINAL_VERDICT",
                    "namespace": io.EXPERIMENT_NAMESPACE,
                    "study_permission": False,
                    "sampling_executed": True,
                    "children_exited": True,
                    "release_transfers": 1,
                }
            )
        else:
            payload.update({"returned_state": "FINAL_VERDICT", "bound_complete": True})
        if mode == "stale-copy" and name == "started.json":
            payload["reviewed_manifest"] = "0" * 64
        target.write_text(json.dumps(payload))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    result = launch.monitor(contract_path, run=run)
    assert result["qualification"] is False and result["authority"] is False
    if mode in ("timeout", "clock-reset", "utc-regression", "prior-cap"):
        assert any(command[:2] == ["docker", "stop"] for command in calls)
        if mode in ("clock-reset", "utc-regression"):
            assert result["classification"] == "CLOCK_DISCONTINUITY_INCOMPLETE"
    elif mode == "oom":
        assert result["classification"] == "OOM_INCOMPLETE"
    elif mode in ("copy-failed", "copy-timeout"):
        assert (
            result["classification"] == "EMPTY_RESULT_INCOMPLETE" and result["copy_error"] is True
        )
    elif mode == "stale-copy":
        assert result["classification"] == "BINDING_MISMATCH_INCOMPLETE"
    else:
        assert (
            result["classification"] == "FINAL_VERDICT_NON_AUTHORITATIVE"
            and result["copy_error"] is False
        )
    assert not any(command[1] in ("start", "restart", "create", "rm") for command in calls)


@pytest.mark.parametrize("field", ["image", "head", "reviewed_manifest", "volume", "freeze_sha256"])
def test_resumed_monitor_refuses_changed_contract_before_docker(
    field: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake = FakeRun()
    row = _launch(tmp_path, monkeypatch, fake)
    monkeypatch.setattr(launch, "PROJECT", io.PROJECT)
    path = Path(str(row["contract"]))
    contract = json.loads(path.read_bytes())
    contract[field] = "changed"
    path.write_text(json.dumps(contract))
    prior = len(fake.calls)
    with pytest.raises(launch.LaunchError):
        launch.monitor(path, run=fake)
    assert len(fake.calls) == prior


def test_partial_reservation_write_stays_consumed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    args = dict(
        protocol_sha256=PROTOCOL,
        image=IMAGE,
        head=HEAD,
        reviewed_manifest=MANIFEST,
        container_name="first",
        volume_name="first",
    )

    def fail(_: int) -> None:
        raise OSError("fixture fsync failure")

    monkeypatch.setattr(os, "fsync", fail)
    with pytest.raises(OSError):
        launch._reserve(tmp_path, **args)
    args.update(container_name="renamed", volume_name="renamed")
    with pytest.raises(launch.LaunchError, match="protocol_consumed"):
        launch._reserve(tmp_path, **args)


@pytest.mark.parametrize(
    "reason,expected", [("transport", "transport"), ("private-key-text", "unknown")]
)
def test_inside_retains_safe_error_stage_and_reason(
    reason: str,
    expected: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project = tmp_path / "inside"
    _patch_source_contract(monkeypatch, project)
    monkeypatch.setattr(launch, "PROJECT", project)
    monkeypatch.setattr(launch, "_uid", lambda: 1000)
    monkeypatch.setattr(launch, "_gid", lambda: 1000)
    monkeypatch.setattr(launch, "_is_linux", lambda: True)
    manifest = SimpleNamespace(
        payload={"protocol_sha256": PROTOCOL, "sources": {SOURCE: SOURCE_DIGEST}}, digest=MANIFEST
    )
    monkeypatch.setattr(phase, "phase_manifest", lambda: manifest)
    data = project / "var"
    data.mkdir(parents=True)
    freeze = _freeze(data / "freeze.json")
    monkeypatch.setattr(io, "_guard_path", lambda path, root, existing=False: path)
    result = launch.inside(
        freeze,
        filesystem_check=lambda: None,
        run_reviewed_study=lambda digest: {
            "state": "ERROR",
            "failure_stage": "validation",
            "failure_reason": reason,
        },
    )
    assert result["classification"] == "ERROR_INCOMPLETE"
    returned = json.loads(
        (
            project / f"var/verification/calendar-score-launcher/{PROTOCOL}/returned-result.json"
        ).read_bytes()
    )
    assert returned["failure_stage"] == "validation" and returned["failure_reason"] == expected
    assert "private-key-text" not in json.dumps(returned)


@pytest.mark.parametrize("registry_name", ["wrong-protocol", PROTOCOL])
def test_inside_accepts_only_exact_protocol_registry(
    registry_name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "inside-registry"
    _patch_source_contract(monkeypatch, project)
    monkeypatch.setattr(launch, "PROJECT", project)
    monkeypatch.setattr(launch, "_uid", lambda: 1000)
    monkeypatch.setattr(launch, "_gid", lambda: 1000)
    monkeypatch.setattr(launch, "_is_linux", lambda: True)
    current = SimpleNamespace(
        payload={"protocol_sha256": PROTOCOL, "sources": {SOURCE: SOURCE_DIGEST}},
        digest=MANIFEST,
    )
    monkeypatch.setattr(phase, "phase_manifest", lambda: current)
    data = project / "var"
    data.mkdir(parents=True)
    freeze = _freeze(data / "freeze.json")
    root = data / "research/calendar_score_v3"
    registry = root / "attempts" / registry_name
    registry.mkdir(parents=True)
    monkeypatch.setattr(io, "EXPERIMENT_ROOT", root)
    monkeypatch.setattr(io, "_guard_path", lambda path, root, existing=False: path.resolve())
    seen: list[Path] = []

    def verify(result: dict[str, object], path: Path) -> bool:
        seen.append(path)
        return True

    monkeypatch.setattr(launch, "_verify_completion", verify)
    launch.inside(
        freeze,
        filesystem_check=lambda: None,
        run_reviewed_study=lambda digest: {"state": "FINAL_VERDICT", "registry": str(registry)},
    )
    assert seen == ([registry.resolve()] if registry_name == PROTOCOL else [])
