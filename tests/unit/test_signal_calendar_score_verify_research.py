"""Independent deterministic saved-calendar verification contracts."""

from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import subprocess
from fractions import Fraction as F
from pathlib import Path
from typing import Any

import pytest
from scripts.research import signal_calendar_evidence as evidence
from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_score as score
from scripts.research import signal_calendar_score_study as study


def _verify() -> Any:
    name = "scripts.research.signal_calendar_score_verify"
    assert importlib.util.find_spec(name) is not None, "independent verifier implementation missing"
    return importlib.import_module(name)


def _identity(
    profile: str, n: int, *, namespace: str = study.PREFLIGHT_NAMESPACE
) -> dict[str, object]:
    return {
        "namespace": namespace,
        "phase": "test_preflight" if namespace == study.PREFLIGHT_NAMESPACE else "test_fixture",
        "profile_id": profile,
        "n": n,
        "replicate": 0,
        "root": bytes(32).hex(),
    }


@pytest.mark.parametrize("item", study.SPECS, ids=lambda item: item.profile_id)
def test_reference_reproduces_frozen_full_set(item: study.StudySpec) -> None:
    verify = _verify()
    identity = _identity(item.profile_id, item.n)
    stream = study.CounterStream(
        namespace=study.PREFLIGHT_NAMESPACE,
        phase="test_preflight",
        profile_id=item.profile_id,
        n=item.n,
        replicate=0,
        root=bytes(32),
    )
    payload = study.generate_payload(item, stream)
    baseline = json.loads(
        (study.PROJECT / "docs/reviews/2026-10-04-calendar-score-study-preflight.json").read_bytes()
    )
    saved = next(row for row in baseline["path_results"] if row["profile_id"] == item.profile_id)
    assert hashlib.sha256(payload).hexdigest() == saved["payload_sha256"]
    result = verify.reference_path(item.profile_id, item.n, payload, identity)
    assert result.count == saved["results"][0]["count"]
    assert [
        {
            key: value
            for key, value in row.items()
            if key not in ("covered", "lower_miss", "upper_miss")
        }
        for row in result.rows
    ] == saved["results"]
    assert result.words == stream.words_consumed == saved["words"]


def test_hand_packed_prefix_totals_exclude_halos_and_strict_ties() -> None:
    verify = _verify()
    # P1 t0: previous=-1, forward=-1,e1=+1 -> zero; t1 previous=-1,
    # forward=+1,e1=+1 -> +.02. Two selected trades, no halo entrants.
    payload = bytes([4, 12, 13, 31])
    count, raw, wins, excess = verify.trade_totals("P1", 2, payload)
    assert (count, raw, wins, excess) == (2, F(1, 50), 1, F(13, 500))
    # Paired center retains ORIGINAL a, rather than (a-benchmark_previous)/3.
    payload = bytes([31] * 4)
    assert verify.trade_totals("P2", 2, payload) == (4, F(8, 75), 4, F(23, 750))


def test_exact_rounding_and_truths_are_independent_of_production(monkeypatch: Any) -> None:
    verify = _verify()

    def prohibited(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("production math called by independent reference")

    for module, names in [
        (study, ("generate_payload", "evaluate_payload", "truths", "exact_cutoff")),
        (evidence, ("replay",)),
        (score, ("calculate", "assess")),
        (laws, ("analytical_truths",)),
    ]:
        for name in names:
            monkeypatch.setattr(module, name, prohibited)
    payload, words = verify.reconstruct(_identity("P1", 2048))
    result = verify.reference_path("P1", 2048, payload, _identity("P1", 2048))
    assert result.words == words == 12300
    assert verify.exact_truths("P1") == {
        "raw": F(0),
        "win": F(1, 4),
        "synthetic_excess": F(-1, 200),
    }
    assert verify.outward_interval(F(1, 3), F(4, 9)) == (
        F(-333333333333333333333333333333333333333333333333333333333334, 10**60),
        F(10**60 + 1, 10**60),
    )
    assert verify.exact_truths("E+")["raw"] == F(1, 25)
    assert verify.exact_truths("E-")["synthetic_excess"] == F(-9, 200)


@pytest.mark.parametrize("namespace", [study.EXPERIMENT_NAMESPACE, "unknown"])
def test_reference_always_refuses_experimental_identity(namespace: str) -> None:
    verify = _verify()
    with pytest.raises(verify.VerificationError, match="identity"):
        verify.reconstruct(_identity("P1", 2048, namespace=namespace))


def test_sparse_no_count_is_refusal_not_coverage() -> None:
    verify = _verify()
    result = verify.calculate_rows("L1", 2048, 0, F(0), 0, F(0))
    assert all(row["reason"] == "zero_count|sparse_selection_unsupported" for row in result)
    assert all(
        not row["arithmetic"] and not row["precision"] and row["lower"] is None for row in result
    )
    with pytest.raises(verify.VerificationError, match="dense_count"):
        verify.calculate_rows("P1", 2048, 2047, F(0), 0, F(0))


@pytest.mark.parametrize("atom", [128, 64, 0])
def test_impossible_atoms_are_rejected_before_totals(atom: int) -> None:
    verify = _verify()
    with pytest.raises(verify.VerificationError, match="atom"):
        verify.trade_totals("P1", 2, bytes([atom] * 4))


def test_independent_sha_literal_vector_and_rejection_count(monkeypatch: Any) -> None:
    verify = _verify()
    stream = verify.ReferenceWords(_identity("P1", 2048))
    assert [stream.word() for _ in range(5)] == [
        17178914821994726101,
        16061446197116128555,
        2642099818172358451,
        8061481959689794875,
        14284209687861624289,
    ]
    limit = (1 << 64) // 50 * 50
    values = [0, 0, limit, 7, 0, 0, 0, *range(20000)]

    def digest(prefix: bytes, counter: int) -> bytes:
        return b"".join(v.to_bytes(8, "big") for v in values[counter * 4 : counter * 4 + 4])

    monkeypatch.setattr(verify, "_digest", digest)
    actual, words = verify.reconstruct(_identity("L1", 2048))
    assert words == 12301
    assert actual[0] == 27  # s+;q+; rejected G then7 => false; both eps+;J0.
    values[:] = [0, 0] + [(1 << 64) - 1] * 1024 + [0] * 20000
    with pytest.raises(verify.VerificationError, match="rejection_limit"):
        verify.reconstruct(_identity("L1", 2048))


def test_independent_binomial_tail_and_registered_inclusive_cutoffs() -> None:
    verify = _verify()
    assert verify.binomial_tail(2, F(1, 2), 2, lower=False) == F(1, 4)
    assert verify.binomial_tail(2, F(1, 2), 0, lower=True) == F(1, 4)
    verify.check_frozen_cutoffs()
    assert verify.fixed_gate("coverage", 31258, 32768, "validation")
    assert not verify.fixed_gate("coverage", 31257, 32768, "validation")
    assert verify.fixed_gate("tail", 270, 32768, "validation")
    assert not verify.fixed_gate("tail", 271, 32768, "validation")
    assert verify.fixed_gate("detection", 29668, 32768, "validation")
    assert not verify.fixed_gate("detection", 29667, 32768, "validation")
    assert verify.fixed_gate("coverage", 7783, 8192, "development")
    assert not verify.fixed_gate("coverage", 7782, 8192, "development")


def test_cached_truth_dictionary_is_not_owned_by_caller() -> None:
    verify = _verify()
    verify.exact_truths("P1")["raw"] = F(999)
    assert verify.exact_truths("P1")["raw"] == 0


def test_prefix_python_integer_fallback_preserves_large_coefficients(monkeypatch: Any) -> None:
    from dataclasses import replace

    verify = _verify()
    original = laws.profile
    monkeypatch.setattr(
        laws,
        "profile",
        lambda name: replace(original(name), a=F(10**40)) if name == "P1" else original(name),
    )
    assert verify.trade_totals("P1", 2, bytes([31] * 4)) == (
        4,
        F(8 * 10**40, 3) + F(2, 25),
        4,
        F(8 * 10**40, 3) + F(1, 250),
    )


def _fixture(root: Path) -> tuple[Any, str, tuple[tuple[str, int, int], ...]]:
    verify = _verify()
    paths = (("P1", 2048, 0), ("P2", 2048, 0))
    manifest = verify.write_fixture(root, paths=paths)
    return verify, manifest, paths


def test_saved_fixture_success_reconstructs_every_counter_and_has_no_authority(
    tmp_path: Path,
) -> None:
    verify, manifest, paths = _fixture(tmp_path / "evidence")
    receipt = verify.verify_fixture(
        tmp_path / "evidence", expected_manifest=manifest, expected_paths=paths
    )
    assert (receipt.paths, receipt.metrics, receipt.words, receipt.payload_bytes) == (
        2,
        6,
        24600,
        4100,
    )
    report = json.loads((tmp_path / "evidence/fixture-report.json").read_bytes())
    assert report["summary"]["phase_verdict"] == "UNAVAILABLE_DETERMINISTIC_FIXTURE"
    assert report["summary"]["metric_cells"]["P1:win"]["R"] == 1
    assert receipt.binding["protocol_digest"] == study.PROTOCOL_SHA256
    assert (tmp_path / "evidence/verified.json").exists()
    assert not hasattr(verify, "PhaseCapability")
    assert not hasattr(verify, "release_validation")


@pytest.mark.parametrize(
    "damage",
    [
        "missing_terminal",
        "duplicate",
        "reorder",
        "truncate",
        "trailing",
        "wrong_digest",
        "wrong_endpoint",
        "bool_count",
        "bad_rational",
        "bad_schema",
        "bad_size",
        "bad_offset",
        "wrong_phase",
        "wrong_manifest",
        "noncanonical",
        "report_counter",
        "terminal_count",
    ],
)
def test_corruption_never_receipts_success(tmp_path: Path, damage: str) -> None:
    verify, manifest, paths = _fixture(tmp_path / "evidence")
    root = tmp_path / "evidence"
    index = root / "fixture-index.jsonl"
    rows = [json.loads(line) for line in index.read_bytes().splitlines()]
    payload = root / "fixture-payload.bin"
    if damage == "missing_terminal":
        (root / "fixture-terminal.json").unlink()
    elif damage == "duplicate":
        rows.append(rows[0])
    elif damage == "reorder":
        rows.reverse()
    elif damage == "truncate":
        payload.write_bytes(payload.read_bytes()[:-1])
    elif damage == "trailing":
        payload.write_bytes(payload.read_bytes() + b"x")
    elif damage == "wrong_digest":
        rows[0]["payload_sha256"] = "0" * 64
    elif damage == "wrong_endpoint":
        rows[0]["results"][0]["upper"] = [1, 1]
    elif damage == "bool_count":
        rows[0]["results"][0]["count"] = True
    elif damage == "bad_rational":
        rows[0]["results"][0]["total"] = [0, 2]
    elif damage == "bad_schema":
        rows[0]["schema"] = True
    elif damage == "bad_size":
        rows[0]["size"] = verify.BUFFER_CAP + 1
    elif damage == "bad_offset":
        rows[0]["offset"] = 1
    elif damage == "wrong_phase":
        rows[0]["phase"] = "development"
    elif damage == "wrong_manifest":
        manifest = "0" * 64
    elif damage == "noncanonical":
        index.write_bytes(b" " + index.read_bytes())
    elif damage == "report_counter":
        path = root / "fixture-report.json"
        record = json.loads(path.read_bytes())
        record["summary"]["metric_cells"]["P1:win"]["C"] += 1
        path.write_bytes(verify.canonical(record))
    elif damage == "terminal_count":
        path = root / "fixture-terminal.json"
        record = json.loads(path.read_bytes())
        record["paths"] = 81920
        path.write_bytes(verify.canonical(record))
    if damage in {
        "duplicate",
        "reorder",
        "wrong_digest",
        "wrong_endpoint",
        "bool_count",
        "bad_rational",
        "bad_schema",
        "bad_size",
        "bad_offset",
        "wrong_phase",
    }:
        index.write_bytes(b"".join(verify.canonical(row) for row in rows))
    with pytest.raises(verify.VerificationError):
        verify.verify_fixture(root, expected_manifest=manifest, expected_paths=paths)
    assert not (root / "verified.json").exists()


def test_fixture_caps_and_namespace_refuse_before_output(tmp_path: Path) -> None:
    verify = _verify()
    with pytest.raises(verify.VerificationError, match="identity"):
        verify.write_fixture(tmp_path / "bad", namespace=study.EXPERIMENT_NAMESPACE)
    assert not (tmp_path / "bad").exists()
    with pytest.raises(verify.VerificationError, match="path_order"):
        verify.write_fixture(tmp_path / "bad", paths=(("P2", 2048, 0), ("P1", 2048, 0)))
    assert not (tmp_path / "bad").exists()


def test_fixture_detects_source_drift_and_durable_receipt_failure(
    tmp_path: Path, monkeypatch: Any
) -> None:
    verify, manifest, paths = _fixture(tmp_path / "source")
    monkeypatch.setattr(verify, "current_manifest", lambda: ("0" * 64, {}))
    with pytest.raises(verify.VerificationError, match="source"):
        verify.verify_fixture(tmp_path / "source", expected_manifest=manifest, expected_paths=paths)
    assert not (tmp_path / "source/verified.json").exists()
    monkeypatch.undo()
    verify, manifest, paths = _fixture(tmp_path / "durability")
    original = study._exclusive_record

    def fail_receipt(path: Path, record: object, **kwargs: Any) -> Any:
        if path.name == "verification-candidate.json":
            raise study.StudyError("close_failure")
        return original(path, record, **kwargs)

    monkeypatch.setattr(study, "_exclusive_record", fail_receipt)
    with pytest.raises(verify.VerificationError, match="close_failure"):
        verify.verify_fixture(
            tmp_path / "durability", expected_manifest=manifest, expected_paths=paths
        )
    assert not (tmp_path / "durability/verified.json").exists()


def test_full_phase_fixed_decision_distinguishes_failed_from_incomplete() -> None:
    verify = _verify()
    families = ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "E+", "E-")
    summary: dict[str, Any] = {
        "metric_cells": {
            f"{p}:{m}": {
                "R": 8192,
                "A": 8192,
                "P": 8192,
                "C": 8192,
                "Tlo": 0,
                "Thi": 0,
                "D": 8192 if p in ("E+", "E-") else 0,
            }
            for p in families
            for m in (
                ("raw", "synthetic_excess")
                if p in ("E+", "E-")
                else ("raw", "win", "synthetic_excess")
            )
        },
        "joint_cells": {p: {"R": 8192, "C": 8192} for p in families},
    }
    summary["diagnostics"] = {
        f"L1:{metric}": {
            "R": 8192,
            "A": 8192,
            "P": 0,
            "C": 8192,
            "Tlo": 0,
            "Thi": 0,
            "D": 0,
            "reasons": {"sparse_selection_unsupported": 8192},
        }
        for metric in ("raw", "win", "synthetic_excess")
    }
    assert verify.phase_decision(summary, "development") == "PASS"
    summary["metric_cells"]["P1:raw"]["C"] = 0
    summary["metric_cells"]["P1:raw"]["Tlo"] = 8192
    assert verify.phase_decision(summary, "development") == "FAILED"
    summary["metric_cells"]["P1:raw"]["A"] = 8191
    with pytest.raises(verify.VerificationError, match="incomplete"):
        verify.phase_decision(summary, "development")


@pytest.mark.parametrize(
    "field,value",
    [("replicate", 32768), ("replicate", 10**10000), ("n", 131073)],
    ids=["replicate_bound", "huge_integer", "geometry_bound"],
)
def test_reference_identity_bounds_before_prefix_allocation(field: str, value: int) -> None:
    verify = _verify()
    identity = _identity("P7", 131072)
    identity[field] = value
    with pytest.raises(verify.VerificationError, match=r"identity|geometry"):
        verify.reconstruct(identity)


def test_supervision_checks_all_fail_safe_samples() -> None:
    verify = _verify()
    for reason, args in [
        ("timeout", (601.0, 1, 0.0, 30 * 1024**3)),
        ("memory", (0.0, 2 * 1024**3 + 1, 0.0, 30 * 1024**3)),
        ("heartbeat", (0.0, 1, 31.0, 30 * 1024**3)),
        ("disk_reserve", (0.0, 1, 0.0, 1)),
    ]:
        with pytest.raises(verify.VerificationError, match=reason):
            verify.check_resources(*args)


def test_benchmark_cli_never_accepts_reduced_geometry_or_sampling() -> None:
    verify = _verify()
    parser = verify.parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--development"])
    with pytest.raises(verify.VerificationError, match="deterministic_only"):
        verify.dispatch(parser.parse_args([]))
    assert verify.benchmark_geometry() == tuple((p, n, 0) for p, n, _ in verify.GEOMETRIES)


def test_benchmark_final_check_and_child_failure_kill_no_success(
    tmp_path: Path, monkeypatch: Any
) -> None:
    verify = _verify()

    class Process:
        pid = -1
        returncode = 1

        def poll(self) -> int:
            return self.returncode

    sampled = []
    monkeypatch.setattr(verify, "_sample", lambda *args, **kwargs: sampled.append((args, kwargs)))
    with pytest.raises(verify.VerificationError, match="worker_failed"):
        verify._supervise(Process(), tmp_path)
    assert len(sampled) == 1
    assert sampled[0][1]["require_heartbeat"] is True


def test_benchmark_source_and_log_close_failure_cannot_succeed(
    tmp_path: Path, monkeypatch: Any
) -> None:
    verify = _verify()

    class Log:
        def close(self) -> None:
            raise OSError("close")

    class Process:
        pid = -1
        returncode = 0

        def poll(self) -> int:
            return 0

    original_open = study._open_exclusive
    monkeypatch.setattr(
        study,
        "_open_exclusive",
        lambda path: Log() if path.name == "benchmark-worker.log" else original_open(path),
    )
    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(verify, "_supervise", lambda *args: 1)
    monkeypatch.setattr(study, "_kill_tree", lambda process: None)
    root = tmp_path / "benchmark"
    monkeypatch.setattr(verify, "_trusted_benchmark_parent", lambda: tmp_path)
    with pytest.raises(verify.VerificationError, match="close_failure"):
        verify.run_benchmark(root)
    assert not (root / "benchmark-result.json").exists()
    assert (root / "benchmark-failure.json").exists()


def test_benchmark_worker_join_failure_never_terminal(tmp_path: Path, monkeypatch: Any) -> None:
    verify = _verify()
    root = tmp_path / "worker"
    root.mkdir()
    manifest, payload = verify.current_manifest()
    verify._record(
        root,
        "benchmark-claim.json",
        {
            "schema": 1,
            "scope": verify.SCOPE,
            "nonce": "a" * 64,
            "manifest": payload,
            "source_manifest_digest": manifest,
        },
    )

    class Thread:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def start(self) -> None:
            pass

        def join(self, timeout: int) -> None:
            pass

        def is_alive(self) -> bool:
            return True

    monkeypatch.setattr(verify.threading, "Thread", Thread)
    monkeypatch.setattr(verify, "write_fixture", lambda *args, **kwargs: manifest)
    monkeypatch.setattr(
        verify,
        "verify_fixture",
        lambda *args, **kwargs: verify.VerificationReceipt({}, 10, 28, 1388952, 231492, 0.1),
    )
    with pytest.raises(verify.VerificationError, match="heartbeat_join"):
        verify._worker(root, "a" * 64)
    assert not (root / "benchmark-terminal.json").exists()


def test_missing_sparse_diagnostics_are_incomplete_and_zero_count_reasons_preserved() -> None:
    verify = _verify()
    summary = verify._cells()
    zero = list(verify.calculate_rows("L1", 2048, 0, F(0), 0, F(0)))
    verify._accumulate(summary, "L1", zero)
    assert set(summary["diagnostics"]) == {"L1:raw", "L1:win", "L1:synthetic_excess"}
    for cell in summary["diagnostics"].values():
        assert cell["R"] == 1 and cell["A"] == cell["P"] == cell["C"] == 0
        assert cell["reasons"] == {"zero_count|sparse_selection_unsupported": 1}
    with pytest.raises(verify.VerificationError, match="incomplete"):
        verify.phase_decision(
            {"metric_cells": {}, "joint_cells": {}, "diagnostics": {}}, "development"
        )


def test_repeated_readonly_verification_never_replaces_receipt(tmp_path: Path) -> None:
    verify, manifest, paths = _fixture(tmp_path / "evidence")
    first = verify.verify_fixture(
        tmp_path / "evidence", expected_manifest=manifest, expected_paths=paths
    )
    original = (tmp_path / "evidence/verified.json").read_bytes()
    second = verify.verify_fixture(
        tmp_path / "evidence", expected_manifest=manifest, expected_paths=paths, receipt_name=None
    )
    assert first.binding == second.binding
    assert (tmp_path / "evidence/verified.json").read_bytes() == original


@pytest.mark.parametrize("failure", ["source", "fsync", "close"])
def test_written_candidate_failure_never_publishes_success_receipt(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    import os

    verify, manifest, paths = _fixture(tmp_path / "evidence")
    root = tmp_path / "evidence"
    observed: list[bytes] = []
    original_manifest = verify.current_manifest
    original_fsync = os.fsync
    original_open = study._open_exclusive

    def written_receipt() -> Path | None:
        for name in ("verification-candidate.json", "verified.json"):
            path = root / name
            if path.exists() and path.stat().st_size:
                return path
        return None

    if failure == "source":

        def changed_after_write() -> Any:
            path = written_receipt()
            if path is not None:
                observed.append(path.read_bytes())
                return "0" * 64, {}
            return original_manifest()

        monkeypatch.setattr(verify, "current_manifest", changed_after_write)
    elif failure == "fsync":

        def fail_real_receipt_sync(descriptor: int) -> None:
            path = written_receipt()
            if path is not None and os.fstat(descriptor).st_ino == path.stat().st_ino:
                observed.append(path.read_bytes())
                raise OSError("receipt fsync after actual bytes")
            original_fsync(descriptor)

        monkeypatch.setattr(os, "fsync", fail_real_receipt_sync)
    else:

        class CloseFailure:
            def __init__(self, stream: Any) -> None:
                self.stream = stream

            def write(self, blob: bytes | memoryview) -> int:
                return int(self.stream.write(blob))

            def flush(self) -> None:
                self.stream.flush()

            def fileno(self) -> int:
                return int(self.stream.fileno())

            def close(self) -> None:
                self.stream.close()
                path = written_receipt()
                assert path is not None
                observed.append(path.read_bytes())
                raise OSError("receipt close after actual bytes")

        def receipt_open(path: Path) -> Any:
            stream = original_open(path)
            return (
                CloseFailure(stream)
                if path.name in ("verification-candidate.json", "verified.json")
                else stream
            )

        monkeypatch.setattr(study, "_open_exclusive", receipt_open)
    with pytest.raises(verify.VerificationError):
        verify.verify_fixture(root, expected_manifest=manifest, expected_paths=paths)
    assert observed and json.loads(observed[0])["paths"] == 2
    assert not (root / "verified.json").exists()


def test_publication_never_overwrites_preexisting_receipt(tmp_path: Path) -> None:
    verify, manifest, paths = _fixture(tmp_path / "evidence")
    root = tmp_path / "evidence"
    protected = b"preexisting receipt owned by another invocation"
    (root / "verified.json").write_bytes(protected)
    with pytest.raises(verify.VerificationError):
        verify.verify_fixture(root, expected_manifest=manifest, expected_paths=paths)
    assert (root / "verified.json").read_bytes() == protected
