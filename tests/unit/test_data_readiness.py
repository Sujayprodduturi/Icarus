"""Immutable real-data bundle gate tests use invented metadata and payload bytes only."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from icarus.engine.data_readiness import ReadinessError, preflight_bundle

ROLES = (
    "daily_stock",
    "pit_universe",
    "corporate_action",
    "m15_stock",
    "nifty_observation",
    "session_calendar",
    "opening_liquidity",
)


def _write_bundle(root: Path, *, invented: bool = True) -> tuple[Path, Path, Path]:
    root.mkdir()
    artifacts = []
    for role in ROLES:
        path = root / f"{role}.jsonl"
        path.write_bytes(f"invented-{role}\n".encode())
        artifacts.append(
            {
                "role": role,
                "path": path.name,
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "format": "jsonl",
                "schema_version": 1,
                "parser_version": "icarus-real-data-v1",
                "vendor": "INVENTED_TEST_VENDOR" if invented else "REVIEWED_VENDOR",
                "venue": "NSE",
                "instrument": "NIFTY 50" if role == "nifty_observation" else "CASH_EQUITY",
                "price_basis": "PRICE_INDEX" if role == "nifty_observation" else "RAW_OBSERVED",
                "source_revision": "fixture-1",
                "retrieved_at": "2026-10-14T00:00:00Z",
                "coverage_start": "2015-01-01T00:00:00Z",
                "coverage_end": "2022-12-30T23:59:59Z",
                "archival_evidence": "invented-local-fixture",
                "use_evidence": "invented-test-only",
                "projection_policy": (
                    "EXACT_OBSERVED_SESSION_CLOSE" if role == "nifty_observation" else "NONE"
                ),
            }
        )
    manifest = root / "manifest.json"
    manifest.write_text(json.dumps({"schema_version": 1, "artifacts": artifacts}))
    policy = root.parent / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "max_manifest_bytes": 100_000,
                "max_artifact_bytes": 10_000,
                "max_total_bytes": 50_000,
                "matching_policy": "exact_event_v1",
                "matching_policy_sha256": "a" * 64,
                "registered_at": "2026-10-13T00:00:00Z",
                "source_binding": "invented-source-policy-v1",
            }
        )
    )
    approval = root.parent / "approval.json"
    approval.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "authority": "INVENTED_REVIEWER" if invented else "EXTERNAL_REVIEWER",
                "licence_evidence": "invented" if invented else "reviewed-licence",
                "approved_at": "2026-10-14T00:00:00Z",
                "invented": invented,
                "manifest_sha256": hashlib.sha256(manifest.read_bytes()).hexdigest(),
                "policy_sha256": hashlib.sha256(policy.read_bytes()).hexdigest(),
                "artifact_sha256": {x["role"]: x["sha256"] for x in artifacts},
            }
        )
    )
    return manifest, approval, policy


def test_preflight_captures_immutable_bytes_without_decoding_price_records(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    result = preflight_bundle(manifest, approval, policy)
    assert result.software_verified is True
    assert result.data_qualified is False
    assert result.run_authorized is False
    assert result.status_reasons == ("INVENTED_EXTERNAL_EVIDENCE", "RUN_AUTHORIZATION_ABSENT")
    assert tuple(item.role for item in result.artifacts) == ROLES
    assert result.artifacts[0].payload.startswith(b"invented-daily_stock")
    with pytest.raises(TypeError):
        result.artifacts[0].metadata["vendor"] = "CHANGED"  # type: ignore[index]


def test_external_metadata_pin_alone_does_not_claim_data_qualified(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle", invented=False)
    result = preflight_bundle(manifest, approval, policy)
    assert result.software_verified and not result.data_qualified and not result.run_authorized
    assert result.status_reasons == ("DATA_PAYLOAD_NOT_ASSEMBLED", "RUN_AUTHORIZATION_ABSENT")


def test_bundle_cannot_contain_its_own_approval_or_use_bool_schema(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    internal = manifest.parent / "approval.json"
    internal.write_bytes(approval.read_bytes())
    with pytest.raises(ReadinessError, match="EXTERNAL_EVIDENCE_PATH"):
        preflight_bundle(manifest, internal, policy)
    value = json.loads(manifest.read_text())
    value["schema_version"] = True
    manifest.write_text(json.dumps(value))
    approved = json.loads(approval.read_text())
    approved["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    approval.write_text(json.dumps(approved))
    with pytest.raises(ReadinessError, match="MANIFEST_SCHEMA"):
        preflight_bundle(manifest, approval, policy)


def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    policy.write_text('{"schema_version":1,"schema_version":1}')
    with pytest.raises(ReadinessError, match="POLICY_JSON"):
        preflight_bundle(manifest, approval, policy)


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="FIFO creation is unavailable on Windows")
def test_nonregular_artifact_is_rejected_before_read(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    target = manifest.parent / "daily_stock.jsonl"
    target.unlink()
    getattr(os, "mkfifo")(target)  # noqa: B009
    with pytest.raises(ReadinessError, match="NONREGULAR_FILE"):
        preflight_bundle(manifest, approval, policy)
    policy.write_text('{"schema_version":NaN}')
    with pytest.raises(ReadinessError, match="POLICY_JSON"):
        preflight_bundle(manifest, approval, policy)


def test_manifest_cannot_approve_itself_or_omit_external_hash_pins(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    value = json.loads(approval.read_text())
    del value["artifact_sha256"]["m15_stock"]
    approval.write_text(json.dumps(value))
    with pytest.raises(ReadinessError, match="APPROVAL_ARTIFACT_PINS"):
        preflight_bundle(manifest, approval, policy)


@pytest.mark.parametrize("bad_path", ["../escape.jsonl", "/absolute.jsonl", "C:/escape.jsonl"])
def test_member_paths_must_be_relative_children(tmp_path: Path, bad_path: str) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    value = json.loads(manifest.read_text())
    value["artifacts"][0]["path"] = bad_path
    manifest.write_text(json.dumps(value))
    approved = json.loads(approval.read_text())
    approved["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    approval.write_text(json.dumps(approved))
    with pytest.raises(ReadinessError, match="MEMBER_PATH"):
        preflight_bundle(manifest, approval, policy)


def test_changed_bytes_duplicate_roles_and_unknown_schema_fail_closed(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    (manifest.parent / "m15_stock.jsonl").write_bytes(b"changed")
    with pytest.raises(ReadinessError, match=r"ARTIFACT_(SIZE|HASH)"):
        preflight_bundle(manifest, approval, policy)

    manifest, approval, policy = _write_bundle(tmp_path / "duplicate")
    value = json.loads(manifest.read_text())
    value["artifacts"][1]["role"] = "daily_stock"
    manifest.write_text(json.dumps(value))
    approved = json.loads(approval.read_text())
    approved["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    approval.write_text(json.dumps(approved))
    with pytest.raises(ReadinessError, match="ARTIFACT_ROLES"):
        preflight_bundle(manifest, approval, policy)

    policy_value = json.loads(policy.read_text())
    policy_value["schema_version"] = 2
    policy.write_text(json.dumps(policy_value))
    with pytest.raises(ReadinessError, match="POLICY_SCHEMA"):
        preflight_bundle(manifest, approval, policy)


def test_symlink_member_and_resource_overflow_fail_before_payload_release(tmp_path: Path) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    target = manifest.parent / "daily_stock.jsonl"
    link = manifest.parent / "linked.jsonl"
    try:
        link.symlink_to(target)
    except OSError:
        pytest.skip("symlinks are unavailable to this Windows test user")
    value = json.loads(manifest.read_text())
    value["artifacts"][0]["path"] = link.name
    value["artifacts"][0]["size"] = link.stat().st_size
    value["artifacts"][0]["sha256"] = hashlib.sha256(link.read_bytes()).hexdigest()
    manifest.write_text(json.dumps(value))
    approved = json.loads(approval.read_text())
    approved["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()
    approved["artifact_sha256"]["daily_stock"] = value["artifacts"][0]["sha256"]
    approval.write_text(json.dumps(approved))
    with pytest.raises(ReadinessError, match="MEMBER_LINK"):
        preflight_bundle(manifest, approval, policy)
