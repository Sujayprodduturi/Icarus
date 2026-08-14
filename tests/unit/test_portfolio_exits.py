"""Every exit rule the DSL accepts must be one the simulator actually honours (task 1.7).

**These exist because it did not.** For a long time the simulator implemented exactly one of the
six exit rules in ``EXIT_RULES``: ``take_profit=None`` was hardcoded at entry, ``bars_held`` was
incremented and never read, and a ``trailing_stop_atr`` was installed as a stop that never moved.
A strategy file declaring a 3R target and a 20-bar time stop parsed cleanly, validated cleanly,
and was then simulated as buy-and-hold-until-stopped.

That is worse than a wrong number. Invariant #25 says a pre-registered strategy is measured as
written; if the artefact and the simulated thing differ, pre-registration is theatre. So the last
test here is the important one: an exit rule the simulator cannot honour must **raise**, not be
skipped, so no future DSL word can silently change what an existing strategy means.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import ExecutionRealism, load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import ExitPlan, ExitReason, PortfolioSimulator
from icarus.strategy.dsl import Bars, ExitRule, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    import numpy.typing as npt

    from icarus.common.config import GoalConfig

START = np.datetime64("2024-01-01")


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _sim(goal: GoalConfig) -> PortfolioSimulator:
    realism = ExecutionRealism(
        fill_requires_trade_through=True,
        queue_volume_multiple_k=2.0,
        next_bar_execution=True,
        latency_ms=750,
        model_partial_fills=True,
        max_participation_of_depth=0.05,
        slippage_bps=5.0,
        tick_size_inr=0.05,
    )
    return PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(realism),
        stale_after_sessions=20,
    )


def _strategy(exits: str) -> object:
    return parse_strategy(
        f"""
name: exit_test
version: 1
timeframe: 1d
universe: nse_liquid
entry: {{structure_bullish: {{k: 2}}}}
exit:
{exits}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )


def _panel(closes: list[float], *, highs: list[float] | None = None) -> Panel:
    close = np.array(closes, dtype=np.float64)
    high = np.array(highs, dtype=np.float64) if highs else close + 1.0
    bars = Bars(
        ts=np.arange(START, START + close.size).astype("datetime64[ns]"),
        open=close.copy(),
        high=high,
        low=close - 1.0,
        close=close,
        volume=np.full(close.size, 1_000_000.0),
    )
    return Panel.build({"AAA": bars}, {"AAA": np.ones(close.size, dtype=np.bool_)})


def _fire_at_zero(size: int) -> npt.NDArray[np.float64]:
    column = np.zeros(size, dtype=np.float64)
    column[0] = 1.0
    return column


def _run(goal: GoalConfig, strategy: object, panel: Panel, stop: float = 10.0) -> object:
    size = len(panel)
    return _sim(goal).run(
        strategy,  # type: ignore[arg-type]
        panel,
        signals={"AAA": _fire_at_zero(size)},
        stops={"AAA": np.full(size, stop)},
        starting_equity=Decimal(100_000),
    )


# --------------------------------------------------------------------------------------
# take_profit_r
# --------------------------------------------------------------------------------------


def test_a_take_profit_at_3r_actually_closes_the_trade(goal: GoalConfig) -> None:
    """Entry near 100 with a 10-wide stop puts the 3R target near 130.

    Price grinds to 140, so the target is crossed. Before this was implemented the position ran
    to the end of the data instead, and `donlevey_sweep_reclaim` — which declares exactly this
    rule — was measured as a strategy that never took profit.
    """
    strategy = _strategy("  - stop_loss_atr: {atr_mult: 2.0}\n  - take_profit_r: {r_multiple: 3.0}")
    result = _run(goal, strategy, _panel([100.0, 100.0, 110.0, 125.0, 140.0, 140.0]))
    assert len(result.trades) == 1  # type: ignore[attr-defined]
    trade = result.trades[0]  # type: ignore[attr-defined]
    assert trade.reason is ExitReason.TAKE_PROFIT
    assert trade.exit_price >= trade.entry_price + 3 * trade.risk_per_share


def test_without_a_take_profit_the_same_run_holds_to_the_end(goal: GoalConfig) -> None:
    """The control. Same prices, no target declared — so the difference above is the rule
    working, not the fixture."""
    strategy = _strategy("  - stop_loss_atr: {atr_mult: 2.0}")
    result = _run(goal, strategy, _panel([100.0, 100.0, 110.0, 125.0, 140.0, 140.0]))
    assert result.trades[0].reason is ExitReason.END_OF_DATA  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# take_profit_pct and precedence
# --------------------------------------------------------------------------------------


def test_a_percentage_target_closes_the_trade(goal: GoalConfig) -> None:
    strategy = _strategy("  - stop_loss_atr: {atr_mult: 2.0}\n  - take_profit_pct: {pct: 0.1}")
    result = _run(goal, strategy, _panel([100.0, 100.0, 105.0, 115.0, 115.0]))
    assert result.trades[0].reason is ExitReason.TAKE_PROFIT  # type: ignore[attr-defined]


def test_when_both_targets_are_declared_the_nearer_one_wins() -> None:
    """A 3R target on a 10-wide stop is +30; a 10% target on a 100 entry is +10.

    Taking the further of the two would let a strategy declare a tight target and be simulated
    with a loose one — silently more profitable than the thing written down.
    """
    plan = ExitPlan.of(
        [
            ExitRule(rule="take_profit_r", literals={"r_multiple": 3.0}),
            ExitRule(rule="take_profit_pct", literals={"pct": 0.1}),
        ]
    )
    assert plan.target_for(Decimal(100), Decimal(10)) == Decimal(110)


# --------------------------------------------------------------------------------------
# time_stop
# --------------------------------------------------------------------------------------


def test_a_time_stop_closes_a_position_that_is_going_nowhere(goal: GoalConfig) -> None:
    """Flat prices, a 3-bar time stop. Nothing else can trigger, so if the trade closes early it
    closed on time — and `bars_held` was previously incremented and never read."""
    strategy = _strategy("  - stop_loss_atr: {atr_mult: 2.0}\n  - time_stop: {bars: 3}")
    result = _run(goal, strategy, _panel([100.0] * 10))
    trade = result.trades[0]  # type: ignore[attr-defined]
    assert trade.reason is ExitReason.TIME_STOP
    assert (trade.exit_ts - trade.entry_ts).days <= 4


def test_without_a_time_stop_the_flat_position_survives_to_the_end(goal: GoalConfig) -> None:
    strategy = _strategy("  - stop_loss_atr: {atr_mult: 2.0}")
    result = _run(goal, strategy, _panel([100.0] * 10))
    assert result.trades[0].reason is ExitReason.END_OF_DATA  # type: ignore[attr-defined]


# --------------------------------------------------------------------------------------
# trailing_stop_atr — it must actually trail
# --------------------------------------------------------------------------------------


def test_a_trailing_stop_follows_the_price_up_and_locks_in_a_gain(goal: GoalConfig) -> None:
    """Price runs 100 -> 150 then falls back to 132.

    A fixed stop at entry-10 (~90) is never touched and the trade ends flat at the end of data.
    A stop trailing 10 behind the peak sits at ~140 by the top and closes the trade *in profit*
    on the way down. Before this, `trailing_stop_atr` installed a stop that never moved — so the
    rule parsed, was accepted, and did nothing.
    """
    strategy = _strategy("  - trailing_stop_atr: {atr_mult: 2.0}")
    prices = [100.0, 100.0, 120.0, 150.0, 132.0, 132.0]
    result = _run(goal, strategy, _panel(prices))
    trade = result.trades[0]  # type: ignore[attr-defined]
    assert trade.reason is ExitReason.TRAILING_STOP
    assert trade.exit_price > trade.entry_price, "the trail locked in a gain"


def test_a_trailing_stop_never_moves_down(goal: GoalConfig) -> None:
    """Price rises then falls; the stop must not follow it back down.

    A stop that can loosen is not a stop — an already-protected position would become unprotected
    again, and the risk the trade was sized on would stop describing its worst case.
    """
    strategy = _strategy("  - trailing_stop_atr: {atr_mult: 2.0}")
    # Entry ~100, stop 10 wide. Peak close 140 ratchets the stop to 130; the fall to 128 takes it
    # out. The original stop was at ~90 and would never have been touched, so the exit price is
    # the evidence: it must be up near the peak, not down at the entry stop.
    result = _run(goal, strategy, _panel([100.0, 100.0, 140.0, 128.0, 128.0]))
    trade = result.trades[0]  # type: ignore[attr-defined]
    assert trade.reason is ExitReason.TRAILING_STOP
    assert trade.exit_price > Decimal(125), "stop stayed up near the 140 peak, not back at 90"


# --------------------------------------------------------------------------------------
# The guard: nothing may be silently ignored again
# --------------------------------------------------------------------------------------


def test_an_exit_rule_the_simulator_cannot_honour_raises(goal: GoalConfig) -> None:
    """The whole point. A DSL word with no implementation here must stop the run.

    Skipping it — which is what happened for four of the six rules — means the strategy that was
    pre-registered and the strategy that was measured are different objects, and every number
    downstream describes something nobody wrote down.
    """
    with pytest.raises(ValueError, match="cannot honour"):
        ExitPlan.of([ExitRule(rule="exit_on_a_hunch", literals={})])


def test_every_rule_the_dsl_accepts_is_one_the_simulator_implements() -> None:
    """Walks ``EXIT_RULES`` itself, so adding a word to the DSL without teaching the simulator
    about it fails here rather than in a backtest six months later."""
    from icarus.strategy.dsl import EXIT_RULES

    defaults = {
        "stop_loss_atr": {"atr_mult": 2.0},
        "stop_loss_pct": {"pct": 0.05},
        "trailing_stop_atr": {"atr_mult": 2.0},
        "take_profit_r": {"r_multiple": 3.0},
        "take_profit_pct": {"pct": 0.1},
        "time_stop": {"bars": 20},
    }
    assert set(defaults) == set(EXIT_RULES), "a rule was added to the DSL; teach ExitPlan about it"
    for name, literals in defaults.items():
        ExitPlan.of([ExitRule(rule=name, literals=literals)])
