"""The metrics battery — task 1.8, PRD §31.

Fixtures are constructed so the answer is arithmetic rather than observation: a curve that rises
by a known amount, a drawdown whose depth is visible in the numbers, a return series whose Sharpe
can be worked out on paper. Where a metric is deliberately ``nan`` rather than zero, that is
tested too — the difference between "no edge" and "not measurable" is the difference between a
gate that fails honestly and one that passes on a technicality.
"""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np
import pytest

from icarus.engine.costmodel import Charges
from icarus.engine.metrics import SESSIONS_PER_YEAR, sharpe_estimate, summarise
from icarus.engine.portfolio import ClosedTrade, ExitReason

START = datetime(2024, 1, 1, tzinfo=UTC)
NO_CHARGES = Charges(
    brokerage=Decimal(0),
    stt=Decimal(0),
    exchange_txn=Decimal(0),
    sebi_fee=Decimal(0),
    gst=Decimal(0),
    stamp_duty=Decimal(0),
    dp_charge=Decimal(0),
    turnover=Decimal(0),
)


def _curve(values: list[float]) -> list[tuple[datetime, Decimal]]:
    return [(START + timedelta(days=i), Decimal(str(v))) for i, v in enumerate(values)]


def _trade(
    *, entry: float, exit_: float, risk: float, quantity: int = 1, days: int = 1
) -> ClosedTrade:
    return ClosedTrade(
        symbol="AAA",
        quantity=quantity,
        entry_ts=START,
        entry_price=Decimal(str(entry)),
        exit_ts=START + timedelta(days=days),
        exit_price=Decimal(str(exit_)),
        reason=ExitReason.STOP_LOSS,
        entry_charges=NO_CHARGES,
        exit_charges=NO_CHARGES,
        risk_per_share=Decimal(str(risk)),
    )


# --------------------------------------------------------------------------------------
# Sharpe, and the interval that makes it readable
# --------------------------------------------------------------------------------------


def test_a_flat_curve_has_no_sharpe_rather_than_a_sharpe_of_zero() -> None:
    """Zero variance means the ratio is undefined, not zero.

    This matters because the gate asks "is the lower bound above 0.0". A flat strategy reported
    as 0.0 with a zero-width interval would sit exactly on the boundary; reported as ``nan`` it
    cannot accidentally satisfy a comparison.
    """
    estimate = sharpe_estimate(np.zeros(100))
    assert math.isnan(estimate.point)
    assert not estimate.is_estimable


def test_too_few_observations_is_not_a_measurement() -> None:
    """Ten returns cannot estimate a Sharpe ratio. A very wide interval still *looks* like a
    number, so below the floor there is no number at all."""
    assert not sharpe_estimate(np.array([0.01, -0.01] * 5)).is_estimable


def test_the_interval_narrows_as_the_sample_grows() -> None:
    """The same edge, measured for four times as long, is measured four times more confidently —
    the standard error falls with sqrt(n). This is the whole reason the gate reads the lower
    bound: a short, lucky run and a long, real one can share a point estimate."""
    rng = np.random.default_rng(7)
    short = sharpe_estimate(rng.normal(0.001, 0.01, 250))
    long = sharpe_estimate(rng.normal(0.001, 0.01, 1000))
    assert long.standard_error < short.standard_error
    assert (long.upper - long.lower) < (short.upper - short.lower)


def test_a_left_tailed_series_is_measured_less_confidently_than_a_symmetric_one() -> None:
    """Two series, same mean and same standard deviation; one has a fat left tail.

    Under the textbook 1/sqrt(n) error they would report identical precision. Mertens' correction
    is here precisely so "wins small constantly, loses catastrophically rarely" — which is what a
    naive Sharpe flatters most — comes back with the wider interval it deserves.
    """
    rng = np.random.default_rng(11)
    symmetric = rng.normal(0.0, 0.01, 2000)
    skewed = symmetric.copy()
    skewed[::200] -= 0.08  # rare, large losses
    skewed = (skewed - skewed.mean()) / skewed.std() * symmetric.std() + symmetric.mean()

    assert sharpe_estimate(skewed).standard_error > sharpe_estimate(symmetric).standard_error


def test_the_point_estimate_is_annualised_from_sessions() -> None:
    """A constant positive return has mean/sd undefined, so use a known series instead: the
    annualisation factor must be sqrt(252) and nothing else."""
    rng = np.random.default_rng(3)
    returns = rng.normal(0.0005, 0.01, 5000)
    per_session = float(np.mean(returns)) / float(np.std(returns, ddof=1))
    assert sharpe_estimate(returns).point == pytest.approx(
        per_session * math.sqrt(SESSIONS_PER_YEAR)
    )


# --------------------------------------------------------------------------------------
# Drawdown
# --------------------------------------------------------------------------------------


def test_the_drawdown_is_peak_to_trough_not_first_to_last() -> None:
    """100 -> 150 -> 75 -> 160 ends up, and still lost half its value on the way.

    A start-to-end measure would report no drawdown at all on this curve, which is the number a
    strategy's author most wants to believe.
    """
    metrics = summarise(_curve([100, 150, 75, 160]), [])
    assert metrics.max_drawdown == pytest.approx(0.5)


def test_a_monotonic_curve_has_no_drawdown_and_therefore_no_calmar() -> None:
    """Calmar is return over drawdown. With no drawdown it is undefined — reporting infinity
    would sort such a strategy first in any ranking, on the strength of never having been tested."""
    metrics = summarise(_curve([100, 110, 120, 130]), [])
    assert metrics.max_drawdown == 0.0
    assert math.isnan(metrics.calmar)


def test_time_under_water_is_the_longest_run_below_a_peak() -> None:
    """Three sessions below the 150 peak before it is regained."""
    metrics = summarise(_curve([100, 150, 140, 130, 145, 160, 170]), [])
    assert metrics.max_drawdown_days == 3


def test_a_curve_that_reaches_zero_ends_the_series_there() -> None:
    """Equity at zero is the end of the backtest. Dividing by it, or by what follows, would
    produce returns whose denominator means nothing and moments dominated by one division."""
    metrics = summarise(_curve([100, 50, 0, 10, 20]), [])
    assert metrics.max_drawdown == pytest.approx(1.0)
    assert not metrics.sharpe.is_estimable


# --------------------------------------------------------------------------------------
# Trade shape
# --------------------------------------------------------------------------------------


def test_expectancy_is_measured_in_units_of_risk_taken() -> None:
    """Two winners of very different rupee size but identical R are the same trade.

    +20 on 10 of risk and +200 on 100 of risk are both +2R. Averaging rupees instead would let
    one large position dominate the statistic that decides whether the edge is real.
    """
    trades = [
        _trade(entry=100, exit_=120, risk=10),
        _trade(entry=1000, exit_=1200, risk=100),
    ]
    metrics = summarise(_curve([100, 101, 102]), trades)
    assert metrics.expectancy_r == pytest.approx(2.0)


def test_a_low_win_rate_with_positive_expectancy_is_not_a_losing_strategy() -> None:
    """One +5R winner against three -1R losers: 25% win rate, +0.5R expectancy.

    Reporting only the win rate would call this a failure. It is the shape most trend systems
    actually have.
    """
    trades = [
        _trade(entry=100, exit_=150, risk=10),
        *[_trade(entry=100, exit_=90, risk=10) for _ in range(3)],
    ]
    metrics = summarise(_curve([100, 101, 102]), trades)
    assert metrics.win_rate == pytest.approx(0.25)
    assert metrics.expectancy_r == pytest.approx(0.5)


def test_a_trade_with_no_recorded_risk_contributes_no_r_rather_than_infinity() -> None:
    """Dividing by a zero stop distance would make one malformed trade's R infinite and every
    aggregate built on it meaningless."""
    metrics = summarise(_curve([100, 101]), [_trade(entry=100, exit_=120, risk=0)])
    assert metrics.expectancy_r == pytest.approx(0.0)


def test_profit_factor_is_undefined_when_nothing_ever_lost() -> None:
    metrics = summarise(_curve([100, 110]), [_trade(entry=100, exit_=110, risk=10)])
    assert math.isnan(metrics.profit_factor)


# --------------------------------------------------------------------------------------
# Exposure — a fraction, and therefore never above one
# --------------------------------------------------------------------------------------


def test_more_sessions_open_than_sessions_is_refused_not_reported() -> None:
    """Exposure is a share of sessions and cannot exceed one.

    The first implementation counted *calendar* days between entry and exit against a denominator
    of *sessions*, sweeping weekends and holidays into the numerator, and reported 1.48. Above 1.0
    the bug announced itself loudly — but a strategy holding for a third of the period would have
    reported 0.48 instead of 0.33 and looked entirely plausible. So the impossible input raises
    here rather than being clamped: clamping 1.48 to 1.0 would have hidden the same bug.
    """
    with pytest.raises(ValueError, match="cannot exceed"):
        summarise(_curve([100] * 10), [], sessions_open=14)


def test_no_trades_means_no_exposure() -> None:
    assert summarise(_curve([100] * 10), []).exposure == 0.0
