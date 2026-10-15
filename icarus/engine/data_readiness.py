"""Fail-closed metadata gate for immutable local market-data bundles.

The gate authenticates byte identity against separately supplied evidence.  It does not
authenticate a vendor, inspect prices, evaluate a strategy, or authorize an experiment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
from types import MappingProxyType
from typing import Any, Final

_HASH: Final = re.compile(r"[0-9a-f]{64}")
ARTIFACT_ROLES: Final = (
    "daily_stock",
    "pit_universe",
    "corporate_action",
    "m15_stock",
    "nifty_observation",
    "session_calendar",
    "opening_liquidity",
)
_ARTIFACT_FIELDS: Final = {
    "role",
    "path",
    "size",
    "sha256",
    "format",
    "schema_version",
    "parser_version",
    "vendor",
    "venue",
    "instrument",
    "price_basis",
    "source_revision",
    "retrieved_at",
    "coverage_start",
    "coverage_end",
    "archival_evidence",
    "use_evidence",
    "projection_policy",
}


class ReadinessError(ValueError):
    """Typed fail-closed boundary error; its code is stable for automation."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class CapturedArtifact:
    role: str
    relative_path: str
    sha256: str
    size: int
    payload: bytes
    metadata: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class BundlePreflight:
    manifest_sha256: str
    approval_sha256: str
    policy_sha256: str
    artifacts: tuple[CapturedArtifact, ...]
    software_verified: bool
    data_qualified: bool
    run_authorized: bool
    status_reasons: tuple[str, ...]


def _reject_alias_chain(path: Path, *, stop: Path | None = None) -> None:
    current = path
    while True:
        if current.is_symlink() or current.is_junction():
            raise ReadinessError("MEMBER_LINK")
        if current == stop or current.parent == current:
            return
        current = current.parent


def _read_limited(path: Path, limit: int, code: str) -> bytes:
    try:
        _reject_alias_chain(path)
        before = path.stat()
        if not stat.S_ISREG(before.st_mode):
            raise ReadinessError("NONREGULAR_FILE")
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise ReadinessError("NONREGULAR_FILE")
            value = handle.read(limit + 1)
            after_open = os.fstat(handle.fileno())
        after = path.stat()
    except ReadinessError:
        raise
    except OSError as exc:
        raise ReadinessError(code) from exc

    def identity(stat: os.stat_result) -> tuple[int, int, int, int]:
        return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns

    if len(value) > limit:
        raise ReadinessError(code)
    if (
        identity(before) != identity(opened)
        or identity(opened) != identity(after_open)
        or identity(after_open) != identity(after)
    ):
        raise ReadinessError("BYTES_CHANGED")
    return value


def _object(data: bytes, code: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        value = json.loads(
            data,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise ReadinessError(code) from exc
    if type(value) is not dict:
        raise ReadinessError(code)
    return value


def _exact_fields(value: dict[str, Any], wanted: set[str], code: str) -> None:
    if set(value) != wanted:
        raise ReadinessError(code)


def _sha(value: object, code: str) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise ReadinessError(code)
    return value


def _positive(value: object, code: str) -> int:
    if type(value) is not int or value <= 0:
        raise ReadinessError(code)
    return value


def _utc_text(value: object, code: str) -> datetime:
    if (
        type(value) is not str
        or not value.endswith("Z")
        or re.search(r"\.\d{7,}Z$", value) is not None
    ):
        raise ReadinessError(code)
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise ReadinessError(code) from exc
    if parsed.tzinfo is not UTC:
        raise ReadinessError(code)
    return parsed


def _member(root: Path, value: object) -> Path:
    if type(value) is not str or not value:
        raise ReadinessError("MEMBER_PATH")
    posix, windows = PurePosixPath(value), PureWindowsPath(value)
    if posix.is_absolute() or windows.is_absolute() or ".." in posix.parts:
        raise ReadinessError("MEMBER_PATH")
    candidate = root.joinpath(*posix.parts)
    try:
        resolved_root = root.resolve(strict=True)
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise ReadinessError("MEMBER_PATH") from exc
    try:
        contained = os.path.commonpath((resolved_root, resolved)) == str(resolved_root)
    except ValueError:
        contained = False
    if not contained:
        raise ReadinessError("MEMBER_PATH")
    _reject_alias_chain(candidate, stop=root)
    return candidate


def preflight_bundle(
    manifest_path: Path, approval_path: Path, policy_path: Path
) -> BundlePreflight:
    """Capture all member bytes after metadata validation without decoding any payload."""
    for path in (manifest_path, approval_path, policy_path):
        if not isinstance(path, Path):
            raise TypeError("preflight paths must be pathlib.Path")
    try:
        bundle_root = manifest_path.parent.resolve(strict=True)
        for external in (approval_path, policy_path):
            resolved = external.resolve(strict=True)
            try:
                contained = os.path.commonpath((bundle_root, resolved)) == str(bundle_root)
            except ValueError:
                contained = False
            if contained:
                raise ReadinessError("EXTERNAL_EVIDENCE_PATH")
    except ReadinessError:
        raise
    except OSError as exc:
        raise ReadinessError("EXTERNAL_EVIDENCE_PATH") from exc
    policy_bytes = _read_limited(policy_path, 1_000_000, "POLICY_SIZE")
    policy = _object(policy_bytes, "POLICY_JSON")
    _exact_fields(
        policy,
        {
            "schema_version",
            "max_manifest_bytes",
            "max_artifact_bytes",
            "max_total_bytes",
            "matching_policy",
            "matching_policy_sha256",
            "registered_at",
            "source_binding",
        },
        "POLICY_FIELDS",
    )
    if type(policy["schema_version"]) is not int or policy["schema_version"] != 1:
        raise ReadinessError("POLICY_SCHEMA")
    manifest_limit = _positive(policy["max_manifest_bytes"], "POLICY_LIMIT")
    artifact_limit = _positive(policy["max_artifact_bytes"], "POLICY_LIMIT")
    total_limit = _positive(policy["max_total_bytes"], "POLICY_LIMIT")
    _sha(policy["matching_policy_sha256"], "POLICY_MATCH_HASH")
    if type(policy["matching_policy"]) is not str or not policy["matching_policy"]:
        raise ReadinessError("POLICY_MATCH_NAME")
    for field in ("registered_at", "source_binding"):
        if type(policy[field]) is not str or not policy[field]:
            raise ReadinessError("POLICY_REGISTRATION")
    policy_registered = _utc_text(policy["registered_at"], "POLICY_REGISTRATION")

    manifest_bytes = _read_limited(manifest_path, manifest_limit, "MANIFEST_SIZE")
    approval_bytes = _read_limited(approval_path, 1_000_000, "APPROVAL_SIZE")
    manifest, approval = (
        _object(manifest_bytes, "MANIFEST_JSON"),
        _object(approval_bytes, "APPROVAL_JSON"),
    )
    _exact_fields(manifest, {"schema_version", "artifacts"}, "MANIFEST_FIELDS")
    _exact_fields(
        approval,
        {
            "schema_version",
            "authority",
            "licence_evidence",
            "approved_at",
            "invented",
            "manifest_sha256",
            "policy_sha256",
            "artifact_sha256",
        },
        "APPROVAL_FIELDS",
    )
    if type(manifest["schema_version"]) is not int or manifest["schema_version"] != 1:
        raise ReadinessError("MANIFEST_SCHEMA")
    if type(approval["schema_version"]) is not int or approval["schema_version"] != 1:
        raise ReadinessError("APPROVAL_SCHEMA")
    if approval["manifest_sha256"] != hashlib.sha256(manifest_bytes).hexdigest():
        raise ReadinessError("APPROVAL_MANIFEST_PIN")
    if approval["policy_sha256"] != hashlib.sha256(policy_bytes).hexdigest():
        raise ReadinessError("APPROVAL_POLICY_PIN")
    rows = manifest["artifacts"]
    if type(rows) is not list or len(rows) != len(ARTIFACT_ROLES):
        raise ReadinessError("ARTIFACT_ROLES")
    if type(approval["artifact_sha256"]) is not dict:
        raise ReadinessError("APPROVAL_ARTIFACT_PINS")
    roles = [row.get("role") for row in rows if type(row) is dict]
    if tuple(roles) != ARTIFACT_ROLES or set(approval["artifact_sha256"]) != set(ARTIFACT_ROLES):
        raise ReadinessError(
            "ARTIFACT_ROLES" if tuple(roles) != ARTIFACT_ROLES else "APPROVAL_ARTIFACT_PINS"
        )

    captured: list[CapturedArtifact] = []
    total = 0
    for row in rows:
        assert type(row) is dict
        _exact_fields(row, _ARTIFACT_FIELDS, "ARTIFACT_FIELDS")
        schema_supported = row["schema_version"] == 1 or (
            row["role"] == "nifty_observation"
            and row["schema_version"] == 2
            and row["projection_policy"] == "DESCRIPTIVE_CANDLE_PROXY"
            and row["parser_version"] == "icarus-benchmark-candle-v2"
        )
        if (
            type(row["schema_version"]) is not int
            or not schema_supported
            or row["format"] not in ("json", "jsonl")
        ):
            raise ReadinessError("ARTIFACT_SCHEMA")
        for field in _ARTIFACT_FIELDS - {"size", "schema_version"}:
            if type(row[field]) is not str or not row[field]:
                raise ReadinessError("ARTIFACT_METADATA")
        declared_size = _positive(row["size"], "ARTIFACT_SIZE")
        declared_hash = _sha(row["sha256"], "ARTIFACT_HASH")
        if approval["artifact_sha256"].get(row["role"]) != declared_hash:
            raise ReadinessError("APPROVAL_ARTIFACT_PINS")
        path = _member(manifest_path.parent, row["path"])
        remaining = total_limit - total
        if declared_size > min(artifact_limit, remaining):
            raise ReadinessError("BUNDLE_SIZE" if declared_size > remaining else "ARTIFACT_SIZE")
        payload = _read_limited(path, min(artifact_limit, remaining), "ARTIFACT_SIZE")
        if len(payload) != declared_size:
            raise ReadinessError("ARTIFACT_SIZE")
        if hashlib.sha256(payload).hexdigest() != declared_hash:
            raise ReadinessError("ARTIFACT_HASH")
        total += len(payload)
        if total > total_limit:
            raise ReadinessError("BUNDLE_SIZE")
        captured.append(
            CapturedArtifact(
                row["role"],
                row["path"],
                declared_hash,
                declared_size,
                payload,
                MappingProxyType(dict(row)),
            )
        )
    invented = approval["invented"]
    if type(invented) is not bool:
        raise ReadinessError("APPROVAL_INVENTED_FLAG")
    for name in ("authority", "licence_evidence", "approved_at"):
        if type(approval[name]) is not str or not approval[name]:
            raise ReadinessError("APPROVAL_METADATA")
    if _utc_text(approval["approved_at"], "APPROVAL_METADATA") < policy_registered:
        raise ReadinessError("APPROVAL_METADATA")
    reasons = (("INVENTED_EXTERNAL_EVIDENCE",) if invented else ("DATA_PAYLOAD_NOT_ASSEMBLED",)) + (
        "RUN_AUTHORIZATION_ABSENT",
    )
    return BundlePreflight(
        hashlib.sha256(manifest_bytes).hexdigest(),
        hashlib.sha256(approval_bytes).hexdigest(),
        hashlib.sha256(policy_bytes).hexdigest(),
        tuple(captured),
        True,
        False,
        False,
        reasons,
    )
