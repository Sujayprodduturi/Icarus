"""Offline deterministic preflight for the frozen Step-6a.2 synthetic protocol.

Task 1 intentionally contains no random generator or interval runner.  Its only jobs are to
authenticate the machine manifest, prove structural support, perform exact analytic binomial
preflight, and keep the held-back validation seed locked behind a complete calibration artifact.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import math
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from scipy.stats import beta, binom

PROTOCOL_VERSION: Final = "step6a2-synthetic-calibration-v1"
SELECTION_SCHEMA: Final = "step6a2-calibration-selection-v1"
METHOD_VERSION: Final = "entry-session-cr2-satterthwaite-v1"
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


def _canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")


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
