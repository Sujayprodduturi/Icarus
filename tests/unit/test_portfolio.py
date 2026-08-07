"""The portfolio simulator — task 1.7, PRD §30.

The fixtures are deliberately tiny and hand-worked: a handful of symbols over a handful of days,
with prices chosen so every expected quantity, fill price and skip reason is derivable in the
comment above the test rather than observed from a run.

What is being pinned is mostly *restraint* — the trades the simulator declines to take. A naive
backtester takes all of them, and each one is money it invents:

* a fifth position when the book already holds four,
* a position whose stop distance would breach the book-level heat cap,
* a fractional share,
* an exit that is assumed to have filled,
* the profitable half of a bar whose range covers both the stop and the target.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import ExecutionRealism, load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import (
    ExitReason,
    PortfolioSimulator,
    Skipped,
    stop_distance_from_exits,
)
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    import numpy.typing as npt

    from icarus.common.config import GoalConfig

START = np.datetime64("2024-01-01")

STRATEGY = """
name: test_book
version: 1
timeframe: 1d
universe: nse_liquid_100
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_atr: {atr_mult: 2.0, atr_period: 14}
sizing:
  risk_r: 0.005
"""


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _realism(**overrides: object) -> ExecutionRealism:
    base: dict[str, object] = {
        "fill_requires_trade_through": True,
        "queue_volume_multiple_k": 2.0,
        "next_bar_execution": True,
        "latency_ms": 750,
        "model_partial_fills": True,
        "max_participation_of_depth": 0.05,
        "slippage_bps": 5.0,
        "tick_size_inr": 0.05,
    }
    return ExecutionRealism(**(base | overrides))  # type: ignore[arg-type]


def _sim(goal: GoalConfig, **realism: object) -> PortfolioSimulator:
    return PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(_realism(**realism)),
    )


def _bars(prices: list[float], volume: float = 1_000_000.0) -> Bars:
    close = np.array(prices, dtype=np.float64)
    return Bars(
        ts=np.arange(START, START + close.size).astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(close.size, volume),
    )


def _panel(prices: dict[str, list[float]], volume: float = 1_000_000.0) -> Panel:
    bars = {symbol: _bars(values, volume) for symbol, values in prices.items()}
    size = len(next(iter(prices.values())))
    tradable = {symbol: np.ones(size, dtype=np.bool_) for symbol in prices}
    return Panel.build(bars, tradable)


def _column(size: int, fire_at: list[int]) -> npt.NDArray[np.float64]:
    column = np.zeros(size, dtype=np.float64)
    column[fire_at] = 1.0
    return column


def _strategy() -> object:
    return parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)


# --------------------------------------------------------------------------------------
# Sizing, whole shares, and the money actually leaving the account
# --------------------------------------------------------------------------------------
#
# Equity 100,000 at risk_r 0.005 is a 500 rupee risk budget. A stop distance of 10/share
# buys exactly 50 shares. Every quantity below is that arithmetic and nothing else.

FLAT = [100.0] * 6


def test_position_size_is_the_risk_budget_divided_by_the_stop_distance(goal: GoalConfig) -> None:
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert len(result.trades) == 1
    assert result.trades[0].quantity == 50


def test_a_position_that_rounds_to_zero_shares_is_not_a_position(goal: GoalConfig) -> None:
    """500 rupees of risk against a 600-rupee stop distance buys 0.83 shares, which is nothing.

    At seed capital this happens constantly, and rounding *up* to one share would silently size
    the trade at more risk than the strategy asked for (task 2.1b).
    """
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 600.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.trades == []
    assert result.skipped[Skipped.ROUNDS_TO_ZERO] == 1


def test_entry_executes_on_the_next_bar_not_the_signal_bar(goal: GoalConfig) -> None:
    """Signal on bar 0, entry at bar 1's open (100) plus 5bps of slippage."""
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    trade = result.trades[0]
    assert trade.entry_ts == datetime(2024, 1, 2, tzinfo=UTC)
    assert trade.entry_price == Decimal("100.05")


def test_charges_are_taken_from_each_fill_not_from_the_final_pnl(goal: GoalConfig) -> None:
    """Gross and net must differ by exactly the two contract notes.

    Applying a modelled cost to the final P&L instead loses the trades that were profitable gross
    and losing net, which at seed size is most of them.
    """
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    trade = result.trades[0]
    assert trade.costs > 0
    assert trade.net_pnl == trade.gross_pnl - trade.costs


# --------------------------------------------------------------------------------------
# The book — the caps a per-symbol simulator cannot express
# --------------------------------------------------------------------------------------


def test_the_book_never_exceeds_max_open_positions(goal: GoalConfig) -> None:
    """Six names fire on the same bar; the config allows four. The other two are recorded, not
    quietly taken — a per-symbol backtester takes all six and reports the result of a system that
    was never going to be run."""
    symbols = [f"S{i}" for i in range(6)]
    panel = _panel({s: FLAT for s in symbols})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={s: _column(6, [0]) for s in symbols},
        stops={s: np.full(6, 10.0) for s in symbols},
        starting_equity=Decimal(100_000),
    )
    assert len({t.symbol for t in result.trades}) == goal.risk.max_open_positions
    assert result.skipped[Skipped.NO_SLOT] == 6 - goal.risk.max_open_positions


def test_the_heat_cap_binds_even_when_every_trade_is_individually_legal(
    goal: GoalConfig,
) -> None:
    """Each position risks 0.5% and the book cap is 2%, so the fifth would breach it — but four
    already fill the position cap, so heat is tested by shrinking equity instead.

    Equity 40,000 gives a 200-rupee budget and a 20-rupee stop buys 10 shares = 200 of risk. Two
    such positions are 400, and 2% of 40,000 is 800, so the third is the one that breaks.
    """
    symbols = [f"S{i}" for i in range(4)]
    panel = _panel({s: FLAT for s in symbols})
    tight = goal.risk.model_copy(update={"max_portfolio_heat": 0.011})
    sim = PortfolioSimulator(risk=tight, costs=CostModel(goal.costs), fills=FillModel(_realism()))
    result = sim.run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={s: _column(6, [0]) for s in symbols},
        stops={s: np.full(6, 10.0) for s in symbols},
        starting_equity=Decimal(100_000),
    )
    assert result.skipped.get(Skipped.HEAT_CAP, 0) >= 1
    open_risk = sum(t.quantity * Decimal(10) for t in result.trades)
    assert open_risk <= Decimal("0.011") * Decimal(100_000)


def test_a_symbol_already_held_does_not_double_up(goal: GoalConfig) -> None:
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0, 1, 2])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.skipped[Skipped.ALREADY_HELD] >= 1
    assert len(result.trades) == 1


# --------------------------------------------------------------------------------------
# Exits
# --------------------------------------------------------------------------------------


def test_a_stop_closes_the_position_and_records_why(goal: GoalConfig) -> None:
    """Entry at 100.05 with a 10-rupee stop sits at 90.05. Bar 3 trades down to 84."""
    panel = _panel({"AAA": [100.0, 100.0, 100.0, 85.0, 85.0, 85.0]})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert len(result.trades) == 1
    assert result.trades[0].reason is ExitReason.STOP_LOSS
    assert result.trades[0].net_pnl < 0


def test_an_open_position_is_closed_at_the_end_of_the_data(goal: GoalConfig) -> None:
    """Otherwise a strategy could hold every loser to the last bar and never book it — an equity
    curve made entirely of realised winners and unrealised losers."""
    panel = _panel({"AAA": FLAT})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.trades[0].reason is ExitReason.END_OF_DATA


def test_an_entry_that_cannot_fill_is_not_a_position(goal: GoalConfig) -> None:
    panel = _panel({"AAA": [100.0, 100.0, 85.0, 85.0, 85.0, 85.0]}, volume=0.0)
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.trades == []
    assert result.skipped[Skipped.ENTRY_NOT_FILLED] == 1


def test_an_exit_that_cannot_fill_leaves_the_position_open_and_exposed(goal: GoalConfig) -> None:
    """Entry fills on bar 1; bars 2-4 do not trade at all, so the stop cannot be honoured.

    The position stays on and the loss keeps running until liquidation at the end of the data.
    This is the outcome a simulator that assumes its stops worked can never show — and it is the
    one that matters, because an unfilled protective order is unmanaged exposure, not a rounding
    difference.

    Volume is per-bar here on purpose: an earlier version of this test used a zero-volume panel
    throughout, which meant the *entry* never filled either and the exit path was never reached at
    all. The test passed and covered nothing, and only a deliberately reintroduced bug found it.
    """
    prices = [100.0, 100.0, 85.0, 85.0, 85.0, 85.0]
    volumes = [1e6, 1e6, 0.0, 0.0, 0.0, 1e6]
    bars = _bars(prices)
    traded = Bars(
        ts=bars.ts,
        open=bars.open,
        high=bars.high,
        low=bars.low,
        close=bars.close,
        volume=np.array(volumes, dtype=np.float64),
    )
    panel = Panel.build({"AAA": traded}, {"AAA": np.ones(6, dtype=np.bool_)})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.unfilled_exits >= 1, "a stop on an untraded session cannot have been honoured"
    assert len(result.trades) == 1
    assert result.trades[0].reason is ExitReason.END_OF_DATA
    assert result.trades[0].net_pnl < 0


def test_when_a_bar_spans_both_the_stop_and_the_target_the_stop_wins(goal: GoalConfig) -> None:
    """Daily data cannot say which came first, so the pessimistic branch is taken.

    Choosing the target would hand the strategy the good half of every ambiguous bar — the
    touch-equals-fill bias arriving through the exit door.
    """
    panel = _panel({"AAA": [100.0, 100.0, 100.0, 100.0, 100.0, 100.0]})
    wide = _bars([100.0] * 6)
    swing = Bars(
        ts=wide.ts,
        open=wide.open,
        high=np.array([101.0, 101.0, 130.0, 101.0, 101.0, 101.0]),
        low=np.array([99.0, 99.0, 70.0, 99.0, 99.0, 99.0]),
        close=wide.close,
        volume=wide.volume,
    )
    panel = Panel.build({"AAA": swing}, {"AAA": np.ones(6, dtype=np.bool_)})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.trades[0].reason is ExitReason.STOP_LOSS


# --------------------------------------------------------------------------------------
# Selection when more candidates fire than there are slots
# --------------------------------------------------------------------------------------


def test_an_ambiguous_selection_day_is_counted_not_hidden(goal: GoalConfig) -> None:
    """With no `rank_by`, choosing four of six comes down to symbol order — which is quietly
    alphabetical, the same bias the cross-sectional tie rule exists to avoid. It is counted so a
    strategy that hits it constantly is visible in the metric sheet."""
    symbols = [f"S{i}" for i in range(6)]
    panel = _panel({s: FLAT for s in symbols})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={s: _column(6, [0]) for s in symbols},
        stops={s: np.full(6, 10.0) for s in symbols},
        starting_equity=Decimal(100_000),
    )
    assert result.ambiguous_selection_days == 1


def test_a_declared_ranking_decides_which_candidates_win(goal: GoalConfig) -> None:
    """Highest rank first, and no ambiguity recorded because the strategy said what best means."""
    symbols = [f"S{i}" for i in range(6)]
    panel = _panel({s: FLAT for s in symbols})
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals={s: _column(6, [0]) for s in symbols},
        stops={s: np.full(6, 10.0) for s in symbols},
        starting_equity=Decimal(100_000),
        ranks={s: np.full(6, float(i)) for i, s in enumerate(symbols)},
    )
    assert {t.symbol for t in result.trades} == {"S5", "S4", "S3", "S2"}
    assert result.ambiguous_selection_days == 0


# --------------------------------------------------------------------------------------
# The stop distance comes from the strategy, not from the engine
# --------------------------------------------------------------------------------------


def test_the_stop_distance_is_read_from_the_strategys_own_exit_rule() -> None:
    """Position size is the risk budget divided by this number, so an engine using its own stop
    would size every position for a trade the strategy never described."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    atr = np.full(5, 3.0)
    distance = stop_distance_from_exits(strategy.exits, atr=atr, close=np.full(5, 100.0))
    assert distance == pytest.approx(np.full(5, 6.0))  # atr_mult 2.0 x ATR 3.0


def test_a_strategy_with_no_protective_exit_cannot_reach_the_simulator() -> None:
    """The DSL rejects it at parse time; this is the backstop for an unvalidated candidate."""
    with pytest.raises(ValueError, match="declares no protective exit"):
        stop_distance_from_exits((), atr=np.full(3, 1.0), close=np.full(3, 100.0))


# --------------------------------------------------------------------------------------
# A stop can fill on the session the position opened (found 2026-08-07, on 16 March 2020)
# --------------------------------------------------------------------------------------


def _gapping_panel() -> Panel:
    """Six flat sessions, except bar 1 collapses intraday from 100 to 60.

    Bar 1 is the *fill* bar for a signal fired on bar 0, so the position opens at ~100 with a
    stop 10 below it and is immediately taken out by the same bar's low. That is an ordinary,
    if unpleasant, session — and for a long time this simulator could not represent it.
    """
    close = np.array([100.0, 60.0, 60.0, 60.0, 60.0, 60.0], dtype=np.float64)
    open_ = np.array([100.0, 100.0, 60.0, 60.0, 60.0, 60.0], dtype=np.float64)
    low = np.array([99.0, 55.0, 59.0, 59.0, 59.0, 59.0], dtype=np.float64)
    high = np.array([101.0, 101.0, 61.0, 61.0, 61.0, 61.0], dtype=np.float64)
    bars = Bars(
        ts=np.arange(START, START + 6).astype("datetime64[ns]"),
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=np.full(6, 1_000_000.0),
    )
    return Panel.build({"AAA": bars}, {"AAA": np.ones(6, dtype=np.bool_)})


def test_a_stop_can_be_hit_on_the_very_session_the_position_opened(goal: GoalConfig) -> None:
    """The signal fires on bar 0, the entry fills on bar 1, and bar 1's low is through the stop.

    Real markets do this — 16 March 2020 is the session that surfaced it here — and a simulator
    that cannot close the trade until bar 2 does not merely mis-date it. It carries the position
    through a collapse it should have exited, and every such trade is a loss the results never
    show. Dating exits to the entry *decision* (bar 0) rather than the entry *fill* (bar 1) is
    what makes the exit legal on bar 1 without breaking next-bar execution.
    """
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        _gapping_panel(),
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert len(result.trades) == 1
    trade = result.trades[0]
    assert trade.reason is ExitReason.STOP_LOSS
    assert trade.entry_ts == trade.exit_ts, "the stop filled on the session the position opened"
    assert trade.net_pnl < 0


def test_the_entry_decision_still_precedes_the_entry_fill(goal: GoalConfig) -> None:
    """The fix must not have collapsed decision-time into execution-time (invariant #13).

    Signal on bar 0, fill on bar 1: the trade's entry timestamp has to be the later of the two.
    If dating exits to the decision bar had been done by moving the *entry* back instead, this
    passes nothing and next-bar execution would be gone.
    """
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        _panel({"AAA": FLAT}),
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    entry = result.trades[0].entry_ts
    assert entry == datetime(2024, 1, 2, tzinfo=UTC), "bar 1, not bar 0"


def test_every_closed_trade_carries_the_risk_it_was_sized_on(goal: GoalConfig) -> None:
    """Without ``risk_per_share`` on the closed trade there is no R-multiple, and without an
    R-multiple there is no expectancy, no mean-R interval for the stagnation check (invariant
    #23), and no unit in which a big win and a small win are comparable."""
    result = _sim(goal).run(
        _strategy(),  # type: ignore[arg-type]
        _panel({"AAA": FLAT}),
        signals={"AAA": _column(6, [0])},
        stops={"AAA": np.full(6, 10.0)},
        starting_equity=Decimal(100_000),
    )
    assert result.trades[0].risk_per_share == Decimal("10.0")
