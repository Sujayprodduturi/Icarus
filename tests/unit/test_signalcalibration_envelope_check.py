"""The aggregate resource gate refuses missing or undersized witnesses."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest
from scripts.check_signalcalibration_envelope import EnvelopeFailure, check_reports

COMMIT = "a" * 40


def _phase(size: int) -> dict[str, Any]:
    return {
        "verdict": "PASSED",
        "result_size_bytes": size,
        "completed_elapsed_seconds": 100.0,
        "completed_peak_rss_bytes": 500_000_000,
        "observed_peak_vms_bytes": 700_000_000,
        "max_encoded_chunk_bytes": size // 100,
        "verification_projected_bytes": 100_000_000,
        "address_space_limit_bytes": 2_147_483_648,
    }


def _reports() -> dict[str, dict[str, Any]]:
    reports: dict[str, dict[str, Any]] = {}
    for mode in ("generated", "scripted", "validation-fallback"):
        reports[mode] = {
            "schema": "step6a2-test-only-resource-proof-v1",
            "authority": "NONE",
            "mode": mode,
            "source_commit": COMMIT,
            "mode_complete": True,
            "reserved_seed_draws": 0,
            "native_environment": {"osrelease": "linux", "pid1": "systemd", "container": False},
            "filesystem_type": "ext4",
            "host_cpu_count": 4,
            "host_ram_bytes": 8_000_000_000,
            "peak_vms_bytes": 800_000_000,
            "fsync_successes": 10,
            "close_successes": 10,
            "fsync_failures": 0,
            "close_failures": 0,
            "phases": {"calibration": _phase(40_000_000)},
        }
    reports["scripted"]["phases"] = {
        "calibration": _phase(50_000_000),
        "validation": _phase(60_000_000),
    }
    reports["validation-fallback"]["phases"]["validation"] = _phase(55_000_000)
    return reports


def test_complete_non_reserved_envelope_passes() -> None:
    verdict = check_reports(_reports(), COMMIT)
    assert verdict["verdict"] == "WITHIN_FROZEN_LIMITS"
    assert verdict["official_streams_drawn"] is False


def test_generated_calibration_failure_requires_separate_validation_witness() -> None:
    reports = _reports()
    reports["generated"]["phases"]["calibration"]["verdict"] = "FAILED"
    assert check_reports(reports, COMMIT)["verdict"] == "WITHIN_FROZEN_LIMITS"
    del reports["validation-fallback"]["phases"]["validation"]
    with pytest.raises(EnvelopeFailure, match="required phase evidence"):
        check_reports(reports, COMMIT)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_validation",
        "small_scripted",
        "source",
        "container",
        "limit",
        "projection",
        "fsync",
        "scripted_verdict",
    ],
)
def test_envelope_refuses_incomplete_or_unsafe_witness(mutation: str) -> None:
    reports = deepcopy(_reports())
    if mutation == "missing_validation":
        del reports["validation-fallback"]["phases"]["validation"]
    elif mutation == "small_scripted":
        reports["scripted"]["phases"]["validation"]["result_size_bytes"] = 1
    elif mutation == "source":
        reports["generated"]["source_commit"] = "b" * 40
    elif mutation == "container":
        reports["scripted"]["native_environment"]["container"] = True
    elif mutation == "limit":
        reports["generated"]["phases"]["calibration"]["completed_peak_rss_bytes"] = 3_000_000_000
    elif mutation == "projection":
        reports["generated"]["phases"]["calibration"]["verification_projected_bytes"] = (
            3_000_000_000
        )
    elif mutation == "scripted_verdict":
        reports["scripted"]["phases"]["validation"]["verdict"] = "FAILED"
    else:
        reports["validation-fallback"]["fsync_failures"] = 1
    with pytest.raises(EnvelopeFailure):
        check_reports(reports, COMMIT)
