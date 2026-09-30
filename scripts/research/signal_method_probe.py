"""Synthetic-only uncertainty research; never imported by the Icarus product."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import subprocess
import sys
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import partial
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy.stats import norm
from scripts import signal_calibration as reference
from scripts.research.signal_uncertainty import Estimate
from scripts.research.signal_uncertainty import estimate as estimate

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "var/research/signal_uncertainty"
SEED = 2026093012
REPLICATES = 1024
DEADLINE = 300.0
METRICS = ("raw", "win", "synthetic_excess")
PROTECTED = (
    "icarus/engine/signalmetrics.py",
    "scripts/signal_calibration.py",
    "docs/plans/2026-09-26-step6a2-calibration-manifest.json",
    "docs/plans/2026-09-26-step6a2-calibration-manifest.sha256",
    "goal.yaml",
    "uv.lock",
)


def guard(seed: int, destination: Path) -> None:
    """Refuse unofficial addresses before writes/draws; no OS durability claim."""
    if type(seed) is not int or seed != SEED:
        raise ValueError("only the frozen non-reserved research seed is permitted")
    resolved = destination.resolve()
    if not resolved.is_relative_to(ROOT.resolve()) or resolved == ROOT.resolve():
        raise ValueError("output must be a child of the research scratch root")
    for parent in (destination, *destination.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("reparse output path refused")


def _json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    # Research checkpoint atomic replacement; no power-loss/official durability claim.
    target = path if exclusive else path.with_name(path.name + ".tmp")
    with target.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(payload, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    if not exclusive:
        os.replace(target, path)


def _ledger(destination: Path, state: str) -> None:
    with (destination / "ledger.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"state": state, "ts": datetime.now(UTC).isoformat()}) + "\n")


def reserve(destination: Path, protocol: dict[str, Any]) -> None:
    guard(SEED, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    _json(destination / "preregister.json", protocol, exclusive=True)
    _ledger(destination, "RESERVED_RESEARCH_ATTEMPT")


@dataclass(frozen=True)
class Trade:
    identifier: str
    entry: int
    holding: int
    raw: float
    benchmark: float | None


def observations(
    trades: tuple[Trade, ...], length: int, span: int
) -> dict[str, tuple[float, ...] | None]:
    if type(length) is not int or type(span) is not int or length <= 0 or span <= 0:
        raise ValueError("invalid declared source geometry")
    seen: set[str] = set()
    for trade in trades:
        if (
            type(trade) is not Trade
            or not isinstance(trade.identifier, str)
            or not trade.identifier
        ):
            raise ValueError("only identified synthetic records accepted")
        if trade.identifier in seen:
            raise ValueError("duplicate synthetic trade")
        seen.add(trade.identifier)
        if (
            type(trade.entry) is not int
            or not 0 <= trade.entry < span
            or type(trade.holding) is not int
            or trade.holding <= 0
            or not math.isfinite(trade.raw)
            or (trade.benchmark is not None and not math.isfinite(trade.benchmark))
        ):
            raise ValueError("invalid synthetic observation")
    raw = tuple(trade.raw for trade in trades)
    excess = (
        tuple(trade.raw - trade.benchmark for trade in trades if trade.benchmark is not None)
        if all(trade.benchmark is not None for trade in trades)
        else None
    )
    if excess is not None and not all(math.isfinite(value) for value in excess):
        raise ValueError("nonfinite paired excess")
    return {"raw": raw, "win": tuple(float(value > 0) for value in raw), "synthetic_excess": excess}


@dataclass
class Counts:
    generated: int = 0
    emitted: int = 0
    coverage: int = 0
    lower_miss: int = 0
    upper_miss: int = 0
    full_range: int = 0
    zero_exclusions: int = 0
    correct_direction: int = 0
    refusals: Counter[str] = field(default_factory=Counter)
    widths: list[float] = field(default_factory=list)
    clipped_widths: list[float] = field(default_factory=list)
    errors: list[float] = field(default_factory=list)

    def add(
        self,
        bounds: tuple[float, float] | None,
        mean: float | None,
        target: float,
        status: str,
        metric: str,
    ) -> None:
        if not math.isfinite(target) or metric not in METRICS:
            raise ValueError("invalid evaluation target/metric")
        if bounds is not None and (
            mean is None
            or not all(math.isfinite(v) for v in (*bounds, mean))
            or bounds[0] > bounds[1]
        ):
            raise ValueError("nonfinite/unordered emitted interval")
        self.generated += 1
        if bounds is None:
            self.refusals[status] += 1
            return
        assert mean is not None
        lo, hi = bounds
        self.emitted += 1
        self.coverage += int(lo <= target <= hi)
        self.lower_miss += int(target < lo)
        self.upper_miss += int(target > hi)
        self.widths.append(hi - lo)
        clipped = max(0.0, min(1.0, hi) - max(0.0, lo)) if metric == "win" else hi - lo
        self.clipped_widths.append(clipped)
        self.full_range += int(metric == "win" and clipped == 1.0)
        null = 0.5 if metric == "win" else 0.0
        self.zero_exclusions += int(lo > null or hi < null)
        self.correct_direction += int(
            (target > null and lo > null) or (target < null and hi < null)
        )
        self.errors.append(mean - target)

    def summary(self, family: int) -> dict[str, Any]:
        assert self.generated == self.emitted + sum(self.refusals.values())
        assert self.emitted == self.coverage + self.lower_miss + self.upper_miss
        alpha = 0.05 / family
        lower = reference.clopper_pearson_lower
        upper = reference.clopper_pearson_upper
        return {
            "generated": self.generated,
            "emitted": self.emitted,
            "refusals": dict(self.refusals),
            "coverage": self.coverage,
            "lower_miss": self.lower_miss,
            "upper_miss": self.upper_miss,
            "joint_success": self.coverage,
            "full_range": self.full_range,
            "zero_exclusions": self.zero_exclusions,
            "correct_direction": self.correct_direction,
            "median_width": float(np.median(self.widths)) if self.widths else None,
            "p90_width": float(np.quantile(self.widths, 0.9)) if self.widths else None,
            "median_clipped_width": float(np.median(self.clipped_widths)) if self.widths else None,
            "bias": math.fsum(self.errors) / self.emitted if self.emitted else None,
            "bounds": {
                "coverage_lower": lower(self.coverage, self.emitted, alpha)
                if self.emitted
                else 0.0,
                "lower_tail_upper": upper(self.lower_miss, self.emitted, alpha)
                if self.emitted
                else 1.0,
                "upper_tail_upper": upper(self.upper_miss, self.emitted, alpha)
                if self.emitted
                else 1.0,
                "emission_lower": lower(self.emitted, self.generated, alpha),
                "joint_lower": lower(self.coverage, self.generated, alpha),
            },
            "family": family,
            "absolute_emission_cutoff": "NOT_EVALUATED_PREFIX",
        }


def noninformative(counts: tuple[Counts, ...]) -> bool:
    emitted = sum(item.emitted for item in counts)
    return emitted > 0 and sum(item.full_range for item in counts) == emitted


def _hashes() -> dict[str, str]:
    paths = (
        *PROTECTED,
        "scripts/research/signal_uncertainty.py",
        "scripts/research/signal_method_probe.py",
        "docs/plans/2026-09-30-signal-method-research-design.md",
        "docs/plans/2026-09-30-signal-method-research-implementation.md",
    )
    return {path: hashlib.sha256((PROJECT / path).read_bytes()).hexdigest() for path in paths}


def _protocol() -> dict[str, Any]:
    return {
        "authority": "NONE",
        "seed": SEED,
        "replicates": REPLICATES,
        "deadline": DEADLINE,
        "profiles": list(range(1, 46)),
        "controls": [100001, 100002, 100003],
        "methods": ["original_cr2", "bartlett_fixed_b_development"],
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True
        ).strip(),
        "source_hashes": _hashes(),
        "python": sys.version,
        "numpy": np.__version__,
        "parent_pid": os.getpid(),
        "author": "Codex operator-authorized synthetic research",
        "candidate_version": "calendar-block-bartlett-fixed-b-v1-dev",
        "scipy": scipy.__version__,
        "platform": platform.platform(),
        "family_profiles": 1350,
        "family_controls": 90,
        "label": "SYNTHETIC_RESEARCH_NOT_CALIBRATION",
    }


def _evaluate(
    trades: tuple[Trade, ...],
    length: int,
    span: int,
    targets: dict[str, float],
    counts: dict[str, dict[str, Counts]],
) -> None:
    vectors = observations(trades, length, span)
    ids = tuple(trade.entry // length for trade in trades)
    for metric in METRICS:
        vector = vectors[metric]
        for method in counts:
            bounds = None
            mean = None
            status = "MISSING_BENCHMARK"
            if vector is not None:
                if method == "original_cr2":
                    value = reference._evaluate_full_batch(
                        np.array(vector), np.array(ids, dtype=np.int64), confidence=0.95
                    )
                    if isinstance(value, reference._FullBatchMoments):
                        bounds, mean = (value.raw_lower, value.raw_upper), value.mean
                        status = "EMITTED"
                    else:
                        status = value.reason.value
                else:
                    candidate = estimate(
                        vector, ids, first_block=0, last_block=(span - 1) // length
                    )
                    if isinstance(candidate, Estimate):
                        bounds, mean = (candidate.lower, candidate.upper), candidate.mean
                        status = "EMITTED"
                    else:
                        status = candidate.reason.value
            counts[method][metric].add(bounds, mean, targets[metric], status, metric)


def worker(destination: Path) -> None:
    guard(SEED, destination)
    protocol = json.loads((destination / "preregister.json").read_bytes())
    if (
        protocol["seed"] != SEED
        or protocol["parent_pid"] != os.getppid()
        or protocol["source_hashes"] != _hashes()
    ):
        raise ValueError("research startup provenance mismatch")
    manifest = reference.load_manifest()
    cells = manifest["phases"]["calibration"]["cells"]
    result: dict[str, Any] = {
        "authority": "NONE",
        "official_streams_drawn": False,
        "complete": False,
        "protocol": protocol,
        "profiles": [],
    }
    control_wins: dict[str, list[Counts]] = {method: [] for method in protocol["methods"]}
    began = time.monotonic()
    for item in [*cells, *({"id": identifier} for identifier in protocol["controls"])]:
        identifier = item["id"]
        counts = {
            method: {metric: Counts() for metric in METRICS} for method in protocol["methods"]
        }
        _ledger(destination, f"PROFILE_{identifier}_STARTED")
        for rid in range(REPLICATES):
            if time.monotonic() - began >= DEADLINE:
                raise TimeoutError("research worker deadline")
            if identifier < 100000:
                rep = reference._generate_replicate_core(
                    manifest,
                    phase="calibration",
                    cell_id=identifier,
                    replicate_id=rid,
                    draw_normal=partial(reference._test_or_rng, SEED, identifier),
                    draw_uniform=partial(reference._uniform_component_draw, SEED, identifier),
                )
                geometry = manifest["geometries"].get(item["geometry_id"])
                span = (
                    item["parameters"]["source_span"]
                    if item["role"] == "dynamic"
                    else len(geometry["entry_counts"]) * geometry["l"]
                )
                length = rep.block_length
                trades = tuple(
                    Trade(str(i), entry, holding, raw, bench)
                    for i, (entry, holding, raw, bench) in enumerate(
                        zip(
                            rep.entry_indices,
                            rep.holding_sessions,
                            rep.raw,
                            rep.benchmark,
                            strict=True,
                        )
                    )
                )
                targets = dict(
                    zip(
                        METRICS,
                        (
                            item["targets"]["raw_mean"],
                            item["targets"]["win_probability"],
                            item["targets"]["excess_mean"],
                        ),
                        strict=True,
                    )
                )
            else:
                mu = {100001: 0.0, 100002: 0.01, 100003: -0.01}[identifier]
                chunk, row = divmod(rid, 256)
                if row == 0:
                    generator = np.random.Generator(
                        np.random.PCG64(
                            np.random.SeedSequence(SEED, spawn_key=(identifier, 0, chunk))
                        )
                    )
                    control_draws = generator.standard_normal((256, 192))
                raw_values = control_draws[row] * 0.02 + mu
                length, span = 63, 24 * 63
                trades = tuple(
                    Trade(
                        str(i), (i // 8) * 63 + (2 * (i % 8) + 1) * 63 // 16, 21, float(raw), 0.002
                    )
                    for i, raw in enumerate(raw_values)
                )
                targets = {
                    "raw": mu,
                    "win": float(norm.cdf(mu / 0.02)),
                    "synthetic_excess": mu - 0.002,
                }
            _evaluate(trades, length, span, targets, counts)
            if rid % 256 == 255:
                reference._STREAM_CACHE.clear()
                result["in_progress"] = {
                    "profile": identifier,
                    "completed_replicates": rid + 1,
                    "possible_additional_inflight": 256,
                    "methods": {
                        method: {
                            metric: counts[method][metric].summary(
                                1350 if identifier < 100000 else 90
                            )
                            for metric in METRICS
                        }
                        for method in counts
                    },
                }
                _json(destination / "result.json", result)
                _ledger(destination, f"PROFILE_{identifier}_PREFIX_{rid + 1}")
        result.pop("in_progress", None)
        family = 1350 if identifier < 100000 else 90
        result["profiles"].append(
            {
                "id": identifier,
                "methods": {
                    method: {metric: counts[method][metric].summary(family) for metric in METRICS}
                    for method in counts
                },
            }
        )
        if identifier >= 100000:
            for method in counts:
                control_wins[method].append(counts[method]["win"])
        _json(destination / "result.json", result)
        print(f"profile {identifier} complete", flush=True)
    result["noninformative_controls"] = {
        method: noninformative(tuple(items)) for method, items in control_wins.items()
    }
    result["complete"], result["elapsed_seconds"] = True, time.monotonic() - began
    _json(destination / "result.json", result)


def _python_launch() -> tuple[str, dict[str, str] | None]:
    # CPython 3.12 Windows venv redirector spawns another process. Use its own
    # multiprocessing workaround so Popen owns the actual worker; checked 2026-09-30.
    # https://github.com/python/cpython/blob/v3.12.10/Lib/multiprocessing/popen_spawn_win32.py
    if os.name == "nt" and sys.prefix != sys.base_prefix:
        environment = os.environ.copy()
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        return str(vars(sys)["_base_executable"]), environment
    return sys.executable, None


def supervise(destination: Path, command: list[str] | None = None) -> None:
    began = time.monotonic()
    protocol = _protocol()
    reserve(destination, protocol)
    _ledger(destination, "STARTED")
    executable, environment = _python_launch()
    arguments = command or [
        executable,
        "-m",
        "scripts.research.signal_method_probe",
        "--worker",
        str(destination),
    ]
    process: subprocess.Popen[str] | None = None
    state = "ERROR"
    try:
        with (destination / "worker.log").open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                arguments,
                cwd=PROJECT,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=environment if command is None else None,
            )
            try:
                code = process.wait(timeout=max(0.0, DEADLINE - (time.monotonic() - began)))
            except subprocess.TimeoutExpired:
                state = "TIMEOUT"
                raise RuntimeError("research timeout; attempt retained") from None
        if code:
            raise RuntimeError("research failed; attempt retained")
        saved = json.loads((destination / "result.json").read_bytes())
        if saved.get("complete") is not True or saved.get("protocol") != protocol:
            raise RuntimeError("worker lacks complete matching research evidence")
        state = "COMPLETE"
    finally:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait()
        _ledger(destination, state)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path)
    args = parser.parse_args()
    if args.worker is not None:
        worker(args.worker)
    else:
        destination = ROOT / str(uuid.uuid4())
        supervise(destination)
        print(destination)


if __name__ == "__main__":
    main()
