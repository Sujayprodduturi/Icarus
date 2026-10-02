"""Deterministic finite-law tests: no RNG, market data or protocol draws."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest
from scripts.research import signal_calendar_laws as law
from scripts.research.signal_calendar_uncertainty import Metric


def path(profile_id: str = "P1", n: int = 64) -> law.InnovationPath:
    profile = law.profile(profile_id)
    first = -max(profile.volatility_memory, 1)
    length = n + profile.hold - first
    return law.InnovationPath(
        first,
        (1,) * length,
        (False,) * length,
        (True,) * length,
        (Fraction(0),) * length,
        (1,) * length,
        (-1,) * length,
    )


@pytest.mark.parametrize(
    "identifier,win",
    [
        ("P1", Fraction(1, 4)),
        ("P2", Fraction(7, 12)),
        ("P3", Fraction(121, 256)),
        ("P4", Fraction(9887, 24576)),
        ("P5", Fraction(1143, 2048)),
        ("P6", Fraction(3577, 6144)),
        ("P7", Fraction(74146261351971311, 144115188075855872)),
        ("L1", Fraction(7, 12)),
    ],
)
def test_exact_selected_targets_and_positive_lrv_proofs(identifier: str, win: Fraction) -> None:
    truths = {truth.metric: truth for truth in law.analytical_truths(identifier)}
    assert truths[Metric.RAW].theta == 0
    assert truths[Metric.SYNTHETIC_EXCESS].theta == Fraction(-1, 200)
    assert truths[Metric.WIN].theta == win
    for truth in truths.values():
        assert truth.lrv_lower_W > 0
        assert truth.lrv_lower_ratio == truth.lrv_lower_W / truth.entry_intensity**2
        assert truth.proof == "INDEPENDENT_PER_TRADE_SIGN_CONDITIONAL_VARIANCE"


def test_selected_straddle_bound_is_exact_not_individual_variance_assumption() -> None:
    expectations = {
        "P1": Fraction(1, 2),
        "P2": Fraction(1, 2),
        "P3": Fraction(7, 16),
        "P4": Fraction(1695, 4096),
        "P5": Fraction(1501, 3072),
        "P6": Fraction(511, 1024),
        "P7": Fraction(50815815317021065, 72057594037927936),
    }
    for identifier, straddle in expectations.items():
        truth = next(t for t in law.analytical_truths(identifier) if t.metric is Metric.WIN)
        assert truth.lrv_lower_W == truth.entry_intensity * straddle / 4


def test_effect_targets_and_family_manifest_counts() -> None:
    for identifier, raw, paired in (
        ("E+", Fraction(1, 25), Fraction(7, 200)),
        ("E-", Fraction(-1, 25), Fraction(-9, 200)),
    ):
        truths = {truth.metric: truth.theta for truth in law.analytical_truths(identifier)}
        assert truths == {Metric.RAW: raw, Metric.SYNTHETIC_EXCESS: paired}
    families = law.path_families()
    assert len(families) == 18
    assert sum(len(f.metrics) for f in families) == 52
    assert sum(len(f.metrics) for f in families if f.formal) == 46
    assert sum(len(f.metrics) for f in families if not f.formal) == 6


def test_complete_source_cost_benchmark_counts_and_next_session_selection() -> None:
    fixture = law.build("P1", 64, path())
    assert len(fixture.source.records) == 128
    assert fixture.source.expected_core_ids == tuple(
        record.identifier for record in fixture.source.records
    )
    first, second = fixture.source.records[:2]
    assert first.raw == Fraction(1, 50) and second.raw == 0
    assert first.benchmark_excess == Fraction(1, 1000)
    assert second.benchmark_excess == Fraction(-19, 1000)
    assert first.decision == -1 and first.entry == 0
    assert first.exits == (1,) and first.recognition == 1
    assert first.source_sessions == (-1, 0, 1)
    assert fixture.source.authorized_source_start == -1
    assert fixture.source.authorized_source_end == 64
    assert tuple(request.metric for request in fixture.requests) == (
        Metric.RAW,
        Metric.WIN,
        Metric.SYNTHETIC_EXCESS,
    )
    assert tuple(request.absolute_full_width for request in fixture.requests) == (
        Fraction(1, 50),
        Fraction(1, 5),
        Fraction(1, 50),
    )


def test_future_sign_changes_outcome_not_entry_decision_schedule() -> None:
    original = path()
    signs = list(original.s)
    signs[1] = -1
    left = law.build("P1", 64, original).source.records
    right = law.build("P1", 64, replace(original, s=tuple(signs))).source.records
    assert tuple((r.identifier, r.entry) for r in left if r.entry == 0) == tuple(
        (r.identifier, r.entry) for r in right if r.entry == 0
    )
    assert left[0].raw != right[0].raw


def test_sparse_gate_keeps_empty_sessions_and_zero_full_count() -> None:
    innovations = path("L1")
    fixture = law.build("L1", 64, replace(innovations, g=(False,) * len(innovations.g)))
    assert fixture.source.core_sessions == tuple(range(64))
    assert fixture.source.records == ()
    assert fixture.source.expected_core_ids == ()
    truth = fixture.truths[0]
    assert truth.entry_intensity == Fraction(3, 100)
    assert law.sparse_emission_upper(64) == 1 - Fraction(49, 50) ** 16
    assert law.sparse_emission_upper(128) == 1 - Fraction(49, 50) ** 26


def test_full_support_resource_bounds_before_path_construction() -> None:
    short = law.resource_bounds("P7", 64)
    long = law.resource_bounds("P7", 128)
    assert (short.rows, short.total_footprint, short.expanded_footprint) == (128, 5760, 72128)
    assert (long.rows, long.total_footprint, long.expanded_footprint) == (256, 11520, 246376)
    assert short.eligible and long.eligible
    assert law.resource_bounds("P7", 192).expanded_footprint == 497352
    assert not law.resource_bounds("P7", 192).eligible
    assert law.resource_bounds("P1", 512).expanded_footprint == 459776
    assert not law.resource_bounds("P1", 512).eligible
    with pytest.raises(law.LawError):
        law.build("P1", 512, path(n=512))


@pytest.mark.parametrize(
    "change", ["shape", "axis", "sign", "boolsign", "gate", "jump", "eps", "q"]
)
def test_invalid_innovation_shape_or_atoms_fail_before_calculator(change: str) -> None:
    innovations = path()
    if change == "shape":
        innovations = replace(innovations, s=innovations.s[:-1])
    elif change == "axis":
        innovations = replace(innovations, first_index=0)
    elif change == "sign":
        innovations = replace(innovations, s=(0, *innovations.s[1:]))
    elif change == "boolsign":
        innovations = replace(innovations, s=(True, *innovations.s[1:]))
    elif change == "gate":
        innovations = replace(innovations, g=(False, *innovations.g[1:]))
    elif change == "jump":
        innovations = replace(innovations, j=(Fraction(9), *innovations.j[1:]))
    elif change == "eps":
        innovations = replace(innovations, epsilon2=(0, *innovations.epsilon2[1:]))
    elif change == "q":
        innovations = replace(innovations, q=(cast(bool, 1), *innovations.q[1:]))
    with pytest.raises(law.LawError):
        law.build("P1", 64, innovations)


def test_unknown_profile_and_unregistered_span_refuse() -> None:
    with pytest.raises(law.LawError):
        law.profile("missing")
    with pytest.raises(law.LawError):
        law.build("P1", 65, path(n=65))


def test_nonfinite_jump_atom_and_wrong_public_identifier_raise_typed_law_error() -> None:

    innovations = path()
    with pytest.raises(law.LawError):
        law.build(
            "P1", 64, replace(innovations, j=(cast(Fraction, float("nan")), *innovations.j[1:]))
        )
    with pytest.raises(law.LawError):
        law.analytical_truths(cast(str, []))


def test_jump_atom_zero_mean_and_cost_subtracted_once_under_rare_outcome() -> None:
    for identifier in ("P5", "P6"):
        item = law.profile(identifier)
        assert sum((probability for _, probability in item.jump_atoms), Fraction(0)) == 1
        assert sum((jump * probability for jump, probability in item.jump_atoms), Fraction(0)) == 0
    innovations = path("P5")
    offset = -innovations.first_index
    jumps = list(innovations.j)
    jumps[offset] = Fraction(8, 25)
    fixture = law.build("P5", 64, replace(innovations, j=tuple(jumps)))
    assert fixture.source.records[0].raw == Fraction(26, 75)
    assert fixture.source.records[0].benchmark_excess == Fraction(983, 3000)


def test_all_registered_families_keep_complete_full_support_halos() -> None:
    for family in law.path_families():
        item = law.profile(family.profile_id)
        fixture = law.build(family.profile_id, family.n, path(family.profile_id, family.n))
        assert len(fixture.source.records) == 2 * family.n
        assert fixture.source.expected_core_ids == tuple(
            record.identifier for record in fixture.source.records
        )
        assert tuple(truth.metric for truth in fixture.truths) == family.metrics
        w = max(item.volatility_memory, 1)
        for record in fixture.source.records:
            assert record.source_sessions == tuple(
                range(record.entry - w, record.entry + item.hold + 1)
            )
            assert record.entry - record.decision == 1
            assert record.recognition - record.entry == item.hold
