"""The book cannot spend money it does not have — task 2d, finding F6.

**What was wrong.** Position size is ``risk_budget / stop_distance``: risk a fixed number of rupees,
so a tight stop buys more shares and a wide stop fewer. Sensible, and unbounded — the narrower the
stop, the larger the position, with nothing capping the rupees deployed. Four checks stood between a
signal and a fill (a free slot, the heat cap, whole shares, the fill itself) and **not one of them
asked whether the account could pay**.

**Why the heat cap could never have caught it.** Heat is ``stop_distance x quantity``, and quantity
is ``risk_budget / stop_distance`` — the stop distance cancels. Every position contributes exactly
``risk_r`` to heat however large it is, so four positions always use 2.0% against a cap of 2.0%: the
cap equals the ceiling and can never bind. Heat measures *risk*; this is *capital*, and nothing was
measuring capital.

**Measured on the panel before the fix.** ``ATR/price`` runs from 3.3% at the median down to 0.003%
at the extreme, where the stop is almost nothing and the position becomes almost everything: the
widest single position a 2x-ATR stop would ask for is **7,706% of equity**, and 0.45% of tradable
symbol-days would produce one over 100%. This is the delivery segment, where leverage is not unwise
but unavailable — those shares could not have been bought with money that did not exist.

**What is actually asserted, in increasing order of strength.** Individual refusals, which check
consequences. A sweep over stop widths and universe sizes, which checks that no single position
and no overlapping set of them ever costs more than the book — reconstructed from the trade log,
so it sees what the run produced rather than what the book held. And one test that reaches into
the engine and hands it a book it could not have bought, because the guard that recomputes
committed cash every entry pass is the only thing standing between a future refactor and an
equity curve that is quietly a little too good.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import ExecutionRealism, load_goal
from icarus.common.types import OrderSide
from icarus.engine.costmodel import CostModel, Segment
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import (
    ExitPlan,
    OpenPosition,
    PortfolioSimulator,
    RunResult,
    Skipped,
    _committed_cash,
    _ts_at,
)
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    from icarus.common.config import GoalConfig

START = np.datetime64("2024-01-01")
_EQUITY = Decimal(100_000)


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _sim(goal: GoalConfig, *, slots: int = 4, position_pct: float = 1.0) -> PortfolioSimulator:
    """**The concentration cap is off by default here, deliberately (finding F34).**

    It ships at 0.25, which bounds every position to a quarter of the book — so with it on, no
    single position can exhaust the account and most of the cases below become unreachable. That
    does not make the cash gate redundant: it is the guard that has to hold whatever the
    concentration cap is set to, and a unit test of one guard should not depend on another being
    configured a particular way. The cap has its own module, and the interaction between the two
    is asserted once at the end of this one, at the shipped value.
    """
    return PortfolioSimulator(
        risk=goal.risk.model_copy(
            update={"max_open_positions": slots, "max_position_pct_of_equity": position_pct}
        ),
        costs=CostModel(goal.costs),
        fills=FillModel(
            ExecutionRealism(
                fill_requires_trade_through=True,
                queue_volume_multiple_k=2.0,
                next_bar_execution=True,
                latency_ms=750,
                model_partial_fills=True,
                max_participation_of_depth=0.05,
                slippage_bps=5.0,
                tick_size_inr=0.05,
            )
        ),
        stale_after_sessions=20,
    )


def _strategy() -> object:
    return parse_strategy(
        """
name: cash_test
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


def _flat_panel(symbols: tuple[str, ...], size: int = 30, price: float = 100.0) -> Panel:
    """Deep, quiet bars: a narrow range so no stop triggers, volume so no fill is capped."""
    closes = np.full(size, price)
    bars = {
        symbol: Bars(
            ts=np.arange(START, START + size).astype("datetime64[ns]"),
            open=closes.copy(),
            high=closes + 0.1,
            low=closes - 0.1,
            close=closes,
            volume=np.full(size, 50_000_000.0),
        )
        for symbol in symbols
    }
    return Panel.build(bars, {s: np.ones(size, dtype=np.bool_) for s in symbols})


def _run(
    goal: GoalConfig,
    *,
    stop_distance: float,
    symbols: tuple[str, ...] = ("AAA",),
    fire_at: int = 0,
    slots: int = 4,
    equity: Decimal = _EQUITY,
    panel: Panel | None = None,
    fire: dict[str, int] | None = None,
    position_pct: float = 1.0,
) -> RunResult:
    panel = panel or _flat_panel(symbols)
    size = len(panel)
    at = fire or dict.fromkeys(symbols, fire_at)
    signals, stops = {}, {}
    for symbol in panel.symbols:
        column = np.zeros(size, dtype=np.float64)
        column[at[symbol]] = 1.0
        signals[symbol] = column
        stops[symbol] = np.full(size, stop_distance)
    return _sim(goal, slots=slots, position_pct=position_pct).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops=stops,
        starting_equity=equity,
    )


def _committed(result: RunResult) -> Decimal:
    """Rupees the run spent on entries — cost basis plus the brokerage paid to acquire it."""
    return sum(
        (t.entry_price * t.quantity + t.entry_charges.total for t in result.trades), Decimal(0)
    )


# --------------------------------------------------------------------------------------
# A position bigger than the account
# --------------------------------------------------------------------------------------


def test_a_stop_tight_enough_to_demand_more_than_the_account_is_refused(
    goal: GoalConfig,
) -> None:
    """₹100,000 x 0.5% risk = ₹500 of risk. At a 1-paisa stop that is 50,000 shares at ₹100 —
    ₹5,000,000, fifty times the account. Every other check passes: one slot, whole shares, and
    heat of exactly ₹500 against a ₹2,000 cap."""
    result = _run(goal, stop_distance=0.01)
    assert result.skipped.get(Skipped.INSUFFICIENT_CASH) == 1
    assert result.trades == []


def test_a_position_the_account_can_afford_is_untouched(goal: GoalConfig) -> None:
    """The guard must not become a general brake. A ₹5 stop buys 100 shares — ₹10,000 of a
    ₹100,000 book — and nothing about that should change."""
    result = _run(goal, stop_distance=5.0)
    assert Skipped.INSUFFICIENT_CASH not in result.skipped
    assert len(result.trades) == 1
    assert result.trades[0].quantity == 100


def test_the_refusal_lands_on_the_cash_check_and_not_on_the_heat_cap(goal: GoalConfig) -> None:
    """Naming the right cause matters: the heat cap *cannot* catch this, and a metric sheet
    blaming it would send the next reader to the wrong number.

    Heat is stop_distance x quantity, and quantity is risk_budget / stop_distance, so the stop
    distance cancels and every position uses exactly risk_r of heat no matter how large it is.
    """
    result = _run(goal, stop_distance=0.01)
    assert Skipped.HEAT_CAP not in result.skipped
    assert result.skipped.get(Skipped.INSUFFICIENT_CASH) == 1


# --------------------------------------------------------------------------------------
# Several positions competing for one pot of money
# --------------------------------------------------------------------------------------


def test_positions_that_each_fit_but_do_not_fit_together_are_refused_in_turn(
    goal: GoalConfig,
) -> None:
    """Four names at ₹40,000 each: the first two fit inside ₹100,000, the rest cannot.

    A per-position check would have passed all four and deployed 160% of the account. The budget
    has to be shared, which means tracking what the earlier fills already spent.
    """
    symbols = ("AAA", "BBB", "CCC", "DDD")
    # ₹500 of risk / ₹1.25 stop = 400 shares at ₹100 = ₹40,000 apiece.
    result = _run(goal, stop_distance=1.25, symbols=symbols, slots=4)
    assert len(result.trades) == 2
    assert result.skipped.get(Skipped.INSUFFICIENT_CASH) == 2
    assert _committed(result) <= _EQUITY


def test_cash_returned_by_an_exit_can_be_spent_again(goal: GoalConfig) -> None:
    """The constraint is a balance, not a lifetime quota.

    Two names each wanting ₹90,000 of a ₹100,000 book: they cannot both be held, but the second
    must be takeable once the first has been sold and the money is back. The first draft of this
    test sized both at ₹333,000, so both were refused, nothing was ever committed and nothing was
    ever returned — it asserted a refusal and called it a test of reuse.
    """
    size = 30
    closes = np.full(size, 100.0)
    # AAA is stopped out on bar 4 by a single deep dip; BBB fires on bar 10 with the cash back.
    dips = closes.copy()
    dips[4] = 88.0
    bars = {
        "AAA": Bars(
            ts=np.arange(START, START + size).astype("datetime64[ns]"),
            open=closes.copy(),
            high=closes + 0.1,
            low=dips - 0.1,
            close=dips,
            volume=np.full(size, 50_000_000.0),
        ),
        "BBB": Bars(
            ts=np.arange(START, START + size).astype("datetime64[ns]"),
            open=closes.copy(),
            high=closes + 0.1,
            low=closes - 0.1,
            close=closes,
            volume=np.full(size, 50_000_000.0),
        ),
    }
    panel = Panel.build(bars, {s: np.ones(size, dtype=np.bool_) for s in bars})
    signals = {"AAA": np.zeros(size), "BBB": np.zeros(size)}
    signals["AAA"][0] = 1.0
    signals["BBB"][10] = 1.0
    result = _sim(goal, slots=4).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        # ₹500 risk / ₹0.5555 = 900 shares at ~₹100 = ~₹90,000 each: one fits, two never do.
        {"AAA": signals["AAA"], "BBB": signals["BBB"]},
        {s: np.full(size, 0.5555) for s in bars},
        starting_equity=_EQUITY,
    )
    assert {t.symbol for t in result.trades} == {"AAA", "BBB"}
    assert Skipped.INSUFFICIENT_CASH not in result.skipped
    # ...and they were never held at the same time, which is what made the reuse necessary.
    aaa = next(t for t in result.trades if t.symbol == "AAA")
    bbb = next(t for t in result.trades if t.symbol == "BBB")
    assert aaa.exit_ts <= bbb.entry_ts


def test_the_brokerage_counts_toward_what_must_be_afforded(goal: GoalConfig) -> None:
    """The boundary sits between two sizes that differ only by whether the charges fit.

    At ₹100.05 a share, 999 shares is ₹99,949.95 of stock — inside a ₹100,000 book — and ₹118.68
    of charges takes it to ₹100,068.63, which is not. 997 shares clears both. Charges are a real
    cash outflow at entry; leaving them out of the check would let the book end a session a few
    hundred rupees overdrawn, which is a small version of the bug being fixed.
    """
    just_over = _run(goal, stop_distance=0.5005)  # 999 shares
    assert just_over.skipped.get(Skipped.INSUFFICIENT_CASH) == 1
    assert just_over.trades == []

    just_under = _run(goal, stop_distance=0.5015)  # 997 shares
    assert Skipped.INSUFFICIENT_CASH not in just_under.skipped
    assert just_under.trades[0].quantity == 997
    assert _committed(just_under) <= _EQUITY


# --------------------------------------------------------------------------------------
# The invariant — not a case anyone thought of
# --------------------------------------------------------------------------------------


def test_a_half_sold_position_owes_only_half_its_entry_charge(goal: GoalConfig) -> None:
    """The identity ``cash = equity - committed`` is exact only if the entry charge is pro-rated.

    When a partial exit closes half a position, that half's share of the entry charge has already
    left equity through ``net_pnl``. Counting the whole charge as still committed subtracts it
    twice and understates cash — small, conservative, and still capable of refusing a position the
    account could afford. The boundary test above works in a window ₹68 wide, so "conservative" is
    not the same as "harmless".
    """
    charges = CostModel(goal.costs).charges(
        Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(100), Decimal(100)
    )
    when = _ts_at(_flat_panel(("AAA",)), 0)
    half_sold = OpenPosition(
        symbol="AAA",
        quantity=50,
        entry_price=Decimal(100),
        entry_ts=when,
        decided_at=when,
        entry_charges=charges,
        entry_quantity=100,
        stop_price=Decimal(95),
        risk_per_share=Decimal(5),
        take_profit=None,
    )
    assert _committed_cash({"AAA": half_sold}) == Decimal(5_000) + charges.total / 2


def test_the_simulator_refuses_to_run_with_a_book_it_could_not_have_paid_for(
    goal: GoalConfig,
) -> None:
    """The invariant itself, asserted where it lives rather than reconstructed from the trade log.

    Everything else in this file checks consequences: a refusal here, a cost basis there. None of
    them would notice a future refactor that let cash go negative *between* the entry checks. The
    engine now recomputes committed cash at the top of every entry pass and raises if it exceeds
    the book, and this proves that guard is wired up rather than decorative — by handing the
    simulator a book it could not have bought.
    """
    panel = _flat_panel(("AAA", "BBB"))
    size = len(panel)
    when = _ts_at(panel, 0)
    charges = CostModel(goal.costs).charges(
        Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(100), Decimal(2_000)
    )
    impossible = OpenPosition(
        symbol="AAA",
        quantity=2_000,  # ₹200,000 of stock against a ₹100,000 book
        entry_price=Decimal(100),
        entry_ts=when,
        decided_at=when,
        entry_charges=charges,
        entry_quantity=2_000,
        stop_price=Decimal(95),
        risk_per_share=Decimal(5),
        take_profit=None,
    )
    assert _committed_cash({"AAA": impossible}) > _EQUITY

    strategy = _strategy()
    signals = {"AAA": np.zeros(size), "BBB": np.zeros(size)}
    signals["BBB"][0] = 1.0  # something must be asking to buy, or the pass returns before the check
    with pytest.raises(ValueError, match="cash is negative"):
        _sim(goal)._process_entries(
            strategy,  # type: ignore[arg-type]
            ExitPlan.of(strategy.exits),  # type: ignore[attr-defined]
            {"AAA": impossible},
            panel,
            0,
            when,
            signals,
            {s: np.full(size, 5.0) for s in ("AAA", "BBB")},
            None,
            _EQUITY,
            RunResult(),
        )


def _no_position_exceeds_the_account(goal: GoalConfig, stop_distance: float, symbols: int) -> None:
    names = tuple(f"S{i:02d}" for i in range(symbols))
    panel = _flat_panel(names, size=40)
    size = len(panel)
    signals, stops = {}, {}
    rng = np.random.default_rng(4)
    for symbol in names:
        column = np.zeros(size, dtype=np.float64)
        column[rng.integers(0, 20, 3)] = 1.0  # a few signals each, at scattered bars
        signals[symbol] = column
        stops[symbol] = np.full(size, stop_distance)
    result = _sim(goal, slots=4).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops=stops,
        starting_equity=_EQUITY,
    )
    assert all(
        t.entry_price * t.quantity + t.entry_charges.total <= _EQUITY for t in result.trades
    ), "a single position cost more than the whole account"


@pytest.mark.parametrize("stop_distance", [0.01, 0.05, 0.25, 1.0, 5.0, 25.0])
@pytest.mark.parametrize("symbols", [1, 4, 12])
def test_no_single_position_ever_costs_more_than_the_account(
    goal: GoalConfig, stop_distance: float, symbols: int
) -> None:
    """Swept across stop widths and universe sizes rather than aimed at one scenario.

    The tight end of this sweep is where the bug lived: at a 1-paisa stop the old code sized a
    ₹5,000,000 position against a ₹100,000 book and recorded it as an ordinary trade.
    """
    _no_position_exceeds_the_account(goal, stop_distance, symbols)


@pytest.mark.parametrize("stop_distance", [0.01, 0.05, 0.25, 1.0, 5.0])
def test_the_book_never_holds_more_than_it_paid_for(goal: GoalConfig, stop_distance: float) -> None:
    """Concurrent cost basis, reconstructed from the trade log, may never exceed the book.

    Overlap is what makes this different from the per-position check above: four positions each
    inside the account can still be 160% of it together, which is the case the shared budget exists
    to stop and the one a per-trade assertion cannot see.
    """
    names = tuple(f"S{i:02d}" for i in range(8))
    panel = _flat_panel(names, size=40)
    size = len(panel)
    signals, stops = {}, {}
    for i, symbol in enumerate(names):
        column = np.zeros(size, dtype=np.float64)
        column[i] = 1.0  # staggered entries, so several are open at once
        signals[symbol] = column
        stops[symbol] = np.full(size, stop_distance)
    result = _sim(goal, slots=4).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops=stops,
        starting_equity=_EQUITY,
    )
    events: list[tuple[object, Decimal]] = []
    for trade in result.trades:
        cost = trade.entry_price * trade.quantity + trade.entry_charges.total
        events.append((trade.entry_ts, cost))
        events.append((trade.exit_ts, -cost))
    outstanding = Decimal(0)
    # Exits settle before entries at the same timestamp, because that is what the simulator does:
    # `run()` calls `_process_exits` first by explicit design, so a slot — and the cash in it —
    # freed this morning is available to this morning's signal. Sorting the other way would flag a
    # breach on any bar where a sale funded a purchase, which is correct behaviour.
    for _ts, delta in sorted(events, key=lambda e: (e[0], e[1])):
        outstanding += delta
        assert outstanding <= _EQUITY, (
            f"the book held {outstanding} of stock against a {_EQUITY} account"
        )


# --------------------------------------------------------------------------------------
# How this guard sits beside the concentration cap (finding F34)
# --------------------------------------------------------------------------------------


def test_at_the_shipped_settings_the_concentration_cap_reaches_the_cash_gate_first(
    goal: GoalConfig,
) -> None:
    """Both guards are live, and it is worth being explicit about which one bites.

    ``max_position_pct_of_equity`` is 0.25 and ``max_open_positions`` is 4, so a full book is at
    most 100% of the account and a *single* position can never exhaust it. The cash gate therefore
    stops being the thing that catches an oversized position — the concentration cap resizes it
    long before. That is not the cash gate becoming redundant: it is the outer of two nested
    limits, and it still binds once charges are counted on a full book.

    Asserted rather than assumed, because "the guard that used to fire never fires now" is exactly
    the change that goes unnoticed until someone loosens the other one.
    """
    shipped = _run(goal, stop_distance=0.01, position_pct=goal.risk.max_position_pct_of_equity)
    assert Skipped.INSUFFICIENT_CASH not in shipped.skipped, "the cap should catch it first"
    assert shipped.concentration_capped == 1
    assert len(shipped.trades) == 1
    held = shipped.trades[0].entry_price * shipped.trades[0].quantity
    assert held <= _EQUITY * Decimal(str(goal.risk.max_position_pct_of_equity))


def test_the_cash_gate_still_binds_when_a_full_book_cannot_be_paid_for(goal: GoalConfig) -> None:
    """The concentration cap does not make the cash gate unreachable, only rarer.

    Five slots at a quarter of the book each is 125% of the account, so the cap alone permits a
    book the money cannot buy. Something still has to say no, and that is this guard.
    """
    symbols = ("AAA", "BBB", "CCC", "DDD", "EEE")
    result = _run(
        goal,
        stop_distance=0.01,
        symbols=symbols,
        slots=5,
        position_pct=goal.risk.max_position_pct_of_equity,
    )
    assert result.skipped.get(Skipped.INSUFFICIENT_CASH) == 1
    assert len(result.trades) == 4
    assert _committed(result) <= _EQUITY
