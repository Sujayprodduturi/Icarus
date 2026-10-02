"""Counters must not hide refusals, one-sided misses or false precision."""

from decimal import Decimal
from fractions import Fraction
from typing import Any, cast

import pytest
from scripts.research import signal_calendar_statistics as m


def test_refusal_and_insufficient_ranges_keep_denominators() -> None:
    counts = m.Counts()
    counts.add(None, None, Fraction(0), precision=False, reason="zero_count_slice")
    counts.add(Decimal("-1"), Decimal("1"), Fraction(0), precision=False, reason="width")
    counts.add(Decimal(".1"), Decimal(".2"), Fraction(0), precision=True, reason="", effect=1)
    assert (
        counts.replicates,
        counts.arithmetic,
        counts.covered,
        counts.lower_tail,
        counts.upper_tail,
        counts.precision,
        counts.detected,
    ) == (3, 2, 1, 1, 0, 1, 1)
    assert counts.reasons == {"zero_count_slice": 1, "width": 1}


@pytest.mark.parametrize("lo,hi", [("NaN", "1"), ("0", "Infinity"), ("2", "1")])
def test_invalid_endpoint_cannot_increment_counters(lo: str, hi: str) -> None:
    counts = m.Counts()
    with pytest.raises(ValueError):
        counts.add(Decimal(lo), Decimal(hi), Fraction(0), precision=True, reason="")
    assert counts.replicates == 0


def test_endpoint_equal_truth_is_covered_and_zero_not_detected() -> None:
    counts = m.Counts()
    counts.add(Decimal(0), Decimal(1), Fraction(0), precision=True, reason="", effect=1)
    assert counts.covered == 1 and counts.detected == 0


def test_confirmation_uses_actual_random_emission_count() -> None:
    counts = m.Counts(
        replicates=32768,
        arithmetic=32700,
        covered=30890,
        lower_tail=900,
        upper_tail=910,
        precision=32000,
    )
    criteria = m.judge(counts, confirmation=True, effect=False)
    conditional = next(c for c in criteria if c.name == "conditional_coverage")
    assert conditional.denominator == 32700
    assert conditional.successes == 30890
    assert conditional.cutoff != 30955


def test_fabricated_counter_identity_refuses_before_bound() -> None:
    counts = m.Counts(replicates=3, arithmetic=2, covered=2, lower_tail=1)
    with pytest.raises(ValueError):
        m.judge(counts, confirmation=False, effect=False)


def test_always_wide_and_always_refuse_cannot_qualify() -> None:
    for arithmetic in (0, 512):
        counts = m.Counts(replicates=512, arithmetic=arithmetic, covered=arithmetic)
        assert not all(c.passed for c in m.judge(counts, confirmation=False, effect=False))


def test_cached_alias_cannot_bypass_strict_input_validation() -> None:
    m.cutoff(1, Fraction(1, 2), lower=True)
    for n, p in [(True, Fraction(1, 2)), (1, 0.5), ([], Fraction(1, 2))]:
        with pytest.raises(ValueError):
            m.cutoff(cast(Any, n), cast(Any, p), lower=True)


def test_development_point_pass_does_not_fake_certified_bound() -> None:
    counts = m.Counts(replicates=512, arithmetic=512, covered=512, precision=512)
    emission = m.judge(counts, confirmation=False, effect=False)[0]
    assert emission.passed
    assert emission.certified_bound == Fraction(0)
    assert not emission.bound_passed
    assert emission.cutoff == 513
