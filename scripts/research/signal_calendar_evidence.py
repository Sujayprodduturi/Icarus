"""Lossless deterministic artificial-law evidence; no RNG, file I/O or market inputs.

Layout v1 stores every source date, including warmup and completion halos.
Content hashes establish integrity only, not authenticated source provenance.
"""

from dataclasses import dataclass
from fractions import Fraction
from hashlib import sha256
from math import lcm

import numpy as np
from scripts.research import signal_calendar_laws as laws

VERSION = "finite-calendar-bytes/v1"


@dataclass(frozen=True, slots=True)
class Evidence:
    version: str
    profile_id: str
    n: int
    payload: bytes


@dataclass(frozen=True, slots=True)
class Aggregate:
    n: int
    count: int
    raw: Fraction
    wins: int
    excess: Fraction


def _geometry(identifier: str, n: int) -> tuple[laws.LawProfile, int, int]:
    p = laws.profile(identifier)
    if type(n) is not int or not 2 <= n <= 1048576:
        raise ValueError("invalid core span")
    w = max(p.volatility_memory, 1)
    return p, w, n + w + p.hold


def _validate(evidence: Evidence) -> tuple[laws.LawProfile, int]:
    if (
        type(evidence) is not Evidence
        or type(evidence.version) is not str
        or evidence.version != VERSION
    ):
        raise ValueError("invalid evidence version")
    p, w, size = _geometry(evidence.profile_id, evidence.n)
    if type(evidence.payload) is not bytes or len(evidence.payload) != size:
        raise ValueError("invalid source length/type")
    for atom in evidence.payload:
        if atom & 128 or atom >> 5 >= len(p.jump_atoms):
            raise ValueError("invalid source atom")
        if p.p_gate == 1 and not atom & 4:
            raise ValueError("impossible dense gate")
    return p, w


def encode(identifier: str, n: int, path: laws.InnovationPath) -> Evidence:
    p, w, size = _geometry(identifier, n)
    if (
        type(path) is not laws.InnovationPath
        or type(path.first_index) is not int
        or path.first_index != -w
    ):
        raise ValueError("invalid source origin")
    fields = (path.s, path.q, path.g, path.j, path.epsilon1, path.epsilon2)
    if any(type(field) is not tuple or len(field) != size for field in fields):
        raise ValueError("invalid source arrays")
    jumps = tuple(value for value, _ in p.jump_atoms)
    packed = bytearray()
    for s, q, g, j, e1, e2 in zip(*fields, strict=True):
        if any(type(sign) is not int or sign not in (-1, 1) for sign in (s, e1, e2)):
            raise ValueError("invalid sign")
        if type(q) is not bool or type(g) is not bool or type(j) is not Fraction or j not in jumps:
            raise ValueError("invalid innovation")
        packed.append(
            int(s == 1)
            | (int(q) << 1)
            | (int(g) << 2)
            | (int(e1 == 1) << 3)
            | (int(e2 == 1) << 4)
            | (jumps.index(j) << 5)
        )
    evidence = Evidence(VERSION, identifier, n, bytes(packed))
    _validate(evidence)
    return evidence


def decode(evidence: Evidence) -> laws.InnovationPath:
    p, w = _validate(evidence)
    b = evidence.payload
    return laws.InnovationPath(
        -w,
        tuple(1 if a & 1 else -1 for a in b),
        tuple(bool(a & 2) for a in b),
        tuple(bool(a & 4) for a in b),
        tuple(p.jump_atoms[a >> 5][0] for a in b),
        tuple(1 if a & 8 else -1 for a in b),
        tuple(1 if a & 16 else -1 for a in b),
    )


def digest(evidence: Evidence) -> str:
    _validate(evidence)
    header = f"{VERSION}\n{laws.GENERATOR_VERSION}\n{evidence.profile_id}\n{evidence.n}\n".encode(
        "ascii"
    )
    hasher = sha256(header)
    hasher.update(evidence.payload)
    return hasher.hexdigest()


def _integer_coefficients(p: laws.LawProfile) -> tuple[tuple[int, ...], int]:
    coefficients = (
        p.delta - p.a / 3,
        p.a,
        p.gamma / p.hold,
        p.volatility_low,
        p.volatility_high,
        laws.BENCHMARK_CONSTANT,
        laws.BENCHMARK_PREVIOUS,
        laws.BENCHMARK_FORWARD / p.hold,
        *(value for value, _ in p.jump_atoms),
    )
    scale = lcm(*(value.denominator for value in coefficients))
    c = tuple(int(value * scale) for value in coefficients)
    return c, scale


def replay(evidence: Evidence) -> Aggregate:
    """Exact core-only replay with integer windows and original entrant weights.

    All source bytes, including warmup/completion halos, remain validated. The
    conservative Python-integer bound covers cumulative windows, coefficient
    products, both outcomes/benchmarks and all sums before any int64 arithmetic.
    Profiles outside that bound use the original arbitrary-precision replay.
    """
    p, w = _validate(evidence)
    c, scale = _integer_coefficients(p)
    limit = (1 << 63) - 1
    # |outcome| <= C*(hold+4); |benchmark| <= C*(hold+2).
    # Two symbols per core date bound both raw and excess signed reductions.
    bound = max(1, *(abs(value) for value in c)) * (2 * p.hold + p.volatility_memory + 16)
    if max(len(evidence.payload), 2 * evidence.n * bound) > limit:
        return _replay_scalar(evidence)
    base, pc, fc, low, high, bc, bp, bf = c[:8]
    atoms = np.frombuffer(evidence.payload, dtype=np.uint8)
    signs = (atoms & 1).astype(np.int64) * 2 - 1
    prefix = np.empty(len(atoms) + 1, dtype=np.int64)
    prefix[0] = 0
    np.cumsum(signs, out=prefix[1:])
    n = evidence.n
    factor = prefix[w + p.hold : w + p.hold + n] - prefix[w : w + n]
    np.cumsum((atoms & 2) != 0, dtype=np.int64, out=prefix[1:])
    volatility = prefix[w : w + n] - prefix[w - p.volatility_memory : w - p.volatility_memory + n]
    previous = signs[w - 1 : w - 1 + n]
    core = atoms[w : w + n]
    first = (core & 4) != 0
    second = first & (previous == 1)
    common = base + pc * previous + fc * factor + np.asarray(c[8:], dtype=np.int64)[core >> 5]
    benchmark = bc + bp * previous + bf * factor
    volatility_value = np.where(volatility != 0, high, low)
    count = raw = wins = excess = 0
    for bit, selected in ((8, first), (16, second)):
        outcome = common + np.where((core & bit) != 0, volatility_value, -volatility_value)
        count += int(np.count_nonzero(selected))
        raw += int(np.sum(outcome, where=selected, dtype=np.int64))
        wins += int(np.count_nonzero(selected & (outcome > 0)))
        excess += int(np.sum(outcome - benchmark, where=selected, dtype=np.int64))
    return Aggregate(n, count, Fraction(raw, scale), wins, Fraction(excess, scale))


def _replay_scalar(evidence: Evidence) -> Aggregate:
    """Original arbitrary-precision loop, retained as the overflow fallback."""
    p, w = _validate(evidence)
    c, scale = _integer_coefficients(p)
    base, previous_coefficient, factor_coefficient, low, high, bc, bp, bf = c[:8]
    jumps = c[8:]
    b = evidence.payload
    factor = sum(1 if b[i] & 1 else -1 for i in range(w, w + p.hold))
    volatility = sum(bool(b[i] & 2) for i in range(w - p.volatility_memory, w))
    count = raw = wins = excess = 0
    for t in range(evidence.n):
        i = t + w
        previous = 1 if b[i - 1] & 1 else -1
        selected = (1 + int(previous == 1)) if b[i] & 4 else 0
        v = high if volatility else low
        common = (
            base + previous_coefficient * previous + factor_coefficient * factor + jumps[b[i] >> 5]
        )
        benchmark = bc + bp * previous + bf * factor
        for bit in (8, 16)[:selected]:
            outcome = common + (v if b[i] & bit else -v)
            raw += outcome
            wins += int(outcome > 0)
            excess += outcome - benchmark
        count += selected
        factor += (1 if b[i + p.hold] & 1 else -1) - (1 if b[i] & 1 else -1)
        volatility += int(bool(b[i] & 2)) - int(bool(b[i - p.volatility_memory] & 2))
    return Aggregate(evidence.n, count, Fraction(raw, scale), wins, Fraction(excess, scale))
