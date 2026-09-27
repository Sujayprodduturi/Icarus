"""Offline deterministic preflight for the frozen Step-6a.2 synthetic protocol.

Task 1 intentionally contains no random generator or interval runner.  Its only jobs are to
authenticate the machine manifest, prove structural support, perform exact analytic binomial
preflight, and keep the held-back validation seed locked behind a complete calibration artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import importlib
import json
import math
import os
import re
import stat
import subprocess
import sys
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Final, NoReturn, cast

import numpy as np
from numpy.typing import NDArray
from scipy.stats import beta, binom, norm, t

PROTOCOL_VERSION: Final = "step6a2-synthetic-calibration-v1"
SELECTION_SCHEMA: Final = "step6a2-calibration-selection-v1"
METHOD_VERSION: Final = "entry-session-cr2-satterthwaite-v1"
_TEST_FIXTURE_SEED: Final = 917260001
_RESERVED_PHASE_SEEDS: Final = frozenset({2026092602, 2026092603})
_ROOT: Final = Path(__file__).resolve().parents[1]
_MANIFEST: Final = _ROOT / "docs/plans/2026-09-26-step6a2-calibration-manifest.json"
_DIGEST: Final = _MANIFEST.with_suffix(".sha256")
_HEX64: Final = re.compile(r"[0-9a-f]{64}")
_TOP_LEVEL_KEYS: Final = {
    "acceptance",
    "candidate_floors",
    "dgp_contract",
    "dynamic_geometries",
    "geometries",
    "integrity",
    "method_version",
    "parity",
    "phases",
    "protocol_version",
    "refusals",
    "rng",
    "runtime_limits",
    "selection_artifact_schema",
    "source_geometry",
    "versions",
}
_CELL_KEYS: Final = {
    "expected_candidate_support",
    "family",
    "geometry_id",
    "id",
    "parameters",
    "role",
    "targets",
}
_EXPECTED_FLOORS: Final = (
    (6, 4.0),
    (8, 6.0),
    (12, 8.0),
    (16, 12.0),
)
_NU_CACHE: dict[tuple[str, tuple[tuple[int, int], ...]], float] = {}
_STREAM_CACHE: OrderedDict[tuple[int, int, int, int, int, str], NDArray[np.float64]] = OrderedDict()
_MAX_CACHED_COMPONENT_CHUNKS: Final = 8

_EXPECTED_STREAMS: Final = {
    "amplitude": 2,
    "block_session_factor_or_ar_innovations": 1,
    "daily_innovations": 4,
    "independent_benchmark_factor": 3,
    "trade_idiosyncratic_normal": 0,
}
_PARAMETER_KEYS: Final = {
    "bounded_rare_magnitude": {"amplitude_high", "amplitude_high_probability", "p", "rho"},
    "cross_block_serial_factor": {"p", "rho"},
    "dynamic_h_block_factor": {
        "h_loss",
        "h_win",
        "nominal_l",
        "p",
        "rho",
        "source_span",
        "trades_per_nominal_block",
    },
    "independent": {"p"},
    "independent_block_factor": {"p", "rho"},
    "overlapping_holds": {"h", "p"},
    "same_session_burst": {"location", "p"},
    "two_regime_shift": {"p_first", "p_last", "rho"},
    "unequal_occupancy": {"p", "rho"},
}


class ManifestError(ValueError):
    """The frozen protocol manifest or its provenance is invalid."""


class SelectionArtifactError(ValueError):
    """A calibration selection artifact cannot unlock held-back validation."""


class BatchRefusal(StrEnum):
    """Offline component-local reasons an exact synthetic interval is unavailable."""

    EMPTY_SAMPLE = "empty_sample"
    TOO_FEW_BLOCKS = "too_few_blocks"
    ZERO_VARIANCE = "zero_variance"
    INVALID_VARIANCE = "invalid_variance"
    INVALID_DF = "invalid_df"


@dataclass(frozen=True, slots=True)
class BatchInterval:
    """Exact offline CR2/t interval; raw bounds are retained before display clipping."""

    mean: float
    variance: float
    degrees_of_freedom: float
    raw_lower: float
    raw_upper: float
    lower: float
    upper: float


@dataclass(frozen=True, slots=True)
class SyntheticReplicate:
    """One artificial paired stock/benchmark vector for offline calibration only."""

    entry_indices: tuple[int, ...]
    holding_sessions: tuple[int, ...]
    block_ids: tuple[int, ...]
    block_length: int
    wins: tuple[bool, ...]
    raw: tuple[float, ...]
    benchmark: tuple[float, ...]
    excess: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class _MetricEventCounts:
    """Counts derived only from one exact metric event-ID partition."""

    metric: str
    generated: int
    emitted: int
    refusal_total: int
    coverage_successes: int
    lower_tail_misses: int
    upper_tail_misses: int
    joint_successes: int


@dataclass(frozen=True, slots=True)
class _Deadline:
    """One monotonic budget shared by preflight, generation, verification and sealing."""

    started_at: float
    duration_seconds: float
    clock: Callable[[], float]

    def remaining(self) -> float:
        remaining = self.duration_seconds - (self.clock() - self.started_at)
        if not math.isfinite(remaining) or remaining <= 0.0:
            raise ManifestError("counted phase deadline expired")
        return remaining


@dataclass(frozen=True, slots=True)
class _ReviewAttestation:
    reviewed_commit: str
    reviewed_tree: str
    protected_blobs: dict[str, str]
    review_record_path: str
    attestation_path: str
    allowed_intervening_paths: tuple[str, ...]
    reviewed_at_utc: str
    raw_sha256: str


@dataclass(frozen=True, slots=True)
class _InvocationProof:
    reviewed_commit: str
    invocation_commit: str
    protected_blobs: dict[str, str]


@dataclass(frozen=True, slots=True)
class _ResourcePolicy:
    address_space_limit_bytes: int
    ops: Any
    deadline: _Deadline


@dataclass(slots=True)
class _ResourceBoundary:
    policy: _ResourcePolicy
    current_vms_bytes: int
    current_rss_bytes: int
    peak_rss_bytes: int
    peak_rss_source: str = "getrusage-ru_maxrss-kib"
    resource_backend: str = "linux-rlimit-as"

    @property
    def address_space_limit_bytes(self) -> int:
        return self.policy.address_space_limit_bytes

    @property
    def deadline(self) -> _Deadline:
        return self.policy.deadline

    def _measure(self) -> tuple[int, int, int]:
        self.deadline.remaining()
        current_vms = self.policy.ops.current_vms_bytes()
        current_rss = self.policy.ops.current_rss_bytes()
        peak = self.policy.ops.peak_rss_bytes()
        limit = self.address_space_limit_bytes
        if (
            type(current_vms) is not int
            or type(current_rss) is not int
            or type(peak) is not int
            or current_vms < 0
            or current_rss < 0
            or peak < 0
            or current_vms > limit
            or current_rss > limit
            or peak > limit
        ):
            raise ManifestError("current VMS, current RSS or peak RSS is invalid or over limit")
        self.current_vms_bytes = current_vms
        self.current_rss_bytes = current_rss
        self.peak_rss_bytes = max(self.peak_rss_bytes, peak)
        return current_vms, current_rss, peak

    def check_planned_allocation(self, planned_bytes: int) -> None:
        if type(planned_bytes) is not int or planned_bytes < 0:
            raise ManifestError("planned allocation must be non-negative integer bytes")
        current_vms, current_rss, _ = self._measure()
        limit = self.address_space_limit_bytes
        if planned_bytes > limit - current_rss:
            raise ManifestError("current RSS plus planned allocation exceeds budget")
        if planned_bytes > limit - current_vms:
            raise ManifestError("planned allocation exceeds address-space budget")

    def check_verifier_projection(self, result_size_bytes: int) -> int:
        if type(result_size_bytes) is not int or result_size_bytes < 0:
            raise ManifestError("result size must be non-negative integer bytes")
        current_vms, _, _ = self._measure()
        total = current_vms + 32 * result_size_bytes + 64 * 1024**2
        if total > self.address_space_limit_bytes:
            raise ManifestError("result verifier projection exceeds address-space budget")
        return total

    def maximum_result_bytes(self) -> int:
        current_vms, _, _ = self._measure()
        available = max(0, self.address_space_limit_bytes - current_vms - 64 * 1024**2)
        return available // 32

    def check_result_write(self, projected_result_size_bytes: int) -> None:
        if type(projected_result_size_bytes) is not int or projected_result_size_bytes < 0:
            raise ManifestError("result write size must be non-negative integer bytes")
        if projected_result_size_bytes > self.maximum_result_bytes():
            raise ManifestError("result write exceeds verifier budget")

    def sample_peak_rss(self) -> int:
        self._measure()
        return self.peak_rss_bytes


@dataclass(frozen=True, slots=True)
class _ArtifactPaths:
    directory: str
    claim_name: str
    result_name: str
    seal_name: str

    def as_claim_record(self) -> dict[str, str]:
        return {
            "claim": f"{self.directory}/{self.claim_name}",
            "result": f"{self.directory}/{self.result_name}",
            "seal": f"{self.directory}/{self.seal_name}",
        }


@dataclass(frozen=True, slots=True)
class _EvidenceFile:
    name: str
    fd: int
    device: int
    inode: int


@dataclass(frozen=True, slots=True)
class _DirectoryHandle:
    path: Path
    fd: int
    device: int
    inode: int


@dataclass(slots=True)
class _EvidenceDirectory:
    handles: tuple[_DirectoryHandle, ...]
    ops: Any
    deadline: _Deadline

    @property
    def path(self) -> Path:
        return self.handles[-1].path

    @property
    def fd(self) -> int:
        return self.handles[-1].fd

    def recheck(self) -> None:
        self.deadline.remaining()
        try:
            for handle in self.handles:
                opened = self.ops.fstat(handle.fd)
                named = self.ops.stat_path(handle.path)
                if (
                    not stat.S_ISDIR(opened.st_mode)
                    or not stat.S_ISDIR(named.st_mode)
                    or (opened.st_dev, opened.st_ino) != (handle.device, handle.inode)
                    or (named.st_dev, named.st_ino) != (handle.device, handle.inode)
                ):
                    raise ManifestError("evidence directory identity changed")
        except OSError as exc:
            raise ManifestError(f"evidence directory identity check failed: {exc}") from exc


_PHASE_CONTEXT_ISSUER: Final = object()


def _phase_context_binding_bytes(
    phase: str,
    paths: _ArtifactPaths,
    review: _ReviewAttestation,
    proof: _InvocationProof,
    resources: _ResourceBoundary,
    claim_sha256: str,
    started_at_utc: str,
) -> bytes:
    return _canonical_bytes(
        {
            "claim_sha256": claim_sha256,
            "phase": phase,
            "paths": paths.as_claim_record(),
            "proof": {
                "invocation_commit": proof.invocation_commit,
                "protected_blobs": dict(proof.protected_blobs),
                "reviewed_commit": proof.reviewed_commit,
            },
            "resources": {
                "address_space_limit_bytes": resources.address_space_limit_bytes,
                "deadline_duration_seconds": resources.deadline.duration_seconds,
                "deadline_started_at": resources.deadline.started_at,
            },
            "review": {
                "allowed_intervening_paths": list(review.allowed_intervening_paths),
                "attestation_path": review.attestation_path,
                "protected_blobs": dict(review.protected_blobs),
                "raw_sha256": review.raw_sha256,
                "review_record_path": review.review_record_path,
                "reviewed_at_utc": review.reviewed_at_utc,
                "reviewed_commit": review.reviewed_commit,
                "reviewed_tree": review.reviewed_tree,
            },
            "started_at_utc": started_at_utc,
        }
    )


@dataclass(frozen=True, slots=True)
class _PhaseContext:
    phase: str
    paths: _ArtifactPaths
    review: _ReviewAttestation
    proof: _InvocationProof
    resources: _ResourceBoundary
    store: _EvidenceDirectory
    claim_file: _EvidenceFile
    result_file: _EvidenceFile
    claim_sha256: str
    claim_bytes: bytes
    started_at_utc: str
    bound_identity_bytes: bytes
    issuer: object
    closed: bool = False
    provider_issued: bool = False

    def __post_init__(self) -> None:
        if self.issuer is not _PHASE_CONTEXT_ISSUER:
            raise ManifestError("phase context was not issued by the counted controller")
        current = _phase_context_binding_bytes(
            self.phase,
            self.paths,
            self.review,
            self.proof,
            self.resources,
            self.claim_sha256,
            self.started_at_utc,
        )
        if not hmac.compare_digest(current, self.bound_identity_bytes):
            raise ManifestError("phase context binding is invalid at issuance")

    def require_active(self, phase: str) -> None:
        if self.closed:
            raise ManifestError("phase context is closed")
        try:
            current_binding = _phase_context_binding_bytes(
                self.phase,
                self.paths,
                self.review,
                self.proof,
                self.resources,
                self.claim_sha256,
                self.started_at_utc,
            )
            if not hmac.compare_digest(current_binding, self.bound_identity_bytes):
                raise ManifestError("phase context binding changed")
            if phase != self.phase:
                raise ManifestError("phase context has the wrong phase")
            self.store.recheck()
            claim = _check_evidence_file(self.store, self.claim_file.name, self.claim_file.fd)
            result = _check_evidence_file(self.store, self.result_file.name, self.result_file.fd)
            if (claim.device, claim.inode) != (self.claim_file.device, self.claim_file.inode) or (
                result.device,
                result.inode,
            ) != (self.result_file.device, self.result_file.inode):
                raise ManifestError("phase evidence identity differs from original binding")
            try:
                current_claim = self.store.ops.read_all(self.claim_file.fd)
            except OSError as read_exc:
                raise ManifestError(f"claim bytes could not be reread: {read_exc}") from read_exc
            if not hmac.compare_digest(current_claim, self.claim_bytes):
                raise ManifestError("claim bytes differ from original binding")
            self.resources.sample_peak_rss()
        except BaseException as exc:
            try:
                self.close()
            except ManifestError as close_exc:
                raise close_exc from exc
            raise

    def close(self) -> None:
        if self.closed:
            return
        object.__setattr__(self, "closed", True)
        failures: list[str] = []
        for file in (self.result_file, self.claim_file):
            try:
                self.store.ops.close(file.fd)
            except OSError as exc:
                failures.append(str(exc))
        for handle in reversed(self.store.handles):
            try:
                self.store.ops.close(handle.fd)
            except OSError as exc:
                failures.append(str(exc))
        if failures:
            raise ManifestError(f"phase context close failed: {failures}")


def parity_audit_ids(replicates: int) -> tuple[int, ...]:
    """Return the 128 fixed parity addresses without consuming any random stream."""
    if type(replicates) is not int or replicates < 2:
        raise ValueError("replicates must be an integer of at least two")
    return tuple(index * (replicates - 1) // 127 for index in range(128))


def evaluate_batch_interval(
    values: NDArray[np.float64],
    block_ids: NDArray[np.int64],
    *,
    confidence: float = 0.95,
    is_win_rate: bool = False,
) -> BatchInterval | BatchRefusal:
    """Evaluate the frozen intercept-only CR2/t candidate on one offline vector."""
    if values.ndim != 1 or block_ids.ndim != 1 or values.size != block_ids.size:
        raise ValueError("values and block_ids must be equal-length one-dimensional arrays")
    if not 0.0 < confidence < 1.0:
        raise ValueError("confidence must lie strictly between zero and one")
    if values.size == 0:
        return BatchRefusal.EMPTY_SAMPLE
    values = values.astype(float, copy=False)
    if not np.isfinite(values).all():
        raise ValueError("batch values must be finite floats")
    if not np.isfinite(block_ids).all():
        raise ValueError("batch block IDs must be finite whole integers")
    if not np.equal(block_ids, np.floor(block_ids)).all():
        raise TypeError("batch block IDs must be whole integers")
    unique_blocks, inverse, counts = np.unique(block_ids, return_inverse=True, return_counts=True)
    count = values.size
    if count < 2 or unique_blocks.size < 2:
        return BatchRefusal.TOO_FEW_BLOCKS
    try:
        mean = math.fsum(float(value) for value in values) / count
        residuals = values - mean
        sample_variance = math.fsum(float(residual * residual) for residual in residuals) / (
            count - 1
        )
    except OverflowError:
        return BatchRefusal.INVALID_VARIANCE
    if not math.isfinite(sample_variance) or sample_variance < 0.0:
        return BatchRefusal.INVALID_VARIANCE
    if sample_variance == 0.0:
        return (
            BatchRefusal.ZERO_VARIANCE
            if np.all(values == values[0])
            else BatchRefusal.INVALID_VARIANCE
        )
    leverage = counts / count
    if np.any(leverage >= 1.0):
        return BatchRefusal.TOO_FEW_BLOCKS
    try:
        scores = np.array(
            [
                math.fsum(float(residual) for residual in residuals[inverse == index])
                for index in range(unique_blocks.size)
            ]
        )
        variance = math.fsum(
            float(score * score / (1.0 - item_leverage))
            for score, item_leverage in zip(scores, leverage, strict=True)
        ) / (count * count)
    except OverflowError:
        return BatchRefusal.INVALID_VARIANCE
    if not math.isfinite(variance) or variance < 0.0:
        return BatchRefusal.INVALID_VARIANCE
    if variance == 0.0:
        return (
            BatchRefusal.ZERO_VARIANCE if np.all(scores == 0.0) else BatchRefusal.INVALID_VARIANCE
        )
    occupancy = tuple(
        (int(block), int(size)) for block, size in zip(unique_blocks, counts, strict=True)
    )
    cache_key = (METHOD_VERSION, occupancy)
    degrees_of_freedom = _NU_CACHE.get(cache_key)
    if degrees_of_freedom is None:
        numerator = np.diag(counts.astype(float)) - np.outer(counts, counts) / count
        denominator = count * count * np.sqrt(np.outer(1.0 - leverage, 1.0 - leverage))
        kernel = numerator / denominator
        trace = float(np.trace(kernel))
        trace_squared = float(np.sum(kernel * kernel))
        if not math.isfinite(trace_squared) or trace_squared <= 0.0:
            return BatchRefusal.INVALID_DF
        degrees_of_freedom = trace * trace / trace_squared
        if not math.isfinite(degrees_of_freedom) or degrees_of_freedom <= 0.0:
            return BatchRefusal.INVALID_DF
        _NU_CACHE[cache_key] = degrees_of_freedom
    iid_variance = sample_variance / count
    if not math.isfinite(iid_variance) or iid_variance <= 0.0:
        return BatchRefusal.INVALID_VARIANCE
    design_effect = variance / iid_variance
    effective_n = sample_variance / variance
    if (
        not math.isfinite(design_effect)
        or design_effect <= 0.0
        or not math.isfinite(effective_n)
        or effective_n <= 0.0
    ):
        return BatchRefusal.INVALID_VARIANCE
    critical = float(t.ppf(1.0 - (1.0 - confidence) / 2.0, degrees_of_freedom))
    margin = critical * math.sqrt(variance)
    if not math.isfinite(critical) or not math.isfinite(margin):
        return BatchRefusal.INVALID_DF
    raw_lower = mean - margin
    raw_upper = mean + margin
    lower, upper = raw_lower, raw_upper
    if is_win_rate:
        lower, upper = max(0.0, lower), min(1.0, upper)
    return BatchInterval(
        mean=mean,
        variance=variance,
        degrees_of_freedom=degrees_of_freedom,
        raw_lower=raw_lower,
        raw_upper=raw_upper,
        lower=lower,
        upper=upper,
    )


def _test_or_rng(
    seed: int, cell_id: int, component_id: int, replicate_id: int, size: int, rows: int
) -> NDArray[np.float64]:
    """Slice a once-generated PCG64 normal component chunk at its addressed row."""
    if seed in _RESERVED_PHASE_SEEDS:
        raise ValueError("reserved phase seeds cannot generate Task 2 fixtures")
    if type(seed) is not int or type(cell_id) is not int or type(replicate_id) is not int:
        raise TypeError("synthetic stream addresses must be whole integers")
    if replicate_id < 0 or size < 1 or not 1 <= rows <= 256:
        raise ValueError("synthetic stream dimensions are invalid")
    chunk_id, offset = divmod(replicate_id, 256)
    if offset >= rows:
        raise ValueError("replicate lies outside its declared chunk remainder")
    cache_key = (seed, cell_id, component_id, chunk_id, size, "normal")
    draws = _STREAM_CACHE.get(cache_key)
    if draws is None:
        generator = np.random.Generator(
            np.random.PCG64(
                np.random.SeedSequence(seed, spawn_key=(cell_id, component_id, chunk_id))
            )
        )
        draws = cast(NDArray[np.float64], generator.standard_normal((rows, size)))
        _STREAM_CACHE[cache_key] = draws
        if len(_STREAM_CACHE) > _MAX_CACHED_COMPONENT_CHUNKS:
            _STREAM_CACHE.popitem(last=False)
    else:
        _STREAM_CACHE.move_to_end(cache_key)
    return cast(NDArray[np.float64], draws[offset].copy())


def _uniform_component_draw(
    seed: int, cell_id: int, component_id: int, replicate_id: int, size: int, rows: int
) -> NDArray[np.float64]:
    """Slice a once-generated PCG64 uniform component chunk for amplitudes."""
    if seed in _RESERVED_PHASE_SEEDS:
        raise ValueError("reserved phase seeds cannot generate Task 2 fixtures")
    if replicate_id < 0 or size < 1 or not 1 <= rows <= 256:
        raise ValueError("synthetic stream dimensions are invalid")
    chunk_id, offset = divmod(replicate_id, 256)
    if offset >= rows:
        raise ValueError("replicate lies outside its declared chunk remainder")
    cache_key = (seed, cell_id, component_id, chunk_id, size, "uniform")
    draws = _STREAM_CACHE.get(cache_key)
    if draws is None:
        generator = np.random.Generator(
            np.random.PCG64(
                np.random.SeedSequence(seed, spawn_key=(cell_id, component_id, chunk_id))
            )
        )
        draws = cast(NDArray[np.float64], generator.uniform(0.0, 1.0, (rows, size)))
        _STREAM_CACHE[cache_key] = draws
        if len(_STREAM_CACHE) > _MAX_CACHED_COMPONENT_CHUNKS:
            _STREAM_CACHE.popitem(last=False)
    else:
        _STREAM_CACHE.move_to_end(cache_key)
    return cast(NDArray[np.float64], draws[offset].copy())


def _cell_for_phase(manifest: Mapping[str, Any], phase: str, cell_id: int) -> dict[str, Any]:
    if phase not in {"calibration", "validation"}:
        raise ValueError("phase must be calibration or validation")
    phase_payload = _mapping(manifest["phases"][phase], f"phases.{phase}")
    for cell in _sequence(phase_payload["cells"], f"phases.{phase}.cells"):
        if isinstance(cell, dict) and cell.get("id") == cell_id:
            return cell
    raise ManifestError(f"unknown {phase} cell id: {cell_id}")


def _fixed_entry_indices(
    manifest: Mapping[str, Any], cell: Mapping[str, Any]
) -> tuple[list[int], int]:
    geometry = _mapping(manifest["geometries"][cell["geometry_id"]], "geometry")
    block_length = int(geometry["l"])
    entries: list[int] = []
    for block, count in enumerate(geometry["entry_counts"]):
        if geometry["entry_rule"] == "ordinary":
            entries.extend(
                block * block_length + math.floor((index + 0.5) * block_length / count)
                for index in range(count)
            )
        elif geometry["entry_rule"] == "burst":
            location = cell["parameters"]["location"]
            offset = {"first": 0, "middle": block_length // 2, "last": block_length - 1}[location]
            entries.extend([block * block_length + offset] * count)
        else:
            offsets = (
                (range(4), range(block_length - 4, block_length))
                if count == 8
                else (range(5), range(block_length - 5, block_length))
            )
            entries.extend(block * block_length + offset for span in offsets for offset in span)
    return entries, block_length


def _generate_replicate_core(
    manifest: Mapping[str, Any],
    *,
    phase: str,
    cell_id: int,
    replicate_id: int,
    draw_normal: Callable[[int, int, int, int], NDArray[np.float64]],
    draw_uniform: Callable[[int, int, int, int], NDArray[np.float64]],
    scripted_latents: NDArray[np.float64] | None = None,
    scripted_amplitudes: NDArray[np.float64] | None = None,
    scripted_factors: NDArray[np.float64] | None = None,
    scripted_wins: NDArray[np.bool_] | None = None,
    scripted_daily_innovations: NDArray[np.float64] | None = None,
) -> SyntheticReplicate:
    """Apply the frozen equations to one replicate supplied by an authorized draw boundary."""
    cell = _cell_for_phase(manifest, phase, cell_id)
    phase_payload = _mapping(manifest["phases"][phase], f"phases.{phase}")
    phase_replicates = int(phase_payload["replicates"])
    if not 0 <= replicate_id < phase_replicates:
        raise ValueError("replicate_id lies outside the frozen phase range")
    chunk_id, _ = divmod(replicate_id, 256)
    chunk_rows = min(256, phase_replicates - chunk_id * 256)
    parameters = _mapping(cell["parameters"], "cell parameters")
    family = str(cell["family"])
    dynamic = family == "dynamic_h_block_factor"
    if dynamic:
        nominal_length = int(parameters["nominal_l"])
        count_blocks = int(parameters["source_span"]) // nominal_length
        per_block = int(parameters["trades_per_nominal_block"])
        entries = [
            block * nominal_length + math.floor((index + 0.5) * nominal_length / per_block)
            for block in range(count_blocks)
            for index in range(per_block)
        ]
    else:
        entries, nominal_length = _fixed_entry_indices(manifest, cell)
    count = len(entries)
    source_blocks = np.array([entry // nominal_length for entry in entries], dtype=np.int64)
    block_count = int(source_blocks.max()) + 1
    raw_latents = (
        draw_normal(0, replicate_id, count, chunk_rows)
        if family != "overlapping_holds"
        else np.zeros(count)
    )
    amplitudes = draw_uniform(2, replicate_id, count, chunk_rows)
    if family in {
        "bounded_rare_magnitude",
        "cross_block_serial_factor",
        "dynamic_h_block_factor",
        "independent_block_factor",
        "same_session_burst",
        "two_regime_shift",
        "unequal_occupancy",
    }:
        factors = draw_normal(1, replicate_id, block_count, chunk_rows)
    else:
        factors = np.zeros(block_count)
    if family == "independent":
        benchmark_factors = draw_normal(3, replicate_id, block_count, chunk_rows)
    else:
        benchmark_factors = np.zeros(block_count)
    if scripted_latents is not None:
        raw_latents[: min(count, scripted_latents.size)] = scripted_latents[:count]
    if scripted_factors is not None:
        factors[: min(count, scripted_factors.size)] = scripted_factors[:count]
    if scripted_amplitudes is not None:
        amplitudes[: min(count, scripted_amplitudes.size)] = scripted_amplitudes[:count]
    if family == "independent":
        latent = raw_latents
        factor = benchmark_factors[source_blocks]
    elif family == "cross_block_serial_factor":
        rho = float(parameters["rho"])
        block_factor = np.empty(source_blocks.max() + 1)
        block_factor[0] = factors[0]
        for block in range(1, block_factor.size):
            block_factor[block] = (
                rho * block_factor[block - 1] + math.sqrt(1.0 - rho * rho) * factors[block]
            )
        factor = block_factor[source_blocks]
        latent = math.sqrt(0.5) * factor + math.sqrt(0.5) * raw_latents
    elif family == "same_session_burst":
        factor = factors[source_blocks]
        latent = math.sqrt(0.75) * factor + 0.5 * raw_latents
    elif family == "overlapping_holds":
        holding = int(parameters["h"])
        daily = draw_normal(4, replicate_id, max(entries) + holding, chunk_rows)
        if scripted_daily_innovations is not None:
            daily[: min(daily.size, scripted_daily_innovations.size)] = scripted_daily_innovations[
                : daily.size
            ]
        factor = np.array(
            [np.sum(daily[entry : entry + holding]) / math.sqrt(holding) for entry in entries]
        )
        latent = factor
    else:
        rho = float(parameters.get("rho", 0.25))
        block_factor = factors[source_blocks]
        factor = block_factor
        latent = math.sqrt(rho) * factor + math.sqrt(1.0 - rho) * raw_latents
    if scripted_latents is not None:
        latent[: min(count, scripted_latents.size)] = scripted_latents[:count]
    if family == "two_regime_shift":
        probabilities = np.where(
            source_blocks < (source_blocks.max() + 1) // 2,
            float(parameters["p_first"]),
            float(parameters["p_last"]),
        )
    else:
        probabilities = np.full(count, float(parameters["p"]))
    wins = latent > norm.ppf(1.0 - probabilities)
    if scripted_wins is not None:
        if scripted_wins.size != count:
            raise ValueError("scripted_wins must cover the complete synthetic vector")
        wins = scripted_wins.astype(bool, copy=False)
    if family == "bounded_rare_magnitude":
        threshold = float(parameters["amplitude_high_probability"])
        high = float(parameters["amplitude_high"])
        amplitude = np.where(amplitudes < threshold, high, 1.0)
    else:
        amplitude = 0.5 + amplitudes
    if scripted_amplitudes is not None:
        amplitude[: min(count, scripted_amplitudes.size)] = scripted_amplitudes[:count]
    fixed_h = parameters.get("h")
    if isinstance(fixed_h, int):
        holding_sessions = np.full(count, fixed_h, dtype=np.int64)
    elif family == "dynamic_h_block_factor":
        holding_sessions = np.where(wins, int(parameters["h_win"]), int(parameters["h_loss"]))
    else:
        holding_sessions = np.full(count, 21, dtype=np.int64)
    block_length = max(63, 3 * int(holding_sessions.max()))
    blocks = np.array(entries) // block_length
    raw = 0.01 * amplitude * (2.0 * wins.astype(float) - 1.0)
    benchmark = 0.002 + 0.005 * factor
    excess = raw - benchmark
    return SyntheticReplicate(
        entry_indices=tuple(entries),
        holding_sessions=tuple(int(item) for item in holding_sessions),
        block_ids=tuple(int(item) for item in blocks),
        block_length=block_length,
        wins=tuple(bool(item) for item in wins),
        raw=tuple(float(item) for item in raw),
        benchmark=tuple(float(item) for item in benchmark),
        excess=tuple(float(item) for item in excess),
    )


def generate_test_fixture_replicate(
    manifest: Mapping[str, Any],
    *,
    phase: str,
    cell_id: int,
    replicate_id: int,
    scripted_latents: NDArray[np.float64] | None = None,
    scripted_amplitudes: NDArray[np.float64] | None = None,
    scripted_factors: NDArray[np.float64] | None = None,
    scripted_wins: NDArray[np.bool_] | None = None,
    scripted_daily_innovations: NDArray[np.float64] | None = None,
) -> SyntheticReplicate:
    """Generate one artificial paired vector with the fixed Task 2 fixture seed."""

    def draw_normal(
        component_id: int, addressed_replicate: int, size: int, rows: int
    ) -> NDArray[np.float64]:
        return _test_or_rng(
            _TEST_FIXTURE_SEED,
            cell_id,
            component_id,
            addressed_replicate,
            size,
            rows,
        )

    def draw_uniform(
        component_id: int, addressed_replicate: int, size: int, rows: int
    ) -> NDArray[np.float64]:
        return _uniform_component_draw(
            _TEST_FIXTURE_SEED,
            cell_id,
            component_id,
            addressed_replicate,
            size,
            rows,
        )

    return _generate_replicate_core(
        manifest,
        phase=phase,
        cell_id=cell_id,
        replicate_id=replicate_id,
        draw_normal=draw_normal,
        draw_uniform=draw_uniform,
        scripted_latents=scripted_latents,
        scripted_amplitudes=scripted_amplitudes,
        scripted_factors=scripted_factors,
        scripted_wins=scripted_wins,
        scripted_daily_innovations=scripted_daily_innovations,
    )


def generate_test_fixture_chunk(
    manifest: Mapping[str, Any],
    *,
    phase: str,
    cell_id: int,
    chunk_id: int,
    rows: int,
) -> tuple[SyntheticReplicate, ...]:
    """Generate a declared chunk by slicing its cached component arrays in row order."""
    if type(chunk_id) is not int or chunk_id < 0 or not 1 <= rows <= 256:
        raise ValueError("chunk_id and rows must name a nonempty declared chunk")
    phase_payload = _mapping(manifest["phases"][phase], f"phases.{phase}")
    phase_replicates = int(phase_payload["replicates"])
    start = chunk_id * 256
    expected_rows = min(256, phase_replicates - start)
    if expected_rows <= 0 or rows != expected_rows:
        raise ValueError("rows must equal the declared chunk size or final remainder")
    return tuple(
        generate_test_fixture_replicate(
            manifest,
            phase=phase,
            cell_id=cell_id,
            replicate_id=start + offset,
        )
        for offset in range(rows)
    )


@dataclass(frozen=True, slots=True)
class _CountedChunk:
    cell_id: int
    chunk_id: int
    replicate_start: int
    replicate_stop_exclusive: int
    replicates: tuple[SyntheticReplicate, ...]


def _counted_component_shapes(
    manifest: Mapping[str, Any], cell: Mapping[str, Any]
) -> tuple[tuple[str, int, int], ...]:
    """Derive the exact frozen distribution, component, and row width before a draw."""

    family = str(cell["family"])
    parameters = _mapping(cell["parameters"], "cell parameters")
    if family == "dynamic_h_block_factor":
        nominal_length = int(parameters["nominal_l"])
        block_count = int(parameters["source_span"]) // nominal_length
        count = block_count * int(parameters["trades_per_nominal_block"])
        daily_size = 0
    else:
        entries, nominal_length = _fixed_entry_indices(manifest, cell)
        count = len(entries)
        block_count = max(entry // nominal_length for entry in entries) + 1
        daily_size = max(entries) + int(parameters.get("h", 0))
    if family == "overlapping_holds":
        return (("uniform", 2, count), ("normal", 4, daily_size))
    if family == "independent":
        return (("normal", 0, count), ("uniform", 2, count), ("normal", 3, block_count))
    return (("normal", 0, count), ("uniform", 2, count), ("normal", 1, block_count))


def _counted_chunk_memory_bound(
    manifest: Mapping[str, Any], cell: Mapping[str, Any], rows: int
) -> int:
    """Conservatively bound cached arrays, transforms, and Python result objects."""

    family = str(cell["family"])
    parameters = _mapping(cell["parameters"], "cell parameters")
    if family == "dynamic_h_block_factor":
        nominal_length = int(parameters["nominal_l"])
        nominal_blocks = int(parameters["source_span"]) // nominal_length
        count = nominal_blocks * int(parameters["trades_per_nominal_block"])
        source_span = int(parameters["source_span"])
        block_count = nominal_blocks
        maximum_h = max(int(parameters["h_loss"]), int(parameters["h_win"]))
    else:
        geometry = _mapping(manifest["geometries"][cell["geometry_id"]], "geometry")
        entry_counts = _sequence(geometry["entry_counts"], "geometry.entry_counts")
        count = sum(int(value) for value in entry_counts)
        source_span = len(entry_counts) * int(geometry["l"])
        block_count = len(entry_counts)
        maximum_h = int(parameters.get("h", 21))
    component_elements = count  # amplitudes
    if family != "overlapping_holds":
        component_elements += count
    if family in {
        "bounded_rare_magnitude",
        "cross_block_serial_factor",
        "dynamic_h_block_factor",
        "independent_block_factor",
        "same_session_burst",
        "two_regime_shift",
        "unequal_occupancy",
    }:
        component_elements += block_count
    if family == "independent":
        component_elements += block_count
    if family == "overlapping_holds":
        component_elements += source_span + maximum_h
    cached_arrays = rows * component_elements * 8
    # Eight output/source tuples can hold Python scalar objects and pointers. 512 bytes per
    # observation plus 4 KiB per replicate also covers temporary NumPy transforms.
    retained_replicates = rows * (count * 512 + 4096)
    return cached_arrays + retained_replicates


class _CountedChunkProvider:
    """One-shot authenticated iterator over the frozen phase topology."""

    def __init__(self, context: _PhaseContext, manifest: dict[str, Any]) -> None:
        self._component_cache: dict[
            tuple[str, str, int, int, int, int, int, int], NDArray[np.float64]
        ] = {}
        self._failed = False
        self._exhausted = False
        self._cell_index = 0
        self._chunk_id = 0
        self._planned_chunk_bytes = 0
        self._active_replicate: int | None = None
        self._active_cell_id: int | None = None
        self._active_rows = 0
        self._active_components: tuple[tuple[str, int, int], ...] = ()
        self._active_component_index = 0
        if type(context) is not _PhaseContext or context.issuer is not _PHASE_CONTEXT_ISSUER:
            raise ManifestError("counted provider context was not issued by the counted controller")
        self._context = context
        try:
            context.require_active(context.phase)
            if context.provider_issued:
                raise ManifestError("phase context already issued its counted provider")
            object.__setattr__(context, "provider_issued", True)
            if context.phase not in {"calibration", "validation"}:
                raise ManifestError("counted provider context has an invalid phase")
            _validate_manifest(manifest)
            self._manifest_bytes = _canonical_bytes(_mapping(manifest, "manifest"))
            manifest_sha = hashlib.sha256(self._manifest_bytes).hexdigest()
            snapshot = _parse_canonical_json_bytes(
                self._manifest_bytes, label="counted provider manifest"
            )
            manifest_path = str(
                _mapping(
                    _mapping(snapshot["integrity"], "integrity")["protected_paths"],
                    "integrity.protected_paths",
                )["manifest"]
            )
            claim = _parse_canonical_json_bytes(context.claim_bytes, label="phase claim")
            if (
                claim.get("manifest_sha256") != manifest_sha
                or claim.get("phase") != context.phase
                or claim.get("protocol_version") != PROTOCOL_VERSION
                or context.proof.protected_blobs.get(manifest_path) != manifest_sha
                or context.review.protected_blobs.get(manifest_path) != manifest_sha
            ):
                raise ManifestError("counted provider manifest differs from authenticated context")
            self._phase = context.phase
            self._snapshot = snapshot
            phase_payload = _mapping(
                _mapping(snapshot["phases"], "phases")[self._phase],
                f"phases.{self._phase}",
            )
            self._phase_seed = int(phase_payload["master_seed"])
            self._replicate_count = int(phase_payload["replicates"])
            self._cells = _sequence(phase_payload["cells"], f"phases.{self._phase}.cells")
            self._cell_count = len(self._cells)
        except BaseException as exc:
            self._fail(exc)

    def __iter__(self) -> _CountedChunkProvider:
        return self

    def __next__(self) -> _CountedChunk:
        if self._failed:
            raise ManifestError("counted provider is permanently closed after failure")
        if self._exhausted:
            raise StopIteration
        if self._cell_index == self._cell_count:
            self._component_cache.clear()
            self._exhausted = True
            raise StopIteration
        try:
            self._authenticate()
            cell = _mapping(self._cells[self._cell_index], "counted provider cell")
            start = self._chunk_id * 256
            rows = min(256, self._replicate_count - start)
            if rows <= 0:
                raise ManifestError("counted provider topology exceeded the frozen phase")
            self._planned_chunk_bytes = _counted_chunk_memory_bound(self._snapshot, cell, rows)
            self._context.resources.check_planned_allocation(self._planned_chunk_bytes)
            generated: list[SyntheticReplicate] = []
            cell_id = int(cell["id"])
            components = _counted_component_shapes(self._snapshot, cell)
            self._active_cell_id = cell_id
            self._active_rows = rows
            self._active_components = components
            for replicate_id in range(start, start + rows):
                self._authenticate()
                self._active_replicate = replicate_id
                self._active_component_index = 0
                generated.append(
                    _generate_replicate_core(
                        self._snapshot,
                        phase=self._phase,
                        cell_id=cell_id,
                        replicate_id=replicate_id,
                        draw_normal=self._draw_normal,
                        draw_uniform=self._draw_uniform,
                    )
                )
                if self._active_component_index != len(self._active_components):
                    raise ManifestError("counted equation core omitted a frozen component draw")
            self._active_replicate = None
            self._authenticate()
            self._context.resources.sample_peak_rss()
            chunk = _CountedChunk(
                cell_id,
                self._chunk_id,
                start,
                start + rows,
                tuple(generated),
            )
            self._component_cache.clear()
            self._active_cell_id = None
            self._active_rows = 0
            self._active_components = ()
            if start + rows == self._replicate_count:
                self._cell_index += 1
                self._chunk_id = 0
            else:
                self._chunk_id += 1
            return chunk
        except BaseException as exc:
            self._fail(exc)

    def _authenticate(self) -> None:
        self._context.require_active(self._phase)

    def _draw_normal(
        self, component_id: int, replicate_id: int, size: int, rows: int
    ) -> NDArray[np.float64]:
        return self._draw_component("normal", component_id, replicate_id, size, rows)

    def _draw_uniform(
        self, component_id: int, replicate_id: int, size: int, rows: int
    ) -> NDArray[np.float64]:
        return self._draw_component("uniform", component_id, replicate_id, size, rows)

    def _draw_component(
        self, distribution: str, component_id: int, replicate_id: int, size: int, rows: int
    ) -> NDArray[np.float64]:
        if self._failed:
            raise ManifestError("counted provider is permanently closed after failure")
        if self._active_replicate is None or self._active_cell_id is None:
            self._fail(ManifestError("counted draw used outside active generation"))
        cell_id = self._active_cell_id
        self._authenticate()
        chunk_id, offset = divmod(replicate_id, 256)
        expected = (
            self._active_components[self._active_component_index]
            if self._active_component_index < len(self._active_components)
            else None
        )
        if (
            replicate_id != self._active_replicate
            or chunk_id != self._chunk_id
            or not 0 <= offset < rows
            or rows != self._active_rows
            or size < 1
            or expected != (distribution, component_id, size)
        ):
            raise ManifestError("counted component address or order differs from frozen equations")
        seed = self._phase_seed
        key = (
            METHOD_VERSION,
            distribution,
            seed,
            cell_id,
            component_id,
            chunk_id,
            rows,
            size,
        )
        draws = self._component_cache.get(key)
        if draws is None:
            self._authenticate()
            self._context.resources.check_planned_allocation(self._planned_chunk_bytes)
            sequence = np.random.SeedSequence(seed, spawn_key=(cell_id, component_id, chunk_id))
            generator = np.random.Generator(np.random.PCG64(sequence))
            self._authenticate()
            if distribution == "normal":
                candidate = generator.standard_normal((rows, size))
            elif distribution == "uniform":
                candidate = generator.uniform(0.0, 1.0, (rows, size))
            else:
                raise ManifestError("counted component distribution is invalid")
            if (
                type(candidate) is not np.ndarray
                or candidate.dtype != np.float64
                or candidate.shape != (rows, size)
                or not np.isfinite(candidate).all()
            ):
                raise ManifestError("counted RNG returned an invalid component array")
            draws = cast(NDArray[np.float64], candidate)
            self._component_cache[key] = draws
            self._context.resources.sample_peak_rss()
        self._authenticate()
        self._context.resources.check_planned_allocation(self._planned_chunk_bytes)
        row = cast(NDArray[np.float64], draws[offset].copy())
        self._context.resources.sample_peak_rss()
        self._active_component_index += 1
        return row

    def _fail(self, exc: BaseException) -> NoReturn:
        if isinstance(exc, StopIteration):
            exc = ManifestError("counted equation core stopped before completing its chunk")
        self._component_cache.clear()
        self._active_replicate = None
        self._active_cell_id = None
        self._active_rows = 0
        self._active_components = ()
        self._failed = True
        try:
            self._context.close()
        except ManifestError as close_exc:
            raise close_exc from exc
        raise exc


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _parse_canonical_json_bytes(raw: bytes, *, label: str) -> dict[str, Any]:
    """Parse one canonical UTF-8 JSON object without accepting ambiguous encodings."""

    if type(raw) is not bytes:
        raise ManifestError(f"{label} must be UTF-8 JSON bytes")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ManifestError(f"{label} is not valid UTF-8 JSON") from exc

    def object_without_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ManifestError(f"{label} has a duplicate JSON key: {key}")
            result[key] = value
        return result

    def finite_float(value: str) -> float:
        parsed = float(value)
        if not math.isfinite(parsed):
            raise ManifestError(f"{label} contains a non-finite JSON number")
        return parsed

    def reject_constant(value: str) -> None:
        raise ManifestError(f"{label} contains a non-finite JSON constant: {value}")

    try:
        payload = json.loads(
            text,
            object_pairs_hook=object_without_duplicates,
            parse_float=finite_float,
            parse_constant=reject_constant,
        )
    except ManifestError:
        raise
    except RecursionError as exc:
        raise ManifestError(f"{label} JSON nesting is too deep") from exc
    except ValueError as exc:
        raise ManifestError(f"{label} is not valid JSON") from exc
    if not isinstance(payload, dict):
        raise ManifestError(f"{label} must be a JSON object")
    try:
        canonical = _canonical_bytes(payload)
    except UnicodeEncodeError as exc:
        raise ManifestError(f"{label} contains invalid Unicode in JSON") from exc
    except RecursionError as exc:
        raise ManifestError(f"{label} JSON nesting is too deep") from exc
    if raw != canonical:
        raise ManifestError(f"{label} is not canonical sorted UTF-8 JSON plus LF")
    return payload


def _mapping(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ManifestError(f"{label} must be an object with string keys")
    return value


def _sequence(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise ManifestError(f"{label} must be an array")
    return value


def _exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise ManifestError(f"{label} keys differ: missing={missing}, extra={extra}")


def _event_ids(
    value: object,
    *,
    label: str,
    replicate_start: int,
    replicate_stop_exclusive: int,
) -> tuple[int, ...]:
    raw_ids = _sequence(value, label)
    if any(type(replicate_id) is not int for replicate_id in raw_ids):
        raise ManifestError(f"{label} must contain integers excluding booleans")
    ids = cast(list[int], raw_ids)
    if any(
        replicate_id < replicate_start or replicate_id >= replicate_stop_exclusive
        for replicate_id in ids
    ):
        raise ManifestError(f"{label} contains an ID outside the replicate range")
    if any(ids[index] >= ids[index + 1] for index in range(len(ids) - 1)):
        raise ManifestError(f"{label} must be strictly increasing")
    return tuple(ids)


def _validate_metric_event_partition(
    manifest: Mapping[str, Any],
    value: object,
    *,
    replicate_start: int,
    replicate_stop_exclusive: int,
    declared_metric: str,
) -> _MetricEventCounts:
    """Validate only the non-parity fields of one metric event-ID partition."""

    if (
        type(replicate_start) is not int
        or type(replicate_stop_exclusive) is not int
        or replicate_start < 0
        or replicate_stop_exclusive <= replicate_start
    ):
        raise ManifestError("metric event replicate range must be nonempty non-negative integers")
    acceptance = _mapping(manifest["acceptance"], "acceptance")
    metrics = _sequence(acceptance["metrics"], "acceptance.metrics")
    if declared_metric not in metrics:
        raise ManifestError("declared metric is not frozen in the manifest")

    events = _mapping(value, "metric events")
    _exact_keys(
        events,
        {
            "metric",
            "emitted_ids",
            "refusals",
            "coverage_ids",
            "lower_miss_ids",
            "upper_miss_ids",
            "joint_success_ids",
        },
        "metric events",
    )
    if events["metric"] != declared_metric:
        raise ManifestError("metric events do not match the declared metric")

    emitted = _event_ids(
        events["emitted_ids"],
        label="emitted_ids",
        replicate_start=replicate_start,
        replicate_stop_exclusive=replicate_stop_exclusive,
    )
    frozen_reasons = _sequence(manifest["refusals"], "refusals")
    if any(not isinstance(reason, str) for reason in frozen_reasons) or len(
        set(frozen_reasons)
    ) != len(frozen_reasons):
        raise ManifestError("manifest refusal reasons must be unique strings")
    reason_order = {reason: index for index, reason in enumerate(frozen_reasons)}
    refusal_items = _sequence(events["refusals"], "metric events refusals")
    refusal_reasons: list[str] = []
    refused: list[int] = []
    for index, item in enumerate(refusal_items):
        refusal = _mapping(item, f"metric events refusals[{index}]")
        _exact_keys(refusal, {"reason", "ids"}, f"metric events refusals[{index}]")
        reason = refusal["reason"]
        if not isinstance(reason, str) or reason not in reason_order:
            raise ManifestError("metric events contain an unknown refusal reason")
        ids = _event_ids(
            refusal["ids"],
            label=f"metric events refusal {reason} ids",
            replicate_start=replicate_start,
            replicate_stop_exclusive=replicate_stop_exclusive,
        )
        if not ids:
            raise ManifestError("metric events refusal ID lists must not be empty")
        refusal_reasons.append(reason)
        refused.extend(ids)
    if len(set(refusal_reasons)) != len(refusal_reasons):
        raise ManifestError("metric events contain a duplicate refusal reason")
    if refusal_reasons != sorted(refusal_reasons, key=reason_order.__getitem__):
        raise ManifestError("metric events refusal reasons differ from manifest order")

    emitted_set = set(emitted)
    refused_set = set(refused)
    if len(refused_set) != len(refused) or emitted_set & refused_set:
        raise ManifestError("emitted and refusal ID lists must be disjoint")
    expected_ids = set(range(replicate_start, replicate_stop_exclusive))
    if emitted_set | refused_set != expected_ids:
        raise ManifestError("emitted and refusal ID lists must partition the replicate range")

    outcomes = {
        name: _event_ids(
            events[name],
            label=name,
            replicate_start=replicate_start,
            replicate_stop_exclusive=replicate_stop_exclusive,
        )
        for name in ("coverage_ids", "lower_miss_ids", "upper_miss_ids")
    }
    outcome_sets = [set(ids) for ids in outcomes.values()]
    if any(not outcome <= emitted_set for outcome in outcome_sets):
        raise ManifestError("outcome IDs must belong to emitted IDs")
    if sum(len(outcome) for outcome in outcome_sets) != len(set().union(*outcome_sets)):
        raise ManifestError("outcome ID lists must be disjoint")
    if set().union(*outcome_sets) != emitted_set:
        raise ManifestError("outcome ID lists must partition emitted IDs")

    joint = _event_ids(
        events["joint_success_ids"],
        label="joint_success_ids",
        replicate_start=replicate_start,
        replicate_stop_exclusive=replicate_stop_exclusive,
    )
    if joint != outcomes["coverage_ids"]:
        raise ManifestError("joint success IDs must exactly equal coverage IDs")
    return _MetricEventCounts(
        metric=declared_metric,
        generated=replicate_stop_exclusive - replicate_start,
        emitted=len(emitted),
        refusal_total=len(refused),
        coverage_successes=len(outcomes["coverage_ids"]),
        lower_tail_misses=len(outcomes["lower_miss_ids"]),
        upper_tail_misses=len(outcomes["upper_miss_ids"]),
        joint_successes=len(joint),
    )


def _floor_pairs(manifest: Mapping[str, Any]) -> tuple[tuple[int, float], ...]:
    raw = _sequence(manifest["candidate_floors"], "candidate_floors")
    pairs: list[tuple[int, float]] = []
    for index, item in enumerate(raw):
        floor = _mapping(item, f"candidate_floors[{index}]")
        _exact_keys(floor, {"minimum_blocks", "minimum_nu"}, f"candidate_floors[{index}]")
        blocks = floor["minimum_blocks"]
        minimum_nu = floor["minimum_nu"]
        if not isinstance(blocks, int) or not isinstance(minimum_nu, int | float):
            raise ManifestError("candidate floor values must be numeric")
        pairs.append((blocks, float(minimum_nu)))
    result = tuple(pairs)
    if result != _EXPECTED_FLOORS:
        raise ManifestError(f"candidate floor order differs: {result!r}")
    return result


def _ordered_occupancy(value: object, label: str) -> tuple[tuple[int, int], ...]:
    raw = _sequence(value, label)
    occupancy: list[tuple[int, int]] = []
    for index, item in enumerate(raw):
        pair = _sequence(item, f"{label}[{index}]")
        if len(pair) != 2 or not all(isinstance(part, int) for part in pair):
            raise ManifestError(f"{label}[{index}] must be [block_id,count]")
        block_id, count = pair
        if block_id != index or count <= 0:
            raise ManifestError(f"{label} must be a complete ordered positive occupancy tuple")
        occupancy.append((block_id, count))
    if not occupancy:
        raise ManifestError(f"{label} must not be empty")
    return tuple(occupancy)


def _derived_fixed_occupancy(
    entry_rule: object,
    block_length: object,
    entry_counts: object,
    source_geometry: Mapping[str, Any],
    burst_location: object | None = None,
) -> tuple[tuple[int, int], ...]:
    """Derive occupied estimator blocks from frozen source-entry rules."""
    if not isinstance(entry_rule, str) or not isinstance(block_length, int) or block_length <= 0:
        raise ManifestError("fixed geometry has invalid entry rule or block length")
    counts = _ordered_occupancy(
        [[index, count] for index, count in enumerate(_sequence(entry_counts, "entry_counts"))],
        "entry_counts",
    )
    origin = source_geometry.get("origin_index")
    if origin != 0:
        raise ManifestError("fixed geometry must retain origin index zero")
    offsets: list[int] = []
    for block, count in counts:
        if entry_rule == "ordinary":
            offsets.extend(
                math.floor((index + 0.5) * block_length / count) for index in range(count)
            )
        elif entry_rule == "burst":
            if burst_location not in {"first", "middle", "last"}:
                raise ManifestError("burst geometry has an illegal source location")
            burst_offsets = _mapping(source_geometry["burst_offsets"], "burst_offsets")
            location = str(burst_location)
            raw_offset = burst_offsets[location]
            if raw_offset == "gL":
                offset = 0
            elif raw_offset == "gL+floor(L/2)":
                offset = block_length // 2
            elif raw_offset == "gL+L-1":
                offset = block_length - 1
            else:
                raise ManifestError("burst geometry has an illegal source offset")
            offsets.extend([offset] * count)
        elif entry_rule == "overlap_edge_8":
            if count != 8:
                raise ManifestError("overlap_edge_8 requires eight entries per source block")
            offsets.extend(
                int(offset if isinstance(offset, int) else block_length + int(offset[1:]))
                for offset in _sequence(source_geometry["overlap_offsets_8"], "overlap_offsets_8")
            )
        elif entry_rule == "overlap_edge_10":
            if count != 10:
                raise ManifestError("overlap_edge_10 requires ten entries per source block")
            offsets.extend(
                int(offset if isinstance(offset, int) else block_length + int(offset[1:]))
                for offset in _sequence(source_geometry["overlap_offsets_10"], "overlap_offsets_10")
            )
        else:
            raise ManifestError(f"unknown fixed entry rule: {entry_rule}")
        if len(offsets) != sum(item_count for _, item_count in counts[: block + 1]):
            raise ManifestError("source-entry rule produced an invalid observation count")
    grouped: dict[int, int] = {}
    position = 0
    for block, _ in counts:
        count = counts[block][1]
        for offset in offsets[position : position + count]:
            source_index = origin + block * block_length + offset
            grouped[source_index // block_length] = grouped.get(source_index // block_length, 0) + 1
        position += count
    return tuple(sorted(grouped.items()))


def _derived_dynamic_occupancy(
    parameters: Mapping[str, Any], holding_period: int
) -> tuple[tuple[int, int], ...]:
    """Derive dynamic-H occupancy from the fixed nominal source grid, without claimed counts."""
    required = {"nominal_l", "source_span", "trades_per_nominal_block"}
    if not required <= set(parameters):
        raise ManifestError("dynamic geometry parameters are incomplete")
    nominal_l = parameters["nominal_l"]
    source_span = parameters["source_span"]
    trades_per_block = parameters["trades_per_nominal_block"]
    if (
        not all(
            isinstance(value, int) and value > 0
            for value in (nominal_l, source_span, trades_per_block)
        )
        or source_span % nominal_l != 0
        or holding_period <= 0
    ):
        raise ManifestError("dynamic geometry parameters are invalid")
    observed_l = max(63, 3 * holding_period)
    grouped: dict[int, int] = {}
    for nominal_block in range(source_span // nominal_l):
        for entry in range(trades_per_block):
            source_index = nominal_block * nominal_l + math.floor(
                (entry + 0.5) * nominal_l / trades_per_block
            )
            observed_block = source_index // observed_l
            grouped[observed_block] = grouped.get(observed_block, 0) + 1
    return tuple(sorted(grouped.items()))


def satterthwaite_nu(occupancy: tuple[tuple[int, int], ...]) -> float:
    """Calculate nu from the complete ordered ``(block_id, count)`` tuple."""
    checked = _ordered_occupancy([list(pair) for pair in occupancy], "occupancy")
    counts = [count for _, count in checked]
    total = sum(counts)
    if len(counts) < 2 or total <= 1 or any(count >= total for count in counts):
        raise ManifestError("occupancy cannot produce a finite Satterthwaite nu")
    matrix: list[list[float]] = []
    for g, count_g in enumerate(counts):
        row: list[float] = []
        for h, count_h in enumerate(counts):
            numerator = (count_g if g == h else 0.0) - count_g * count_h / total
            denominator = total**2 * math.sqrt((1.0 - count_g / total) * (1.0 - count_h / total))
            row.append(numerator / denominator)
        matrix.append(row)
    trace = sum(matrix[index][index] for index in range(len(matrix)))
    trace_squared_matrix = sum(
        matrix[row][column] * matrix[column][row]
        for row in range(len(matrix))
        for column in range(len(matrix))
    )
    result = trace**2 / trace_squared_matrix
    if not math.isfinite(result) or result <= 0.0:
        raise ManifestError("occupancy produced invalid Satterthwaite nu")
    return result


def _support(
    occupancy: tuple[tuple[int, int], ...], floors: Sequence[tuple[int, float]]
) -> list[bool]:
    nu = satterthwaite_nu(occupancy)
    return [len(occupancy) >= blocks and nu >= minimum_nu for blocks, minimum_nu in floors]


def _validate_manifest(manifest: dict[str, Any]) -> None:
    _exact_keys(manifest, _TOP_LEVEL_KEYS, "top-level")
    if manifest["protocol_version"] != PROTOCOL_VERSION:
        raise ManifestError("unknown protocol version")
    if manifest["selection_artifact_schema"] != SELECTION_SCHEMA:
        raise ManifestError("unknown selection artifact schema")
    if manifest["method_version"] != METHOD_VERSION:
        raise ManifestError("unknown estimator method version")
    floors = _floor_pairs(manifest)

    rng = _mapping(manifest["rng"], "rng")
    _exact_keys(
        rng,
        {"bit_generator", "chunk_size", "component_streams", "seed_sequence", "stream_order"},
        "rng",
    )
    streams = _mapping(rng.get("component_streams"), "rng.component_streams")
    if streams != _EXPECTED_STREAMS:
        raise ManifestError("illegal component stream mapping")
    if rng.get("bit_generator") != "PCG64" or rng.get("chunk_size") != 256:
        raise ManifestError("illegal RNG or chunk mapping")

    phases = _mapping(manifest["phases"], "phases")
    _exact_keys(phases, {"calibration", "validation"}, "phases")
    expected_phase = {
        "calibration": (2026092602, 10000, list(range(1, 46))),
        "validation": (2026092603, 20000, list(range(1001, 1038))),
    }
    geometries = _mapping(manifest["geometries"], "geometries")
    for phase_name, (seed, replicates, expected_ids) in expected_phase.items():
        phase = _mapping(phases[phase_name], f"phases.{phase_name}")
        _exact_keys(phase, {"cells", "master_seed", "replicates"}, f"phases.{phase_name}")
        if phase["master_seed"] != seed:
            raise ManifestError(f"illegal {phase_name} seed")
        if phase["replicates"] != replicates:
            raise ManifestError(f"illegal {phase_name} replicate count")
        cells = _sequence(phase["cells"], f"phases.{phase_name}.cells")
        cell_ids = [cell.get("id") if isinstance(cell, dict) else None for cell in cells]
        if cell_ids != expected_ids:
            raise ManifestError(f"illegal {phase_name} cell IDs")
        for cell in cells:
            checked_cell = _mapping(cell, f"cell {cell_ids}")
            _exact_keys(checked_cell, _CELL_KEYS, f"cell {checked_cell['id']}")
            if checked_cell["role"] not in {"anchor", "support", "dynamic"}:
                raise ManifestError(f"cell {checked_cell['id']} has an illegal role")
            if not isinstance(checked_cell["parameters"], dict) or not isinstance(
                checked_cell["targets"], dict
            ):
                raise ManifestError(f"cell {checked_cell['id']} parameters/targets must be objects")
            family = checked_cell["family"]
            if family not in _PARAMETER_KEYS:
                raise ManifestError(f"cell {checked_cell['id']} has an unknown family")
            _exact_keys(
                checked_cell["parameters"],
                _PARAMETER_KEYS[family],
                f"cell {checked_cell['id']} parameters",
            )
            _exact_keys(
                checked_cell["targets"],
                {"excess_mean", "raw_mean", "win_probability"},
                f"cell {checked_cell['id']} targets",
            )
            support = checked_cell["expected_candidate_support"]
            if support != [bool(item) for item in support] or len(support) != len(floors):
                raise ManifestError(f"cell {checked_cell['id']} has invalid expected support")
            geometry_id = checked_cell["geometry_id"]
            if checked_cell["role"] == "dynamic":
                expected_dynamic_id = (
                    "cal_dynamic" if phase_name == "calibration" else "val_dynamic"
                )
                if geometry_id != expected_dynamic_id:
                    raise ManifestError(f"cell {checked_cell['id']} has illegal dynamic geometry")
            elif geometry_id not in geometries:
                raise ManifestError(f"cell {checked_cell['id']} references an unknown geometry")

    acceptance = _mapping(manifest["acceptance"], "acceptance")
    _exact_keys(
        acceptance,
        {
            "alpha_family",
            "boundary_inclusive",
            "checks",
            "cutoffs",
            "family_sizes",
            "formulas",
            "ideal_method",
            "ideal_power",
            "metrics",
            "thresholds",
        },
        "acceptance",
    )
    family_sizes = _mapping(acceptance.get("family_sizes"), "acceptance.family_sizes")
    _exact_keys(family_sizes, {"calibration", "validation"}, "acceptance.family_sizes")
    if family_sizes != {"calibration": 675, "validation": 555}:
        raise ManifestError("illegal family sizes")
    if acceptance.get("metrics") != ["raw", "win", "synthetic_excess"]:
        raise ManifestError("illegal metric order")
    if acceptance.get("checks") != [
        "coverage_lower",
        "lower_tail_upper",
        "upper_tail_upper",
        "emission_lower",
        "joint_lower",
    ]:
        raise ManifestError("illegal acceptance check order")
    formulas = _mapping(acceptance["formulas"], "acceptance.formulas")
    _exact_keys(formulas, {"cp_lower", "cp_upper", "ideal_power_lower"}, "acceptance.formulas")
    ideal_method = _mapping(acceptance["ideal_method"], "acceptance.ideal_method")
    _exact_keys(
        ideal_method,
        {"coverage", "emission", "joint_success", "lower_tail", "upper_tail"},
        "acceptance.ideal_method",
    )
    thresholds = _mapping(acceptance["thresholds"], "acceptance.thresholds")
    _exact_keys(
        thresholds,
        {
            "coverage_lower",
            "emission_absolute_calibration",
            "emission_absolute_validation",
            "emission_lower",
            "emission_rate",
            "joint_lower",
            "tail_upper",
        },
        "acceptance.thresholds",
    )
    cutoffs = _mapping(acceptance["cutoffs"], "acceptance.cutoffs")
    ideal_power = _mapping(acceptance["ideal_power"], "acceptance.ideal_power")
    _exact_keys(cutoffs, {"calibration", "validation"}, "acceptance.cutoffs")
    _exact_keys(ideal_power, {"calibration", "validation"}, "acceptance.ideal_power")
    for phase_name in ("calibration", "validation"):
        _exact_keys(
            _mapping(cutoffs[phase_name], f"acceptance.cutoffs.{phase_name}"),
            {
                "coverage_or_joint_minimum_successes",
                "emission_minimum_successes",
                "tail_maximum_misses",
            },
            f"acceptance.cutoffs.{phase_name}",
        )
        _exact_keys(
            _mapping(ideal_power[phase_name], f"acceptance.ideal_power.{phase_name}"),
            {
                "coverage_or_joint_failure_probability",
                "lower_bound",
                "tail_failure_probability",
            },
            f"acceptance.ideal_power.{phase_name}",
        )

    for geometry_id, raw_geometry in geometries.items():
        _exact_keys(
            _mapping(raw_geometry, f"geometries.{geometry_id}"),
            {
                "block_counts",
                "candidate_support",
                "entry_counts",
                "entry_rule",
                "expected_blocks",
                "expected_nu",
                "fixed_h",
                "l",
            },
            f"geometries.{geometry_id}",
        )
    dynamic = _mapping(manifest["dynamic_geometries"], "dynamic_geometries")
    _exact_keys(dynamic, {"calibration", "validation"}, "dynamic_geometries")
    for phase_name in ("calibration", "validation"):
        phase_dynamic = _mapping(dynamic[phase_name], f"dynamic_geometries.{phase_name}")
        _exact_keys(phase_dynamic, {"entry_rule", "outcomes"}, f"dynamic_geometries.{phase_name}")
        outcomes = _mapping(phase_dynamic["outcomes"], f"dynamic_geometries.{phase_name}.outcomes")
        for outcome_name, outcome in outcomes.items():
            _exact_keys(
                _mapping(outcome, f"dynamic {phase_name} {outcome_name}"),
                {"block_counts", "expected_blocks", "expected_nu", "l"},
                f"dynamic {phase_name} {outcome_name}",
            )
    integrity = _mapping(manifest["integrity"], "integrity")
    _exact_keys(
        integrity,
        {"allowed_untracked", "output_artifact_pattern", "protected_paths"},
        "integrity",
    )
    _exact_keys(
        _mapping(integrity["protected_paths"], "integrity.protected_paths"),
        {"estimator", "harness", "manifest", "manifest_digest"},
        "integrity.protected_paths",
    )
    _exact_keys(
        _mapping(manifest["runtime_limits"], "runtime_limits"),
        {"max_elapsed_seconds", "max_peak_rss_bytes"},
        "runtime_limits",
    )
    _exact_keys(
        _mapping(manifest["versions"], "versions"),
        {"numpy", "psutil", "python", "scipy"},
        "versions",
    )
    parity = _mapping(manifest["parity"], "parity")
    _exact_keys(
        parity,
        {
            "audit_ids",
            "cache_key",
            "critical_boundary",
            "dimensionless_tolerance",
            "near_zero",
            "scalar_tolerance",
            "zero_status_exact",
        },
        "parity",
    )
    _exact_keys(
        _mapping(parity["dimensionless_tolerance"], "parity.dimensionless_tolerance"),
        {"absolute", "relative"},
        "parity.dimensionless_tolerance",
    )
    _exact_keys(
        _mapping(parity["scalar_tolerance"], "parity.scalar_tolerance"),
        {"mean_absolute_scale", "relative", "variance_absolute_scale"},
        "parity.scalar_tolerance",
    )
    source_geometry = _mapping(manifest["source_geometry"], "source_geometry")
    _exact_keys(
        source_geometry,
        {
            "burst_offsets",
            "ordinary_entry",
            "origin_index",
            "overlap_offsets_10",
            "overlap_offsets_8",
        },
        "source_geometry",
    )
    _exact_keys(
        _mapping(source_geometry["burst_offsets"], "source_geometry.burst_offsets"),
        {"first", "last", "middle"},
        "source_geometry.burst_offsets",
    )
    dgp = _mapping(manifest["dgp_contract"], "dgp_contract")
    _exact_keys(
        dgp,
        {
            "amplitude",
            "benchmark",
            "excess",
            "families",
            "factor_coupling",
            "hold_innovations",
            "latent_sign",
            "outcome",
            "target_excess_mean",
            "target_raw_mean",
            "target_win_probability",
        },
        "dgp_contract",
    )
    _exact_keys(
        _mapping(dgp["amplitude"], "dgp_contract.amplitude"),
        {"ordinary", "rare_calibration", "rare_validation"},
        "dgp_contract.amplitude",
    )
    families = _mapping(dgp["families"], "dgp_contract.families")
    _exact_keys(families, set(_PARAMETER_KEYS), "dgp_contract.families")
    family_keys = {
        "bounded_rare_magnitude": {"amplitude", "factor", "latent"},
        "cross_block_serial_factor": {"factor_initial", "factor_transition", "latent"},
        "dynamic_h_block_factor": {"factor", "holding", "latent"},
        "independent": {"benchmark_factor", "latent"},
        "independent_block_factor": {"factor", "latent"},
        "overlapping_holds": {"factor", "latent"},
        "same_session_burst": {"factor", "latent"},
        "two_regime_shift": {"factor", "latent", "regime"},
        "unequal_occupancy": {"factor", "latent"},
    }
    for family, expected_keys in family_keys.items():
        _exact_keys(
            _mapping(families[family], f"dgp_contract.families.{family}"),
            expected_keys,
            f"dgp_contract.families.{family}",
        )


def load_manifest(path: Path = _MANIFEST, digest_path: Path = _DIGEST) -> dict[str, Any]:
    """Authenticate, canonicalize, and structurally validate the frozen manifest."""
    try:
        raw = path.read_bytes()
        digest_raw = digest_path.read_bytes()
    except OSError as exc:
        raise ManifestError(f"manifest file unavailable: {exc}") from exc
    if not digest_raw.endswith(b"\n") or digest_raw.count(b"\n") != 1:
        raise ManifestError("detached digest must end in exactly one LF")
    digest = digest_raw[:-1].decode("ascii", errors="strict")
    if _HEX64.fullmatch(digest) is None:
        raise ManifestError("detached digest must be 64 lowercase hexadecimal characters")
    actual_digest = hashlib.sha256(raw).hexdigest()
    if not hmac.compare_digest(actual_digest, digest):
        raise ManifestError("manifest digest mismatch")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest is not valid UTF-8 JSON: {exc}") from exc
    manifest = _mapping(payload, "manifest")
    if raw != _canonical_bytes(manifest):
        raise ManifestError("manifest is not canonical sorted UTF-8 JSON plus LF")
    _validate_manifest(manifest)
    return manifest


def clopper_pearson_lower(successes: int, trials: int, alpha: float) -> float:
    if trials <= 0 or not 0 <= successes <= trials or not 0.0 < alpha < 1.0:
        raise ValueError("invalid Clopper-Pearson arguments")
    if successes == 0:
        return 0.0
    return float(beta.ppf(alpha, successes, trials - successes + 1))


def clopper_pearson_upper(successes: int, trials: int, alpha: float) -> float:
    if trials <= 0 or not 0 <= successes <= trials or not 0.0 < alpha < 1.0:
        raise ValueError("invalid Clopper-Pearson arguments")
    if successes == trials:
        return 1.0
    return float(beta.ppf(1.0 - alpha, successes + 1, trials - successes))


def _recompute_metric_summary(
    manifest: Mapping[str, Any],
    *,
    phase: str,
    counts: _MetricEventCounts,
) -> dict[str, Any]:
    """Recompute one exact metric summary from event-derived counts."""

    phases = _mapping(manifest["phases"], "phases")
    if phase not in {"calibration", "validation"} or phase not in phases:
        raise ManifestError("metric summary phase is not frozen in the manifest")
    if not isinstance(counts, _MetricEventCounts):
        raise ManifestError("metric summary counts have the wrong type")
    integer_counts = (
        counts.generated,
        counts.emitted,
        counts.refusal_total,
        counts.coverage_successes,
        counts.lower_tail_misses,
        counts.upper_tail_misses,
        counts.joint_successes,
    )
    if any(type(value) is not int for value in integer_counts):
        raise ManifestError("metric summary counts must be integers excluding booleans")
    phase_contract = _mapping(phases[phase], f"phases.{phase}")
    if counts.generated != phase_contract["replicates"]:
        raise ManifestError("generated count differs from the frozen phase replicate count")

    acceptance = _mapping(manifest["acceptance"], "acceptance")
    metrics = _sequence(acceptance["metrics"], "acceptance.metrics")
    if counts.metric not in metrics:
        raise ManifestError("metric summary names an unknown metric")
    if any(value < 0 for value in integer_counts):
        raise ManifestError("metric summary counts must be non-negative")
    if counts.emitted + counts.refusal_total != counts.generated:
        raise ManifestError("emitted and refusal counts do not equal the generated total")
    if (
        counts.coverage_successes + counts.lower_tail_misses + counts.upper_tail_misses
        != counts.emitted
    ):
        raise ManifestError("metric outcome counts do not partition emitted trials")
    if counts.joint_successes != counts.coverage_successes:
        raise ManifestError("joint successes must equal coverage successes")
    if (
        counts.coverage_successes > counts.emitted
        or counts.lower_tail_misses > counts.emitted
        or counts.upper_tail_misses > counts.emitted
        or counts.joint_successes > counts.generated
    ):
        raise ManifestError("metric summary successes exceed their trial counts")

    family_sizes = _mapping(acceptance["family_sizes"], "acceptance.family_sizes")
    family_size = family_sizes[phase]
    if type(family_size) is not int or family_size <= 0:
        raise ManifestError("phase family size must be a positive integer")
    alpha = float(acceptance["alpha_family"]) / family_size
    thresholds = _mapping(acceptance["thresholds"], "acceptance.thresholds")
    coverage_threshold = float(thresholds["coverage_lower"])
    tail_threshold = float(thresholds["tail_upper"])
    emission_threshold = float(thresholds["emission_lower"])
    emission_rate_threshold = float(thresholds["emission_rate"])
    joint_threshold = float(thresholds["joint_lower"])
    absolute_emission = thresholds[f"emission_absolute_{phase}"]
    if type(absolute_emission) is not int:
        raise ManifestError("absolute emission threshold must be an integer")

    emitted = counts.emitted
    generated = counts.generated
    coverage_bound = (
        clopper_pearson_lower(counts.coverage_successes, emitted, alpha) if emitted else 0.0
    )
    lower_tail_bound = (
        clopper_pearson_upper(counts.lower_tail_misses, emitted, alpha) if emitted else 1.0
    )
    upper_tail_bound = (
        clopper_pearson_upper(counts.upper_tail_misses, emitted, alpha) if emitted else 1.0
    )
    emission_bound = clopper_pearson_lower(emitted, generated, alpha)
    joint_bound = clopper_pearson_lower(counts.joint_successes, generated, alpha)
    emission_rate = emitted / generated

    return {
        "metric": counts.metric,
        "counts": {
            "emitted": emitted,
            "refusal_total": counts.refusal_total,
            "coverage_successes": counts.coverage_successes,
            "lower_tail_misses": counts.lower_tail_misses,
            "upper_tail_misses": counts.upper_tail_misses,
            "joint_successes": counts.joint_successes,
        },
        "checks": {
            "coverage_lower": {
                "successes": counts.coverage_successes,
                "trials": emitted,
                "bound": coverage_bound,
                "threshold": coverage_threshold,
                "passed": emitted > 0 and coverage_bound >= coverage_threshold,
            },
            "lower_tail_upper": {
                "successes": counts.lower_tail_misses,
                "trials": emitted,
                "bound": lower_tail_bound,
                "threshold": tail_threshold,
                "passed": emitted > 0 and lower_tail_bound <= tail_threshold,
            },
            "upper_tail_upper": {
                "successes": counts.upper_tail_misses,
                "trials": emitted,
                "bound": upper_tail_bound,
                "threshold": tail_threshold,
                "passed": emitted > 0 and upper_tail_bound <= tail_threshold,
            },
            "emission_lower": {
                "successes": emitted,
                "trials": generated,
                "bound": emission_bound,
                "rate": emission_rate,
                "absolute_minimum": absolute_emission,
                "threshold": emission_threshold,
                "passed": (
                    emitted >= absolute_emission
                    and emission_rate >= emission_rate_threshold
                    and emission_bound >= emission_threshold
                ),
            },
            "joint_lower": {
                "successes": counts.joint_successes,
                "trials": generated,
                "bound": joint_bound,
                "threshold": joint_threshold,
                "passed": joint_bound >= joint_threshold,
            },
        },
    }


def _minimum_lower_successes(trials: int, alpha: float, threshold: float) -> int:
    low, high = 0, trials
    while low < high:
        middle = (low + high) // 2
        if clopper_pearson_lower(middle, trials, alpha) >= threshold:
            high = middle
        else:
            low = middle + 1
    return low


def _maximum_upper_successes(trials: int, alpha: float, threshold: float) -> int:
    low, high = 0, trials
    while low < high:
        middle = (low + high + 1) // 2
        if clopper_pearson_upper(middle, trials, alpha) <= threshold:
            low = middle
        else:
            high = middle - 1
    return low


def _preflight_cutoffs(manifest: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, float]]:
    acceptance = _mapping(manifest["acceptance"], "acceptance")
    family_sizes = _mapping(acceptance["family_sizes"], "acceptance.family_sizes")
    phases = _mapping(manifest["phases"], "phases")
    thresholds = _mapping(acceptance["thresholds"], "acceptance.thresholds")
    ideal = _mapping(acceptance["ideal_method"], "acceptance.ideal_method")
    cutoffs: dict[str, Any] = {}
    power: dict[str, float] = {}
    for phase_name in ("calibration", "validation"):
        phase = _mapping(phases[phase_name], f"phases.{phase_name}")
        trials = int(phase["replicates"])
        family_size = int(family_sizes[phase_name])
        alpha = float(acceptance["alpha_family"]) / family_size
        coverage_cutoff = _minimum_lower_successes(
            trials, alpha, float(thresholds["coverage_lower"])
        )
        emission_cutoff = _minimum_lower_successes(
            trials, alpha, float(thresholds["emission_lower"])
        )
        tail_cutoff = _maximum_upper_successes(trials, alpha, float(thresholds["tail_upper"]))
        cutoffs[phase_name] = {
            "coverage_or_joint_minimum_successes": coverage_cutoff,
            "emission_minimum_successes": emission_cutoff,
            "tail_maximum_misses": tail_cutoff,
        }
        cell_metric_count = len(_sequence(phase["cells"], f"phases.{phase_name}.cells")) * len(
            _sequence(acceptance["metrics"], "acceptance.metrics")
        )
        coverage_failure = float(binom.cdf(coverage_cutoff - 1, trials, float(ideal["coverage"])))
        joint_failure = float(binom.cdf(coverage_cutoff - 1, trials, float(ideal["joint_success"])))
        lower_tail_failure = float(binom.sf(tail_cutoff, trials, float(ideal["lower_tail"])))
        upper_tail_failure = float(binom.sf(tail_cutoff, trials, float(ideal["upper_tail"])))
        emission_probability = float(ideal["emission"])
        emission_failure = (
            0.0
            if emission_probability == 1.0
            else float(binom.cdf(emission_cutoff - 1, trials, emission_probability))
        )
        power[phase_name] = max(
            0.0,
            1.0
            - cell_metric_count
            * (
                coverage_failure
                + joint_failure
                + lower_tail_failure
                + upper_tail_failure
                + emission_failure
            ),
        )
    return cutoffs, power


def _analytic_targets(
    cell: Mapping[str, Any], occupancy: tuple[tuple[int, int], ...]
) -> dict[str, float]:
    """Derive declared cell targets from the frozen family parameters and occupancy."""
    parameters = _mapping(cell["parameters"], "cell parameters")
    family = cell["family"]
    if family == "two_regime_shift":
        if len(occupancy) % 2 != 0:
            raise ManifestError("two-regime target needs an even occupied-block count")
        first = parameters["p_first"]
        last = parameters["p_last"]
        if not isinstance(first, int | float) or not isinstance(last, int | float):
            raise ManifestError("two-regime target probabilities are invalid")
        midpoint = len(occupancy) // 2
        weighted_probability = sum(
            count * (float(first) if block < midpoint else float(last))
            for block, count in occupancy
        ) / sum(count for _, count in occupancy)
    else:
        probability = parameters.get("p")
        if not isinstance(probability, int | float):
            raise ManifestError(f"{family} target probability is invalid")
        weighted_probability = float(probability)
    amplitude_mean = 1.0
    if family == "bounded_rare_magnitude":
        high = parameters["amplitude_high"]
        high_probability = parameters["amplitude_high_probability"]
        if not isinstance(high, int | float) or not isinstance(high_probability, int | float):
            raise ManifestError("rare-magnitude target parameters are invalid")
        amplitude_mean = 1.0 + (float(high) - 1.0) * float(high_probability)
    raw_mean = 0.01 * amplitude_mean * (2.0 * weighted_probability - 1.0)
    return {
        "raw_mean": raw_mean,
        "win_probability": weighted_probability,
        "excess_mean": raw_mean - 0.002,
    }


def _assert_analytic_targets(
    cell: Mapping[str, Any], occupancy: tuple[tuple[int, int], ...]
) -> None:
    expected = _analytic_targets(cell, occupancy)
    targets = _mapping(cell["targets"], "cell targets")
    for name, value in expected.items():
        actual = targets[name]
        if not isinstance(actual, int | float) or not math.isclose(
            float(actual), value, rel_tol=1e-13, abs_tol=1e-15
        ):
            raise ManifestError(f"cell {cell['id']} analytic target differs: {name}")


def preflight_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Recompute every deterministic support and analytic acceptance proof."""
    _validate_manifest(manifest)
    floors = _floor_pairs(manifest)
    geometries = _mapping(manifest["geometries"], "geometries")
    source_geometry = _mapping(manifest["source_geometry"], "source_geometry")
    for geometry_id, raw_geometry in geometries.items():
        geometry = _mapping(raw_geometry, f"geometries.{geometry_id}")
        occupancy = _ordered_occupancy(geometry.get("block_counts"), f"{geometry_id}.block_counts")
        if geometry.get("entry_rule") == "burst":
            derived_occupancy = _derived_fixed_occupancy(
                geometry.get("entry_rule"),
                geometry.get("l"),
                geometry.get("entry_counts"),
                source_geometry,
                "first",
            )
            if any(
                _derived_fixed_occupancy(
                    geometry.get("entry_rule"),
                    geometry.get("l"),
                    geometry.get("entry_counts"),
                    source_geometry,
                    location,
                )
                != derived_occupancy
                for location in ("middle", "last")
            ):
                raise ManifestError(f"{geometry_id} burst locations disagree on occupancy")
        else:
            derived_occupancy = _derived_fixed_occupancy(
                geometry.get("entry_rule"),
                geometry.get("l"),
                geometry.get("entry_counts"),
                source_geometry,
            )
        if occupancy != derived_occupancy:
            raise ManifestError(f"{geometry_id} derived occupancy differs from claimed occupancy")
        fixed_h = geometry.get("fixed_h")
        if (
            not isinstance(fixed_h, int)
            or isinstance(fixed_h, bool)
            or fixed_h <= 0
            or geometry.get("l") != max(63, 3 * fixed_h)
        ):
            raise ManifestError(f"{geometry_id} fixed H/L equation differs")
        actual_nu = satterthwaite_nu(occupancy)
        if geometry.get("expected_blocks") != len(occupancy):
            raise ManifestError(f"{geometry_id} expected block proof differs")
        if not math.isclose(
            float(geometry["expected_nu"]), actual_nu, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ManifestError(f"{geometry_id} expected nu proof differs")
        if geometry.get("candidate_support") != _support(occupancy, floors):
            raise ManifestError(f"{geometry_id} candidate support proof differs")

    phases = _mapping(manifest["phases"], "phases")
    anchor_support = True
    for phase_name in ("calibration", "validation"):
        phase = _mapping(phases[phase_name], f"phases.{phase_name}")
        for raw_cell in _sequence(phase["cells"], f"phases.{phase_name}.cells"):
            cell = _mapping(raw_cell, "cell")
            if cell["role"] == "dynamic":
                _assert_analytic_targets(cell, ((0, 1),))
                actual_support = [True] * len(floors)
            else:
                geometry = _mapping(geometries[cell["geometry_id"]], "geometry")
                occupancy = _ordered_occupancy(geometry["block_counts"], "geometry.block_counts")
                if cell["family"] == "same_session_burst" and (
                    _derived_fixed_occupancy(
                        geometry["entry_rule"],
                        geometry["l"],
                        geometry["entry_counts"],
                        source_geometry,
                        _mapping(cell["parameters"], "burst parameters")["location"],
                    )
                    != occupancy
                ):
                    raise ManifestError(f"cell {cell['id']} burst source occupancy differs")
                parameters = _mapping(cell["parameters"], "cell parameters")
                if "h" in parameters and parameters["h"] != geometry["fixed_h"]:
                    raise ManifestError(f"cell {cell['id']} H differs from its fixed geometry")
                _assert_analytic_targets(cell, occupancy)
                actual_support = _support(occupancy, floors)
            if cell["expected_candidate_support"] != actual_support:
                raise ManifestError(f"cell {cell['id']} expected candidate support differs")
            if cell["role"] == "anchor" and not all(actual_support):
                anchor_support = False
    if not anchor_support:
        raise ManifestError("a mandatory 24-block anchor fails a candidate floor")

    dynamic_support: dict[str, dict[str, dict[str, float | int]]] = {}
    dynamic = _mapping(manifest["dynamic_geometries"], "dynamic_geometries")
    for phase_name in ("calibration", "validation"):
        phase_dynamic = _mapping(dynamic[phase_name], f"dynamic_geometries.{phase_name}")
        outcomes = _mapping(
            phase_dynamic.get("outcomes"), f"dynamic_geometries.{phase_name}.outcomes"
        )
        phase = _mapping(phases[phase_name], f"phases.{phase_name}")
        dynamic_cells = [
            _mapping(cell, f"phases.{phase_name}.cell")
            for cell in _sequence(phase["cells"], f"phases.{phase_name}.cells")
            if isinstance(cell, dict) and cell.get("role") == "dynamic"
        ]
        if not dynamic_cells:
            raise ManifestError(f"{phase_name} has no dynamic geometry cells")
        declared_holdings: set[int] = set()
        for cell in dynamic_cells:
            parameters = _mapping(cell["parameters"], "dynamic parameters")
            h_loss = parameters["h_loss"]
            h_win = parameters["h_win"]
            if (
                not isinstance(h_loss, int)
                or isinstance(h_loss, bool)
                or not isinstance(h_win, int)
                or isinstance(h_win, bool)
                or h_loss <= 0
                or h_win <= 0
                or h_loss == h_win
            ):
                raise ManifestError(f"dynamic {phase_name} has invalid declared H outcomes")
            if parameters["nominal_l"] != max(63, 3 * max(h_loss, h_win)):
                raise ManifestError(f"dynamic {phase_name} nominal L equation differs")
            declared_holdings.update((h_loss, h_win))
        expected_outcomes = {f"H={holding}" for holding in declared_holdings}
        if set(outcomes) != expected_outcomes:
            raise ManifestError(f"dynamic {phase_name} outcomes differ from declared H values")
        dynamic_support[phase_name] = {}
        for outcome_name, raw_outcome in outcomes.items():
            if not isinstance(outcome_name, str) or not outcome_name.startswith("H="):
                raise ManifestError(f"dynamic {phase_name} has an illegal holding-period outcome")
            try:
                holding_period = int(outcome_name.removeprefix("H="))
            except ValueError as exc:
                raise ManifestError(f"dynamic {phase_name} has an illegal holding period") from exc
            outcome = _mapping(raw_outcome, f"dynamic {phase_name} {outcome_name}")
            occupancy = _ordered_occupancy(
                outcome.get("block_counts"), f"dynamic {phase_name} {outcome_name}.block_counts"
            )
            derived_occupancy = _derived_dynamic_occupancy(
                _mapping(dynamic_cells[0]["parameters"], "dynamic parameters"), holding_period
            )
            if any(
                _derived_dynamic_occupancy(
                    _mapping(cell["parameters"], "dynamic parameters"), holding_period
                )
                != derived_occupancy
                for cell in dynamic_cells[1:]
            ):
                raise ManifestError(f"dynamic {phase_name} cells disagree on source geometry")
            if occupancy != derived_occupancy:
                raise ManifestError(
                    f"dynamic {phase_name} {outcome_name} derived occupancy differs "
                    "from claimed occupancy"
                )
            actual_nu = satterthwaite_nu(occupancy)
            if (
                outcome.get("l") != max(63, 3 * holding_period)
                or outcome.get("expected_blocks") != len(occupancy)
                or not math.isclose(
                    float(outcome["expected_nu"]), actual_nu, rel_tol=1e-12, abs_tol=1e-12
                )
            ):
                raise ManifestError(f"dynamic {phase_name} {outcome_name} proof differs")
            if not all(_support(occupancy, floors)):
                raise ManifestError(f"dynamic {phase_name} {outcome_name} is candidate-dependent")
            dynamic_support[phase_name][outcome_name] = {
                "blocks": len(occupancy),
                "nu": actual_nu,
            }

    cutoffs, power = _preflight_cutoffs(manifest)
    acceptance = _mapping(manifest["acceptance"], "acceptance")
    if cutoffs != acceptance["cutoffs"]:
        raise ManifestError("frozen exact integer cutoffs differ from recomputed values")
    recorded_power = _mapping(acceptance["ideal_power"], "acceptance.ideal_power")
    for phase_name, lower_bound in power.items():
        phase_power = _mapping(recorded_power[phase_name], f"ideal_power.{phase_name}")
        if not math.isclose(
            float(phase_power["lower_bound"]), lower_bound, rel_tol=1e-13, abs_tol=1e-15
        ):
            raise ManifestError(f"frozen {phase_name} ideal power differs")
        if lower_bound < 0.90:
            raise ManifestError(f"{phase_name} ideal whole-gate power is below 0.90")
    return {
        "anchor_support_proven": True,
        "cutoffs": cutoffs,
        "dynamic_support": dynamic_support,
        "ideal_whole_gate_power_lower": power,
    }


def _platform_name() -> str:
    return sys.platform


def _decode_mount_field(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return chr(int(match.group(1), 8))

    return re.sub(r"\\([0-7]{3})", replace, value)


def _filesystem_type_for_path(mountinfo: bytes, path: Path) -> str:
    try:
        text = mountinfo.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise ManifestError("Linux mountinfo is not UTF-8") from exc
    target = os.path.normcase(os.path.abspath(path))
    matches: list[tuple[int, str]] = []
    for line in text.splitlines():
        before, marker, after = line.partition(" - ")
        fields = before.split()
        trailing = after.split()
        if not marker or len(fields) < 5 or not trailing:
            raise ManifestError("Linux mountinfo row is malformed")
        mountpoint = os.path.normcase(os.path.abspath(_decode_mount_field(fields[4])))
        try:
            inside = os.path.commonpath((target, mountpoint)) == mountpoint
        except ValueError:
            inside = False
        if inside:
            matches.append((len(mountpoint), trailing[0]))
    if not matches:
        raise ManifestError("evidence filesystem cannot be resolved from mountinfo")
    longest = max(length for length, _ in matches)
    selected = [filesystem for length, filesystem in matches if length == longest]
    if len(selected) != 1:
        raise ManifestError("evidence filesystem mount is ambiguous")
    return selected[0]


def _verify_native_linux_environment(evidence: Mapping[str, Any]) -> None:
    _exact_keys(evidence, {"osrelease", "pid1", "container"}, "native Linux evidence")
    osrelease = evidence["osrelease"]
    pid1 = evidence["pid1"]
    container = evidence["container"]
    if (
        type(osrelease) is not str
        or type(pid1) is not str
        or type(container) is not bool
        or "microsoft" in osrelease.casefold()
        or container
        or pid1 not in {"systemd", "init"}
    ):
        raise ManifestError("native Linux environment could not be proved")


def _prepare_linux_resource_boundary(
    manifest: Mapping[str, Any],
    evidence_path: Path,
    ops: Any,
    deadline: _Deadline,
) -> _ResourceBoundary:
    deadline.remaining()
    _verify_native_linux_environment(
        _mapping(ops.native_environment_evidence(), "native Linux evidence")
    )
    runtime = _mapping(manifest["runtime_limits"], "runtime_limits")
    limit = runtime["max_peak_rss_bytes"]
    elapsed = runtime["max_elapsed_seconds"]
    if type(limit) is not int or limit <= 0 or type(elapsed) not in (int, float):
        raise ManifestError("authenticated runtime limits are invalid")
    filesystem = _filesystem_type_for_path(ops.read_mountinfo(), evidence_path)
    if filesystem not in {"ext4", "xfs", "btrfs"}:
        raise ManifestError(f"evidence filesystem is unsupported: {filesystem}")
    deadline.remaining()
    ops.set_address_space_limit(limit, limit)
    if ops.get_address_space_limit() != (limit, limit):
        raise ManifestError("RLIMIT_AS installation did not read back exactly")
    deadline.remaining()
    current_vms = ops.current_vms_bytes()
    current_rss = ops.current_rss_bytes()
    peak_rss = ops.peak_rss_bytes()
    if (
        type(current_vms) is not int
        or type(current_rss) is not int
        or type(peak_rss) is not int
        or current_vms < 0
        or current_rss < 0
        or peak_rss < 0
        or current_vms > limit
        or current_rss > limit
        or peak_rss > limit
    ):
        raise ManifestError("process resource measurements are invalid or over limit")
    return _ResourceBoundary(
        _ResourcePolicy(limit, ops, deadline),
        current_vms,
        current_rss,
        peak_rss,
    )


class _NativeLinuxOps:
    def __init__(self) -> None:
        required = ("O_DIRECTORY", "O_NOFOLLOW", "O_CLOEXEC")
        if any(not hasattr(os, name) for name in required):
            raise ManifestError("native Linux secure-open flags are unavailable")
        if not all(operation in os.supports_dir_fd for operation in (os.open, os.mkdir, os.stat)):
            raise ManifestError("native Linux dir_fd operations are unavailable")

    def native_environment_evidence(self) -> dict[str, Any]:
        osrelease = Path("/proc/sys/kernel/osrelease").read_text(encoding="utf-8").strip()
        pid1 = Path("/proc/1/comm").read_text(encoding="utf-8").strip()
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8").casefold()
        markers = (Path("/.dockerenv"), Path("/run/.containerenv"))
        container = (
            any(path.exists() for path in markers)
            or any(name in cgroup for name in ("docker", "containerd", "kubepods", "lxc"))
            or bool(os.environ.get("container"))
        )
        return {"osrelease": osrelease, "pid1": pid1, "container": container}

    def read_mountinfo(self) -> bytes:
        return Path("/proc/self/mountinfo").read_bytes()

    def set_address_space_limit(self, soft: int, hard: int) -> None:
        resource_module: Any = importlib.import_module("resource")
        resource_module.setrlimit(resource_module.RLIMIT_AS, (soft, hard))

    def get_address_space_limit(self) -> tuple[int, int]:
        resource_module: Any = importlib.import_module("resource")
        soft, hard = resource_module.getrlimit(resource_module.RLIMIT_AS)
        return int(soft), int(hard)

    def current_vms_bytes(self) -> int:
        psutil_module: Any = importlib.import_module("psutil")
        return int(psutil_module.Process().memory_info().vms)

    def current_rss_bytes(self) -> int:
        psutil_module: Any = importlib.import_module("psutil")
        return int(psutil_module.Process().memory_info().rss)

    def peak_rss_bytes(self) -> int:
        resource_module: Any = importlib.import_module("resource")
        return int(resource_module.getrusage(resource_module.RUSAGE_SELF).ru_maxrss) * 1024

    def utc_now(self) -> str:
        from datetime import UTC

        return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    def open_root(self, path: Path) -> int:
        return os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)

    def open_dir_at(self, parent_fd: int, name: str) -> int:
        return os.open(
            name,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )

    def mkdir_at(self, parent_fd: int, name: str, mode: int) -> None:
        os.mkdir(name, mode=mode, dir_fd=parent_fd)

    def fstat(self, fd: int) -> os.stat_result:
        return os.fstat(fd)

    def stat_path(self, path: Path) -> os.stat_result:
        return path.lstat()

    def stat_at(self, parent_fd: int, name: str) -> os.stat_result:
        return os.stat(name, dir_fd=parent_fd, follow_symlinks=False)

    def fsync(self, fd: int) -> None:
        os.fsync(fd)

    def close(self, fd: int) -> None:
        os.close(fd)

    def open_exclusive_file(self, directory_fd: int, name: str, mode: int) -> int:
        return os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
            mode,
            dir_fd=directory_fd,
        )

    def open_existing_file(self, directory_fd: int, name: str) -> int:
        return os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=directory_fd,
        )

    def write(self, fd: int, data: bytes) -> int:
        return os.write(fd, data)

    def read_all(self, fd: int) -> bytes:
        size = os.fstat(fd).st_size
        pread = cast(Callable[[int, int, int], bytes], os.__dict__["pread"])
        chunks: list[bytes] = []
        offset = 0
        while offset < size:
            chunk = pread(fd, min(1024 * 1024, size - offset), offset)
            if not chunk:
                raise OSError("unexpected EOF while rereading retained evidence")
            chunks.append(chunk)
            offset += len(chunk)
        return b"".join(chunks)


def _open_or_create_evidence_directory(
    repo: Path,
    relative: Path,
    ops: Any,
    deadline: _Deadline,
) -> _EvidenceDirectory:
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        raise ManifestError("evidence directory path is not repository-relative")
    handles: list[_DirectoryHandle] = []
    owned_fds: list[int] = []
    try:
        root_fd = ops.open_root(repo)
        owned_fds.append(root_fd)
        root_stat = ops.fstat(root_fd)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ManifestError("repository root handle is not a directory")
        handles.append(
            _DirectoryHandle(repo, root_fd, int(root_stat.st_dev), int(root_stat.st_ino))
        )
        for component in relative.parts:
            deadline.remaining()
            parent = handles[-1]
            created = False
            try:
                child_fd = ops.open_dir_at(parent.fd, component)
            except FileNotFoundError:
                ops.mkdir_at(parent.fd, component, 0o700)
                child_fd = ops.open_dir_at(parent.fd, component)
                created = True
            owned_fds.append(child_fd)
            child_path = parent.path / component
            child_stat = ops.fstat(child_fd)
            if not stat.S_ISDIR(child_stat.st_mode):
                raise ManifestError("evidence path component is not a directory")
            handles.append(
                _DirectoryHandle(
                    child_path,
                    child_fd,
                    int(child_stat.st_dev),
                    int(child_stat.st_ino),
                )
            )
            if created:
                ops.fsync(child_fd)
                ops.fsync(parent.fd)
        store = _EvidenceDirectory(tuple(handles), ops, deadline)
        store.recheck()
        return store
    except BaseException as exc:
        close_failures: list[str] = []
        for fd in reversed(owned_fds):
            try:
                ops.close(fd)
            except OSError as close_exc:
                close_failures.append(str(close_exc))
        if close_failures:
            raise ManifestError(
                f"evidence directory failure and close failed: {close_failures}"
            ) from exc
        if isinstance(exc, ManifestError):
            raise
        if isinstance(exc, OSError):
            raise ManifestError(f"evidence directory creation or fsync failed: {exc}") from exc
        raise


def _check_evidence_file(store: _EvidenceDirectory, name: str, fd: int) -> _EvidenceFile:
    try:
        opened = store.ops.fstat(fd)
        named = store.ops.stat_at(store.fd, name)
    except OSError as exc:
        raise ManifestError(f"evidence file identity check failed: {exc}") from exc
    if not stat.S_ISREG(opened.st_mode) or not stat.S_ISREG(named.st_mode):
        raise ManifestError("evidence file is not regular")
    if opened.st_nlink != 1 or named.st_nlink != 1:
        raise ManifestError("evidence file has an extra hard link")
    if (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino):
        raise ManifestError("evidence file identity changed")
    return _EvidenceFile(name, fd, int(opened.st_dev), int(opened.st_ino))


def _open_exclusive_evidence_file(store: _EvidenceDirectory, name: str) -> _EvidenceFile:
    if type(name) is not str or not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ManifestError("evidence filename is invalid")
    store.recheck()
    try:
        fd = store.ops.open_exclusive_file(store.fd, name, 0o600)
    except FileExistsError as exc:
        raise ManifestError(f"evidence artifact already exists: {name}") from exc
    except OSError as exc:
        raise ManifestError(f"evidence file open failed: {exc}") from exc
    try:
        return _check_evidence_file(store, name, fd)
    except BaseException as exc:
        try:
            store.ops.close(fd)
        except OSError as close_exc:
            raise ManifestError(f"evidence file close failed: {close_exc}") from exc
        raise


def _write_all_evidence(file: _EvidenceFile, data: bytes, store: _EvidenceDirectory) -> None:
    offset = 0
    while offset < len(data):
        store.deadline.remaining()
        try:
            written = store.ops.write(file.fd, data[offset:])
        except OSError as exc:
            raise ManifestError(f"evidence write failed: {exc}") from exc
        if type(written) is not int or written <= 0 or written > len(data) - offset:
            raise ManifestError("evidence write returned an invalid short-write count")
        offset += written


def _write_immutable_claim(store: _EvidenceDirectory, name: str, raw: bytes) -> _EvidenceFile:
    writer = _open_exclusive_evidence_file(store, name)
    writer_owned = True
    reader_fd: int | None = None
    reader_owned = False
    try:
        _write_all_evidence(writer, raw, store)
        store.ops.fsync(writer.fd)
        checked_writer = _check_evidence_file(store, name, writer.fd)
        reader_fd = store.ops.open_existing_file(store.fd, name)
        reader_owned = True
        if type(reader_fd) is not int:
            raise ManifestError("claim retained handle is invalid")
        retained = _check_evidence_file(store, name, reader_fd)
        if (retained.device, retained.inode) != (checked_writer.device, checked_writer.inode):
            raise ManifestError("claim identity changed while reopening")
        store.ops.close(writer.fd)
        writer_owned = False
        store.ops.fsync(store.fd)
        store.recheck()
        reader_owned = False
        return retained
    except BaseException as exc:
        close_failures: list[str] = []
        for fd, owned in ((reader_fd, reader_owned), (writer.fd, writer_owned)):
            if fd is None or not owned:
                continue
            try:
                store.ops.close(fd)
            except (OSError, KeyError) as close_exc:
                close_failures.append(str(close_exc))
        if close_failures:
            raise ManifestError(f"evidence close failed: {close_failures}") from exc
        if isinstance(exc, ManifestError):
            raise
        if isinstance(exc, OSError):
            operation = "fsync" if "fsync" in str(exc) else "write"
            raise ManifestError(f"evidence {operation} failed: {exc}") from exc
        raise


def _reserve_result_file(store: _EvidenceDirectory, name: str) -> _EvidenceFile:
    file = _open_exclusive_evidence_file(store, name)
    try:
        store.ops.fsync(file.fd)
        checked = _check_evidence_file(store, name, file.fd)
        store.ops.fsync(store.fd)
        store.recheck()
        return checked
    except BaseException as exc:
        try:
            store.ops.close(file.fd)
        except (OSError, KeyError) as close_exc:
            raise ManifestError(f"result reservation close failed: {close_exc}") from exc
        if isinstance(exc, ManifestError):
            raise
        if isinstance(exc, OSError):
            raise ManifestError(f"result reservation fsync failed: {exc}") from exc
        raise


def _derive_artifact_paths(
    manifest: Mapping[str, Any], phase: str, reviewed_commit: str
) -> _ArtifactPaths:
    if phase not in {"calibration", "validation"}:
        raise ManifestError("counted phase is invalid")
    manifest_sha = hashlib.sha256(_canonical_bytes(_mapping(manifest, "manifest"))).hexdigest()
    directory = f"docs/reviews/step6a2/{manifest_sha}"
    return _ArtifactPaths(
        directory=directory,
        claim_name=f"{phase}.claim",
        result_name=f"{phase}-{reviewed_commit}-{phase}.json",
        seal_name=f"{phase}.seal",
    )


def _assert_artifacts_absent(store: _EvidenceDirectory, paths: _ArtifactPaths) -> None:
    for name in (paths.claim_name, paths.result_name, paths.seal_name):
        try:
            store.ops.stat_at(store.fd, name)
        except (FileNotFoundError, KeyError):
            continue
        except OSError as exc:
            raise ManifestError(f"artifact reservation check failed: {exc}") from exc
        raise ManifestError(f"evidence artifact already exists: {name}")


def _close_phase_start_resources(
    store: _EvidenceDirectory,
    *files: _EvidenceFile | None,
) -> None:
    failures: list[str] = []
    for file in files:
        if file is None:
            continue
        try:
            store.ops.close(file.fd)
        except (OSError, KeyError) as exc:
            failures.append(str(exc))
    for handle in reversed(store.handles):
        try:
            store.ops.close(handle.fd)
        except (OSError, KeyError) as exc:
            failures.append(str(exc))
    if failures:
        raise ManifestError(f"phase start resource close failed: {failures}")


def _begin_linux_phase(
    phase: str,
    manifest: dict[str, Any],
    ops: Any,
    deadline: _Deadline,
) -> _PhaseContext:
    if phase == "validation":
        raise ManifestError("validation requires the verified calibration trio from Slice 4")
    if phase != "calibration":
        raise ManifestError("counted phase is invalid")
    _validate_manifest(manifest)
    manifest_sha = hashlib.sha256(_canonical_bytes(_mapping(manifest, "manifest"))).hexdigest()
    attestation_path = f"docs/reviews/step6a2/{manifest_sha}/task3.review.json"
    attestation_raw = _read_tracked_worktree_bytes(_ROOT, attestation_path)
    review = _parse_review_attestation(manifest, attestation_raw)
    allowed_untracked = tuple(
        str(value)
        for value in _sequence(
            _mapping(manifest["integrity"], "integrity")["allowed_untracked"],
            "integrity.allowed_untracked",
        )
    )
    proof = _verify_reviewed_git_state(
        _ROOT,
        manifest,
        review,
        deadline,
        allowed_untracked=allowed_untracked,
    )
    evidence_path = _ROOT / Path(review.attestation_path).parent
    resources = _prepare_linux_resource_boundary(manifest, evidence_path, ops, deadline)
    paths = _derive_artifact_paths(manifest, phase, review.reviewed_commit)
    store = _open_or_create_evidence_directory(_ROOT, Path(paths.directory), ops, deadline)
    claim_file: _EvidenceFile | None = None
    result_file: _EvidenceFile | None = None
    try:
        _assert_artifacts_absent(store, paths)
        started_at = ops.utc_now()
        _check_utc(started_at, "claim start")
        attempt_id = f"{review.reviewed_commit}-{phase}"
        claim = {
            "artifact_paths": paths.as_claim_record(),
            "attempt_id": attempt_id,
            "invocation_commit": proof.invocation_commit,
            "manifest_sha256": manifest_sha,
            "phase": phase,
            "protected_blobs": dict(proof.protected_blobs),
            "protocol_version": PROTOCOL_VERSION,
            "review_attestation": {
                "path": review.attestation_path,
                "sha256": review.raw_sha256,
            },
            "reviewed_commit": review.reviewed_commit,
            "schema": "step6a2-phase-claim-v1",
            "started_at_utc": started_at,
        }
        claim_raw = _canonical_bytes(claim)
        claim_file = _write_immutable_claim(store, paths.claim_name, claim_raw)
        result_file = _reserve_result_file(store, paths.result_name)
        claim_sha = hashlib.sha256(claim_raw).hexdigest()
        binding = _phase_context_binding_bytes(
            phase,
            paths,
            review,
            proof,
            resources,
            claim_sha,
            started_at,
        )
        context = _PhaseContext(
            phase,
            paths,
            review,
            proof,
            resources,
            store,
            claim_file,
            result_file,
            claim_sha,
            claim_raw,
            started_at,
            binding,
            _PHASE_CONTEXT_ISSUER,
        )
        return context
    except BaseException as exc:
        try:
            _close_phase_start_resources(store, result_file, claim_file)
        except ManifestError as close_exc:
            raise close_exc from exc
        raise


def _begin_counted_phase(phase: str) -> Any:
    started = time.monotonic()
    manifest = load_manifest()
    duration = float(manifest["runtime_limits"]["max_elapsed_seconds"])
    deadline = _Deadline(started, duration, time.monotonic)
    if _platform_name() != "linux":
        raise ManifestError("counted phases require native Linux")
    ops = _NativeLinuxOps()
    return _begin_linux_phase(phase, manifest, ops, deadline)


def _strict_repo_path(value: object, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value.startswith("/")
        or "\\" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
    ):
        raise ManifestError(f"{label} is invalid")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise ManifestError(f"{label} is not a normalized POSIX path")
    return value


def _parse_review_attestation(manifest: Mapping[str, Any], raw: bytes) -> _ReviewAttestation:
    payload = _parse_canonical_json_bytes(raw, label="review attestation")
    _exact_keys(
        payload,
        {
            "schema",
            "protocol_version",
            "manifest_sha256",
            "verdict",
            "reviewed_commit",
            "reviewed_tree",
            "protected_blobs",
            "review_record_path",
            "allowed_intervening_paths",
            "review_scope",
            "reviewer",
            "reviewed_at_utc",
        },
        "review attestation",
    )
    manifest_sha = hashlib.sha256(_canonical_bytes(_mapping(manifest, "manifest"))).hexdigest()
    if (
        payload["schema"] != "step6a2-task3-review-v1"
        or payload["protocol_version"] != PROTOCOL_VERSION
        or payload["manifest_sha256"] != manifest_sha
        or payload["verdict"] != "APPROVED"
    ):
        raise ManifestError("review attestation identity or verdict differs")
    for key in ("reviewed_commit", "reviewed_tree"):
        if type(payload[key]) is not str or re.fullmatch(r"[0-9a-f]{40}", payload[key]) is None:
            raise ManifestError(f"review attestation {key} is invalid")
    protected = _mapping(payload["protected_blobs"], "review attestation protected_blobs")
    expected_paths = set(_manifest_protected_paths(manifest))
    if set(protected) != expected_paths or any(
        type(value) is not str or _HEX64.fullmatch(value) is None for value in protected.values()
    ):
        raise ManifestError("review attestation protected blobs differ")
    attestation_path = f"docs/reviews/step6a2/{manifest_sha}/task3.review.json"
    review_path = _strict_repo_path(
        payload["review_record_path"], "review attestation review record path"
    )
    if not review_path.startswith("docs/reviews/") or review_path == attestation_path:
        raise ManifestError("review attestation review record path is invalid")
    allowed = payload["allowed_intervening_paths"]
    if (
        not isinstance(allowed, list)
        or any(type(value) is not str for value in allowed)
        or allowed != sorted({review_path, attestation_path})
    ):
        raise ManifestError("review attestation allowed paths differ")
    if payload["review_scope"] != [
        "artifact_verifier",
        "counted_calibration",
        "held_back_validation",
        "resource_and_durability",
    ]:
        raise ManifestError("review attestation scope differs")
    reviewer = _mapping(payload["reviewer"], "review attestation reviewer")
    _exact_keys(reviewer, {"model", "role"}, "review attestation reviewer")
    if (
        type(reviewer["model"]) is not str
        or not reviewer["model"]
        or reviewer["role"] != "independent_statistical_safety"
    ):
        raise ManifestError("review attestation reviewer differs")
    _check_utc(payload["reviewed_at_utc"], "review attestation timestamp")
    return _ReviewAttestation(
        reviewed_commit=payload["reviewed_commit"],
        reviewed_tree=payload["reviewed_tree"],
        protected_blobs=dict(protected),
        review_record_path=review_path,
        attestation_path=attestation_path,
        allowed_intervening_paths=tuple(allowed),
        reviewed_at_utc=payload["reviewed_at_utc"],
        raw_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _git(repo: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo,
        check=False,
        capture_output=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout


def _git_with_deadline(repo: Path, deadline: _Deadline, *args: str) -> bytes:
    timeout = deadline.remaining()
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=repo,
            check=False,
            capture_output=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise ManifestError("counted phase deadline expired during git preflight") from exc
    if completed.returncode != 0:
        message = completed.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(f"git {' '.join(args)} failed: {message}")
    return completed.stdout


def _nul_paths(raw: bytes, label: str) -> tuple[str, ...]:
    if raw and not raw.endswith(b"\0"):
        raise ManifestError(f"{label} did not return NUL-terminated paths")
    try:
        return tuple(item.decode("utf-8", errors="strict") for item in raw.split(b"\0")[:-1])
    except UnicodeDecodeError as exc:
        raise ManifestError(f"{label} returned a non-UTF-8 repository path") from exc


def _read_tracked_worktree_bytes(repo: Path, relative: str) -> bytes:
    if type(relative) is not str or not relative or "\0" in relative:
        raise ManifestError("tracked path is invalid")
    pure = Path(relative)
    if pure.is_absolute() or any(part in {"", ".", ".."} for part in pure.parts):
        raise ManifestError("tracked path escapes the repository")
    cursor = repo
    for part in pure.parts:
        cursor = cursor / part
        try:
            metadata = cursor.lstat()
        except OSError as exc:
            raise ManifestError(f"tracked file unavailable: {relative}") from exc
        if stat.S_ISLNK(metadata.st_mode):
            raise ManifestError(f"tracked path contains a symlink: {relative}")
    if not stat.S_ISREG(metadata.st_mode):
        raise ManifestError(f"tracked path is not a regular file: {relative}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        fd = os.open(cursor, flags)
        opened = os.fstat(fd)
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        after = cursor.lstat()
    except OSError as exc:
        raise ManifestError(f"tracked file could not be read securely: {relative}") from exc
    finally:
        if "fd" in locals():
            os.close(fd)
    if (
        not stat.S_ISREG(opened.st_mode)
        or (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino)
        or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
    ):
        raise ManifestError(f"tracked file identity changed while reading: {relative}")
    return b"".join(chunks)


def verify_protected_git_state(
    repo: Path,
    *,
    protected_paths: tuple[str, ...],
    allowed_untracked: tuple[str, ...],
) -> dict[str, str]:
    """Require a clean commit and byte-identical tracked protected inputs."""
    root = Path(_git(repo, "rev-parse", "--show-toplevel").decode("utf-8").strip()).resolve()
    if root != repo.resolve():
        raise ManifestError("repository root differs from the requested preflight root")
    allowed = {path.replace("\\", "/") for path in allowed_untracked}
    protected = {path.replace("\\", "/") for path in protected_paths}
    status = _git(repo, "status", "--porcelain=v1", "--untracked-files=all").decode("utf-8")
    for line in status.splitlines():
        code, path = line[:2], line[3:].replace("\\", "/")
        if code == "??" and path in allowed:
            continue
        if path in protected:
            raise ManifestError(f"protected tracked file differs from HEAD: {path}")
        raise ManifestError(f"working tree is not clean: {line}")

    blobs: dict[str, str] = {"commit": _git(repo, "rev-parse", "HEAD").decode("ascii").strip()}
    for protected_path in protected_paths:
        normalized = protected_path.replace("\\", "/")
        _git(repo, "ls-files", "--error-unmatch", "--", normalized)
        committed = _git(repo, "show", f"HEAD:{normalized}")
        try:
            working = (repo / Path(normalized)).read_bytes()
        except OSError as exc:
            raise ManifestError(f"protected tracked file unavailable: {normalized}") from exc
        if working != committed:
            raise ManifestError(f"protected tracked file differs from HEAD: {normalized}")
        blobs[normalized] = hashlib.sha256(working).hexdigest()
    return blobs


def _verify_reviewed_git_state(
    repo: Path,
    manifest: Mapping[str, Any],
    attestation: _ReviewAttestation,
    deadline: _Deadline,
    *,
    allowed_untracked: tuple[str, ...],
) -> _InvocationProof:
    root = Path(
        _git_with_deadline(repo, deadline, "rev-parse", "--show-toplevel")
        .decode("utf-8", errors="strict")
        .strip()
    ).resolve()
    if root != repo.resolve():
        raise ManifestError("repository root differs from counted preflight root")
    invocation = _git_with_deadline(repo, deadline, "rev-parse", "HEAD").decode("ascii").strip()
    actual_attestation = _read_tracked_worktree_bytes(repo, attestation.attestation_path)
    if hashlib.sha256(actual_attestation).hexdigest() != attestation.raw_sha256:
        raise ManifestError("tracked review attestation bytes differ from parsed attestation")
    staged = _nul_paths(
        _git_with_deadline(repo, deadline, "diff", "--cached", "--name-only", "-z", invocation),
        "staged index diff",
    )
    if staged:
        raise ManifestError("Git index differs from invocation HEAD")
    try:
        merge_base = (
            _git_with_deadline(
                repo, deadline, "merge-base", attestation.reviewed_commit, invocation
            )
            .decode("ascii")
            .strip()
        )
    except ManifestError as exc:
        raise ManifestError("reviewed commit is not an ancestor of invocation HEAD") from exc
    if merge_base != attestation.reviewed_commit:
        raise ManifestError("reviewed commit is not an ancestor of invocation HEAD")
    reviewed_tree = (
        _git_with_deadline(repo, deadline, "rev-parse", f"{attestation.reviewed_commit}^{{tree}}")
        .decode("ascii")
        .strip()
    )
    if reviewed_tree != attestation.reviewed_tree:
        raise ManifestError("reviewed tree differs from attestation")

    allowed_paths = set(attestation.allowed_intervening_paths)
    history = _git_with_deadline(
        repo, deadline, "rev-list", "--parents", f"{attestation.reviewed_commit}..{invocation}"
    )
    for raw_line in history.splitlines():
        fields = raw_line.decode("ascii", errors="strict").split()
        if len(fields) != 2:
            raise ManifestError("review ancestry contains a merge commit")
        commit = fields[0]
        changed = set(
            _nul_paths(
                _git_with_deadline(
                    repo,
                    deadline,
                    "diff-tree",
                    "--no-commit-id",
                    "--name-only",
                    "-r",
                    "-z",
                    f"{commit}^",
                    commit,
                ),
                "intervening commit diff",
            )
        )
        if not changed <= allowed_paths:
            raise ManifestError("intervening commit changes a non-review path")
    endpoint = set(
        _nul_paths(
            _git_with_deadline(
                repo,
                deadline,
                "diff",
                "--name-only",
                "-z",
                attestation.reviewed_commit,
                invocation,
            ),
            "review endpoint diff",
        )
    )
    if not endpoint <= allowed_paths:
        raise ManifestError("review endpoint changes a non-review path")
    for path in allowed_paths:
        _git_with_deadline(repo, deadline, "cat-file", "-e", f"{invocation}:{path}")

    for relative, expected_sha in attestation.protected_blobs.items():
        committed = _git_with_deadline(
            repo, deadline, "show", f"{attestation.reviewed_commit}:{relative}"
        )
        if hashlib.sha256(committed).hexdigest() != expected_sha:
            raise ManifestError(f"reviewed protected blob differs: {relative}")

    tree = _git_with_deadline(repo, deadline, "ls-tree", "-r", "-z", invocation)
    for entry in tree.split(b"\0"):
        if not entry:
            continue
        try:
            header, raw_path = entry.split(b"\t", 1)
            mode, object_type, oid = header.decode("ascii").split()
            relative = raw_path.decode("utf-8", errors="strict")
        except (ValueError, UnicodeDecodeError) as exc:
            raise ManifestError("invocation tree contains an unsupported entry") from exc
        if object_type != "blob" or mode == "120000":
            raise ManifestError(f"tracked path is not a regular file: {relative}")
        working = _read_tracked_worktree_bytes(repo, relative)
        committed = _git_with_deadline(repo, deadline, "cat-file", "blob", oid)
        if working != committed:
            raise ManifestError(f"tracked file differs from HEAD: {relative}")

    untracked = set(
        _nul_paths(
            _git_with_deadline(repo, deadline, "ls-files", "--others", "--exclude-standard", "-z"),
            "untracked file listing",
        )
    )
    normalized_allowed = {path.replace("\\", "/") for path in allowed_untracked}
    if not untracked <= normalized_allowed:
        raise ManifestError("working tree contains an untracked path outside the exact allowance")
    return _InvocationProof(
        reviewed_commit=attestation.reviewed_commit,
        invocation_commit=invocation,
        protected_blobs=dict(attestation.protected_blobs),
    )


def _selection_error(message: str) -> SelectionArtifactError:
    return SelectionArtifactError(message)


def validate_selection_artifact(
    manifest: dict[str, Any],
    artifact: dict[str, Any],
    *,
    manifest_sha256: str,
    protected_blobs: dict[str, str],
) -> None:
    """Refuse validation unless calibration is complete and selected the first passing floor."""
    expected_top = {
        "calibration",
        "calibration_result_sha256",
        "manifest_sha256",
        "protected_blobs",
        "protocol_version",
        "schema",
        "selected_candidate",
    }
    if set(artifact) != expected_top:
        raise _selection_error("selection artifact keys are incomplete or unknown")
    if artifact["schema"] != SELECTION_SCHEMA or artifact["protocol_version"] != PROTOCOL_VERSION:
        raise _selection_error("selection artifact schema/protocol mismatch")
    if (
        not isinstance(artifact["calibration_result_sha256"], str)
        or _HEX64.fullmatch(artifact["calibration_result_sha256"]) is None
    ):
        raise _selection_error("selection artifact calibration-result hash is malformed")
    if artifact["manifest_sha256"] != manifest_sha256:
        raise _selection_error("selection artifact manifest hash mismatch")
    if artifact["protected_blobs"] != protected_blobs:
        raise _selection_error("selection artifact protected blob hashes mismatch")
    if set(protected_blobs) != {"manifest", "manifest_digest", "harness", "estimator"} or any(
        not isinstance(value, str) or _HEX64.fullmatch(value) is None
        for value in protected_blobs.values()
    ):
        raise _selection_error("selection artifact protected blob hashes are malformed")

    calibration = artifact["calibration"]
    if not isinstance(calibration, dict) or set(calibration) != {
        "candidate_results",
        "cells",
        "master_seed",
        "replicates_per_cell",
    }:
        raise _selection_error("selection artifact calibration section is incomplete")
    phase = manifest["phases"]["calibration"]
    if calibration["master_seed"] != phase["master_seed"]:
        raise _selection_error("selection artifact calibration seed mismatch")
    if calibration["replicates_per_cell"] != phase["replicates"]:
        raise _selection_error("selection artifact replicate count mismatch")
    cells = calibration["cells"]
    if not isinstance(cells, list):
        raise _selection_error("selection artifact calibration cells must be an array")
    expected_ids = [cell["id"] for cell in phase["cells"]]
    if [cell.get("cell_id") if isinstance(cell, dict) else None for cell in cells] != expected_ids:
        raise _selection_error("selection artifact lacks complete calibration cell IDs")
    expected_metrics = set(manifest["acceptance"]["metrics"])
    expected_checks = set(manifest["acceptance"]["checks"])
    family_size = manifest["acceptance"]["family_sizes"]["calibration"]
    alpha = manifest["acceptance"]["alpha_family"] / family_size
    thresholds = manifest["acceptance"]["thresholds"]
    absolute_emission = thresholds["emission_absolute_calibration"]
    for cell in cells:
        if (
            set(cell) != {"cell_id", "generated", "metrics"}
            or cell["generated"] != phase["replicates"]
        ):
            raise _selection_error(f"cell {cell.get('cell_id')} has incomplete generated counts")
        metrics = cell["metrics"]
        if not isinstance(metrics, dict) or set(metrics) != expected_metrics:
            raise _selection_error(f"cell {cell['cell_id']} has incomplete metric checks")
        for metric, result in metrics.items():
            count_keys = {
                "checks",
                "coverage_successes",
                "emitted",
                "joint_successes",
                "lower_tail_misses",
                "refusal_total",
                "upper_tail_misses",
            }
            if not isinstance(result, dict) or set(result) != count_keys:
                raise _selection_error(
                    f"cell {cell['cell_id']} metric {metric} lacks complete calibration counts"
                )
            counts = {key: result[key] for key in count_keys - {"checks"}}
            if any(
                not isinstance(value, int) or isinstance(value, bool) for value in counts.values()
            ):
                raise _selection_error(
                    f"cell {cell['cell_id']} metric {metric} has non-integer calibration counts"
                )
            emitted = counts["emitted"]
            generated = cell["generated"]
            if (
                not 0 <= emitted <= generated
                or counts["refusal_total"] != generated - emitted
                or not 0 <= counts["coverage_successes"] <= emitted
                or not 0 <= counts["lower_tail_misses"] <= emitted
                or not 0 <= counts["upper_tail_misses"] <= emitted
                or not 0 <= counts["joint_successes"] <= generated
                or (
                    counts["coverage_successes"]
                    + counts["lower_tail_misses"]
                    + counts["upper_tail_misses"]
                    != emitted
                )
                or counts["joint_successes"] != counts["coverage_successes"]
            ):
                raise _selection_error(
                    f"cell {cell['cell_id']} metric {metric} has inconsistent calibration counts"
                )
            checks = result["checks"]
            if (
                not isinstance(checks, dict)
                or set(checks) != expected_checks
                or any(not isinstance(value, bool) for value in checks.values())
            ):
                raise _selection_error(
                    f"cell {cell['cell_id']} metric {metric} checks are incomplete"
                )
            expected_check_values = {
                "coverage_lower": emitted > 0
                and clopper_pearson_lower(counts["coverage_successes"], emitted, alpha)
                >= thresholds["coverage_lower"],
                "lower_tail_upper": emitted > 0
                and clopper_pearson_upper(counts["lower_tail_misses"], emitted, alpha)
                <= thresholds["tail_upper"],
                "upper_tail_upper": emitted > 0
                and clopper_pearson_upper(counts["upper_tail_misses"], emitted, alpha)
                <= thresholds["tail_upper"],
                "emission_lower": emitted >= absolute_emission
                and emitted / generated >= thresholds["emission_rate"]
                and clopper_pearson_lower(emitted, generated, alpha)
                >= thresholds["emission_lower"],
                "joint_lower": clopper_pearson_lower(counts["joint_successes"], generated, alpha)
                >= thresholds["joint_lower"],
            }
            if checks != expected_check_values:
                raise _selection_error(
                    f"cell {cell['cell_id']} metric {metric} check verdicts do not match counts"
                )

    candidate_results = calibration["candidate_results"]
    floors = manifest["candidate_floors"]
    if not isinstance(candidate_results, list) or len(candidate_results) != len(floors):
        raise _selection_error("selection artifact candidate results are incomplete")
    if any(
        not isinstance(result, dict)
        or set(result) != {"fixed_refusal_controls_passed", "floor", "passed"}
        or result["floor"] != floor
        or not isinstance(result["passed"], bool)
        or result["fixed_refusal_controls_passed"] is not True
        for result, floor in zip(candidate_results, floors, strict=True)
    ):
        raise _selection_error("selection artifact candidate order differs")
    cells_by_id = {cell["cell_id"]: cell for cell in cells}
    manifest_cells = manifest["phases"]["calibration"]["cells"]
    for candidate_index, result in enumerate(candidate_results):
        eligible_checks = (
            cells_by_id[cell["id"]]["metrics"][metric]["checks"].values()
            for cell in manifest_cells
            if cell["expected_candidate_support"][candidate_index]
            for metric in manifest["acceptance"]["metrics"]
        )
        expected_pass = result["fixed_refusal_controls_passed"] and all(
            check for metric_checks in eligible_checks for check in metric_checks
        )
        if result["passed"] is not expected_pass:
            raise _selection_error("selection artifact candidate verdict does not match counts")
    first_passing = next(
        (result["floor"] for result in candidate_results if result["passed"]),
        None,
    )
    if first_passing is None or artifact["selected_candidate"] != first_passing:
        raise _selection_error("selected floor is not the first passing candidate")


@dataclass(frozen=True, slots=True)
class _ExpectedPhaseContext:
    """Immutable values established outside the untrusted result bytes."""

    phase: str
    provenance_bytes: bytes
    attempt_bytes: bytes
    runtime_bytes: bytes
    verified_calibration_floor: tuple[int, float] | None

    def __post_init__(self) -> None:
        if type(self.phase) is not str or self.phase not in {"calibration", "validation"}:
            raise ManifestError("expected phase is invalid")
        for label, raw in (
            ("expected provenance", self.provenance_bytes),
            ("expected attempt", self.attempt_bytes),
            ("expected runtime", self.runtime_bytes),
        ):
            _parse_canonical_json_bytes(raw, label=label)
        floor = self.verified_calibration_floor
        if self.phase == "calibration" and floor is not None:
            raise ManifestError("calibration must not have a verified floor")
        if self.phase == "validation":
            if (
                not isinstance(floor, tuple)
                or len(floor) != 2
                or type(floor[0]) is not int
                or type(floor[1]) not in (int, float)
            ):
                raise ManifestError("validation requires an external verified floor")
            _finite_number(floor[1], "validation floor")


@dataclass(frozen=True, slots=True)
class VerifiedPhaseResult:
    phase: str
    phase_verdict: str
    selected_floor: tuple[int, float] | None


def _finite_number(value: object, label: str, *, nonnegative: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ManifestError(f"{label} must be finite number excluding booleans")
    try:
        number = float(value)
    except (OverflowError, ValueError) as exc:
        raise ManifestError(f"{label} must be finite number") from exc
    if not math.isfinite(number):
        raise ManifestError(f"{label} must be finite number")
    if nonnegative and number < 0.0:
        raise ManifestError(f"{label} must be non-negative")
    return number


def _nonnegative_int(value: object, label: str) -> int:
    if type(value) is not int or value < 0:
        raise ManifestError(f"{label} must be non-negative integer excluding booleans")
    return value


def _check_utc(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z", value) is None
    ):
        raise ManifestError(f"{label} must be six-digit UTC")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError as exc:
        raise ManifestError(f"{label} has an invalid UTC calendar value") from exc


def _same_frozen(value: object, expected: object, label: str) -> None:
    if _canonical_bytes(_mapping(value, label)) != _canonical_bytes(_mapping(expected, label)):
        raise ManifestError(f"{label} differs from frozen expected value")


def _verify_expected_identity(
    manifest: dict[str, Any],
    result: dict[str, Any],
    context: _ExpectedPhaseContext,
    expected: dict[str, Any],
) -> None:
    _exact_keys(
        expected,
        {
            "manifest_sha256",
            "method_version",
            "selection_artifact_schema",
            "reviewed_commit",
            "invocation_commit",
            "protected_blobs",
            "review_attestation_sha256",
            "claim_sha256",
            "dependencies",
        },
        "expected provenance",
    )
    for name in ("manifest_sha256", "review_attestation_sha256", "claim_sha256"):
        if type(expected[name]) is not str or _HEX64.fullmatch(expected[name]) is None:
            raise ManifestError(f"provenance {name} is invalid")
    for name in ("reviewed_commit", "invocation_commit"):
        if type(expected[name]) is not str or re.fullmatch(r"[0-9a-f]{40}", expected[name]) is None:
            raise ManifestError(f"provenance {name} is invalid")
    blobs = _mapping(expected["protected_blobs"], "protected blobs")
    if set(blobs) != set(_manifest_protected_paths(manifest)) or any(
        type(value) is not str or _HEX64.fullmatch(value) is None for value in blobs.values()
    ):
        raise ManifestError("provenance protected blobs are invalid")
    if (
        expected["method_version"] != manifest["method_version"]
        or expected["selection_artifact_schema"] != manifest["selection_artifact_schema"]
    ):
        raise ManifestError("provenance method or selection schema differs")
    _same_frozen(expected["dependencies"], manifest["versions"], "provenance dependencies")
    _same_frozen(result["provenance"], expected, "result provenance")
    attempt = _parse_canonical_json_bytes(context.attempt_bytes, label="expected attempt")
    _exact_keys(attempt, {"attempt_id", "started_at_utc"}, "expected attempt")
    if attempt["attempt_id"] != f"{expected['reviewed_commit']}-{context.phase}":
        raise ManifestError("expected attempt ID differs from reviewed commit and phase")
    _check_utc(attempt["started_at_utc"], "attempt start")
    _same_frozen(result["attempt"], attempt, "result attempt")
    phase_data = manifest["phases"][context.phase]
    contract = {
        "master_seed": phase_data["master_seed"],
        "replicates_per_cell": phase_data["replicates"],
        "cell_definitions": phase_data["cells"],
        "candidate_floors": manifest["candidate_floors"],
        "metrics": manifest["acceptance"]["metrics"],
        "checks": manifest["acceptance"]["checks"],
        "family_size": manifest["acceptance"]["family_sizes"][context.phase],
    }
    _same_frozen(result["phase_contract"], contract, "phase contract")
    runtime = _parse_canonical_json_bytes(context.runtime_bytes, label="expected runtime")
    _exact_keys(
        runtime,
        {
            "platform",
            "resource_backend",
            "address_space_limit_bytes",
            "peak_rss_before_verification_bytes",
            "peak_rss_source",
            "planned_peak_bytes",
            "maximum_result_bytes",
            "generation_elapsed_seconds",
            "deadline_seconds",
            "resource_state",
        },
        "expected runtime",
    )
    if (
        runtime["platform"],
        runtime["resource_backend"],
        runtime["peak_rss_source"],
        runtime["resource_state"],
    ) != ("linux", "linux-rlimit-as", "getrusage-ru_maxrss-kib", "WITHIN_LIMIT"):
        raise ManifestError("runtime platform, backend, source or state differs")
    limits = manifest["runtime_limits"]
    if (
        runtime["address_space_limit_bytes"] != limits["max_peak_rss_bytes"]
        or type(runtime["address_space_limit_bytes"]) is not int
        or runtime["deadline_seconds"] != limits["max_elapsed_seconds"]
        or type(runtime["deadline_seconds"]) is not int
    ):
        raise ManifestError("runtime limits differ from frozen manifest")
    for name in (
        "peak_rss_before_verification_bytes",
        "planned_peak_bytes",
        "maximum_result_bytes",
    ):
        amount = _nonnegative_int(runtime[name], f"runtime {name}")
        if amount > limits["max_peak_rss_bytes"]:
            raise ManifestError(f"runtime {name} exceeds frozen memory limit")
    elapsed = _finite_number(
        runtime["generation_elapsed_seconds"], "runtime elapsed", nonnegative=True
    )
    if elapsed > limits["max_elapsed_seconds"]:
        raise ManifestError("runtime generation exceeds frozen deadline")
    _same_frozen(result["runtime"], runtime, "result runtime")
    terminal = _mapping(result["terminal"], "terminal")
    _exact_keys(terminal, {"state", "ended_at_utc", "failure"}, "terminal")
    if terminal["state"] != "UNVERIFIED" or terminal["failure"] is not None:
        raise ManifestError("only complete unverified results can be verified")
    _check_utc(terminal["ended_at_utc"], "terminal end")
    if terminal["ended_at_utc"] < attempt["started_at_utc"]:
        raise ManifestError("terminal precedes attempt")


def _verify_parity(
    manifest: dict[str, Any],
    events: dict[str, Any],
    cell: dict[str, Any],
    metric: str,
    replicates: int,
    start: int,
    stop: int,
) -> None:
    records = _sequence(events["parity"], "parity records")
    fixed = set(parity_audit_ids(replicates)) & set(range(start, stop))
    target_key = {"raw": "raw_mean", "win": "win_probability", "synthetic_excess": "excess_mean"}[
        metric
    ]
    target = _finite_number(cell["targets"][target_key], "parity target")
    covered, lower, upper = (
        set(events[name]) for name in ("coverage_ids", "lower_miss_ids", "upper_miss_ids")
    )
    emitted = set(events["emitted_ids"])
    refusal_status = {
        item: refusal["reason"] for refusal in events["refusals"] for item in refusal["ids"]
    }
    seen: list[int] = []
    trigger_names = {"ordinary", "non_finite", "zero", "near_zero", "t_critical"}
    result_keys = {
        "status",
        "mean",
        "cr2_variance",
        "nu",
        "sample_variance",
        "design_effect",
        "effective_n",
        "raw_lower",
        "raw_upper",
        "coverage",
        "lower_miss",
        "upper_miss",
    }
    numeric = result_keys - {"status", "coverage", "lower_miss", "upper_miss"}
    for record in records:
        item = _mapping(record, "parity record")
        _exact_keys(
            item,
            {"replicate_id", "triggers", "max_abs_outcome", "batch", "scalar", "cr1"},
            "parity record",
        )
        rid = _nonnegative_int(item["replicate_id"], "parity replicate ID")
        if rid < start or rid >= stop or (seen and rid <= seen[-1]):
            raise ManifestError("parity IDs must be ordered and inside their chunk")
        seen.append(rid)
        triggers = _sequence(item["triggers"], "parity triggers")
        if (
            not triggers
            or any(type(value) is not str or value not in trigger_names for value in triggers)
            or triggers != sorted(set(triggers))
        ):
            raise ManifestError("parity triggers must be sorted, nonempty and unique")
        if (rid in fixed) != ("ordinary" in triggers):
            raise ManifestError("fixed ordinary parity audit IDs differ")
        scale = _finite_number(item["max_abs_outcome"], "parity max outcome", nonnegative=True)
        parsed: dict[str, dict[str, Any]] = {}
        for name in ("batch", "scalar", "cr1"):
            value = _mapping(item[name], f"parity {name}")
            variance_name = "cr1_variance" if name == "cr1" else "cr2_variance"
            _exact_keys(value, (result_keys - {"cr2_variance"}) | {variance_name}, f"parity {name}")
            status = value["status"]
            if status != "EMITTED" and status not in manifest["refusals"]:
                raise ManifestError("parity status is unknown")
            if status == "EMITTED":
                for field in (numeric - {"cr2_variance"}) | {variance_name}:
                    number = _finite_number(value[field], f"parity {name} {field}")
                    if (
                        field
                        in {variance_name, "nu", "sample_variance", "design_effect", "effective_n"}
                        and number <= 0.0
                    ):
                        raise ManifestError("emitted parity numeric must be positive")
                if any(
                    type(value[field]) is not bool
                    for field in ("coverage", "lower_miss", "upper_miss")
                ):
                    raise ManifestError("emitted parity decisions must be booleans")
                if (
                    sum(bool(value[field]) for field in ("coverage", "lower_miss", "upper_miss"))
                    != 1
                ):
                    raise ManifestError("emitted parity decisions do not partition")
            elif any(value[field] is not None for field in value if field != "status"):
                raise ManifestError("refused parity must have null numbers and decisions")
            parsed[name] = value
        batch, scalar = parsed["batch"], parsed["scalar"]
        if (
            batch["status"] != scalar["status"]
            or (batch["status"] == "EMITTED") != (rid in emitted)
            or (batch["status"] != "EMITTED") != (rid in refusal_status)
            or (rid in refusal_status and batch["status"] != refusal_status[rid])
        ):
            raise ManifestError("parity status differs from base event partition")
        if batch["status"] == "EMITTED":
            variance_scale = scale * scale
            if not math.isfinite(variance_scale):
                raise ManifestError("parity scaled variance tolerance is non-finite")
            for field in numeric:
                absolute = (
                    1e-14 * variance_scale
                    if field in {"cr2_variance", "sample_variance"}
                    else 1e-14 * scale
                    if field in {"mean", "raw_lower", "raw_upper"}
                    else 1e-12
                )
                a, b = float(batch[field]), float(scalar[field])
                if (
                    not math.isfinite(absolute)
                    or abs(a - b) > 1e-11 * max(abs(a), abs(b)) + absolute
                ):
                    raise ManifestError("batch/scalar parity differs beyond frozen tolerance")
            for source in (batch, scalar):
                margin = float(t.ppf(0.975, float(source["nu"]))) * math.sqrt(
                    float(source["cr2_variance"])
                )
                for bound, calculated in (
                    ("raw_lower", float(source["mean"]) - margin),
                    ("raw_upper", float(source["mean"]) + margin),
                ):
                    absolute = 1e-14 * scale
                    saved = float(source[bound])
                    if (
                        not math.isfinite(calculated)
                        or abs(saved - calculated)
                        > 1e-11 * max(abs(saved), abs(calculated)) + absolute
                    ):
                        raise ManifestError(
                            "parity raw interval differs from mean, variance and nu"
                        )
            if any(
                batch[field] != scalar[field] for field in ("coverage", "lower_miss", "upper_miss")
            ):
                raise ManifestError("batch/scalar parity decisions differ")
            if (batch["coverage"], batch["lower_miss"], batch["upper_miss"]) != (
                rid in covered,
                rid in lower,
                rid in upper,
            ):
                raise ManifestError("parity decisions differ from event IDs")
            decisions = (
                float(batch["raw_lower"]) <= target <= float(batch["raw_upper"]),
                target < float(batch["raw_lower"]),
                target > float(batch["raw_upper"]),
            )
            if decisions != (batch["coverage"], batch["lower_miss"], batch["upper_miss"]):
                raise ManifestError("parity decision differs from raw interval and target")
            near_zero = (
                0.0 < float(batch["cr2_variance"]) <= 1e-12 * scale**2
                or 0.0 < float(batch["sample_variance"]) <= 1e-12 * scale**2
            )
            if ("near_zero" in triggers) != near_zero or "zero" in triggers:
                raise ManifestError("zero/near-zero parity trigger differs")
            critical = (
                abs(
                    abs((float(batch["mean"]) - target) / math.sqrt(float(batch["cr2_variance"])))
                    - float(t.ppf(0.975, float(batch["nu"])))
                )
                <= 1e-8
            )
            if ("t_critical" in triggers) != critical:
                raise ManifestError("t-critical parity trigger differs")
        elif "near_zero" in triggers or ("zero" in triggers) != (
            batch["status"] == "ZERO_VARIANCE"
        ):
            raise ManifestError("refusal parity trigger differs")
    if not fixed <= set(seen):
        raise ManifestError("fixed parity audit is incomplete")


def _candidate_support(
    manifest: dict[str, Any], phase: str, cell: dict[str, Any], floor: dict[str, Any]
) -> tuple[bool, bool, bool]:
    if cell["role"] == "dynamic":
        parameters = cell["parameters"]
        occupancies = tuple(
            _derived_dynamic_occupancy(parameters, parameters[name]) for name in ("h_loss", "h_win")
        )
    else:
        geometry = manifest["geometries"][cell["geometry_id"]]
        location = cell["parameters"].get("location")
        occupancies = (
            _derived_fixed_occupancy(
                geometry["entry_rule"],
                geometry["l"],
                geometry["entry_counts"],
                manifest["source_geometry"],
                location,
            ),
        )
    block_fail = False
    df_only_fail = False
    supported = True
    for occupancy in occupancies:
        blocks_ok = len(occupancy) >= floor["minimum_blocks"]
        nu_ok = satterthwaite_nu(occupancy) >= floor["minimum_nu"]
        supported &= blocks_ok and nu_ok
        block_fail |= not blocks_ok
        df_only_fail |= blocks_ok and not nu_ok
    return supported, block_fail, df_only_fail


def _verify_summary(
    manifest: dict[str, Any],
    raw: object,
    phase: str,
    cell_summaries: list[dict[str, Any]],
    verified_floor: tuple[int, float] | None,
) -> VerifiedPhaseResult:
    summary = _mapping(raw, "phase summary")
    _exact_keys(
        summary,
        {"cells", "candidate_results", "selected_floor", "parity_complete", "phase_verdict"},
        "phase summary",
    )
    if _canonical_bytes({"cells": summary["cells"]}) != _canonical_bytes({"cells": cell_summaries}):
        raise ManifestError("phase summary cell counts or CP checks differ from event partitions")
    if summary["parity_complete"] is not True:
        raise ManifestError("phase parity is incomplete")
    all_floors = manifest["candidate_floors"]
    if phase == "calibration":
        floors = all_floors
    else:
        assert verified_floor is not None
        floors = [
            floor
            for floor in all_floors
            if (floor["minimum_blocks"], float(floor["minimum_nu"])) == verified_floor
        ]
        if len(floors) != 1:
            raise ManifestError("externally verified validation floor is not frozen")
    candidate_results: list[dict[str, Any]] = []
    block_witness = False
    df_witness = False
    for floor in floors:
        eligible_cells = []
        for cell in manifest["phases"][phase]["cells"]:
            support, block_fail, df_only_fail = _candidate_support(manifest, phase, cell, floor)
            index = all_floors.index(floor)
            if support is not cell["expected_candidate_support"][index]:
                raise ManifestError("derived candidate floor mask differs from frozen cell")
            block_witness |= block_fail
            df_witness |= df_only_fail
            if support:
                eligible_cells.append(cell["id"])
        by_id = {cell["cell_id"]: cell for cell in cell_summaries}
        passed = all(
            check["passed"]
            for cell_id in eligible_cells
            for metric in by_id[cell_id]["metrics"]
            for check in metric["checks"].values()
        )
        candidate_results.append(
            {"floor": floor, "fixed_refusal_controls_passed": True, "passed": passed}
        )
    if phase == "calibration" and (not block_witness or not df_witness):
        raise ManifestError("candidate refusal controls lack actual block and df-only witnesses")
    if _canonical_bytes({"candidate_results": summary["candidate_results"]}) != _canonical_bytes(
        {"candidate_results": candidate_results}
    ):
        raise ManifestError("candidate floor controls or verdicts differ")
    selected = next((item["floor"] for item in candidate_results if item["passed"]), None)
    if _canonical_bytes({"floor": summary["selected_floor"]}) != _canonical_bytes(
        {"floor": selected}
    ):
        raise ManifestError("selected floor is not first passing or external validation floor")
    verdict = "PASSED" if selected is not None else "FAILED"
    if summary["phase_verdict"] != verdict:
        raise ManifestError("phase verdict differs from event-derived candidate gates")
    frozen_selected = (
        (selected["minimum_blocks"], float(selected["minimum_nu"]))
        if selected is not None
        else None
    )
    return VerifiedPhaseResult(phase, verdict, frozen_selected)


def validate_phase_result(
    manifest: dict[str, Any], result: dict[str, Any], expected_provenance: _ExpectedPhaseContext
) -> VerifiedPhaseResult:
    """Purely rederive the complete phase verdict from independently bound evidence."""
    if not isinstance(expected_provenance, _ExpectedPhaseContext):
        raise ManifestError("expected context has the wrong type")
    _validate_manifest(manifest)
    phase = expected_provenance.phase
    phase_data = manifest["phases"][phase]
    expected = _parse_canonical_json_bytes(
        expected_provenance.provenance_bytes, label="expected provenance"
    )
    _exact_keys(
        expected,
        {
            "manifest_sha256",
            "method_version",
            "selection_artifact_schema",
            "reviewed_commit",
            "invocation_commit",
            "protected_blobs",
            "review_attestation_sha256",
            "claim_sha256",
            "dependencies",
        },
        "expected provenance",
    )
    if expected["manifest_sha256"] != hashlib.sha256(_canonical_bytes(manifest)).hexdigest():
        raise ManifestError("manifest bytes do not match expected provenance hash")
    result = _mapping(result, "phase result")
    _exact_keys(
        result,
        {
            "schema",
            "protocol_version",
            "phase",
            "attempt",
            "provenance",
            "phase_contract",
            "chunks",
            "summary",
            "runtime",
            "terminal",
        },
        "phase result",
    )
    if (
        result["schema"] != "step6a2-calibration-result-v1"
        or result["protocol_version"] != PROTOCOL_VERSION
        or result["phase"] != phase
    ):
        raise ManifestError("phase result schema, protocol or phase differs")
    _verify_expected_identity(manifest, result, expected_provenance, expected)
    metrics = manifest["acceptance"]["metrics"]
    cells = phase_data["cells"]
    replicates = phase_data["replicates"]
    chunks = _sequence(result["chunks"], "phase chunks")
    cell_summaries: list[dict[str, Any]] = []
    cursor = 0
    for cell in cells:
        totals = {metric: [0] * 6 for metric in metrics}
        for chunk_id, start in enumerate(range(0, replicates, 256)):
            if cursor >= len(chunks):
                raise ManifestError("phase chunks omit a frozen cell or range")
            stop = min(start + 256, replicates)
            chunk = _mapping(chunks[cursor], f"chunk {cursor}")
            _exact_keys(
                chunk,
                {"cell_id", "chunk_id", "replicate_start", "replicate_stop_exclusive", "metrics"},
                f"chunk {cursor}",
            )
            if (
                type(chunk["cell_id"]) is not int
                or type(chunk["chunk_id"]) is not int
                or type(chunk["replicate_start"]) is not int
                or type(chunk["replicate_stop_exclusive"]) is not int
                or (
                    chunk["cell_id"],
                    chunk["chunk_id"],
                    chunk["replicate_start"],
                    chunk["replicate_stop_exclusive"],
                )
                != (cell["id"], chunk_id, start, stop)
            ):
                raise ManifestError("phase chunk cell, order or range differs")
            events = _sequence(chunk["metrics"], "chunk metrics")
            if len(events) != len(metrics):
                raise ManifestError("chunk lacks all ordered metrics")
            for metric, value in zip(metrics, events, strict=True):
                metric_events = _mapping(value, "metric events")
                _exact_keys(
                    metric_events,
                    {
                        "metric",
                        "emitted_ids",
                        "refusals",
                        "coverage_ids",
                        "lower_miss_ids",
                        "upper_miss_ids",
                        "joint_success_ids",
                        "parity",
                    },
                    "metric events",
                )
                base = {key: item for key, item in metric_events.items() if key != "parity"}
                counts = _validate_metric_event_partition(
                    manifest,
                    base,
                    replicate_start=start,
                    replicate_stop_exclusive=stop,
                    declared_metric=metric,
                )
                if any(
                    refusal["reason"] in {"BELOW_CALIBRATED_BLOCKS", "BELOW_CALIBRATED_DF"}
                    for refusal in base["refusals"]
                ):
                    raise ManifestError("candidate-floor refusal appears in base events")
                _verify_parity(manifest, metric_events, cell, metric, replicates, start, stop)
                for index, amount in enumerate(
                    (
                        counts.emitted,
                        counts.refusal_total,
                        counts.coverage_successes,
                        counts.lower_tail_misses,
                        counts.upper_tail_misses,
                        counts.joint_successes,
                    )
                ):
                    totals[metric][index] += amount
            cursor += 1
        cell_summaries.append(
            {
                "cell_id": cell["id"],
                "generated": replicates,
                "metrics": [
                    _recompute_metric_summary(
                        manifest,
                        phase=phase,
                        counts=_MetricEventCounts(metric, replicates, *totals[metric]),
                    )
                    for metric in metrics
                ],
            }
        )
    if cursor != len(chunks):
        raise ManifestError("phase chunks contain extra cells or ranges")
    return _verify_summary(
        manifest,
        result["summary"],
        phase,
        cell_summaries,
        expected_provenance.verified_calibration_floor,
    )


def _manifest_protected_paths(manifest: Mapping[str, Any]) -> tuple[str, ...]:
    integrity = _mapping(manifest["integrity"], "integrity")
    protected = _mapping(integrity["protected_paths"], "integrity.protected_paths")
    return tuple(
        str(protected[key]) for key in ("manifest", "manifest_digest", "harness", "estimator")
    )


def _cli() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("preflight", help="authenticate and recompute deterministic preflight")
    validation = subparsers.add_parser(
        "validate-selection", help="check the calibration selection gate"
    )
    validation.add_argument("artifact", type=Path)
    args = parser.parse_args()

    manifest = load_manifest()
    allowed = tuple(manifest["integrity"]["allowed_untracked"])
    if args.command == "validate-selection":
        artifact_path = args.artifact.resolve()
        try:
            relative_artifact = artifact_path.relative_to(_ROOT).as_posix()
        except ValueError as exc:
            raise ManifestError("selection artifact must be inside the repository") from exc
        allowed = (*allowed, relative_artifact)
    git_blobs = verify_protected_git_state(
        _ROOT,
        protected_paths=_manifest_protected_paths(manifest),
        allowed_untracked=allowed,
    )
    report = preflight_manifest(manifest)
    if args.command == "validate-selection":
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        path_map = manifest["integrity"]["protected_paths"]
        expected_blobs = {name: git_blobs[path] for name, path in path_map.items()}
        validate_selection_artifact(
            manifest,
            artifact,
            manifest_sha256=hashlib.sha256(_MANIFEST.read_bytes()).hexdigest(),
            protected_blobs=expected_blobs,
        )
        raise ManifestError(
            "validation remains locked until Task 3 verifies immutable calibration-result bytes"
        )
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(_cli())
