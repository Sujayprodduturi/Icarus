"""Deterministic parity and malformed-source tests; no sampled paths."""

from dataclasses import replace
from fractions import Fraction
from typing import Any, cast

import pytest
from scripts.research import signal_calendar_evidence as e
from scripts.research import signal_calendar_laws as law


class VersionAlias(str):
    pass


def patterned(identifier: str, n: int, pattern: int) -> law.InnovationPath:
    p = law.profile(identifier)
    first = -max(p.volatility_memory, 1)
    size = n + p.hold - first
    return law.InnovationPath(
        first,
        tuple(1 if (i + pattern) % 3 else -1 for i in range(size)),
        tuple((i + pattern) % 5 == 0 for i in range(size)),
        tuple(p.p_gate == 1 or (i + pattern) % 4 == 0 for i in range(size)),
        tuple(p.jump_atoms[(i + pattern) % len(p.jump_atoms)][0] for i in range(size)),
        tuple(1 if (i + pattern) % 2 else -1 for i in range(size)),
        tuple(-1 if (i + pattern) % 7 else 1 for i in range(size)),
    )


@pytest.mark.parametrize("identifier", [p.identifier for p in law.PROFILES])
@pytest.mark.parametrize("pattern", [0, 1, 2])
def test_lossless_replay_matches_old_completed_trades(identifier: str, pattern: int) -> None:
    original = patterned(identifier, 128, pattern)
    packed = e.encode(identifier, 128, original)
    assert e.decode(packed) == original
    assert len(packed.payload) == len(original.s)
    old = law.build(identifier, 128, original).source.records
    result = e.replay(packed)
    assert result.count == len(old)
    assert result.raw == sum((r.raw for r in old), Fraction())
    assert result.excess == sum((cast(Fraction, r.benchmark_excess) for r in old), Fraction())
    assert result.wins == sum(r.raw > 0 for r in old)
    assert e.digest(packed) == e.digest(e.encode(identifier, 128, e.decode(packed)))


@pytest.mark.parametrize(
    "change",
    [
        "version",
        "version_type",
        "profile",
        "span",
        "short",
        "long",
        "mutable",
        "bit",
        "jump",
        "gate",
    ],
)
def test_malformed_evidence_is_refused_before_output(change: str) -> None:
    good = e.encode("P1", 128, patterned("P1", 128, 0))
    bad = {
        "version": replace(good, version="unknown"),
        "version_type": replace(good, version=VersionAlias(e.VERSION)),
        "profile": replace(good, profile_id="unknown"),
        "span": replace(good, n=True),
        "short": replace(good, payload=good.payload[:-1]),
        "long": replace(good, payload=good.payload + b"\x00"),
        "mutable": replace(good, payload=cast(bytes, bytearray(good.payload))),
        "bit": replace(good, payload=b"\x80" + good.payload[1:]),
        "jump": replace(good, payload=bytes([good.payload[0] | 96]) + good.payload[1:]),
        "gate": replace(good, payload=bytes([good.payload[0] & ~4]) + good.payload[1:]),
    }[change]
    for operation in (e.decode, e.replay, e.digest):
        with pytest.raises(ValueError):
            operation(bad)


@pytest.mark.parametrize("field", ["first_index", "s", "q", "g", "j", "epsilon1", "epsilon2"])
def test_encoder_refuses_corrupt_arrays(field: str) -> None:
    good = patterned("P1", 128, 0)
    value = 0 if field == "first_index" else (None, *getattr(good, field)[1:])
    with pytest.raises(ValueError):
        e.encode("P1", 128, replace(good, **cast(dict[str, Any], {field: value})))


@pytest.mark.parametrize("n", [-1, 0, 1, 1048577, 2.0, True])
def test_span_bounds_are_refused(n: object) -> None:
    good = e.encode("P1", 128, patterned("P1", 128, 0))
    with pytest.raises(ValueError):
        e.replay(replace(good, n=cast(int, n)))


def test_identity_binds_profile_and_encoder_rejects_length() -> None:
    original = patterned("P1", 128, 0)
    good = e.encode("P1", 128, original)
    assert e.digest(good) != e.digest(replace(good, profile_id="P2"))
    with pytest.raises(ValueError):
        e.encode("P1", 128, replace(original, s=original.s[:-1]))


def test_identity_binds_halo_core_and_profile_and_zero_entries() -> None:
    path = patterned("L1", 128, 0)
    path = replace(path, g=(False,) * len(path.g))
    good = e.encode("L1", 128, path)
    assert e.replay(good).count == 0
    assert e.replay(good).raw == 0
    altered = replace(good, payload=good.payload[:-1] + bytes([good.payload[-1] ^ 1]))
    assert e.digest(good) != e.digest(altered)
    assert e.replay(good) == e.replay(altered)  # Recognition halo retained even when unused.


def test_long_span_and_ties_preserve_whole_calendar() -> None:
    path = patterned("P7", 131072, 0)
    packed = e.encode("P7", 131072, path)
    assert e.decode(packed) == path
    result = e.replay(packed)
    assert result.n == 131072
    assert 131072 <= result.count <= 262144
    assert result == e.replay(packed)
    short = patterned("P1", 128, 0)
    short = replace(
        short, s=(1,) * len(short.s), epsilon1=(-1,) * len(short.s), epsilon2=(-1,) * len(short.s)
    )
    tied = e.replay(e.encode("P1", 128, short))
    assert tied.count == 256 and tied.wins == 0 and tied.raw == 0
