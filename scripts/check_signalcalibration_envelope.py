"""Aggregate three non-reserved native resource reports into one fail-closed verdict."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


class EnvelopeFailure(ValueError):
    """A required resource witness is missing or exceeds the frozen limit."""


def _positive_int(value: Any, label: str) -> int:
    if type(value) is not int or value <= 0:
        raise EnvelopeFailure(f"{label} must be a positive integer")
    return value


def check_reports(reports: dict[str, dict[str, Any]], expected_commit: str) -> dict[str, Any]:
    limit = 2_147_483_648
    duration = 7_200
    modes = {"generated", "scripted", "validation-fallback"}
    if set(reports) != modes or re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise EnvelopeFailure("resource report set or source commit is invalid")
    for mode, report in reports.items():
        if (
            report.get("schema") != "step6a2-test-only-resource-proof-v1"
            or report.get("authority") != "NONE"
            or report.get("mode") != mode
            or report.get("source_commit") != expected_commit
            or report.get("mode_complete") is not True
            or report.get("reserved_seed_draws") != 0
        ):
            raise EnvelopeFailure(f"{mode} report identity or completion differs")
        native = report.get("native_environment")
        if (
            not isinstance(native, dict)
            or native.get("container") is not False
            or native.get("pid1") not in {"init", "systemd"}
            or "microsoft" in str(native.get("osrelease", "")).casefold()
            or report.get("filesystem_type") not in {"ext4", "xfs", "btrfs"}
        ):
            raise EnvelopeFailure(f"{mode} native host or filesystem was not proved")
        for label in (
            "host_cpu_count",
            "host_ram_bytes",
            "peak_vms_bytes",
            "fsync_successes",
            "close_successes",
        ):
            _positive_int(report.get(label), f"{mode}.{label}")
        if (
            report.get("fsync_failures") != 0
            or report.get("close_failures") != 0
            or report["peak_vms_bytes"] > limit
        ):
            raise EnvelopeFailure(f"{mode} native operation or address-space limit failed")
        phases = report.get("phases")
        required = {"calibration", "validation"} if mode != "generated" else {"calibration"}
        if not isinstance(phases, dict) or not required.issubset(phases):
            raise EnvelopeFailure(f"{mode} required phase evidence is missing")
        for phase, evidence in phases.items():
            if phase not in {"calibration", "validation"} or not isinstance(evidence, dict):
                raise EnvelopeFailure(f"{mode} phase record is invalid")
            for label in (
                "result_size_bytes",
                "completed_peak_rss_bytes",
                "observed_peak_vms_bytes",
                "max_encoded_chunk_bytes",
                "verification_projected_bytes",
            ):
                _positive_int(evidence.get(label), f"{mode}.{phase}.{label}")
            elapsed = evidence.get("completed_elapsed_seconds")
            if not isinstance(elapsed, (int, float)) or isinstance(elapsed, bool):
                raise EnvelopeFailure(f"{mode}.{phase} has no numeric elapsed time")
            if (
                not 0 < elapsed < duration
                or evidence["completed_peak_rss_bytes"] > limit
                or evidence["observed_peak_vms_bytes"] > limit
                or evidence["verification_projected_bytes"] > limit
                or evidence.get("address_space_limit_bytes") != limit
                or evidence.get("verdict") not in {"PASSED", "FAILED"}
            ):
                raise EnvelopeFailure(f"{mode}.{phase} exceeded or lacked a frozen limit")
    generated = reports["generated"]["phases"]
    fallback = reports["validation-fallback"]["phases"]
    scripted = reports["scripted"]["phases"]
    if (
        scripted["calibration"]["verdict"] != "PASSED"
        or scripted["validation"]["verdict"] != "PASSED"
        or fallback["calibration"]["verdict"] != "PASSED"
    ):
        raise EnvelopeFailure("scripted handoff did not complete with passing fixtures")
    for phase in ("calibration", "validation"):
        comparator = generated["calibration"] if phase == "calibration" else fallback["validation"]
        for label in ("result_size_bytes", "max_encoded_chunk_bytes"):
            if scripted[phase][label] < comparator[label]:
                raise EnvelopeFailure(f"scripted {phase} did not bound generated {label}")
        if phase == "validation" and "validation" in generated:
            for label in ("result_size_bytes", "max_encoded_chunk_bytes"):
                if scripted[phase][label] < generated["validation"][label]:
                    raise EnvelopeFailure(f"scripted validation did not bound generated {label}")
    return {
        "schema": "step6a2-native-resource-envelope-verdict-v1",
        "source_commit": expected_commit,
        "verdict": "WITHIN_FROZEN_LIMITS",
        "authority": "NONE",
        "official_streams_drawn": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--expected-commit", required=True)
    args = parser.parse_args()
    try:
        reports = {
            mode: json.loads(
                (
                    args.directory / f"signal-resource-{mode}" / "resource-proof-report.json"
                ).read_bytes()
            )
            for mode in ("generated", "scripted", "validation-fallback")
        }
        verdict = check_reports(reports, args.expected_commit)
    except (EnvelopeFailure, OSError, ValueError, KeyError, TypeError) as exc:
        print(f"native resource envelope refused: {exc}")
        return 1
    print(json.dumps(verdict, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
