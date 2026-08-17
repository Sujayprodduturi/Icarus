"""No single name may take more than a quarter of the book — finding F34, decision D11.

**What risk sizing does not bound.** Size is ``risk_budget / stop_distance``, so the loss *if the
stop holds* is exactly ``risk_r`` of the account whatever the position's value. The heat cap
measures the same quantity and therefore cannot help: stop distance cancels out of
``stop_distance x quantity``, so four positions always use exactly ``4 x risk_r`` of heat however
large they are. Neither control looks at rupees deployed. The cash gate (task 2d) added a ceiling
of *the whole account*, which is a bound but not a limit.

**Why that is not enough.** A stop is not a guarantee overnight. ``fills.py`` already models this —
a stop fills at the worse of trigger and open — and on NSE cash equity a large share of the move
happens between sessions. So the number that decides what a gap costs is not risk-per-trade, it is
**concentration**:

======================  =====================  ==========================================
position, % of account  10% adverse gap        20% gap (the lower circuit)
======================  =====================  ==========================================
50%                     -5% — past the halt    **-10% — the drawdown kill switch**
25%                     -2.5%                  -5% — painful, survivable
======================  =====================  ==========================================

At 50%, one name gapping to the circuit takes the account to ``max_drawdown_killswitch`` in a
single morning, from a position that was "risking 0.5%". 0.25 is also *derived* rather than picked:
``max_open_positions`` is 4, so it is one name's equal share of a fully deployed book.

**It reduces, it does not refuse** — the fourth term in the ``min(...)`` CLAUDE.md §4 defines
sizing to be. That differs from the cash gate, which skips, and the difference is not arbitrary:
cash is scale-dependent, so a skip is the signal decision D9 reads as ``NEEDS_MORE_CAPITAL``;
concentration is scale-invariant, so a strategy wanting 40% of the book wants 40% at any account
size and there is nothing for more money to fix.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import ExecutionRealism, load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator, RunResult, Skipped
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    from icarus.common.config import GoalConfig

START = np.datetime64("2024-01-01")
_EQUITY = Decimal(100_000)
_PRICE = 100.0


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _sim(goal: GoalConfig, *, position_pct: float, slots: int = 4) -> PortfolioSimulator:
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
name: concentration_test
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


def _panel(symbols: tuple[str, ...] = ("AAA",), size: int = 30, price: float = _PRICE) -> Panel:
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
    position_pct: float,
    symbols: tuple[str, ...] = ("AAA",),
    slots: int = 4,
    price: float = _PRICE,
    equity: Decimal = _EQUITY,
) -> RunResult:
    panel = _panel(symbols, price=price)
    size = len(panel)
    signals, stops = {}, {}
    for symbol in panel.symbols:
        column = np.zeros(size, dtype=np.float64)
        column[0] = 1.0
        signals[symbol] = column
        stops[symbol] = np.full(size, stop_distance)
    return _sim(goal, position_pct=position_pct, slots=slots).run(
        _strategy(),  # type: ignore[arg-type]
        panel,
        signals=signals,
        stops=stops,
        starting_equity=equity,
    )


def _value(result: RunResult) -> Decimal:
    return sum((t.entry_price * t.quantity for t in result.trades), Decimal(0))


# --------------------------------------------------------------------------------------
# The cap binds, and binds on what is actually paid
# --------------------------------------------------------------------------------------


def test_a_position_over_the_cap_is_resized_not_refused() -> None:
    """A one-paisa stop asks for 50,000 shares — ₹5,000,000 against a ₹100,000 book.

    Risk sizing is happy with that: heat is exactly ₹500 either way, because stop distance cancels.
    The cap is the only control that looks at the rupees.
    """
    goal = load_goal()
    result = _run(goal, stop_distance=0.01, position_pct=0.25)
    assert len(result.trades) == 1, "resized, not refused — the signal was still taken"
    assert result.concentration_capped == 1
    assert _value(result) <= _EQUITY / 4


def test_a_position_inside_the_cap_is_left_alone(goal: GoalConfig) -> None:
    """The cap must not become a general brake. A ₹5 stop buys 100 shares — ₹10,000, a tenth of
    the book — and the cap has no business touching it."""
    result = _run(goal, stop_distance=5.0, position_pct=0.25)
    assert result.trades[0].quantity == 100
    assert result.concentration_capped == 0


def test_the_cap_is_measured_on_the_filled_price_not_the_bar_open(goal: GoalConfig) -> None:
    """Sizing off ``bar.open`` would leave the filled value a few basis points over the cap.

    A marketable limit pays ``open x (1 + slippage)`` rounded up to a tick, so at 5bps a position
    sized at exactly the cap fills about ₹12 above it on a ₹25,000 position. Small, and still a
    limit that does not hold — which is the failure this repo keeps finding. The engine asks the
    fill model for the price it will actually pay before it sizes.
    """
    result = _run(goal, stop_distance=0.01, position_pct=0.25)
    cap = _EQUITY / 4
    assert _value(result) <= cap
    # ...and it is genuinely up against the cap, not comfortably inside it by accident: one more
    # share at the filled price would breach it.
    trade = result.trades[0]
    assert trade.entry_price * (trade.quantity + 1) > cap


@pytest.mark.parametrize("pct", [0.05, 0.10, 0.25, 0.50])
def test_no_position_ever_exceeds_the_configured_cap(goal: GoalConfig, pct: float) -> None:
    """Swept, because a cap that holds at one setting and not another is not a cap."""
    for stop in (0.01, 0.05, 0.2, 1.0, 5.0):
        result = _run(goal, stop_distance=stop, position_pct=pct)
        for trade in result.trades:
            assert trade.entry_price * trade.quantity <= _EQUITY * Decimal(str(pct)), (
                f"stop={stop} pct={pct} produced a position over the cap"
            )


def test_a_share_costing_more_than_the_cap_is_refused_and_named() -> None:
    """₹30,000 a share against a ₹100,000 book: no whole number of shares is a quarter of it.

    Its own reason rather than ``rounds_to_zero``, which is risk sizing asking for less than a
    share, or ``insufficient_cash``, which is the account unable to pay at all. This one says the
    name is too expensive *relative to the book* — a fact more capital would fix and a bigger
    appetite would not.
    """
    goal = load_goal()
    result = _run(goal, stop_distance=0.01, position_pct=0.25, price=30_000.0)
    assert result.trades == []
    assert result.skipped.get(Skipped.CONCENTRATION_CAP) == 1


# --------------------------------------------------------------------------------------
# It cannot be edited into not being a limit (invariant #4)
# --------------------------------------------------------------------------------------


def test_the_shipped_value_is_a_quarter_and_a_full_book_is_the_whole_account() -> None:
    """0.25 is derived, not chosen: one name's equal share of ``max_open_positions`` slots.

    Pinned because the derivation is the justification. If ``max_open_positions`` ever moves, this
    fails and somebody has to decide again rather than leaving two numbers quietly disagreeing —
    the same trap ``max_open_positions`` and ``max_portfolio_heat`` are already checked against.
    """
    risk = load_goal().risk
    assert risk.max_position_pct_of_equity == 0.25
    assert risk.max_open_positions * risk.max_position_pct_of_equity == pytest.approx(1.0)


def test_a_cap_looser_than_half_the_account_is_refused(goal: GoalConfig) -> None:
    """The code's ceiling, not the config's value (invariant #4).

    At 50% a single 20% circuit-down gap is a 10% account loss, which is exactly
    ``max_drawdown_killswitch`` — one name, one morning, operator-only restart. Anything looser is
    a limit edited into not being one, so the loader refuses it however it is signed.
    """
    with pytest.raises(ValueError, match="max_position_pct_of_equity"):
        goal.risk.__class__.model_validate(
            {**goal.risk.model_dump(), "max_position_pct_of_equity": 0.75}
        )


def test_zero_is_refused_too(goal: GoalConfig) -> None:
    """A cap of nothing would refuse every trade, which is a halt wearing a limit's clothes."""
    with pytest.raises(ValueError):
        goal.risk.__class__.model_validate(
            {**goal.risk.model_dump(), "max_position_pct_of_equity": 0.0}
        )
