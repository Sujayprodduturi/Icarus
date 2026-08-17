"""A holding in a symbol that stops trading — task 2c, finding F4.

**What was wrong.** Every session the simulator asks each open position "do you exit today?", and
to answer it needs the day's bar. If the symbol printed none, the code skipped to the next
position — *including on the last bar of the fold*, the one where everything is supposed to be
closed out and counted. So a position in a delisted or suspended name was carried forever:

* it never became a closed trade, so it was invisible to win rate, expectancy, the trade log and
  the tax ledger;
* its money vanished — realised P&L only flows on a close, unrealised P&L is marked at a close
  that does not exist, and even the entry brokerage is only charged when the trade closes;
* it kept one of the four slots for the rest of the fold, in a book already discarding 94-99.99%
  of its signals for want of one.

Measured on the current panel before the fix: 96 of 693 symbols stop printing before the panel
ends, and 71 times a symbol is tradable one session and dark the next — 53 of those staying dark
for 60 or more sessions, one for 2,840. Rare enough that it is a correctness bug rather than an
explanation of the results, and unacceptable either way in something that will place real orders.

**What the fix must not do** is fire on an ordinary trading halt. A stock that stops for a week and
resumes was genuinely unsellable during that week, and carrying the position is right. So the
threshold matters in both directions, and both directions are tested here.
"""

from __future__ import annotations

from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np
import pytest
from tests.unit.simharness import simulator

from icarus.common.config import load_goal
from icarus.common.types import OrderSide
from icarus.engine.costmodel import CostModel, Segment
from icarus.engine.portfolio import ExitReason, PortfolioSimulator, RunResult
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    import numpy.typing as npt

    from icarus.common.config import GoalConfig

START = np.datetime64("2024-01-01")
_EQUITY = Decimal(1_000_000)


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _sim(
    goal: GoalConfig, *, stale_after: int = 20, slots: int | None = None
) -> PortfolioSimulator:
    # The concentration cap is off here on purpose (finding F34). These tests are about what
    # happens to a position whose symbol goes dark, and they need a large one to make the
    # write-off arithmetic legible; at the shipped 0.25 the cap would resize every fixture and
    # every hand-computed rupee figure below would be measuring the cap instead of the write-off.
    # The cap has its own module.
    return simulator(goal, slots=slots, position_pct=1.0, stale_after=stale_after)


def _bars(closes: npt.NDArray[np.float64]) -> Bars:
    """A flat-ish series where ``nan`` means the symbol printed nothing that session."""
    return Bars(
        ts=np.arange(START, START + closes.size).astype("datetime64[ns]"),
        open=closes.copy(),
        high=closes + 1.0,
        low=closes - 1.0,
        close=closes,
        volume=np.where(np.isnan(closes), np.nan, 1_000_000.0),
    )


def _goes_dark(size: int, at: int, *, resumes: int | None = None) -> npt.NDArray[np.float64]:
    """Prices that hold at 100 and stop printing from ``at``, optionally coming back."""
    closes = np.full(size, 100.0)
    closes[at:] = np.nan
    if resumes is not None:
        closes[resumes:] = 100.0
    return closes


def _panel(series: dict[str, npt.NDArray[np.float64]]) -> Panel:
    bars = {s: _bars(c) for s, c in series.items()}
    # Tradability follows the data: a session with no bar is not one the universe rules could have
    # admitted, and the real panel has no tradable day without a finite close.
    live = {s: ~np.isnan(c) for s, c in series.items()}
    return Panel.build(bars, live)


def _strategy() -> object:
    return parse_strategy(
        """
name: dark_test
version: 1
timeframe: 1d
universe: nse_liquid
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_pct: {pct: 0.5}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )


def _run(
    goal: GoalConfig,
    series: dict[str, npt.NDArray[np.float64]],
    *,
    stale_after: int = 20,
    slots: int | None = None,
    fire_at: dict[str, int] | None = None,
) -> RunResult:
    panel = _panel(series)
    size = len(panel)
    fire = fire_at or dict.fromkeys(series, 0)
    signals, stops = {}, {}
    for symbol in series:
        column = np.zeros(size, dtype=np.float64)
        column[fire[symbol]] = 1.0
        signals[symbol] = column
        stops[symbol] = np.full(size, 50.0)
    return _sim(goal, stale_after=stale_after, slots=slots).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops=stops,
        starting_equity=_EQUITY,
    )


# --------------------------------------------------------------------------------------
# The bug itself
# --------------------------------------------------------------------------------------


def test_a_symbol_that_stops_trading_still_produces_exactly_one_closed_trade(
    goal: GoalConfig,
) -> None:
    """Before 2c this run produced **zero** trades and the position was never heard from again."""
    result = _run(goal, {"AAA": _goes_dark(30, at=5)}, stale_after=20)
    assert len(result.trades) == 1
    assert result.trades[0].reason is ExitReason.STALE_MARK


def test_the_money_ends_up_in_the_equity_curve(goal: GoalConfig) -> None:
    """The heart of it: capital used to leave the accounts as neither a loss nor a gain.

    Final equity must equal the starting book plus every trade's net P&L — no residue, no leak.
    """
    result = _run(goal, {"AAA": _goes_dark(30, at=5)}, stale_after=20)
    booked = sum((t.net_pnl for t in result.trades), Decimal(0))
    assert result.final_equity == _EQUITY + booked


def test_the_entry_brokerage_is_charged_rather_than_forgotten(goal: GoalConfig) -> None:
    """It was only ever applied when a trade closed, so a position that never closed was free."""
    result = _run(goal, {"AAA": _goes_dark(30, at=5)}, stale_after=20)
    assert result.trades[0].entry_charges.total > 0
    assert result.trades[0].exit_charges.total > 0


def test_the_slot_is_released_so_a_later_signal_can_use_it(goal: GoalConfig) -> None:
    """A one-slot book. AAA dies on bar 5; BBB fires on bar 20 and must be able to take the seat.

    This is the consequence that compounds: the audit measured 94-99.99% of signals discarded for
    want of a slot, and a dead position was holding one of four permanently.
    """
    series = {"AAA": _goes_dark(40, at=5), "BBB": np.full(40, 100.0)}
    result = _run(goal, series, stale_after=10, slots=1, fire_at={"AAA": 0, "BBB": 20})
    assert {t.symbol for t in result.trades} == {"AAA", "BBB"}


# --------------------------------------------------------------------------------------
# The price it is written off at
# --------------------------------------------------------------------------------------


def test_it_closes_at_the_last_price_the_symbol_actually_printed(goal: GoalConfig) -> None:
    closes = np.full(30, 100.0)
    closes[4] = 137.0  # the last real print
    closes[5:] = np.nan
    result = _run(goal, {"AAA": closes}, stale_after=20)
    assert result.trades[0].exit_price == Decimal("137.0")


def test_the_optimism_is_reported_rather_than_hidden(goal: GoalConfig) -> None:
    """Marking at the last print flatters the result — a stock usually stops because something
    went wrong. The operator chose that over inventing a haircut (2026-08-14), on condition the
    exposure is visible, so the count and the gross rupees are carried on the result."""
    result = _run(goal, {"AAA": _goes_dark(30, at=5)}, stale_after=20)
    trade = result.trades[0]
    assert result.stale_marks == 1
    assert result.stale_mark_value == trade.exit_price * trade.quantity


def test_a_clean_run_reports_no_stale_marks_at_all(goal: GoalConfig) -> None:
    """The counter must stay at zero when nothing was assumed, or it says nothing when it moves."""
    result = _run(goal, {"AAA": np.full(30, 100.0)}, stale_after=20)
    assert result.stale_marks == 0
    assert result.stale_mark_value == Decimal(0)
    assert [t.reason for t in result.trades] == [ExitReason.END_OF_DATA]


# --------------------------------------------------------------------------------------
# The threshold, in both directions
# --------------------------------------------------------------------------------------


def test_an_ordinary_halt_does_not_trigger_a_write_off(goal: GoalConfig) -> None:
    """A stock that stops for a few days and comes back was genuinely unsellable meanwhile.

    Carrying the position through it is not a bug, it is the truth, and a fix that closed here
    would invent an exit at a price nobody could have got.
    """
    series = {"AAA": _goes_dark(40, at=5, resumes=12)}
    result = _run(goal, series, stale_after=20)
    assert result.stale_marks == 0
    assert [t.reason for t in result.trades] == [ExitReason.END_OF_DATA]


def test_the_threshold_is_the_exact_session_it_says(goal: GoalConfig) -> None:
    """One session short, the position lives; on the session itself, it is written off.

    Pinned exactly because an off-by-one here is invisible in any aggregate.
    """
    short = _run(goal, {"AAA": _goes_dark(30, at=5, resumes=9)}, stale_after=5)
    assert short.stale_marks == 0  # dark on bars 5..8 — four sessions, one short

    exact = _run(goal, {"AAA": _goes_dark(30, at=5, resumes=10)}, stale_after=5)
    assert exact.stale_marks == 1  # dark on bars 5..9 — the fifth trips it


def test_a_symbol_that_comes_back_resets_the_count(goal: GoalConfig) -> None:
    """Two four-session gaps are not one eight-session gap. The run that matters is the current
    one, which is why the counter lives on the position rather than being read off the panel."""
    closes = np.full(40, 100.0)
    closes[5:9] = np.nan
    closes[13:17] = np.nan
    result = _run(goal, {"AAA": closes}, stale_after=5)
    assert result.stale_marks == 0


def test_the_last_bar_of_the_fold_writes_off_however_briefly_it_has_been_dark(
    goal: GoalConfig,
) -> None:
    """The case the old code missed most cheaply: the `continue` ran even when `final=True`.

    One dark session is nothing — unless it is the session the fold ends on, when leaving the
    position open means leaving it out of the accounts for good.
    """
    closes = np.full(30, 100.0)
    closes[29] = np.nan
    result = _run(goal, {"AAA": closes}, stale_after=20)
    assert result.stale_marks == 1
    assert result.trades[0].reason is ExitReason.STALE_MARK


# --------------------------------------------------------------------------------------
# The equity curve across the gap
# --------------------------------------------------------------------------------------


def test_a_dark_stretch_does_not_carve_a_hole_in_the_equity_curve(goal: GoalConfig) -> None:
    """Found by the code review of this task, and it is the write-off's own side effect.

    Open P&L is marked at the day's close, and a dark day has none — so the position used to drop
    out of equity entirely the moment its symbol stopped printing, which is not "unknown", it is
    **zero**. A holding up 20% vanished on the day it went dark and reappeared as realised P&L
    twenty sessions later: two invented daily returns and a genuine peak-to-trough between them,
    feeding the volatility, the Sharpe and the max-drawdown the stop gate reads. Carrying the last
    traded price is what a broker statement does, and it makes the curve flat across the gap.
    """
    closes = np.full(40, 100.0)
    closes[1:6] = 130.0  # the position runs up before the symbol stops printing
    closes[6:] = np.nan
    result = _run(goal, {"AAA": closes}, stale_after=20)
    curve = [value for _ts, value in result.equity]
    steps = [b - a for a, b in pairwise(curve[5:])]

    # The session it goes dark must be flat: nothing happened, nothing can be marked differently.
    assert steps[0] == 0, "equity moved on the session the symbol stopped printing"
    # Exactly one step across the whole dark stretch, and it is the cost of closing — not a
    # revaluation. Anything else is a price change invented for a day with no price.
    moved = [s for s in steps if s != 0]
    assert moved == [-result.trades[0].costs]


# --------------------------------------------------------------------------------------
# Nothing survives the last bar
# --------------------------------------------------------------------------------------


_ENTERED = 5_000
"""Shares the starved scenario below buys: ₹1,000,000 book x 0.5% risk / ₹1 stop distance."""


def _starved(size: int = 30) -> Panel:
    """Deep enough to buy 5,000 shares, far too thin to sell them.

    Volume is a million for the first three sessions and forty thereafter, so the entry fills whole
    and every exit afterwards is capped by ``max_participation_of_depth`` to two shares a session.
    The bar is deliberately **narrow** — a ten-paisa range against a one-rupee stop — so the
    position is never stopped out and survives to the final bar with almost all of it unsold.

    Getting this fixture wrong is how the first draft of these two tests came to prove nothing: with
    thin volume from bar zero the *entry* was capped too, only two shares were ever bought, and both
    tests passed against a position that was fully closed by an ordinary exit.
    """
    closes = np.full(size, 100.0)
    volume = np.full(size, 40.0)
    volume[:3] = 1_000_000.0
    bars = Bars(
        ts=np.arange(START, START + size).astype("datetime64[ns]"),
        open=closes.copy(),
        high=closes + 0.1,
        low=closes - 0.1,
        close=closes,
        volume=volume,
    )
    return Panel.build({"AAA": bars}, {"AAA": np.ones(size, dtype=np.bool_)})


def _run_starved(goal: GoalConfig) -> RunResult:
    panel = _starved()
    size = len(panel)
    signals = {"AAA": np.zeros(size)}
    signals["AAA"][0] = 1.0
    return _sim(goal, stale_after=20).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops={"AAA": np.full(size, 1.0)},
        starting_equity=_EQUITY,
    )


def test_a_final_bar_exit_that_cannot_fill_still_leaves_no_position_behind(
    goal: GoalConfig,
) -> None:
    """The other half of F4, and the half the first pass missed.

    The write-off covered the *no-bar* case. But when the last bar exists and the closing order is
    capped by participation — or refused outright — the residual stayed in the book and the span
    ended around it: 4,998 of 5,000 shares never becoming a trade, invisible to the log, the win
    rate and the tax ledger, and never charged an exit cost. Mid-run an unfilled exit correctly
    leaves the position open and exposed; on the final bar there is no later to be exposed into.
    """
    result = _run_starved(goal)
    assert sum(t.quantity for t in result.trades) == _ENTERED
    assert {t.reason for t in result.trades} == {ExitReason.END_OF_DATA, ExitReason.STALE_MARK}
    assert result.final_equity == _EQUITY + sum((t.net_pnl for t in result.trades), Decimal(0))


def test_the_write_off_is_dated_to_the_bar_its_price_came_from(goal: GoalConfig) -> None:
    """Price and date have to describe the same event, or the holding period is fiction.

    Dating the exit at the session the write-off was *noticed* while pricing it at a session up to
    twenty earlier stretches ``holding_days`` by the whole dark stretch — and that is what buckets
    a trade as short- or long-term for tax.
    """
    closes = np.full(40, 100.0)
    closes[10:] = np.nan
    result = _run(goal, {"AAA": closes}, stale_after=20)
    trade = result.trades[0]
    assert trade.exit_ts.date().isoformat() == str(START + 9)  # the last bar it printed


# --------------------------------------------------------------------------------------
# Entry cost is shared out, not repeated
# --------------------------------------------------------------------------------------


def test_a_position_closed_in_pieces_pays_its_entry_cost_once(goal: GoalConfig) -> None:
    """``entry_charges`` is the cost of the whole entry, and every chunk was being handed all of it.

    A position drained over nine partial fills booked nine full entry charges — roughly nine times
    what was actually paid — straight into net P&L, expectancy and the tax ledger. Pre-existing,
    but the write-off inherits the same field, so it is fixed here.
    """
    result = _run_starved(goal)
    assert len(result.trades) > 1, "the fixture produced one clean exit and tested nothing"
    booked = sum((t.entry_charges.total for t in result.trades), Decimal(0))
    once = CostModel(goal.costs).charges(
        Segment.EQUITY_DELIVERY,
        OrderSide.BUY,
        result.trades[0].entry_price,
        Decimal(_ENTERED),
    )
    # The pieces must add up to the entry cost, not to a multiple of it.
    assert booked == once.total


# --------------------------------------------------------------------------------------
# Fail safe
# --------------------------------------------------------------------------------------


def test_writing_off_a_symbol_with_no_price_at_all_raises_rather_than_guessing(
    goal: GoalConfig,
) -> None:
    """A holding that never had a bar cannot exist — the position could not have been opened.

    If it somehow does, the simulator has lost track of its own book, and inventing a price for it
    would bury that. Invariant #10: fail safe, not silent.
    """
    from icarus.engine.portfolio import _last_traded_close

    panel = _panel({"AAA": np.full(10, np.nan)})
    with pytest.raises(ValueError, match="printed no close"):
        _last_traded_close(panel, 0, 5)
