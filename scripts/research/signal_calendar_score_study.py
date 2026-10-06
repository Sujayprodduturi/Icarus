"""Frozen calendar-score v2 contracts and supervised deterministic preflight.

This synthetic-only module cannot start development or validation sampling.  It
measures the exact generator/evaluator/replay geometry and deterministic disk I/O;
all experimental-stream construction refuses.  RSS limits are monitored cancellation
limits, not hard address-space caps, and Windows power-loss equivalence is not claimed.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
import secrets
import stat
import subprocess
import sys
import threading
import time
from collections.abc import Iterator, Mapping
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from functools import lru_cache
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import psutil  # type: ignore[import-untyped]
from scripts.research import signal_calendar_evidence as evidence
from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_score as score

PROJECT = Path(__file__).resolve().parents[2]
MODULE = "scripts.research.signal_calendar_score_study"
PROTOCOL_PATH = "docs/plans/2026-10-04-calendar-score-study-protocol.md"
PROTOCOL_SHA256 = "130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71"
EXPERIMENT_NAMESPACE = "icarus/calendar-score-research/v2"
PREFLIGHT_NAMESPACE = "icarus/calendar-score-research/test-preflight/v2"
TEST_NAMESPACE = "icarus/calendar-score-research/test-fixture/v2"
STREAM_IDENTIFIER = "sha256-counter-u64x4-big-endian/v2"
EXPERIMENT_ROOT = PROJECT / "var/research/calendar_score_v2"
PHASE_REPLICATES = {"development": 8192, "validation": 32768}
PHASE_DEADLINES = {"development": 21600.0, "validation": 43200.0}
PREFLIGHT_DEADLINE = 600.0
PHASE_CAPS = {"development": 3 * 1024**3, "validation": 12 * 1024**3}
PHASE_BOUNDED_ESTIMATES = {"development": 2584248320, "validation": 10286661632}
FREE_RESERVE = 20 * 1024**3
WORKER_RSS_CAP = 2 * 1024**3
PARENT_RSS_CAP = 512 * 1024**2
MAX_BUFFER = 16 * 1024**2
MAX_RECORD = 256 * 1024
PATH_METADATA_CAP = 8192
PHASE_RECORDS_CAP = 16 * 1024**2
SYNC_PATHS = 256
SYNC_BYTES = 16 * 1024**2
ETA = Fraction(1, 1760)


class StudyError(RuntimeError):
    """A fail-safe study gate or evidence contract was violated."""


@dataclass(frozen=True, slots=True)
class StudySpec:
    profile_id: str
    n: int
    classes: int
    formal: bool


SPECS = (
    StudySpec("P1", 2048, 2, True),
    StudySpec("P2", 2048, 2, True),
    StudySpec("P3", 16384, 9, True),
    StudySpec("P4", 8192, 5, True),
    StudySpec("P5", 32768, 2, True),
    StudySpec("P6", 32768, 2, True),
    StudySpec("P7", 131072, 40, True),
    StudySpec("E+", 2048, 2, True),
    StudySpec("E-", 2048, 2, True),
    StudySpec("L1", 2048, 2, False),
)


def spec(profile_id: str) -> StudySpec:
    for item in SPECS:
        if item.profile_id == profile_id:
            return item
    raise StudyError("unknown_profile")


def _metrics(item: StudySpec) -> tuple[score.Metric, ...]:
    if item.profile_id in ("E+", "E-"):
        return score.Metric.RAW, score.Metric.SYNTHETIC_EXCESS
    return score.Metric.RAW, score.Metric.WIN, score.Metric.SYNTHETIC_EXCESS


def phase_totals(phase: str) -> tuple[int, int]:
    if phase not in PHASE_REPLICATES:
        raise StudyError("invalid_phase")
    replicates = PHASE_REPLICATES[phase]
    return len(SPECS) * replicates, sum(len(_metrics(item)) for item in SPECS) * replicates


def statement_count() -> int:
    formal_metrics = sum(len(_metrics(item)) for item in SPECS if item.formal)
    formal_families = sum(item.formal for item in SPECS)
    effects = sum(len(_metrics(item)) for item in SPECS if item.profile_id in ("E+", "E-"))
    return 3 * formal_metrics + formal_families + effects


def _support(item: StudySpec, metric: score.Metric) -> tuple[Fraction, Fraction]:
    profile = laws.profile(item.profile_id)
    jumps = tuple(value for value, probability in profile.jump_atoms if probability > 0)
    if metric is score.Metric.WIN:
        return Fraction(0), Fraction(1)
    if metric is score.Metric.RAW:
        center = profile.delta - profile.a / 3
        radius = (
            abs(profile.a)
            + abs(profile.gamma)
            + max(profile.volatility_low, profile.volatility_high)
        )
    else:
        center = profile.delta - profile.a / 3 - laws.BENCHMARK_CONSTANT
        radius = (
            abs(profile.a - laws.BENCHMARK_PREVIOUS)
            + abs(profile.gamma - laws.BENCHMARK_FORWARD)
            + max(profile.volatility_low, profile.volatility_high)
        )
    return center - radius + min(jumps), center + radius + max(jumps)


def targets(item: StudySpec) -> tuple[score.Target, ...]:
    return tuple(
        score.Target(
            metric,
            *_support(item, metric),
            Fraction(1, 5) if metric is score.Metric.WIN else Fraction(1, 50),
        )
        for metric in _metrics(item)
    )


def truths(item: StudySpec) -> dict[str, Fraction]:
    exact = {truth.metric.value: truth.theta for truth in laws.analytical_truths(item.profile_id)}
    expected = {metric.value for metric in _metrics(item)}
    if set(exact) != expected:
        raise StudyError("truth_manifest_mismatch")
    return exact


def _model(item: StudySpec) -> score.Model:
    declared = score.Declaration.FIXTURE_DECLARED
    return score.Model(
        item.n,
        item.classes,
        item.formal,
        score.Scope.SYNTHETIC,
        declared,
        declared,
        declared,
        declared,
    )


def adequacy(item: StudySpec) -> score.Adequacy:
    return score.assess(_model(item), targets(item), tail_exponent=5)


@lru_cache(maxsize=64)
def exact_cutoff(n: int, p: Fraction, *, lower: bool, eta: Fraction = ETA) -> int:
    if (
        type(n) is not int
        or not 0 < n <= 32768
        or type(p) is not Fraction
        or not 0 < p < 1
        or p.denominator > 200
        or type(lower) is not bool
        or type(eta) is not Fraction
        or not 0 < eta < 1
        or max(eta.numerator.bit_length(), eta.denominator.bit_length()) > 32
    ):
        raise StudyError("invalid_binomial_contract")
    a, d = p.numerator, p.denominator
    c = d - a
    denominator = d**n
    total = 0
    if lower:
        term = a**n
        for k in range(n, -1, -1):
            total += term
            if total * eta.denominator > denominator * eta.numerator:
                return k + 1
            if k:
                term, remainder = divmod(term * k * c, (n - k + 1) * a)
                if remainder:
                    raise StudyError("binomial_recurrence")
        return 0
    term = c**n
    for k in range(n + 1):
        total += term
        if total * eta.denominator > denominator * eta.numerator:
            return k - 1
        if k < n:
            term, remainder = divmod(term * (n - k) * a, (k + 1) * c)
            if remainder:
                raise StudyError("binomial_recurrence")
    return n


def accepts_exact_binomial(
    k: int, n: int, p: Fraction, *, lower: bool, eta: Fraction = ETA
) -> bool:
    if type(k) is not int or not 0 <= k <= n:
        raise StudyError("invalid_binomial_count")
    cutoff = exact_cutoff(n, p, lower=lower, eta=eta)
    return k >= cutoff if lower else k <= cutoff


class WordSource(Protocol):
    words_consumed: int

    def next_word(self) -> int: ...


BATCH_DATES = 8192
MAX_PEEK_WORDS = 6 * BATCH_DATES


def _counter_digest(prefix: bytes, counter: int) -> bytes:
    return hashlib.sha256(prefix + counter.to_bytes(8, "big")).digest()


class CounterStream:
    """Frozen counter-mode SHA-256 word stream; every lane is consumed once."""

    def __init__(
        self,
        *,
        namespace: str,
        phase: str,
        profile_id: str,
        n: int,
        replicate: int,
        root: bytes,
        _capability: object | None = None,
    ) -> None:
        if (
            type(namespace) is not str
            or namespace not in (EXPERIMENT_NAMESPACE, PREFLIGHT_NAMESPACE, TEST_NAMESPACE)
            or type(phase) is not str
            or (namespace == EXPERIMENT_NAMESPACE and phase not in PHASE_REPLICATES)
            or (namespace == PREFLIGHT_NAMESPACE and phase != "test_preflight")
            or (namespace == TEST_NAMESPACE and phase != "test_fixture")
            or type(profile_id) is not str
            or type(n) is not int
            or n <= 0
            or type(replicate) is not int
            or replicate < 0
            or type(root) is not bytes
            or len(root) != 32
        ):
            if _capability is not None:
                from scripts.research import signal_calendar_score_phase as phase_contract

                phase_contract._revoke(_capability)
            raise StudyError("invalid_stream_identity")
        if namespace == EXPERIMENT_NAMESPACE and _capability is None:
            raise StudyError("unclaimed_experimental_stream")
        if _capability is not None:
            from scripts.research import signal_calendar_score_phase as phase_contract

            phase_contract._authorize_stream(
                _capability,
                {
                    "namespace": namespace,
                    "phase": phase,
                    "profile_id": profile_id,
                    "n": n,
                    "replicate": replicate,
                    "root": root,
                },
            )
        identity = [
            namespace,
            laws.GENERATOR_VERSION,
            STREAM_IDENTIFIER,
            phase,
            f"{profile_id}:{n}",
            replicate,
            root.hex(),
        ]
        self.prefix = (
            json.dumps(identity, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n"
        ).encode("utf8")
        self.words_consumed = 0
        self._counter = 0
        self._buffer = b""
        self._offset = 0

    def peek_words(self, count: int) -> bytes:
        """Return an owned immutable prefix without consuming any word."""
        if type(count) is not int or not 1 <= count <= MAX_PEEK_WORDS:
            raise StudyError("word_buffer_count")
        remaining = len(self._buffer) - self._offset
        blocks = max(0, (8 * count - remaining + 31) // 32)
        # Refusal is atomic: no hashing, cursor or counter change.
        if blocks > (1 << 64) - self._counter:
            raise StudyError("counter_overflow")
        if blocks:
            suffix = self._buffer[self._offset :]
            generated = b"".join(
                _counter_digest(self.prefix, counter)
                for counter in range(self._counter, self._counter + blocks)
            )
            self._buffer = suffix + generated
            self._offset = 0
            self._counter += blocks
        return self._buffer[self._offset : self._offset + 8 * count]

    def consume_words(self, count: int) -> None:
        if (
            type(count) is not int
            or not 1 <= count <= MAX_PEEK_WORDS
            or 8 * count > len(self._buffer) - self._offset
        ):
            raise StudyError("word_buffer_count")
        self._offset += 8 * count
        self.words_consumed += count

    def next_word(self) -> int:
        word = int.from_bytes(self.peek_words(1), "big")
        self.consume_words(1)
        return word


def uniform(source: WordSource, denominator: int) -> int:
    if type(denominator) is not int or not 1 <= denominator <= 1 << 64:
        raise StudyError("invalid_uniform_denominator")
    limit = (1 << 64) // denominator * denominator
    for _ in range(1024):
        word = source.next_word()
        if type(word) is not int or not 0 <= word < 1 << 64:
            raise StudyError("invalid_stream_word")
        if word < limit:
            return word % denominator
    raise StudyError("rejection_limit")


def source_length(item: StudySpec) -> int:
    profile = laws.profile(item.profile_id)
    return item.n + max(profile.volatility_memory, 1) + profile.hold


@lru_cache(maxsize=16)
def _jump_partition(profile_id: str) -> tuple[int, tuple[int, ...]]:
    profile = laws.profile(profile_id)
    denominator = math.lcm(*(probability.denominator for _, probability in profile.jump_atoms))
    edge = 0
    edges = []
    for _, probability in profile.jump_atoms:
        edge += probability.numerator * (denominator // probability.denominator)
        edges.append(edge)
    if edge != denominator:
        raise StudyError("jump_probability_partition")
    return denominator, tuple(edges)


def _jump_index(source: WordSource, profile: laws.LawProfile) -> int:
    denominator, edges = _jump_partition(profile.identifier)
    draw = uniform(source, denominator)
    for index, edge in enumerate(edges):
        if draw < edge:
            return index
    raise StudyError("jump_probability_partition")


def _scalar_atom(source: WordSource, profile: laws.LawProfile) -> int:
    s = uniform(source, 2) == 0
    q = uniform(source, profile.p_volatility.denominator) < profile.p_volatility.numerator
    g = uniform(source, profile.p_gate.denominator) < profile.p_gate.numerator
    epsilon1 = uniform(source, 2) == 0
    epsilon2 = uniform(source, 2) == 0
    jump = _jump_index(source, profile)
    return (
        int(s)
        | (int(q) << 1)
        | (int(g) << 2)
        | (int(epsilon1) << 3)
        | (int(epsilon2) << 4)
        | (jump << 5)
    )


def _batch_atoms(source: CounterStream, profile: laws.LawProfile, count: int) -> bytes | None:
    if type(count) is not int or not 1 <= count <= BATCH_DATES:
        raise StudyError("word_buffer_count")
    jump_denominator, edges = _jump_partition(profile.identifier)
    denominators = (
        2,
        profile.p_volatility.denominator,
        profile.p_gate.denominator,
        2,
        2,
        jump_denominator,
    )
    words = np.frombuffer(source.peek_words(6 * count), dtype=">u8").reshape(count, 6)
    for column, denominator in enumerate(denominators):
        limit = (1 << 64) // denominator * denominator
        # 2**64 cannot be represented in uint64 and every word is then accepted.
        if limit != 1 << 64 and np.any(words[:, column] >= np.uint64(limit)):
            return None
    # At most 393240 buffered bytes + immutable peek; input, one remainder,
    # output and masks each <=393216 bytes. Even overlapping temporaries <4MiB.
    output = np.zeros(count, dtype=np.uint8)
    thresholds = (1, profile.p_volatility.numerator, profile.p_gate.numerator, 1, 1)
    for column, threshold in enumerate(thresholds):
        accepted = words[:, column] % np.uint64(denominators[column]) < np.uint64(threshold)
        output |= accepted.astype(np.uint8) << np.uint8(column)
    jump_draw = words[:, 5] % np.uint64(jump_denominator)
    for edge in edges[:-1]:
        output += (jump_draw >= np.uint64(edge)).astype(np.uint8) << np.uint8(5)
    source.consume_words(6 * count)
    return output.tobytes()


def generate_payload(item: StudySpec, source: WordSource, *, progress: Any | None = None) -> bytes:
    profile = laws.profile(item.profile_id)
    length = source_length(item)
    if not 0 < length <= MAX_BUFFER:
        raise StudyError("payload_buffer_cap")
    output = bytearray(length)
    index = 0
    while index < len(output):
        count = min(BATCH_DATES, len(output) - index)
        if progress is not None:
            # Baseline callback is after row 0, then row 65536, etc.
            count = min(count, 65536 - ((index - 1) % 65536))
        packed = None
        if type(source) is CounterStream:
            try:
                packed = _batch_atoms(source, profile, count)
            except StudyError as error:
                if str(error) != "counter_overflow":
                    raise
                # Consume valid residual lanes through the unchanged scalar map.
        if packed is None:
            for offset in range(count):
                output[index + offset] = _scalar_atom(source, profile)
        else:
            output[index : index + count] = packed
        index += count
        if progress is not None and (index - 1) % 65536 == 0:
            progress(index - 1)
    return bytes(output)


@dataclass(frozen=True, slots=True)
class ResultRow:
    metric: str
    truth: Fraction | None
    total: Fraction
    count: int
    arithmetic: bool
    precision: bool
    reason: str
    lower: Fraction | None
    upper: Fraction | None
    covered: bool
    lower_miss: bool
    upper_miss: bool
    detected: bool


@dataclass(frozen=True, slots=True)
class PathResult:
    profile_id: str
    n: int
    rows: tuple[ResultRow, ...]
    count: int


def evaluate_payload(item: StudySpec, payload: bytes) -> PathResult:
    if type(payload) is not bytes or len(payload) != source_length(item):
        raise StudyError("invalid_payload_length")
    aggregate = evidence.replay(
        evidence.Evidence(evidence.VERSION, item.profile_id, item.n, payload)
    )
    target_items = targets(item)
    totals = {
        score.Metric.RAW: aggregate.raw,
        score.Metric.WIN: Fraction(aggregate.wins),
        score.Metric.SYNTHETIC_EXCESS: aggregate.excess,
    }
    exact_truths = truths(item)
    try:
        report = score.calculate(
            _model(item),
            tuple(
                score.Totals(target, totals[target.metric], aggregate.count)
                for target in target_items
            ),
            tail_exponent=5,
        )
    except score.ScoreError as error:
        if item.formal or str(error) != "zero_count":
            raise StudyError(f"formal_score_refusal:{error}") from error
        refusal_rows = tuple(
            ResultRow(
                target.metric.value,
                exact_truths[target.metric.value],
                totals[target.metric],
                aggregate.count,
                False,
                False,
                "zero_count|sparse_selection_unsupported",
                None,
                None,
                False,
                False,
                False,
                False,
            )
            for target in target_items
        )
        return PathResult(item.profile_id, item.n, refusal_rows, aggregate.count)
    result_rows: list[ResultRow] = []
    for target, interval in zip(target_items, report.intervals, strict=True):
        truth = exact_truths[target.metric.value]
        lo, hi = Fraction(interval.lower), Fraction(interval.upper)
        precision = report.adequacy.decision_eligible
        result_rows.append(
            ResultRow(
                target.metric.value,
                truth,
                totals[target.metric],
                aggregate.count,
                True,
                precision,
                report.adequacy.reason,
                lo,
                hi,
                lo <= truth <= hi,
                truth < lo,
                truth > hi,
                precision
                and ((item.profile_id == "E+" and lo > 0) or (item.profile_id == "E-" and hi < 0)),
            )
        )
    return PathResult(item.profile_id, item.n, tuple(result_rows), aggregate.count)


def canonical_json(payload: object) -> bytes:
    try:
        return (
            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
        ).encode("utf8")
    except (TypeError, ValueError, OverflowError) as error:
        raise StudyError("noncanonical_record") from error


def _is_reparse(path: Path) -> bool:
    try:
        info = path.lstat()
    except FileNotFoundError:
        return False
    attributes = getattr(info, "st_file_attributes", 0)
    reparse = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return stat.S_ISLNK(info.st_mode) or bool(attributes & reparse)


def _guard_reparse_chain(path: Path) -> None:
    cursor = Path(os.path.abspath(path))
    while True:
        if _is_reparse(cursor):
            raise StudyError("reparse_path")
        if cursor.parent == cursor:
            return
        cursor = cursor.parent


def _guard_path(path: Path, root: Path, *, existing: bool = False) -> Path:
    lexical_root = Path(os.path.abspath(root))
    lexical_path = Path(os.path.abspath(path))
    try:
        inside = os.path.commonpath((lexical_root, lexical_path)) == str(lexical_root)
    except ValueError as error:
        raise StudyError("path_escape") from error
    if not inside or lexical_path == lexical_root:
        raise StudyError("path_escape")
    if not lexical_root.exists():
        raise StudyError("reparse_path")
    _guard_reparse_chain(lexical_path if existing else lexical_path.parent)
    resolved_root = lexical_root.resolve(strict=True)
    candidate = lexical_path.resolve(strict=existing)
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise StudyError("path_escape")
    return candidate


def _open_exclusive(path: Path) -> Any:
    _guard_reparse_chain(path)
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        opened = os.fstat(descriptor)
        lexical = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or _is_reparse(path)
            or (opened.st_dev, opened.st_ino) != (lexical.st_dev, lexical.st_ino)
        ):
            raise StudyError("nonregular_file")
        return os.fdopen(descriptor, "wb", buffering=0)
    except BaseException:
        os.close(descriptor)
        raise


def _write_all(stream: Any, blob: bytes | memoryview) -> None:
    if len(blob) > MAX_BUFFER:
        raise StudyError("write_buffer_cap")
    remaining = memoryview(blob)
    while remaining:
        written = stream.write(remaining)
        if type(written) is not int or not 0 < written <= len(remaining):
            raise StudyError("short_write")
        remaining = remaining[written:]


def _sync_directory(path: Path) -> str:
    if os.name == "nt":
        return "WINDOWS_DIRECTORY_SYNC_NOT_CLAIMED"
    descriptor = os.open(path, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return "SYNCED"


def _exclusive_record(path: Path, payload: object, *, root: Path) -> None:
    _guard_path(path, root)
    blob = canonical_json(payload)
    if len(blob) > MAX_RECORD:
        raise StudyError("record_cap")
    stream = _open_exclusive(path)
    failure: BaseException | None = None
    try:
        _write_all(stream, blob)
        stream.flush()
        os.fsync(stream.fileno())
    except BaseException as error:
        failure = error
        raise
    finally:
        try:
            stream.close()
        except BaseException as error:
            if failure is None:
                raise StudyError("close_failure") from error
    _sync_directory(path.parent)


class CanonicalRecordWriter:
    def __init__(
        self,
        path: Path,
        *,
        total_cap: int,
        record_cap: int = MAX_RECORD,
        sync_every: int = SYNC_PATHS,
    ) -> None:
        if min(total_cap, record_cap, sync_every) <= 0 or record_cap > MAX_RECORD:
            raise StudyError("invalid_writer_bounds")
        _guard_reparse_chain(path.parent)
        if not path.parent.is_dir():
            raise StudyError("writer_parent_missing")
        self.path = path
        self.root = path.parent
        _guard_path(path, self.root)
        self.stream = _open_exclusive(path)
        self.total_cap = total_cap
        self.record_cap = record_cap
        self.sync_every = sync_every
        self.total = 0
        self.pending = 0
        self.closed = False

    def write(self, payload: object) -> None:
        if self.closed:
            raise StudyError("writer_closed")
        blob = canonical_json(payload)
        if len(blob) > self.record_cap:
            raise StudyError("record_cap")
        if self.total + len(blob) > self.total_cap:
            raise StudyError("total_cap")
        _write_all(self.stream, blob)
        self.total += len(blob)
        self.pending += 1
        if self.pending >= self.sync_every:
            self.sync()

    def sync(self) -> None:
        self.stream.flush()
        os.fsync(self.stream.fileno())
        self.pending = 0

    def close(self) -> None:
        if self.closed:
            return
        failure: BaseException | None = None
        try:
            self.sync()
        except BaseException as error:
            failure = error
            raise
        finally:
            try:
                self.stream.close()
            except BaseException as error:
                if failure is None:
                    raise StudyError("close_failure") from error
            self.closed = True
        _sync_directory(self.path.parent)

    def __enter__(self) -> CanonicalRecordWriter:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_canonical_records(
    path: Path, *, total_cap: int, record_cap: int = MAX_RECORD
) -> Iterator[dict[str, Any]]:
    if min(total_cap, record_cap) <= 0 or path.stat().st_size > total_cap:
        raise StudyError("bounded_read_cap")
    total = 0
    with path.open("rb") as stream:
        while True:
            line = stream.readline(record_cap + 1)
            if not line:
                break
            total += len(line)
            if len(line) > record_cap or total > total_cap or not line.endswith(b"\n"):
                raise StudyError("trailing_or_noncanonical")
            try:
                value = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise StudyError("trailing_or_noncanonical") from error
            if type(value) is not dict or canonical_json(value) != line:
                raise StudyError("trailing_or_noncanonical")
            yield value


RESOURCE_PATH = PROJECT / "docs/plans/calendar-score-operational-resources.json"
RESOURCE_SHA256 = "96199af0f371c34e1d99371e1629dfb0d61e6bb32e59f41fddcacc6746e43bcd"
RESOURCE_PREVIOUS_SHA256 = "8a2225727e08cb7eb848e46ab856eca5649d727c15a101f0ab1bb3d9a1d313bc"
RESOURCE_BASELINE_SHA256 = "e13f6e229442c07edd5f559c878a2c5a1a176080f1c3d7f963914cc63dbd4434"
RESOURCE_ID = "calendar-score-verification-resources/v3"


@dataclass(frozen=True, slots=True)
class OperationalResources:
    resource_contract_id: str
    resource_contract_sha256: str
    legacy_verifier_seconds: int
    effective_verifier_seconds: int

    def binding(self) -> dict[str, Any]:
        return asdict(self)

    def compare(self, development: float, validation: float) -> dict[str, Any]:
        if any(
            type(v) not in (int, float)
            or (type(v) is int and v.bit_length() > 63)
            or not math.isfinite(v)
            or v < 0
            for v in (development, validation)
        ):
            raise StudyError("invalid_resource_projection")
        return {
            "legacy_verifier_seconds": self.legacy_verifier_seconds,
            "effective_verifier_seconds": self.effective_verifier_seconds,
            "projected_development_verify_seconds": development,
            "projected_validation_verify_seconds": validation,
            "legacy_development_eligible": development <= self.legacy_verifier_seconds,
            "legacy_validation_eligible": validation <= self.legacy_verifier_seconds,
            "effective_development_eligible": development <= self.effective_verifier_seconds,
            "effective_validation_eligible": validation <= self.effective_verifier_seconds,
        }


def _load_operational_resources(path: Path, *, expected_sha256: str) -> OperationalResources:
    """Explicit private fixture seam; production always uses the reviewed whole-file pin."""
    try:
        guarded = _guard_path(path, path.parent, existing=True)
        before = guarded.stat()
        if not stat.S_ISREG(before.st_mode):
            raise StudyError("resource_contract_nonregular")
        with guarded.open("rb") as stream:
            blob = stream.read(16385)
        after = guarded.stat()
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) or len(blob) > 16384:
            raise StudyError("resource_contract_bound")
        value = json.loads(blob)
        digest = hashlib.sha256(blob).hexdigest()
        if canonical_json(value) != blob or digest != expected_sha256:
            raise StudyError("resource_contract_digest")
        if (
            type(value) is not dict
            or set(value) != {"schema", "family", "protocol_sha256", "effective_id", "history"}
            or canonical_json({k: v for k, v in value.items() if k != "history"})
            != canonical_json(
                {
                    "schema": 1,
                    "family": "calendar-score-operational-resources/v1",
                    "protocol_sha256": PROTOCOL_SHA256,
                    "effective_id": RESOURCE_ID,
                }
            )
        ):
            raise StudyError("resource_contract_schema")
        history = value["history"]
        if type(history) is not list or len(history) != 3:
            raise StudyError("resource_contract_history")
        keys = {
            "id",
            "sequence",
            "recorded_on",
            "amended_at_utc",
            "verifier_seconds",
            "acknowledged_post_hoc",
            "reason",
            "predecessor_sha256",
            "evidence",
            "entry_sha256",
        }
        for entry in history:
            if type(entry) is not dict or set(entry) != keys:
                raise StudyError("resource_contract_schema")
            if (
                entry["entry_sha256"]
                != hashlib.sha256(
                    canonical_json({k: v for k, v in entry.items() if k != "entry_sha256"})
                ).hexdigest()
            ):
                raise StudyError("resource_contract_history")
        if history[0]["entry_sha256"] != RESOURCE_BASELINE_SHA256:
            raise StudyError("resource_contract_baseline")
        prior = {
            **value,
            "effective_id": "calendar-score-verification-resources/v2",
            "history": history[:2],
        }
        if hashlib.sha256(canonical_json(prior)).hexdigest() != RESOURCE_PREVIOUS_SHA256:
            raise StudyError("resource_contract_prior")
        amendment = history[1]
        stamp = amendment["amended_at_utc"]
        if type(stamp) is not str or len(stamp) != 20:
            raise StudyError("resource_contract_timestamp")
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        if (
            parsed.tzinfo is None
            or parsed.utcoffset() != UTC.utcoffset(parsed)
            or parsed.isoformat().replace("+00:00", "Z") != stamp
            or stamp[:10] != "2026-10-04"
        ):
            raise StudyError("resource_contract_timestamp")
        prior_paths = (
            "docs/plans/2026-10-04-calendar-score-verification-budget-amendment-proposal.md",
            "docs/reviews/2026-10-04-calendar-score-verifier-optimization-2-benchmarks.json",
        )
        current_paths = (
            "docs/plans/2026-10-04-calendar-score-sixteen-hour-budget-amendment.md",
            "docs/reviews/2026-10-04-calendar-score-verifier-optimization-3-benchmarks.json",
        )
        evidence: dict[str, dict[str, str]] = {}
        for relative in dict.fromkeys(prior_paths + current_paths):
            source = _guard_path(PROJECT / relative, PROJECT, existing=True)
            if not stat.S_ISREG(source.stat().st_mode):
                raise StudyError("resource_contract_nonregular")
            with source.open("rb") as stream:
                data = stream.read(MAX_RECORD + 1)
            if len(data) > MAX_RECORD:
                raise StudyError("resource_contract_evidence")
            evidence[relative] = {"path": relative, "sha256": hashlib.sha256(data).hexdigest()}
        expected_amendment = {
            "id": "calendar-score-verification-resources/v2",
            "sequence": 1,
            "recorded_on": "2026-10-04",
            "amended_at_utc": stamp,
            "verifier_seconds": 50400,
            "acknowledged_post_hoc": True,
            "reason": (
                "Deterministic cold full-workload verification exceeded the original twelve-hour "
                "resource budget; separately reviewed fourteen-hour operational amendment; "
                "statistical gates unchanged"
            ),
            "predecessor_sha256": RESOURCE_BASELINE_SHA256,
            "evidence": [evidence[relative] for relative in prior_paths],
            "entry_sha256": amendment["entry_sha256"],
        }
        if canonical_json(amendment) != canonical_json(expected_amendment):
            raise StudyError("resource_contract_amendment")
        latest = history[2]
        current_stamp = latest["amended_at_utc"]
        if type(current_stamp) is not str or len(current_stamp) != 20:
            raise StudyError("resource_contract_timestamp")
        current_time = datetime.fromisoformat(current_stamp.replace("Z", "+00:00"))
        if (
            current_time.tzinfo is None
            or current_time.utcoffset() != UTC.utcoffset(current_time)
            or current_time.isoformat().replace("+00:00", "Z") != current_stamp
            or current_time <= parsed
        ):
            raise StudyError("resource_contract_timestamp")
        expected_latest = {
            "id": RESOURCE_ID,
            "sequence": 2,
            "recorded_on": current_stamp[:10],
            "amended_at_utc": current_stamp,
            "verifier_seconds": 57600,
            "acknowledged_post_hoc": True,
            "reason": (
                "Reviewed fourteen-hour cold full-workload qualification failed; separately "
                "reviewed sixteen-hour operational allowance for observed startup variation "
                "and amendment overhead; statistical gates unchanged"
            ),
            "predecessor_sha256": amendment["entry_sha256"],
            "evidence": [evidence[relative] for relative in current_paths],
            "entry_sha256": latest["entry_sha256"],
        }
        if canonical_json(latest) != canonical_json(expected_latest):
            raise StudyError("resource_contract_amendment")
        return OperationalResources(
            RESOURCE_ID, digest, history[0]["verifier_seconds"], latest["verifier_seconds"]
        )

    except StudyError as error:
        if str(error).startswith("resource_contract"):
            raise
        raise StudyError("resource_contract_path") from error
    except (OSError, ValueError, TypeError, KeyError, UnicodeError) as error:
        raise StudyError("resource_contract_invalid") from error


def load_operational_resources() -> OperationalResources:
    return _load_operational_resources(RESOURCE_PATH, expected_sha256=RESOURCE_SHA256)


def _operational_record(path: Path, payload: dict[str, Any], *, root: Path) -> None:
    if "operational_resources" not in payload:
        payload["operational_resources"] = load_operational_resources().binding()
    _exclusive_record(path, payload, root=root)


SOURCE_PATHS = (
    PROTOCOL_PATH,
    "docs/plans/calendar-score-operational-resources.json",
    "docs/plans/2026-10-04-calendar-score-verification-budget-amendment-proposal.md",
    "docs/plans/2026-10-04-calendar-score-verification-budget-amendment-build.md",
    "docs/reviews/2026-10-04-calendar-score-verifier-optimization-2-benchmarks.json",
    "scripts/research/signal_calendar_score_verify.py",
    "docs/plans/2026-10-04-calendar-score-sampled-lifecycle.md",
    "docs/plans/2026-10-04-calendar-score-verifier-optimization.md",
    "docs/plans/2026-10-04-calendar-score-verifier-optimization-2.md",
    "docs/plans/2026-10-04-calendar-score-verifier-optimization-3.md",
    "docs/plans/2026-10-04-calendar-score-sixteen-hour-budget-amendment.md",
    "docs/reviews/2026-10-04-calendar-score-verifier-optimization-3-benchmarks.json",
    "scripts/research/signal_calendar_score_study.py",
    "scripts/research/signal_calendar_evidence.py",
    "scripts/research/signal_calendar_laws.py",
    "scripts/research/signal_calendar_score.py",
    "scripts/research/signal_calendar_uncertainty.py",
    "scripts/research/signal_moment_uncertainty.py",
    "scripts/research/signal_bounded_uncertainty.py",
    "goal.yaml",
    "uv.lock",
    "scripts/research/signal_calendar_score_phase.py",
    "scripts/research/signal_calendar_score_runner.py",
    "scripts/research/signal_calendar_score_runner_service.py",
    "tests/unit/test_signal_calendar_score_phase_research.py",
    "tests/unit/test_signal_calendar_score_runner_research.py",
    "tests/unit/test_signal_calendar_score_runner_preflight_research.py",
    "docs/plans/2026-10-05-calendar-score-full-runner.md",
    "docs/reviews/2026-10-05-calendar-score-full-runner-timing-refinement.md",
)


@dataclass(frozen=True, slots=True)
class Manifest:
    payload: dict[str, Any]
    digest: str


class _MetadataSnapshot(importlib.metadata.Distribution):
    """Read-only parser input; never stores a distribution path or lookup result."""

    def __init__(self, text: str | None) -> None:
        self._text = text

    def read_text(self, filename: str) -> str | None:
        return self._text

    def locate_file(self, path: Any) -> Path:
        raise NotImplementedError("metadata snapshot has no filesystem authority")


@lru_cache(maxsize=2)
def _parse_metadata_version(text: str) -> str:
    return _MetadataSnapshot(text).version


def _fresh_package_version(name: str) -> str:
    distribution = importlib.metadata.distribution(name)
    text = (
        distribution.read_text("METADATA")
        or distribution.read_text("PKG-INFO")
        or distribution.read_text("")
    )
    # Two <=1 MiB text keys; fresh discovery/read precedes every cache lookup.
    # A character bound avoids adding UnicodeEncodeError to parser semantics.
    if isinstance(text, str) and len(text) <= 262_144:
        return _parse_metadata_version(text)
    return _MetadataSnapshot(text).version


def manifest_for_paths(
    paths: Mapping[str, Path], *, protocol_hash: str, scope: str = "synthetic_only"
) -> Manifest:
    if (
        type(protocol_hash) is not str
        or len(protocol_hash) != 64
        or any(character not in "0123456789abcdef" for character in protocol_hash)
        or not paths
        or scope not in ("synthetic_only", "deterministic_test_fixture")
    ):
        raise StudyError("invalid_manifest_input")
    hashes: dict[str, str] = {}
    for label, path in sorted(paths.items()):
        if type(label) is not str or not label or not isinstance(path, Path) or not path.is_file():
            raise StudyError("invalid_manifest_source")
        hashes[label] = hashlib.sha256(path.read_bytes()).hexdigest()
    libraries: dict[str, str] = {}
    for name in ("psutil", "numpy"):
        try:
            libraries[name] = _fresh_package_version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    payload: dict[str, Any] = {
        "operational_resources": load_operational_resources().binding(),
        "schema": 2,
        "scope": scope,
        "protocol_sha256": protocol_hash,
        "sources": hashes,
        "python": sys.version,
        "platform": sys.platform,
        "libraries": libraries,
        "generator": laws.GENERATOR_VERSION,
        "evidence": evidence.VERSION,
        "stream": STREAM_IDENTIFIER,
    }
    blob = canonical_json(payload)
    return Manifest(payload, hashlib.sha256(blob).hexdigest())


def source_manifest() -> Manifest:
    paths = {relative: PROJECT / relative for relative in SOURCE_PATHS}
    if hashlib.sha256(paths[PROTOCOL_PATH].read_bytes()).hexdigest() != PROTOCOL_SHA256:
        raise StudyError("protocol_drift")
    manifest = manifest_for_paths(paths, protocol_hash=PROTOCOL_SHA256)
    verify_manifest(manifest, paths, protocol_hash=PROTOCOL_SHA256)
    return manifest


def verify_manifest(manifest: Manifest, paths: Mapping[str, Path], *, protocol_hash: str) -> None:
    if type(manifest) is not Manifest or manifest.payload.get("protocol_sha256") != protocol_hash:
        raise StudyError("protocol_drift")
    if hashlib.sha256(canonical_json(manifest.payload)).hexdigest() != manifest.digest:
        raise StudyError("manifest_digest")
    if canonical_json(manifest.payload.get("operational_resources")) != canonical_json(
        load_operational_resources().binding()
    ):
        raise StudyError("resource_contract_binding")
    expected = manifest.payload.get("sources")
    if type(expected) is not dict or set(expected) != set(paths):
        raise StudyError("source_closure")
    if PROTOCOL_PATH in paths:
        actual_protocol = hashlib.sha256(paths[PROTOCOL_PATH].read_bytes()).hexdigest()
        if actual_protocol != protocol_hash or expected[PROTOCOL_PATH] != protocol_hash:
            raise StudyError("protocol_drift")
    for label, path in paths.items():
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected[label]:
            raise StudyError("source_drift")


@dataclass(frozen=True, slots=True)
class SupervisionLimits:
    deadline_seconds: float
    rss_bytes: int
    heartbeat_seconds: float
    free_reserve_bytes: int


def check_supervision(
    limits: SupervisionLimits,
    elapsed: float,
    rss: int,
    heartbeat_age: float,
    free_bytes: int,
) -> None:
    values = (elapsed, heartbeat_age)
    if any(
        type(value) not in (int, float) or not math.isfinite(value) or value < 0 for value in values
    ):
        raise StudyError("invalid_supervision_sample")
    if any(type(value) is not int or value < 0 for value in (rss, free_bytes)):
        raise StudyError("invalid_supervision_sample")
    if elapsed >= limits.deadline_seconds:
        raise StudyError("timeout")
    if rss > limits.rss_bytes:
        raise StudyError("memory")
    if heartbeat_age > limits.heartbeat_seconds:
        raise StudyError("heartbeat")
    if free_bytes < limits.free_reserve_bytes:
        raise StudyError("disk_reserve")


def resource_disclosure() -> dict[str, Any]:
    return {
        "operational_resources": load_operational_resources().binding(),
        "rss_enforcement": "MONITORED_CANCELLATION_LIMIT",
        "sample_interval_seconds": "<=0.25",
        "transient_peaks_between_samples": "UNPROVED",
        "windows_power_loss_equivalence": "NOT_CLAIMED",
    }


@dataclass(frozen=True, slots=True)
class PreflightPhase:
    profile_id: str
    n: int
    replicates: int


@dataclass(frozen=True, slots=True)
class PreflightPlan:
    namespace: str
    phase: str
    root: bytes
    phases: tuple[PreflightPhase, ...]
    disk_probe_bytes: int
    safety_factor: int
    evidence_root: Path | None = None


def preflight_plan() -> PreflightPlan:
    phases = tuple(PreflightPhase(item.profile_id, item.n, 1) for item in SPECS)
    return PreflightPlan(
        PREFLIGHT_NAMESPACE,
        "test_preflight",
        bytes(32),
        phases,
        32 * 1024 * 1024,
        2,
        PROJECT / "var/verification/2026-10-04/calendar-score-study-preflight",
    )


def test_preflight_plan(evidence_root: Path, specs: tuple[StudySpec, ...]) -> PreflightPlan:
    if type(specs) is not tuple or not specs or any(item not in SPECS for item in specs):
        raise StudyError("invalid_test_preflight")
    phases = tuple(PreflightPhase(item.profile_id, item.n, 1) for item in specs)
    return PreflightPlan(
        PREFLIGHT_NAMESPACE,
        "test_preflight",
        bytes(32),
        phases,
        32 * 1024,
        2,
        evidence_root,
    )


@dataclass(frozen=True, slots=True)
class PreflightReceipt:
    source_manifest_digest: str
    generated_paths: int
    replayed_paths: int
    disk_probe_bytes: int
    generation_seconds: float
    replay_seconds: float
    disk_write_seconds: float
    disk_read_seconds: float
    peak_rss_bytes: int
    free_disk_bytes: int
    projected_development_seconds: float
    projected_development_verify_seconds: float
    projected_validation_seconds: float
    projected_validation_verify_seconds: float
    operational_resources: dict[str, Any]
    verification_budget_comparison: dict[str, Any]
    eligible: bool
    digest: str


def _probe_bytes(size: int) -> Iterator[bytes]:
    remaining = size
    counter = 0
    while remaining:
        block = hashlib.sha256(
            b"calendar-score-v2-disk-probe" + counter.to_bytes(8, "big")
        ).digest()
        chunk = block[: min(remaining, len(block))]
        yield chunk
        remaining -= len(chunk)
        counter += 1


def _hash_file(path: Path, *, expected_size: int | None = None) -> str:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            size += len(chunk)
            digest.update(chunk)
    if expected_size is not None and size != expected_size:
        raise StudyError("file_size_drift")
    return digest.hexdigest()


def _pack_result(result: PathResult) -> list[dict[str, Any]]:
    def pair(value: Fraction | None) -> list[int] | None:
        return None if value is None else [value.numerator, value.denominator]

    return [
        {
            "arithmetic": row.arithmetic,
            "count": row.count,
            "detected": row.detected,
            "lower": pair(row.lower),
            "metric": row.metric,
            "precision": row.precision,
            "reason": row.reason,
            "total": pair(row.total),
            "truth": pair(row.truth),
            "upper": pair(row.upper),
        }
        for row in result.rows
    ]


def execute_preflight(plan: PreflightPlan, manifest: Manifest) -> PreflightReceipt:
    if (
        type(plan) is not PreflightPlan
        or plan.namespace != PREFLIGHT_NAMESPACE
        or plan.phase != "test_preflight"
        or plan.root != bytes(32)
        or plan.evidence_root is None
        or not plan.phases
        or plan.safety_factor != 2
        or plan.disk_probe_bytes <= 0
    ):
        raise StudyError("invalid_preflight_plan")
    production = manifest.payload.get("scope") == "synthetic_only"
    expected = preflight_plan()
    if production and replace(plan, evidence_root=expected.evidence_root) != expected:
        raise StudyError("reduced_production_preflight")
    if not production and manifest.payload.get("scope") != "deterministic_test_fixture":
        raise StudyError("invalid_preflight_manifest")
    if plan.evidence_root.exists():
        if not plan.evidence_root.is_dir():
            raise StudyError("preflight_destination")
        _guard_path(plan.evidence_root / ".root-check", plan.evidence_root)
    else:
        if not plan.evidence_root.parent.is_dir():
            raise StudyError("preflight_destination")
        _guard_path(plan.evidence_root, plan.evidence_root.parent)
        plan.evidence_root.mkdir()
    resources: OperationalResources | None = None
    try:
        resources = load_operational_resources()
        return _execute_preflight_work(plan, manifest, resources)
    except BaseException as error:
        try:
            failure_path = plan.evidence_root / "preflight-failure.json"
            if not failure_path.exists():
                failure: dict[str, Any] = {
                    "state": "ERROR",
                    "stage": "direct_preflight",
                    "error_type": type(error).__name__,
                    "operational_resources": None if resources is None else resources.binding(),
                    "resource_contract_error": resources is None,
                }
                reason = _stable_failure_reason(error)
                if reason is not None:
                    failure["reason"] = reason
                _operational_record(failure_path, failure, root=plan.evidence_root)
        except BaseException as persistence:
            error.add_note("Failure evidence could not be persisted: " + type(persistence).__name__)
        raise


def _execute_preflight_work(
    plan: PreflightPlan, manifest: Manifest, resources: OperationalResources
) -> PreflightReceipt:
    assert plan.evidence_root is not None
    if canonical_json(manifest.payload.get("operational_resources")) != canonical_json(
        resources.binding()
    ):
        raise StudyError("resource_contract_binding")
    started = time.monotonic()
    generation_seconds = replay_seconds = 0.0
    generated = replayed = 0
    peak_rss = psutil.Process().memory_info().rss
    payload_path = plan.evidence_root / "preflight-payload.bin"
    index_path = plan.evidence_root / "preflight-index.jsonl"
    payload_stream = _open_exclusive(payload_path)
    offset = 0
    try:
        with CanonicalRecordWriter(
            index_path,
            total_cap=PATH_METADATA_CAP * len(plan.phases),
            record_cap=PATH_METADATA_CAP,
            sync_every=1,
        ) as writer:
            for phase in plan.phases:
                item = spec(phase.profile_id)
                if phase.n != item.n or phase.replicates != 1:
                    raise StudyError("preflight_geometry_drift")
                if time.monotonic() - started >= PREFLIGHT_DEADLINE:
                    raise StudyError("preflight_timeout")
                stream = CounterStream(
                    namespace=PREFLIGHT_NAMESPACE,
                    phase="test_preflight",
                    profile_id=item.profile_id,
                    n=item.n,
                    replicate=0,
                    root=bytes(32),
                )
                before = time.perf_counter()
                payload = generate_payload(item, stream)
                generated_result = evaluate_payload(item, payload)
                record = {
                    "operational_resources": resources.binding(),
                    "offset": offset,
                    "payload_sha256": hashlib.sha256(payload).hexdigest(),
                    "profile_id": item.profile_id,
                    "results": _pack_result(generated_result),
                    "size": len(payload),
                    "words": stream.words_consumed,
                }
                if len(canonical_json(record)) > PATH_METADATA_CAP:
                    raise StudyError("path_metadata_cap")
                _write_all(payload_stream, payload)
                payload_stream.flush()
                os.fsync(payload_stream.fileno())
                writer.write(record)
                generation_seconds += time.perf_counter() - before
                generated += 1
                offset += len(payload)
                peak_rss = max(peak_rss, psutil.Process().memory_info().rss)
    finally:
        payload_stream.close()
    rows = list(
        read_canonical_records(
            index_path,
            total_cap=PATH_METADATA_CAP * len(plan.phases),
            record_cap=PATH_METADATA_CAP,
        )
    )
    with payload_path.open("rb") as payload_reader:
        for phase, row in zip(plan.phases, rows, strict=True):
            before = time.perf_counter()
            item = spec(phase.profile_id)
            size = source_length(item)
            if (
                canonical_json(row.get("operational_resources"))
                != canonical_json(resources.binding())
                or row.get("profile_id") != item.profile_id
                or row.get("offset") != payload_reader.tell()
                or row.get("size") != size
            ):
                raise StudyError("preflight_ordered_identity")
            payload = payload_reader.read(size)
            stream = CounterStream(
                namespace=PREFLIGHT_NAMESPACE,
                phase="test_preflight",
                profile_id=item.profile_id,
                n=item.n,
                replicate=0,
                root=bytes(32),
            )
            expected_payload = generate_payload(item, stream)
            replayed_result = evaluate_payload(item, payload)
            if (
                payload != expected_payload
                or row.get("payload_sha256") != hashlib.sha256(payload).hexdigest()
                or row.get("words") != stream.words_consumed
                or row.get("results") != _pack_result(replayed_result)
            ):
                raise StudyError("preflight_replay")
            replay_seconds += time.perf_counter() - before
            replayed += 1
        if payload_reader.read(1):
            raise StudyError("preflight_trailing_payload")
    if len(rows) != len(plan.phases):
        raise StudyError("preflight_missing_index")
    probe = plan.evidence_root / "preflight-disk-probe.bin"
    probe_hasher = hashlib.sha256()
    before = time.perf_counter()
    probe_stream = _open_exclusive(probe)
    try:
        for chunk in _probe_bytes(plan.disk_probe_bytes):
            _write_all(probe_stream, chunk)
            probe_hasher.update(chunk)
        probe_stream.flush()
        os.fsync(probe_stream.fileno())
    finally:
        probe_stream.close()
    write_seconds = time.perf_counter() - before
    before = time.perf_counter()
    read_hasher = hashlib.sha256()
    with probe.open("rb") as reader:
        while chunk := reader.read(1024 * 1024):
            read_hasher.update(chunk)
    read_seconds = time.perf_counter() - before
    if read_hasher.digest() != probe_hasher.digest():
        raise StudyError("disk_probe_digest")
    payload_digest = _hash_file(payload_path, expected_size=offset)
    index_digest = _hash_file(index_path)
    cleanup_targets = (probe,)
    _operational_record(
        plan.evidence_root / "preflight-cleanup-intent.json",
        {
            "allowlist": [path.name for path in cleanup_targets],
            "probe_sha256": probe_hasher.hexdigest(),
            "state": "INTENT",
        },
        root=plan.evidence_root,
    )
    if (
        _hash_file(payload_path, expected_size=offset) != payload_digest
        or _hash_file(index_path) != index_digest
        or _hash_file(probe, expected_size=plan.disk_probe_bytes) != probe_hasher.hexdigest()
    ):
        raise StudyError("preflight_cleanup_identity")
    deleted: list[str] = []
    try:
        for target in cleanup_targets:
            _guard_path(target, plan.evidence_root, existing=True).unlink()
            deleted.append(target.name)
    except BaseException as error:
        try:
            _operational_record(
                plan.evidence_root / "preflight-cleanup-failure.json",
                {
                    "deleted": deleted,
                    "operational_resources": resources.binding(),
                    "resource_contract_error": False,
                    "error_type": type(error).__name__,
                    "state": "PARTIAL_FAILURE",
                },
                root=plan.evidence_root,
            )
        except BaseException as persistence:
            error.add_note("Failure evidence could not be persisted: " + type(persistence).__name__)
        raise StudyError("preflight_cleanup_failure") from error
    _operational_record(
        plan.evidence_root / "preflight-probe-cleanup.json",
        {
            "bytes": plan.disk_probe_bytes,
            "deleted": [path.name for path in cleanup_targets],
            "index_sha256": index_digest,
            "payload_sha256": payload_digest,
            "sha256": probe_hasher.hexdigest(),
            "state": "DELETED",
        },
        root=plan.evidence_root,
    )
    development_seconds = plan.safety_factor * generation_seconds * PHASE_REPLICATES["development"]
    validation_seconds = plan.safety_factor * generation_seconds * PHASE_REPLICATES["validation"]
    development_verify_seconds = (
        plan.safety_factor * replay_seconds * PHASE_REPLICATES["development"]
    )
    validation_verify_seconds = plan.safety_factor * replay_seconds * PHASE_REPLICATES["validation"]
    free_disk_bytes = psutil.disk_usage(str(plan.evidence_root)).free
    comparison = resources.compare(development_verify_seconds, validation_verify_seconds)
    if load_operational_resources() != resources:
        raise StudyError("resource_contract_drift")
    eligible = (
        generated == replayed == sum(phase.replicates for phase in plan.phases)
        and development_seconds <= PHASE_DEADLINES["development"]
        and validation_seconds <= PHASE_DEADLINES["validation"]
        and comparison["effective_development_eligible"]
        and comparison["effective_validation_eligible"]
        and peak_rss <= WORKER_RSS_CAP
        and free_disk_bytes >= FREE_RESERVE + PHASE_BOUNDED_ESTIMATES["validation"]
        and PHASE_BOUNDED_ESTIMATES["development"] <= PHASE_CAPS["development"]
        and PHASE_BOUNDED_ESTIMATES["validation"] <= PHASE_CAPS["validation"]
    )
    fields: dict[str, Any] = {
        "operational_resources": resources.binding(),
        "verification_budget_comparison": comparison,
        "disk_probe_bytes": plan.disk_probe_bytes,
        "disk_read_seconds": read_seconds,
        "disk_write_seconds": write_seconds,
        "eligible": eligible,
        "generated_paths": generated,
        "generation_seconds": generation_seconds,
        "peak_rss_bytes": peak_rss,
        "free_disk_bytes": free_disk_bytes,
        "projected_development_seconds": development_seconds,
        "projected_development_verify_seconds": development_verify_seconds,
        "projected_validation_seconds": validation_seconds,
        "projected_validation_verify_seconds": validation_verify_seconds,
        "replay_seconds": replay_seconds,
        "replayed_paths": replayed,
        "source_manifest_digest": manifest.digest,
    }
    digest = hashlib.sha256(canonical_json(fields)).hexdigest()
    receipt = PreflightReceipt(**fields, digest=digest)
    _operational_record(
        plan.evidence_root / "preflight-receipt.json",
        {**fields, "digest": digest, "resource_disclosure": resource_disclosure()},
        root=plan.evidence_root,
    )
    return receipt


def _heartbeat(path: Path, stop: threading.Event, errors: list[BaseException]) -> None:
    try:
        while not stop.is_set():
            temporary = path.with_suffix(".tmp")
            _guard_path(temporary, path.parent)
            if path.exists():
                _guard_path(path, path.parent, existing=True)
            stream = _open_exclusive(temporary)
            failure: BaseException | None = None
            try:
                _write_all(
                    stream,
                    canonical_json({"monotonic": time.monotonic(), "pid": os.getpid()}),
                )
                stream.flush()
                os.fsync(stream.fileno())
            except BaseException as error:
                failure = error
                raise
            finally:
                try:
                    stream.close()
                except BaseException as error:
                    if failure is None:
                        raise StudyError("close_failure") from error
            os.replace(temporary, path)
            if stop.wait(0.5):
                return
    except BaseException as error:
        errors.append(error)
        stop.set()


def _launch_python() -> tuple[str, dict[str, str] | None]:
    base = str(getattr(sys, "_base_executable", sys.executable))
    if sys.platform == "win32" and sys.executable != base:
        environment = os.environ.copy()
        environment["__PYVENV_LAUNCHER__"] = sys.executable
        return base, environment
    return sys.executable, None


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


def _supervision_sample(
    root: Path, started: float, worker_rss: int, *, require_heartbeat: bool
) -> None:
    parent_rss = psutil.Process().memory_info().rss
    if parent_rss > PARENT_RSS_CAP:
        raise StudyError("parent_memory")
    log = root / "preflight-worker.log"
    if log.exists() and log.stat().st_size > MAX_BUFFER:
        raise StudyError("worker_log_cap")
    heartbeat = root / "heartbeat.json"
    if require_heartbeat and not heartbeat.exists():
        raise StudyError("heartbeat")
    heartbeat_age = (
        time.time() - heartbeat.stat().st_mtime
        if heartbeat.exists()
        else time.monotonic() - started
    )
    check_supervision(
        SupervisionLimits(PREFLIGHT_DEADLINE, WORKER_RSS_CAP, 30.0, FREE_RESERVE),
        time.monotonic() - started,
        worker_rss,
        heartbeat_age,
        psutil.disk_usage(str(root)).free,
    )


def _supervise_preflight(process: subprocess.Popen[bytes], root: Path) -> int:
    started = time.monotonic()
    peak_worker_rss = 0
    while process.poll() is None:
        try:
            worker = psutil.Process(process.pid)
            worker_rss = worker.memory_info().rss + sum(
                child.memory_info().rss for child in worker.children(recursive=True)
            )
        except psutil.NoSuchProcess:
            if process.poll() is not None:
                break
            raise StudyError("worker_disappeared") from None
        peak_worker_rss = max(peak_worker_rss, worker_rss)
        _supervision_sample(root, started, worker_rss, require_heartbeat=False)
        time.sleep(0.25)
    _supervision_sample(root, started, 0, require_heartbeat=True)
    if process.returncode != 0:
        raise StudyError("preflight_worker_failed")
    return peak_worker_rss


def _internal_preflight_worker(root: Path, nonce: str) -> None:
    claim_rows = list(read_canonical_records(root / "preflight-claim.json", total_cap=MAX_RECORD))
    if len(claim_rows) != 1:
        raise StudyError("preflight_claim")
    claim = claim_rows[0]
    resources = load_operational_resources()
    if canonical_json(claim.get("operational_resources")) != canonical_json(resources.binding()):
        raise StudyError("resource_contract_binding")
    manifest_record = claim.get("manifest")
    if (
        claim.get("nonce") != nonce
        or type(manifest_record) is not dict
        or type(manifest_record.get("payload")) is not dict
        or type(manifest_record.get("digest")) is not str
    ):
        raise StudyError("preflight_claim")
    manifest = Manifest(manifest_record["payload"], manifest_record["digest"])
    if hashlib.sha256(canonical_json(manifest.payload)).hexdigest() != manifest.digest:
        raise StudyError("manifest_digest")
    plan_record = claim.get("plan")
    if type(plan_record) is not dict or type(plan_record.get("phases")) is not list:
        raise StudyError("preflight_claim")
    if canonical_json(plan_record.get("operational_resources")) != canonical_json(
        resources.binding()
    ):
        raise StudyError("resource_contract_binding")
    try:
        plan = PreflightPlan(
            plan_record["namespace"],
            plan_record["phase"],
            bytes.fromhex(plan_record["root"]),
            tuple(PreflightPhase(**item) for item in plan_record["phases"]),
            plan_record["disk_probe_bytes"],
            plan_record["safety_factor"],
            root,
        )
    except (KeyError, TypeError, ValueError) as error:
        raise StudyError("preflight_claim") from error
    if manifest.payload.get("scope") == "synthetic_only" and manifest != source_manifest():
        raise StudyError("source_drift")
    stop = threading.Event()
    heartbeat_errors: list[BaseException] = []
    heartbeat = threading.Thread(
        target=_heartbeat,
        args=(root / "heartbeat.json", stop, heartbeat_errors),
        daemon=True,
    )
    heartbeat.start()
    try:
        receipt = execute_preflight(plan, manifest)
    finally:
        stop.set()
        heartbeat.join(timeout=5)
        if heartbeat.is_alive():
            raise StudyError("heartbeat_join")
        if heartbeat_errors:
            raise StudyError("heartbeat_io") from heartbeat_errors[0]
    _operational_record(
        root / "preflight-terminal.json",
        {"digest": receipt.digest, "state": "COMPLETE"},
        root=root,
    )


def _read_preflight_receipt(
    root: Path, manifest: Manifest, *, plan: PreflightPlan | None = None
) -> PreflightReceipt:
    if type(plan) is not PreflightPlan or plan.evidence_root != root:
        raise StudyError("preflight_receipt_plan")
    rows = list(read_canonical_records(root / "preflight-receipt.json", total_cap=MAX_RECORD))
    if len(rows) != 1:
        raise StudyError("preflight_receipt")
    row = rows[0]
    disclosure = row.pop("resource_disclosure", None)
    digest = row.pop("digest", None)
    if (
        set(row) != set(PreflightReceipt.__dataclass_fields__) - {"digest"}
        or canonical_json(disclosure) != canonical_json(resource_disclosure())
        or digest != hashlib.sha256(canonical_json(row)).hexdigest()
        or row.get("source_manifest_digest") != manifest.digest
    ):
        raise StudyError("preflight_receipt")
    integers = (
        "generated_paths",
        "replayed_paths",
        "disk_probe_bytes",
        "peak_rss_bytes",
        "free_disk_bytes",
    )
    floats = (
        "generation_seconds",
        "replay_seconds",
        "disk_write_seconds",
        "disk_read_seconds",
        "projected_development_seconds",
        "projected_validation_seconds",
        "projected_development_verify_seconds",
        "projected_validation_verify_seconds",
    )
    if (
        any(type(row[k]) is not int or row[k] < 0 or row[k].bit_length() > 63 for k in integers)
        or any(type(row[k]) is not float or not math.isfinite(row[k]) or row[k] < 0 for k in floats)
        or type(row["eligible"]) is not bool
    ):
        raise StudyError("preflight_receipt_types")
    if (
        type(plan.safety_factor) is not int
        or plan.safety_factor != 2
        or any(
            type(phase) is not PreflightPhase
            or type(phase.replicates) is not int
            or phase.replicates != 1
            or phase.n != spec(phase.profile_id).n
            for phase in plan.phases
        )
    ):
        raise StudyError("preflight_receipt_plan")
    expected_projections = {
        "projected_development_seconds": plan.safety_factor
        * row["generation_seconds"]
        * PHASE_REPLICATES["development"],
        "projected_validation_seconds": plan.safety_factor
        * row["generation_seconds"]
        * PHASE_REPLICATES["validation"],
        "projected_development_verify_seconds": plan.safety_factor
        * row["replay_seconds"]
        * PHASE_REPLICATES["development"],
        "projected_validation_verify_seconds": plan.safety_factor
        * row["replay_seconds"]
        * PHASE_REPLICATES["validation"],
    }
    if canonical_json({k: row[k] for k in expected_projections}) != canonical_json(
        expected_projections
    ):
        raise StudyError("preflight_receipt_projection")
    resources = load_operational_resources()
    comparison = resources.compare(
        row["projected_development_verify_seconds"], row["projected_validation_verify_seconds"]
    )
    if canonical_json(row["operational_resources"]) != canonical_json(
        resources.binding()
    ) or canonical_json(row["verification_budget_comparison"]) != canonical_json(comparison):
        raise StudyError("resource_contract_binding")
    expected_count = sum(phase.replicates for phase in plan.phases)
    eligible = (
        row["generated_paths"] == row["replayed_paths"] == expected_count
        and expected_count > 0
        and row["disk_probe_bytes"] == plan.disk_probe_bytes
        and row["projected_development_seconds"] <= PHASE_DEADLINES["development"]
        and row["projected_validation_seconds"] <= PHASE_DEADLINES["validation"]
        and comparison["effective_development_eligible"]
        and comparison["effective_validation_eligible"]
        and row["peak_rss_bytes"] <= WORKER_RSS_CAP
        and row["free_disk_bytes"] >= FREE_RESERVE + PHASE_BOUNDED_ESTIMATES["validation"]
        and PHASE_BOUNDED_ESTIMATES["development"] <= PHASE_CAPS["development"]
        and PHASE_BOUNDED_ESTIMATES["validation"] <= PHASE_CAPS["validation"]
    )
    if row["eligible"] is not eligible:
        raise StudyError("preflight_receipt_eligibility")
    return PreflightReceipt(**row, digest=digest)


def _plan_record(plan: PreflightPlan) -> dict[str, Any]:
    return {
        "operational_resources": load_operational_resources().binding(),
        "disk_probe_bytes": plan.disk_probe_bytes,
        "namespace": plan.namespace,
        "phase": plan.phase,
        "phases": [asdict(phase) for phase in plan.phases],
        "root": plan.root.hex(),
        "safety_factor": plan.safety_factor,
    }


def _stable_failure_reason(error: BaseException) -> str | None:
    if not isinstance(error, StudyError):
        return None
    reason = str(error)
    if (
        not reason
        or len(reason) > 64
        or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789_" for character in reason)
    ):
        return "study_error"
    return reason


def run_supervised_preflight(
    root: Path, *, plan: PreflightPlan | None = None, manifest: Manifest | None = None
) -> PreflightReceipt:
    production = plan is None and manifest is None
    if (plan is None) != (manifest is None):
        raise StudyError("preflight_configuration")
    if production:
        plan = replace(preflight_plan(), evidence_root=root)
        trusted_root = Path(os.path.abspath(PROJECT / "var/verification"))
    else:
        assert plan is not None and manifest is not None
        if (
            manifest.payload.get("scope") != "deterministic_test_fixture"
            or plan.evidence_root != root
        ):
            raise StudyError("preflight_configuration")
        trusted_root = Path(os.path.abspath(root.parent))
    if root.exists():
        raise StudyError("preflight_destination")
    _guard_path(root, trusted_root)
    root.mkdir()
    process: subprocess.Popen[bytes] | None = None
    stage = "startup"
    resources: OperationalResources | None = None
    try:
        resources = load_operational_resources()
        if production:
            manifest = source_manifest()
        assert plan is not None and manifest is not None
        if production:
            current = source_manifest()
            if current != manifest:
                raise StudyError("source_drift")
        required = FREE_RESERVE + PHASE_BOUNDED_ESTIMATES["validation"]
        if psutil.disk_usage(str(root)).free < required:
            raise StudyError("disk_reserve")
        nonce = secrets.token_hex(32)
        stage = "claim"
        _operational_record(
            root / "preflight-claim.json",
            {
                "manifest": {"digest": manifest.digest, "payload": manifest.payload},
                "nonce": nonce,
                "plan": _plan_record(plan),
                "protocol_sha256": PROTOCOL_SHA256,
                "state": "CLAIMED_DETERMINISTIC_PREFLIGHT",
            },
            root=root,
        )
        python, environment = _launch_python()
        stage = "launch"
        log = _open_exclusive(root / "preflight-worker.log")
        log_failure: BaseException | None = None
        supervisor_peak_rss = 0
        try:
            process = subprocess.Popen(
                [
                    python,
                    "-m",
                    MODULE,
                    "--internal-worker",
                    str(root),
                    "--nonce",
                    nonce,
                ],
                cwd=PROJECT,
                env=environment,
                stdout=log,
                stderr=log,
            )
            stage = "supervision"
            supervisor_peak_rss = _supervise_preflight(process, root)
        except BaseException as error:
            log_failure = error
            raise
        finally:
            try:
                log.close()
            except BaseException as error:
                if log_failure is None:
                    raise StudyError("close_failure") from error
        stage = "supervision_record"
        _operational_record(
            root / "preflight-supervision.json",
            {
                "peak_worker_rss_bytes": supervisor_peak_rss,
                "state": "COMPLETE",
                "transient_peaks_between_samples": "UNPROVED",
            },
            root=root,
        )
        stage = "source_recheck"
        if production and source_manifest() != manifest:
            raise StudyError("source_drift")
        stage = "receipt"
        receipt = _read_preflight_receipt(root, manifest, plan=plan)
        terminal = list(
            read_canonical_records(root / "preflight-terminal.json", total_cap=MAX_RECORD)
        )
        if canonical_json(terminal) != canonical_json(
            [
                {
                    "digest": receipt.digest,
                    "state": "COMPLETE",
                    "operational_resources": resources.binding(),
                }
            ]
        ):
            raise StudyError("preflight_terminal")
        return receipt
    except BaseException as error:
        try:
            if process is not None and process.poll() is None:
                _kill_tree(process)
        except BaseException as cleanup:
            error.add_note("Worker termination could not be completed: " + type(cleanup).__name__)
        try:
            if not (root / "preflight-failure.json").exists():
                failure_payload: dict[str, Any] = {
                    "operational_resources": None if resources is None else resources.binding(),
                    "resource_contract_error": resources is None,
                    "error_type": type(error).__name__,
                    "stage": stage,
                    "state": "ERROR",
                }
                reason = _stable_failure_reason(error)
                if reason is not None:
                    failure_payload["reason"] = reason
                _operational_record(
                    root / "preflight-failure.json",
                    failure_payload,
                    root=root,
                )
        except BaseException as persistence:
            error.add_note("Failure evidence could not be persisted: " + type(persistence).__name__)
        raise


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--preflight", action="store_true")
    result.add_argument("--internal-worker", type=Path, help=argparse.SUPPRESS)
    result.add_argument("--nonce", help=argparse.SUPPRESS)
    result.add_argument(
        "--evidence-root",
        type=Path,
        default=PROJECT / "var/verification/2026-10-04/calendar-score-study-preflight",
    )
    return result


def dispatch(args: argparse.Namespace) -> None:
    if args.internal_worker is not None:
        if type(args.nonce) is not str or len(args.nonce) != 64:
            raise StudyError("internal_mode_requires_live_parent_capability")
        _internal_preflight_worker(args.internal_worker, args.nonce)
        return
    if args.nonce is not None:
        raise StudyError("internal_mode_requires_live_parent_capability")
    if not args.preflight:
        raise StudyError("preflight_only")
    receipt = run_supervised_preflight(args.evidence_root)
    print(
        canonical_json({**asdict(receipt), "resource_disclosure": resource_disclosure()}).decode(),
        end="",
    )


def main() -> None:
    dispatch(parser().parse_args())


if __name__ == "__main__":
    main()
