"""One `PortfolioSimulator` builder for the four modules that each had their own.

`test_portfolio_cash`, `test_portfolio_dark`, `test_portfolio_exits` and
`test_portfolio_concentration` each carried a verbatim copy of the same eighteen-line
:class:`ExecutionRealism` block. Four copies of a fixture is four places to update when a realism
setting changes, and three of them will be missed — which matters here because those settings are
what make the simulation pessimistic. A test suite quietly running on stale slippage would report
better fills than the engine gives.

Not a `conftest.py` fixture: these are called with different arguments inside a single test, and a
fixture would have to become a factory fixture to allow that, which is more indirection than a
plain function for no gain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from icarus.common.config import ExecutionRealism
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator

if TYPE_CHECKING:
    from icarus.common.config import GoalConfig

# The pessimistic settings the whole suite simulates against. One place, so a change to any of them
# reaches every portfolio test at once.
REALISM = ExecutionRealism(
    fill_requires_trade_through=True,
    queue_volume_multiple_k=2.0,
    next_bar_execution=True,
    latency_ms=750,
    model_partial_fills=True,
    max_participation_of_depth=0.05,
    slippage_bps=5.0,
    tick_size_inr=0.05,
)


def simulator(
    goal: GoalConfig,
    *,
    slots: int | None = None,
    position_pct: float | None = None,
    stale_after: int = 20,
) -> PortfolioSimulator:
    """A simulator on the shipped config, with only the named risk values overridden.

    ``position_pct`` exists so a module testing one guard can stand the *other* one down. The
    concentration cap ships at 0.25 and bounds every position to a quarter of the book, which makes
    most cash-gate and dark-symbol fixtures unreachable — those modules pass ``1.0`` and say so.
    Leaving it ``None`` uses the shipped value, which is what a test of real behaviour should do.
    """
    update: dict[str, object] = {}
    if slots is not None:
        update["max_open_positions"] = slots
    if position_pct is not None:
        update["max_position_pct_of_equity"] = position_pct
    return PortfolioSimulator(
        risk=goal.risk.model_copy(update=update) if update else goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(REALISM),
        stale_after_sessions=stale_after,
    )
