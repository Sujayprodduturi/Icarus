"""Performance metrics for a simulated run (task 1.8, PRD §31).

Everything here is computed on the **net** series — after broker charges, statutory levies and
tax. Gross numbers are a bug (CLAUDE.md §5), so this module never sees a gross figure: the
simulator has already subtracted costs by the time a :class:`~icarus.engine.portfolio.RunResult`
exists, and the runner settles tax on the trade ledger annually (:func:`_tax` there),
which is when it is actually owed.

**Sharpe is reported with a confidence interval, and the gate reads the lower bound.** From ~100
trades a measured 0.9 might really be anywhere from 0.1 to 1.7, so gating the point estimate gates
luck (``goal.yaml → stop_gate.require_sharpe_lower_bound_above``). The standard error used is
Mertens' — the one that accounts for skew and excess kurtosis — rather than the textbook
``1/sqrt(n)``:

    SE = sqrt( (1 + S^2/2 - skew*S + (kurtosis-3)/4 * S^2) / n )

Trading returns are neither normal nor independent, and a strategy whose edge is "wins small
constantly, loses catastrophically rarely" has a *high* point Sharpe and a *wide* true interval.
The textbook error would report that strategy as precisely measured, which is exactly backwards.
Source: Mertens (2002), *Comments on variance of the IID estimator in Lo (2002)*; the same moment
correction DSR uses in 1.9, implemented once here so the two cannot disagree.

Metrics are only meaningful on out-of-sample folds; the runner is what enforces that, and
:func:`summarise` will happily describe an in-sample series if handed one. That is deliberate —
in-sample numbers are needed to measure in-sample-to-out-of-sample decay, which is itself a
diagnostic the runner computes across folds.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from icarus.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from icarus.engine.portfolio import ClosedTrade

log = get_logger("engine.metrics")

SESSIONS_PER_YEAR = 252

# Below this many return observations a Sharpe ratio is not an estimate of anything. Reported as
# nan rather than as a number with a very wide interval, because a very wide interval still looks
# like a measurement and this is not one.
_MIN_OBSERVATIONS = 20

_Z_FOR_LEVEL = {0.90: 1.6449, 0.95: 1.9600, 0.975: 2.2414, 0.99: 2.5758}


@dataclass(frozen=True, slots=True)
class SharpeEstimate:
    """A Sharpe ratio and the interval it actually lives in."""

    point: float
    lower: float
    upper: float
    standard_error: float
    observations: int
    confidence_level: float

    @property
    def is_estimable(self) -> bool:
        return not math.isnan(self.point)


@dataclass(frozen=True, slots=True)
class Metrics:
    """The battery, computed on the series it was handed — which is net of **costs only**.

    This said "net of cost and tax" until 2026-08-16 and it was never true. The equity curve the
    simulator produces has charges subtracted per fill; tax is annual on the aggregate, so it is
    computed afterwards by ``runner._tax`` over the closed-trade ledger and reported separately.
    Nothing here has ever been after-tax, and `stop_gate.net_of_cost_and_tax` — asserted `True`
    in the loader and read by no code — does not change that (finding F38).
    """

    # Return shape
    sharpe: SharpeEstimate
    sortino: float
    calmar: float
    cagr: float
    total_return: float
    volatility_annual: float

    # Drawdown
    max_drawdown: float
    max_drawdown_days: int

    # Trade shape
    trades: int
    win_rate: float
    profit_factor: float
    expectancy_r: float
    """Mean outcome per trade in units of the risk taken on it. The number that says whether the
    edge is real: a 30%-win-rate strategy with expectancy +0.4R is a good strategy."""

    avg_win_r: float
    avg_loss_r: float
    avg_holding_days: float

    # Exposure
    sessions: int
    exposure: float
    """Share of sessions with at least one position open. A strategy that is flat 95% of the time
    has a Sharpe computed on very little actual risk-taking, and comparing it to a fully-invested
    one on Sharpe alone is comparing two different things."""

    def as_json(self) -> dict[str, object]:
        return {
            "sharpe": round(self.sharpe.point, 3),
            "sharpe_lower": round(self.sharpe.lower, 3),
            "sharpe_upper": round(self.sharpe.upper, 3),
            "sharpe_se": round(self.sharpe.standard_error, 3),
            "sortino": round(self.sortino, 3),
            "calmar": round(self.calmar, 3),
            "cagr": round(self.cagr, 4),
            "total_return": round(self.total_return, 4),
            "volatility_annual": round(self.volatility_annual, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "max_drawdown_days": self.max_drawdown_days,
            "trades": self.trades,
            "win_rate": round(self.win_rate, 4),
            "profit_factor": round(self.profit_factor, 3),
            "expectancy_r": round(self.expectancy_r, 4),
            "avg_win_r": round(self.avg_win_r, 3),
            "avg_loss_r": round(self.avg_loss_r, 3),
            "avg_holding_days": round(self.avg_holding_days, 1),
            "sessions": self.sessions,
            "exposure": round(self.exposure, 3),
        }


def summarise(
    equity: Sequence[tuple[datetime, Decimal]],
    trades: Sequence[ClosedTrade],
    *,
    confidence_level: float = 0.95,
    sessions_open: int | None = None,
) -> Metrics:
    """Describe one run. ``equity`` is the mark-to-market curve, one point per session.

    ``sessions_open`` is the exposure numerator and must be a count of the *same* sessions the
    curve covers. It is checked rather than trusted: the first caller passed calendar days,
    producing an exposure of 1.48, and a fraction above one is only obviously wrong when the
    holding period is long. Raising here catches the same mistake when it is not obvious.
    """
    if sessions_open is not None and sessions_open > len(equity):
        raise ValueError(
            f"sessions_open ({sessions_open}) cannot exceed the {len(equity)} sessions in the "
            f"equity curve — exposure is a share of sessions, so the numerator must be counted "
            f"on the session axis, not on the calendar"
        )
    curve = np.array([float(value) for _, value in equity], dtype=np.float64)
    returns = _returns(curve)
    sharpe = sharpe_estimate(returns, confidence_level=confidence_level)
    peak_to_trough, drawdown_days = _drawdown(curve)

    rs = np.array([_r_multiple(t) for t in trades], dtype=np.float64)
    wins, losses = rs[rs > 0], rs[rs < 0]
    gross_win = float(sum(float(t.net_pnl) for t in trades if t.net_pnl > 0))
    gross_loss = float(-sum(float(t.net_pnl) for t in trades if t.net_pnl < 0))

    years = len(returns) / SESSIONS_PER_YEAR if len(returns) else 0.0
    total = float(curve[-1] / curve[0] - 1.0) if curve.size > 1 and curve[0] > 0 else 0.0
    # A wiped-out account has total == -1.0, which failed the guard and fell through to 0.0 —
    # so the single worst possible outcome printed as "flat" in the headline CAGR column, next to
    # a 100% drawdown. Total loss is -100% a year, not zero.
    if total <= -1.0:
        cagr = -1.0
    else:
        cagr = ((1.0 + total) ** (1.0 / years) - 1.0) if years > 0 else 0.0
    volatility = (
        float(np.std(returns, ddof=1)) * math.sqrt(SESSIONS_PER_YEAR) if returns.size > 1 else 0.0
    )

    return Metrics(
        sharpe=sharpe,
        sortino=_sortino(returns),
        # Calmar against the drawdown that actually happened. A run with no drawdown has an
        # undefined Calmar, not an infinite one — reporting inf would rank it first on any sort.
        calmar=(cagr / peak_to_trough) if peak_to_trough > 0 else float("nan"),
        cagr=cagr,
        total_return=total,
        volatility_annual=volatility,
        max_drawdown=peak_to_trough,
        max_drawdown_days=drawdown_days,
        trades=len(trades),
        win_rate=float(wins.size / rs.size) if rs.size else 0.0,
        profit_factor=(gross_win / gross_loss) if gross_loss > 0 else float("nan"),
        expectancy_r=float(rs.mean()) if rs.size else 0.0,
        avg_win_r=float(wins.mean()) if wins.size else 0.0,
        avg_loss_r=float(losses.mean()) if losses.size else 0.0,
        avg_holding_days=float(np.mean([t.holding_days for t in trades])) if trades else 0.0,
        sessions=len(equity),
        exposure=(sessions_open / len(equity)) if sessions_open and equity else 0.0,
    )


def sharpe_estimate(
    returns: npt.NDArray[np.float64], *, confidence_level: float = 0.95
) -> SharpeEstimate:
    """Annualised Sharpe with a skew- and kurtosis-aware confidence interval.

    ``nan`` — not zero, and not a number with a wide interval — below
    :data:`_MIN_OBSERVATIONS` or on a series with no variance. A flat equity curve has no Sharpe,
    and returning 0.0 would let it pass a "greater than zero" gate on a technicality.
    """
    n = int(returns.size)
    level = confidence_level
    if n < _MIN_OBSERVATIONS:
        return SharpeEstimate(math.nan, math.nan, math.nan, math.nan, n, level)
    sigma = float(np.std(returns, ddof=1))
    if sigma <= 0.0:
        return SharpeEstimate(math.nan, math.nan, math.nan, math.nan, n, level)

    per_session = float(np.mean(returns)) / sigma
    annual = per_session * math.sqrt(SESSIONS_PER_YEAR)

    skew = _moment(returns, 3)
    kurtosis = _moment(returns, 4)
    # Mertens' standard error, in per-session units, then annualised the same way the point
    # estimate is. Computing the interval on the annualised figure directly would apply the
    # moment correction to the wrong scale.
    variance = (
        1.0 + 0.5 * per_session**2 - skew * per_session + 0.25 * (kurtosis - 3.0) * per_session**2
    ) / n
    # A heavy enough left tail can drive the bracket negative; the interval is then not
    # computable rather than imaginary, and saying so beats reporting sqrt of a negative.
    if variance <= 0.0:
        return SharpeEstimate(annual, math.nan, math.nan, math.nan, n, level)
    standard_error = math.sqrt(variance) * math.sqrt(SESSIONS_PER_YEAR)

    z = _Z_FOR_LEVEL.get(level)
    if z is None:
        raise ValueError(f"no z-score for confidence level {level}; add it to _Z_FOR_LEVEL")
    return SharpeEstimate(
        point=annual,
        lower=annual - z * standard_error,
        upper=annual + z * standard_error,
        standard_error=standard_error,
        observations=n,
        confidence_level=level,
    )


def decay(in_sample: Metrics, out_of_sample: Metrics) -> float:
    """How much of the in-sample Sharpe survived out of sample, as a fraction.

    Below ~0.5 the strategy is mostly fitted. Negative means the OOS edge reversed, which is worse
    than no edge: it says the fitted pattern was real and backwards.
    """
    if not in_sample.sharpe.is_estimable or in_sample.sharpe.point <= 0:
        return math.nan
    return out_of_sample.sharpe.point / in_sample.sharpe.point


def _returns(curve: npt.NDArray[np.float64]) -> npt.NDArray[np.float64]:
    """Session-over-session simple returns. Zero-or-negative equity ends the series.

    A backtest that reaches zero equity is over; carrying on would produce returns relative to a
    denominator that no longer means anything, and a single division by a near-zero equity would
    dominate every moment used above.
    """
    if curve.size < 2:
        return np.zeros(0, dtype=np.float64)
    # Include the observation that CROSSES to zero, then stop. Cutting before it dropped the
    # terminal -100% from every moment, so a strategy that blew up reported a Sharpe computed
    # only on the sessions before the blow-up — optimistic in exactly the case the gate exists
    # to catch. What must not be included is anything *after* zero, where the denominator is
    # meaningless.
    alive = np.flatnonzero(curve <= 0.0)
    end = int(alive[0]) + 1 if alive.size else curve.size
    live = curve[:end]
    if live.size < 2:
        return np.zeros(0, dtype=np.float64)
    out: npt.NDArray[np.float64] = np.diff(live) / live[:-1]
    return out


def _drawdown(curve: npt.NDArray[np.float64]) -> tuple[float, int]:
    """Worst peak-to-trough fall as a fraction, and the longest run spent below a peak."""
    if curve.size < 2:
        return 0.0, 0
    peak = np.maximum.accumulate(curve)
    with np.errstate(invalid="ignore", divide="ignore"):
        drawdown = np.where(peak > 0, 1.0 - curve / peak, 0.0)
    underwater = curve < peak
    longest = current = 0
    for wet in underwater:
        current = current + 1 if wet else 0
        longest = max(longest, current)
    return float(np.max(drawdown)), longest


def _sortino(returns: npt.NDArray[np.float64]) -> float:
    """Return per unit of *downside* deviation. ``nan`` when nothing ever went down."""
    if returns.size < 2:
        return math.nan
    downside = returns[returns < 0.0]
    if downside.size == 0:
        return math.nan
    # Deviation below zero, not below the mean: the question Sortino answers is "how much pain",
    # and pain is measured from flat, not from the strategy's own average day.
    deviation = math.sqrt(float(np.mean(downside**2)))
    if deviation <= 0.0:
        return math.nan
    return float(np.mean(returns)) / deviation * math.sqrt(SESSIONS_PER_YEAR)


def _moment(returns: npt.NDArray[np.float64], order: int) -> float:
    centred = returns - float(np.mean(returns))
    sigma = float(np.std(returns, ddof=1))
    if sigma <= 0.0:
        return 0.0
    return float(np.mean(centred**order)) / sigma**order


def _r_multiple(trade: ClosedTrade) -> float:
    """A trade's net outcome in units of the risk it took on.

    Risk is the per-share stop distance times the quantity — the loss the position was sized to
    accept. Expressing outcomes this way is what makes a ₹200 win on a ₹100-risk trade comparable
    to a ₹2,000 win on a ₹1,000-risk one, and it is the unit the stagnation check (invariant #23)
    and the trade-count floor both speak.
    """
    risk = float(trade.risk_per_share) * float(trade.quantity)
    if risk <= 0.0:
        return 0.0
    return float(trade.net_pnl) / risk


__all__ = [
    "SESSIONS_PER_YEAR",
    "Metrics",
    "SharpeEstimate",
    "decay",
    "sharpe_estimate",
    "summarise",
]
