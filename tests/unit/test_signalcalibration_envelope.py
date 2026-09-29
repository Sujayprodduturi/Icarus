"""Resource-proof harness guards; these tests never draw a reserved stream."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, cast

import numpy as np
import pytest
import scripts.prove_signalcalibration_envelope as proof
import scripts.signal_calibration as calibration


def test_test_seed_guard_refuses_both_reserved_masters() -> None:
    manifest = calibration.load_manifest()
    reserved = {int(phase["master_seed"]) for phase in manifest["phases"].values()}
    original = np.random.SeedSequence
    for seed in reserved:
        for value in (seed, np.int64(seed)):
            with pytest.raises(calibration.ManifestError, match="reserved seed"):
                proof._test_only_seed_sequence(original, reserved, value)
    candidate = proof._test_only_seed_sequence(original, reserved, 2026092911)
    assert isinstance(candidate, original)


def test_scratch_repo_has_real_protected_bytes_and_test_only_review(tmp_path: Path) -> None:
    manifest = calibration.load_manifest()
    repo = proof._build_scratch_repo(calibration._ROOT, tmp_path, manifest)
    assert repo != calibration._ROOT
    protected = calibration._manifest_protected_paths(manifest)
    for relative in protected:
        assert (repo / relative).read_bytes() == (calibration._ROOT / relative).read_bytes()
    manifest_sha = hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    attestation = repo / f"docs/reviews/step6a2/{manifest_sha}/task3.review.json"
    review = calibration._parse_review_attestation(manifest, attestation.read_bytes())
    assert review.reviewed_commit
    assert b"SCRATCH RESOURCE PROOF ONLY" in (repo / review.review_record_path).read_bytes()
    git_proof = calibration._verify_reviewed_git_state(
        repo,
        manifest,
        review,
        calibration._Deadline(0.0, 30.0, lambda: 1.0),
        allowed_untracked=tuple(manifest["integrity"]["allowed_untracked"]),
    )
    assert git_proof.protected_blobs == review.protected_blobs
    (repo / "unexpected.txt").write_bytes(b"not allowed\n")
    with pytest.raises(calibration.ManifestError, match="untracked"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            review,
            calibration._Deadline(0.0, 30.0, lambda: 1.0),
            allowed_untracked=tuple(manifest["integrity"]["allowed_untracked"]),
        )


def test_native_proof_refuses_windows_before_scratch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(proof, "_platform_name", lambda: "win32")
    monkeypatch.setattr(
        proof, "_build_scratch_repo", lambda *args: pytest.fail("created scratch repo on Windows")
    )
    with pytest.raises(calibration.ManifestError, match="bare Linux"):
        proof._run_native_envelope(calibration._ROOT)


def test_high_size_events_verify_one_frozen_chunk() -> None:
    manifest = calibration.load_manifest()
    cell = manifest["phases"]["validation"]["cells"][0]
    chunk = calibration._CountedChunk(cell["id"], 0, 0, 256, cast(Any, (None,) * 256))
    event = proof._high_size_events(manifest, "validation", "raw", chunk)
    counts = calibration._validate_metric_event_partition(
        manifest,
        {key: value for key, value in event.items() if key != "parity"},
        replicate_start=0,
        replicate_stop_exclusive=256,
        declared_metric="raw",
    )
    calibration._verify_parity(manifest, event, cell, "raw", 20_000, 0, 256)
    assert counts.emitted == 256
    assert len(event["parity"]) >= 16


def test_written_chunk_meter_counts_only_successful_real_chunk_appends() -> None:
    written: list[bytes] = []

    def append(context: Any, data: bytes, offset: int, *, closing_reserve: int) -> int:
        del context, closing_reserve
        written.append(data)
        return offset + len(data)

    meter = proof._WrittenChunkMeter(append)
    context = cast(Any, None)
    header = b'{"phase":"calibration","chunks":['
    first = b'{"cell_id":"first","metrics":{}}'
    second = b',{"cell_id":"second","metrics":{"longer":true}}'
    offset = meter(context, header, 0, closing_reserve=1)
    assert meter.max_bytes == 0
    offset = meter(context, first, offset, closing_reserve=1)
    assert meter.max_bytes == len(first)
    offset = meter(context, second, offset, closing_reserve=1)
    assert offset == sum(map(len, written))
    assert written == [header, first, second]
    assert meter.max_bytes == len(second)

    def fail(context: Any, data: bytes, offset: int, *, closing_reserve: int) -> int:
        del context, data, offset, closing_reserve
        raise OSError("append failed")

    failed_meter = proof._WrittenChunkMeter(fail)
    with pytest.raises(OSError, match="append failed"):
        failed_meter(context, second, 0, closing_reserve=1)
    assert failed_meter.max_bytes == 0


def test_source_provenance_rejects_dirty_protected_bytes(tmp_path: Path) -> None:
    manifest = calibration.load_manifest()
    source = tmp_path / "source"
    source.mkdir()
    proof._git(source, "init", "-q")
    proof._git(source, "config", "user.email", "resource-proof@example.invalid")
    proof._git(source, "config", "user.name", "Resource proof test")
    paths = (
        *calibration._manifest_protected_paths(manifest),
        "scripts/prove_signalcalibration_envelope.py",
        ".github/workflows/signal-resource-proof.yml",
    )
    for relative in paths:
        destination = source / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((calibration._ROOT / relative).read_bytes())
    proof._commit_all(source, "clean source")
    assert proof._assert_source_provenance(source, manifest)
    protected = source / calibration._manifest_protected_paths(manifest)[0]
    protected.write_bytes(protected.read_bytes() + b"tampered")
    with pytest.raises(calibration.ManifestError, match="not clean"):
        proof._assert_source_provenance(source, manifest)
