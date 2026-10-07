"""Full phase contracts; all generated fixtures remain in the TEST domain."""

from __future__ import annotations

import importlib
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any, NoReturn

import pytest


def phase_module() -> ModuleType:
    assert importlib.util.find_spec("scripts.research.signal_calendar_score_phase") is not None
    return importlib.import_module("scripts.research.signal_calendar_score_phase")


@pytest.mark.parametrize(
    "name,paths,metrics", [("development", 81920, 229376), ("validation", 327680, 917504)]
)
def test_actual_plan_has_frozen_lazy_order(name: object, paths: int, metrics: int) -> None:
    phase = phase_module()
    plan = phase.actual_plan(name)
    assert (plan.paths, plan.metrics) == (paths, metrics)
    identities = phase.iter_paths(plan)
    assert iter(identities) is identities
    assert next(identities) == ("P1", 2048, 0)
    last = None
    for identity in identities:
        last = identity
    assert last == ("L1", 2048, plan.replicates - 1)


@pytest.mark.parametrize("name", ["test_fixture", "", True, 1, None])
def test_actual_plan_refuses_unknown_or_boolean_phase(name: object) -> None:
    phase = phase_module()
    with pytest.raises(phase.PhaseError):
        phase.actual_plan(name)


def test_test_phase_roundtrip_has_candidate_only_and_independent_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    plan = phase._test_plan("development")
    root = tmp_path / "roundtrip"
    root.mkdir()
    claim = phase._prepare_test_claim(root, plan)
    capability = phase._test_capability(root, claim)
    observations: list[Any] = []
    produced = phase.write_phase(root, claim, capability, observations.append)
    assert (produced.paths, produced.metrics, produced.payload_bytes) == (10, 28, 231492)
    assert produced.decision == "UNAVAILABLE_TEST_ONLY"
    assert not (root / "phase-terminal.json").exists()
    assert (root / "phase-terminal-candidate.json").exists()
    assert observations[-1].paths == 10
    phase._publish_test_terminal(root, produced)
    checked = phase.verify_phase(
        root, phase._hash(claim), phase.current_binding(), "primary", observations.append
    )
    assert checked.summary == produced.summary
    assert checked.words == produced.words
    assert checked.payload_digest == produced.payload_digest
    assert not (root / "verified-primary.json").exists()
    assert (root / "verified-primary-candidate.json").exists()


def test_public_stream_stays_refused_before_hash_with_forged_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.research import signal_calendar_score_study as study

    called: list[Any] = []
    monkeypatch.setattr(study, "_counter_digest", lambda *args: called.append(args))
    with pytest.raises(study.StudyError):
        study.CounterStream(
            namespace=study.EXPERIMENT_NAMESPACE,
            phase="development",
            profile_id="P1",
            n=2048,
            replicate=0,
            root=bytes(32),
            _capability=object(),
        )
    assert called == []


def test_test_claim_cannot_mint_experimental_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "forged"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    import json

    value = json.loads(claim)
    value["namespace"] = "icarus/calendar-score-research/v3"
    forged = phase.io.canonical_json(value)
    with pytest.raises(phase.PhaseError):
        phase._test_capability(root, forged)


@pytest.mark.parametrize("field", ["replicates", "raw_cap", "metadata_cap", "overhead_cap"])
def test_plan_refuses_equal_float_fields(field: str) -> None:
    from dataclasses import replace

    phase = phase_module()
    plan = phase.actual_plan("development")
    altered = replace(plan, **{field: float(getattr(plan, field))})
    with pytest.raises(phase.PhaseError):
        phase._validate_plan(altered)


@pytest.mark.parametrize("column", [1, 2])
def test_plan_refuses_equal_float_geometry(column: int) -> None:
    from dataclasses import replace

    phase = phase_module()
    plan = phase.actual_plan("development")
    first = list(plan.geometries[0])
    first[column] = float(first[column])
    altered = replace(plan, geometries=(tuple(first), *plan.geometries[1:]))
    with pytest.raises(phase.PhaseError):
        phase._validate_plan(altered)


@pytest.fixture
def saved_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[ModuleType, Path, bytes, Any]:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "phase"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    cap = phase._test_capability(root, claim)
    produced = phase.write_phase(root, claim, cap, lambda _: None)
    phase._publish_test_terminal(root, produced)
    return phase, root, claim, produced


@pytest.mark.parametrize(
    "fault",
    [
        "missing",
        "duplicate",
        "reorder",
        "extra",
        "bool_words",
        "bool_n",
        "unknown_schema",
        "unknown_field",
        "word_count",
        "endpoint",
        "payload_hash",
        "noncanonical",
        "truncated",
        "extra_payload",
        "false_report",
        "false_terminal",
    ],
)
def test_saved_phase_corruption_never_emits_receipt(
    saved_phase: tuple[ModuleType, Path, bytes, Any], fault: str
) -> None:
    import json

    phase, root, claim, _ = saved_phase
    path = root / "phase-index.jsonl"
    rows = [json.loads(line) for line in path.read_bytes().splitlines()]
    if fault == "missing":
        rows.pop(2)
    elif fault == "duplicate":
        rows.insert(2, rows[1])
    elif fault == "reorder":
        rows[1], rows[2] = rows[2], rows[1]
    elif fault == "extra":
        rows.append(rows[-1])
    elif fault == "bool_words":
        rows[1]["words"] = True
    elif fault == "bool_n":
        rows[1]["n"] = True
    elif fault == "unknown_schema":
        rows[1]["schema"] = 2
    elif fault == "unknown_field":
        rows[1]["ignored"] = "no"
    elif fault == "word_count":
        rows[1]["words"] += 1
    elif fault == "endpoint":
        rows[1]["results"][0]["lower"][0] += 1
    elif fault == "payload_hash":
        rows[1]["payload_sha256"] = "0" * 64
    if fault in {"truncated", "extra_payload"}:
        payload = root / "phase-payload.bin"
        content = payload.read_bytes()
        payload.write_bytes(content[:-1] if fault == "truncated" else content + b"x")
    elif fault in {"false_report", "false_terminal"}:
        record_path = root / (
            "phase-report.json" if fault == "false_report" else "phase-terminal.json"
        )
        value = json.loads(record_path.read_bytes())
        value["counts"]["paths"] = True
        record_path.write_bytes(phase.io.canonical_json(value))
    elif fault == "noncanonical":
        path.write_bytes(b" " + path.read_bytes())
    else:
        path.write_bytes(b"".join(phase.io.canonical_json(row) for row in rows))
    with pytest.raises(phase.io.StudyError):
        phase.verify_phase(
            root, phase._hash(claim), phase.current_binding(), "primary", lambda _: None
        )
    assert not (root / "verified-primary-candidate.json").exists()
    assert not (root / "verified-primary.json").exists()


def test_reference_replay_never_calls_production_math(
    saved_phase: tuple[ModuleType, Path, bytes, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    phase, root, claim, _ = saved_phase

    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("production calculator reused")

    monkeypatch.setattr(phase.io, "generate_payload", forbidden)
    monkeypatch.setattr(phase.io, "evaluate_payload", forbidden)
    result = phase.verify_phase(
        root, phase._hash(claim), phase.current_binding(), "primary", lambda _: None
    )
    assert result.paths == 10


def test_consumed_active_words_and_original_error_survive_close_fault(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "failure"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    original = RuntimeError("evaluation failed")
    original_close = phase.io.CanonicalRecordWriter.close

    def fail_evaluation(*args: Any) -> NoReturn:
        raise original

    def fail_close(writer: Any) -> NoReturn:
        original_close(writer)
        raise OSError("close failed")

    monkeypatch.setattr(phase.io, "evaluate_payload", fail_evaluation)
    monkeypatch.setattr(phase.io.CanonicalRecordWriter, "close", fail_close)
    with pytest.raises(RuntimeError) as caught:
        phase.write_phase(root, claim, capability, lambda _: None)
    assert caught.value is original
    assert "Owned shutdown: OSError" in original.__notes__
    failure = json.loads((root / "phase-writer-failure.json").read_bytes())
    assert failure["completed"]["active_words"] == 12300
    assert failure["completed"]["paths"] == 0
    assert not (root / "phase-terminal-candidate.json").exists()
    assert not (root / "phase-terminal.json").exists()
    with pytest.raises(phase.PhaseError):
        phase.write_phase(root, claim, capability, lambda _: None)


def test_private_claimed_reference_uses_literal_framing_without_math_reuse(
    saved_phase: tuple[ModuleType, Path, bytes, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    phase, root, claim, produced = saved_phase
    identity = {
        "namespace": phase.io.TEST_NAMESPACE,
        "phase": "test_fixture",
        "profile_id": "P1",
        "n": 2048,
        "replicate": 0,
        "root": "0" * 64,
    }
    payload = (root / "phase-payload.bin").read_bytes()[:2050]

    def forbidden(*args: Any, **kwargs: Any) -> NoReturn:
        raise AssertionError("production math reused")

    monkeypatch.setattr(phase.io, "generate_payload", forbidden)
    monkeypatch.setattr(phase.io, "evaluate_payload", forbidden)
    result = phase.reference._claimed_reference_path(
        "P1", 2048, payload, identity, root, claim, phase.current_binding()
    )
    assert result.words == 12300
    assert (
        result.rows[0]["total"]
        == phase.reference.reference_path("P1", 2048, payload, identity).rows[0]["total"]
    )
    assert produced.words > result.words


@pytest.mark.parametrize(
    "field,value",
    [
        ("namespace", "icarus/calendar-score-research/v3"),
        ("phase", "validation"),
        ("root", "1" * 64),
        ("replicate", True),
        ("replicate", 1),
        ("n", 2048.0),
    ],
)
def test_claimed_replay_refuses_wrong_identity_before_sha(
    saved_phase: tuple[ModuleType, Path, bytes, Any],
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: Any,
) -> None:
    phase, root, claim, _ = saved_phase
    identity = {
        "namespace": phase.io.TEST_NAMESPACE,
        "phase": "test_fixture",
        "profile_id": "P1",
        "n": 2048,
        "replicate": 0,
        "root": "0" * 64,
    }
    identity[field] = value
    calls: list[Any] = []
    monkeypatch.setattr(phase.reference, "_digest", lambda *args: calls.append(args))
    with pytest.raises(phase.reference.VerificationError):
        phase.reference._claimed_reference_path(
            "P1", 2048, bytes(2050), identity, root, claim, phase.current_binding()
        )
    assert calls == []


@pytest.mark.parametrize(
    "field,value", [("arithmetic", False), ("precision", False), ("count", 2047)]
)
def test_formal_refusal_stops_before_append_with_active_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    import json
    from dataclasses import replace

    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "formal-error"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    original = phase.io.evaluate_payload

    def refused(item: Any, payload: Any) -> Any:
        result = original(item, payload)
        return replace(result, rows=(replace(result.rows[0], **{field: value}), *result.rows[1:]))

    monkeypatch.setattr(phase.io, "evaluate_payload", refused)
    with pytest.raises(phase.PhaseError):
        phase.write_phase(root, claim, capability, lambda _: None)
    assert (root / "phase-payload.bin").stat().st_size == 0
    failure = json.loads((root / "phase-writer-failure.json").read_bytes())
    assert failure["completed"]["active_words"] == 12300
    assert failure["completed"]["paths"] == 0
    assert not (root / "phase-terminal-candidate.json").exists()


def test_source_drift_during_evaluation_refuses_before_path_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "source-error"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    original = phase.io.evaluate_payload
    manifest = phase.phase_manifest()

    def drift(item: Any, payload: Any) -> Any:
        result = original(item, payload)
        monkeypatch.setattr(
            phase, "phase_manifest", lambda: phase.io.Manifest(manifest.payload, "0" * 64)
        )
        return result

    monkeypatch.setattr(phase.io, "evaluate_payload", drift)
    with pytest.raises(phase.PhaseError):
        phase.write_phase(root, claim, capability, lambda _: None)
    assert (root / "phase-payload.bin").stat().st_size == 0
    assert len((root / "phase-index.jsonl").read_bytes().splitlines()) == 1
    failure = json.loads((root / "phase-writer-failure.json").read_bytes())
    assert failure["completed"]["active_words"] == 12300
    assert failure["completed"]["paths"] == 0


@pytest.mark.parametrize("value", ["2026-10-05T12:00:00", True, "not-a-time"])
def test_claim_refuses_noncanonical_utc_before_words(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, value: Any
) -> None:
    import json

    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "utc"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    parsed = json.loads(claim)
    assert "utc" in parsed
    parsed["utc"] = value
    forged = phase.io.canonical_json(parsed)
    (root / "phase-claim.json").write_bytes(forged)
    with pytest.raises(phase.PhaseError):
        phase._test_capability(root, forged)


@pytest.mark.parametrize("fault", ["root", "claim", "source"])
def test_capability_refusal_is_terminal_for_recognized_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "revoke"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    if fault == "source":
        manifest = phase.phase_manifest()
        monkeypatch.setattr(
            phase, "phase_manifest", lambda: phase.io.Manifest(manifest.payload, "0" * 64)
        )
        with pytest.raises(phase.PhaseError):
            phase._authorize_stream(
                capability,
                {
                    "namespace": phase.io.TEST_NAMESPACE,
                    "phase": "test_fixture",
                    "profile_id": "P1",
                    "n": 2048,
                    "replicate": 0,
                    "root": bytes(32),
                },
            )
        monkeypatch.setattr(phase, "phase_manifest", lambda: manifest)
    else:
        with pytest.raises(phase.PhaseError):
            phase.write_phase(
                root / "wrong" if fault == "root" else root,
                claim + b"x" if fault == "claim" else claim,
                capability,
                lambda _: None,
            )
    with pytest.raises(phase.PhaseError):
        phase._capability(capability)


def test_unknown_capability_does_not_revoke_other_live_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "foreign"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    with pytest.raises(phase.PhaseError):
        phase.write_phase(root, claim, object(), lambda _: None)
    assert phase._capability(capability).valid is True


def test_control_record_reserves_exact_serialized_bytes_before_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    plan = phase._test_plan("development")
    seen: list[int] = []

    def bounded(root: Path, actual: Any, raw: int, index: int, *, added_control: int = 0) -> None:
        seen.append(added_control)
        if added_control:
            raise phase.PhaseError("cap")

    monkeypatch.setattr(phase, "_storage", bounded)
    with pytest.raises(phase.PhaseError):
        phase._record(tmp_path, "candidate.json", {"schema": 1}, plan=plan)
    assert seen and seen[0] == len(phase.io.canonical_json({"utc": phase._utc(), "schema": 1}))
    assert not (tmp_path / "candidate.json").exists()


def test_test_writer_and_replay_execute_full_claim_check_frequency(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "frequency"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development", preflight=True))
    capability = phase._test_capability(root, claim)
    original = phase.validate_claim
    calls: list[int] = []

    def check(*args: Any, **kwargs: Any) -> Any:
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(phase, "validate_claim", check)
    produced = phase.write_phase(root, claim, capability, lambda _: None)
    assert len(calls) == 22
    phase._publish_test_terminal(root, produced)
    calls.clear()
    phase.verify_phase(root, phase._hash(claim), phase.current_binding(), "primary", lambda _: None)
    assert len(calls) == 22


def test_constructor_invalid_identity_revokes_only_recognized_capability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    monkeypatch.setattr(phase, "TEST_ANCHOR", tmp_path)
    root = tmp_path / "invalid-constructor"
    root.mkdir()
    claim = phase._prepare_test_claim(root, phase._test_plan("development"))
    capability = phase._test_capability(root, claim)
    with pytest.raises(phase.io.StudyError):
        phase.io.CounterStream(
            namespace=phase.io.TEST_NAMESPACE,
            phase="test_fixture",
            profile_id="P1",
            n=True,
            replicate=0,
            root=bytes(32),
            _capability=object(),
        )
    assert phase._capability(capability).valid is True
    with pytest.raises(phase.io.StudyError):
        phase.io.CounterStream(
            namespace=phase.io.TEST_NAMESPACE,
            phase="test_fixture",
            profile_id="P1",
            n=True,
            replicate=0,
            root=bytes(32),
            _capability=capability,
        )
    with pytest.raises(phase.PhaseError):
        phase._capability(capability)


def test_owned_fixture_replay_consumes_setup_and_each_path_permit_checks(
    saved_phase: tuple[ModuleType, Path, bytes, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    phase, root, claim, _ = saved_phase
    runner = importlib.import_module("scripts.research.signal_calendar_score_runner")
    setup: list[int] = []
    checks: list[int] = []
    original = phase._check_replay_permit
    monkeypatch.setattr(runner, "_validate_worker_registration", lambda *a: setup.append(1))

    def checked(*args: Any, **kwargs: Any) -> None:
        checks.append(1)
        original(*args, **kwargs)

    monkeypatch.setattr(phase, "_check_replay_permit", checked)
    phase.verify_phase(
        root,
        phase._hash(claim),
        phase.current_binding(),
        "primary",
        lambda _: None,
        _worker_marker=object(),
    )
    assert setup == [1]
    assert len(checks) == 10
    permit = next(reversed(phase._FIXTURE_REPLAY_PERMITS.values()))
    with pytest.raises(phase.PhaseError, match="replay_issuer"):
        phase._check_replay_permit(permit, root, claim, phase.current_binding())


@pytest.mark.parametrize("damage", ["bytes", "delete", "symlink"])
def test_lexical_path_reuse_keeps_fresh_reads_and_independent_mappings(
    damage: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import hashlib

    phase = phase_module()
    io = phase.io
    resource = io.load_operational_resources()
    source = tmp_path / "source.txt"
    source.write_bytes(b"first")
    monkeypatch.setattr(io, "PROJECT", tmp_path)
    monkeypatch.setattr(io, "SOURCE_PATHS", ("source.txt",))
    monkeypatch.setattr(phase, "EXTRA_SOURCES", ())
    monkeypatch.setattr(
        io, "PROTOCOL_DOCUMENTS", {"source.txt": hashlib.sha256(b"first").hexdigest()}
    )
    monkeypatch.setattr(io, "load_operational_resources", lambda: resource)
    metadata_calls: list[str] = []

    def version(name: str) -> str:
        metadata_calls.append(name)
        return "fixture"

    monkeypatch.setattr(io, "_fresh_package_version", version)
    original = io.manifest_for_paths
    seen: list[Path] = []
    reads: list[Path] = []
    read = Path.read_bytes

    def fresh_read(path: Path) -> bytes:
        reads.append(path)
        return read(path)

    def capture(paths: dict[str, Path], **kwargs: Any) -> Any:
        seen.append(paths["source.txt"])
        result = original(paths, **kwargs)
        paths.clear()
        return result

    monkeypatch.setattr(Path, "read_bytes", fresh_read)
    monkeypatch.setattr(io, "manifest_for_paths", capture)
    first = phase.phase_manifest()
    second = phase.phase_manifest()
    assert first == second
    assert seen[0] is seen[1]
    assert reads == [source] * 4
    assert metadata_calls == ["psutil", "numpy"] * 2
    if damage == "bytes":
        source.write_bytes(b"changed")
    elif damage == "delete":
        source.unlink()
    else:
        target = tmp_path / "replacement.txt"
        target.write_bytes(b"different")
        source.unlink()
        try:
            source.symlink_to(target)
        except OSError:
            pytest.skip(
                "Windows account cannot create symbolic links; native Linux covers this case"
            )
    with pytest.raises(io.StudyError, match="protocol_document_drift"):
        phase.phase_manifest()


def test_lexical_reuse_keys_project_and_both_source_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    phase = phase_module()
    io = phase.io
    resources = io.load_operational_resources()
    for name in ("one", "two"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "source.txt").write_bytes(name.encode())
        (tmp_path / name / "extra.txt").write_bytes(b"extra")
    monkeypatch.setattr(io, "PROTOCOL_DOCUMENTS", {})
    monkeypatch.setattr(io, "load_operational_resources", lambda: resources)
    monkeypatch.setattr(io, "_fresh_package_version", lambda name: "fixture")
    monkeypatch.setattr(io, "SOURCE_PATHS", ("source.txt",))
    monkeypatch.setattr(phase, "EXTRA_SOURCES", ())
    monkeypatch.setattr(io, "PROJECT", tmp_path / "one")
    first = phase.phase_manifest()
    monkeypatch.setattr(io, "PROJECT", tmp_path / "two")
    second = phase.phase_manifest()
    assert first.digest != second.digest
    monkeypatch.setattr(phase, "EXTRA_SOURCES", ("extra.txt",))
    assert set(phase.phase_manifest().payload["sources"]) == {"source.txt", "extra.txt"}
    monkeypatch.setattr(io, "SOURCE_PATHS", ("extra.txt",))
    assert set(phase.phase_manifest().payload["sources"]) == {"extra.txt"}
    assert phase._manifest_paths.cache_info().maxsize == 2
