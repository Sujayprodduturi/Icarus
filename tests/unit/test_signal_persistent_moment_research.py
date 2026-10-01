"""Deterministic Gaussian-moment laws; no samples or fitted premises."""

from dataclasses import replace
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any, cast

import pytest
from scripts.research import signal_moment_uncertainty as m
from scripts.research.signal_bounded_uncertainty import LatentIndex
from tests.unit.test_signal_moment_uncertainty_research import fixture, request

D = m.Declaration.FIXTURE_DECLARED


def model(
    source: m.MomentSourceContract, indices: tuple[int, ...], r: m.Numeric = Fraction(1, 2)
) -> m.GaussianMomentModelContract:
    assert hasattr(m, "GaussianMomentModelContract"), "combined contract not implemented"
    return m.GaussianMomentModelContract(
        source.fixture,
        "declared-joint-law",
        "factor-axis",
        tuple(
            LatentIndex(g.identifier, t, "factor-axis")
            for g, t in zip(source.groups, indices, strict=True)
        ),
        r,
        D,
        D,
        D,
        D,
        D,
        D,
        D,
    )


def combined(
    source: m.MomentSourceContract,
    rows: tuple[m.Observation, ...],
    indices: tuple[int, ...],
    r: m.Numeric = Fraction(1, 2),
    req: m.MomentRequest | None = None,
) -> m.PersistentMomentResult | m.MomentRefusal:
    contract = model(source, indices, r)
    assert hasattr(m, "estimate_persistent"), "combined calculator not implemented"
    return m.estimate_persistent(source, rows, request() if req is None else req, contract)


def test_unequal_weights_irregular_gaps_linear_gaussian_sharp_variance() -> None:
    source, rows = fixture(
        (1, 3, 2),
        (1, 2, 3, 4, 5, 6),
        (Fraction(1, 25), Fraction(1, 100), Fraction(9, 400)),
        (0, 0, 0),
    )
    source = replace(source, independence=m.Declaration.UNKNOWN)
    result = combined(source, rows, (0, 3, 9))
    assert isinstance(result, m.PersistentMomentResult)
    assert isinstance(result.calculation, m.MomentEstimate)
    assert result.calculation.mean == Fraction(7, 2)
    assert result.calculation.group_weights == (Fraction(1, 6), Fraction(1, 2), Fraction(1, 3))
    assert result.calculation.variance_bound >= Fraction(3047, 460800)
    assert result.calculation.variance_bound - Fraction(3047, 460800) < Fraction(1, 10**90)
    assert result.diagonal_variance == Fraction(11, 1800)
    assert (
        Fraction(result.calculation.radius) ** 2
        >= result.calculation.variance_bound / result.calculation.alpha
    )


@pytest.mark.parametrize("r", [0, Fraction(1, 2)])
def test_exact_diagonal_recovery_zero_persistence_or_one_active(r: m.Numeric) -> None:
    source, rows = fixture((1, 1), (0, 1), (1, 0), (0, 1))
    req = request(alpha=Fraction(1, 3))
    result = combined(source, rows, (0, 1000000), r, req)
    assert isinstance(result, m.PersistentMomentResult)
    assert result.cross_variance_upper == 0
    assert result.calculation == m.estimate(source, rows, req)


def test_zero_group_does_not_compress_gap() -> None:
    source, rows = fixture((1, 3, 2), (0, 0, 0, 0, 0, 0), (4, 0, 4), (0, 0, 0))
    result = combined(source, rows, (0, 2, 10))
    assert isinstance(result, m.PersistentMomentResult)
    assert result.active_gaps == (10,)
    assert result.calculation.variance_bound >= Fraction(427, 768)
    assert result.calculation.variance_bound - Fraction(427, 768) < Fraction(1, 10**90)


@pytest.mark.parametrize(
    "field",
    [
        "stationary_gaussian_start",
        "independent_gaussian_innovations",
        "known_persistence_bound",
        "whole_local_map",
        "independent_local_noise",
        "marginal_preservation",
        "geometry",
    ],
)
def test_unknown_model_premise_refuses(field: str) -> None:
    source, rows = fixture()
    result = m.estimate_persistent(
        source,
        rows,
        request(),
        replace(model(source, (0, 1)), **cast(dict[str, Any], {field: m.Declaration.UNKNOWN})),
    )
    assert isinstance(result, m.MomentRefusal)
    assert result.reason.value == "unknown_persistent_model"


@pytest.mark.parametrize("indices", [(0, 0), (0,), (-1, 2)])
def test_invalid_latent_map_refuses(indices: tuple[int, ...]) -> None:
    source, rows = fixture()
    points = tuple(LatentIndex(str(i), t, "factor-axis") for i, t in enumerate(indices))
    result = m.estimate_persistent(
        source, rows, request(), replace(model(source, (0, 1)), indices=points)
    )
    assert isinstance(result, m.MomentRefusal)
    assert result.reason.value == "invalid_latent_map"


def test_model_provenance_fixture_axis_and_r_refuse() -> None:
    source, rows = fixture()
    for kwargs in (
        {"fixture": "other"},
        {"provenance": ""},
        {"latent_axis": "other"},
        {"persistence_bound": 1},
        {"persistence_bound": -1},
    ):
        result = m.estimate_persistent(
            source, rows, request(), replace(model(source, (0, 1)), **kwargs)
        )
        assert isinstance(result, m.MomentRefusal)


def test_giant_gap_refuses_before_power_allocation() -> None:
    source, rows = fixture()
    result = combined(source, rows, (0, 10**100))
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT


def test_absolute_width_failure_has_diagnostics_without_endpoints() -> None:
    source, rows = fixture()
    result = combined(source, rows, (0, 1), req=request(width=Fraction(1, 100)))
    assert isinstance(result, m.PersistentMomentResult)
    assert isinstance(result.calculation, m.MomentInsufficientEvidence)
    assert not hasattr(result.calculation, "lower")
    assert result.cross_variance_upper > 0


def test_ambient_context_does_not_change_certified_result() -> None:
    source, rows = fixture()
    expected = combined(source, rows, (0, 3))
    with localcontext() as context:
        context.prec = 2
        context.Emax = 2
        context.Emin = -2
        for signal in context.traps:
            context.traps[signal] = True
        assert combined(source, rows, (0, 3)) == expected


def test_direct_paired_excess_preserves_original_mean() -> None:
    source, rows = fixture(metric=m.Metric.SYNTHETIC_EXCESS)
    rows = tuple(replace(row, benchmark=Fraction(1, 2)) for row in rows)
    result = combined(source, rows, (0, 3), req=request(metric=m.Metric.SYNTHETIC_EXCESS))
    assert isinstance(result, m.PersistentMomentResult)
    assert result.calculation.mean == Fraction(3, 2)


def test_all_known_still_checks_model_and_center() -> None:
    source, rows = fixture((1, 1), (2, 3), (0, 0), (2, 3))
    result = combined(source, rows, (0, 1))
    assert isinstance(result, m.PersistentMomentResult)
    assert result.calculation.mean == Fraction(5, 2)
    assert result.calculation.radius == 0
    assert isinstance(combined(source, rows, (0, 0)), m.MomentRefusal)
    contradiction = combined(source, tuple(replace(row, raw=7) for row in rows), (0, 1))
    assert isinstance(contradiction, m.MomentRefusal)
    assert contradiction.reason is m.Reason.ZERO_MOMENT_CONTRADICTION


def test_independent_route_preserves_refusal_precedence() -> None:
    source, rows = fixture()
    invalid = replace(source, independence=m.Declaration.UNKNOWN, geometry=m.Declaration.UNKNOWN)
    refusal = m.estimate(invalid, rows, request())
    assert isinstance(refusal, m.MomentRefusal)
    assert refusal.reason is m.Reason.UNKNOWN_INDEPENDENCE


def test_r_zero_recovers_independent_with_multiple_active_groups() -> None:
    source, rows = fixture()
    req = request(alpha=Fraction(1, 3))
    result = combined(source, rows, (0, 3), 0, req)
    assert isinstance(result, m.PersistentMomentResult)
    assert result.calculation == m.estimate(source, rows, req)
    assert result.cross_variance_upper == 0


def test_irrational_covariance_sqrt_is_enclosed_not_rounded_down() -> None:
    source, rows = fixture((1, 1), (0, 0), (2, 3), (0, 0))
    result = combined(source, rows, (0, 3))
    assert isinstance(result, m.PersistentMomentResult)
    # Pair contribution = 2*(1/2)*(1/2)*(1/8)*sqrt(6).
    with localcontext() as context:
        context.prec = 180
        exact_cross_approx = Decimal(6).sqrt() / Decimal(16)
    assert result.cross_variance_upper >= Fraction(exact_cross_approx)
    assert result.cross_variance_upper - Fraction(exact_cross_approx) < Fraction(1, 10**95)


@pytest.mark.parametrize("true_variance", [Fraction(5, 24), Fraction(151, 384)])
def test_negative_persistence_and_nonlinear_hermite_laws_are_below_absolute_bound(
    true_variance: Fraction,
) -> None:
    source, rows = fixture((1, 1, 1), (0, 0, 0), (1, 1, 1), (0, 0, 0))
    result = combined(source, rows, (0, 1, 4))
    assert isinstance(result, m.PersistentMomentResult)
    # rho=-1/2 linear gives 5/24. Normalized H2 covariance is rho**(2*gap),
    # giving exact true variance151/384 for this geometry.
    assert result.calculation.variance_bound >= Fraction(35, 72)
    assert result.calculation.variance_bound >= true_variance


def test_local_noise_variance_retains_noise_diagonal_but_covariance_contracts() -> None:
    source, rows = fixture((1, 1), (0, 0), (1, 1), (0, 0))
    result = combined(source, rows, (0, 3))
    assert isinstance(result, m.PersistentMomentResult)
    # Each Y=(F+epsilon)/sqrt(2) has variance1, covariance1/16.
    assert result.diagonal_variance == Fraction(1, 2)
    assert result.calculation.variance_bound >= Fraction(9, 16)
    assert result.calculation.variance_bound >= Fraction(17, 32)


def test_extreme_small_moments_and_large_observed_mean_remain_outward() -> None:
    source, rows = fixture(
        (1, 1), (10**1000, 10**1000), (Decimal("1e-2000"), Decimal("1e-2000")), (0, 0)
    )
    result = combined(source, rows, (0, 3))
    assert isinstance(result, m.PersistentMomentResult)
    assert isinstance(result.calculation, m.MomentEstimate)
    calc = result.calculation
    assert calc.mean == 10**1000
    assert result.cross_variance_upper > 0
    assert calc.radius > 0
    assert Fraction(calc.lower) <= calc.mean - Fraction(calc.radius)
    assert Fraction(calc.upper) >= calc.mean + Fraction(calc.radius)


def test_wrong_public_model_type_refuses_before_all_known_shortcut() -> None:
    source, rows = fixture((1,), (0,), (0,), (0,))
    result = m.estimate_persistent(
        source, rows, request(), cast(m.GaussianMomentModelContract, object())
    )
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.UNKNOWN_PERSISTENT_MODEL


@pytest.mark.parametrize("r", [float("nan"), float("inf"), Decimal("NaN")])
def test_nonfinite_persistence_refuses_without_exception(r: m.Numeric) -> None:
    source, rows = fixture()
    result = combined(source, rows, (0, 3), r)
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.NONFINITE


def test_all_known_does_not_accept_outcome_dependent_selection() -> None:
    source, rows = fixture((1,), (0,), (0,), (0,))
    result = combined(source, rows, (0,), req=replace(request(), selection=m.Declaration.OBSERVED))
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.OUTCOME_DEPENDENT_SELECTION


def test_large_decimal_coefficient_refuses_before_conversion() -> None:
    source, rows = fixture()
    r = Decimal("0.5" + "0" * 4999)
    result = combined(source, rows, (0, 3), r)
    assert isinstance(result, m.MomentRefusal)
    assert result.reason is m.Reason.TECHNICAL_LIMIT
