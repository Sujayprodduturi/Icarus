"""Independent exact artificial-calendar verification; serialized receipts carry no authority."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import subprocess
import threading
import time
from dataclasses import asdict, dataclass
from fractions import Fraction as F
from functools import cache
from pathlib import Path
from typing import Any

import numpy as np
import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_laws as laws

PROTOCOL_DIGEST = "130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71"
TEST = "icarus/calendar-score-research/test-fixture/v2"
PREFLIGHT = "icarus/calendar-score-research/test-preflight/v2"
GEOMETRIES = (
    ("P1", 2048, 2),
    ("P2", 2048, 2),
    ("P3", 16384, 9),
    ("P4", 8192, 5),
    ("P5", 32768, 2),
    ("P6", 32768, 2),
    ("P7", 131072, 40),
    ("E+", 2048, 2),
    ("E-", 2048, 2),
    ("L1", 2048, 2),
)
FULL_PATHS = tuple((p, n, 0) for p, n, _ in GEOMETRIES)
GRID = 10**60
MAX_RECORD = 256 * 1024
PATH_CAP = 8192
BUFFER_CAP = 16 * 1024**2
BATCH = 8192
MODULE = "scripts.research.signal_calendar_score_verify"
PROJECT = Path(__file__).resolve().parents[2]
SCOPE = "DETERMINISTIC_FIXTURE_ONLY"


class VerificationError(RuntimeError):
    """Incomplete/corrupt fixture, distinct from a complete statistical failure."""


@dataclass(frozen=True, slots=True)
class ReferenceResult:
    count: int
    raw: F
    wins: int
    excess: F
    rows: tuple[dict[str, object], ...]
    words: int


@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    binding: dict[str, str]
    paths: int
    metrics: int
    words: int
    payload_bytes: int
    seconds: float


def _geometry(profile_id: str, n: int) -> tuple[laws.LawProfile, int, int]:
    if type(profile_id) is not str or profile_id not in {p for p, _, _ in GEOMETRIES}:
        raise VerificationError("geometry")
    if type(n) is not int or not 2 <= n <= next(nn for p, nn, _ in GEOMETRIES if p == profile_id):
        raise VerificationError("geometry")
    profile = laws.profile(profile_id)
    halo = max(1, profile.volatility_memory)
    return profile, halo, n + halo + profile.hold


def _identity(value: dict[str, object]) -> dict[str, object]:
    required = {"namespace", "phase", "profile_id", "n", "replicate", "root"}
    if type(value) is not dict or set(value) != required:
        raise VerificationError("identity")
    namespace = value["namespace"]
    if namespace not in (TEST, PREFLIGHT) or type(namespace) is not str:
        raise VerificationError("identity")
    if value["phase"] != ("test_fixture" if namespace == TEST else "test_preflight"):
        raise VerificationError("identity")
    root = value["root"]
    if type(root) is not str or len(root) != 64 or any(c not in "0123456789abcdef" for c in root):
        raise VerificationError("identity")
    if type(value["replicate"]) is not int or not 0 <= value["replicate"] <= 32767:
        raise VerificationError("identity")
    _geometry(value["profile_id"], value["n"])  # type: ignore[arg-type]
    return dict(value)


def _digest(prefix: bytes, counter: int) -> bytes:
    return hashlib.sha256(prefix + counter.to_bytes(8, "big")).digest()


class ReferenceWords:
    """Separately framed SHA reconstruction with independently counted consumption."""

    def __init__(self, identity: dict[str, object]) -> None:
        identity = _identity(identity)
        fields = [
            identity["namespace"],
            "finite-calendar-law/v1",
            "sha256-counter-u64x4-big-endian/v2",
            identity["phase"],
            f"{identity['profile_id']}:{identity['n']}",
            identity["replicate"],
            identity["root"],
        ]
        self.prefix = (json.dumps(fields, separators=(",", ":"), ensure_ascii=True) + "\n").encode(
            "utf8"
        )
        self.counter = 0
        self.pending = b""
        self.words = 0

    def peek(self, count: int) -> bytes:
        if type(count) is not int or not 1 <= count <= 6 * BATCH:
            raise VerificationError("word_bound")
        blocks = max(0, (count * 8 - len(self.pending) + 31) // 32)
        if self.counter + blocks > 1 << 64:
            raise VerificationError("counter_overflow")
        if blocks:
            self.pending += b"".join(
                _digest(self.prefix, k) for k in range(self.counter, self.counter + blocks)
            )
            self.counter += blocks
        return self.pending[: count * 8]

    def consume(self, count: int) -> None:
        if type(count) is not int or not 1 <= count <= 6 * BATCH or count * 8 > len(self.pending):
            raise VerificationError("word_bound")
        self.pending = self.pending[count * 8 :]
        self.words += count

    def word(self) -> int:
        value = int.from_bytes(self.peek(1), "big")
        self.consume(1)
        return value

    def uniform(self, denominator: int) -> int:
        if type(denominator) is not int or not 1 <= denominator <= 1 << 64:
            raise VerificationError("denominator")
        boundary = (1 << 64) - (1 << 64) % denominator
        for _ in range(1024):
            value = self.word()
            if value < boundary:
                return value % denominator
        raise VerificationError("rejection_limit")


def reconstruct(identity: dict[str, object]) -> tuple[bytes, int]:
    identity = _identity(identity)
    profile, _, length = _geometry(identity["profile_id"], identity["n"])  # type: ignore[arg-type]
    stream = ReferenceWords(identity)
    partition = math.lcm(*(prob.denominator for _, prob in profile.jump_atoms))
    jump_edges = []
    edge = 0
    for _, probability in profile.jump_atoms:
        edge += int(probability * partition)
        jump_edges.append(edge)
    denominators = (
        2,
        profile.p_volatility.denominator,
        profile.p_gate.denominator,
        2,
        2,
        partition,
    )
    thresholds = (1, profile.p_volatility.numerator, profile.p_gate.numerator, 1, 1)
    output = bytearray(length)
    for start in range(0, length, BATCH):
        count = min(BATCH, length - start)
        try:
            words = np.frombuffer(stream.peek(6 * count), dtype=">u8").reshape(count, 6)
            accepted = all(
                boundary == 1 << 64 or not np.any(words[:, column] >= np.uint64(boundary))
                for column, denominator in enumerate(denominators)
                for boundary in [(1 << 64) - (1 << 64) % denominator]
            )
        except VerificationError as error:
            if str(error) != "counter_overflow":
                raise
            accepted = False
        if accepted:
            remainders = words % np.array(denominators, dtype=np.uint64)
            flags = remainders[:, :5] < np.array(thresholds, dtype=np.uint64)
            packed = (flags.astype(np.uint8) * np.array([1, 2, 4, 8, 16], dtype=np.uint8)).sum(
                axis=1, dtype=np.uint8
            )
            jump = np.searchsorted(
                np.array(jump_edges, dtype=np.uint64), remainders[:, 5], side="right"
            ).astype(np.uint8)
            packed |= jump * np.uint8(32)
            output[start : start + count] = packed.tobytes()
            stream.consume(6 * count)
        else:
            for row in range(start, start + count):
                atoms = [stream.uniform(d) for d in denominators]
                bits = sum(1 << k for k in range(5) if atoms[k] < thresholds[k])
                jump_index = next(k for k, edge in enumerate(jump_edges) if atoms[5] < edge)
                output[row] = bits + 32 * jump_index
    return bytes(output), stream.words


def trade_totals(profile_id: str, n: int, payload: bytes) -> tuple[int, F, int, F]:
    p, w, length = _geometry(profile_id, n)
    if type(payload) is not bytes or len(payload) != length:
        raise VerificationError("length")
    atoms = np.frombuffer(payload, dtype=np.uint8)
    if (
        np.any(atoms & 128)
        or np.any((atoms >> 5) >= len(p.jump_atoms))
        or (p.p_gate == 1 and np.any((atoms & 4) == 0))
    ):
        raise VerificationError("atom")
    coefficients = (
        p.delta - p.a / 3,
        p.a,
        p.gamma / p.hold,
        p.volatility_low,
        p.volatility_high,
        laws.BENCHMARK_CONSTANT,
        laws.BENCHMARK_PREVIOUS,
        laws.BENCHMARK_FORWARD / p.hold,
        *(jump for jump, _ in p.jump_atoms),
    )
    scale = math.lcm(*(v.denominator for v in coefficients))
    c = tuple(int(v * scale) for v in coefficients)
    base, a, factor_coefficient, low, high, bc, bp, bf = c[:8]
    # Every prefix is bounded by length; weighted outcome sums <=2*n*max_outcome.
    # Bound ALL common, benchmark, outcome/excess intermediates before array maths.
    common_bound = abs(base) + abs(a) + abs(factor_coefficient) * p.hold + max(map(abs, c[8:]))
    raw_bound = common_bound + max(abs(low), abs(high))
    benchmark_bound = abs(bc) + abs(bp) + abs(bf) * p.hold
    safe = max(length, scale, *map(abs, c), 2 * n * (raw_bound + benchmark_bound)) < 1 << 63
    if not safe:
        # Prefix lists are <=2*(131113)*36 bytes at frozen maximum geometry;
        # totals accumulate in Python integers, never whole-history outcome lists.
        prefix = [0]
        vol_prefix = [0]
        for atom in payload:
            prefix.append(prefix[-1] + (1 if atom & 1 else -1))
            vol_prefix.append(vol_prefix[-1] + int(bool(atom & 2)))
        count = wins = total_raw = total_excess = 0
        for i in range(w, w + n):
            previous = 1 if payload[i - 1] & 1 else -1
            entrants = (1 + int(previous == 1)) if payload[i] & 4 else 0
            factor = prefix[i + p.hold] - prefix[i]
            volatility = high if vol_prefix[i] - vol_prefix[i - p.volatility_memory] else low
            common = base + a * previous + factor_coefficient * factor + c[8 + (payload[i] >> 5)]
            benchmark = bc + bp * previous + bf * factor
            for symbol in range(entrants):
                outcome = common + (volatility if payload[i] & (8 << symbol) else -volatility)
                total_raw += outcome
                total_excess += outcome - benchmark
                wins += outcome > 0
            count += entrants
        return count, F(total_raw, scale), wins, F(total_excess, scale)
    signs_array = (2 * (atoms & 1).astype(np.int64)) - 1
    sign_prefix = np.concatenate(
        (np.array([0], dtype=np.int64), np.cumsum(signs_array, dtype=np.int64))
    )
    vol_prefix_array = np.concatenate(
        (np.array([0], dtype=np.int64), np.cumsum((atoms & 2) != 0, dtype=np.int64))
    )
    # Three source int64 arrays <=3.15MiB; <=8192 core dates per calculation.
    # Prefix construction plus <=16 overlapping chunk arrays stays below8MiB.
    total_raw = total_excess = count = wins = 0
    for start in range(w, w + n, BATCH):
        indexes = np.arange(start, min(start + BATCH, w + n), dtype=np.int64)
        previous_array = signs_array[indexes - 1]
        factor_array = sign_prefix[indexes + p.hold] - sign_prefix[indexes]
        high_state = (
            vol_prefix_array[indexes] - vol_prefix_array[indexes - p.volatility_memory]
        ) > 0
        volatility_array = np.where(high_state, high, low)
        common_array = (
            base
            + a * previous_array
            + factor_coefficient * factor_array
            + np.array(c[8:], dtype=np.int64)[atoms[indexes] >> 5]
        )
        benchmark_array = bc + bp * previous_array + bf * factor_array
        gate = (atoms[indexes] & 4) != 0
        for symbol in (0, 1):
            chosen = gate if symbol == 0 else gate & (previous_array == 1)
            outcomes_array = common_array + volatility_array * np.where(
                (atoms[indexes] & (8 << symbol)) != 0, 1, -1
            )
            total_raw += int(outcomes_array[chosen].sum(dtype=np.int64))
            total_excess += int((outcomes_array - benchmark_array)[chosen].sum(dtype=np.int64))
            count += int(np.count_nonzero(chosen))
            wins += int(np.count_nonzero(chosen & (outcomes_array > 0)))
    return count, F(total_raw, scale), wins, F(total_excess, scale)


@cache
def _truth_items(profile_id: str) -> tuple[tuple[str, F], ...]:
    p, _, _ = _geometry(profile_id, 2)
    high_probability = 1 - (1 - p.p_volatility) ** p.volatility_memory
    win = F(0)
    for previous, weight in ((-1, F(1, 3)), (1, F(2, 3))):
        for positive in range(p.hold + 1):
            forward = F(2 * positive - p.hold, p.hold)
            factor_weight = F(math.comb(p.hold, positive), 2**p.hold)
            for volatility, vol_weight in (
                (p.volatility_low, 1 - high_probability),
                (p.volatility_high, high_probability),
            ):
                for jump, jump_weight in p.jump_atoms:
                    center = p.delta - p.a / 3 + p.a * previous + p.gamma * forward + jump
                    for residual in (-1, 1):
                        win += (
                            weight
                            * factor_weight
                            * vol_weight
                            * jump_weight
                            * int(center + residual * volatility > 0)
                            / 2
                        )
    result = {"raw": p.delta, "synthetic_excess": p.delta - F(3, 1000) - F(3, 500) / 3}
    if profile_id not in ("E+", "E-"):
        result["win"] = win
    return tuple(result.items())


def exact_truths(profile_id: str) -> dict[str, F]:
    return dict(_truth_items(profile_id))


def support(profile_id: str, metric: str) -> tuple[F, F]:
    p, _, _ = _geometry(profile_id, 2)
    if metric == "win":
        return F(0), F(1)
    center = p.delta - p.a / 3
    a, gamma = p.a, p.gamma
    if metric == "synthetic_excess":
        center -= F(3, 1000)
        a -= F(3, 500)
        gamma -= F(1, 100)
    elif metric != "raw":
        raise VerificationError("metric")
    radius = abs(a) + abs(gamma) + max(p.volatility_low, p.volatility_high)
    jumps = [jump for jump, probability in p.jump_atoms if probability]
    return center - radius + min(jumps), center + radius + max(jumps)


def outward_interval(mean: F, square: F) -> tuple[F, F]:
    if type(mean) is not F or type(square) is not F or square < 0:
        raise VerificationError("interval")
    root = math.isqrt(square.numerator * GRID**2 // square.denominator)
    if root * root * square.denominator < square.numerator * GRID**2:
        root += 1
    radius = F(root, GRID)
    lower = (mean - radius) * GRID
    upper = (mean + radius) * GRID
    return F(lower.numerator // lower.denominator, GRID), F(
        -(-upper.numerator // upper.denominator), GRID
    )


def _pair(value: F | None) -> list[int] | None:
    return None if value is None else [value.numerator, value.denominator]


def calculate_rows(
    profile_id: str, n: int, count: int, raw: F, wins: int, excess: F
) -> tuple[dict[str, object], ...]:
    _geometry(profile_id, n)
    if (
        type(count) is not int
        or not 0 <= count <= 2 * n
        or type(wins) is not int
        or not 0 <= wins <= count
    ):
        raise VerificationError("count")
    if profile_id != "L1" and count < n:
        raise VerificationError("dense_count")
    if any(
        type(value) is not F
        or max(value.numerator.bit_length(), value.denominator.bit_length()) > 256
        for value in (raw, excess)
    ):
        raise VerificationError("numeric_bound")
    classes = next(c for p, _, c in GEOMETRIES if p == profile_id)
    truths = exact_truths(profile_id)
    metrics = (
        ("raw", "synthetic_excess")
        if profile_id in ("E+", "E-")
        else ("raw", "win", "synthetic_excess")
    )
    widths = {"raw": F(1, 50), "win": F(1, 5), "synthetic_excess": F(1, 50)}
    eligible = profile_id != "L1" and all(
        F(40 * classes, n) * (support(profile_id, m)[1] - support(profile_id, m)[0]) ** 2
        <= (widths[m] - F(4, GRID)) ** 2
        for m in metrics
    )
    reason = (
        ""
        if eligible
        else ("sparse_selection_unsupported" if profile_id == "L1" else "history_insufficient")
    )
    rows: list[dict[str, object]] = []
    for metric in metrics:
        if metric not in truths:
            raise VerificationError("truth_missing")
        total = {"raw": raw, "win": F(wins), "synthetic_excess": excess}[metric]
        lo, hi = support(profile_id, metric)
        if not lo * count <= total <= hi * count:
            raise VerificationError("support")
        lower = upper = None
        covered = lower_miss = upper_miss = detected = False
        if count:
            square = F(10 * classes * n, count**2) * (hi - lo) ** 2
            lower, upper = outward_interval(total / count, square)
            if eligible and upper - lower > widths[metric]:
                raise VerificationError("width")
            covered = lower <= truths[metric] <= upper
            lower_miss = truths[metric] < lower
            upper_miss = truths[metric] > upper
            detected = eligible and (
                (profile_id == "E+" and lower > 0) or (profile_id == "E-" and upper < 0)
            )
        rows.append(
            {
                "metric": metric,
                "truth": _pair(truths[metric]),
                "total": _pair(total),
                "count": count,
                "arithmetic": bool(count),
                "precision": eligible if count else False,
                "reason": reason if count else "zero_count|sparse_selection_unsupported",
                "lower": _pair(lower),
                "upper": _pair(upper),
                "covered": bool(covered),
                "lower_miss": bool(lower_miss),
                "upper_miss": bool(upper_miss),
                "detected": bool(detected),
            }
        )
    return tuple(rows)


def reference_path(
    profile_id: str, n: int, payload: bytes, identity: dict[str, object]
) -> ReferenceResult:
    identity = _identity(identity)
    if identity["profile_id"] != profile_id or identity["n"] != n:
        raise VerificationError("identity")
    expected, words = reconstruct(identity)
    if payload != expected:
        raise VerificationError("reconstruction")
    count, raw, wins, excess = trade_totals(profile_id, n, payload)
    return ReferenceResult(
        count, raw, wins, excess, calculate_rows(profile_id, n, count, raw, wins, excess), words
    )


def binomial_tail(n: int, p: F, k: int, *, lower: bool) -> F:
    if (
        type(n) is not int
        or not 1 <= n <= 32768
        or type(k) is not int
        or not 0 <= k <= n
        or type(p) is not F
        or not 0 < p < 1
        or p.denominator > 200
        or type(lower) is not bool
    ):
        raise VerificationError("binomial")
    a, d = p.numerator, p.denominator
    b = d - a
    term = math.comb(n, k) * a**k * b ** (n - k)
    total = term
    # lower=True means left tail P(X<=k); otherwise right tail P(X>=k).
    if lower:
        for j in range(k, 0, -1):
            term, remainder = divmod(term * j * b, (n - j + 1) * a)
            if remainder:
                raise VerificationError("binomial_recurrence")
            total += term
    else:
        for j in range(k, n):
            term, remainder = divmod(term * (n - j) * a, (j + 1) * b)
            if remainder:
                raise VerificationError("binomial_recurrence")
            total += term
    return F(total, d**n)


@cache
def check_frozen_cutoffs() -> None:
    for p, k, left in ((F(19, 20), 31258, False), (F(1, 100), 270, True), (F(9, 10), 29668, False)):
        accepted = binomial_tail(32768, p, k, lower=left)
        adjacent = binomial_tail(32768, p, k + 1 if left else k - 1, lower=left)
        if not accepted <= F(1, 1760) < adjacent:
            raise VerificationError("cutoff")


def fixed_gate(kind: str, count: int, n: int, phase: str) -> bool:
    if type(count) is not int or type(n) is not int or not 0 <= count <= n:
        raise VerificationError("gate")
    if phase == "validation":
        if n != 32768:
            raise VerificationError("phase_count")
        cutoffs = {"coverage": 31258, "joint": 31258, "tail": 270, "detection": 29668}
        if kind not in cutoffs:
            raise VerificationError("gate")
        return count <= cutoffs[kind] if kind == "tail" else count >= cutoffs[kind]
    if (
        phase != "development"
        or n != 8192
        or kind not in ("coverage", "joint", "tail", "detection")
    ):
        raise VerificationError("phase_count")
    threshold = F(1, 100) if kind == "tail" else F(9, 10) if kind == "detection" else F(19, 20)
    return F(count, n) <= threshold if kind == "tail" else F(count, n) >= threshold


def canonical(value: object) -> bytes:
    try:
        return (
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf8")
    except (TypeError, ValueError, OverflowError) as error:
        raise VerificationError("canonical") from error


def _hash(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _seal(record: dict[str, object]) -> dict[str, object]:
    # Canonical-copy mappings: no caller-owned dictionaries become trusted state.
    copied: dict[str, object] = json.loads(canonical(record))
    copied["digest"] = _hash(canonical(copied))
    return copied


def _unseal(record: dict[str, Any]) -> dict[str, Any]:
    copied = dict(record)
    digest = copied.pop("digest", None)
    if type(digest) is not str or digest != _hash(canonical(copied)):
        raise VerificationError("record_digest")
    return copied


def current_manifest() -> tuple[str, dict[str, Any]]:
    # Only primitive I/O/source-supervision helpers are shared, never math authority.
    from scripts.research import signal_calendar_score_study as io

    manifest = io.source_manifest()
    return manifest.digest, json.loads(canonical(manifest.payload))


def _paths(paths: tuple[tuple[str, int, int], ...]) -> tuple[tuple[str, int, int], ...]:
    if type(paths) is not tuple or not 1 <= len(paths) <= 10:
        raise VerificationError("path_order")
    previous = -1
    for entry in paths:
        if type(entry) is not tuple or len(entry) != 3:
            raise VerificationError("path_order")
        profile_id, n, replicate = entry
        if (
            type(profile_id) is not str
            or type(n) is not int
            or type(replicate) is not int
            or replicate != 0
        ):
            raise VerificationError("path_order")
        index = next(
            (i for i, (p, nn, _) in enumerate(GEOMETRIES) if (p, nn) == (profile_id, n)), None
        )
        if index is None or index <= previous:
            raise VerificationError("path_order")
        previous = index
    return paths


def _record(root: Path, name: str, record: dict[str, object]) -> None:
    from scripts.research import signal_calendar_score_study as io

    io._exclusive_record(root / name, _seal(record), root=root)


def _load(root: Path, name: str) -> dict[str, Any]:
    from scripts.research import signal_calendar_score_study as io

    path = io._guard_path(root / name, root, existing=True)
    rows = list(io.read_canonical_records(path, total_cap=MAX_RECORD, record_cap=MAX_RECORD))
    if len(rows) != 1:
        raise VerificationError("record_count")
    return _unseal(rows[0])


def _cells() -> dict[str, Any]:
    return {
        "metric_cells": {},
        "joint_cells": {},
        "diagnostics": {},
        "phase_verdict": "UNAVAILABLE_DETERMINISTIC_FIXTURE",
        "one_sided_statements": 88,
    }


def _accumulate(summary: dict[str, Any], profile_id: str, rows: list[dict[str, Any]]) -> None:
    if profile_id == "L1":
        for row in rows:
            cell = summary["diagnostics"].setdefault(
                f"L1:{row['metric']}",
                {"R": 0, "A": 0, "P": 0, "C": 0, "Tlo": 0, "Thi": 0, "D": 0, "reasons": {}},
            )
            cell["R"] += 1
            for key, field in (
                ("A", "arithmetic"),
                ("P", "precision"),
                ("C", "covered"),
                ("Tlo", "lower_miss"),
                ("Thi", "upper_miss"),
                ("D", "detected"),
            ):
                cell[key] += int(row[field])
            reason = row["reason"]
            cell["reasons"][reason] = cell["reasons"].get(reason, 0) + 1
        return
    joint = summary["joint_cells"].setdefault(profile_id, {"R": 0, "C": 0})
    joint["R"] += 1
    joint["C"] += int(
        all(row["arithmetic"] and row["precision"] and row["covered"] for row in rows)
    )
    for row in rows:
        cell = summary["metric_cells"].setdefault(
            f"{profile_id}:{row['metric']}",
            {"R": 0, "A": 0, "P": 0, "C": 0, "Tlo": 0, "Thi": 0, "D": 0},
        )
        cell["R"] += 1
        for key, field in (
            ("A", "arithmetic"),
            ("P", "precision"),
            ("C", "covered"),
            ("Tlo", "lower_miss"),
            ("Thi", "upper_miss"),
            ("D", "detected"),
        ):
            cell[key] += int(row[field])


def phase_decision(summary: dict[str, Any], phase: str) -> str:
    if phase not in ("development", "validation"):
        raise VerificationError("phase")
    n = 8192 if phase == "development" else 32768
    metric_keys = {
        f"{p}:{m}"
        for p, _, _ in GEOMETRIES
        if p != "L1"
        for m in (
            ("raw", "synthetic_excess") if p in ("E+", "E-") else ("raw", "win", "synthetic_excess")
        )
    }
    joint_keys = {p for p, _, _ in GEOMETRIES if p != "L1"}
    if (
        set(summary.get("metric_cells", {})) != metric_keys
        or set(summary.get("joint_cells", {})) != joint_keys
    ):
        raise VerificationError("incomplete")
    diagnostics = summary.get("diagnostics", {})
    if set(diagnostics) != {"L1:raw", "L1:win", "L1:synthetic_excess"}:
        raise VerificationError("incomplete")
    for cell in diagnostics.values():
        if set(cell) != {"R", "A", "P", "C", "Tlo", "Thi", "D", "reasons"} or any(
            type(cell[k]) is not int or not 0 <= cell[k] <= n
            for k in ("R", "A", "P", "C", "Tlo", "Thi", "D")
        ):
            raise VerificationError("incomplete")
        if (
            cell["R"] != n
            or not 0 <= cell["P"] <= cell["A"] <= n
            or cell["C"] + cell["Tlo"] + cell["Thi"] != cell["A"]
        ):
            raise VerificationError("incomplete")
        reasons = cell["reasons"]
        if (
            type(reasons) is not dict
            or any(
                type(k) is not str or type(v) is not int or not 0 <= v <= n
                for k, v in reasons.items()
            )
            or sum(reasons.values()) != n
        ):
            raise VerificationError("incomplete")
    passing = True
    for key, cell in summary["metric_cells"].items():
        if set(cell) != {"R", "A", "P", "C", "Tlo", "Thi", "D"} or any(
            type(v) is not int or not 0 <= v <= n for v in cell.values()
        ):
            raise VerificationError("incomplete")
        if (
            cell["R"] != n
            or cell["A"] != n
            or cell["P"] != n
            or cell["C"] + cell["Tlo"] + cell["Thi"] != n
        ):
            raise VerificationError("incomplete")
        passing &= fixed_gate("coverage", cell["C"], n, phase)
        passing &= fixed_gate("tail", cell["Tlo"], n, phase) and fixed_gate(
            "tail", cell["Thi"], n, phase
        )
        if key.startswith(("E+:", "E-:")):
            passing &= fixed_gate("detection", cell["D"], n, phase)
    for cell in summary["joint_cells"].values():
        if (
            set(cell) != {"R", "C"}
            or any(type(v) is not int or not 0 <= v <= n for v in cell.values())
            or cell["R"] != n
        ):
            raise VerificationError("incomplete")
        passing &= fixed_gate("joint", cell["C"], n, phase)
    return "PASS" if passing else "FAILED"


def _fixture_identity(namespace: str, profile_id: str, n: int, replicate: int) -> dict[str, object]:
    return {
        "namespace": namespace,
        "phase": "test_preflight" if namespace == PREFLIGHT else "test_fixture",
        "profile_id": profile_id,
        "n": n,
        "replicate": replicate,
        "root": "0" * 64,
    }


def write_fixture(
    root: Path, *, paths: tuple[tuple[str, int, int], ...] = FULL_PATHS, namespace: str = PREFLIGHT
) -> str:
    from scripts.research import signal_calendar_score_study as io

    if type(namespace) is not str or namespace not in (TEST, PREFLIGHT):
        raise VerificationError("identity")
    paths = _paths(paths)
    if root.exists():
        raise VerificationError("destination")
    # Guard every lexical ancestor BEFORE creating the new leaf.
    io._guard_path(root, root.parent)
    root.mkdir()
    manifest_digest, manifest_payload = current_manifest()
    phase = "test_preflight" if namespace == PREFLIGHT else "test_fixture"
    claim: dict[str, object] = {
        "schema": 1,
        "scope": SCOPE,
        "namespace": namespace,
        "phase": phase,
        "root": "0" * 64,
        "paths": [list(p) for p in paths],
        "protocol_digest": PROTOCOL_DIGEST,
        "source_manifest_digest": manifest_digest,
        "manifest": manifest_payload,
    }
    _record(root, "fixture-claim.json", claim)
    claim_digest = _hash((root / "fixture-claim.json").read_bytes())
    summary = _cells()
    offset = words = metrics = 0
    payload_stream = io._open_exclusive(root / "fixture-payload.bin")
    payload_error: BaseException | None = None
    try:
        with io.CanonicalRecordWriter(
            root / "fixture-index.jsonl", total_cap=BUFFER_CAP, record_cap=PATH_CAP
        ) as writer:
            for profile_id, n, replicate in paths:
                item = io.spec(profile_id)
                stream = io.CounterStream(
                    namespace=namespace,
                    phase=phase,
                    profile_id=profile_id,
                    n=n,
                    replicate=replicate,
                    root=bytes(32),
                )
                payload = io.generate_payload(item, stream)
                production_result = io.evaluate_payload(item, payload)
                rows = io._pack_result(production_result)
                for row, result in zip(rows, production_result.rows, strict=True):
                    row.update(
                        {
                            "covered": result.covered,
                            "lower_miss": result.lower_miss,
                            "upper_miss": result.upper_miss,
                        }
                    )
                row = {
                    "schema": 1,
                    "phase": phase,
                    "profile_id": profile_id,
                    "n": n,
                    "replicate": replicate,
                    "offset": offset,
                    "size": len(payload),
                    "payload_sha256": _hash(payload),
                    "words": stream.words_consumed,
                    "results": rows,
                    "claim_digest": claim_digest,
                }
                if len(canonical(row)) > PATH_CAP:
                    raise VerificationError("path_metadata_cap")
                io._write_all(payload_stream, payload)
                writer.write(row)
                _accumulate(summary, profile_id, rows)
                offset += len(payload)
                words += stream.words_consumed
                metrics += len(rows)
        payload_stream.flush()
        os.fsync(payload_stream.fileno())
    except BaseException as error:
        payload_error = error
        raise
    finally:
        try:
            payload_stream.close()
        except BaseException as error:
            if payload_error is None:
                raise VerificationError("close_failure") from error
    if current_manifest()[0] != manifest_digest:
        raise VerificationError("source_drift")
    payload_digest = io._hash_file(root / "fixture-payload.bin", expected_size=offset)
    index_digest = io._hash_file(root / "fixture-index.jsonl")
    _record(
        root,
        "fixture-report.json",
        {
            "schema": 1,
            "scope": SCOPE,
            "summary": summary,
            "claim_digest": claim_digest,
            "payload_digest": payload_digest,
            "index_digest": index_digest,
        },
    )
    report_digest = io._hash_file(root / "fixture-report.json")
    _record(
        root,
        "fixture-terminal.json",
        {
            "schema": 1,
            "scope": SCOPE,
            "state": "FIXTURE_COMPLETE",
            "claim_digest": claim_digest,
            "payload_digest": payload_digest,
            "index_digest": index_digest,
            "report_digest": report_digest,
            "paths": len(paths),
            "metrics": metrics,
            "words": words,
            "payload_bytes": offset,
        },
    )
    return manifest_digest


def _verify_fixture(
    root: Path,
    expected_manifest: str,
    expected_paths: tuple[tuple[str, int, int], ...],
    receipt_name: str | None,
) -> VerificationReceipt:
    from scripts.research import signal_calendar_score_study as io

    started = time.perf_counter()
    paths = _paths(expected_paths)
    actual_manifest, manifest_payload = current_manifest()
    if actual_manifest != expected_manifest:
        raise VerificationError("source_drift")
    claim = _load(root, "fixture-claim.json")
    namespace = claim.get("namespace")
    if namespace not in (TEST, PREFLIGHT) or type(namespace) is not str:
        raise VerificationError("identity")
    phase = "test_preflight" if namespace == PREFLIGHT else "test_fixture"
    expected_claim = {
        "schema": 1,
        "scope": SCOPE,
        "namespace": namespace,
        "phase": phase,
        "root": "0" * 64,
        "paths": [list(p) for p in paths],
        "protocol_digest": PROTOCOL_DIGEST,
        "source_manifest_digest": actual_manifest,
        "manifest": manifest_payload,
    }
    if canonical(claim) != canonical(expected_claim):
        raise VerificationError("claim")
    claim_digest = io._hash_file(root / "fixture-claim.json")
    terminal = _load(root, "fixture-terminal.json")
    report = _load(root, "fixture-report.json")
    payload_path = io._guard_path(root / "fixture-payload.bin", root, existing=True)
    index_path = io._guard_path(root / "fixture-index.jsonl", root, existing=True)
    expected_bytes = sum(_geometry(p, n)[2] for p, n, _ in paths)
    if payload_path.stat().st_size != expected_bytes or expected_bytes > BUFFER_CAP:
        raise VerificationError("payload_size")
    if index_path.stat().st_size > len(paths) * PATH_CAP:
        raise VerificationError("path_metadata_cap")
    check_frozen_cutoffs()
    summary = _cells()
    index_rows = iter(
        io.read_canonical_records(index_path, total_cap=len(paths) * PATH_CAP, record_cap=PATH_CAP)
    )
    payload_hasher = hashlib.sha256()
    offset = words = metrics = 0
    with payload_path.open("rb") as stream:
        for profile_id, n, replicate in paths:
            row = next(index_rows, None)
            if row is None:
                raise VerificationError("missing_index")
            length = _geometry(profile_id, n)[2]
            # Exact canonical headers discriminate bool from int BEFORE allocation.
            header = {
                k: v for k, v in row.items() if k not in ("results", "words", "payload_sha256")
            }
            expected_header = {
                "schema": 1,
                "phase": phase,
                "profile_id": profile_id,
                "n": n,
                "replicate": replicate,
                "offset": offset,
                "size": length,
                "claim_digest": claim_digest,
            }
            if canonical(header) != canonical(expected_header):
                raise VerificationError("ordered_identity")
            payload = stream.read(length)
            if len(payload) != length:
                raise VerificationError("truncated_payload")
            result = reference_path(
                profile_id, n, payload, _fixture_identity(namespace, profile_id, n, replicate)
            )
            expected_row = {
                **expected_header,
                "payload_sha256": _hash(payload),
                "words": result.words,
                "results": list(result.rows),
            }
            if canonical(row) != canonical(expected_row):
                raise VerificationError("reference_mismatch")
            payload_hasher.update(payload)
            _accumulate(summary, profile_id, list(result.rows))
            offset += length
            words += result.words
            metrics += len(result.rows)
        if stream.read(1) or next(index_rows, None) is not None:
            raise VerificationError("trailing_evidence")
    payload_digest = payload_hasher.hexdigest()
    index_digest = io._hash_file(index_path)
    expected_report = {
        "schema": 1,
        "scope": SCOPE,
        "summary": summary,
        "claim_digest": claim_digest,
        "payload_digest": payload_digest,
        "index_digest": index_digest,
    }
    if canonical(report) != canonical(expected_report):
        raise VerificationError("report")
    report_digest = io._hash_file(root / "fixture-report.json")
    expected_terminal = {
        "schema": 1,
        "scope": SCOPE,
        "state": "FIXTURE_COMPLETE",
        "claim_digest": claim_digest,
        "payload_digest": payload_digest,
        "index_digest": index_digest,
        "report_digest": report_digest,
        "paths": len(paths),
        "metrics": metrics,
        "words": words,
        "payload_bytes": offset,
    }
    if canonical(terminal) != canonical(expected_terminal):
        raise VerificationError("terminal")
    binding = {
        "protocol_digest": PROTOCOL_DIGEST,
        "source_manifest_digest": actual_manifest,
        "attempt_id": "deterministic_fixture",
        "session_id": claim_digest,
        "phase": phase,
        "seed_commitment": _hash(bytes(32)),
        "payload_digest": payload_digest,
        "index_digest": index_digest,
        "results_digest": index_digest,
        "terminal_digest": io._hash_file(root / "fixture-terminal.json"),
    }
    if current_manifest()[0] != actual_manifest:
        raise VerificationError("source_drift")
    receipt = VerificationReceipt(
        binding, len(paths), metrics, words, offset, time.perf_counter() - started
    )
    if receipt_name is not None:
        candidate_name = {
            "verified.json": "verification-candidate.json",
            "verified-primary.json": "verification-primary-candidate.json",
            "verified-reviewer.json": "verification-reviewer-candidate.json",
        }[receipt_name]
        record: dict[str, object] = {
            "schema": 1,
            "scope": SCOPE,
            "record_role": "INERT_UNTIL_EXCLUSIVE_PUBLICATION",
            "publication_name": receipt_name,
            **asdict(receipt),
        }
        # A failed durable write/source/resource check retains only an inert candidate.
        _record(root, candidate_name, record)
        if current_manifest()[0] != actual_manifest:
            raise VerificationError("source_drift")
        check_resources(
            time.perf_counter() - started,
            psutil.Process().memory_info().rss,
            0.0,
            psutil.disk_usage(str(root)).free,
        )
        candidate = io._guard_path(root / candidate_name, root, existing=True)
        destination = io._guard_path(root / receipt_name, root)
        receipt_bytes = canonical(_seal(record))
        if io._hash_file(candidate, expected_size=len(receipt_bytes)) != _hash(receipt_bytes):
            raise VerificationError("candidate_drift")
        # Atomic exclusive namespace publication never overwrites an existing receipt.
        # No fallible checks follow publication; directory/power-loss sync is unclaimed.
        os.link(candidate, destination, follow_symlinks=False)
    elif current_manifest()[0] != actual_manifest:
        raise VerificationError("source_drift")
    return receipt


def verify_fixture(
    root: Path,
    *,
    expected_manifest: str,
    expected_paths: tuple[tuple[str, int, int], ...],
    receipt_name: str | None = "verified.json",
) -> VerificationReceipt:
    from scripts.research import signal_calendar_score_study as io

    if receipt_name not in (
        None,
        "verified.json",
        "verified-primary.json",
        "verified-reviewer.json",
    ):
        raise VerificationError("receipt_name")
    try:
        return _verify_fixture(root, expected_manifest, expected_paths, receipt_name)
    except (io.StudyError, OSError) as error:
        raise VerificationError(
            str(error) if isinstance(error, io.StudyError) else "io_failure"
        ) from error


def benchmark_geometry() -> tuple[tuple[str, int, int], ...]:
    return FULL_PATHS


def check_resources(elapsed: float, rss: int, heartbeat_age: float, free: int) -> None:
    from scripts.research import signal_calendar_score_study as io

    try:
        io.check_supervision(
            io.SupervisionLimits(600.0, 2 * 1024**3, 30.0, 20 * 1024**3),
            elapsed,
            rss,
            heartbeat_age,
            free,
        )
    except io.StudyError as error:
        raise VerificationError(str(error)) from error


def _sample(root: Path, started: float, rss: int, *, require_heartbeat: bool) -> None:
    if psutil.Process().memory_info().rss > 512 * 1024**2:
        raise VerificationError("parent_memory")
    log = root / "benchmark-worker.log"
    if log.exists() and log.stat().st_size > BUFFER_CAP:
        raise VerificationError("worker_log_cap")
    heartbeat = root / "heartbeat.json"
    if require_heartbeat and not heartbeat.exists():
        raise VerificationError("heartbeat")
    age = (
        time.time() - heartbeat.stat().st_mtime
        if heartbeat.exists()
        else time.monotonic() - started
    )
    check_resources(
        time.monotonic() - started, rss, max(0.0, age), psutil.disk_usage(str(root)).free
    )


def _supervise(process: subprocess.Popen[bytes], root: Path) -> int:
    started = time.monotonic()
    peak = 0
    while process.poll() is None:
        try:
            worker = psutil.Process(process.pid)
            rss = worker.memory_info().rss + sum(
                child.memory_info().rss for child in worker.children(recursive=True)
            )
        except psutil.NoSuchProcess:
            if process.poll() is not None:
                break
            raise VerificationError("worker_disappeared") from None
        peak = max(peak, rss)
        _sample(root, started, rss, require_heartbeat=False)
        time.sleep(0.25)
    _sample(root, started, 0, require_heartbeat=True)
    if process.returncode != 0:
        raise VerificationError("worker_failed")
    return peak


def _worker(root: Path, nonce: str) -> None:
    from scripts.research import signal_calendar_score_study as io

    claim = _load(root, "benchmark-claim.json")
    manifest_digest, manifest_payload = current_manifest()
    expected = {
        "schema": 1,
        "scope": SCOPE,
        "nonce": nonce,
        "manifest": manifest_payload,
        "source_manifest_digest": manifest_digest,
    }
    if canonical(claim) != canonical(expected):
        raise VerificationError("benchmark_claim")
    _record(root, "worker-ready.json", {"schema": 1, "monotonic": time.monotonic()})
    stop = threading.Event()
    errors: list[BaseException] = []
    heartbeat = threading.Thread(
        target=io._heartbeat, args=(root / "heartbeat.json", stop, errors), daemon=True
    )
    heartbeat.start()
    started = time.monotonic()
    verify_started: float | None = None
    creation_seconds = 0.0
    receipt: VerificationReceipt | None = None
    try:
        before = time.perf_counter()
        fixture_root = root / "fixture"
        written_manifest = write_fixture(fixture_root)
        creation_seconds = time.perf_counter() - before
        if written_manifest != manifest_digest:
            raise VerificationError("source_drift")
        # No independent reference/truth/cutoff call occurred during fixture creation.
        # Explicitly reset bounded local immutable caches to prove cold measurement.
        _truth_items.cache_clear()
        check_frozen_cutoffs.cache_clear()
        verify_started = time.perf_counter()
        receipt = verify_fixture(
            fixture_root, expected_manifest=manifest_digest, expected_paths=FULL_PATHS
        )
        _sample(root, started, psutil.Process().memory_info().rss, require_heartbeat=True)
        if current_manifest()[0] != manifest_digest:
            raise VerificationError("source_drift")
    finally:
        stop.set()
        heartbeat.join(timeout=5)
        if heartbeat.is_alive():
            raise VerificationError("heartbeat_join")
        if errors:
            raise VerificationError("heartbeat_io") from errors[0]
    if receipt is None or verify_started is None:
        raise VerificationError("incomplete")
    verification_seconds = time.perf_counter() - verify_started
    _record(
        root,
        "benchmark-measurement.json",
        {
            "schema": 1,
            "scope": SCOPE,
            "fixture_creation_seconds": creation_seconds,
            "verification_seconds": verification_seconds,
            "receipt": asdict(receipt),
            "source_manifest_digest": manifest_digest,
            "geometry": [list(p) for p in FULL_PATHS],
        },
    )
    _sample(root, started, psutil.Process().memory_info().rss, require_heartbeat=True)
    if current_manifest()[0] != manifest_digest:
        raise VerificationError("source_drift")
    _record(
        root,
        "benchmark-terminal.json",
        {
            "schema": 1,
            "scope": SCOPE,
            "state": "BENCHMARK_COMPLETE",
            "measurement_digest": io._hash_file(root / "benchmark-measurement.json"),
            "source_manifest_digest": manifest_digest,
        },
    )


def _trusted_benchmark_parent() -> Path:
    return PROJECT / "var/verification"


def run_benchmark(root: Path) -> dict[str, object]:
    from scripts.research import signal_calendar_score_study as io

    if root.exists():
        raise VerificationError("destination")
    io._guard_path(root, _trusted_benchmark_parent())
    root.mkdir()
    process: subprocess.Popen[bytes] | None = None
    started = time.perf_counter()
    try:
        manifest_digest, manifest_payload = current_manifest()
        required = 20 * 1024**3 + io.PHASE_BOUNDED_ESTIMATES["validation"]
        if psutil.disk_usage(str(root)).free < required:
            raise VerificationError("disk_reserve")
        # A nonce authenticates only this deterministic child, never a study key.
        nonce = os.urandom(32).hex()
        _record(
            root,
            "benchmark-claim.json",
            {
                "schema": 1,
                "scope": SCOPE,
                "nonce": nonce,
                "manifest": manifest_payload,
                "source_manifest_digest": manifest_digest,
            },
        )
        python, environment = io._launch_python()
        log = io._open_exclusive(root / "benchmark-worker.log")
        failed: BaseException | None = None
        launch = time.monotonic()
        try:
            process = subprocess.Popen(
                [python, "-m", MODULE, "--internal-worker", str(root), "--nonce", nonce],
                cwd=PROJECT,
                env=environment,
                stdout=log,
                stderr=log,
            )
            peak = _supervise(process, root)
        except BaseException as error:
            failed = error
            raise
        finally:
            try:
                log.close()
            except BaseException as error:
                if failed is None:
                    raise VerificationError("close_failure") from error
        _sample(root, launch, 0, require_heartbeat=True)
        if current_manifest()[0] != manifest_digest:
            raise VerificationError("source_drift")
        measurement = _load(root, "benchmark-measurement.json")
        terminal = _load(root, "benchmark-terminal.json")
        ready = _load(root, "worker-ready.json")
        if canonical(terminal) != canonical(
            {
                "schema": 1,
                "scope": SCOPE,
                "state": "BENCHMARK_COMPLETE",
                "measurement_digest": io._hash_file(root / "benchmark-measurement.json"),
                "source_manifest_digest": manifest_digest,
            }
        ):
            raise VerificationError("benchmark_terminal")
        if (
            measurement.get("schema") != 1
            or measurement.get("scope") != SCOPE
            or measurement.get("source_manifest_digest") != manifest_digest
            or measurement.get("geometry") != [list(p) for p in FULL_PATHS]
        ):
            raise VerificationError("benchmark_measurement")
        creation = measurement.get("fixture_creation_seconds")
        pure = measurement.get("verification_seconds")
        if any(type(v) is not float or not math.isfinite(v) or v < 0 for v in (creation, pure)):
            raise VerificationError("benchmark_measurement")
        _sample(root, launch, 0, require_heartbeat=True)
        if current_manifest()[0] != manifest_digest:
            raise VerificationError("source_drift")
        wall = time.perf_counter() - started
        # Conservatively retain process startup, parent source/receipt work,
        # polling delay, child cold initialization and final checks in per-set timing.
        assert type(creation) is float and type(pure) is float
        per_set = wall - creation
        if per_set < pure:
            raise VerificationError("benchmark_timing")
        result: dict[str, object] = {
            "schema": 1,
            "scope": SCOPE,
            "geometry": [list(p) for p in FULL_PATHS],
            "paths": 10,
            "metrics": 28,
            "experimental_draws": 0,
            "phase_verdict": "UNAVAILABLE_DETERMINISTIC_FIXTURE",
            "source_manifest_digest": manifest_digest,
            "protocol_digest": PROTOCOL_DIGEST,
            "verification_seconds": pure,
            "conservative_per_set_seconds": per_set,
            "timing_boundary": "full verifier receipt and final pre-result resource/source checks",
            "timing_excludes": "benchmark-result persistence and redundant post-result checks",
            "parent_wall_seconds": wall,
            "fixture_creation_seconds": creation,
            "process_startup_seconds": max(0.0, ready["monotonic"] - launch),
            "peak_worker_rss": peak,
            "resource_disclosure": io.resource_disclosure(),
            "validation_projection_seconds": 2 * 32768 * per_set,
            "development_projection_seconds": 2 * 8192 * per_set,
            "per_set_limit_seconds": 43200 / (2 * 32768),
            "eligible": 2 * 32768 * per_set <= 43200,
        }
        _record(root, "benchmark-result.json", result)
        _sample(root, launch, 0, require_heartbeat=True)
        if current_manifest()[0] != manifest_digest:
            raise VerificationError("source_drift")
        return result
    except BaseException as error:
        if process is not None:
            io._kill_tree(process)
        reason = (
            str(error) if isinstance(error, (VerificationError, io.StudyError)) else "io_failure"
        )
        _record(
            root,
            "benchmark-failure.json",
            {
                "schema": 1,
                "scope": SCOPE,
                "state": "ERROR",
                "reason": reason,
                "experimental_draws": 0,
            },
        )
        if isinstance(error, VerificationError):
            raise
        raise VerificationError(reason) from error


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    group = result.add_mutually_exclusive_group()
    group.add_argument("--benchmark", action="store_true")
    group.add_argument("--verify-fixture", action="store_true")
    group.add_argument("--internal-worker", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--evidence-root", type=Path)
    result.add_argument("--expected-manifest")
    result.add_argument("--nonce", help=argparse.SUPPRESS)
    return result


def dispatch(args: argparse.Namespace) -> object:
    if args.internal_worker is not None:
        if (
            type(args.nonce) is not str
            or len(args.nonce) != 64
            or any(c not in "0123456789abcdef" for c in args.nonce)
        ):
            raise VerificationError("benchmark_claim")
        _worker(args.internal_worker, args.nonce)
        return None
    if args.evidence_root is None:
        raise VerificationError("deterministic_only")
    if args.benchmark:
        if args.expected_manifest is not None or args.nonce is not None:
            raise VerificationError("deterministic_only")
        return run_benchmark(args.evidence_root)
    if args.verify_fixture:
        if type(args.expected_manifest) is not str or args.nonce is not None:
            raise VerificationError("deterministic_only")
        return verify_fixture(
            args.evidence_root,
            expected_manifest=args.expected_manifest,
            expected_paths=FULL_PATHS,
            receipt_name=None,
        )
    raise VerificationError("deterministic_only")


def main() -> None:
    result = dispatch(parser().parse_args())
    if result is not None:
        print(
            canonical(asdict(result) if isinstance(result, VerificationReceipt) else result).decode(
                "utf8"
            ),
            end="",
        )


if __name__ == "__main__":
    main()
