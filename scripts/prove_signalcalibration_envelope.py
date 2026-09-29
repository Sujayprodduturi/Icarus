"""Test-only native resource surrogate; never uses Icarus's reserved streams."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import UTC, datetime
from numbers import Integral
from pathlib import Path
from typing import Any, cast

import numpy as np
import scripts.signal_calibration as calibration
from scipy.stats import t


def _platform_name() -> str:
    return sys.platform


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _git_bytes(repo: Path, *args: str) -> bytes:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True).stdout


def _assert_source_provenance(source_root: Path, manifest: dict[str, Any]) -> str:
    if _git_bytes(source_root, "status", "--porcelain"):
        raise calibration.ManifestError("resource proof source checkout is not clean")
    protected = (
        *calibration._manifest_protected_paths(manifest),
        "scripts/prove_signalcalibration_envelope.py",
        ".github/workflows/signal-resource-proof.yml",
    )
    for relative in protected:
        committed = _git_bytes(source_root, "show", f"HEAD:{relative}")
        if committed != (source_root / relative).read_bytes():
            raise calibration.ManifestError(f"resource proof source bytes differ: {relative}")
    return _git(source_root, "rev-parse", "HEAD")


def _commit_all(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _build_scratch_repo(source_root: Path, scratch_root: Path, manifest: dict[str, Any]) -> Path:
    """Copy actual protected bytes, then issue a clearly test-only scratch review fixture."""
    repo = scratch_root / "scratch-review-repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "resource-proof@example.invalid")
    _git(repo, "config", "user.name", "Icarus scratch resource proof")
    _git(repo, "config", "core.autocrlf", "false")
    protected = calibration._manifest_protected_paths(manifest)
    for relative in protected:
        destination = repo / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((source_root / relative).read_bytes())
    reviewed = _commit_all(repo, "Copy real protected bytes for test-only resource proof")
    reviewed_tree = _git(repo, "rev-parse", f"{reviewed}^{{tree}}")
    manifest_sha = hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    review_path = "docs/reviews/resource-proof-test-only.md"
    attestation_path = f"docs/reviews/step6a2/{manifest_sha}/task3.review.json"
    review_file = repo / review_path
    review_file.parent.mkdir(parents=True, exist_ok=True)
    review_file.write_bytes(b"SCRATCH RESOURCE PROOF ONLY; no official authorization.\n")
    protected_blobs = {
        relative: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        for relative in protected
    }
    attestation = {
        "schema": "step6a2-task3-review-v1",
        "protocol_version": calibration.PROTOCOL_VERSION,
        "manifest_sha256": manifest_sha,
        "verdict": "APPROVED",
        "reviewed_commit": reviewed,
        "reviewed_tree": reviewed_tree,
        "protected_blobs": protected_blobs,
        "review_record_path": review_path,
        "allowed_intervening_paths": sorted([review_path, attestation_path]),
        "review_scope": [
            "artifact_verifier",
            "counted_calibration",
            "held_back_validation",
            "resource_and_durability",
        ],
        "reviewer": {"model": "scratch-test-only", "role": "independent_statistical_safety"},
        "reviewed_at_utc": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
    }
    attestation_file = repo / attestation_path
    attestation_file.parent.mkdir(parents=True, exist_ok=True)
    attestation_file.write_bytes(calibration._canonical_bytes(attestation))
    _commit_all(repo, "Record test-only scratch review fixture")
    return repo


def _test_only_seed_sequence(
    original: Callable[..., Any], reserved: set[int], entropy: Any, **kwargs: Any
) -> Any:
    if isinstance(entropy, Integral) and int(entropy) in reserved:
        raise calibration.ManifestError("resource surrogate attempted reserved seed")
    return original(entropy, **kwargs)


class _HighSizeProvider:
    """Stream the frozen topology without allocating all scripted chunks at once."""

    def __init__(self, context: calibration._PhaseContext, manifest: dict[str, Any]) -> None:
        context.require_active(context.phase)
        if context.provider_issued:
            raise calibration.ManifestError("scratch provider already issued")
        object.__setattr__(context, "provider_issued", True)
        self.context = context
        self.cells = manifest["phases"][context.phase]["cells"]
        self.replicates = int(manifest["phases"][context.phase]["replicates"])
        self.cell_index = 0
        self.chunk_index = 0

    def __iter__(self) -> _HighSizeProvider:
        return self

    def __next__(self) -> calibration._CountedChunk:
        if self.cell_index >= len(self.cells):
            raise StopIteration
        self.context.require_active(self.context.phase)
        cell_id = int(self.cells[self.cell_index]["id"])
        start = self.chunk_index * 256
        stop = min(self.replicates, start + 256)
        chunk = calibration._CountedChunk(
            cell_id, self.chunk_index, start, stop, cast(Any, (None,) * (stop - start))
        )
        self.chunk_index += 1
        if stop == self.replicates:
            self.chunk_index = 0
            self.cell_index += 1
        return chunk


def _high_size_events(
    manifest: dict[str, Any], phase: str, metric: str, chunk: calibration._CountedChunk
) -> dict[str, Any]:
    cells = manifest["phases"][phase]["cells"]
    cell = next(item for item in cells if item["id"] == chunk.cell_id)
    target_key = {"raw": "raw_mean", "win": "win_probability", "synthetic_excess": "excess_mean"}[
        metric
    ]
    target = float(cell["targets"][target_key])
    mean = 0.5 if metric == "win" else 0.0
    critical = float(t.ppf(0.975, 10.0))
    interval = {
        "status": "EMITTED",
        "mean": mean,
        "cr2_variance": 1.0,
        "nu": 10.0,
        "sample_variance": 1.0,
        "design_effect": 1.0,
        "effective_n": 1.0,
        "raw_lower": mean - critical,
        "raw_upper": mean + critical,
        "coverage": mean - critical <= target <= mean + critical,
        "lower_miss": target < mean - critical,
        "upper_miss": target > mean + critical,
    }
    cr1 = dict(interval)
    cr1["cr1_variance"] = cr1.pop("cr2_variance")
    start, stop = chunk.replicate_start, chunk.replicate_stop_exclusive
    replicates = int(manifest["phases"][phase]["replicates"])
    fixed = set(calibration.parity_audit_ids(replicates))
    selected = sorted((fixed & set(range(start, stop))) | set(range(start, min(stop, start + 16))))
    parity = [
        {
            "replicate_id": replicate_id,
            "triggers": ["near_zero", "ordinary"] if replicate_id in fixed else ["near_zero"],
            "max_abs_outcome": 1_000_000.0,
            "batch": interval,
            "scalar": dict(interval),
            "cr1": cr1,
        }
        for replicate_id in selected
    ]
    ids = list(range(start, stop))
    return {
        "metric": metric,
        "emitted_ids": ids,
        "refusals": [],
        "coverage_ids": ids,
        "lower_miss_ids": [],
        "upper_miss_ids": [],
        "joint_success_ids": ids,
        "parity": parity,
    }


class _WrittenChunkMeter:
    """Count only chunk bytes that the real result writer successfully appended."""

    def __init__(self, append: Callable[..., int]) -> None:
        self.append = append
        self.max_bytes = 0

    def __call__(
        self,
        context: calibration._PhaseContext,
        data: bytes,
        written: int,
        *,
        closing_reserve: int,
    ) -> int:
        updated = self.append(context, data, written, closing_reserve=closing_reserve)
        if data.startswith((b'{"cell_id":', b',{"cell_id":')):
            self.max_bytes = max(self.max_bytes, len(data))
        return updated


class _MeasuringNativeLinuxOps(calibration._NativeLinuxOps):
    def __init__(self) -> None:
        super().__init__()
        self.peak_vms_bytes = 0
        self.fsync_successes = 0
        self.close_successes = 0
        self.fsync_failures = 0
        self.close_failures = 0

    def current_vms_bytes(self) -> int:
        value = super().current_vms_bytes()
        self.peak_vms_bytes = max(self.peak_vms_bytes, value)
        return value

    def fsync(self, fd: int) -> None:
        try:
            super().fsync(fd)
        except OSError:
            self.fsync_failures += 1
            raise
        self.fsync_successes += 1
        self.current_vms_bytes()

    def close(self, fd: int) -> None:
        try:
            super().close(fd)
        except OSError:
            self.close_failures += 1
            raise
        self.close_successes += 1


def _run_native_envelope(source_root: Path, mode: str = "generated") -> dict[str, Any]:
    if _platform_name() != "linux":
        raise calibration.ManifestError("resource proof requires bare Linux")
    if mode not in {"generated", "scripted", "validation-fallback"}:
        raise calibration.ManifestError("resource proof mode is invalid")
    ops = _MeasuringNativeLinuxOps()
    native = ops.native_environment_evidence()
    calibration._verify_native_linux_environment(native)
    manifest = calibration.load_manifest()
    calibration._validate_manifest(manifest)
    source_commit = _assert_source_provenance(source_root, manifest)
    expected_topology = {"calibration": (45, 10_000), "validation": (37, 20_000)}
    for phase, (cells, replicates) in expected_topology.items():
        payload = manifest["phases"][phase]
        if len(payload["cells"]) != cells or payload["replicates"] != replicates:
            raise calibration.ManifestError("resource proof frozen topology changed")
    reserved = {int(manifest["phases"][phase]["master_seed"]) for phase in expected_topology}
    test_seeds = {"calibration": 2026092911, "validation": 2026092912}
    if len(set(test_seeds.values())) != 2 or reserved.intersection(test_seeds.values()):
        raise calibration.ManifestError("resource proof test seeds overlap reserved seeds")
    original_root = calibration._ROOT
    original_provider = calibration._CountedChunkProvider
    original_events = calibration._build_metric_events
    original_append = calibration._append_phase_bytes
    original_seed_sequence = np.random.SeedSequence
    contexts: list[calibration._PhaseContext] = []
    meter = _WrittenChunkMeter(original_append)
    with tempfile.TemporaryDirectory(prefix="icarus-resource-proof-") as directory:
        repo = _build_scratch_repo(source_root, Path(directory), manifest)

        class TestOnlyProvider(calibration._CountedChunkProvider):
            def __init__(
                self, context: calibration._PhaseContext, settings: dict[str, Any]
            ) -> None:
                super().__init__(context, settings)
                self._phase_seed = test_seeds[context.phase]

        def guarded_seed_sequence(entropy: Any, **kwargs: Any) -> Any:
            return _test_only_seed_sequence(original_seed_sequence, reserved, entropy, **kwargs)

        def write_selected(context: calibration._PhaseContext, *, scripted: bool) -> None:
            meter.max_bytes = 0
            vars(calibration)["_CountedChunkProvider"] = (
                _HighSizeProvider if scripted else TestOnlyProvider
            )
            vars(calibration)["_build_metric_events"] = (
                _high_size_events if scripted else original_events
            )
            calibration._write_phase_result(context, manifest)

        vars(calibration)["_ROOT"] = repo
        vars(np.random)["SeedSequence"] = guarded_seed_sequence
        vars(calibration)["_append_phase_bytes"] = meter
        try:
            memory: Any = importlib.import_module("psutil")
            report: dict[str, Any] = {
                "schema": "step6a2-test-only-resource-proof-v1",
                "authority": "NONE",
                "mode": mode,
                "source_commit": source_commit,
                "native_environment": native,
                "host_cpu_count": os.cpu_count(),
                "host_ram_bytes": int(memory.virtual_memory().total),
                "filesystem_type": calibration._filesystem_type_for_path(
                    ops.read_mountinfo(), repo
                ),
                "topology": expected_topology,
                "test_seeds": test_seeds,
                "reserved_seed_draws": 0,
                "phases": {},
                "mode_complete": False,
            }
            started = time.monotonic()
            deadline = calibration._Deadline(
                started, float(manifest["runtime_limits"]["max_elapsed_seconds"]), time.monotonic
            )
            calibration.preflight_manifest(manifest)
            deadline.remaining()
            print("test-only full-size calibration starting", file=sys.stderr, flush=True)
            first = calibration._begin_linux_phase("calibration", manifest, ops, deadline)
            contexts.append(first)
            write_selected(first, scripted=mode != "generated")
            first_completion = calibration._complete_phase(first, manifest)
            report["phases"]["calibration"] = _phase_resource_report(
                first, first_completion, ops, meter.max_bytes
            )
            print("test-only full-size calibration complete", file=sys.stderr, flush=True)
            if first_completion.phase_verdict == "PASSED":
                second = calibration._begin_validation_phase(first, first_completion, manifest)
                contexts.append(second)
                print("test-only full-size validation starting", file=sys.stderr, flush=True)
                write_selected(second, scripted=mode == "scripted")
                second_completion = calibration._complete_phase(second, manifest)
                report["phases"]["validation"] = _phase_resource_report(
                    second, second_completion, ops, meter.max_bytes
                )
                print("test-only full-size validation complete", file=sys.stderr, flush=True)
            else:
                report["incomplete_reason"] = (
                    "test-seed calibration verdict did not authorize validation"
                )
            report["mode_complete"] = mode == "generated" or "validation" in report["phases"]
        finally:
            vars(np.random)["SeedSequence"] = original_seed_sequence
            vars(calibration)["_CountedChunkProvider"] = original_provider
            vars(calibration)["_build_metric_events"] = original_events
            vars(calibration)["_append_phase_bytes"] = original_append
            vars(calibration)["_ROOT"] = original_root
            failures: list[calibration.ManifestError] = []
            for context in reversed(contexts):
                if not context.closed:
                    try:
                        context.close()
                    except calibration.ManifestError as exc:
                        failures.append(exc)
            if failures:
                raise calibration.ManifestError(f"resource proof close failed: {failures}")
        report["peak_vms_bytes"] = max(ops.peak_vms_bytes, ops.current_vms_bytes())
        report["fsync_successes"] = ops.fsync_successes
        report["close_successes"] = ops.close_successes
        report["fsync_failures"] = ops.fsync_failures
        report["close_failures"] = ops.close_failures
        if ops.fsync_failures or ops.close_failures:
            raise calibration.ManifestError("resource proof native fsync or close failed")
        return report


def _phase_resource_report(
    context: calibration._PhaseContext,
    completion: calibration._PhaseCompletion,
    ops: _MeasuringNativeLinuxOps,
    max_chunk_bytes: int,
) -> dict[str, Any]:
    candidate = json.loads((context.store.path / context.paths.seal_name).read_bytes())
    snapshot = candidate["prewrite_snapshot"]
    return {
        "verdict": completion.phase_verdict,
        "result_size_bytes": completion.result_size_bytes,
        "completed_elapsed_seconds": completion.completed_total_elapsed_seconds,
        "completed_peak_rss_bytes": completion.completed_peak_rss_bytes,
        "current_vms_bytes": ops.current_vms_bytes(),
        "observed_peak_vms_bytes": ops.peak_vms_bytes,
        "max_encoded_chunk_bytes": max_chunk_bytes,
        "address_space_limit_bytes": context.resources.address_space_limit_bytes,
        "verification_projected_bytes": snapshot["verification_projected_bytes"],
        "candidate_sha256": completion.candidate_sha256,
        "result_sha256": completion.result_sha256,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--mode", choices=("generated", "scripted", "validation-fallback"), required=True
    )
    args = parser.parse_args()
    try:
        report = _run_native_envelope(calibration._ROOT, args.mode)
    except (calibration.ManifestError, OSError) as exc:
        print(f"resource proof failed: {exc}", file=sys.stderr)
        return 1
    encoded = json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    (calibration._ROOT / "resource-proof-report.json").write_bytes((encoded + "\n").encode("utf-8"))
    print(encoded)
    return 0 if report["mode_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
