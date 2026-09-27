"""Deterministic contract tests for Step-6a.2 Task 3 slice 1A."""

from __future__ import annotations

import dataclasses
import json
from typing import Any

import pytest
import scripts.signal_calibration as calibration
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
