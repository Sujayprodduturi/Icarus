"""Deterministic controls for the frozen Step-6a.2 calibration protocol."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
import scripts.signal_calibration as calibration
from scripts.signal_calibration import (
    ManifestError,
    SelectionArtifactError,
    clopper_pearson_lower,
    clopper_pearson_upper,
    load_manifest,
    preflight_manifest,
    satterthwaite_nu,
    validate_selection_artifact,
    verify_protected_git_state,
)

_ROOT = Path(__file__).resolve().parents[2]
_MANIFEST = _ROOT / "docs" / "plans" / "2026-09-26-step6a2-calibration-manifest.json"
_DIGEST = _MANIFEST.with_suffix(".sha256")


def _write_canonical(path: Path, payload: dict[str, Any]) -> Path:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    path.write_bytes((raw + "\n").encode("utf-8"))
    digest_path = path.with_suffix(".sha256")
    digest_path.write_bytes((hashlib.sha256(path.read_bytes()).hexdigest() + "\n").encode("ascii"))
    return digest_path


def _mutated_manifest(tmp_path: Path, mutate: Any) -> tuple[Path, Path]:
    payload = json.loads(_MANIFEST.read_text(encoding="utf-8"))
    mutate(payload)
    path = tmp_path / _MANIFEST.name
    return path, _write_canonical(path, payload)


def test_committed_manifest_is_canonical_and_complete() -> None:
    """Dropping, reordering, or silently changing a frozen cell must invalidate the protocol."""
    assert _MANIFEST.exists(), "the reviewed machine manifest has not been frozen"
    manifest = load_manifest(_MANIFEST, _DIGEST)

    assert [cell["id"] for cell in manifest["phases"]["calibration"]["cells"]] == list(range(1, 46))
    assert [cell["id"] for cell in manifest["phases"]["validation"]["cells"]] == list(
        range(1001, 1038)
    )
    assert manifest["candidate_floors"] == [
        {"minimum_blocks": 6, "minimum_nu": 4},
        {"minimum_blocks": 8, "minimum_nu": 6},
        {"minimum_blocks": 12, "minimum_nu": 8},
        {"minimum_blocks": 16, "minimum_nu": 12},
    ]
    assert manifest["rng"]["component_streams"] == {
        "amplitude": 2,
        "block_session_factor_or_ar_innovations": 1,
        "daily_innovations": 4,
        "independent_benchmark_factor": 3,
        "trade_idiosyncratic_normal": 0,
    }
    assert "families" in manifest["dgp_contract"], "DGP equations are not frozen in the manifest"
    assert set(manifest["dgp_contract"]["families"]) == {
        "bounded_rare_magnitude",
        "cross_block_serial_factor",
        "dynamic_h_block_factor",
        "independent",
        "independent_block_factor",
        "overlapping_holds",
        "same_session_burst",
        "two_regime_shift",
        "unequal_occupancy",
    }


def test_manifest_loader_rejects_a_byte_changed_manifest(tmp_path: Path) -> None:
    """A content edit without its reviewed detached digest must not be accepted."""
    changed = tmp_path / _MANIFEST.name
    changed.write_bytes(_MANIFEST.read_bytes().replace(b"2026092602", b"2026092604", 1))
    digest = tmp_path / _DIGEST.name
    digest.write_bytes(_DIGEST.read_bytes())

    with pytest.raises(ManifestError, match="digest"):
        load_manifest(changed, digest)


@pytest.mark.parametrize(
    "mutate,match",
    [
        (lambda value: value.pop("parity"), "top-level keys"),
        (lambda value: value.__setitem__("unexpected", True), "top-level keys"),
        (lambda value: value.__setitem__("protocol_version", "unknown"), "protocol version"),
        (
            lambda value: value["phases"]["calibration"].__setitem__("master_seed", 2026092603),
            "calibration seed",
        ),
        (
            lambda value: value["phases"]["validation"]["cells"][0].__setitem__("id", 1002),
            "cell IDs",
        ),
        (
            lambda value: value["rng"]["component_streams"].__setitem__("amplitude", 4),
            "component stream",
        ),
        (
            lambda value: value["rng"].__setitem__("unexpected", True),
            "rng keys",
        ),
    ],
)
def test_manifest_loader_rejects_self_consistent_semantic_edits(
    tmp_path: Path, mutate: Any, match: str
) -> None:
    """Rehashing an unreviewed protocol edit must not make it semantically valid."""
    path, digest = _mutated_manifest(tmp_path, mutate)

    with pytest.raises(ManifestError, match=match):
        load_manifest(path, digest)


def test_satterthwaite_nu_uses_the_complete_ordered_occupancy() -> None:
    """Replacing the occupancy tuple with block count alone must change this control."""
    balanced = tuple((block, 8) for block in range(6))
    unequal_calibration = tuple((block, (4, 8, 16, 32)[block % 4]) for block in range(24))
    unequal_validation = tuple((block, (5, 10, 20, 30)[block % 4]) for block in range(24))
    unequal_support = tuple((block, (4, 8, 16, 32)[block % 4]) for block in range(12))

    assert satterthwaite_nu(balanced) == pytest.approx(5.0, abs=1e-12)
    assert satterthwaite_nu(unequal_calibration) == pytest.approx(14.8947491881, abs=1e-10)
    assert satterthwaite_nu(unequal_validation) == pytest.approx(16.7970047406, abs=1e-10)
    assert satterthwaite_nu(unequal_support) == pytest.approx(6.970118972910953, abs=1e-12)


def test_preflight_proves_fixed_and_both_dynamic_h_support_outcomes() -> None:
    """Silently treating an outcome-dependent dynamic geometry as fixed must fail this proof."""
    report = preflight_manifest(load_manifest(_MANIFEST, _DIGEST))

    assert report["anchor_support_proven"] is True
    assert report["dynamic_support"] == {
        "calibration": {
            "H=21": {"blocks": 48, "nu": pytest.approx(47.0, abs=1e-12)},
            "H=42": {"blocks": 24, "nu": pytest.approx(23.0, abs=1e-12)},
        },
        "validation": {
            "H=28": {"blocks": 30, "nu": pytest.approx(29.0, abs=1e-12)},
            "H=35": {"blocks": 24, "nu": pytest.approx(23.0, abs=1e-12)},
        },
    }


def test_preflight_derives_fixed_geometry_instead_of_trusting_claimed_occupancy(
    tmp_path: Path,
) -> None:
    """A self-consistent claimed occupancy must still agree with the frozen entry geometry."""

    def mutate(value: dict[str, Any]) -> None:
        geometry = value["geometries"]["cal_anchor"]
        geometry["block_counts"][0][1] = 7
        geometry["expected_nu"] = satterthwaite_nu(
            tuple((block, count) for block, count in geometry["block_counts"])
        )

    path, digest = _mutated_manifest(tmp_path, mutate)

    with pytest.raises(ManifestError, match="derived occupancy"):
        preflight_manifest(load_manifest(path, digest))


def test_preflight_derives_each_dynamic_h_outcome_from_the_nominal_source_grid(
    tmp_path: Path,
) -> None:
    """A dynamic-H outcome cannot replace its derived occupancy with a self-consistent claim."""

    def mutate(value: dict[str, Any]) -> None:
        outcome = value["dynamic_geometries"]["calibration"]["outcomes"]["H=21"]
        outcome["block_counts"][0][1] = 5
        outcome["expected_nu"] = satterthwaite_nu(
            tuple((block, count) for block, count in outcome["block_counts"])
        )

    path, digest = _mutated_manifest(tmp_path, mutate)

    with pytest.raises(ManifestError, match="derived occupancy"):
        preflight_manifest(load_manifest(path, digest))


def test_exact_clopper_pearson_endpoints_and_frozen_integer_cutoffs() -> None:
    """Changing endpoint conventions or strictness at an equality boundary must move a cutoff."""
    assert clopper_pearson_lower(0, 10, 0.001) == 0.0
    assert clopper_pearson_upper(10, 10, 0.001) == 1.0

    report = preflight_manifest(load_manifest(_MANIFEST, _DIGEST))
    assert report["cutoffs"] == {
        "calibration": {
            "coverage_or_joint_minimum_successes": 9396,
            "emission_minimum_successes": 9582,
            "tail_maximum_misses": 327,
        },
        "validation": {
            "coverage_or_joint_minimum_successes": 18734,
            "emission_minimum_successes": 19114,
            "tail_maximum_misses": 697,
        },
    }
    assert report["ideal_whole_gate_power_lower"]["calibration"] == pytest.approx(
        0.9992916663266935, abs=1e-14
    )
    assert report["ideal_whole_gate_power_lower"]["validation"] > 0.999999


def _selection_fixture(manifest: dict[str, Any]) -> dict[str, Any]:
    sha = hashlib.sha256(_MANIFEST.read_bytes()).hexdigest()
    metrics = manifest["acceptance"]["metrics"]
    checks = manifest["acceptance"]["checks"]
    cells = [
        {
            "cell_id": cell["id"],
            "generated": manifest["phases"]["calibration"]["replicates"],
            "metrics": {
                metric: {
                    "checks": {check: True for check in checks},
                    "coverage_successes": manifest["phases"]["calibration"]["replicates"],
                    "emitted": manifest["phases"]["calibration"]["replicates"],
                    "joint_successes": manifest["phases"]["calibration"]["replicates"],
                    "lower_tail_misses": 0,
                    "refusal_total": 0,
                    "upper_tail_misses": 0,
                }
                for metric in metrics
            },
        }
        for cell in manifest["phases"]["calibration"]["cells"]
    ]
    candidates = [
        {"fixed_refusal_controls_passed": True, "floor": floor, "passed": True}
        for floor in manifest["candidate_floors"]
    ]
    return {
        "schema": "step6a2-calibration-selection-v1",
        "calibration_result_sha256": "5" * 64,
        "protocol_version": manifest["protocol_version"],
        "manifest_sha256": sha,
        "protected_blobs": {
            "manifest": "1" * 64,
            "manifest_digest": "2" * 64,
            "harness": "3" * 64,
            "estimator": "4" * 64,
        },
        "calibration": {
            "master_seed": manifest["phases"]["calibration"]["master_seed"],
            "replicates_per_cell": manifest["phases"]["calibration"]["replicates"],
            "cells": cells,
            "candidate_results": candidates,
        },
        "selected_candidate": manifest["candidate_floors"][0],
    }


def test_validation_gate_rejects_missing_calibration_count() -> None:
    """Pass booleans alone must not substitute for complete calibration accounting."""
    manifest = load_manifest(_MANIFEST, _DIGEST)
    artifact = _selection_fixture(manifest)
    del artifact["calibration"]["cells"][0]["metrics"]["raw"]["emitted"]

    with pytest.raises(SelectionArtifactError, match="complete calibration counts"):
        validate_selection_artifact(
            manifest,
            artifact,
            manifest_sha256=hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
            protected_blobs=artifact["protected_blobs"],
        )


def test_validation_gate_rejects_incoherent_complete_calibration_counts() -> None:
    """Counter identities, not verdict booleans, must prove calibration accounting."""
    manifest = load_manifest(_MANIFEST, _DIGEST)
    artifact = _selection_fixture(manifest)
    artifact["calibration"]["cells"][0]["metrics"]["raw"]["coverage_successes"] -= 1

    with pytest.raises(SelectionArtifactError, match="inconsistent calibration counts"):
        validate_selection_artifact(
            manifest,
            artifact,
            manifest_sha256=hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
            protected_blobs=artifact["protected_blobs"],
        )


def test_validation_gate_rejects_a_selection_artifact_missing_one_cell() -> None:
    """A mere selection file must not unlock validation without all frozen calibration cells."""
    manifest = load_manifest(_MANIFEST, _DIGEST)
    artifact = _selection_fixture(manifest)
    artifact["calibration"]["cells"].pop()

    with pytest.raises(SelectionArtifactError, match="complete calibration cell IDs"):
        validate_selection_artifact(
            manifest,
            artifact,
            manifest_sha256=hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
            protected_blobs=artifact["protected_blobs"],
        )


def test_validation_gate_rejects_a_non_first_passing_candidate() -> None:
    """Selecting a later passing floor must not consume the held-back validation seed."""
    manifest = load_manifest(_MANIFEST, _DIGEST)
    artifact = _selection_fixture(manifest)
    artifact["selected_candidate"] = manifest["candidate_floors"][2]

    with pytest.raises(SelectionArtifactError, match="first passing candidate"):
        validate_selection_artifact(
            manifest,
            artifact,
            manifest_sha256=hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
            protected_blobs=artifact["protected_blobs"],
        )


def test_cli_validation_stays_locked_without_verified_result_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A well-formed selection summary cannot unlock held-back validation by itself."""
    manifest = load_manifest(_MANIFEST, _DIGEST)
    artifact = _selection_fixture(manifest)
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_bytes(_MANIFEST.read_bytes())
    artifact_path = tmp_path / "selection.json"
    artifact_path.write_text(json.dumps(artifact), encoding="utf-8")
    path_map = manifest["integrity"]["protected_paths"]
    blobs = {path_map[key]: artifact["protected_blobs"][key] for key in artifact["protected_blobs"]}

    monkeypatch.setattr(calibration, "_ROOT", tmp_path)
    monkeypatch.setattr(calibration, "_MANIFEST", manifest_path)
    monkeypatch.setattr(calibration, "load_manifest", lambda: manifest)
    monkeypatch.setattr(calibration, "verify_protected_git_state", lambda *_args, **_kwargs: blobs)
    monkeypatch.setattr(
        "sys.argv", ["signal_calibration.py", "validate-selection", str(artifact_path)]
    )

    with pytest.raises(ManifestError, match="remains locked"):
        calibration._cli()


def test_git_preflight_rejects_self_consistent_uncommitted_protected_edit(tmp_path: Path) -> None:
    """A dirty harness with a matching worktree hash must still fail provenance verification."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"], cwd=tmp_path, check=True
    )
    subprocess.run(["git", "config", "user.name", "Icarus Test"], cwd=tmp_path, check=True)
    for name in ("manifest.json", "manifest.sha256", "harness.py", "estimator.py"):
        (tmp_path / name).write_text(name + "\n", encoding="ascii")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "fixture"], cwd=tmp_path, check=True)
    (tmp_path / "harness.py").write_text("edited\n", encoding="ascii")

    with pytest.raises(ManifestError, match="protected tracked file differs"):
        verify_protected_git_state(
            tmp_path,
            protected_paths=(
                "manifest.json",
                "manifest.sha256",
                "harness.py",
                "estimator.py",
            ),
            allowed_untracked=("AGENTS.md",),
        )
