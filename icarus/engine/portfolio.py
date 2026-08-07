"""The portfolio simulator — what a strategy would actually have done (task 1.7, PRD §30).

**It simulates a portfolio, not a trade.** The obvious cheaper design walks one symbol from start
to finish and totals the trades, and it produces a number that corresponds to nothing: a
cross-sectional strategy is a *basket* ("buy the strongest ten"), which is unmeasurable one symbol
at a time, and even a single-name strategy has to answer "what if five names fire and I can hold
four?" A per-symbol sum answers that question with "hold all five", which is not the system we
would run. The whole point of the stop gate is believing the number, so the simulator holds a real
book: at most ``max_open_positions``, inside ``max_portfolio_heat``, choosing when it cannot take
everything.

**Nothing here may relax a risk limit.** The caps come from ``goal.yaml`` and this module only
reads them (invariant #4). A strategy asking to risk more gets less, never more; the DSL already
rejects a ``risk_r`` above the cap at parse time, and the heat cap is applied again here because
four trades each individually inside the per-trade cap can still breach the book-level one.

**Three places a backtest quietly invents money, all closed here:**

* *Fractional shares.* Equities trade in whole shares. A position sized at 3.7 shares is not a
  position; it rounds **down**, and if it rounds to zero the trade did not happen and is counted
  as such. At seed capital this bites often, which is why it is recorded rather than smoothed
  (the same problem task 2.1b names for the live Risk agent).
* *Free exits.* Every fill — entry and exit — goes through the same
  :class:`~icarus.engine.fills.FillModel`, so an exit can fail to fill exactly like an entry can.
  An unfilled stop leaves the position open and still exposed, which is the honest outcome and the
  one a "assume the stop worked" simulator never shows.
* *Costs paid at the end.* Charges are computed per fill, from the actual filled quantity and
  price, and subtracted as they occur. Applying a modelled cost to the final P&L instead loses the
  trades that were profitable gross and losing net — which at seed size is most of them.

**Exits are evaluated before entries on each bar.** A slot freed by this morning's stop is
available to this morning's signal; the reverse order would silently cap the book one position
below its limit whenever a position closed.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field, replace
from datetime import UTC
from decimal import ROUND_DOWN, Decimal
from typing import TYPE_CHECKING

import numpy as np

from icarus.common.types import OrderSide
from icarus.engine.costmodel import Segment
from icarus.engine.fills import FillModel, Intent, OrderKind, SimBar

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    import numpy.typing as npt

    from icarus.common.config import Risk
    from icarus.engine.costmodel import Charges, CostModel
    from icarus.strategy.dsl import ExitRule, Panel, StrategyCandidate

    Column = npt.NDArray[np.float64]


class ExitReason(enum.StrEnum):
    """Why a position closed. Kept because "what killed this strategy" is the first question the
    metric sheet has to answer, and a bare P&L cannot say."""

    STOP_LOSS = "stop_loss"
    TRAILING_STOP = "trailing_stop"
    TAKE_PROFIT = "take_profit"
    TIME_STOP = "time_stop"
    END_OF_DATA = "end_of_data"


class Skipped(enum.StrEnum):
    """Why a signal did not become a position. Every one of these is a trade a naive simulator
    would have taken, so the counts belong in the metric sheet, not in a debug log."""

    NO_SLOT = "no_slot"
    HEAT_CAP = "heat_cap"
    ROUNDS_TO_ZERO = "rounds_to_zero"
    NO_STOP_DISTANCE = "no_stop_distance"
    ENTRY_NOT_FILLED = "entry_not_filled"
    ALREADY_HELD = "already_held"


@dataclass(slots=True)
class OpenPosition:
    """A live position. Mutable: the trailing stop and the bar count move with the market."""

    symbol: str
    quantity: int
    entry_price: Decimal
    entry_ts: datetime
    decided_at: datetime
    """The bar whose close produced the entry signal — one session before ``entry_ts``.

    Kept separately because the protective stop was decided *here*, not on the fill bar. Dating
    exits to ``entry_ts`` instead made a stop unable to fill on the session it was placed, which
    is both wrong and optimistic: real stops do get hit the same day you buy. It surfaced on
    2020-03-16, the worst session in the sample, as a same-bar assertion rather than as a quietly
    missing loss — the loud failure was luck, so the field exists to remove the luck.
    """

    entry_charges: Charges
    stop_price: Decimal
    risk_per_share: Decimal
    take_profit: Decimal | None
    time_stop_bars: int | None = None
    trailing: bool = False
    bars_held: int = 0
    peak_close: Decimal = Decimal(0)

    @property
    def open_risk(self) -> Decimal:
        """Rupees still at risk if the stop fills — the quantity that the heat cap governs."""
        return self.risk_per_share * self.quantity


@dataclass(frozen=True, slots=True)
class ClosedTrade:
    """One completed round trip, itemised enough to reconcile and to feed the tax ledger."""

    symbol: str
    quantity: int
    entry_ts: datetime
    entry_price: Decimal
    exit_ts: datetime
    exit_price: Decimal
    reason: ExitReason
    entry_charges: Charges
    exit_charges: Charges
    risk_per_share: Decimal
    """What the position was sized to lose per share — entry minus the protective stop.

    Carried on the closed trade rather than recomputed from the exit, because the exit price is
    not the stop: a trade that closed on a trailing stop or ran to the end of the data has no stop
    distance visible in its own record. Without this, R-multiples — and therefore expectancy, the
    stagnation check's mean-R confidence interval (invariant #23), and the trade-count floor —
    cannot be computed at all.
    """

    @property
    def gross_pnl(self) -> Decimal:
        return (self.exit_price - self.entry_price) * self.quantity

    @property
    def costs(self) -> Decimal:
        return self.entry_charges.total + self.exit_charges.total

    @property
    def net_pnl(self) -> Decimal:
        """After charges, before tax. Tax is annual on the aggregate, so it cannot live here."""
        return self.gross_pnl - self.costs

    @property
    def holding_days(self) -> int:
        return (self.exit_ts.date() - self.entry_ts.date()).days


@dataclass(slots=True)
class RunResult:
    """Everything the metric sheet (1.8) and the tax ledger (1.6) need from one run."""

    trades: list[ClosedTrade] = field(default_factory=list)
    equity: list[tuple[datetime, Decimal]] = field(default_factory=list)
    skipped: dict[Skipped, int] = field(default_factory=dict)
    unfilled_exits: int = 0
    ambiguous_selection_days: int = 0

    def record_skip(self, reason: Skipped) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    @property
    def final_equity(self) -> Decimal:
        return self.equity[-1][1] if self.equity else Decimal(0)


def _dec(value: float) -> Decimal:
    """Bars are float64 because whole-series arithmetic wants that; money is Decimal.

    ``str`` rather than ``Decimal(float)`` on purpose: the latter carries the full binary
    expansion, so a price of 100.1 becomes 100.099999999999994315658…, and that difference
    reappears as a paisa the contract note disagrees about.
    """
    return Decimal(str(value))


class PortfolioSimulator:
    """Replays a strategy over a panel, one date at a time, holding a real book.

    Deliberately date-major: the outer loop is the calendar and the inner loop is symbols, because
    a cross-sectional word needs every symbol's bar *t* before it can score any symbol's bar *t*
    (task 1.4c). A symbol-major loop cannot compute a ranking at all — it has already finished with
    the first symbol before it reaches the second.
    """

    def __init__(
        self,
        *,
        risk: Risk,
        costs: CostModel,
        fills: FillModel,
        segment: Segment = Segment.EQUITY_DELIVERY,
    ) -> None:
        self._risk = risk
        self._costs = costs
        self._fills = fills
        self._segment = segment

    def run(
        self,
        strategy: StrategyCandidate,
        panel: Panel,
        signals: Mapping[str, Column],
        stops: Mapping[str, Column],
        *,
        starting_equity: Decimal,
        ranks: Mapping[str, Column] | None = None,
    ) -> RunResult:
        """Walk the panel.

        ``signals`` is the entry condition per symbol, ``stops`` the per-share stop distance in
        rupees (from the strategy's own protective exit), and ``ranks`` the optional ``rank_by``
        column. All three are computed by the caller so this class stays free of DSL evaluation and
        can be tested against hand-built arrays.
        """
        result = RunResult()
        plan = ExitPlan.of(strategy.exits)
        book: dict[str, OpenPosition] = {}
        equity = starting_equity
        last = len(panel) - 1

        for t in range(last + 1):
            ts = _ts_at(panel, t)
            # Exits first: a slot freed this morning is available to this morning's signal.
            equity += self._process_exits(book, panel, t, ts, stops, result, final=t == last)
            if t < last:
                self._process_entries(
                    strategy, plan, book, panel, t, ts, signals, stops, ranks, equity, result
                )
            result.equity.append((ts, equity + self._unrealised(book, panel, t, ts)))
        return result

    # -- exits -------------------------------------------------------------------------------

    def _process_exits(
        self,
        book: dict[str, OpenPosition],
        panel: Panel,
        t: int,
        ts: datetime,
        stops: Mapping[str, Column],
        result: RunResult,
        *,
        final: bool,
    ) -> Decimal:
        realised = Decimal(0)
        for symbol in list(book):
            position = book[symbol]
            index = panel.index_of(symbol)
            bar = _sim_bar(panel, index, t, ts)
            if bar is None:
                continue
            position.bars_held += 1
            position.peak_close = max(position.peak_close, bar.close)
            self._trail_stop(position, float(stops[symbol][t]))

            intent, reason = self._exit_intent(position, bar, ts, final=final)
            if intent is None or reason is None:
                continue
            fill = self._fills.execute(intent, bar)
            if not fill.filled or fill.price is None or fill.ts is None:
                # An unfilled exit is not a closed trade. The position stays open and stays
                # exposed, which is exactly what would have happened — and is the outcome a
                # simulator that assumes its stops worked can never show.
                result.unfilled_exits += 1
                continue
            charges = self._costs.charges(
                self._segment, OrderSide.SELL, fill.price, Decimal(fill.filled_quantity)
            )
            trade = ClosedTrade(
                symbol=symbol,
                quantity=fill.filled_quantity,
                entry_ts=position.entry_ts,
                entry_price=position.entry_price,
                exit_ts=fill.ts,
                exit_price=fill.price,
                reason=reason,
                entry_charges=position.entry_charges,
                exit_charges=charges,
                risk_per_share=position.risk_per_share,
            )
            result.trades.append(trade)
            realised += trade.net_pnl
            if fill.filled_quantity >= position.quantity:
                del book[symbol]
            else:
                position.quantity -= fill.filled_quantity
        return realised

    def _exit_intent(
        self, position: OpenPosition, bar: SimBar, ts: datetime, *, final: bool
    ) -> tuple[Intent | None, ExitReason | None]:
        """The first exit that applies, checked worst-case first.

        Order matters and is deliberately pessimistic: when a bar's range spans both the stop and
        the target, daily data cannot say which came first, so the **stop** is taken. Choosing the
        target instead would hand the strategy the good half of every ambiguous bar, which is the
        touch-equals-fill bias arriving through the exit door.

        **Every exit is dated to the bar that decided the entry, not to today and not to the fill
        bar**, and the distinction is load-bearing. A protective stop is a *resting order sitting
        at the broker* — invariant #16 requires every open position to carry one — so it was
        decided at the same moment the entry was, one session before the fill. Next-bar execution
        constrains *decisions*, not the intra-bar triggering of an order already resting.

        Dating exits to the current bar would force the engine to wait a day before honouring its
        own stop, inventing a day of unprotected loss. Dating them to ``entry_ts`` — the fill bar —
        was the original mistake: it made a stop unable to execute on the very session the position
        opened, so a trade that gapped through its stop on day one could never be stopped out. That
        is a real outcome, and always a loss, so suppressing it flattered every result. ``ts`` is
        still passed so the caller's bar is available; it is deliberately not the decision time.
        """
        decided = position.decided_at
        if final:
            return (
                Intent(OrderSide.SELL, OrderKind.MARKETABLE_LIMIT, position.quantity, decided),
                ExitReason.END_OF_DATA,
            )
        if bar.low <= position.stop_price:
            reason = (
                ExitReason.TRAILING_STOP
                if position.stop_price > position.entry_price
                else ExitReason.STOP_LOSS
            )
            return (
                Intent(
                    OrderSide.SELL,
                    OrderKind.STOP,
                    position.quantity,
                    decided,
                    limit_price=position.stop_price,
                ),
                reason,
            )
        if position.take_profit is not None and bar.high > position.take_profit:
            return (
                Intent(
                    OrderSide.SELL,
                    OrderKind.RESTING_LIMIT,
                    position.quantity,
                    decided,
                    limit_price=position.take_profit,
                ),
                ExitReason.TAKE_PROFIT,
            )
        if position.time_stop_bars is not None and position.bars_held >= position.time_stop_bars:
            # A time stop is a decision, not a resting order — the strategy chose in advance to be
            # out after N bars, and the exit is a market-hours order at the next opportunity. It is
            # checked last because both price exits would have triggered intra-bar, before the
            # close that makes the bar count tick over.
            return (
                Intent(OrderSide.SELL, OrderKind.MARKETABLE_LIMIT, position.quantity, decided),
                ExitReason.TIME_STOP,
            )
        return None, None

    @staticmethod
    def _trail_stop(position: OpenPosition, distance: float) -> None:
        """Ratchet a trailing stop up behind the peak close. It never moves down.

        ``distance`` is the same per-share stop distance column the position was sized from, so
        the trail and the original stop are one number and cannot drift apart.

        A stop that could loosen is not a stop. Letting it fall back as volatility rose would make
        an already-protected position unprotected again, and the risk the trade was sized on would
        stop describing the loss it can actually take.
        """
        if not position.trailing or not np.isfinite(distance) or distance <= 0:
            return
        candidate = position.peak_close - _dec(distance)
        if candidate > position.stop_price:
            position.stop_price = candidate

    # -- entries -----------------------------------------------------------------------------

    def _process_entries(
        self,
        strategy: StrategyCandidate,
        plan: ExitPlan,
        book: dict[str, OpenPosition],
        panel: Panel,
        t: int,
        ts: datetime,
        signals: Mapping[str, Column],
        stops: Mapping[str, Column],
        ranks: Mapping[str, Column] | None,
        equity: Decimal,
        result: RunResult,
    ) -> None:
        candidates = [
            symbol
            for symbol in panel.symbols
            if signals[symbol][t] == 1.0 and panel.tradable[panel.index_of(symbol), t]
        ]
        if not candidates:
            return
        for symbol in list(candidates):
            if symbol in book:
                result.record_skip(Skipped.ALREADY_HELD)
                candidates.remove(symbol)

        free_slots = self._risk.max_open_positions - len(book)
        if len(candidates) > max(free_slots, 0):
            if ranks is None:
                result.ambiguous_selection_days += 1
            else:
                candidates.sort(key=lambda s: (-_rank_of(ranks[s], t), s))
        # Everything past the last free slot is a trade the book had no room for. Counted, not
        # dropped: "the strategy fired 900 times and we could take 300 of them" is a fact about
        # the strategy, and a simulator that silently discards the other 600 reports a hit rate
        # measured on a sample it chose.
        for _ in candidates[max(free_slots, 0) :]:
            result.record_skip(Skipped.NO_SLOT)
        if free_slots <= 0:
            return

        heat_used = sum((p.open_risk for p in book.values()), Decimal(0))
        heat_cap = _dec(self._risk.max_portfolio_heat) * equity
        risk_budget = _dec(strategy.sizing.risk_r) * equity

        for symbol in candidates[:free_slots]:
            index = panel.index_of(symbol)
            bar = _sim_bar(panel, index, t + 1, _ts_at(panel, t + 1))
            stop_distance = _dec(float(stops[symbol][t]))
            if bar is None or not np.isfinite(stops[symbol][t]) or stop_distance <= 0:
                result.record_skip(Skipped.NO_STOP_DISTANCE)
                continue
            quantity = int((risk_budget / stop_distance).to_integral_value(rounding=ROUND_DOWN))
            if quantity <= 0:
                # Whole shares only. At seed capital this is common, and it is a trade that did
                # not happen rather than a fractional one that did (task 2.1b).
                result.record_skip(Skipped.ROUNDS_TO_ZERO)
                continue
            if heat_used + stop_distance * quantity > heat_cap:
                # Four trades each inside the per-trade cap can still breach the book-level one,
                # which is why this is re-checked here and not only at parse time (invariant #4).
                result.record_skip(Skipped.HEAT_CAP)
                continue

            fill = self._fills.execute(
                Intent(OrderSide.BUY, OrderKind.MARKETABLE_LIMIT, quantity, ts), bar
            )
            if not fill.filled or fill.price is None or fill.ts is None:
                result.record_skip(Skipped.ENTRY_NOT_FILLED)
                continue
            filled = fill.filled_quantity
            book[symbol] = OpenPosition(
                symbol=symbol,
                quantity=filled,
                entry_price=fill.price,
                entry_ts=fill.ts,
                decided_at=ts,
                entry_charges=self._costs.charges(
                    self._segment, OrderSide.BUY, fill.price, Decimal(filled)
                ),
                stop_price=fill.price - stop_distance,
                risk_per_share=stop_distance,
                take_profit=plan.target_for(fill.price, stop_distance),
                time_stop_bars=plan.time_stop_bars,
                trailing=plan.trailing,
                peak_close=fill.price,
            )
            heat_used += stop_distance * filled

    def _unrealised(
        self, book: Mapping[str, OpenPosition], panel: Panel, t: int, ts: datetime
    ) -> Decimal:
        """Open P&L marked at the close, so the equity curve is not a step function of exits.

        **Only positions that already existed on this bar.** Entries are decided on bar `t` and
        fill on bar `t+1`, so a position created during this iteration was not held at `close[t]`.
        Marking it here charged bar `t` with the whole overnight move from `close[t]` to the next
        open — a fabricated return on every entry's decision bar, inflating measured volatility
        and biasing the very Sharpe the stop gate reads.
        """
        total = Decimal(0)
        for symbol, position in book.items():
            if position.entry_ts > ts:
                continue
            close = panel.bars[panel.index_of(symbol)].close[t]
            if np.isfinite(close):
                total += (_dec(float(close)) - position.entry_price) * position.quantity
        return total


def _ts_at(panel: Panel, t: int) -> datetime:
    """Bar ``t``'s timestamp as a **tz-aware UTC** datetime (invariant #22).

    Two traps in one line. ``datetime64[ns].item()`` returns an *integer* of nanoseconds, not a
    datetime — which compares happily against another integer, so the next-bar assertion in the
    fill model would have been comparing two ints and passing for the wrong reason. And ``.item()``
    yields a naive datetime; naive and aware timestamps raise on comparison, which is the good
    outcome, but only if the conversion happens in exactly one place. This is that place.
    """
    naive: datetime = panel.ts[t].astype("datetime64[us]").item()
    return naive.replace(tzinfo=UTC)


def _sim_bar(panel: Panel, index: int, t: int, ts: datetime) -> SimBar | None:
    """One bar in the money type, or ``None`` where the symbol had no session.

    A gap in a symbol's series is real data — it did not trade — and must not become a synthetic
    bar. Returning ``None`` makes the caller decide, which for an open position means "carry it,
    unchanged" and for a candidate means "cannot enter".
    """
    bars = panel.bars[index]
    values = (bars.open[t], bars.high[t], bars.low[t], bars.close[t], bars.volume[t])
    if not all(np.isfinite(v) for v in values):
        return None
    price = [_dec(float(v)) for v in values]
    return SimBar(
        ts=ts, open=price[0], high=price[1], low=price[2], close=price[3], volume=price[4]
    )


def _rank_of(column: Column, t: int) -> float:
    value = float(column[t])
    return value if np.isfinite(value) else float("-inf")


@dataclass(frozen=True, slots=True)
class ExitPlan:
    """Every exit rule a strategy declared, resolved into what the simulator must actually do.

    **This exists because the simulator used to honour one rule out of six and say nothing.**
    ``take_profit_r``, ``take_profit_pct`` and ``time_stop`` parsed, validated, and were then
    dropped on the floor; ``trailing_stop_atr`` was installed as a *fixed* stop that never
    trailed. So a strategy file declaring a 3R target and a 20-bar time stop was simulated as
    buy-and-hold-until-stopped — a materially different strategy from the one pre-registered, and
    invariant #25 is worth nothing if the artefact and the thing measured are not the same.

    :meth:`of` therefore **refuses** any rule it does not implement rather than ignoring it. A new
    exit word added to the DSL now breaks the backtest loudly instead of quietly changing what a
    strategy means.
    """

    take_profit_r: float | None = None
    take_profit_pct: float | None = None
    time_stop_bars: int | None = None
    trailing: bool = False

    @classmethod
    def of(cls, exits: Sequence[ExitRule]) -> ExitPlan:
        known = {"stop_loss_atr", "stop_loss_pct", "trailing_stop_atr"}
        plan = cls()
        for rule in exits:
            if rule.rule in known:
                plan = replace(plan, trailing=plan.trailing or rule.rule == "trailing_stop_atr")
            elif rule.rule == "take_profit_r":
                plan = replace(plan, take_profit_r=float(rule.literals["r_multiple"]))
            elif rule.rule == "take_profit_pct":
                plan = replace(plan, take_profit_pct=float(rule.literals["pct"]))
            elif rule.rule == "time_stop":
                plan = replace(plan, time_stop_bars=int(rule.literals["bars"]))
            else:
                raise ValueError(
                    f"the portfolio simulator cannot honour the exit rule {rule.rule!r}. It parses "
                    f"in the DSL but nothing here implements it, so a strategy declaring it would "
                    f"be simulated as a different strategy than the one written down. Implement it "
                    f"or remove it from EXIT_RULES — never run past it."
                )
        return plan

    def target_for(self, entry_price: Decimal, risk_per_share: Decimal) -> Decimal | None:
        """The take-profit level, or ``None``. The **nearer** target wins if both are declared."""
        levels = [
            entry_price + _dec(self.take_profit_r) * risk_per_share
            if self.take_profit_r is not None
            else None,
            entry_price * (Decimal(1) + _dec(self.take_profit_pct))
            if self.take_profit_pct is not None
            else None,
        ]
        present = [level for level in levels if level is not None]
        return min(present) if present else None


def stop_distance_from_exits(exits: Sequence[ExitRule], *, atr: Column, close: Column) -> Column:
    """Rupees of risk per share, from whichever protective exit the strategy declared.

    Derived from the strategy rather than configured, because the stop *is* the risk unit: position
    size is the risk budget divided by this number, so a simulator using its own stop would size
    every position for a trade the strategy never described.
    """
    for rule in exits:
        if rule.rule == "stop_loss_atr":
            return float(rule.literals["atr_mult"]) * atr
        if rule.rule == "trailing_stop_atr":
            return float(rule.literals["atr_mult"]) * atr
        if rule.rule == "stop_loss_pct":
            return float(rule.literals["pct"]) * close
    raise ValueError(
        "strategy declares no protective exit — the DSL rejects that at parse time, so reaching "
        "here means an unvalidated candidate was handed to the simulator"
    )
