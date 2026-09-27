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
from typing import Any, cast

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
        return fd

    def _stat(self, path: Path) -> Any:
        node = self.nodes[path]
        mode = stat.S_IFDIR | 0o700 if node["kind"] == "dir" else stat.S_IFREG | 0o600
        return SimpleNamespace(
            st_mode=mode, st_dev=node["dev"], st_ino=node["ino"], st_nlink=node["nlink"]
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
        self.nodes[self.fds[fd]]["data"].extend(data[:amount])
        self.calls.append(("write", self.fds[fd], amount))
        return amount

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

    with pytest.raises(ManifestError, match=r"binding|claim bytes"):
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
    monkeypatch.setattr(
        calibration,
        "_scalar_cr2_moments",
        lambda *_args: MetricRefusal.ZERO_VARIANCE,
    )

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
