"""Isolated calendar research evidence runner; no market data or official streams.

Preflight draws no experimental path. A sampled phase requires fresh feasibility,
exclusive claim, frozen sources and a supervised worker. Saved PASS files never
authorize confirmation. Windows limits are research monitoring/cancellation,
not an official hard-resource or crash-durability certificate.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import TracebackType
from typing import Any, TextIO

import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_compact as compact
from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_statistics as statistics
from scripts.research import signal_calendar_uncertainty as calendar

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT / "var/research/calendar_ratio"
PROTOCOL = "docs/plans/2026-10-01-signal-calendar-stress-confirmation-protocol.md"
PROTOCOL_HASH = "4d5d1749c799d124129ced0e3def82af91ca6f61fcccdcca7fe7a0f8fd044255"
AMENDMENT = "docs/plans/2026-10-02-calendar-research-resource-amendment.md"
AMENDMENT_HASH = "06ab50ce55fc0b6eb225f7959d7202ad8afc11835bc0c9bf5f367bd51bba9d7c"
NAMESPACE = "icarus/calendar-ratio-research/v1"
CAP = 2 * 1024**3
ARTIFACT_CAPS = {"development": CAP, "confirmation": 3 * 1024**3}
MEMORY_CAP = 2 * 1024**3
ENCODING = "canonical-atoms-decimal-coeff-base64/v1"
STREAM = "sha256-counter-u64x4-big-endian/v1"
REPLICATES = {"development": 512, "confirmation": 32768}
DEADLINES = {"development": 1800.0, "confirmation": 10800.0}
SOURCES = (
    PROTOCOL,
    AMENDMENT,
    "scripts/research/signal_calendar_runner.py",
    "scripts/research/signal_calendar_laws.py",
    "scripts/research/signal_calendar_statistics.py",
    "scripts/research/signal_calendar_compact.py",
    "scripts/research/signal_calendar_uncertainty.py",
    "scripts/research/signal_moment_uncertainty.py",
    "scripts/research/signal_bounded_uncertainty.py",
    "goal.yaml",
    "uv.lock",
)


def canonical(payload: object) -> bytes:
    return (
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf8")


def pack_decimal(value: str) -> list[object]:
    decimal = Decimal(value)
    if not decimal.is_finite() or str(decimal) != value or len(value) > 8192:
        raise ValueError("noncanonical/unbounded decimal")
    components = decimal.as_tuple()
    coefficient = int("".join(str(d) for d in components.digits))
    encoded = base64.b64encode(
        coefficient.to_bytes(max(1, (coefficient.bit_length() + 7) // 8), "big")
    )
    return [components.sign, components.exponent, encoded.decode("ascii")]


def unpack_decimal(value: object) -> str:
    if (
        type(value) is not list
        or len(value) != 3
        or type(value[0]) is not int
        or value[0] not in (0, 1)
        or type(value[1]) is not int
        or abs(value[1]) > 8192
        or type(value[2]) is not str
        or len(value[2]) > 8192
    ):
        raise ValueError("invalid packed decimal")
    blob = base64.b64decode(value[2], validate=True)
    coefficient = int.from_bytes(blob, "big")
    digits = tuple(int(d) for d in str(coefficient))
    result = str(Decimal((value[0], digits, value[1])))
    if pack_decimal(result) != value:
        raise ValueError("noncanonical packed decimal")
    return result


_DECIMALS = ("lower", "upper", "width_math", "width_display")


def pack_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: pack_decimal(v) if k in _DECIMALS and v is not None else v for k, v in result.items()}
        for result in results
    ]


def unpack_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {k: unpack_decimal(v) if k in _DECIMALS and v is not None else v for k, v in result.items()}
        for result in results
    ]


def source_manifest() -> dict[str, Any]:
    hashes = {p: hashlib.sha256((PROJECT / p).read_bytes()).hexdigest() for p in SOURCES}
    if hashes[PROTOCOL] != PROTOCOL_HASH:
        raise ValueError("frozen protocol mismatch")
    if hashes[AMENDMENT] != AMENDMENT_HASH:
        raise ValueError("frozen resource amendment mismatch")
    return {
        "schema": 1,
        "scope": "synthetic_only",
        "protocol": PROTOCOL_HASH,
        "resource_amendment": AMENDMENT_HASH,
        "sources": hashes,
        "python": sys.version,
        "platform": sys.platform,
        "psutil": psutil.__version__,
        "generator": laws.GENERATOR_VERSION,
        "encoding": ENCODING,
        "stream": STREAM,
        "namespace": NAMESPACE,
    }


def check_sources(manifest: dict[str, Any]) -> None:
    if manifest != source_manifest():
        raise ValueError("source/environment mismatch")


def _guard(destination: Path, root: Path) -> None:
    resolved = destination.resolve()
    if not resolved.is_relative_to(root.resolve()) or resolved == root.resolve():
        raise ValueError("research output escape")
    for parent in (destination, *destination.parents):
        if parent.is_symlink() or parent.is_junction():
            raise ValueError("reparse path refused")


def _exclusive(path: Path, payload: object) -> None:
    with path.open("xb") as stream:
        stream.write(canonical(payload))
        stream.flush()
        os.fsync(stream.fileno())


def claim(destination: Path, manifest: dict[str, Any], *, root: Path = ROOT) -> None:
    _guard(destination, root)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir()
    _exclusive(destination / "claim.json", {"ts": datetime.now(UTC).isoformat(), **manifest})


class EvidenceWriter:
    def __init__(self, path: Path, *, cap: int = CAP) -> None:
        if type(cap) is not int or cap <= 0:
            raise ValueError("invalid evidence cap")
        self.path, self.cap = path, cap
        self.bytes_written = 0
        self.stream: TextIO | None = None

    def __enter__(self) -> EvidenceWriter:
        self.stream = self.path.open("x", encoding="utf8", newline="\n")
        return self

    def write(self, payload: object) -> None:
        blob = canonical(payload)
        if len(blob) > 256 * 1024 or self.bytes_written + len(blob) > self.cap:
            raise ValueError("bounded evidence limit")
        if self.stream is None:
            raise ValueError("writer not open")
        self.stream.write(blob.decode("utf8"))
        self.bytes_written += len(blob)

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        assert self.stream is not None
        try:
            self.stream.flush()
            os.fsync(self.stream.fileno())
        finally:
            self.stream.close()


class Atoms:
    """Domain-separated counter words; rejection mapping has exact atom support.

    SHA256 stream independence is a computational experimental assumption, not
    mathematical IID certification. Each rejected word is counted and retained.
    """

    def __init__(self, seed: bytes, phase: str, family: str, replicate: int) -> None:
        if (
            type(seed) is not bytes
            or len(seed) != 32
            or phase not in REPLICATES
            or type(family) is not str
            or not family
            or type(replicate) is not int
            or not 0 <= replicate < REPLICATES[phase]
        ):
            raise ValueError("invalid atom address")
        self.prefix = canonical(
            [NAMESPACE, laws.GENERATOR_VERSION, STREAM, phase, family, replicate, seed.hex()]
        )
        self.words = 0
        self.block = b""

    def uniform(self, denominator: int) -> int:
        if type(denominator) is not int or not 1 <= denominator <= 512:
            raise ValueError("unsupported atom denominator")
        limit = (2**64 // denominator) * denominator
        for _ in range(1024):
            block_index, lane = divmod(self.words, 4)
            if lane == 0:
                self.block = hashlib.sha256(self.prefix + block_index.to_bytes(8, "big")).digest()
            self.words += 1
            word = int.from_bytes(self.block[lane * 8 : lane * 8 + 8], "big")
            if word < limit:
                return word % denominator
        raise ValueError("atom rejection ceiling")


def geometry_ready(identifier: str, n: int) -> bool:
    return laws.resource_bounds(identifier, n).eligible


def _path(family: laws.PathFamily, atoms: Atoms | None, *, pattern: int = 0) -> laws.InnovationPath:
    profile = laws.profile(family.profile_id)
    bounds = laws.resource_bounds(family.profile_id, family.n)
    if not bounds.eligible:
        raise ValueError("geometry resource refusal")
    s: list[int] = []
    q: list[bool] = []
    g: list[bool] = []
    j: list[Fraction] = []
    e1: list[int] = []
    e2: list[int] = []
    for index in range(bounds.first_index, bounds.last_index + 1):
        if atoms is None:
            # Fixed full-support invention; no experimental atom stream.
            s.append(
                1
                if pattern == 0
                or (index // 16 if pattern == 3 else (index * index + index) // 5) % 2
                else -1
            )
            q.append(True)
            g.append(True)
            j.append(profile.jump_atoms[(index % len(profile.jump_atoms)) if pattern else 0][0])
            e1.append(
                1 if (index // 9 if pattern >= 2 else (index * index + 3 * index) // 7) % 2 else -1
            )
            e2.append(
                1 if (index // 9 if pattern >= 2 else (index * index + 5 * index) // 11) % 2 else -1
            )
        else:
            s.append(1 if atoms.uniform(2) else -1)
            pv, pg = profile.p_volatility, profile.p_gate
            q.append(atoms.uniform(pv.denominator) < pv.numerator)
            g.append(atoms.uniform(pg.denominator) < pg.numerator)
            denominator = max(p.denominator for _, p in profile.jump_atoms)
            # Frozen atom denominators divide512 (or1); no biased float mapping.
            pick = atoms.uniform(denominator)
            edge = 0
            for value, probability in profile.jump_atoms:
                edge += int(probability * denominator)
                if pick < edge:
                    j.append(value)
                    break
            else:
                raise ValueError("jump probability partition")
            e1.append(1 if atoms.uniform(2) else -1)
            e2.append(1 if atoms.uniform(2) else -1)
    return laws.InnovationPath(
        bounds.first_index, tuple(s), tuple(q), tuple(g), tuple(j), tuple(e1), tuple(e2)
    )


def encode_path(family: laws.PathFamily, path: laws.InnovationPath) -> str:
    atoms = [v for v, _ in laws.profile(family.profile_id).jump_atoms]
    codes = bytes(
        (
            int(s == 1)
            | (int(q) << 1)
            | (int(g) << 2)
            | (int(e1 == 1) << 3)
            | (int(e2 == 1) << 4)
            | (atoms.index(j) << 5)
        )
        for s, q, g, j, e1, e2 in zip(
            path.s, path.q, path.g, path.j, path.epsilon1, path.epsilon2, strict=True
        )
    )
    return codes.hex()


def decode_path(family: laws.PathFamily, encoded: str) -> laws.InnovationPath:
    bounds = laws.resource_bounds(family.profile_id, family.n)
    atoms = [v for v, _ in laws.profile(family.profile_id).jump_atoms]
    if type(encoded) is not str or len(encoded) > 8192:
        raise ValueError("invalid path encoding")
    codes = bytes.fromhex(encoded)
    if len(codes) != bounds.last_index - bounds.first_index + 1:
        raise ValueError("path encoding span")
    if any(c >> 5 >= len(atoms) for c in codes):
        raise ValueError("path atom code")
    return laws.InnovationPath(
        bounds.first_index,
        tuple(1 if c & 1 else -1 for c in codes),
        tuple(bool(c & 2) for c in codes),
        tuple(bool(c & 4) for c in codes),
        tuple(atoms[c >> 5] for c in codes),
        tuple(1 if c & 8 else -1 for c in codes),
        tuple(1 if c & 16 else -1 for c in codes),
    )


def evaluate_reference(family: laws.PathFamily, path: laws.InnovationPath) -> list[dict[str, Any]]:
    fixture = laws.build(family.profile_id, family.n, path)
    outcomes = []
    for model, request, truth in zip(fixture.models, fixture.requests, fixture.truths, strict=True):
        result = calendar.estimate(fixture.source, model, request)
        if isinstance(result, calendar.CalendarRefusal):
            item = {
                "metric": model.metric.value,
                "truth": str(truth.theta),
                "reason": result.reason.value,
                "precision": False,
                "lower": None,
                "upper": None,
                "raw_mean": str(result.raw_mean),
                "count": result.total_count,
            }
        else:
            item = {
                "metric": model.metric.value,
                "truth": str(truth.theta),
                "reason": ""
                if isinstance(result, calendar.CalendarCandidate)
                else result.reason.value,
                "precision": isinstance(result, calendar.CalendarCandidate),
                "lower": str(result.candidate_lower),
                "upper": str(result.candidate_upper),
                "mean": str(result.mean),
                "sum": str(result.total_sum),
                "count": result.total_count,
                "width_math": str(result.mathematical_width_upper),
                "width_display": str(result.displayed_width_upper),
            }
        outcomes.append(item)
    return outcomes


def evaluate(family: laws.PathFamily, path: laws.InnovationPath) -> list[dict[str, Any]]:
    return compact.evaluate(family, path)


def _observe(count: statistics.Counts, result: dict[str, Any], family: laws.PathFamily) -> None:
    count.add(
        Decimal(result["lower"]) if result["lower"] is not None else None,
        Decimal(result["upper"]) if result["upper"] is not None else None,
        Fraction(result["truth"]),
        precision=result["precision"],
        reason=result["reason"],
        effect=1 if family.profile_id == "E+" else -1 if family.profile_id == "E-" else 0,
    )


def _report(counts: dict[str, statistics.Counts], phase: str) -> dict[str, Any]:
    summaries = {}
    passed = True
    for family in laws.path_families():
        for metric in family.metrics:
            key = f"{family.profile_id}:{family.n}:{metric.value}"
            count = counts[key]
            if count.replicates != REPLICATES[phase]:
                raise ValueError("incomplete cell")
            criteria = statistics.judge(
                count,
                confirmation=phase == "confirmation",
                effect=family.profile_id in ("E+", "E-"),
            )
            summaries[key] = {
                "counts": asdict(count),
                "formal": family.formal,
                "criteria": [
                    {
                        **asdict(c),
                        "threshold": str(c.threshold),
                        "certified_bound": str(c.certified_bound),
                    }
                    for c in criteria
                ],
            }
            if family.formal and not all(c.passed for c in criteria):
                passed = False
    return {
        "complete": True,
        "passed": passed,
        "scope": "restricted_artificial_family",
        "cells": summaries,
    }


@dataclass(frozen=True)
class Feasibility:
    manifest: dict[str, Any]
    maximum_seconds_per_path: float
    maximum_bytes_per_path: int
    projected_seconds: float
    projected_bytes: int
    nondegenerate_metrics: int
    eligible: bool
    marker: object | None = None


_MEASURED = object()


def preflight() -> Feasibility:
    """Measured full-support inventions and conservative projections, no RNG.

    A timing projection alone is NOT sufficient authority for a sampled study.
    Review must approve measured-vs-projected evidence under this exact source.
    """
    manifest = source_manifest()
    durations = []
    sizes = []
    projected_seconds = 0.0
    projected_bytes = 0
    arithmetic = 0
    witnessed: set[tuple[str, int, str]] = set()
    for family in laws.path_families():
        if not geometry_ready(family.profile_id, family.n):
            raise ValueError("pre-draw geometry refusal")
        family_times = []
        family_sizes = []
        for variant in range(12):
            start = time.perf_counter()
            path = _path(family, None, pattern=variant % 4)
            result = evaluate(family, path)
            encoded = encode_path(family, path)
            replay = evaluate(family, decode_path(family, encoded))
            if result != replay:
                raise ValueError("deterministic replay mismatch")
            packed = pack_results(result)
            payload = {
                "family": family.profile_id,
                "n": family.n,
                "replicate": 32767,
                "path": encoded,
                "words": 1000000,
                "results": packed,
            }
            if unpack_results(packed) != result:
                raise ValueError("decimal encoding replay mismatch")
            # Deterministic operation timing, no experimental stream construction.
            for counter in range(3 * len(path.s)):
                block = hashlib.sha256(b"x" * 300 + counter.to_bytes(8, "big")).digest()
                for lane in (0, 8, 16, 24):
                    int.from_bytes(block[lane : lane + 8], "big") % 50
            family_sizes.append(len(canonical(payload)))
            family_times.append(time.perf_counter() - start)
            arithmetic += sum(r["lower"] is not None for r in result)
            witnessed.update(
                (family.profile_id, family.n, r["metric"]) for r in result if r["lower"] is not None
            )
        durations.extend(family_times)
        sizes.extend(family_sizes)
        projected_seconds += max(family_times) * 4 * 32768
        projected_bytes += max(family_sizes) * 2 * 32768
    # Fourfold measured throughput and twofold largest serialized row margin.
    seconds = projected_seconds + 60
    size = projected_bytes + 16 * 1024**2
    return Feasibility(
        manifest,
        max(durations),
        max(sizes),
        seconds,
        size,
        arithmetic,
        len(witnessed) == sum(len(f.metrics) for f in laws.path_families())
        and seconds <= DEADLINES["confirmation"]
        and size <= ARTIFACT_CAPS["confirmation"],
        _MEASURED,
    )


_AUTHORITY = object()


@dataclass(frozen=True)
class _Confirmation:
    manifest: dict[str, Any]
    marker: object
    development_seed_commitment: str
    confirmation_seed_commitment: str


@dataclass(frozen=True)
class _VerifiedReport:
    report: dict[str, Any]
    manifest: dict[str, Any]
    phase: str
    seed_commitment: str
    marker: object
    digest: str


def confirmation_permission(
    report: object, manifest: dict[str, Any], *, confirmation_commitment: str | None = None
) -> _Confirmation:
    # This helper is only called by the parent after independent full replay;
    # never load report authority from an arbitrary saved PASS JSON.
    if (
        type(report) is not _VerifiedReport
        or report.marker is not _AUTHORITY
        or report.phase != "development"
        or report.manifest != manifest
        or hashlib.sha256(canonical(report.report)).hexdigest() != report.digest
        or report.report.get("complete") is not True
        or report.report.get("passed") is not True
    ):
        raise ValueError("failed/incomplete development")
    check_sources(manifest)
    if (
        type(confirmation_commitment) is not str
        or len(confirmation_commitment) != 64
        or any(c not in "0123456789abcdef" for c in confirmation_commitment)
        or confirmation_commitment == report.seed_commitment
    ):
        raise ValueError("missing/substituted independent confirmation commitment")
    return _Confirmation(manifest, _AUTHORITY, report.seed_commitment, confirmation_commitment)


def _worker(destination: Path) -> None:
    claim_data = json.loads((destination / "claim.json").read_bytes())
    manifest = claim_data["source"]
    check_sources(manifest)
    phase = claim_data["phase"]
    if phase not in REPLICATES:
        raise ValueError("invalid phase")
    seed = bytes.fromhex(claim_data["seed"])
    start = time.monotonic()
    with EvidenceWriter(
        destination / "paths.jsonl", cap=ARTIFACT_CAPS[phase] - 16 * 1024**2
    ) as writer:
        for family in laws.path_families():
            for replicate in range(REPLICATES[phase]):
                if time.monotonic() - start >= DEADLINES[phase]:
                    raise TimeoutError("worker deadline")
                atoms = Atoms(seed, phase, f"{family.profile_id}:{family.n}", replicate)
                path = _path(family, atoms)
                result = evaluate(family, path)
                writer.write(
                    {
                        "family": family.profile_id,
                        "n": family.n,
                        "replicate": replicate,
                        "path": encode_path(family, path),
                        "words": atoms.words,
                        "results": pack_results(result),
                    }
                )


def verify(
    destination: Path, phase: str, manifest: dict[str, Any], *, deadline: float | None = None
) -> _VerifiedReport:
    check_sources(manifest)
    if phase not in REPLICATES:
        raise ValueError("invalid verification phase")
    claim_data = json.loads((destination / "claim.json").read_bytes())
    if claim_data.get("phase") != phase or claim_data.get("source") != manifest:
        raise ValueError("claim phase/source mismatch")
    seed_text = claim_data.get("seed")
    if type(seed_text) is not str:
        raise ValueError("claim seed missing")
    seed = bytes.fromhex(seed_text)
    if len(seed) != 32 or claim_data.get("seed_commitment") != hashlib.sha256(seed).hexdigest():
        raise ValueError("claim seed commitment mismatch")
    families = laws.path_families()
    counts = {
        f"{f.profile_id}:{f.n}:{m.value}": statistics.Counts() for f in families for m in f.metrics
    }
    with (destination / "paths.jsonl").open("rb") as stream:
        for family in families:
            for replicate in range(REPLICATES[phase]):
                if deadline is not None and time.monotonic() >= deadline:
                    raise TimeoutError("verification deadline")
                if psutil.Process().memory_info().rss > MEMORY_CAP:
                    raise ValueError("verification working-set cap")
                line = stream.readline(256 * 1024 + 1)
                if not line or len(line) > 256 * 1024:
                    raise ValueError("incomplete/unbounded evidence")
                row = json.loads(line)
                if (row["family"], row["n"], row["replicate"]) != (
                    family.profile_id,
                    family.n,
                    replicate,
                ):
                    raise ValueError("duplicate/omitted/reordered path")
                path = decode_path(family, row["path"])
                atoms = Atoms(seed, phase, f"{family.profile_id}:{family.n}", replicate)
                expected_path = _path(family, atoms)
                if (
                    path != expected_path
                    or type(row["words"]) is not int
                    or row["words"] != atoms.words
                ):
                    raise ValueError("seed/word transcript mismatch")
                result = evaluate(family, path)
                if unpack_results(row["results"]) != result:
                    raise ValueError("source result replay mismatch")
                for item in result:
                    _observe(
                        counts[f"{family.profile_id}:{family.n}:{item['metric']}"], item, family
                    )
        if stream.read(1):
            raise ValueError("extra path evidence")
    check_sources(manifest)
    report = _report(counts, phase)
    return _VerifiedReport(
        report,
        manifest,
        phase,
        hashlib.sha256(seed).hexdigest(),
        None,
        hashlib.sha256(canonical(report)).hexdigest(),
    )


def _launch() -> tuple[str, dict[str, str] | None]:
    base = str(getattr(sys, "_base_executable", sys.executable))
    if sys.platform == "win32" and sys.executable != base:
        environment = os.environ.copy()
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        return base, environment
    return sys.executable, None


def run_phase(
    destination: Path,
    phase: str,
    seed: bytes,
    feasibility: Feasibility,
    *,
    authority: _Confirmation | None = None,
) -> _VerifiedReport:
    if phase not in REPLICATES or type(seed) is not bytes or len(seed) != 32:
        raise ValueError("invalid research phase seed")
    check_sources(feasibility.manifest)
    if not feasibility.eligible:
        raise ValueError("infeasible sampled study")
    if feasibility.marker is not _MEASURED:
        raise ValueError("no live measured feasibility")
    if phase == "confirmation" and (
        type(authority) is not _Confirmation
        or authority.marker is not _AUTHORITY
        or authority.manifest != feasibility.manifest
        or hashlib.sha256(seed).hexdigest() != authority.confirmation_seed_commitment
        or hashlib.sha256(seed).hexdigest() == authority.development_seed_commitment
    ):
        raise ValueError("no live verified development authority")
    # The preflight must also have independent exact-source review before calling.
    claim(
        destination,
        {
            "source": feasibility.manifest,
            "phase": phase,
            "seed": seed.hex(),
            "seed_commitment": hashlib.sha256(seed).hexdigest(),
            "feasibility": {k: v for k, v in asdict(feasibility).items() if k != "marker"},
        },
    )
    start = time.monotonic()
    process: subprocess.Popen[bytes] | None = None
    try:
        if phase == "confirmation":
            assert authority is not None
            family_id = hashlib.sha256(
                canonical([feasibility.manifest, authority.development_seed_commitment])
            ).hexdigest()
            family_claim = ROOT / "_confirmations" / (family_id + ".json")
            _guard(family_claim, ROOT)
            family_claim.parent.mkdir(parents=True, exist_ok=True)
            _exclusive(
                family_claim,
                {
                    "destination": str(destination),
                    "development_seed_commitment": authority.development_seed_commitment,
                },
            )
        stream_id = hashlib.sha256(canonical([NAMESPACE, STREAM, phase, seed.hex()])).hexdigest()
        stream_claim = ROOT / "_streams" / (stream_id + ".json")
        _guard(stream_claim, ROOT)
        stream_claim.parent.mkdir(parents=True, exist_ok=True)
        _exclusive(
            stream_claim,
            {
                "phase": phase,
                "destination": str(destination),
                "seed_commitment": hashlib.sha256(seed).hexdigest(),
            },
        )
        python, environment = _launch()
        with (destination / "worker.log").open("xb") as log:
            process = subprocess.Popen(
                [python, "-m", __name__, "--worker", str(destination)],
                cwd=PROJECT,
                env=environment,
                stdout=log,
                stderr=log,
            )
            while process.poll() is None:
                if time.monotonic() - start >= DEADLINES[phase]:
                    raise TimeoutError("parent research deadline")
                if (
                    sum(p.stat().st_size for p in destination.iterdir() if p.is_file())
                    > ARTIFACT_CAPS[phase]
                ):
                    raise ValueError("aggregate artifact cap")
                try:
                    usage = (
                        psutil.Process(process.pid).memory_info().rss
                        + psutil.Process().memory_info().rss
                    )
                except psutil.NoSuchProcess:
                    if process.poll() is not None:
                        break
                    raise
                if usage > MEMORY_CAP:
                    raise ValueError("monitored working-set cap")
                time.sleep(0.05)
            if process.returncode != 0:
                raise ValueError("worker failed; attempt cannot resume")
        verified = verify(
            destination, phase, feasibility.manifest, deadline=start + DEADLINES[phase]
        )
        report = verified.report
        if time.monotonic() - start >= DEADLINES[phase]:
            raise TimeoutError("final verification deadline")
        _exclusive(
            destination / "terminal.json",
            {"ts": datetime.now(UTC).isoformat(), "state": "COMPLETE", **report},
        )
        return replace(verified, marker=_AUTHORITY)
    except BaseException as error:
        if process is not None and process.poll() is None:
            process.kill()
            process.wait(timeout=10)
        _exclusive(
            destination / "error.json",
            {"ts": datetime.now(UTC).isoformat(), "state": "ERROR", "type": type(error).__name__},
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    if args.worker is not None:
        _guard(args.worker, ROOT)
        _worker(args.worker)
    elif args.preflight:
        print(
            canonical({k: v for k, v in asdict(preflight()).items() if k != "marker"}).decode(),
            end="",
        )
    else:
        parser.error("use --preflight; sampled phases need reviewed same-process orchestration")


if __name__ == "__main__":
    main()
