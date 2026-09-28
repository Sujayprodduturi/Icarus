"""Deterministic contract tests for Step-6a.2 Task 3 slice 1A."""

from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import os
import stat
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar, cast

import numpy as np
import pytest
import scripts.signal_calibration as calibration
from scipy.stats import t
from scripts.signal_calibration import ManifestError, load_manifest

from icarus.engine.signalmetrics import (
    CandidateMoments,
    MetricRefusal,
    _cr2_moments,
)

_REAL_COUNTED_CHUNK_PROVIDER = calibration._CountedChunkProvider


def _run_git(repo: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)
    return completed.stdout.strip()


def _commit_all(repo: Path, message: str) -> str:
    _run_git(repo, "add", "-A")
    _run_git(repo, "commit", "-m", message)
    return _run_git(repo, "rev-parse", "HEAD")


def _reviewed_repo(tmp_path: Path) -> tuple[Path, dict[str, Any], bytes]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _run_git(repo, "init")
    _run_git(repo, "config", "user.email", "task3@example.invalid")
    _run_git(repo, "config", "user.name", "Task Three")
    _run_git(repo, "config", "core.autocrlf", "false")
    manifest = _manifest()
    protected = calibration._manifest_protected_paths(manifest)
    for index, relative in enumerate(protected):
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(f"protected-{index}\n".encode())
    (repo / "tracked.txt").write_text("reviewed\n", encoding="utf-8")
    reviewed = _commit_all(repo, "reviewed code")
    reviewed_tree = _run_git(repo, "rev-parse", f"{reviewed}^{{tree}}")
    manifest_sha = hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    evidence = f"docs/reviews/step6a2/{manifest_sha}"
    review_path = "docs/reviews/task3-independent-review.md"
    attestation_path = f"{evidence}/task3.review.json"
    (repo / review_path).parent.mkdir(parents=True, exist_ok=True)
    (repo / review_path).write_text("approved\n", encoding="utf-8")
    protected_blobs = {
        relative: hashlib.sha256((repo / relative).read_bytes()).hexdigest()
        for relative in protected
    }
    attestation = {
        "allowed_intervening_paths": sorted([review_path, attestation_path]),
        "manifest_sha256": manifest_sha,
        "protected_blobs": protected_blobs,
        "protocol_version": calibration.PROTOCOL_VERSION,
        "review_record_path": review_path,
        "review_scope": [
            "artifact_verifier",
            "counted_calibration",
            "held_back_validation",
            "resource_and_durability",
        ],
        "reviewed_at_utc": "2026-09-27T00:00:00.000000Z",
        "reviewed_commit": reviewed,
        "reviewed_tree": reviewed_tree,
        "reviewer": {"model": "gpt-6-astra", "role": "independent_statistical_safety"},
        "schema": "step6a2-task3-review-v1",
        "verdict": "APPROVED",
    }
    raw = calibration._canonical_bytes(attestation)
    path = repo / attestation_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    _commit_all(repo, "record independent review")
    return repo, manifest, raw


def _manifest() -> dict[str, Any]:
    return load_manifest()


def _events() -> dict[str, Any]:
    return {
        "metric": "raw",
        "emitted_ids": [0, 2, 5],
        "refusals": [
            {"reason": "EMPTY_SAMPLE", "ids": [1, 4]},
            {"reason": "INVALID_DF", "ids": [3]},
        ],
        "coverage_ids": [0],
        "lower_miss_ids": [2],
        "upper_miss_ids": [5],
        "joint_success_ids": [0],
    }


def test_strict_json_parser_accepts_only_exact_canonical_bytes() -> None:
    payload = {"a": [1, {"unicode": "✓"}], "z": 2}
    raw = (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")

    assert calibration._parse_canonical_json_bytes(raw, label="result") == payload


@pytest.mark.parametrize(
    "raw",
    [
        b'{"a":1,"a":2}\n',
        b'{"a":NaN}\n',
        b'{"a":Infinity}\n',
        b'{"a":-Infinity}\n',
        b'{"z":2,"a":1}\n',
        b'{"a": 1}\n',
        b'{"a":1}',
        b'{"a":1}\n\n',
        b'{"a":1}\ntrailing',
        b'\xef\xbb\xbf{"a":1}\n',
        b"[]\n",
        b'{"a":1}\xff\n',
        b'{"x":"\\ud800"}\n',
        b'{"x":' + (b"1" * 5_000) + b"}\n",
    ],
)
def test_strict_json_parser_rejects_noncanonical_or_ambiguous_bytes(raw: bytes) -> None:
    with pytest.raises(ManifestError, match=r"canonical|JSON|UTF-8|object"):
        calibration._parse_canonical_json_bytes(raw, label="result")


def test_strict_json_parser_normalizes_excessive_nesting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def nesting_failure(*_args: Any, **_kwargs: Any) -> None:
        raise RecursionError("maximum recursion depth exceeded while decoding JSON")

    monkeypatch.setattr(json, "loads", nesting_failure)
    with pytest.raises(ManifestError, match="JSON nesting"):
        calibration._parse_canonical_json_bytes(b'{"x":{}}\n', label="result")


def test_metric_events_validate_a_complete_mixed_partition() -> None:
    counts = calibration._validate_metric_event_partition(
        _manifest(),
        _events(),
        replicate_start=0,
        replicate_stop_exclusive=6,
        declared_metric="raw",
    )

    assert counts == calibration._MetricEventCounts(
        metric="raw",
        generated=6,
        emitted=3,
        refusal_total=3,
        coverage_successes=1,
        lower_tail_misses=1,
        upper_tail_misses=1,
        joint_successes=1,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        counts.emitted = 4  # type: ignore[misc]


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value["emitted_ids"].insert(1, 0), "strictly increasing"),
        (lambda value: value["refusals"][0].__setitem__("ids", [1]), "partition"),
        (lambda value: value["refusals"][0].__setitem__("ids", [0, 1, 4]), "disjoint"),
        (lambda value: value["refusals"][0].__setitem__("ids", [1, 4, 6]), "range"),
        (lambda value: value["refusals"][0].__setitem__("ids", [True, 4]), "integer"),
    ],
)
def test_metric_events_reject_bad_generated_partitions(mutate: Any, match: str) -> None:
    events = _events()
    mutate(events)

    with pytest.raises(ManifestError, match=match):
        calibration._validate_metric_event_partition(
            _manifest(),
            events,
            replicate_start=0,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value["coverage_ids"].append(2), "disjoint"),
        (lambda value: value.__setitem__("lower_miss_ids", []), "partition"),
        (lambda value: value.__setitem__("coverage_ids", [0, 4]), "emitted"),
        (lambda value: value.__setitem__("joint_success_ids", [2]), "joint"),
    ],
)
def test_metric_events_reject_bad_outcome_partitions(mutate: Any, match: str) -> None:
    events = _events()
    mutate(events)

    with pytest.raises(ManifestError, match=match):
        calibration._validate_metric_event_partition(
            _manifest(),
            events,
            replicate_start=0,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )


@pytest.mark.parametrize(
    ("mutate", "match"),
    [
        (lambda value: value["refusals"].reverse(), "order"),
        (
            lambda value: value["refusals"][0].__setitem__("reason", "NOT_FROZEN"),
            "reason",
        ),
        (lambda value: value["refusals"][0].__setitem__("ids", []), "empty"),
        (
            lambda value: value["refusals"].append({"reason": "EMPTY_SAMPLE", "ids": [3]}),
            "duplicate",
        ),
    ],
)
def test_metric_events_reject_bad_refusal_enums_and_order(mutate: Any, match: str) -> None:
    events = _events()
    mutate(events)

    with pytest.raises(ManifestError, match=match):
        calibration._validate_metric_event_partition(
            _manifest(),
            events,
            replicate_start=0,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )


def test_metric_events_require_exact_keys_metric_and_range_types() -> None:
    extra = _events()
    extra["parity"] = []
    with pytest.raises(ManifestError, match="keys"):
        calibration._validate_metric_event_partition(
            _manifest(),
            extra,
            replicate_start=0,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )

    wrong_metric = _events()
    wrong_metric["metric"] = "win"
    with pytest.raises(ManifestError, match="declared metric"):
        calibration._validate_metric_event_partition(
            _manifest(),
            wrong_metric,
            replicate_start=0,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )

    with pytest.raises(ManifestError, match="replicate range"):
        calibration._validate_metric_event_partition(
            _manifest(),
            _events(),
            replicate_start=False,
            replicate_stop_exclusive=6,
            declared_metric="raw",
        )


def _counts(**changes: Any) -> calibration._MetricEventCounts:
    values: dict[str, Any] = {
        "metric": "raw",
        "generated": 10_000,
        "emitted": 9_500,
        "refusal_total": 500,
        "coverage_successes": 9_000,
        "lower_tail_misses": 250,
        "upper_tail_misses": 250,
        "joint_successes": 9_000,
    }
    values.update(changes)
    return calibration._MetricEventCounts(**values)


def test_summary_recomputation_uses_the_declared_denominators() -> None:
    summary = calibration._recompute_metric_summary(
        _manifest(), phase="calibration", counts=_counts()
    )

    assert summary["counts"] == {
        "emitted": 9_500,
        "refusal_total": 500,
        "coverage_successes": 9_000,
        "lower_tail_misses": 250,
        "upper_tail_misses": 250,
        "joint_successes": 9_000,
    }
    checks = summary["checks"]
    assert checks["coverage_lower"]["trials"] == 9_500
    assert checks["lower_tail_upper"]["trials"] == 9_500
    assert checks["upper_tail_upper"]["trials"] == 9_500
    assert checks["emission_lower"]["trials"] == 10_000
    assert checks["joint_lower"]["trials"] == 10_000
    assert checks["coverage_lower"]["passed"] is True
    assert checks["joint_lower"]["passed"] is False


def test_summary_recomputation_handles_zero_emissions_without_invalid_beta() -> None:
    summary = calibration._recompute_metric_summary(
        _manifest(),
        phase="calibration",
        counts=_counts(
            emitted=0,
            refusal_total=10_000,
            coverage_successes=0,
            lower_tail_misses=0,
            upper_tail_misses=0,
            joint_successes=0,
        ),
    )

    assert summary["checks"]["coverage_lower"]["bound"] == 0.0
    assert summary["checks"]["lower_tail_upper"]["bound"] == 1.0
    assert summary["checks"]["upper_tail_upper"]["bound"] == 1.0
    assert all(check["passed"] is False for check in summary["checks"].values())


def test_summary_recomputation_pins_clopper_pearson_edges() -> None:
    manifest = _manifest()
    alpha = (
        manifest["acceptance"]["alpha_family"]
        / manifest["acceptance"]["family_sizes"]["calibration"]
    )
    summary = calibration._recompute_metric_summary(
        manifest,
        phase="calibration",
        counts=_counts(
            emitted=10_000,
            refusal_total=0,
            coverage_successes=10_000,
            lower_tail_misses=0,
            upper_tail_misses=0,
            joint_successes=10_000,
        ),
    )

    assert summary["checks"]["coverage_lower"]["bound"] == pytest.approx(
        calibration.clopper_pearson_lower(10_000, 10_000, alpha)
    )
    assert summary["checks"]["lower_tail_upper"]["bound"] == pytest.approx(
        calibration.clopper_pearson_upper(0, 10_000, alpha)
    )
    assert summary["checks"]["emission_lower"]["bound"] == pytest.approx(
        calibration.clopper_pearson_lower(10_000, 10_000, alpha)
    )
    assert all(check["passed"] is True for check in summary["checks"].values())


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"generated": 9_999, "refusal_total": 499}, "phase replicate"),
        ({"emitted": True}, "integer"),
        ({"refusal_total": 499}, "generated"),
        ({"lower_tail_misses": 249}, "outcome"),
        ({"joint_successes": 8_999}, "joint"),
    ],
)
def test_summary_recomputation_rejects_forged_counts(changes: dict[str, Any], match: str) -> None:
    with pytest.raises(ManifestError, match=match):
        calibration._recompute_metric_summary(
            _manifest(), phase="calibration", counts=_counts(**changes)
        )


def test_summary_recomputation_uses_validation_phase_contract() -> None:
    summary = calibration._recompute_metric_summary(
        _manifest(),
        phase="validation",
        counts=calibration._MetricEventCounts(
            metric="win",
            generated=20_000,
            emitted=19_000,
            refusal_total=1_000,
            coverage_successes=18_000,
            lower_tail_misses=500,
            upper_tail_misses=500,
            joint_successes=18_000,
        ),
    )

    emission = summary["checks"]["emission_lower"]
    assert emission["absolute_minimum"] == 19_000
    assert emission["trials"] == 20_000
    assert emission["rate"] == pytest.approx(0.95)


def _canonical(value: dict[str, Any]) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _result_envelope(phase: str) -> tuple[dict[str, Any], Any]:
    manifest = _manifest()
    commit = "a" * 40
    blob = "b" * 64
    protected = {path: blob for path in manifest["integrity"]["protected_paths"].values()}
    attempt = {"attempt_id": f"{commit}-{phase}", "started_at_utc": "2026-09-27T00:00:00.000000Z"}
    provenance = {
        "manifest_sha256": hashlib.sha256(_canonical(manifest)).hexdigest(),
        "method_version": manifest["method_version"],
        "selection_artifact_schema": manifest["selection_artifact_schema"],
        "reviewed_commit": commit,
        "invocation_commit": commit,
        "protected_blobs": protected,
        "review_attestation_sha256": "d" * 64,
        "claim_sha256": "e" * 64,
        "dependencies": manifest["versions"],
    }
    runtime = {
        "platform": "linux",
        "resource_backend": "linux-rlimit-as",
        "address_space_limit_bytes": 2_147_483_648,
        "peak_rss_before_verification_bytes": 2_000_000,
        "peak_rss_source": "getrusage-ru_maxrss-kib",
        "planned_peak_bytes": 3_000_000,
        "maximum_result_bytes": 100_000_000,
        "generation_elapsed_seconds": 1.0,
        "deadline_seconds": 7_200,
        "resource_state": "WITHIN_LIMIT",
    }
    phase_data = manifest["phases"][phase]
    result = {
        "schema": "step6a2-calibration-result-v1",
        "protocol_version": manifest["protocol_version"],
        "phase": phase,
        "attempt": attempt,
        "provenance": provenance,
        "phase_contract": {
            "master_seed": phase_data["master_seed"],
            "replicates_per_cell": phase_data["replicates"],
            "cell_definitions": phase_data["cells"],
            "candidate_floors": manifest["candidate_floors"],
            "metrics": manifest["acceptance"]["metrics"],
            "checks": manifest["acceptance"]["checks"],
            "family_size": manifest["acceptance"]["family_sizes"][phase],
        },
        "chunks": [],
        "summary": {},
        "runtime": runtime,
        "terminal": {
            "state": "UNVERIFIED",
            "ended_at_utc": "2026-09-27T00:00:01.000000Z",
            "failure": None,
        },
    }
    floor = (6, 4.0) if phase == "validation" else None
    context = calibration._ExpectedPhaseContext(
        phase=phase,
        provenance_bytes=_canonical(provenance),
        attempt_bytes=_canonical(attempt),
        runtime_bytes=_canonical(runtime),
        verified_calibration_floor=floor,
    )
    return result, context


def test_result_verifier_rejects_incomplete_evidence() -> None:
    result, context = _result_envelope("calibration")
    with pytest.raises(ManifestError):
        calibration.validate_phase_result(_manifest(), result, context)


def _complete_result(phase: str) -> tuple[dict[str, Any], Any]:
    result, context = _result_envelope(phase)
    manifest = _manifest()
    metrics = manifest["acceptance"]["metrics"]
    replicates = manifest["phases"][phase]["replicates"]
    summaries = []
    for cell in manifest["phases"][phase]["cells"]:
        cell_metrics = []
        for metric in metrics:
            counts = calibration._MetricEventCounts(
                metric, replicates, replicates, 0, replicates, 0, 0, replicates
            )
            cell_metrics.append(
                calibration._recompute_metric_summary(manifest, phase=phase, counts=counts)
            )
        summaries.append({"cell_id": cell["id"], "generated": replicates, "metrics": cell_metrics})
        for chunk_id, start in enumerate(range(0, replicates, 256)):
            stop = min(start + 256, replicates)
            events = []
            for metric in metrics:
                target_key = {
                    "raw": "raw_mean",
                    "win": "win_probability",
                    "synthetic_excess": "excess_mean",
                }[metric]
                target = cell["targets"][target_key]
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
                parity = [
                    {
                        "replicate_id": replicate_id,
                        "triggers": ["ordinary"],
                        "max_abs_outcome": 1.0,
                        "batch": interval,
                        "scalar": dict(interval),
                        "cr1": cr1,
                    }
                    for replicate_id in calibration.parity_audit_ids(replicates)
                    if start <= replicate_id < stop
                ]
                events.append(
                    {
                        "metric": metric,
                        "emitted_ids": list(range(start, stop)),
                        "refusals": [],
                        "coverage_ids": list(range(start, stop)),
                        "lower_miss_ids": [],
                        "upper_miss_ids": [],
                        "joint_success_ids": list(range(start, stop)),
                        "parity": parity,
                    }
                )
            result["chunks"].append(
                {
                    "cell_id": cell["id"],
                    "chunk_id": chunk_id,
                    "replicate_start": start,
                    "replicate_stop_exclusive": stop,
                    "metrics": events,
                }
            )
    floors = (
        manifest["candidate_floors"]
        if phase == "calibration"
        else [manifest["candidate_floors"][0]]
    )
    result["summary"] = {
        "cells": summaries,
        "candidate_results": [
            {"floor": floor, "fixed_refusal_controls_passed": True, "passed": True}
            for floor in floors
        ],
        "selected_floor": floors[0],
        "parity_complete": True,
        "phase_verdict": "PASSED",
    }
    return result, context


@pytest.mark.parametrize("phase", ["calibration", "validation"])
def test_complete_phase_result_verifies_all_frozen_cells(phase: str) -> None:
    result, context = _complete_result(phase)
    verified = calibration.validate_phase_result(_manifest(), result, context)
    assert verified.phase == phase
    assert verified.phase_verdict == "PASSED"
    assert verified.selected_floor == (6, 4.0)


@pytest.fixture(scope="module")
def full_calibration() -> tuple[dict[str, Any], Any]:
    return _complete_result("calibration")


@pytest.fixture(scope="module")
def full_validation() -> tuple[dict[str, Any], Any]:
    return _complete_result("validation")


def _replace_first_chunk(result: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    changed = dict(result)
    changed["chunks"] = list(result["chunks"])
    chunk = dict(changed["chunks"][0])
    changed["chunks"][0] = chunk
    return changed, chunk


@pytest.mark.parametrize(
    "field,bad",
    [
        ("phase", "validation"),
        ("schema", "wrong"),
        ("protocol_version", "wrong"),
    ],
)
def test_result_refuses_wrong_envelope(
    full_calibration: tuple[dict[str, Any], Any], field: str, bad: Any
) -> None:
    original, context = full_calibration
    changed = dict(original)
    changed[field] = bad
    with pytest.raises(ManifestError):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("platform", "win32"),
        ("resource_backend", "none"),
        ("peak_rss_source", "windows"),
        ("address_space_limit_bytes", True),
        ("deadline_seconds", 7199),
        ("generation_elapsed_seconds", float("inf")),
        ("planned_peak_bytes", -1),
        ("resource_state", "EXCEEDED"),
    ],
)
def test_result_refuses_invalid_expected_runtime(
    full_calibration: tuple[dict[str, Any], Any], field: str, bad: Any
) -> None:
    original, context = full_calibration
    runtime = dict(original["runtime"])
    runtime[field] = bad
    changed = dict(original)
    changed["runtime"] = runtime
    with pytest.raises(ManifestError):
        changed_context = dataclasses.replace(context, runtime_bytes=_canonical(runtime))
        calibration.validate_phase_result(_manifest(), changed, changed_context)


def test_result_refuses_unbound_expected_context(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    with pytest.raises(ManifestError, match="context"):
        calibration.validate_phase_result(_manifest(), original, dict(dataclasses.asdict(context)))  # type: ignore[arg-type]


def test_result_refuses_wrong_manifest_hash(full_calibration: tuple[dict[str, Any], Any]) -> None:
    original, context = full_calibration
    provenance = dict(original["provenance"])
    provenance["manifest_sha256"] = "0" * 64
    changed = dict(original)
    changed["provenance"] = provenance
    context = dataclasses.replace(context, provenance_bytes=_canonical(provenance))
    with pytest.raises(ManifestError, match="manifest"):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize(
    "mutation", ["omit", "overlap", "wrong_cell", "wrong_metric", "candidate_refusal"]
)
def test_result_refuses_chunk_or_partition_tamper(
    full_calibration: tuple[dict[str, Any], Any], mutation: str
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    if mutation == "omit":
        changed["chunks"].pop(0)
    elif mutation == "wrong_cell":
        chunk["cell_id"] = 1001
    else:
        chunk["metrics"] = list(chunk["metrics"])
        events = dict(chunk["metrics"][0])
        chunk["metrics"][0] = events
        if mutation == "overlap":
            events["emitted_ids"] = [0, *events["emitted_ids"]]
        elif mutation == "wrong_metric":
            events["metric"] = "win"
        else:
            events["emitted_ids"] = list(range(1, 256))
            events["coverage_ids"] = list(range(1, 256))
            events["joint_success_ids"] = list(range(1, 256))
            events["refusals"] = [{"reason": "BELOW_CALIBRATED_DF", "ids": [0]}]
    with pytest.raises(ManifestError):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize(
    "mutation", ["missing", "duplicate", "wrong_trigger", "wrong_scalar", "forged_success"]
)
def test_result_refuses_parity_tamper(
    full_calibration: tuple[dict[str, Any], Any], mutation: str
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    records = list(events["parity"])
    events["parity"] = records
    if mutation == "missing":
        records.pop(0)
    elif mutation == "duplicate":
        records.insert(1, records[0])
    else:
        record = dict(records[0])
        records[0] = record
        if mutation == "wrong_trigger":
            record["triggers"] = ["ordinary", "t_critical"]
        elif mutation == "wrong_scalar":
            scalar = dict(record["scalar"])
            scalar["mean"] = 1.0
            record["scalar"] = scalar
        else:
            events["coverage_ids"] = list(range(1, 256))
    with pytest.raises(ManifestError):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_result_refuses_forged_cp_bound(full_calibration: tuple[dict[str, Any], Any]) -> None:
    original, context = full_calibration
    changed = dict(original)
    summary = dict(original["summary"])
    changed["summary"] = summary
    cells = list(summary["cells"])
    summary["cells"] = cells
    cell = dict(cells[0])
    cells[0] = cell
    metrics = list(cell["metrics"])
    cell["metrics"] = metrics
    metric = dict(metrics[0])
    metrics[0] = metric
    checks = dict(metric["checks"])
    metric["checks"] = checks
    coverage = dict(checks["coverage_lower"])
    checks["coverage_lower"] = coverage
    coverage["bound"] = 1.0
    with pytest.raises(ManifestError, match="summary"):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize("floor", [None, (8, 6.0), (6, 4.0, 0), (True, 4.0)])
def test_validation_requires_external_exact_floor(
    full_validation: tuple[dict[str, Any], Any], floor: Any
) -> None:
    original, context = full_validation
    with pytest.raises(ManifestError):
        altered = dataclasses.replace(context, verified_calibration_floor=floor)
        calibration.validate_phase_result(_manifest(), original, altered)


def test_parity_accepts_sum_of_relative_and_scaled_absolute_tolerances(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    scalar = dict(record["scalar"])
    record["scalar"] = scalar
    scalar["cr2_variance"] = 1.0 + 1.0005e-11
    margin = float(t.ppf(0.975, 10.0)) * scalar["cr2_variance"] ** 0.5
    scalar["raw_lower"] = -margin
    scalar["raw_upper"] = margin
    calibration.validate_phase_result(_manifest(), changed, context)


def test_parity_refuses_identically_forged_wider_raw_bounds(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    for name in ("batch", "scalar"):
        interval = dict(record[name])
        interval["raw_lower"] -= 1.0
        interval["raw_upper"] += 1.0
        record[name] = interval
    with pytest.raises(ManifestError, match="interval"):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_parity_refuses_overflowed_scaled_tolerance(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    record["max_abs_outcome"] = 1e308
    with pytest.raises(ManifestError, match="tolerance"):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_selected_floor_requires_frozen_json_number_type(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed = dict(original)
    summary = dict(original["summary"])
    changed["summary"] = summary
    summary["selected_floor"] = {"minimum_blocks": 6, "minimum_nu": 4.0}
    with pytest.raises(ManifestError, match="floor"):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize(
    "field,bad",
    [
        ("peak_rss_before_verification_bytes", 2_147_483_649),
        ("planned_peak_bytes", 2_147_483_649),
        ("generation_elapsed_seconds", 7_201.0),
    ],
)
def test_runtime_refuses_frozen_limit_overage(
    full_calibration: tuple[dict[str, Any], Any],
    field: str,
    bad: Any,
) -> None:
    original, context = full_calibration
    runtime = dict(original["runtime"])
    runtime[field] = bad
    changed = dict(original)
    changed["runtime"] = runtime
    context = dataclasses.replace(context, runtime_bytes=_canonical(runtime))
    with pytest.raises(ManifestError, match="runtime"):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_parity_refusal_must_match_exact_event_reason(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["emitted_ids"] = list(range(1, 256))
    events["coverage_ids"] = list(range(1, 256))
    events["joint_success_ids"] = list(range(1, 256))
    events["refusals"] = [{"reason": "ZERO_VARIANCE", "ids": [0]}]
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    record["triggers"] = ["ordinary"]
    for name in ("batch", "scalar", "cr1"):
        interval: dict[str, Any] = {key: None for key in record[name]}
        interval["status"] = "INVALID_DF"
        record[name] = interval
    with pytest.raises(ManifestError, match="status"):
        calibration.validate_phase_result(_manifest(), changed, context)


@pytest.mark.parametrize("stamp", ["2026-13-27T00:00:00.000000Z", "2026-09-27T25:00:00.000000Z"])
def test_expected_context_refuses_invalid_utc_calendar(stamp: str) -> None:
    result, context = _result_envelope("calibration")
    attempt = dict(result["attempt"])
    attempt["started_at_utc"] = stamp
    changed = dict(result)
    changed["attempt"] = attempt
    context = dataclasses.replace(context, attempt_bytes=_canonical(attempt))
    with pytest.raises(ManifestError, match="UTC"):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_expected_context_refuses_missing_provenance_key() -> None:
    result, context = _result_envelope("calibration")
    provenance = dict(result["provenance"])
    provenance.pop("manifest_sha256")
    context = dataclasses.replace(context, provenance_bytes=_canonical(provenance))
    with pytest.raises(ManifestError, match="provenance"):
        calibration.validate_phase_result(_manifest(), result, context)


def test_complete_statistical_failure_is_verified_without_a_floor(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed = dict(original)
    changed["chunks"] = list(original["chunks"])
    for index in range(40):
        chunk = dict(changed["chunks"][index])
        changed["chunks"][index] = chunk
        chunk["metrics"] = list(chunk["metrics"])
        events = dict(chunk["metrics"][0])
        chunk["metrics"][0] = events
        start, stop = chunk["replicate_start"], chunk["replicate_stop_exclusive"]
        events.update(
            {
                "emitted_ids": [],
                "refusals": [{"reason": "ZERO_VARIANCE", "ids": list(range(start, stop))}],
                "coverage_ids": [],
                "lower_miss_ids": [],
                "upper_miss_ids": [],
                "joint_success_ids": [],
                "parity": [
                    {
                        **record,
                        "triggers": ["ordinary", "zero"],
                        **{
                            name: {
                                key: ("ZERO_VARIANCE" if key == "status" else None)
                                for key in record[name]
                            }
                            for name in ("batch", "scalar", "cr1")
                        },
                    }
                    for record in events["parity"]
                ],
            }
        )
    summary = dict(original["summary"])
    changed["summary"] = summary
    summary["cells"] = list(summary["cells"])
    cell = dict(summary["cells"][0])
    summary["cells"][0] = cell
    cell["metrics"] = list(cell["metrics"])
    cell["metrics"][0] = calibration._recompute_metric_summary(
        _manifest(),
        phase="calibration",
        counts=calibration._MetricEventCounts("raw", 10_000, 0, 10_000, 0, 0, 0, 0),
    )
    summary["candidate_results"] = [
        {**candidate, "passed": False} for candidate in summary["candidate_results"]
    ]
    summary["selected_floor"] = None
    summary["phase_verdict"] = "FAILED"
    verified = calibration.validate_phase_result(_manifest(), changed, context)
    assert verified.phase_verdict == "FAILED"
    assert verified.selected_floor is None


def test_parity_sample_variance_uses_squared_outcome_scale(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    record["max_abs_outcome"] = 10_000_000.0
    record["triggers"] = ["near_zero", "ordinary"]
    scalar = dict(record["scalar"])
    record["scalar"] = scalar
    scalar["sample_variance"] = 1.5
    calibration.validate_phase_result(_manifest(), changed, context)


def test_parity_huge_json_integer_refuses_with_manifest_error(
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    original, context = full_calibration
    changed, chunk = _replace_first_chunk(original)
    chunk["metrics"] = list(chunk["metrics"])
    events = dict(chunk["metrics"][0])
    chunk["metrics"][0] = events
    events["parity"] = list(events["parity"])
    record = dict(events["parity"][0])
    events["parity"][0] = record
    record["max_abs_outcome"] = 10**400
    with pytest.raises(ManifestError, match=r"finite|number"):
        calibration.validate_phase_result(_manifest(), changed, context)


def test_validation_huge_floor_integer_refuses_with_manifest_error() -> None:
    _, context = _result_envelope("validation")
    with pytest.raises(ManifestError, match="floor"):
        dataclasses.replace(context, verified_calibration_floor=(6, 10**400))


def test_unhashable_expected_phase_refuses_with_manifest_error() -> None:
    _, context = _result_envelope("calibration")
    with pytest.raises(ManifestError, match="phase"):
        dataclasses.replace(context, phase=[])


def test_review_attestation_and_clean_git_history_are_verified(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    deadline = calibration._Deadline(0.0, 60.0, lambda: 1.0)
    attestation = calibration._parse_review_attestation(manifest, raw)

    proof = calibration._verify_reviewed_git_state(
        repo,
        manifest,
        attestation,
        deadline,
        allowed_untracked=("AGENTS.md",),
    )

    assert proof.invocation_commit == _run_git(repo, "rev-parse", "HEAD")
    assert proof.reviewed_commit == attestation.reviewed_commit


def test_review_attestation_rejects_unknown_key(tmp_path: Path) -> None:
    _, manifest, raw = _reviewed_repo(tmp_path)
    payload = json.loads(raw)
    payload["unexpected"] = True

    with pytest.raises(ManifestError, match="review attestation"):
        calibration._parse_review_attestation(manifest, calibration._canonical_bytes(payload))


def test_git_proof_rejects_change_then_revert_hidden_by_endpoint(tmp_path: Path) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    attestation_path = next(repo.glob("docs/reviews/step6a2/*/task3.review.json"))
    attestation = calibration._parse_review_attestation(manifest, attestation_path.read_bytes())
    reviewed_bytes = (repo / "tracked.txt").read_bytes()
    (repo / "tracked.txt").write_text("temporarily changed\n", encoding="utf-8")
    _commit_all(repo, "unapproved tracked change")
    (repo / "tracked.txt").write_bytes(reviewed_bytes)
    _commit_all(repo, "revert unapproved tracked change")

    with pytest.raises(ManifestError, match="intervening"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            attestation,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_proof_compares_every_tracked_worktree_byte(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    (repo / "tracked.txt").write_text("dirty but status is not authority\n", encoding="utf-8")
    _run_git(repo, "update-index", "--skip-worktree", "tracked.txt")

    with pytest.raises(ManifestError, match="tracked file differs"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            calibration._parse_review_attestation(manifest, raw),
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_proof_allows_only_the_exact_untracked_name(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    (repo / "AGENTS.md.extra").write_text("not allowed\n", encoding="utf-8")

    with pytest.raises(ManifestError, match="untracked"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            calibration._parse_review_attestation(manifest, raw),
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_subprocess_uses_shared_deadline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, float] = {}

    def timed_out(*args: Any, **kwargs: Any) -> Any:
        seen["timeout"] = kwargs["timeout"]
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timed_out)
    deadline = calibration._Deadline(10.0, 5.0, lambda: 12.0)

    with pytest.raises(ManifestError, match="deadline"):
        calibration._git_with_deadline(tmp_path, deadline, "status")

    assert seen["timeout"] == pytest.approx(3.0)


def test_worktree_reader_rejects_symlink_component(tmp_path: Path) -> None:
    if os.name == "nt":
        pytest.skip(
            "Windows symlink creation requires privileges; native counted mode refuses Windows"
        )
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret").write_text("outside\n", encoding="utf-8")
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(ManifestError, match="symlink"):
        calibration._read_tracked_worktree_bytes(repo, "link/secret")


class _ResourceOps:
    def __init__(self, mountinfo: bytes, readback: tuple[int, int] | None = None) -> None:
        self.mountinfo = mountinfo
        self.readback = readback
        self.installed: tuple[int, int] | None = None

    def native_environment_evidence(self) -> dict[str, Any]:
        return {"osrelease": "6.8.0", "pid1": "systemd", "container": False}

    def read_mountinfo(self) -> bytes:
        return self.mountinfo

    def set_address_space_limit(self, soft: int, hard: int) -> None:
        self.installed = (soft, hard)

    def get_address_space_limit(self) -> tuple[int, int]:
        assert self.installed is not None
        return self.readback or self.installed

    def current_vms_bytes(self) -> int:
        return 128 * 1024 * 1024

    def current_rss_bytes(self) -> int:
        return 96 * 1024 * 1024

    def peak_rss_bytes(self) -> int:
        return 64 * 1024 * 1024


def _ext4_mountinfo(root: Path) -> bytes:
    rendered = str(root).replace("\\", "/").replace(" ", "\\040")
    return f"36 25 0:32 / {rendered} rw,relatime - ext4 /dev/test rw\n".encode()


def test_linux_resource_boundary_installs_manifest_limit_and_separates_rss(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))

    boundary = calibration._prepare_linux_resource_boundary(
        manifest,
        tmp_path,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    expected = manifest["runtime_limits"]["max_peak_rss_bytes"]
    assert ops.installed == (expected, expected)
    assert boundary.address_space_limit_bytes == expected
    assert boundary.peak_rss_bytes == 64 * 1024 * 1024
    assert boundary.peak_rss_source == "getrusage-ru_maxrss-kib"


def test_linux_resource_boundary_rejects_overlay_before_limit_install(tmp_path: Path) -> None:
    mountinfo = _ext4_mountinfo(tmp_path).replace(b" - ext4 ", b" - overlay ")
    ops = _ResourceOps(mountinfo)

    with pytest.raises(ManifestError, match="filesystem"):
        calibration._prepare_linux_resource_boundary(
            _manifest(),
            tmp_path,
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )

    assert ops.installed is None


def test_linux_resource_boundary_rejects_limit_readback_mismatch(tmp_path: Path) -> None:
    expected = _manifest()["runtime_limits"]["max_peak_rss_bytes"]
    ops = _ResourceOps(_ext4_mountinfo(tmp_path), (expected, expected - 1))

    with pytest.raises(ManifestError, match="RLIMIT_AS"):
        calibration._prepare_linux_resource_boundary(
            _manifest(),
            tmp_path,
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )


def test_mount_resolution_uses_longest_containing_mount(tmp_path: Path) -> None:
    parent = str(tmp_path).replace("\\", "/")
    child = str(tmp_path / "evidence").replace("\\", "/")
    mountinfo = (
        f"1 0 0:1 / {parent} rw - ext4 /dev/a rw\n2 1 0:2 / {child} rw - xfs /dev/b rw\n"
    ).encode()

    assert calibration._filesystem_type_for_path(mountinfo, tmp_path / "evidence" / "x") == "xfs"


def test_native_windows_refuses_before_linux_ops_or_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    touched: list[str] = []

    def forbidden_ops() -> Any:
        touched.append("linux-ops")
        raise AssertionError("Linux syscalls must not be constructed on Windows")

    monkeypatch.setattr(calibration, "_ROOT", tmp_path)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "win32")
    monkeypatch.setattr(calibration, "_NativeLinuxOps", forbidden_ops)

    with pytest.raises(ManifestError, match="native Linux"):
        calibration._begin_counted_phase("calibration")

    assert touched == []
    assert not (tmp_path / "docs/reviews/step6a2").exists()


def test_resource_preflight_honours_deadline_before_syscalls(tmp_path: Path) -> None:
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))

    with pytest.raises(ManifestError, match="deadline"):
        calibration._prepare_linux_resource_boundary(
            _manifest(),
            tmp_path,
            ops,
            calibration._Deadline(0.0, 1.0, lambda: 2.0),
        )

    assert ops.installed is None


class _EvidenceOps:
    def __init__(self, root: Path) -> None:
        self.nodes: dict[Path, dict[str, Any]] = {
            root: {"kind": "dir", "dev": 1, "ino": 1, "nlink": 1, "data": bytearray()}
        }
        self.fds: dict[int, Path] = {}
        self.offsets: dict[int, int] = {}
        self.next_fd = 10
        self.next_ino = 2
        self.calls: list[tuple[Any, ...]] = []
        self.fail_on: str | None = None
        self.short_write = 1
        self.swap_directory = False

    def _fail(self, operation: str) -> None:
        if self.fail_on == operation:
            raise OSError(f"injected {operation} failure")

    def _fd(self, path: Path) -> int:
        fd = self.next_fd
        self.next_fd += 1
        self.fds[fd] = path
        self.offsets[fd] = 0
        return fd

    def _stat(self, path: Path) -> Any:
        node = self.nodes[path]
        mode = stat.S_IFDIR | 0o700 if node["kind"] == "dir" else stat.S_IFREG | 0o600
        return SimpleNamespace(
            st_mode=mode,
            st_dev=node["dev"],
            st_ino=node["ino"],
            st_nlink=node["nlink"],
            st_size=len(node["data"]),
        )

    def open_root(self, path: Path) -> int:
        return self._fd(path)

    def open_dir_at(self, parent_fd: int, name: str) -> int:
        path = self.fds[parent_fd] / name
        if path not in self.nodes:
            raise FileNotFoundError(path)
        return self._fd(path)

    def mkdir_at(self, parent_fd: int, name: str, mode: int) -> None:
        self._fail("mkdir")
        path = self.fds[parent_fd] / name
        if path in self.nodes:
            raise FileExistsError(path)
        self.nodes[path] = {
            "kind": "dir",
            "dev": 1,
            "ino": self.next_ino,
            "nlink": 1,
            "data": bytearray(),
        }
        self.next_ino += 1
        self.calls.append(("mkdir", path, mode))

    def fstat(self, fd: int) -> Any:
        return self._stat(self.fds[fd])

    def stat_path(self, path: Path) -> Any:
        value = self._stat(path)
        if self.swap_directory:
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_dev=value.st_dev,
                st_ino=value.st_ino + 1000,
                st_nlink=value.st_nlink,
            )
        return value

    def stat_at(self, parent_fd: int, name: str) -> Any:
        return self._stat(self.fds[parent_fd] / name)

    def fsync(self, fd: int) -> None:
        self._fail("fsync")
        self.calls.append(("fsync", self.fds[fd]))

    def close(self, fd: int) -> None:
        self._fail("close")
        self.calls.append(("close", self.fds[fd]))
        del self.fds[fd]
        del self.offsets[fd]

    def open_exclusive_file(self, directory_fd: int, name: str, mode: int) -> int:
        self._fail("open")
        path = self.fds[directory_fd] / name
        if path in self.nodes:
            raise FileExistsError(path)
        self.nodes[path] = {
            "kind": "file",
            "dev": 1,
            "ino": self.next_ino,
            "nlink": 1,
            "data": bytearray(),
        }
        self.next_ino += 1
        self.calls.append(("open-file", path, mode))
        return self._fd(path)

    def open_existing_file(self, directory_fd: int, name: str) -> int:
        self._fail("reopen")
        path = self.fds[directory_fd] / name
        if path not in self.nodes:
            raise FileNotFoundError(path)
        self.calls.append(("reopen-file", path))
        return self._fd(path)

    def write(self, fd: int, data: bytes) -> int:
        self._fail("write")
        amount = min(self.short_write, len(data))
        node = self.nodes[self.fds[fd]]
        offset = self.offsets[fd]
        end = offset + amount
        if end > len(node["data"]):
            node["data"].extend(b"\0" * (end - len(node["data"])))
        node["data"][offset:end] = data[:amount]
        self.offsets[fd] = end
        self.calls.append(("write", self.fds[fd], amount))
        return amount

    def tell(self, fd: int) -> int:
        return self.offsets[fd]

    def pread(self, fd: int, size: int, offset: int) -> bytes:
        self._fail("pread")
        data = self.nodes[self.fds[fd]]["data"]
        self.calls.append(("pread", self.fds[fd], size, offset))
        return bytes(data[offset : offset + size])

    def read_all(self, fd: int) -> bytes:
        return bytes(self.nodes[self.fds[fd]]["data"])


def _fake_evidence_store(tmp_path: Path) -> tuple[Any, _EvidenceOps]:
    ops = _EvidenceOps(tmp_path)
    store = calibration._open_or_create_evidence_directory(
        tmp_path,
        Path("docs/reviews/step6a2/abc"),
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    return store, ops


def test_evidence_directory_creation_fsyncs_each_new_directory_and_parent(
    tmp_path: Path,
) -> None:
    store, ops = _fake_evidence_store(tmp_path)

    assert store.path == tmp_path / "docs/reviews/step6a2/abc"
    mkdir_calls = [call for call in ops.calls if call[0] == "mkdir"]
    fsync_calls = [call for call in ops.calls if call[0] == "fsync"]
    assert len(mkdir_calls) == 4
    assert len(fsync_calls) == 8


def test_evidence_directory_rechecks_retained_fd_against_path(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    ops.swap_directory = True

    with pytest.raises(ManifestError, match="directory identity"):
        store.recheck()


def test_claim_write_handles_short_writes_and_is_immutable(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    claim = b'{"schema":"claim"}\n'

    retained = calibration._write_immutable_claim(store, "calibration.claim", claim)

    path = store.path / "calibration.claim"
    assert bytes(ops.nodes[path]["data"]) == claim
    assert retained.fd in ops.fds
    with pytest.raises(ManifestError, match="already exists"):
        calibration._write_immutable_claim(store, "calibration.claim", b"different\n")
    assert bytes(ops.nodes[path]["data"]) == claim


@pytest.mark.parametrize("operation", ["write", "fsync", "close"])
def test_failed_claim_is_left_reserved_without_cleanup(tmp_path: Path, operation: str) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    ops.fail_on = operation

    with pytest.raises(ManifestError, match=operation):
        calibration._write_immutable_claim(store, "calibration.claim", b"claim\n")

    assert store.path / "calibration.claim" in ops.nodes
    assert all(call[0] != "unlink" for call in ops.calls)


@pytest.mark.parametrize(
    ("mode", "nlink", "match"),
    [(stat.S_IFLNK | 0o777, 1, "regular"), (stat.S_IFREG | 0o600, 2, "link")],
)
def test_evidence_file_rejects_symlink_or_extra_hard_link(
    tmp_path: Path, mode: int, nlink: int, match: str
) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    original_fstat = ops.fstat

    def bad_fstat(fd: int) -> Any:
        value = original_fstat(fd)
        if ops.nodes[ops.fds[fd]]["kind"] == "file":
            return SimpleNamespace(
                st_mode=mode, st_dev=value.st_dev, st_ino=value.st_ino, st_nlink=nlink
            )
        return value

    ops.fstat = bad_fstat  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match=match):
        calibration._write_immutable_claim(store, "calibration.claim", b"claim\n")


def test_result_reservation_retains_handle_and_does_not_open_seal(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)

    result = calibration._reserve_result_file(store, "calibration-result.json")

    assert result.name == "calibration-result.json"
    assert result.fd in ops.fds
    assert all("seal" not in str(call) for call in ops.calls)


@pytest.mark.parametrize(
    "review_path",
    [
        "docs/reviews/../escape.md",
        "docs/reviews//double.md",
        "docs\\reviews\\backslash.md",
        "docs/reviews/control\x01.md",
        "docs/reviews/nul\x00.md",
        "/docs/reviews/absolute.md",
    ],
)
def test_review_attestation_rejects_noncanonical_review_path(
    tmp_path: Path, review_path: str
) -> None:
    _, manifest, raw = _reviewed_repo(tmp_path)
    payload = json.loads(raw)
    attestation_path = next(
        value
        for value in payload["allowed_intervening_paths"]
        if value.endswith("task3.review.json")
    )
    payload["review_record_path"] = review_path
    payload["allowed_intervening_paths"] = sorted([review_path, attestation_path])

    with pytest.raises(ManifestError, match="review record path"):
        calibration._parse_review_attestation(manifest, calibration._canonical_bytes(payload))


@pytest.mark.parametrize(
    ("field", "value", "match"),
    [
        ("manifest_sha256", "0" * 64, "identity"),
        ("reviewed_tree", "0" * 40, "reviewed tree"),
        ("review_scope", [], "scope"),
        ("reviewed_commit", True, "reviewed_commit"),
    ],
)
def test_review_attestation_rejects_forged_valid_shape(
    tmp_path: Path, field: str, value: Any, match: str
) -> None:
    _, manifest, raw = _reviewed_repo(tmp_path)
    payload = json.loads(raw)
    payload[field] = value

    if field == "reviewed_tree":
        repo = tmp_path / "repo"
        attestation_path = next(repo.glob("docs/reviews/step6a2/*/task3.review.json"))
        attestation_path.write_bytes(calibration._canonical_bytes(payload))
        _commit_all(repo, "record forged reviewed tree")
        parsed = calibration._parse_review_attestation(manifest, attestation_path.read_bytes())
        with pytest.raises(ManifestError, match=match):
            calibration._verify_reviewed_git_state(
                repo,
                manifest,
                parsed,
                calibration._Deadline(0.0, 60.0, lambda: 1.0),
                allowed_untracked=("AGENTS.md",),
            )
    else:
        with pytest.raises(ManifestError, match=match):
            calibration._parse_review_attestation(manifest, calibration._canonical_bytes(payload))


def test_mount_resolution_rejects_ambiguous_stacked_mounts(tmp_path: Path) -> None:
    target = str(tmp_path).replace("\\", "/")
    mountinfo = (
        f"1 0 0:1 / {target} rw - ext4 /dev/a rw\n2 1 0:2 / {target} rw - xfs /dev/b rw\n"
    ).encode()

    with pytest.raises(ManifestError, match="ambiguous"):
        calibration._filesystem_type_for_path(mountinfo, tmp_path / "file")


@pytest.mark.parametrize(
    "evidence",
    [
        {"osrelease": "6.1.0-microsoft-standard-WSL2", "pid1": "systemd", "container": False},
        {"osrelease": "6.8.0", "pid1": "systemd", "container": True},
        {"osrelease": "6.8.0", "pid1": "python", "container": False},
    ],
)
def test_native_linux_environment_proof_refuses_wsl_container_or_unknown_init(
    evidence: dict[str, Any],
) -> None:
    with pytest.raises(ManifestError, match="native Linux"):
        calibration._verify_native_linux_environment(evidence)


def test_evidence_store_retains_all_ancestor_directory_handles(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)

    assert len(store.handles) == 5
    assert all(handle.fd in ops.fds for handle in store.handles)


def test_evidence_directory_failure_closes_every_opened_handle(tmp_path: Path) -> None:
    ops = _EvidenceOps(tmp_path)
    ops.fail_on = "mkdir"

    with pytest.raises(ManifestError, match="directory"):
        calibration._open_or_create_evidence_directory(
            tmp_path,
            Path("docs/reviews/step6a2/abc"),
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )

    assert ops.fds == {}


def test_result_identity_failure_closes_new_file_handle(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    baseline_fds = set(ops.fds)
    original = ops.fstat

    def changed_file_identity(fd: int) -> Any:
        value = original(fd)
        if ops.nodes[ops.fds[fd]]["kind"] == "file":
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_dev=value.st_dev,
                st_ino=value.st_ino + 1,
                st_nlink=value.st_nlink,
            )
        return value

    ops.fstat = changed_file_identity  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="identity"):
        calibration._reserve_result_file(store, "calibration-result.json")

    assert set(ops.fds) == baseline_fds


@pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux resource syscalls")
def test_native_linux_child_enforces_production_address_space_boundary(
    tmp_path: Path,
) -> None:
    script = (
        "import sys,time\n"
        "from pathlib import Path\n"
        "import scripts.signal_calibration as c\n"
        "m=c.load_manifest()\n"
        "ops=c._NativeLinuxOps()\n"
        "d=c._Deadline(time.monotonic(),30.0,time.monotonic)\n"
        "b=c._prepare_linux_resource_boundary(m,Path(sys.argv[1]),ops,d)\n"
        "limit=m['runtime_limits']['max_peak_rss_bytes']\n"
        "assert b.address_space_limit_bytes==2*1024**3==limit\n"
        "assert ops.get_address_space_limit()==(limit,limit)\n"
        "try:\n"
        " bytearray(limit+1)\n"
        "except MemoryError:\n"
        " raise SystemExit(0)\n"
        "raise SystemExit(9)\n"
    )
    environment = {
        **os.environ,
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
    }
    completed = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        check=False,
        capture_output=True,
        text=True,
        timeout=45,
        env=environment,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux openat/fsync")
def test_native_linux_secure_evidence_syscalls_refuse_identity_attacks(
    tmp_path: Path,
) -> None:
    ops = calibration._NativeLinuxOps()
    deadline = calibration._Deadline(time.monotonic(), 30.0, time.monotonic)
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "linked").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ManifestError, match="directory"):
        calibration._open_or_create_evidence_directory(tmp_path, Path("linked/run"), ops, deadline)

    store = calibration._open_or_create_evidence_directory(
        tmp_path, Path("evidence/run"), ops, deadline
    )
    claim = calibration._write_immutable_claim(store, "calibration.claim", b"{}\n")
    result = calibration._reserve_result_file(store, "calibration-result.json")
    try:
        claim_path = store.path / claim.name
        assert claim_path.read_bytes() == b"{}\n"
        assert (os.stat(claim_path).st_mode & 0o777) == 0o600
        hardlink = store.path / "claim-hardlink"
        os.link(claim_path, hardlink)
        with pytest.raises(ManifestError, match="hard link"):
            calibration._check_evidence_file(store, claim.name, claim.fd)
        hardlink.unlink()

        result_path = store.path / result.name
        replaced = store.path / "replaced-result"
        os.replace(result_path, replaced)
        result_path.write_bytes(b"replacement\n")
        with pytest.raises(ManifestError, match="identity"):
            calibration._check_evidence_file(store, result.name, result.fd)
    finally:
        ops.close(result.fd)
        ops.close(claim.fd)
        for handle in reversed(store.handles):
            ops.close(handle.fd)


class _ControllerOps(_EvidenceOps):
    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.limit: tuple[int, int] | None = None

    def native_environment_evidence(self) -> dict[str, Any]:
        return {"osrelease": "6.8.0", "pid1": "systemd", "container": False}

    def read_mountinfo(self) -> bytes:
        return _ext4_mountinfo(self.fds.get(10, next(iter(self.nodes))))

    def set_address_space_limit(self, soft: int, hard: int) -> None:
        self.limit = (soft, hard)

    def get_address_space_limit(self) -> tuple[int, int]:
        assert self.limit is not None
        return self.limit

    def current_vms_bytes(self) -> int:
        return 128 * 1024 * 1024

    def current_rss_bytes(self) -> int:
        return 96 * 1024 * 1024

    def peak_rss_bytes(self) -> int:
        return 64 * 1024 * 1024

    def utc_now(self) -> str:
        return "2026-09-27T01:02:03.000000Z"


def test_linux_phase_start_binds_claim_result_and_context_without_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)

    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    context.require_active("calibration")
    claim_path = context.store.path / "calibration.claim"
    result_path = context.store.path / context.paths.result_name
    assert claim_path in ops.nodes
    assert result_path in ops.nodes
    assert context.store.path / "calibration.seal" not in ops.nodes
    assert context.claim_file.fd in ops.fds
    assert context.result_file.fd in ops.fds
    claim = calibration._parse_canonical_json_bytes(
        bytes(ops.nodes[claim_path]["data"]), label="claim"
    )
    assert claim["attempt_id"] == f"{context.review.reviewed_commit}-calibration"
    assert claim["artifact_paths"]["seal"].endswith("/calibration.seal")


def test_phase_context_rejects_wrong_phase_and_use_after_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    with pytest.raises(ManifestError, match="wrong phase"):
        context.require_active("validation")
    context.close()
    with pytest.raises(ManifestError, match="closed"):
        context.require_active("calibration")


def test_validation_context_is_refused_before_resource_or_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)

    with pytest.raises(ManifestError, match="verified calibration trio"):
        calibration._begin_linux_phase(
            "validation",
            manifest,
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )

    assert ops.limit is None
    assert not any(node["kind"] == "file" for node in ops.nodes.values())


def test_result_collision_after_claim_leaves_claim_reserved_and_no_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    attestation = calibration._parse_review_attestation(manifest, raw)
    manifest_sha = hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    evidence = repo / f"docs/reviews/step6a2/{manifest_sha}"
    result_name = f"calibration-{attestation.reviewed_commit}-calibration.json"
    ops.nodes[evidence] = {"kind": "dir", "dev": 1, "ino": 90, "nlink": 1, "data": bytearray()}
    ops.nodes[evidence / result_name] = {
        "kind": "file",
        "dev": 1,
        "ino": 91,
        "nlink": 1,
        "data": bytearray(b"reserved"),
    }

    with pytest.raises(ManifestError, match="already exists"):
        calibration._begin_linux_phase(
            "calibration",
            manifest,
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )

    assert evidence / "calibration.claim" not in ops.nodes
    assert evidence / "calibration.seal" not in ops.nodes


def test_post_claim_result_open_failure_keeps_claim_and_never_creates_seal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    original = ops.open_exclusive_file
    opens = 0

    def fail_second_open(directory_fd: int, name: str, mode: int) -> int:
        nonlocal opens
        opens += 1
        if opens == 2:
            raise OSError("injected result open failure")
        return original(directory_fd, name, mode)

    ops.open_exclusive_file = fail_second_open  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="open"):
        calibration._begin_linux_phase(
            "calibration",
            manifest,
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )

    evidence = next(
        path
        for path in ops.nodes
        if str(path).endswith("step6a2") is False
        and path.name == hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    )
    assert evidence / "calibration.claim" in ops.nodes
    assert evidence / "calibration.seal" not in ops.nodes


def test_git_proof_binds_the_exact_tracked_attestation_bytes(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    payload = json.loads(raw)
    payload["reviewer"]["model"] = "substituted-model"
    substituted = calibration._parse_review_attestation(
        manifest, calibration._canonical_bytes(payload)
    )

    with pytest.raises(ManifestError, match="attestation bytes"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            substituted,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_proof_rejects_staged_new_file(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    (repo / "staged.py").write_text("unreviewed = True\n", encoding="utf-8")
    _run_git(repo, "add", "staged.py")

    with pytest.raises(ManifestError, match="index"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            calibration._parse_review_attestation(manifest, raw),
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_proof_rejects_nonancestor_reviewed_commit(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    payload = json.loads(raw)
    tree = _run_git(repo, "rev-parse", "HEAD^{tree}")
    created = subprocess.run(
        ["git", "commit-tree", tree, "-m", "unrelated root"],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    payload["reviewed_commit"] = created
    payload["reviewed_tree"] = tree
    attestation_path = next(repo.glob("docs/reviews/step6a2/*/task3.review.json"))
    attestation_path.write_bytes(calibration._canonical_bytes(payload))
    _commit_all(repo, "record unrelated attestation")
    parsed = calibration._parse_review_attestation(manifest, attestation_path.read_bytes())

    with pytest.raises(ManifestError, match="ancestor"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            parsed,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_git_proof_rejects_merge_between_review_and_invocation(tmp_path: Path) -> None:
    repo, manifest, raw = _reviewed_repo(tmp_path)
    main = _run_git(repo, "branch", "--show-current")
    reviewed = json.loads(raw)["reviewed_commit"]
    _run_git(repo, "branch", "review-side", reviewed)
    _run_git(repo, "switch", "review-side")
    _run_git(repo, "commit", "--allow-empty", "-m", "empty side review")
    _run_git(repo, "switch", main)
    _run_git(repo, "merge", "--no-ff", "review-side", "-m", "merge review history")

    with pytest.raises(ManifestError, match="merge"):
        calibration._verify_reviewed_git_state(
            repo,
            manifest,
            calibration._parse_review_attestation(manifest, raw),
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
            allowed_untracked=("AGENTS.md",),
        )


def test_resource_controller_refuses_planned_allocation_and_verifier_projection(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))
    controller = calibration._prepare_linux_resource_boundary(
        manifest,
        tmp_path,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    remaining = controller.address_space_limit_bytes - ops.current_vms_bytes()

    controller.check_planned_allocation(remaining)
    with pytest.raises(ManifestError, match="planned allocation"):
        controller.check_planned_allocation(remaining + 1)

    result_size = 1024
    assert controller.check_verifier_projection(result_size) == (
        ops.current_vms_bytes() + 32 * result_size + 64 * 1024**2
    )


def test_resource_controller_refuses_result_write_before_projected_budget(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))
    controller = calibration._prepare_linux_resource_boundary(
        manifest,
        tmp_path,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    maximum = controller.maximum_result_bytes()

    controller.check_result_write(maximum)
    with pytest.raises(ManifestError, match=r"result.*budget"):
        controller.check_result_write(maximum + 1)


def test_resource_controller_rechecks_peak_rss(tmp_path: Path) -> None:
    manifest = _manifest()
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))
    controller = calibration._prepare_linux_resource_boundary(
        manifest,
        tmp_path,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    ops.peak_rss_bytes = lambda: manifest["runtime_limits"]["max_peak_rss_bytes"] + 1  # type: ignore[method-assign]

    with pytest.raises(ManifestError, match="peak RSS"):
        controller.sample_peak_rss()


def test_resource_controller_rechecks_deadline(tmp_path: Path) -> None:
    now = [0.0]
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))
    controller = calibration._prepare_linux_resource_boundary(
        _manifest(),
        tmp_path,
        ops,
        calibration._Deadline(0.0, 1.0, lambda: now[0]),
    )
    now[0] = 2.0

    with pytest.raises(ManifestError, match="deadline"):
        controller.sample_peak_rss()


def test_phase_context_wrong_phase_permanently_closes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    with pytest.raises(ManifestError, match="wrong phase"):
        context.require_active("validation")

    assert context.closed is True
    with pytest.raises(ManifestError, match="closed"):
        context.require_active("calibration")


def test_phase_context_compares_identity_to_original_bound_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    for file in (context.claim_file, context.result_file):
        path = context.store.path / file.name
        ops.nodes[path]["ino"] += 100
        ops.fds[file.fd] = path

    with pytest.raises(ManifestError, match="identity"):
        context.require_active("calibration")

    assert context.closed is True


def test_phase_context_rejects_unissued_direct_construction() -> None:
    fields = {
        field.name: None
        for field in dataclasses.fields(calibration._PhaseContext)
        if field.name != "closed"
    }
    with pytest.raises(ManifestError, match="issued"):
        calibration._PhaseContext(**fields)  # type: ignore[arg-type]


def test_evidence_root_fstat_failure_closes_unregistered_fd(tmp_path: Path) -> None:
    ops = _EvidenceOps(tmp_path)
    original = ops.fstat

    def fail_root(fd: int) -> Any:
        if ops.fds[fd] == tmp_path:
            raise OSError("injected root fstat failure")
        return original(fd)

    ops.fstat = fail_root  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="directory"):
        calibration._open_or_create_evidence_directory(
            tmp_path,
            Path("docs/reviews/step6a2/abc"),
            ops,
            calibration._Deadline(0.0, 60.0, lambda: 1.0),
        )
    assert ops.fds == {}


def test_claim_close_error_after_release_never_retries_reused_writer_fd(
    tmp_path: Path,
) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    original_open = ops.open_exclusive_file
    original_close = ops.close
    writer_fd: int | None = None
    closes = 0
    sentinel = tmp_path / "sentinel"
    ops.nodes[sentinel] = {
        "kind": "file",
        "dev": 1,
        "ino": 99_999,
        "nlink": 1,
        "data": bytearray(),
    }

    def track_writer(directory_fd: int, name: str, mode: int) -> int:
        nonlocal writer_fd
        writer_fd = original_open(directory_fd, name, mode)
        return writer_fd

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal closes
        if fd == writer_fd:
            closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("claim close reported failure after release")
        original_close(fd)

    ops.open_exclusive_file = track_writer  # type: ignore[method-assign]
    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="close"):
        calibration._write_immutable_claim(store, "calibration.claim", b"claim\n")

    assert writer_fd is not None
    assert closes == 1
    assert ops.fds[writer_fd] == sentinel


def test_claim_directory_fsync_failure_does_not_double_close_writer(tmp_path: Path) -> None:
    store, ops = _fake_evidence_store(tmp_path)
    original_fsync = ops.fsync
    count = 0

    def fail_directory_fsync(fd: int) -> None:
        nonlocal count
        count += 1
        if count == 2:
            raise OSError("injected directory fsync failure")
        original_fsync(fd)

    ops.fsync = fail_directory_fsync  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="fsync"):
        calibration._write_immutable_claim(store, "calibration.claim", b"claim\n")

    assert store.path / "calibration.claim" in ops.nodes


def test_resource_controller_checks_current_rss_plus_planned_allocation(
    tmp_path: Path,
) -> None:
    manifest = _manifest()
    ops = _ResourceOps(_ext4_mountinfo(tmp_path))
    limit = manifest["runtime_limits"]["max_peak_rss_bytes"]
    ops.current_rss_bytes = lambda: limit - 10  # type: ignore[method-assign]
    controller = calibration._prepare_linux_resource_boundary(
        manifest,
        tmp_path,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    with pytest.raises(ManifestError, match="current RSS"):
        controller.check_planned_allocation(11)


def test_resource_policy_limit_and_deadline_are_immutable(tmp_path: Path) -> None:
    controller = calibration._prepare_linux_resource_boundary(
        _manifest(),
        tmp_path,
        _ResourceOps(_ext4_mountinfo(tmp_path)),
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )

    limit_attribute = "address_space_limit_bytes"
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        setattr(controller, limit_attribute, 1)
    deadline_attribute = "deadline"
    with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
        setattr(
            controller,
            deadline_attribute,
            calibration._Deadline(0.0, 999.0, lambda: 1.0),
        )


def test_phase_context_phase_and_binding_are_immutable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    phase_attribute = "phase"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(context, phase_attribute, "validation")
    identity_attribute = "bound_identity_bytes"
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(context, identity_attribute, b"forged")
    context.require_active("calibration")
    assert context.closed is False


@pytest.mark.parametrize("mutation", ["proof", "review", "claim"])
def test_phase_context_mutated_bound_evidence_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    if mutation == "proof":
        context.proof.protected_blobs["scripts/signal_calibration.py"] = "0" * 64
    elif mutation == "review":
        context.review.protected_blobs["scripts/signal_calibration.py"] = "1" * 64
    else:
        claim_path = context.store.path / context.claim_file.name
        ops.nodes[claim_path]["data"].extend(b"tamper")

    with pytest.raises(
        ManifestError,
        match=r"binding|claim bytes|claim grew beyond its frozen size",
    ):
        context.require_active("calibration")
    assert context.closed is True


@pytest.fixture(autouse=True)
def _forbid_accidental_reserved_rng(monkeypatch: pytest.MonkeyPatch) -> None:
    original = np.random.SeedSequence

    def guarded(seed: Any = None, *args: Any, **kwargs: Any) -> Any:
        if seed in calibration._RESERVED_PHASE_SEEDS:
            pytest.fail("reserved RNG constructed outside an explicit provider spy")
        return original(seed, *args, **kwargs)

    monkeypatch.setattr(np.random, "SeedSequence", guarded)


class _ProviderResources:
    def __init__(self, fail: str | None = None) -> None:
        self.fail = fail
        self.planned: list[int] = []
        self.samples = 0
        self.active_calls: list[str] = []
        self.active_call_count = 0

    def check_planned_allocation(self, planned_bytes: int) -> None:
        self.planned.append(planned_bytes)
        if self.fail == "allocation":
            raise ManifestError("planned allocation refused")

    def sample_peak_rss(self) -> int:
        self.samples += 1
        if self.fail == "rss":
            raise ManifestError("peak RSS refused")
        return 1


def _provider_context(
    monkeypatch: pytest.MonkeyPatch,
    manifest: dict[str, Any],
    *,
    phase: str = "calibration",
    resources: _ProviderResources | None = None,
    active_failure: str | None = None,
) -> calibration._PhaseContext:
    context = object.__new__(calibration._PhaseContext)
    manifest_raw = calibration._canonical_bytes(manifest)
    manifest_sha = hashlib.sha256(manifest_raw).hexdigest()
    manifest_path = manifest["integrity"]["protected_paths"]["manifest"]
    object.__setattr__(context, "phase", phase)
    object.__setattr__(context, "issuer", calibration._PHASE_CONTEXT_ISSUER)
    object.__setattr__(context, "provider_issued", False)
    actual_resources = resources or _ProviderResources()
    object.__setattr__(context, "resources", actual_resources)
    object.__setattr__(
        context, "proof", SimpleNamespace(protected_blobs={manifest_path: manifest_sha})
    )
    object.__setattr__(
        context, "review", SimpleNamespace(protected_blobs={manifest_path: manifest_sha})
    )
    object.__setattr__(
        context,
        "claim_bytes",
        calibration._canonical_bytes(
            {
                "manifest_sha256": manifest_sha,
                "phase": phase,
                "protocol_version": calibration.PROTOCOL_VERSION,
            }
        ),
    )
    object.__setattr__(context, "closed", False)

    def require_active(self: calibration._PhaseContext, requested: str) -> None:
        actual_resources.active_call_count += 1
        if len(actual_resources.active_calls) < 100:
            actual_resources.active_calls.append(requested)
        if self.closed:
            raise ManifestError("phase context is closed")
        if active_failure is not None:
            object.__setattr__(self, "closed", True)
            raise ManifestError(active_failure)
        if requested != self.phase:
            object.__setattr__(self, "closed", True)
            raise ManifestError("phase context has the wrong phase")

    def close(self: calibration._PhaseContext) -> None:
        object.__setattr__(self, "closed", True)

    monkeypatch.setattr(calibration._PhaseContext, "require_active", require_active)
    monkeypatch.setattr(calibration._PhaseContext, "close", close)
    return context


class _ScriptedCountedGenerator:
    def __init__(self, address: tuple[int, int, int, int], calls: list[tuple[Any, ...]]) -> None:
        self.address = address
        self.calls = calls

    def standard_normal(self, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
        self.calls.append((*self.address, "normal", shape))
        return np.zeros(shape, dtype=np.float64)

    def uniform(self, low: float, high: float, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
        self.calls.append((*self.address, "uniform", low, high, shape))
        return np.full(shape, 0.75, dtype=np.float64)


def test_counted_provider_uses_authenticated_reserved_addresses_and_chunk_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)
    constructions: list[tuple[int, int, int, int]] = []
    draws: list[tuple[Any, ...]] = []

    def seed_sequence(seed: int, *, spawn_key: tuple[int, int, int]) -> Any:
        address = (seed, *spawn_key)
        constructions.append(address)
        return address

    monkeypatch.setattr(np.random, "SeedSequence", seed_sequence)
    monkeypatch.setattr(np.random, "PCG64", lambda address: address)
    monkeypatch.setattr(
        np.random,
        "Generator",
        lambda address: _ScriptedCountedGenerator(address, draws),
    )
    provider = calibration._CountedChunkProvider(context, manifest)
    chunk = next(provider)

    assert (
        chunk.cell_id,
        chunk.chunk_id,
        chunk.replicate_start,
        chunk.replicate_stop_exclusive,
    ) == (
        1,
        0,
        0,
        256,
    )
    assert len(chunk.replicates) == 256
    assert constructions == [
        (2026092602, 1, 0, 0),
        (2026092602, 1, 2, 0),
        (2026092602, 1, 3, 0),
    ]
    assert [call[-1] for call in draws] == [(256, 192), (256, 192), (256, 24)]
    assert provider._component_cache == {}
    active_calls = cast(Any, context.resources).active_calls
    assert active_calls[0] == "calibration"
    assert cast(Any, context.resources).active_call_count > len(draws)


def test_counted_provider_preserves_dynamic_grouping_through_shared_core() -> None:
    manifest = _manifest()

    def draw(_component: int, _replicate: int, size: int, _rows: int) -> np.ndarray[Any, Any]:
        return np.zeros(size, dtype=np.float64)

    replicate = calibration._generate_replicate_core(
        manifest,
        phase="calibration",
        cell_id=44,
        replicate_id=0,
        draw_normal=draw,
        draw_uniform=lambda _component, _replicate, size, _rows: np.full(
            size, 0.75, dtype=np.float64
        ),
        scripted_wins=np.array([True, False] * 96),
    )

    assert replicate.block_length == 126
    assert set(replicate.holding_sessions) == {21, 42}
    assert len(set(replicate.block_ids)) == 24


def test_counted_provider_topology_reaches_declared_remainder_without_rng(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)
    seen_count = 0
    endpoints: list[tuple[int, int, int]] = []

    def lightweight(
        _manifest: Any,
        *,
        phase: str,
        cell_id: int,
        replicate_id: int,
        draw_normal: Any,
        draw_uniform: Any,
        **_scripted: Any,
    ) -> calibration.SyntheticReplicate:
        nonlocal seen_count
        del _manifest, phase, draw_uniform, _scripted
        provider = cast(Any, draw_normal).__self__
        provider._active_component_index = len(provider._active_components)
        address = (cell_id, replicate_id // 256, replicate_id)
        if seen_count == 0 or (cell_id == 45 and replicate_id == 9_999):
            endpoints.append(address)
        seen_count += 1
        return calibration.SyntheticReplicate((), (), (), 63, (), (), (), ())

    monkeypatch.setattr(calibration, "_generate_replicate_core", lightweight)
    provider = calibration._CountedChunkProvider(context, manifest)
    topology: list[tuple[int, int, int]] = []
    while True:
        try:
            chunk = next(provider)
        except StopIteration:
            break
        topology.append((chunk.cell_id, chunk.chunk_id, len(chunk.replicates)))

    assert len(topology) == 45 * 40
    assert topology[:2] == [(1, 0, 256), (1, 1, 256)]
    assert topology[-2:] == [(45, 38, 256), (45, 39, 16)]
    assert endpoints == [(1, 0, 0), (45, 39, 9_999)]
    assert seen_count == 45 * 10_000
    assert provider._component_cache == {}
    assert context.closed is False


@pytest.mark.parametrize("failure", ["allocation", "rss", "deadline"])
def test_counted_provider_resource_failure_clears_cache_and_closes_context(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    manifest = _manifest()
    resources = _ProviderResources(fail=None if failure == "deadline" else failure)
    context = _provider_context(
        monkeypatch,
        manifest,
        resources=resources,
        active_failure="counted phase deadline expired" if failure == "deadline" else None,
    )
    monkeypatch.setattr(
        np.random,
        "SeedSequence",
        lambda seed, *, spawn_key: (seed, *spawn_key),
    )
    monkeypatch.setattr(np.random, "PCG64", lambda address: address)
    monkeypatch.setattr(
        np.random,
        "Generator",
        lambda address: _ScriptedCountedGenerator(address, []),
    )
    if failure == "deadline":
        with pytest.raises(ManifestError, match="deadline"):
            calibration._CountedChunkProvider(context, manifest)
    else:
        provider = calibration._CountedChunkProvider(context, manifest)
        with pytest.raises(ManifestError):
            next(provider)
        assert provider._component_cache == {}

    assert context.closed is True


def test_counted_provider_refuses_unissued_closed_wrong_phase_and_tampered_manifest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    unissued = object.__new__(calibration._PhaseContext)
    object.__setattr__(unissued, "issuer", object())
    with pytest.raises(ManifestError, match="issued"):
        calibration._CountedChunkProvider(unissued, manifest)

    closed = _provider_context(monkeypatch, manifest)
    object.__setattr__(closed, "closed", True)
    with pytest.raises(ManifestError, match="closed"):
        calibration._CountedChunkProvider(closed, manifest)

    wrong = _provider_context(monkeypatch, manifest, phase="wrong")
    with pytest.raises(ManifestError, match="phase"):
        calibration._CountedChunkProvider(wrong, manifest)
    assert wrong.closed is True

    tampered_context = _provider_context(monkeypatch, manifest)
    tampered = json.loads(json.dumps(manifest))
    tampered["phases"]["calibration"]["master_seed"] = 7
    with pytest.raises(ManifestError, match=r"seed|manifest"):
        calibration._CountedChunkProvider(tampered_context, tampered)
    assert tampered_context.closed is True


def test_counted_provider_uses_local_manifest_snapshot_and_row_copies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)
    arrays: list[np.ndarray[Any, Any]] = []

    class MutableGenerator(_ScriptedCountedGenerator):
        def standard_normal(self, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            array = np.zeros(shape, dtype=np.float64)
            arrays.append(array)
            return array

        def uniform(self, low: float, high: float, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            del low, high
            array = np.full(shape, 0.75, dtype=np.float64)
            arrays.append(array)
            return array

    monkeypatch.setattr(
        np.random,
        "SeedSequence",
        lambda seed, *, spawn_key: (seed, *spawn_key),
    )
    monkeypatch.setattr(np.random, "PCG64", lambda address: address)
    monkeypatch.setattr(
        np.random,
        "Generator",
        lambda address: MutableGenerator(address, []),
    )
    provider = calibration._CountedChunkProvider(context, manifest)
    manifest["phases"]["calibration"]["cells"][0]["parameters"]["p"] = 0.99
    chunk = next(provider)

    assert chunk.replicates[0].wins == chunk.replicates[1].wins
    assert all(np.all(array == (0.75 if index == 1 else 0.0)) for index, array in enumerate(arrays))
    assert provider._manifest_bytes != calibration._canonical_bytes(manifest)


def test_counted_context_issues_only_one_provider_even_after_exhaustion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    active_context = _provider_context(monkeypatch, manifest)
    calibration._CountedChunkProvider(active_context, manifest)
    with pytest.raises(ManifestError, match="already issued"):
        calibration._CountedChunkProvider(active_context, manifest)
    assert active_context.closed is True

    exhausted_context = _provider_context(monkeypatch, manifest)
    provider = calibration._CountedChunkProvider(exhausted_context, manifest)
    provider._cell_index = len(manifest["phases"]["calibration"]["cells"])
    with pytest.raises(StopIteration):
        next(provider)
    assert exhausted_context.closed is False
    with pytest.raises(ManifestError, match="already issued"):
        calibration._CountedChunkProvider(exhausted_context, manifest)
    assert exhausted_context.closed is True


def test_counted_provider_direct_draw_and_unexpected_stop_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    direct_context = _provider_context(monkeypatch, manifest)
    direct = calibration._CountedChunkProvider(direct_context, manifest)
    with pytest.raises(ManifestError, match="outside active generation"):
        direct._draw_normal(0, 0, 192, 256)
    assert direct_context.closed is True

    stopped_context = _provider_context(monkeypatch, manifest)
    stopped = calibration._CountedChunkProvider(stopped_context, manifest)

    def stop_early(*_args: Any, **_kwargs: Any) -> calibration.SyntheticReplicate:
        raise StopIteration

    monkeypatch.setattr(calibration, "_generate_replicate_core", stop_early)
    with pytest.raises(ManifestError, match="stopped before completing"):
        next(stopped)
    assert stopped_context.closed is True
    assert stopped._cell_index == 0
    with pytest.raises(ManifestError, match="permanently closed"):
        next(stopped)


@pytest.mark.parametrize("wrong_size", [191, 193])
def test_counted_provider_rejects_component_size_before_rng(
    monkeypatch: pytest.MonkeyPatch, wrong_size: int
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)

    def wrong_core(
        _manifest: Any,
        *,
        phase: str,
        cell_id: int,
        replicate_id: int,
        draw_normal: Any,
        draw_uniform: Any,
        **_scripted: Any,
    ) -> calibration.SyntheticReplicate:
        del _manifest, phase, cell_id, draw_uniform, _scripted
        draw_normal(0, replicate_id, wrong_size, 256)
        pytest.fail("wrong component size reached the equation body")

    monkeypatch.setattr(calibration, "_generate_replicate_core", wrong_core)
    provider = calibration._CountedChunkProvider(context, manifest)
    with pytest.raises(ManifestError, match="address or order"):
        next(provider)
    assert context.closed is True


@pytest.mark.parametrize(
    ("cell_id", "chunk_id"),
    [(1, 39), (7, 0), (12, 0), (18, 0), (24, 0), (30, 0), (33, 0), (41, 0), (44, 0)],
)
def test_counted_provider_all_family_traces_match_safe_fixture_stream(
    monkeypatch: pytest.MonkeyPatch, cell_id: int, chunk_id: int
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)
    safe_seed_sequence = np.random.SeedSequence
    real_generator = np.random.Generator
    requested_addresses: list[tuple[int, int, int, int]] = []
    draw_trace: list[tuple[str, tuple[int, int]]] = []

    def substitute_seed(seed: int, *, spawn_key: tuple[int, int, int]) -> Any:
        if seed in calibration._RESERVED_PHASE_SEEDS:
            requested_addresses.append((seed, *spawn_key))
            seed = calibration._TEST_FIXTURE_SEED
        return safe_seed_sequence(seed, spawn_key=spawn_key)

    class RecordingGenerator:
        def __init__(self, bit_generator: Any) -> None:
            self._generator = real_generator(bit_generator)

        def standard_normal(self, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            draw_trace.append(("normal", shape))
            return self._generator.standard_normal(shape)

        def uniform(self, low: float, high: float, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            draw_trace.append(("uniform", shape))
            return self._generator.uniform(low, high, shape)

    monkeypatch.setattr(np.random, "SeedSequence", substitute_seed)
    monkeypatch.setattr(np.random, "Generator", RecordingGenerator)
    provider = calibration._CountedChunkProvider(context, manifest)
    provider._cell_index = cell_id - 1
    provider._chunk_id = chunk_id
    chunk = next(provider)
    rows = 16 if chunk_id == 39 else 256
    cell = manifest["phases"]["calibration"]["cells"][cell_id - 1]
    shapes = calibration._counted_component_shapes(manifest, cell)

    assert requested_addresses == [
        (2026092602, cell_id, component_id, chunk_id)
        for _distribution, component_id, _size in shapes
    ]
    assert draw_trace == [
        (distribution, (rows, size)) for distribution, _component_id, size in shapes
    ]
    for offset in (0, rows - 1):
        replicate_id = chunk_id * 256 + offset
        assert chunk.replicates[offset] == calibration.generate_test_fixture_replicate(
            manifest,
            phase="calibration",
            cell_id=cell_id,
            replicate_id=replicate_id,
        )
    assert provider._component_cache == {}


def test_counted_provider_row_copy_cannot_mutate_cached_component(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    context = _provider_context(monkeypatch, manifest)
    source_arrays: list[np.ndarray[Any, Any]] = []

    class SourceGenerator(_ScriptedCountedGenerator):
        def standard_normal(self, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            array = np.zeros(shape, dtype=np.float64)
            source_arrays.append(array)
            return array

        def uniform(self, low: float, high: float, shape: tuple[int, int]) -> np.ndarray[Any, Any]:
            del low, high
            array = np.full(shape, 0.75, dtype=np.float64)
            source_arrays.append(array)
            return array

    def mutate_rows(
        _manifest: Any,
        *,
        phase: str,
        cell_id: int,
        replicate_id: int,
        draw_normal: Any,
        draw_uniform: Any,
        **_scripted: Any,
    ) -> calibration.SyntheticReplicate:
        del _manifest, phase, cell_id, _scripted
        normal = draw_normal(0, replicate_id, 192, 256)
        amplitude = draw_uniform(2, replicate_id, 192, 256)
        benchmark = draw_normal(3, replicate_id, 24, 256)
        normal[0] = 99.0
        amplitude[0] = 99.0
        benchmark[0] = 99.0
        return calibration.SyntheticReplicate((), (), (), 63, (), (), (), ())

    monkeypatch.setattr(calibration, "_generate_replicate_core", mutate_rows)
    monkeypatch.setattr(
        np.random,
        "SeedSequence",
        lambda seed, *, spawn_key: (seed, *spawn_key),
    )
    monkeypatch.setattr(np.random, "PCG64", lambda address: address)
    monkeypatch.setattr(
        np.random,
        "Generator",
        lambda address: SourceGenerator(address, []),
    )
    provider = calibration._CountedChunkProvider(context, manifest)
    next(provider)

    assert np.all(source_arrays[0] == 0.0)
    assert np.all(source_arrays[1] == 0.75)
    assert np.all(source_arrays[2] == 0.0)


def _scripted_metric_replicate(
    values: tuple[float, ...],
    *,
    wins: tuple[bool, ...] | None = None,
    excess: tuple[float, ...] | None = None,
    blocks: tuple[int, ...] = (0, 0, 1, 1),
) -> calibration.SyntheticReplicate:
    count = len(values)
    return calibration.SyntheticReplicate(
        entry_indices=tuple(range(count)),
        holding_sessions=(21,) * count,
        block_ids=blocks,
        block_length=63,
        wins=wins if wins is not None else tuple(value > 0.0 for value in values),
        raw=values,
        benchmark=(0.0,) * count,
        excess=excess if excess is not None else values,
    )


def _scripted_metric_chunk(
    overrides: dict[int, calibration.SyntheticReplicate] | None = None,
) -> calibration._CountedChunk:
    ordinary = _scripted_metric_replicate((-1.0, -0.5, 0.5, 1.0))
    replicates = [ordinary] * 256
    for replicate_id, replicate in (overrides or {}).items():
        replicates[replicate_id] = replicate
    return calibration._CountedChunk(1, 0, 0, 256, tuple(replicates))


def test_full_batch_moments_match_public_and_scalar_with_uncapped_effective_n() -> None:
    values = np.array([0.0, 0.02, 0.01, -0.01, 0.03, 0.04])
    blocks = np.array([0, 0, 1, 2, 2, 2], dtype=np.int64)
    full = calibration._evaluate_full_batch(values, blocks, confidence=0.90)
    public = calibration.evaluate_batch_interval(values, blocks, confidence=0.90)
    scalar = _cr2_moments(
        tuple(float(value) for value in values), tuple(int(block) for block in blocks)
    )

    assert isinstance(full, calibration._FullBatchMoments)
    assert isinstance(public, calibration.BatchInterval)
    assert full.mean == public.mean
    assert full.cr2_variance == public.variance
    assert full.nu == public.degrees_of_freedom
    assert full.raw_lower == public.raw_lower
    assert full.raw_upper == public.raw_upper
    assert full.sample_variance == pytest.approx(7 / 20_000)
    assert full.cr2_variance == pytest.approx(7 / 400_000)
    assert full.effective_n == pytest.approx(20.0)
    assert full.effective_n > len(values)
    assert isinstance(scalar, CandidateMoments)
    assert full.effective_n == pytest.approx(scalar.effective_n_uncapped)


def test_full_batch_retains_finite_input_nonfinite_intermediate_failure() -> None:
    result = calibration._evaluate_full_batch(
        np.array([1e308, -1e308, 1e308, -1e308]),
        np.array([0, 0, 1, 1], dtype=np.int64),
        confidence=0.95,
    )

    assert isinstance(result, calibration._BatchFailure)
    assert result.reason is calibration.BatchRefusal.INVALID_VARIANCE
    assert result.non_finite_intermediate is True


def test_metric_adapter_keeps_sibling_metrics_independent_and_refusals_ordered() -> None:
    manifest = _manifest()
    replicate = _scripted_metric_replicate(
        (-1.0, -0.5, 0.5, 1.0),
        wins=(True, True, True, True),
        excess=(-2.0, -1.0, 1.0, 2.0),
    )
    chunk = _scripted_metric_chunk({index: replicate for index in range(256)})

    raw = calibration._build_metric_events(manifest, "calibration", "raw", chunk)
    win = calibration._build_metric_events(manifest, "calibration", "win", chunk)
    excess = calibration._build_metric_events(manifest, "calibration", "synthetic_excess", chunk)

    assert raw["emitted_ids"] == list(range(256))
    assert excess["emitted_ids"] == list(range(256))
    assert win["emitted_ids"] == []
    assert win["refusals"] == [{"reason": "ZERO_VARIANCE", "ids": list(range(256))}]
    assert win["coverage_ids"] == win["lower_miss_ids"] == win["upper_miss_ids"] == []
    assert win["joint_success_ids"] == win["coverage_ids"]
    assert all(
        refusal["reason"] not in {"BELOW_CALIBRATED_BLOCKS", "BELOW_CALIBRATED_DF"}
        for events in (raw, win, excess)
        for refusal in events["refusals"]
    )


def test_metric_adapter_emits_fixed_and_non_audit_combined_triggers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    near = _scripted_metric_replicate((1.0, 1.0 + 1e-7, 1.0 - 1e-7, 1.0))
    zero = _scripted_metric_replicate(
        (1.0, 1.0, 1.0, 1.0),
        wins=(True, True, True, True),
    )
    chunk = _scripted_metric_chunk({0: near, 1: zero, 2: near})
    scalar_calls = 0
    original = _cr2_moments

    def counted_scalar(values: tuple[float, ...], blocks: tuple[int, ...]) -> Any:
        nonlocal scalar_calls
        scalar_calls += 1
        return original(values, blocks)

    monkeypatch.setattr(calibration, "_scalar_cr2_moments", counted_scalar)
    events = calibration._build_metric_events(manifest, "calibration", "raw", chunk)
    parity = {record["replicate_id"]: record for record in events["parity"]}

    assert parity[0]["triggers"] == ["near_zero", "ordinary"]
    assert parity[1]["triggers"] == ["zero"]
    assert parity[2]["triggers"] == ["near_zero"]
    assert scalar_calls == len(events["parity"])
    assert 1 not in events["emitted_ids"]
    assert events["refusals"][0]["reason"] == "ZERO_VARIANCE"


def test_metric_adapter_detects_exact_t_critical_boundary() -> None:
    manifest = _manifest()
    cell = manifest["phases"]["calibration"]["cells"][0]
    target = float(cell["targets"]["raw_mean"])
    base_values = np.array([-1.0, -1.0, 1.0, 1.0])
    blocks = np.array([0, 0, 1, 1], dtype=np.int64)
    base = calibration._evaluate_full_batch(base_values, blocks, confidence=0.95)
    assert isinstance(base, calibration._FullBatchMoments)
    shift = target + float(t.ppf(0.975, base.nu)) * math.sqrt(base.cr2_variance) - base.mean
    boundary = _scripted_metric_replicate(tuple(float(value + shift) for value in base_values))
    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk({2: boundary})
    )
    record = next(item for item in events["parity"] if item["replicate_id"] == 2)

    assert record["triggers"] == ["t_critical"]


def test_metric_adapter_cr1_matches_unequal_occupancy_hand_formula() -> None:
    manifest = _manifest()
    values = (0.0, 0.02, 0.01, -0.01, 0.03, 0.04)
    replicate = _scripted_metric_replicate(values, blocks=(0, 0, 1, 2, 2, 2))
    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk({0: replicate})
    )
    record = events["parity"][0]

    assert record["cr1"]["mean"] == pytest.approx(3 / 200)
    assert record["cr1"]["sample_variance"] == pytest.approx(7 / 20_000)
    assert record["cr1"]["cr1_variance"] == pytest.approx(7 / 480_000)
    assert record["cr1"]["effective_n"] == pytest.approx(24.0)
    assert record["cr1"]["effective_n"] > len(values)


def test_metric_adapter_cr1_refusal_is_report_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    monkeypatch.setattr(
        calibration,
        "_serialize_cr1_result",
        lambda *_args: calibration._null_parity_result("INVALID_VARIANCE", "cr1_variance"),
    )

    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk()
    )

    assert events["emitted_ids"] == list(range(256))
    assert events["parity"][0]["batch"]["status"] == "EMITTED"
    assert events["parity"][0]["cr1"]["status"] == "INVALID_VARIANCE"


def test_cr1_can_emit_when_cr2_has_its_own_df_refusal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    special = _scripted_metric_replicate((-2.0, -1.0, 1.0, 2.0))
    original_batch = calibration._evaluate_full_batch
    original_scalar = _cr2_moments

    def refused_batch(values: Any, blocks: Any, *, confidence: float) -> Any:
        if float(values[0]) == -2.0:
            return calibration._BatchFailure(calibration.BatchRefusal.INVALID_DF)
        return original_batch(values, blocks, confidence=confidence)

    def refused_scalar(values: tuple[float, ...], blocks: tuple[int, ...]) -> Any:
        if values[0] == -2.0:
            return MetricRefusal.INVALID_DF
        return original_scalar(values, blocks)

    monkeypatch.setattr(calibration, "_evaluate_full_batch", refused_batch)
    monkeypatch.setattr(calibration, "_scalar_cr2_moments", refused_scalar)
    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk({0: special})
    )
    record = events["parity"][0]

    assert record["batch"]["status"] == "INVALID_DF"
    assert record["scalar"]["status"] == "INVALID_DF"
    assert record["cr1"]["status"] == "EMITTED"


def test_full_batch_finite_underflow_is_not_labeled_nonfinite() -> None:
    result = calibration._evaluate_full_batch(
        np.array([0.0, 5e-324, 0.0, 5e-324]),
        np.array([0, 0, 1, 1], dtype=np.int64),
        confidence=0.95,
    )

    assert result == calibration._BatchFailure(
        calibration.BatchRefusal.INVALID_VARIANCE,
        non_finite_intermediate=False,
    )


def test_metric_adapter_retains_nonfinite_intermediate_and_halts_nonfinite_input() -> None:
    manifest = _manifest()
    overflow = _scripted_metric_replicate((1e308, -1e308, 1e308, -1e308))
    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk({1: overflow})
    )
    record = next(item for item in events["parity"] if item["replicate_id"] == 1)

    assert record["triggers"] == ["non_finite"]
    assert record["batch"]["status"] == "INVALID_VARIANCE"

    nonfinite = _scripted_metric_replicate((math.inf, -1.0, 0.5, 1.0))
    with pytest.raises(ManifestError, match="metric input"):
        calibration._build_metric_events(
            manifest, "calibration", "raw", _scripted_metric_chunk({1: nonfinite})
        )


def test_metric_adapter_does_not_hide_wrong_scalar_refusal_on_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = _scripted_metric_replicate((), blocks=())
    original = _cr2_moments

    def wrong_only_for_empty(
        values: tuple[float, ...], blocks: tuple[int, ...]
    ) -> CandidateMoments | MetricRefusal:
        if not values:
            return MetricRefusal.ZERO_VARIANCE
        return original(values, blocks)

    monkeypatch.setattr(calibration, "_scalar_cr2_moments", wrong_only_for_empty)

    with pytest.raises(ManifestError, match="parity"):
        calibration._build_metric_events(
            _manifest(), "calibration", "raw", _scripted_metric_chunk({0: empty})
        )


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda chunk: dataclasses.replace(chunk, chunk_id=cast(Any, False)),
            "strict integers",
        ),
        (
            lambda chunk: dataclasses.replace(
                chunk,
                replicates=(
                    dataclasses.replace(
                        chunk.replicates[0],
                        block_ids=cast(Any, (0.0, 0.0, 1.0, 1.0)),
                    ),
                    *chunk.replicates[1:],
                ),
            ),
            "block IDs",
        ),
        (
            lambda chunk: dataclasses.replace(
                chunk,
                replicates=(
                    dataclasses.replace(
                        chunk.replicates[0],
                        wins=cast(Any, (1, 0, 1, 0)),
                    ),
                    *chunk.replicates[1:],
                ),
            ),
            "wins",
        ),
    ],
)
def test_metric_adapter_refuses_noncanonical_integer_and_boolean_types(
    mutate: Any, message: str
) -> None:
    with pytest.raises(ManifestError, match=message):
        calibration._build_metric_events(
            _manifest(), "calibration", "raw", mutate(_scripted_metric_chunk())
        )


@pytest.mark.parametrize(
    ("metric", "field", "values"),
    [
        ("raw", "raw", ("1.0", -0.5, 0.5, 1.0)),
        ("raw", "raw", (True, -0.5, 0.5, 1.0)),
        ("synthetic_excess", "excess", ("1.0", -0.5, 0.5, 1.0)),
        ("synthetic_excess", "excess", (True, -0.5, 0.5, 1.0)),
    ],
)
def test_metric_adapter_refuses_coercible_nonfloat_metric_values(
    metric: str, field: str, values: tuple[Any, ...]
) -> None:
    chunk = _scripted_metric_chunk()
    replicate = dataclasses.replace(chunk.replicates[0], **{field: cast(Any, values)})
    malformed = dataclasses.replace(chunk, replicates=(replicate, *chunk.replicates[1:]))

    with pytest.raises(ManifestError, match="exact floats"):
        calibration._build_metric_events(_manifest(), "calibration", metric, malformed)


def test_metric_adapter_near_zero_uses_verifier_exact_boundary_formula(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    cell = manifest["phases"]["calibration"]["cells"][0]
    target = float(cell["targets"]["raw_mean"])
    special = _scripted_metric_replicate((1.5, -1.5, 0.5, -0.5))
    verifier_threshold = 1e-12 * 1.5**2
    chained_threshold = math.nextafter(verifier_threshold, math.inf)
    assert chained_threshold == 1e-12 * 1.5 * 1.5
    original = calibration._evaluate_full_batch

    def boundary_batch(values: Any, blocks: Any, *, confidence: float) -> Any:
        if float(values[0]) == 1.5:
            return calibration._FullBatchMoments(
                mean=target,
                sample_variance=1.0,
                cr2_variance=chained_threshold,
                nu=2.0,
                design_effect=chained_threshold * 4.0,
                effective_n=1.0 / chained_threshold,
                raw_lower=target - 1e-5,
                raw_upper=target + 1e-5,
            )
        return original(values, blocks, confidence=confidence)

    monkeypatch.setattr(calibration, "_evaluate_full_batch", boundary_batch)
    events = calibration._build_metric_events(
        manifest, "calibration", "raw", _scripted_metric_chunk({1: special})
    )

    assert all(record["replicate_id"] != 1 for record in events["parity"])


@pytest.mark.parametrize(
    ("chunk", "metric", "message"),
    [
        (
            calibration._CountedChunk(999, 0, 0, 256, _scripted_metric_chunk().replicates),
            "raw",
            "cell",
        ),
        (
            calibration._CountedChunk(1, 1, 0, 256, _scripted_metric_chunk().replicates),
            "raw",
            "range",
        ),
        (_scripted_metric_chunk(), "foreign", "metric"),
    ],
)
def test_metric_adapter_refuses_foreign_chunk_identity_or_metric(
    chunk: calibration._CountedChunk, metric: str, message: str
) -> None:
    with pytest.raises(ManifestError, match=message):
        calibration._build_metric_events(_manifest(), "calibration", metric, chunk)


def test_metric_adapter_invokes_internal_validators_before_return(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = _manifest()
    calls: list[str] = []
    partition = calibration._validate_metric_event_partition
    parity = calibration._verify_parity

    def checked_partition(*args: Any, **kwargs: Any) -> Any:
        calls.append("partition")
        return partition(*args, **kwargs)

    def checked_parity(*args: Any, **kwargs: Any) -> Any:
        calls.append("parity")
        return parity(*args, **kwargs)

    monkeypatch.setattr(calibration, "_validate_metric_event_partition", checked_partition)
    monkeypatch.setattr(calibration, "_verify_parity", checked_parity)
    calibration._build_metric_events(manifest, "calibration", "raw", _scripted_metric_chunk())

    assert calls == ["partition", "parity"]


class _ScriptedChunkProvider:
    chunks: ClassVar[list[dict[str, Any]]] = []
    fail_after: int | None = None

    def __init__(self, context: Any, manifest: dict[str, Any]) -> None:
        self.context = context
        self.index = 0

    def __iter__(self) -> _ScriptedChunkProvider:
        return self

    def __next__(self) -> calibration._CountedChunk:
        if self.fail_after is not None and self.index == self.fail_after:
            self.context.close()
            raise ManifestError("injected provider failure")
        if self.index >= len(self.chunks):
            raise StopIteration
        item = self.chunks[self.index]
        self.index += 1
        rows = item["replicate_stop_exclusive"] - item["replicate_start"]
        return calibration._CountedChunk(
            item["cell_id"],
            item["chunk_id"],
            item["replicate_start"],
            item["replicate_stop_exclusive"],
            cast(Any, (None,) * rows),
        )


def _writer_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete_result: dict[str, Any],
) -> tuple[dict[str, Any], calibration._PhaseContext, _ControllerOps]:
    repo, manifest, _ = _reviewed_repo(tmp_path)
    ops = _ControllerOps(repo)
    ops.short_write = 10_000_000
    monkeypatch.setattr(calibration, "_ROOT", repo)
    context = calibration._begin_linux_phase(
        "calibration",
        manifest,
        ops,
        calibration._Deadline(0.0, 60.0, lambda: 1.0),
    )
    _ScriptedChunkProvider.chunks = list(complete_result["chunks"])
    _ScriptedChunkProvider.fail_after = None
    by_key = {
        (chunk["cell_id"], chunk["chunk_id"], event["metric"]): event
        for chunk in complete_result["chunks"]
        for event in chunk["metrics"]
    }

    def scripted_events(
        _manifest: dict[str, Any],
        _phase: str,
        metric: str,
        chunk: calibration._CountedChunk,
    ) -> dict[str, Any]:
        return cast(dict[str, Any], by_key[(chunk.cell_id, chunk.chunk_id, metric)])

    monkeypatch.setattr(calibration, "_CountedChunkProvider", _ScriptedChunkProvider)
    monkeypatch.setattr(calibration, "_build_metric_events", scripted_events)
    return manifest, context, ops


def _independent_writer_expected(
    context: calibration._PhaseContext,
    manifest: dict[str, Any],
    chunks: list[dict[str, Any]],
) -> calibration._ExpectedPhaseContext:
    phase = context.phase
    phase_data = manifest["phases"][phase]
    by_cell = {cell["id"]: cell for cell in phase_data["cells"]}
    planned = calibration._WRITER_CHUNK_ALLOCATION_BYTES
    for index, chunk in enumerate(chunks):
        rows = chunk["replicate_stop_exclusive"] - chunk["replicate_start"]
        provider = calibration._counted_chunk_memory_bound(
            manifest, by_cell[chunk["cell_id"]], rows
        )
        encoded = (b"" if index == 0 else b",") + calibration._json_fragment(chunk)
        planned = max(
            planned,
            provider + calibration._WRITER_CHUNK_ALLOCATION_BYTES + len(encoded) * 4,
        )
    planned = max(planned, calibration._WRITER_SUMMARY_ALLOCATION_BYTES)
    provenance = {
        "manifest_sha256": hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest(),
        "method_version": manifest["method_version"],
        "selection_artifact_schema": manifest["selection_artifact_schema"],
        "reviewed_commit": context.review.reviewed_commit,
        "invocation_commit": context.proof.invocation_commit,
        "protected_blobs": dict(context.proof.protected_blobs),
        "review_attestation_sha256": context.review.raw_sha256,
        "claim_sha256": context.claim_sha256,
        "dependencies": manifest["versions"],
    }
    attempt = {
        "attempt_id": f"{context.review.reviewed_commit}-{phase}",
        "started_at_utc": context.started_at_utc,
    }
    limit = context.resources.address_space_limit_bytes
    runtime = {
        "platform": "linux",
        "resource_backend": "linux-rlimit-as",
        "address_space_limit_bytes": limit,
        "peak_rss_before_verification_bytes": 64 * 1024 * 1024,
        "peak_rss_source": "getrusage-ru_maxrss-kib",
        "planned_peak_bytes": planned,
        "maximum_result_bytes": (limit - 128 * 1024 * 1024 - 64 * 1024**2) // 32,
        "generation_elapsed_seconds": 1.0,
        "deadline_seconds": 7_200,
        "resource_state": "WITHIN_LIMIT",
    }
    return calibration._ExpectedPhaseContext(
        phase,
        calibration._canonical_bytes(provenance),
        calibration._canonical_bytes(attempt),
        calibration._canonical_bytes(runtime),
        None,
    )


def _prepared_verification_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    complete_result: dict[str, Any],
    *,
    stored_result: dict[str, Any] | None = None,
) -> tuple[
    dict[str, Any],
    calibration._PhaseContext,
    _ControllerOps,
    calibration._ExpectedPhaseContext,
]:
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete_result)
    expected = _independent_writer_expected(context, manifest, complete_result["chunks"])
    prepared = json.loads(json.dumps(complete_result if stored_result is None else stored_result))
    prepared["provenance"] = calibration._parse_canonical_json_bytes(
        expected.provenance_bytes, label="prepared provenance"
    )
    prepared["attempt"] = calibration._parse_canonical_json_bytes(
        expected.attempt_bytes, label="prepared attempt"
    )
    prepared["runtime"] = calibration._parse_canonical_json_bytes(
        expected.runtime_bytes, label="prepared runtime"
    )
    prepared["terminal"]["ended_at_utc"] = context.started_at_utc
    raw = calibration._canonical_bytes(prepared)
    result_path = context.store.path / context.paths.result_name
    ops.nodes[result_path]["data"] = bytearray(raw)
    calibration._handoff_result_reader(context)
    calibration._bind_writer_expected(context, expected)
    return manifest, context, ops, expected


def _stub_completion_verifier(
    monkeypatch: pytest.MonkeyPatch,
    context: calibration._PhaseContext,
    *,
    verdict: str = "PASSED",
) -> list[int]:
    result_path = context.store.path / context.paths.result_name
    raw = bytes(context.store.ops.nodes[result_path]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="stub result")
    selected = parsed["summary"]["selected_floor"]
    floor = (
        (selected["minimum_blocks"], float(selected["minimum_nu"]))
        if selected is not None and verdict == "PASSED"
        else None
    )
    calls: list[int] = []

    def verify(
        supplied: calibration._PhaseContext, _manifest: dict[str, Any]
    ) -> calibration._VerifiedPhaseEvidence:
        assert supplied is context
        calls.append(1)
        expected_binding = context.writer_expected_binding_bytes
        assert isinstance(expected_binding, bytes)
        return calibration._VerifiedPhaseEvidence(
            context.phase,
            verdict,
            floor,
            hashlib.sha256(raw).hexdigest(),
            len(raw),
            256 * 1024 * 1024,
            64 * 1024 * 1024,
            0.25,
            context.bound_identity_bytes,
            expected_binding,
        )

    monkeypatch.setattr(calibration, "_verify_finished_phase_result", verify)
    return calls


def test_phase_writer_streams_canonical_complete_result_and_hands_off_reader(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    expected_result, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, expected_result)
    writer_fd = context.result_file.fd
    independent = _independent_writer_expected(context, manifest, expected_result["chunks"])
    prior_calls = len(ops.calls)

    returned = calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="written result")
    assert returned == independent
    verified = calibration.validate_phase_result(manifest, parsed, independent)
    assert verified.phase_verdict == "PASSED"
    assert parsed["chunks"] == expected_result["chunks"]
    assert parsed["summary"] == expected_result["summary"]
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert context.closed is False
    assert context.writing_finished is True
    assert writer_fd not in ops.fds
    assert context.result_file.fd in ops.fds
    result_path = context.store.path / context.paths.result_name
    fsyncs = [call[1] for call in ops.calls[prior_calls:] if call[0] == "fsync"]
    assert fsyncs.count(result_path) == len(expected_result["chunks"]) + 2
    assert fsyncs.count(context.store.path) == len(expected_result["chunks"]) + 2
    assert context.store.path / context.paths.seal_name not in ops.nodes
    context.require_active("calibration")
    retained_fds = dict(ops.fds)

    evidence = calibration._verify_finished_phase_result(context, manifest)

    assert evidence.phase == "calibration"
    assert evidence.phase_verdict == "PASSED"
    assert evidence.selected_floor == verified.selected_floor
    assert evidence.result_sha256 == hashlib.sha256(raw).hexdigest()
    assert evidence.result_size_bytes == len(raw)
    assert evidence.verification_projected_bytes > len(raw)
    assert evidence.final_peak_rss_bytes == 64 * 1024 * 1024
    assert evidence.verification_elapsed_seconds == 0.0
    assert evidence.context_binding_bytes == context.bound_identity_bytes
    assert dict(ops.fds) == retained_fds
    assert context.closed is False
    assert context.store.path / context.paths.seal_name not in ops.nodes
    with pytest.raises(ManifestError, match="already finished"):
        calibration._write_phase_result(context, manifest)
    assert context.closed is True


def test_phase_writer_complete_statistical_failure_remains_unverified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    source, _ = full_calibration
    failed = json.loads(json.dumps(source))
    critical = float(t.ppf(0.975, 10.0))
    for chunk in failed["chunks"]:
        raw = chunk["metrics"][0]
        raw["coverage_ids"] = []
        raw["lower_miss_ids"] = list(raw["emitted_ids"])
        raw["joint_success_ids"] = []
        for record in raw["parity"]:
            record["max_abs_outcome"] = 1_000_000.0
            for comparator in ("batch", "scalar", "cr1"):
                result = record[comparator]
                result["mean"] = 1_000_000.0
                variance_name = "cr1_variance" if comparator == "cr1" else "cr2_variance"
                result[variance_name] = 100.0
                result["sample_variance"] = 100.0
                result["raw_lower"] = 1_000_000.0 - critical * 10.0
                result["raw_upper"] = 1_000_000.0 + critical * 10.0
                result["coverage"] = False
                result["lower_miss"] = True
                result["upper_miss"] = False
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, failed)

    expected = calibration._write_phase_result(context, manifest)
    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="failed complete result")

    assert parsed["terminal"]["state"] == "UNVERIFIED"
    assert parsed["summary"]["phase_verdict"] == "FAILED"
    assert calibration.validate_phase_result(manifest, parsed, expected).phase_verdict == "FAILED"
    completion = calibration._complete_phase(context, manifest)
    assert completion.phase_verdict == "FAILED"
    assert completion.selected_floor is None
    assert calibration._require_phase_completion(context, completion) is completion
    candidate_path = context.store.path / context.paths.seal_name
    candidate = calibration._parse_canonical_json_bytes(
        bytes(ops.nodes[candidate_path]["data"]), label="failed candidate"
    )
    assert candidate["phase_verdict"] == "FAILED"
    assert candidate["authority"] == "NONE"
    assert context.closed is False
    context.close()


@pytest.mark.parametrize("state", ["unfinalized", "missing_binding"])
def test_finished_verifier_refuses_unfinalized_or_unbound_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    state: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, _ = _writer_fixture(tmp_path, monkeypatch, complete)
    if state == "missing_binding":
        calibration._handoff_result_reader(context)

    with pytest.raises(ManifestError, match=r"finished phase|writer-bound"):
        calibration._verify_finished_phase_result(context, manifest)

    assert context.closed is True


def test_finished_verifier_rejects_forged_matching_result_and_expected_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, expected = _prepared_verification_fixture(
        tmp_path, monkeypatch, complete
    )
    forged = json.loads(json.dumps(complete))
    forged["runtime"]["resource_state"] = "FORGED"
    result_path = context.store.path / context.paths.result_name
    ops.nodes[result_path]["data"] = bytearray(calibration._canonical_bytes(forged))
    object.__setattr__(
        context,
        "writer_expected",
        dataclasses.replace(
            expected,
            runtime_bytes=calibration._canonical_bytes(forged["runtime"]),
        ),
    )

    with pytest.raises(ManifestError, match="authentication"):
        calibration._verify_finished_phase_result(context, manifest)

    assert context.closed is True


@pytest.mark.parametrize("mutation", ["malformed", "incomplete", "event"])
def test_finished_verifier_refuses_invalid_saved_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    stored = json.loads(json.dumps(complete))
    if mutation == "incomplete":
        stored["summary"] = {
            "candidate_results": [],
            "cells": [],
            "parity_complete": False,
            "phase_verdict": "INCOMPLETE",
            "selected_floor": None,
        }
        stored["terminal"]["state"] = "INCOMPLETE"
        stored["terminal"]["failure"] = {
            "kind": "ManifestError",
            "message": "stopped",
            "cell_id": 0,
            "chunk_id": 0,
            "replicate_ids": [],
        }
    elif mutation == "event":
        stored["chunks"][0]["metrics"][0]["coverage_ids"].append(10_000)
    manifest, context, ops, _ = _prepared_verification_fixture(
        tmp_path, monkeypatch, complete, stored_result=stored
    )
    if mutation == "malformed":
        result_path = context.store.path / context.paths.result_name
        ops.nodes[result_path]["data"] = bytearray(b'{"bad":}\n')

    with pytest.raises(ManifestError):
        calibration._verify_finished_phase_result(context, manifest)

    assert context.closed is True
    assert context.store.path / context.paths.seal_name not in ops.nodes


def test_finished_verifier_checks_projection_before_result_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    result_path = context.store.path / context.paths.result_name
    prior_calls = len(ops.calls)
    monkeypatch.setattr(
        calibration._ResourceBoundary,
        "check_verifier_projection",
        lambda _self, _size: (_ for _ in ()).throw(ManifestError("projection refused")),
    )

    with pytest.raises(ManifestError, match="projection refused"):
        calibration._verify_finished_phase_result(context, manifest)

    result_reads = [
        call for call in ops.calls[prior_calls:] if call[0] == "pread" and call[1] == result_path
    ]
    assert result_reads == []
    assert context.closed is True


@pytest.mark.parametrize("mutation", ["grow", "shrink"])
def test_finished_verifier_reads_only_frozen_result_extent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    result_path = context.store.path / context.paths.result_name
    original_pread = ops.pread
    mutated = False

    def mutate_before_first_result_read(fd: int, size: int, offset: int) -> bytes:
        nonlocal mutated
        if not mutated and ops.fds[fd] == result_path:
            mutated = True
            if mutation == "grow":
                ops.nodes[result_path]["data"].extend(b"x")
            else:
                del ops.nodes[result_path]["data"][-1]
        return original_pread(fd, size, offset)

    ops.pread = mutate_before_first_result_read  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match=r"grew|ended|extent"):
        calibration._verify_finished_phase_result(context, manifest)

    assert mutated is True
    assert context.closed is True


@pytest.mark.parametrize("mutation", ["content", "identity"])
def test_finished_verifier_detects_post_recomputation_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    result_path = context.store.path / context.paths.result_name
    original_validate = calibration.validate_phase_result

    def mutate_after_validate(*args: Any, **kwargs: Any) -> Any:
        verified = original_validate(*args, **kwargs)
        if mutation == "content":
            ops.nodes[result_path]["data"][10] ^= 1
        else:
            ops.nodes[result_path]["ino"] += 1
        return verified

    monkeypatch.setattr(calibration, "validate_phase_result", mutate_after_validate)
    with pytest.raises(ManifestError, match=r"changed|identity"):
        calibration._verify_finished_phase_result(context, manifest)

    assert context.closed is True


def test_finished_verifier_bounds_claim_reread_before_result_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    claim_path = context.store.path / context.paths.claim_name
    result_path = context.store.path / context.paths.result_name
    original_claim_size = len(context.claim_bytes)
    ops.nodes[claim_path]["data"].extend(b"x" * (2 * 1024**2))
    prior_calls = len(ops.calls)

    with pytest.raises(ManifestError, match="claim grew"):
        calibration._verify_finished_phase_result(context, manifest)

    new_reads = [call for call in ops.calls[prior_calls:] if call[0] == "pread"]
    claim_reads = [call for call in new_reads if call[1] == claim_path]
    assert claim_reads
    assert max(call[2] for call in claim_reads) <= max(original_claim_size, 1)
    assert all(call[1] != result_path for call in new_reads)
    assert context.closed is True


def test_finished_verifier_deadline_covers_each_bounded_result_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    result_path = context.store.path / context.paths.result_name
    expired = False

    def clock() -> float:
        return 61.0 if expired else 1.0

    deadline = calibration._Deadline(0.0, 60.0, clock)
    object.__setattr__(context.resources.policy, "deadline", deadline)
    context.store.deadline = deadline
    original_pread = ops.pread

    def expire_after_first_result_read(fd: int, size: int, offset: int) -> bytes:
        nonlocal expired
        chunk = original_pread(fd, size, offset)
        if ops.fds[fd] == result_path:
            expired = True
        return chunk

    ops.pread = expire_after_first_result_read  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="deadline"):
        calibration._verify_finished_phase_result(context, manifest)

    assert context.closed is True


def test_finished_verifier_rechecks_deadline_after_reader_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    expired = False

    def clock() -> float:
        return 61.0 if expired else 1.0

    deadline = calibration._Deadline(0.0, 60.0, clock)
    object.__setattr__(context.resources.policy, "deadline", deadline)
    context.store.deadline = deadline
    original_open = ops.open_existing_file
    original_close = ops.close
    verification_reader: int | None = None

    def track_reader(directory_fd: int, name: str) -> int:
        nonlocal verification_reader
        verification_reader = original_open(directory_fd, name)
        return verification_reader

    def expire_after_reader_close(fd: int) -> None:
        nonlocal expired
        original_close(fd)
        if fd == verification_reader:
            expired = True

    ops.open_existing_file = track_reader  # type: ignore[method-assign]
    ops.close = expire_after_reader_close  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="deadline"):
        calibration._verify_finished_phase_result(context, manifest)

    assert verification_reader is not None
    assert verification_reader not in ops.fds
    assert context.closed is True


def test_finished_verifier_never_retries_reader_close_after_fd_reuse(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    original_open = ops.open_existing_file
    original_close = ops.close
    verification_reader: int | None = None
    reader_closes = 0
    sentinel = tmp_path / "verification-close-sentinel"
    ops.nodes[sentinel] = {
        "kind": "file",
        "dev": 1,
        "ino": 199_999,
        "nlink": 1,
        "data": bytearray(),
    }

    def track_reader(directory_fd: int, name: str) -> int:
        nonlocal verification_reader
        verification_reader = original_open(directory_fd, name)
        return verification_reader

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal reader_closes
        if fd == verification_reader:
            reader_closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("verification close reported failure after release")
        original_close(fd)

    ops.open_existing_file = track_reader  # type: ignore[method-assign]
    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="reader close"):
        calibration._verify_finished_phase_result(context, manifest)

    assert verification_reader is not None
    assert reader_closes == 1
    assert ops.fds[verification_reader] == sentinel
    assert context.closed is True


def test_complete_phase_writes_inert_candidate_then_issues_process_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    independently_verified = calibration._verify_finished_phase_result(context, manifest)
    prior_calls = len(ops.calls)

    completion = calibration._complete_phase(context, manifest)

    candidate_path = context.store.path / context.paths.seal_name
    raw = bytes(ops.nodes[candidate_path]["data"])
    candidate = calibration._parse_canonical_json_bytes(raw, label="completion candidate")
    assert set(candidate) == {
        "attempt_id",
        "authority",
        "claim_path",
        "claim_sha256",
        "invocation_commit",
        "manifest_sha256",
        "phase",
        "phase_verdict",
        "prewrite_snapshot",
        "protocol_version",
        "result_path",
        "result_sha256",
        "result_size_bytes",
        "review_attestation_sha256",
        "reviewed_commit",
        "schema",
        "verifier",
    }
    paths = context.paths.as_claim_record()
    harness_path = manifest["integrity"]["protected_paths"]["harness"]
    expected_candidate = {
        "attempt_id": f"{context.review.reviewed_commit}-{context.phase}",
        "authority": "NONE",
        "claim_path": paths["claim"],
        "claim_sha256": context.claim_sha256,
        "invocation_commit": context.proof.invocation_commit,
        "manifest_sha256": hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest(),
        "phase": context.phase,
        "phase_verdict": "PASSED",
        "prewrite_snapshot": {
            "captured_at_utc": "2026-09-27T01:02:03.000000Z",
            "peak_rss_bytes": 64 * 1024 * 1024,
            "resource_verdict": "WITHIN_LIMIT",
            "total_elapsed_seconds": 1.0,
            "verification_elapsed_seconds": independently_verified.verification_elapsed_seconds,
            "verification_projected_bytes": independently_verified.verification_projected_bytes,
        },
        "protocol_version": calibration.PROTOCOL_VERSION,
        "result_path": paths["result"],
        "result_sha256": independently_verified.result_sha256,
        "result_size_bytes": independently_verified.result_size_bytes,
        "review_attestation_sha256": context.review.raw_sha256,
        "reviewed_commit": context.review.reviewed_commit,
        "schema": "step6a2-completion-candidate-v2",
        "verifier": {
            "harness_sha256": context.proof.protected_blobs[harness_path],
            "schema": "step6a2-result-verifier-v1",
        },
    }
    assert candidate == expected_candidate
    assert independently_verified.selected_floor is not None
    expected_capability_payload = {
        "attempt_id": expected_candidate["attempt_id"],
        "candidate": {
            "device": 1,
            "inode": ops.nodes[candidate_path]["ino"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        },
        "claim": {
            "device": context.claim_file.device,
            "inode": context.claim_file.inode,
            "sha256": context.claim_sha256,
        },
        "completed_at_utc": "2026-09-27T01:02:03.000000Z",
        "completed_peak_rss_bytes": 64 * 1024 * 1024,
        "completed_total_elapsed_seconds": 1.0,
        "context_binding_sha256": hashlib.sha256(context.bound_identity_bytes).hexdigest(),
        "manifest_sha256": expected_candidate["manifest_sha256"],
        "phase": context.phase,
        "phase_verdict": "PASSED",
        "pid": context.original_pid,
        "result": {
            "device": context.result_file.device,
            "inode": context.result_file.inode,
            "sha256": independently_verified.result_sha256,
            "size_bytes": independently_verified.result_size_bytes,
        },
        "selected_floor": list(independently_verified.selected_floor),
        "writer_expected_binding_sha256": hashlib.sha256(
            context.writer_expected_binding_bytes or b""
        ).hexdigest(),
    }
    assert completion.payload_binding_bytes == calibration._canonical_bytes(
        expected_capability_payload
    )
    assert candidate["schema"] == "step6a2-completion-candidate-v2"
    assert candidate["authority"] == "NONE"
    assert candidate["phase_verdict"] == "PASSED"
    assert (
        candidate["result_sha256"]
        == hashlib.sha256(
            bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
        ).hexdigest()
    )
    assert raw.endswith(b"\n") and raw.count(b"\n") == 1
    assert calibration._require_phase_completion(context, completion) is completion
    assert context.closed is False
    calls = ops.calls[prior_calls:]
    assert calls.index(("fsync", candidate_path)) < calls.index(("fsync", context.store.path))
    prior_require = len(ops.calls)
    expired = calibration._Deadline(0.0, 60.0, lambda: 61.0)
    object.__setattr__(context.resources.policy, "deadline", expired)
    context.store.deadline = expired
    assert calibration._require_phase_completion(context, completion) is completion
    assert len(ops.calls) == prior_require
    context.close()
    with pytest.raises(ManifestError, match="closed"):
        calibration._require_phase_completion(context, completion)


def test_complete_phase_refuses_short_candidate_write_and_closes_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    calls = _stub_completion_verifier(monkeypatch, context)
    ops.short_write = 7

    with pytest.raises(ManifestError, match="exact"):
        calibration._complete_phase(context, manifest)

    candidate = context.store.path / context.paths.seal_name
    assert calls == [1]
    assert len(ops.nodes[candidate]["data"]) == 7
    assert context.completion is None
    assert context.closed is True


def test_phase_completion_is_exact_object_bound_to_current_context_values(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, _, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)

    copied = dataclasses.replace(completion)
    with pytest.raises(ManifestError, match="issued"):
        calibration._require_phase_completion(context, copied)
    context.proof.protected_blobs["scripts/signal_calibration.py"] = "0" * 64
    with pytest.raises(ManifestError, match="binding"):
        calibration._require_phase_completion(context, completion)


def test_complete_phase_detects_same_size_candidate_edit_during_result_rehash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    original = calibration._rehash_exact_evidence
    changed = False

    def mutate_after_rehash(*args: Any, **kwargs: Any) -> str:
        nonlocal changed
        digest = original(*args, **kwargs)
        if kwargs.get("label") == "completed result":
            candidate = context.store.path / context.paths.seal_name
            ops.nodes[candidate]["data"][0] ^= 1
            changed = True
        return digest

    monkeypatch.setattr(calibration, "_rehash_exact_evidence", mutate_after_rehash)
    with pytest.raises(ManifestError, match="candidate bytes changed"):
        calibration._complete_phase(context, manifest)

    assert changed is True
    assert context.closed is True
    assert context.completion is None


def test_complete_phase_final_deadline_check_follows_payload_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    expired = False
    deadline = context.resources.deadline
    object.__setattr__(deadline, "clock", lambda: 61.0 if expired else 1.0)
    original = calibration._phase_completion_payload

    def expire_during_payload(
        completion: calibration._PhaseCompletion,
    ) -> dict[str, Any]:
        nonlocal expired
        payload = original(completion)
        expired = True
        return payload

    monkeypatch.setattr(calibration, "_phase_completion_payload", expire_during_payload)
    with pytest.raises(ManifestError, match="deadline"):
        calibration._complete_phase(context, manifest)

    assert context.store.path / context.paths.seal_name in ops.nodes
    assert context.completion is None
    assert context.closed is True


@pytest.mark.parametrize("sync_target", ["file", "directory"])
def test_complete_phase_sync_failure_leaves_inert_candidate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    sync_target: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    original = ops.fsync
    candidate = context.store.path / context.paths.seal_name
    reached = False

    def fail_selected(fd: int) -> None:
        nonlocal reached
        path = ops.fds[fd]
        if path == (candidate if sync_target == "file" else context.store.path):
            reached = True
            raise OSError(f"injected candidate {sync_target} sync failure")
        original(fd)

    ops.fsync = fail_selected  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="I/O failed"):
        calibration._complete_phase(context, manifest)

    assert reached is True
    assert bytes(ops.nodes[candidate]["data"]).endswith(b"\n")
    assert context.completion is None
    assert context.closed is True


def test_complete_phase_repeated_attempt_invalidates_first_authority_without_rewrite(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    calls = _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    candidate = context.store.path / context.paths.seal_name
    raw = bytes(ops.nodes[candidate]["data"])

    with pytest.raises(ManifestError, match="already attempted"):
        calibration._complete_phase(context, manifest)

    assert calls == [1]
    assert bytes(ops.nodes[candidate]["data"]) == raw
    assert context.closed is True
    with pytest.raises(ManifestError, match="closed"):
        calibration._require_phase_completion(context, completion)


def test_complete_phase_writer_release_error_does_not_close_reused_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    original_open = ops.open_exclusive_file
    original_close = ops.close
    writer_fd: int | None = None
    closes = 0
    sentinel = tmp_path / "completion-sentinel"
    ops.nodes[sentinel] = {
        "kind": "file",
        "dev": 1,
        "ino": 88_888,
        "nlink": 1,
        "data": bytearray(),
    }

    def track_candidate(directory_fd: int, name: str, mode: int) -> int:
        nonlocal writer_fd
        fd = original_open(directory_fd, name, mode)
        if name == context.paths.seal_name:
            writer_fd = fd
        return fd

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal closes
        if fd == writer_fd:
            closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("candidate close reported failure after release")
        original_close(fd)

    ops.open_exclusive_file = track_candidate  # type: ignore[method-assign]
    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="close"):
        calibration._complete_phase(context, manifest)

    assert writer_fd is not None
    assert closes == 1
    assert ops.fds[writer_fd] == sentinel
    assert context.completion is None
    assert context.closed is True


def test_complete_phase_existing_candidate_is_never_modified(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    candidate = context.store.path / context.paths.seal_name
    ops.nodes[candidate] = {
        "kind": "file",
        "dev": 1,
        "ino": 77_777,
        "nlink": 1,
        "data": bytearray(b"existing\n"),
    }

    with pytest.raises(ManifestError, match="already exists"):
        calibration._complete_phase(context, manifest)

    assert bytes(ops.nodes[candidate]["data"]) == b"existing\n"
    assert context.completion is None
    assert context.closed is True


def test_complete_phase_fresh_verification_rejects_postverification_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    calibration._verify_finished_phase_result(context, manifest)
    result_path = context.store.path / context.paths.result_name
    ops.nodes[result_path]["data"][0] ^= 1

    with pytest.raises(ManifestError):
        calibration._complete_phase(context, manifest)

    assert context.store.path / context.paths.seal_name not in ops.nodes
    assert context.completion is None
    assert context.closed is True


def test_complete_phase_refuses_pid_change_before_candidate_reservation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    calls = _stub_completion_verifier(monkeypatch, context)
    monkeypatch.setattr(os, "getpid", lambda: context.original_pid + 1)

    with pytest.raises(ManifestError, match="PID"):
        calibration._complete_phase(context, manifest)

    assert calls == []
    assert context.store.path / context.paths.seal_name not in ops.nodes
    assert context.closed is True


@pytest.mark.parametrize(("refusal_call", "candidate_exists"), [(1, False), (2, True)])
def test_complete_phase_resource_refusal_preallocation_and_final_boundary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    refusal_call: int,
    candidate_exists: bool,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    original = context.resources.check_planned_allocation
    calls = 0

    def refuse_selected(planned_bytes: int) -> None:
        nonlocal calls
        calls += 1
        if calls == refusal_call:
            raise ManifestError("injected completion allocation refusal")
        original(planned_bytes)

    monkeypatch.setattr(
        calibration._ResourceBoundary,
        "check_planned_allocation",
        lambda self, planned_bytes: (
            refuse_selected(planned_bytes) if self is context.resources else original(planned_bytes)
        ),
    )
    with pytest.raises(ManifestError, match="allocation refusal"):
        calibration._complete_phase(context, manifest)

    candidate = context.store.path / context.paths.seal_name
    assert (candidate in ops.nodes) is candidate_exists
    assert calls == refusal_call
    assert context.completion is None
    assert context.closed is True


def test_complete_phase_reader_release_error_does_not_close_reused_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    original_open = ops.open_existing_file
    original_close = ops.close
    reader_fd: int | None = None
    closes = 0
    sentinel = tmp_path / "completion-reader-sentinel"
    ops.nodes[sentinel] = {
        "kind": "file",
        "dev": 1,
        "ino": 66_666,
        "nlink": 1,
        "data": bytearray(),
    }

    def track_candidate_reader(directory_fd: int, name: str) -> int:
        nonlocal reader_fd
        fd = original_open(directory_fd, name)
        if name == context.paths.seal_name:
            reader_fd = fd
        return fd

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal closes
        if fd == reader_fd:
            closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("candidate reader close reported failure after release")
        original_close(fd)

    ops.open_existing_file = track_candidate_reader  # type: ignore[method-assign]
    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="close"):
        calibration._complete_phase(context, manifest)

    assert reader_fd is not None
    assert closes == 1
    assert ops.fds[reader_fd] == sentinel
    assert context.completion is None
    assert context.closed is True


@pytest.mark.parametrize("mutation", ["missing", "reordered"])
def test_phase_writer_closes_canonical_incomplete_on_safe_topology_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    independent = _independent_writer_expected(context, manifest, complete["chunks"])
    if mutation == "missing":
        _ScriptedChunkProvider.chunks = []
    else:
        chunks = list(_ScriptedChunkProvider.chunks)
        chunks[0], chunks[1] = chunks[1], chunks[0]
        _ScriptedChunkProvider.chunks = chunks

    with pytest.raises(ManifestError, match=r"topology|order"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="incomplete result")
    assert parsed["chunks"] == []
    assert parsed["summary"] == {
        "candidate_results": [],
        "cells": [],
        "parity_complete": False,
        "phase_verdict": "INCOMPLETE",
        "selected_floor": None,
    }
    assert parsed["terminal"]["state"] == "INCOMPLETE"
    assert context.closed is True
    incomplete_expected = dataclasses.replace(
        independent,
        runtime_bytes=calibration._canonical_bytes(parsed["runtime"]),
    )
    with pytest.raises(ManifestError, match="complete unverified"):
        calibration.validate_phase_result(manifest, parsed, incomplete_expected)


def test_phase_writer_bounds_failure_message_and_preserves_committed_chunks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    original = calibration._build_metric_events
    calls = 0

    def fail_after_first_chunk(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls > 3:
            raise ManifestError("x" * 100_000)
        return original(*args, **kwargs)

    monkeypatch.setattr(calibration, "_build_metric_events", fail_after_first_chunk)
    with pytest.raises(ManifestError, match=r"x+"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="bounded incomplete")
    assert len(parsed["chunks"]) == 1
    assert parsed["chunks"][0] == complete["chunks"][0]
    assert len(parsed["terminal"]["failure"]["message"].encode()) <= 1024
    assert parsed["summary"]["cells"] == []
    assert context.closed is True


def test_phase_writer_incomplete_allocation_refusal_precedes_suffix_build(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    scripted = calibration._build_metric_events
    original_guard = calibration._ResourceBoundary.check_planned_allocation
    calls = 0
    adapter_failed = False

    def fail_during_second_chunk(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal adapter_failed, calls
        calls += 1
        if calls > 3:
            adapter_failed = True
            raise ManifestError("injected adapter failure")
        return scripted(*args, **kwargs)

    def refuse_incomplete_allocation(
        resources: calibration._ResourceBoundary, planned_bytes: int
    ) -> None:
        if adapter_failed:
            raise ManifestError("incomplete allocation refused")
        original_guard(resources, planned_bytes)

    monkeypatch.setattr(calibration, "_build_metric_events", fail_during_second_chunk)
    monkeypatch.setattr(
        calibration._ResourceBoundary,
        "check_planned_allocation",
        refuse_incomplete_allocation,
    )
    monkeypatch.setattr(
        calibration,
        "_result_suffix",
        lambda *_args, **_kwargs: pytest.fail("incomplete suffix built before allocation refusal"),
    )

    with pytest.raises(ManifestError, match="incomplete allocation refused"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    assert raw and b"INCOMPLETE" not in raw
    assert context.closed is True


def test_phase_writer_provider_closed_failure_never_fabricates_incomplete(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    _ScriptedChunkProvider.fail_after = 0

    with pytest.raises(ManifestError, match="provider failure"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    with pytest.raises(ManifestError):
        calibration._parse_canonical_json_bytes(raw, label="provider partial")
    assert b"INCOMPLETE" not in raw
    assert context.closed is True


@pytest.mark.parametrize("operation", ["write", "fsync"])
def test_phase_writer_durability_failure_preserves_partial_bytes_and_closes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    operation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    ops.fail_on = operation

    with pytest.raises(ManifestError, match=operation):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    with pytest.raises(ManifestError):
        calibration._parse_canonical_json_bytes(raw, label="durability partial")
    assert b"INCOMPLETE" not in raw
    assert context.closed is True


def test_phase_writer_directory_fsync_failure_after_committed_chunk_halts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    original = ops.fsync
    prior_calls = len(ops.calls)
    directory_fsyncs = 0

    def fail_third_directory_fsync(fd: int) -> None:
        nonlocal directory_fsyncs
        if ops.fds[fd] == context.store.path:
            directory_fsyncs += 1
            if directory_fsyncs == 3:
                raise OSError("injected directory fsync failure")
        original(fd)

    ops.fsync = fail_third_directory_fsync  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="fsync"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    first_chunk = calibration._json_fragment(complete["chunks"][0])
    assert first_chunk in raw
    assert sum(call == ("fsync", context.store.path) for call in ops.calls[prior_calls:]) == 2
    with pytest.raises(ManifestError):
        calibration._parse_canonical_json_bytes(raw, label="directory-fsync partial")
    assert b"INCOMPLETE" not in raw
    assert context.closed is True


def test_phase_writer_invalid_short_write_preserves_partial_bytes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    original = ops.write
    writes = 0

    def zero_after_prefix(fd: int, data: bytes) -> int:
        nonlocal writes
        writes += 1
        if writes == 2:
            return 0
        ops.short_write = 7
        return original(fd, data)

    ops.write = zero_after_prefix  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="short-write"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    assert raw and b"INCOMPLETE" not in raw
    assert context.closed is True


def test_phase_writer_rejects_same_inode_prepopulation_before_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    result_path = context.store.path / context.paths.result_name
    ops.nodes[result_path]["data"].extend(b"preexisting")
    monkeypatch.setattr(
        _ScriptedChunkProvider,
        "__next__",
        lambda _self: pytest.fail("provider advanced before extent check"),
    )

    with pytest.raises(ManifestError, match="size or write offset"):
        calibration._write_phase_result(context, manifest)

    assert bytes(ops.nodes[result_path]["data"]) == b"preexisting"
    assert context.closed is True


def test_phase_writer_rejects_rewound_writer_before_next_append(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    scripted = calibration._build_metric_events
    calls = 0

    def rewind_after_first(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        if calls == 4:
            ops.offsets[context.result_file.fd] = 0
        return scripted(*args, **kwargs)

    monkeypatch.setattr(calibration, "_build_metric_events", rewind_after_first)
    with pytest.raises(ManifestError, match="write offset"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    assert b"INCOMPLETE" not in raw
    assert context.closed is True


def test_result_handoff_identity_failure_closes_reader_writer_and_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    _, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    original_open = ops.open_existing_file
    original_fstat = ops.fstat
    reader_fd: int | None = None

    def track_reader(directory_fd: int, name: str) -> int:
        nonlocal reader_fd
        reader_fd = original_open(directory_fd, name)
        return reader_fd

    def changed_reader(fd: int) -> Any:
        value = original_fstat(fd)
        if fd == reader_fd:
            return SimpleNamespace(
                st_mode=value.st_mode,
                st_dev=value.st_dev,
                st_ino=value.st_ino + 1,
                st_nlink=value.st_nlink,
                st_size=value.st_size,
            )
        return value

    ops.open_existing_file = track_reader  # type: ignore[method-assign]
    ops.fstat = changed_reader  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="identity"):
        calibration._handoff_result_reader(context)

    assert reader_fd is not None
    assert reader_fd not in ops.fds
    assert context.closed is True
    assert ops.fds == {}


def test_result_handoff_close_error_never_retries_reused_writer_fd(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    _, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    writer_fd = context.result_file.fd
    original = ops.close
    sentinel = tmp_path / "sentinel"
    ops.nodes[sentinel] = {
        "kind": "file",
        "dev": 1,
        "ino": 99_999,
        "nlink": 1,
        "data": bytearray(),
    }
    writer_closes = 0

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal writer_closes
        if fd == writer_fd:
            writer_closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("close reported failure after release")
        original(fd)

    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="handoff"):
        calibration._handoff_result_reader(context)

    assert writer_closes == 1
    assert ops.fds[writer_fd] == sentinel
    assert context.closed is True


def test_result_handoff_close_error_before_release_is_not_retried(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    _, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    writer_fd = context.result_file.fd
    original = ops.close
    writer_closes = 0

    def fail_before_release(fd: int) -> None:
        nonlocal writer_closes
        if fd == writer_fd:
            writer_closes += 1
            raise OSError("close failed before release")
        original(fd)

    ops.close = fail_before_release  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="handoff"):
        calibration._handoff_result_reader(context)

    assert writer_closes == 1
    assert writer_fd in ops.fds
    assert context.closed is True


def test_result_handoff_deadline_expiry_and_duplicate_are_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    _, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    expired = False

    def clock() -> float:
        return 61.0 if expired else 1.0

    deadline = calibration._Deadline(0.0, 60.0, clock)
    object.__setattr__(context.resources.policy, "deadline", deadline)
    context.store.deadline = deadline
    original_open = ops.open_existing_file

    def expire_after_open(directory_fd: int, name: str) -> int:
        nonlocal expired
        fd = original_open(directory_fd, name)
        expired = True
        return fd

    ops.open_existing_file = expire_after_open  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="deadline"):
        calibration._handoff_result_reader(context)
    assert context.closed is True

    second_root = tmp_path / "second"
    second_root.mkdir()
    _, second, _ = _writer_fixture(second_root, monkeypatch, complete)
    object.__setattr__(second, "writing_finished", True)
    with pytest.raises(ManifestError, match="already finished"):
        calibration._handoff_result_reader(second)
    assert second.closed is True


@pytest.mark.parametrize("guard", ["allocation", "projection"])
def test_phase_writer_resource_guard_fails_before_provider_advance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    guard: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, _ = _writer_fixture(tmp_path, monkeypatch, complete)
    monkeypatch.setattr(
        _ScriptedChunkProvider,
        "__next__",
        lambda _self: pytest.fail("provider advanced after resource refusal"),
    )
    if guard == "allocation":
        monkeypatch.setattr(
            calibration._ResourceBoundary,
            "check_planned_allocation",
            lambda _self, _amount: (_ for _ in ()).throw(
                ManifestError("planned allocation injected")
            ),
        )
    else:
        monkeypatch.setattr(
            calibration._ResourceBoundary,
            "check_result_write",
            lambda _self, _amount: (_ for _ in ()).throw(ManifestError("result write injected")),
        )

    with pytest.raises(ManifestError, match="injected"):
        calibration._write_phase_result(context, manifest)
    assert context.closed is True


def test_phase_writer_manifest_startup_failure_invalidates_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, _ = _writer_fixture(tmp_path, monkeypatch, complete)
    malformed = json.loads(json.dumps(manifest))
    malformed["protocol_version"] = "wrong"

    with pytest.raises(ManifestError, match="protocol"):
        calibration._write_phase_result(context, malformed)

    assert context.closed is True


def test_phase_writer_invalid_failure_timestamp_cannot_close_incomplete_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    monkeypatch.setattr(
        calibration,
        "_build_metric_events",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ManifestError("adapter")),
    )
    ops.utc_now = lambda: "invalid"  # type: ignore[method-assign]

    with pytest.raises(ManifestError, match="UTC"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    with pytest.raises(ManifestError):
        calibration._parse_canonical_json_bytes(raw, label="bad timestamp partial")
    assert context.closed is True


@pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux completion syscalls")
def test_native_completion_candidate_and_forked_authority_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = calibration.load_manifest()
    ops = calibration._NativeLinuxOps()
    deadline = calibration._Deadline(time.monotonic(), 30.0, time.monotonic)
    store = calibration._open_or_create_evidence_directory(
        tmp_path, Path("evidence/completion"), ops, deadline
    )
    claim_raw = b"{}\n"
    result_raw = b"{}\n"
    claim = calibration._write_immutable_claim(store, "calibration.claim", claim_raw)
    result = calibration._reserve_result_file(store, "calibration-result.json")
    review = calibration._ReviewAttestation(
        "a" * 40,
        "b" * 40,
        {},
        "docs/reviews/review.md",
        "docs/reviews/attestation.json",
        (),
        "2026-09-27T00:00:00.000000Z",
        "c" * 64,
    )
    harness_path = manifest["integrity"]["protected_paths"]["harness"]
    proof = calibration._InvocationProof("a" * 40, "d" * 40, {harness_path: "e" * 64})
    resources = calibration._ResourceBoundary(
        calibration._ResourcePolicy(2 * 1024**3, ops, deadline),
        ops.current_vms_bytes(),
        ops.current_rss_bytes(),
        ops.peak_rss_bytes(),
    )
    paths = calibration._ArtifactPaths(
        "evidence/completion", claim.name, result.name, "calibration.seal"
    )
    started = "2026-09-27T00:00:00.000000Z"
    claim_sha = hashlib.sha256(claim_raw).hexdigest()
    binding = calibration._phase_context_binding_bytes(
        "calibration", paths, review, proof, resources, claim_sha, started
    )
    context = calibration._PhaseContext(
        "calibration",
        paths,
        review,
        proof,
        resources,
        store,
        claim,
        result,
        claim_sha,
        claim_raw,
        started,
        binding,
        calibration._PHASE_CONTEXT_ISSUER,
    )
    calibration._write_all_evidence(result, result_raw, store)
    ops.fsync(result.fd)
    calibration._handoff_result_reader(context)
    expected = calibration._ExpectedPhaseContext("calibration", b"{}\n", b"{}\n", b"{}\n", None)
    calibration._bind_writer_expected(context, expected)
    expected_binding = context.writer_expected_binding_bytes
    assert isinstance(expected_binding, bytes)
    verified = calibration._VerifiedPhaseEvidence(
        "calibration",
        "FAILED",
        None,
        hashlib.sha256(result_raw).hexdigest(),
        len(result_raw),
        1024,
        1024,
        0.01,
        context.bound_identity_bytes,
        expected_binding,
    )
    monkeypatch.setattr(calibration, "_verify_finished_phase_result", lambda *_args: verified)

    completion = calibration._complete_phase(context, manifest)

    candidate = store.path / paths.seal_name
    assert candidate.read_bytes().endswith(b"\n")
    assert (candidate.stat().st_mode & 0o777) == 0o600
    assert calibration._require_phase_completion(context, completion) is completion
    child_pid = cast(Any, os).fork()
    if child_pid == 0:
        try:
            calibration._require_phase_completion(context, completion)
        except ManifestError:
            os._exit(0)
        os._exit(7)
    _, status = os.waitpid(child_pid, 0)
    assert status == 0
    context.close()


@pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux descriptor modes")
def test_native_result_handoff_retains_actually_read_only_descriptor(
    tmp_path: Path,
) -> None:
    ops = calibration._NativeLinuxOps()
    deadline = calibration._Deadline(time.monotonic(), 30.0, time.monotonic)
    store = calibration._open_or_create_evidence_directory(
        tmp_path, Path("evidence/result"), ops, deadline
    )
    claim_raw = b"{}\n"
    claim = calibration._write_immutable_claim(store, "calibration.claim", claim_raw)
    result = calibration._reserve_result_file(store, "calibration-result.json")
    review = calibration._ReviewAttestation(
        "a" * 40,
        "b" * 40,
        {},
        "docs/reviews/review.md",
        "docs/reviews/attestation.json",
        (),
        "2026-09-27T00:00:00.000000Z",
        "c" * 64,
    )
    proof = calibration._InvocationProof("a" * 40, "d" * 40, {})
    resources = calibration._ResourceBoundary(
        calibration._ResourcePolicy(2 * 1024**3, ops, deadline),
        ops.current_vms_bytes(),
        ops.current_rss_bytes(),
        ops.peak_rss_bytes(),
    )
    paths = calibration._ArtifactPaths(
        "evidence/result",
        claim.name,
        result.name,
        "calibration.seal",
    )
    started = "2026-09-27T00:00:00.000000Z"
    claim_sha = hashlib.sha256(claim_raw).hexdigest()
    binding = calibration._phase_context_binding_bytes(
        "calibration", paths, review, proof, resources, claim_sha, started
    )
    context = calibration._PhaseContext(
        "calibration",
        paths,
        review,
        proof,
        resources,
        store,
        claim,
        result,
        claim_sha,
        claim_raw,
        started,
        binding,
        calibration._PHASE_CONTEXT_ISSUER,
    )
    calibration._write_all_evidence(result, b"{}\n", store)
    ops.fsync(result.fd)

    calibration._handoff_result_reader(context)

    with pytest.raises(OSError):
        os.write(context.result_file.fd, b"x")
    context.require_active("calibration")
    context.close()


def test_phase_writer_rejects_extra_chunk_after_complete_topology(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops = _writer_fixture(tmp_path, monkeypatch, complete)
    _ScriptedChunkProvider.chunks = [
        *_ScriptedChunkProvider.chunks,
        _ScriptedChunkProvider.chunks[-1],
    ]

    with pytest.raises(ManifestError, match="extra"):
        calibration._write_phase_result(context, manifest)

    raw = bytes(ops.nodes[context.store.path / context.paths.result_name]["data"])
    parsed = calibration._parse_canonical_json_bytes(raw, label="extra incomplete")
    assert parsed["chunks"] == complete["chunks"]
    assert parsed["terminal"]["state"] == "INCOMPLETE"
    assert parsed["summary"]["phase_verdict"] == "INCOMPLETE"
    assert context.closed is True


def test_validation_startup_requires_live_completion_and_fresh_deadline(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, calibration_context, ops, _ = _prepared_verification_fixture(
        tmp_path, monkeypatch, complete
    )
    _stub_completion_verifier(monkeypatch, calibration_context)
    completion = calibration._complete_phase(calibration_context, manifest)
    assert completion.phase_verdict == "PASSED"
    original_deadline = calibration_context.resources.deadline
    object.__setattr__(original_deadline, "clock", lambda: 60.0)
    monkeypatch.setattr(time, "monotonic", lambda: 60.0)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    monkeypatch.setattr(
        np.random,
        "PCG64",
        lambda *_args, **_kwargs: pytest.fail("validation startup drew RNG"),
    )

    validation = calibration._begin_validation_phase(calibration_context, completion, manifest)

    assert validation.phase == "validation"
    assert validation.resources.deadline is not original_deadline
    assert validation.resources.deadline.duration_seconds == 7200
    assert validation.resources.deadline.started_at == 60.0
    assert validation.verified_calibration_floor == completion.selected_floor
    assert validation.calibration_completion_binding_bytes == completion.payload_binding_bytes
    assert calibration_context.closed
    assert validation.store.path / validation.paths.claim_name in ops.nodes
    assert validation.store.path / validation.paths.result_name in ops.nodes
    assert validation.store.path / validation.paths.seal_name not in ops.nodes
    with pytest.raises(ManifestError):
        calibration._begin_validation_phase(calibration_context, completion, manifest)
    validation.close()


def test_validation_startup_refuses_failed_completion_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, calibration_context, ops, _ = _prepared_verification_fixture(
        tmp_path, monkeypatch, complete
    )
    _stub_completion_verifier(monkeypatch, calibration_context, verdict="FAILED")
    completion = calibration._complete_phase(calibration_context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    paths = calibration._derive_artifact_paths(
        manifest, "validation", completion.context.review.reviewed_commit
    )
    with pytest.raises(ManifestError, match="PASSED"):
        calibration._begin_validation_phase(calibration_context, completion, manifest)
    assert calibration_context.store.path / paths.claim_name not in ops.nodes
    assert not calibration_context.closed
    assert not calibration_context.completion_consumed
    calibration_context.close()


@pytest.mark.parametrize("target", ["claim", "result", "candidate"])
def test_validation_startup_recomputes_trio_and_consumes_on_tamper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    target: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    path = context.store.path / getattr(
        context.paths,
        {"claim": "claim_name", "result": "result_name", "candidate": "seal_name"}[target],
    )
    ops.nodes[path]["data"][0] ^= 1
    validation_paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )

    with pytest.raises(ManifestError, match=r"changed|bytes"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert context.closed
    assert context.completion_consumed
    assert context.store.path / validation_paths.claim_name not in ops.nodes
    with pytest.raises(ManifestError):
        calibration._begin_validation_phase(context, completion, manifest)


@pytest.mark.parametrize("boundary", ["after_claim", "after_result"])
def test_validation_startup_catches_late_calibration_edit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    boundary: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    path = context.store.path / context.paths.seal_name
    reached = False
    if boundary == "after_claim":
        original = calibration._write_immutable_claim

        def inject(store: Any, name: str, raw: bytes) -> Any:
            nonlocal reached
            result = original(store, name, raw)
            reached = True
            ops.nodes[path]["data"][0] ^= 1
            return result

        monkeypatch.setattr(calibration, "_write_immutable_claim", inject)
    else:
        original_result = calibration._reserve_result_file

        def inject_result(store: Any, name: str) -> Any:
            nonlocal reached
            result = original_result(store, name)
            reached = True
            ops.nodes[path]["data"][0] ^= 1
            return result

        monkeypatch.setattr(calibration, "_reserve_result_file", inject_result)

    with pytest.raises(ManifestError, match="candidate bytes changed"):
        calibration._begin_validation_phase(context, completion, manifest)

    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert reached
    assert context.closed
    assert context.store.path / paths.claim_name in ops.nodes
    assert (context.store.path / paths.result_name in ops.nodes) is (boundary == "after_result")


def test_validation_startup_git_allowance_is_exact_before_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, _ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original = calibration._verify_reviewed_git_state
    seen: list[tuple[str, ...]] = []

    def inspect(*args: Any, **kwargs: Any) -> Any:
        seen.append(tuple(kwargs["allowed_untracked"]))
        return original(*args, **kwargs)

    monkeypatch.setattr(calibration, "_verify_reviewed_git_state", inspect)
    validation = calibration._begin_validation_phase(context, completion, manifest)

    assert seen == [("AGENTS.md", *tuple(context.paths.as_claim_record().values()))]
    assert all("validation" not in item for item in seen[0])
    validation.close()


@pytest.mark.parametrize("defect", ["copied", "wrong_limit", "wrong_pid"])
def test_validation_startup_refuses_authority_or_limit_without_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    defect: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    if defect == "copied":
        completion = dataclasses.replace(completion)
    elif defect == "wrong_limit":
        ops.get_address_space_limit = lambda: (1024, 1024)  # type: ignore[method-assign]
    else:
        monkeypatch.setattr(os, "getpid", lambda: context.original_pid + 1)

    with pytest.raises(ManifestError):
        calibration._begin_validation_phase(context, completion, manifest)

    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.closed is (defect == "wrong_limit")
    assert context.store.path / paths.claim_name not in ops.nodes
    if defect == "copied":
        authentic = context.completion
        assert authentic is not None
        validation = calibration._begin_validation_phase(context, authentic, manifest)
        validation.close()
    elif defect == "wrong_pid":
        context.close()


def test_validation_trio_uses_independent_owned_readers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original_open = ops.open_existing_file
    original_fds = {context.claim_file.fd, context.result_file.fd}
    trio_names = {context.paths.claim_name, context.paths.result_name, context.paths.seal_name}
    new_fds: list[int] = []

    def track(directory_fd: int, name: str) -> int:
        fd = original_open(directory_fd, name)
        if name in trio_names:
            assert fd not in original_fds
            new_fds.append(fd)
        return fd

    ops.open_existing_file = track  # type: ignore[method-assign]
    validation = calibration._begin_validation_phase(context, completion, manifest)

    assert len(new_fds) == 12
    assert len(set(new_fds)) == 12
    assert all(fd not in ops.fds for fd in new_fds)
    validation.close()


def test_validation_candidate_reader_release_then_error_is_not_reclosed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original_open = ops.open_existing_file
    original_close = ops.close
    candidate_fd: int | None = None
    closes = 0
    sentinel = tmp_path / "validation-reader-sentinel"
    ops.nodes[sentinel] = {"kind": "file", "dev": 1, "ino": 987654, "nlink": 1, "data": bytearray()}

    def track(directory_fd: int, name: str) -> int:
        nonlocal candidate_fd
        fd = original_open(directory_fd, name)
        if name == context.paths.seal_name and candidate_fd is None:
            candidate_fd = fd
        return fd

    def release_reuse_then_fail(fd: int) -> None:
        nonlocal closes
        if fd == candidate_fd:
            closes += 1
            del ops.fds[fd]
            del ops.offsets[fd]
            ops.fds[fd] = sentinel
            ops.offsets[fd] = 0
            raise OSError("candidate reader close after release")
        original_close(fd)

    ops.open_existing_file = track  # type: ignore[method-assign]
    ops.close = release_reuse_then_fail  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match="close"):
        calibration._begin_validation_phase(context, completion, manifest)

    assert candidate_fd is not None
    assert closes == 1
    assert ops.fds[candidate_fd] == sentinel
    assert context.closed


def test_calibration_context_binding_rejects_validation_lineage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    _manifest_data, context, _ops, _ = _prepared_verification_fixture(
        tmp_path, monkeypatch, complete
    )
    with pytest.raises(ManifestError, match="cannot carry validation lineage"):
        calibration._phase_context_binding_bytes(
            "calibration",
            context.paths,
            context.review,
            context.proof,
            context.resources,
            context.claim_sha256,
            context.started_at_utc,
            context.original_pid,
            (6, 4.0),
            b"forged",
        )
    context.close()


def test_validation_trio_rejects_invalid_nested_candidate_even_with_matching_digest(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    candidate_path = context.store.path / context.paths.seal_name
    payload = calibration._parse_canonical_json_bytes(
        bytes(ops.nodes[candidate_path]["data"]), label="test candidate"
    )
    payload["prewrite_snapshot"]["peak_rss_bytes"] = True
    raw = calibration._canonical_bytes(payload)
    ops.nodes[candidate_path]["data"] = bytearray(raw)
    forged = dataclasses.replace(
        completion,
        candidate_sha256=hashlib.sha256(raw).hexdigest(),
        candidate_size_bytes=len(raw),
    )

    def isolate_candidate_schema(
        supplied: calibration._PhaseContext, offered: calibration._PhaseCompletion
    ) -> calibration._PhaseCompletion:
        assert supplied is context and offered is forged
        return forged

    # The exact-object authority refusal has its own test; reach the nested schema here.
    monkeypatch.setattr(calibration, "_require_phase_completion", isolate_candidate_schema)
    with pytest.raises(ManifestError, match="size or peak"):
        calibration._recheck_calibration_trio(
            context,
            forged,
            manifest,
            calibration._Deadline(0.0, 7200.0, lambda: 1.0),
            context.resources,
            recompute=False,
        )
    context.close()


@pytest.mark.parametrize("mutation", ["clock", "claim", "result"])
def test_validation_startup_rechecks_after_calibration_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    tick = [1.0]
    monkeypatch.setattr(time, "monotonic", lambda: tick[0])
    original_close = calibration._PhaseContext.close
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )

    def change_during_close(self: calibration._PhaseContext) -> None:
        if self is context:
            if mutation == "clock":
                tick[0] = 7202.0
            else:
                name = paths.claim_name if mutation == "claim" else paths.result_name
                ops.nodes[context.store.path / name]["data"].extend(b"x")
        original_close(self)

    monkeypatch.setattr(calibration._PhaseContext, "close", change_during_close)
    with pytest.raises(ManifestError):
        calibration._begin_validation_phase(context, completion, manifest)

    assert context.closed
    assert context.store.path / paths.claim_name in ops.nodes
    assert context.store.path / paths.result_name in ops.nodes


def test_validation_trio_refuses_completion_revoked_during_recomputation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original = calibration.validate_phase_result

    def revoke(*args: Any, **kwargs: Any) -> Any:
        verified = original(*args, **kwargs)
        object.__setattr__(context, "completion", None)
        return verified

    monkeypatch.setattr(calibration, "validate_phase_result", revoke)
    with pytest.raises(ManifestError, match="completion"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert context.closed
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.store.path / paths.claim_name not in ops.nodes


def test_validation_context_cannot_construct_counted_provider_yet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, _ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    validation = calibration._begin_validation_phase(context, completion, manifest)
    monkeypatch.setattr(
        np.random, "PCG64", lambda *_args, **_kwargs: pytest.fail("validation drew RNG")
    )
    with pytest.raises(ManifestError, match="validation"):
        _REAL_COUNTED_CHUNK_PROVIDER(validation, manifest)
    assert validation.closed


@pytest.mark.parametrize("boundary", ["trio", "git"])
def test_validation_fresh_deadline_covers_trio_and_git(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    boundary: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    tick = [1.0]
    monkeypatch.setattr(time, "monotonic", lambda: tick[0])
    reached = False
    if boundary == "trio":
        original = ops.open_existing_file

        def expire_trio(directory_fd: int, name: str) -> int:
            nonlocal reached
            fd = original(directory_fd, name)
            if name == context.paths.claim_name and not reached:
                reached = True
                tick[0] = 7202.0
            return fd

        ops.open_existing_file = expire_trio  # type: ignore[method-assign]
    else:
        original_git = calibration._verify_reviewed_git_state

        def expire_git(*args: Any, **kwargs: Any) -> Any:
            nonlocal reached
            reached = True
            tick[0] = 7202.0
            return original_git(*args, **kwargs)

        monkeypatch.setattr(calibration, "_verify_reviewed_git_state", expire_git)

    with pytest.raises(ManifestError, match="deadline"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert reached
    assert context.closed
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.store.path / paths.claim_name not in ops.nodes


@pytest.mark.parametrize("artifact", ["claim", "result"])
def test_validation_reservation_fsync_failure_is_permanently_reserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    artifact: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    target = context.store.path / (paths.claim_name if artifact == "claim" else paths.result_name)
    original = ops.fsync
    reached = False

    def fail_target(fd: int) -> None:
        nonlocal reached
        if ops.fds[fd] == target:
            reached = True
            raise OSError("injected validation fsync failure")
        original(fd)

    ops.fsync = fail_target  # type: ignore[method-assign]
    with pytest.raises(ManifestError, match=r"fsync|I/O"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert reached
    assert context.closed and context.completion_consumed
    assert target in ops.nodes
    assert context.store.path / paths.seal_name not in ops.nodes


@pytest.mark.parametrize("mutation", ["replacement", "hardlink"])
def test_validation_late_calibration_identity_or_link_refuses(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original = calibration._write_immutable_claim
    reached = False

    def change_after_claim(store: Any, name: str, raw: bytes) -> Any:
        nonlocal reached
        file = original(store, name, raw)
        reached = True
        candidate = ops.nodes[context.store.path / context.paths.seal_name]
        if mutation == "replacement":
            candidate["ino"] += 100
        else:
            candidate["nlink"] = 2
        return file

    monkeypatch.setattr(calibration, "_write_immutable_claim", change_after_claim)
    with pytest.raises(ManifestError, match=r"identity|link"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert reached and context.closed
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.store.path / paths.claim_name in ops.nodes
    assert context.store.path / paths.result_name not in ops.nodes


def test_validation_startup_refuses_completion_revoked_in_final_trio_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original = calibration._close_phase_start_resources
    cleanup_calls = 0

    def revoke_at_final_cleanup(store: Any, *files: Any) -> None:
        nonlocal cleanup_calls
        if files and all(
            file.name
            in {context.paths.claim_name, context.paths.result_name, context.paths.seal_name}
            for file in files
        ):
            cleanup_calls += 1
            if cleanup_calls == 4:
                object.__setattr__(context, "completion", None)
        original(store, *files)

    monkeypatch.setattr(calibration, "_close_phase_start_resources", revoke_at_final_cleanup)
    with pytest.raises(ManifestError, match="completion"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert cleanup_calls == 4
    assert context.closed
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.store.path / paths.claim_name in ops.nodes
    assert context.store.path / paths.result_name in ops.nodes


@pytest.mark.parametrize("mutation", ["inode", "hardlink"])
def test_validation_final_candidate_rehash_rechecks_identity_after_hash(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    full_calibration: tuple[dict[str, Any], Any],
    mutation: str,
) -> None:
    complete, _ = full_calibration
    manifest, context, ops, _ = _prepared_verification_fixture(tmp_path, monkeypatch, complete)
    _stub_completion_verifier(monkeypatch, context)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_platform_name", lambda: "linux")
    original = calibration._rehash_exact_evidence
    candidate_path = context.store.path / context.paths.seal_name
    candidate_hashes = 0

    def mutate_after_final_hash(*args: Any, **kwargs: Any) -> str:
        nonlocal candidate_hashes
        digest = original(*args, **kwargs)
        if kwargs.get("label") == "calibration evidence" and ops.fds[args[2]] == candidate_path:
            candidate_hashes += 1
            if candidate_hashes == 4:
                node = ops.nodes[candidate_path]
                if mutation == "inode":
                    node["ino"] += 1000
                else:
                    node["nlink"] = 2
        return digest

    monkeypatch.setattr(calibration, "_rehash_exact_evidence", mutate_after_final_hash)
    with pytest.raises(ManifestError, match=r"identity|link"):
        calibration._begin_validation_phase(context, completion, manifest)
    assert candidate_hashes == 4
    assert context.closed
    paths = calibration._derive_artifact_paths(
        manifest, "validation", context.review.reviewed_commit
    )
    assert context.store.path / paths.claim_name in ops.nodes
    assert context.store.path / paths.result_name in ops.nodes


@pytest.mark.skipif(sys.platform != "linux", reason="requires native Linux evidence syscalls")
def test_native_validation_startup_reserves_real_scratch_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = calibration.load_manifest()
    ops = calibration._NativeLinuxOps()
    limit = manifest["runtime_limits"]["max_peak_rss_bytes"]
    monkeypatch.setattr(calibration, "_ROOT", tmp_path)
    monkeypatch.setattr(ops, "get_address_space_limit", lambda: (limit, limit))
    monkeypatch.setattr(
        ops,
        "set_address_space_limit",
        lambda *_args: pytest.fail("scratch smoke installed RLIMIT"),
    )
    deadline = calibration._Deadline(time.monotonic(), 30.0, time.monotonic)
    harness = manifest["integrity"]["protected_paths"]["harness"]
    manifest_sha = hashlib.sha256(calibration._canonical_bytes(manifest)).hexdigest()
    review = calibration._ReviewAttestation(
        "a" * 40,
        "b" * 40,
        {harness: "e" * 64},
        "docs/reviews/scratch-review.md",
        f"docs/reviews/step6a2/{manifest_sha}/task3.review.json",
        (),
        "2026-09-27T00:00:00.000000Z",
        "c" * 64,
    )
    proof = calibration._InvocationProof(
        review.reviewed_commit,
        "d" * 40,
        {harness: "e" * 64},
    )
    paths = calibration._derive_artifact_paths(manifest, "calibration", review.reviewed_commit)
    store = calibration._open_or_create_evidence_directory(
        tmp_path, Path(paths.directory), ops, deadline
    )
    resources = calibration._ResourceBoundary(
        calibration._ResourcePolicy(limit, ops, deadline),
        ops.current_vms_bytes(),
        ops.current_rss_bytes(),
        ops.peak_rss_bytes(),
    )
    started_at = "2026-09-27T00:00:00.000000Z"
    claim_raw = calibration._canonical_bytes(
        {
            "artifact_paths": paths.as_claim_record(),
            "attempt_id": f"{review.reviewed_commit}-calibration",
            "invocation_commit": proof.invocation_commit,
            "manifest_sha256": manifest_sha,
            "phase": "calibration",
            "protected_blobs": dict(proof.protected_blobs),
            "protocol_version": calibration.PROTOCOL_VERSION,
            "review_attestation": {
                "path": review.attestation_path,
                "sha256": review.raw_sha256,
            },
            "reviewed_commit": review.reviewed_commit,
            "schema": "step6a2-phase-claim-v1",
            "started_at_utc": started_at,
        }
    )
    claim = calibration._write_immutable_claim(store, paths.claim_name, claim_raw)
    result = calibration._reserve_result_file(store, paths.result_name)
    claim_sha = hashlib.sha256(claim_raw).hexdigest()
    binding = calibration._phase_context_binding_bytes(
        "calibration", paths, review, proof, resources, claim_sha, started_at
    )
    context = calibration._PhaseContext(
        "calibration",
        paths,
        review,
        proof,
        resources,
        store,
        claim,
        result,
        claim_sha,
        claim_raw,
        started_at,
        binding,
        calibration._PHASE_CONTEXT_ISSUER,
    )
    result_raw = b"{}\n"
    calibration._write_all_evidence(result, result_raw, store)
    ops.fsync(result.fd)
    calibration._handoff_result_reader(context)
    expected = calibration._ExpectedPhaseContext("calibration", b"{}\n", b"{}\n", b"{}\n", None)
    calibration._bind_writer_expected(context, expected)
    expected_binding = context.writer_expected_binding_bytes
    assert isinstance(expected_binding, bytes)
    floor = (6, 4.0)
    evidence = calibration._VerifiedPhaseEvidence(
        "calibration",
        "PASSED",
        floor,
        hashlib.sha256(result_raw).hexdigest(),
        len(result_raw),
        1024,
        ops.peak_rss_bytes(),
        0.01,
        context.bound_identity_bytes,
        expected_binding,
    )
    monkeypatch.setattr(calibration, "_verify_finished_phase_result", lambda *_args: evidence)
    completion = calibration._complete_phase(context, manifest)
    monkeypatch.setattr(calibration, "_read_tracked_worktree_bytes", lambda *_args: b"scratch\n")
    monkeypatch.setattr(calibration, "_parse_review_attestation", lambda *_args: review)
    monkeypatch.setattr(calibration, "_verify_reviewed_git_state", lambda *_args, **_kwargs: proof)
    monkeypatch.setattr(
        calibration,
        "validate_phase_result",
        lambda *_args: calibration.VerifiedPhaseResult("calibration", "PASSED", floor),
    )

    def resource_view(
        _manifest: Any,
        _evidence_path: Path,
        received_ops: Any,
        fresh_deadline: calibration._Deadline,
    ) -> calibration._ResourceBoundary:
        assert received_ops is ops
        return calibration._ResourceBoundary(
            calibration._ResourcePolicy(limit, ops, fresh_deadline),
            ops.current_vms_bytes(),
            ops.current_rss_bytes(),
            ops.peak_rss_bytes(),
        )

    monkeypatch.setattr(calibration, "_prepare_linux_resource_boundary", resource_view)
    monkeypatch.setattr(
        np.random, "PCG64", lambda *_args, **_kwargs: pytest.fail("scratch startup drew RNG")
    )
    validation = calibration._begin_validation_phase(context, completion, manifest)
    try:
        assert context.closed
        assert validation.verified_calibration_floor == floor
        assert validation.resources.deadline is not deadline
        for file in (validation.claim_file, validation.result_file):
            path = validation.store.path / file.name
            metadata = path.stat()
            assert stat.S_ISREG(metadata.st_mode)
            assert metadata.st_mode & 0o777 == 0o600
            assert (metadata.st_dev, metadata.st_ino) == (file.device, file.inode)
            assert (os.fstat(file.fd).st_dev, os.fstat(file.fd).st_ino) == (file.device, file.inode)
        assert not (validation.store.path / validation.paths.seal_name).exists()
        assert (store.path / paths.seal_name).is_file()
    finally:
        validation.close()
