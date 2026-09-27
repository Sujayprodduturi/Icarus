"""Deterministic contract tests for Step-6a.2 Task 3 slice 1A."""

from __future__ import annotations

import dataclasses
import hashlib
import json
from typing import Any

import pytest
import scripts.signal_calibration as calibration
from scipy.stats import t
from scripts.signal_calibration import ManifestError, load_manifest


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
