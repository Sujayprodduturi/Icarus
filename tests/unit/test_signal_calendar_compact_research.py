"""Exact frozen-law summary equivalence on invented deterministic atom arrays."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction

import pytest
from scripts.research import signal_calendar_compact as m
from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_runner as reference


def invented(family: laws.PathFamily, mode: str) -> laws.InnovationPath:
    item = laws.profile(family.profile_id)
    bounds = laws.resource_bounds(family.profile_id, family.n)
    length = bounds.last_index - bounds.first_index + 1
    signs = tuple(1 if mode in ("dense", "flat") or i % 3 else -1 for i in range(length))
    q = tuple(mode == "dense" or i % 5 == 0 for i in range(length))
    if item.p_gate == 1:
        gates = (True,) * length
    else:
        gates = tuple(mode == "dense" or (mode != "quiet" and i % 7 == 0) for i in range(length))
    jumps = tuple(
        item.jump_atoms[i % len(item.jump_atoms)][0] if mode == "signed" else Fraction(0)
        for i in range(length)
    )
    eps1 = tuple(1 if mode == "flat" or ((i * i + 3 * i) // 7) % 2 else -1 for i in range(length))
    eps2 = tuple(1 if mode == "flat" or ((i * i + 5 * i) // 11) % 2 else -1 for i in range(length))
    return laws.InnovationPath(bounds.first_index, signs, q, gates, jumps, eps1, eps2)


@pytest.mark.parametrize("mode", ["dense", "signed", "flat", "quiet"])
def test_all_registered_families_match_complete_reference_dictionaries(mode: str) -> None:
    compact = m
    for family in laws.path_families():
        path = invented(family, mode)
        assert compact.evaluate(family, path) == reference.evaluate_reference(family, path)


def test_all_zero_sparse_and_zero_slice_refusals_preserve_raw_mean_count() -> None:
    compact = m
    family = next(f for f in laws.path_families() if f.profile_id == "L1" and f.n == 64)
    path = invented(family, "quiet")
    result = compact.evaluate(family, path)
    assert result == reference.evaluate_reference(family, path)
    assert all(item["reason"] == "zero_full_count" and item["count"] == 0 for item in result)
    gate = list(path.g)
    gate[-path.first_index] = True
    path = replace(path, g=tuple(gate))
    result = compact.evaluate(family, path)
    assert result == reference.evaluate_reference(family, path)
    assert all(item["reason"] == "zero_count_slice" and item["count"] > 0 for item in result)


def test_degenerate_strict_win_ties_and_asymmetric_quantiles_match() -> None:
    compact = m
    family = laws.path_families()[0]
    path = invented(family, "flat")
    result = compact.evaluate(family, path)
    assert result == reference.evaluate_reference(family, path)
    assert all(item["reason"] == "degenerate_roots" for item in result)
    path = replace(path, epsilon1=(-1,) * len(path.s), epsilon2=(-1,) * len(path.s))
    result = compact.evaluate(family, path)
    assert result == reference.evaluate_reference(family, path)
    assert result[1]["raw_mean"] == "0"


@pytest.mark.parametrize("change", ["sign", "shape", "gate", "jump", "first"])
def test_malformed_atom_arrays_raise_same_typed_law_error(change: str) -> None:
    compact = m
    family = laws.path_families()[0]
    path = invented(family, "dense")
    if change == "sign":
        path = replace(path, s=(0, *path.s[1:]))
    elif change == "shape":
        path = replace(path, epsilon1=path.epsilon1[:-1])
    elif change == "gate":
        path = replace(path, g=(False, *path.g[1:]))
    elif change == "jump":
        path = replace(path, j=(Fraction(9), *path.j[1:]))
    elif change == "first":
        path = replace(path, first_index=0)
    with pytest.raises(laws.LawError) as fast:
        compact.evaluate(family, path)
    with pytest.raises(laws.LawError) as slow:
        reference.evaluate_reference(family, path)
    assert fast.value.reason is slow.value.reason


def test_unregistered_and_overbudget_geometry_not_rescued_by_compaction() -> None:
    compact = m
    source_family = laws.path_families()[0]
    path = invented(source_family, "dense")
    for n in (65, 512):
        family = replace(source_family, n=n)
        with pytest.raises(laws.LawError) as fast:
            compact.evaluate(family, path)
        with pytest.raises(laws.LawError) as slow:
            reference.evaluate_reference(family, path)
        assert fast.value.reason is slow.value.reason


def test_boundary_spike_zero_quantile_spread_refusal_matches_reference() -> None:
    compact = m
    family = laws.path_families()[0]
    path = invented(family, "flat")
    offset = -path.first_index
    e1 = list(path.epsilon1)
    e2 = list(path.epsilon2)
    e1[offset] = e2[offset] = -1
    path = replace(path, epsilon1=tuple(e1), epsilon2=tuple(e2))
    result = compact.evaluate(family, path)
    assert result == reference.evaluate_reference(family, path)
    assert all(item["reason"] == "degenerate_quantiles" for item in result)


def test_integer_scaling_keeps_original_signed_rare_outcome_mean() -> None:
    compact = m
    family = next(f for f in laws.path_families() if f.profile_id == "P5" and f.n == 64)
    path = invented(family, "signed")
    fixture = laws.build(family.profile_id, family.n, path)
    result = compact.evaluate(family, path)
    raw = sum((Fraction(record.raw) for record in fixture.source.records), Fraction(0))
    paired = sum(
        (
            Fraction(record.benchmark_excess)
            for record in fixture.source.records
            if record.benchmark_excess is not None
        ),
        Fraction(0),
    )
    wins = sum(Fraction(record.raw) > 0 for record in fixture.source.records)
    expected = (raw, Fraction(wins), paired)
    for row, total in zip(result, expected, strict=True):
        assert Fraction(row["sum"]) == total
        assert Fraction(row["mean"]) == total / len(fixture.source.records)
