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
from decimal import ROUND_DOWN, Decimal
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np

from icarus.common.types import OrderSide
from icarus.engine.costmodel import Segment
from icarus.engine.fills import FillModel, Intent, OrderKind
from icarus.engine.simcore import (
    ExitPlan as ExitPlan,
)
from icarus.engine.simcore import (
    ExitReason as ExitReason,
)
from icarus.engine.simcore import SignalId
from icarus.engine.simcore import (
    _dec as _dec,
)
from icarus.engine.simcore import (
    _exit_intent as _exit_intent,
)
from icarus.engine.simcore import (
    _last_traded_close as _last_traded_close,
)
from icarus.engine.simcore import (
    _sim_bar as _sim_bar,
)
from icarus.engine.simcore import (
    _trail_stop as _trail_stop,
)
from icarus.engine.simcore import (
    _ts_at as _ts_at,
)
from icarus.engine.simcore import (
    stop_distance_from_exits as stop_distance_from_exits,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime

    import numpy.typing as npt

    from icarus.common.config import Risk
    from icarus.engine.costmodel import Charges, CostModel
    from icarus.strategy.dsl import Panel, StrategyCandidate

    Column = npt.NDArray[np.float64]


class Skipped(enum.StrEnum):
    """Why a signal did not become a position. Every one of these is a trade a naive simulator
    would have taken, so the counts belong in the metric sheet, not in a debug log."""

    NO_SLOT = "no_slot"
    HEAT_CAP = "heat_cap"
    INSUFFICIENT_CASH = "insufficient_cash"
    """The account could not pay for the shares (finding F6).

    Counted rather than shrunk to fit. Buying what you can afford is what a real account does, but
    it would silently change the position size the strategy specified, and it would erase the one
    signal that decision D9 exists to read: a strategy that works and is simply too big for the
    money is ``NEEDS_MORE_CAPITAL``, not a worse strategy. A skip counter says that out loud."""

    CONCENTRATION_CAP = "concentration_cap"
    """One share already costs more than ``max_position_pct_of_equity`` of the book (F34, D11).

    Distinct from ``rounds_to_zero``, which is risk sizing asking for less than a whole share, and
    from ``insufficient_cash``, which is the account being unable to pay at all. This one says the
    name is too *expensive relative to the book* to hold within the concentration limit — a
    ₹30,000 share against a ₹1,00,000 account cannot be a quarter of it. More capital fixes it;
    a bigger appetite does not."""

    ROUNDS_TO_ZERO = "rounds_to_zero"
    NO_STOP_DISTANCE = "no_stop_distance"
    ENTRY_NOT_FILLED = "entry_not_filled"
    ALREADY_HELD = "already_held"


class PortfolioOmission(enum.StrEnum):
    """Observed entry signals that never reached the historical refusal counters."""

    NO_NEXT_BAR = "no_next_bar"
    NOT_TRADABLE = "not_tradable"
    NO_EXECUTION_BAR = "no_execution_bar"


@dataclass(frozen=True, slots=True)
class PortfolioDiscard:
    """One emitted entry signal that did not become a portfolio position."""

    signal_id: SignalId
    reason: Skipped | PortfolioOmission

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId):
            raise TypeError("PortfolioDiscard.signal_id must be a SignalId")
        if not isinstance(self.reason, (Skipped, PortfolioOmission)):
            raise TypeError("PortfolioDiscard.reason must be a Skipped or PortfolioOmission")


def _legacy_skip_reason(reason: Skipped | PortfolioOmission) -> Skipped | None:
    """Project new observations back onto the unchanged historical counters."""
    if reason is PortfolioOmission.NO_EXECUTION_BAR:
        return Skipped.NO_STOP_DISTANCE
    return reason if isinstance(reason, Skipped) else None


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
    entry_quantity: int
    """What was bought. ``quantity`` shrinks as partial fills drain the position; this does not.

    Needed because ``entry_charges`` is the cost of the whole entry, and each chunk closed must
    carry only its share of it."""

    stop_price: Decimal
    risk_per_share: Decimal
    take_profit: Decimal | None
    time_stop_bars: int | None = None
    trailing: bool = False
    bars_held: int = 0
    peak_close: Decimal = Decimal(0)
    dark_sessions: int = 0
    """Consecutive sessions the symbol has printed no bar. Reset by any bar that arrives.

    Counted rather than inferred from the panel because "how long has *this holding* been unable to
    trade" is a property of the position, not of the symbol: a name can go dark, come back, and go
    dark again while we hold it, and only the current run matters."""

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
    emitted_signals: int = 0
    accepted_signal_ids: list[SignalId] = field(default_factory=list)
    portfolio_discards: list[PortfolioDiscard] = field(default_factory=list)
    unfilled_exits: int = 0
    ambiguous_selection_days: int = 0
    """Days where more candidates fired than there were slots and nothing ordered them.

    Two causes, counted together because they have the same consequence — the book was filled in
    alphabetical order by the sort's tiebreak. Either the strategy declared no ``rank_by`` at all,
    or it declared one that **tied across the cut**, which is the same thing wearing a ranker's
    name (finding F25). A run with a high count here has not tested the strategy the file
    describes; it has tested that strategy plus an alphabetical selection rule.
    """
    stale_marks: int = 0
    """Positions closed at a price nobody quoted, because the symbol had stopped printing bars."""
    stale_mark_value: Decimal = Decimal(0)
    """Gross rupees exited at those prices — the exposure the operator has to take on trust.

    Reported beside the count because the count alone cannot say whether this mattered: two stale
    exits out of four hundred trades is noise, and two that between them carried a fifth of the
    book is the result."""

    concentration_capped: int = 0
    """Entries taken **smaller** than risk sizing asked for, because of the position cap (F34).

    A count rather than a skip, because these trades happened. It is reported for the same reason
    the skip counters are: the cap silently changes what the strategy did, and a strategy whose
    every entry is resized is not the strategy that was written — it is a concentrated one wearing
    a limit. If this number approaches the trade count, the honest reading is that the edge lives
    in position sizes the book will not allow."""

    def record_skip(self, reason: Skipped) -> None:
        self.skipped[reason] = self.skipped.get(reason, 0) + 1

    def record_discard(self, discard: PortfolioDiscard) -> None:
        """Record one refusal and maintain the historical skip-counter projection."""
        self.portfolio_discards.append(discard)
        if (legacy_reason := _legacy_skip_reason(discard.reason)) is not None:
            self.record_skip(legacy_reason)

    def reconcile_signals(self, expected: set[SignalId]) -> None:
        """Fail closed unless every emitted ID has exactly one accepted/discarded outcome."""
        accepted = self.accepted_signal_ids
        discarded = [discard.signal_id for discard in self.portfolio_discards]
        accepted_set = set(accepted)
        discarded_set = set(discarded)
        projection: dict[Skipped, int] = {}
        for discard in self.portfolio_discards:
            if not isinstance(discard.reason, (Skipped, PortfolioOmission)):
                raise ValueError("portfolio signal accounting contains an unknown discard reason")
            if (legacy_reason := _legacy_skip_reason(discard.reason)) is not None:
                projection[legacy_reason] = projection.get(legacy_reason, 0) + 1

        valid = (
            len(accepted_set) == len(accepted)
            and len(discarded_set) == len(discarded)
            and accepted_set.isdisjoint(discarded_set)
            and accepted_set | discarded_set == expected
            and projection == self.skipped
        )
        if not valid:
            raise ValueError("portfolio signal accounting is not an exact one-outcome partition")
        self.emitted_signals = len(expected)

    @property
    def final_equity(self) -> Decimal:
        return self.equity[-1][1] if self.equity else Decimal(0)


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
        stale_after_sessions: int,
    ) -> None:
        self._risk = risk
        self._costs = costs
        self._fills = fills
        self._segment = segment
        self._stale_after = stale_after_sessions

    def run(
        self,
        strategy: StrategyCandidate,
        panel: Panel,
        signals: Mapping[str, Column],
        stops: Mapping[str, Column],
        *,
        starting_equity: Decimal,
        ranks: Mapping[str, Column] | None = None,
        source_indices: Sequence[int] | None = None,
    ) -> RunResult:
        """Walk the panel.

        ``signals`` is the entry condition per symbol, ``stops`` the per-share stop distance in
        rupees (from the strategy's own protective exit), and ``ranks`` the optional ``rank_by``
        column. All three are computed by the caller so this class stays free of DSL evaluation and
        can be tested against hand-built arrays.
        """
        source = tuple(range(len(panel))) if source_indices is None else tuple(source_indices)
        if len(source) != len(panel) or any(
            type(index) is not int or index < 0 for index in source
        ):
            raise ValueError("source_indices must match the panel with nonnegative whole indices")
        if any(current != previous + 1 for previous, current in pairwise(source)):
            raise ValueError("source_indices must be contiguous full-source indices")

        result = RunResult()
        plan = ExitPlan.of(strategy.exits)
        book: dict[str, OpenPosition] = {}
        equity = starting_equity
        last = len(panel) - 1
        expected_signals = {
            SignalId(strategy.name, strategy.version, symbol, _ts_at(panel, t), source[t])
            for t in range(last + 1)
            for symbol in panel.symbols
            if signals[symbol][t] == 1.0
        }

        for t in range(last + 1):
            ts = _ts_at(panel, t)
            # Exits first: a slot freed this morning is available to this morning's signal.
            equity += self._process_exits(book, panel, t, ts, stops, result, final=t == last)
            if t == last:
                for symbol in panel.symbols:
                    if signals[symbol][t] == 1.0:
                        result.record_discard(
                            PortfolioDiscard(
                                SignalId(strategy.name, strategy.version, symbol, ts, source[t]),
                                PortfolioOmission.NO_NEXT_BAR,
                            )
                        )
            else:
                for symbol in panel.symbols:
                    if signals[symbol][t] == 1.0 and not panel.tradable[panel.index_of(symbol), t]:
                        result.record_discard(
                            PortfolioDiscard(
                                SignalId(strategy.name, strategy.version, symbol, ts, source[t]),
                                PortfolioOmission.NOT_TRADABLE,
                            )
                        )
                self._process_entries(
                    strategy,
                    plan,
                    book,
                    panel,
                    t,
                    ts,
                    signals,
                    stops,
                    ranks,
                    equity,
                    result,
                    source[t],
                )
            result.equity.append((ts, equity + self._unrealised(book, panel, t, ts)))
        result.reconcile_signals(expected_signals)
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
                # No bar means the symbol did not trade, so no exit can *execute* — carrying the
                # position is right, and for an ordinary halt it is what would really have
                # happened. What was wrong was carrying it forever: this branch used to `continue`
                # even on the last bar of the span, so a holding in a delisted name was never
                # closed, never counted as a trade, contributed to neither realised nor unrealised
                # equity, and kept one of the four slots for good. The capital simply left the
                # accounts (finding F4).
                position.dark_sessions += 1
                if position.dark_sessions >= self._stale_after:
                    realised += self._write_off(book, panel, index, symbol, t, result)
                continue
            position.dark_sessions = 0
            position.bars_held += 1
            position.peak_close = max(position.peak_close, bar.close)
            _trail_stop(position, float(stops[symbol][t]))

            intent, reason = _exit_intent(position, bar, ts, final=final)
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
                entry_charges=_scaled(
                    position.entry_charges,
                    Decimal(fill.filled_quantity) / Decimal(position.entry_quantity),
                ),
                exit_charges=charges,
                risk_per_share=position.risk_per_share,
            )
            result.trades.append(trade)
            realised += trade.net_pnl
            if fill.filled_quantity >= position.quantity:
                del book[symbol]
            else:
                position.quantity -= fill.filled_quantity

        # Nothing may survive the last bar of the span. Writing off only the *no-bar* case left the
        # same hole open through a different door: an end-of-data exit that the fill model caps by
        # participation, or refuses outright, leaves a residual in the book and the span then ends
        # around it — 700 of 2,500 shares never becoming a trade, invisible to the log, the win
        # rate and the tax ledger, and never charged an exit cost. Mid-run an unfilled exit
        # correctly leaves the position open and exposed; on the final bar there is no "later" for
        # it to be exposed into, and the only honest treatment is a mark (finding F4, second half).
        if final:
            for symbol in list(book):
                realised += self._write_off(book, panel, panel.index_of(symbol), symbol, t, result)
        return realised

    def _write_off(
        self,
        book: dict[str, OpenPosition],
        panel: Panel,
        index: int,
        symbol: str,
        t: int,
        result: RunResult,
    ) -> Decimal:
        """Close a position at a price we **marked** rather than one we transacted at.

        Two ways to arrive here, sharing one epistemic status — no trade happened at this price:

        * the symbol stopped printing bars, so there was no bar and no counterparty at all;
        * the span ended with the position still open, because the closing order could not be
          filled in full against the last bar.

        **Deliberately not routed through the FillModel.** Everywhere else, an exit is an order
        meeting a bar, and the fill model's job is to be pessimistic about whether it met it at all
        (invariant #12 — touch is not fill). Here there is no bar and no counterparty: nobody was
        offering that price, or any price. Fabricating a bar so the fill model had something to
        chew on would dress an assumption up as a measurement. The trade is booked directly and
        tagged ``STALE_MARK`` so the metric sheet can separate it out.

        The exit charges *are* applied, because the pessimistic reading is that closing this costs
        what closing anything costs. It is the one part of the write-off that is not a guess.

        Marking at the last traded close is the **optimistic** choice, and knowingly so (operator,
        2026-08-14): a stock usually stops printing because something went wrong, so the last print
        flatters the outcome. The alternative — writing it to zero — overstates the loss wherever
        the name later resumed. Rather than invent a haircut nobody derived, the count and the
        rupee value are reported so the assumption is visible and can be stress-tested.
        """
        position = book.pop(symbol)
        price, at = _last_traded_close(panel, index, t)
        charges = self._costs.charges(
            self._segment, OrderSide.SELL, price, Decimal(position.quantity)
        )
        trade = ClosedTrade(
            symbol=symbol,
            quantity=position.quantity,
            entry_ts=position.entry_ts,
            entry_price=position.entry_price,
            exit_ts=_ts_at(panel, at),
            exit_price=price,
            reason=ExitReason.STALE_MARK,
            entry_charges=_scaled(
                position.entry_charges,
                Decimal(position.quantity) / Decimal(position.entry_quantity),
            ),
            exit_charges=charges,
            risk_per_share=position.risk_per_share,
        )
        result.trades.append(trade)
        result.stale_marks += 1
        result.stale_mark_value += price * position.quantity
        return trade.net_pnl

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
        decision_index: int | None = None,
    ) -> None:
        source_index = t if decision_index is None else decision_index
        signal_ids = {
            symbol: SignalId(strategy.name, strategy.version, symbol, ts, source_index)
            for symbol in panel.symbols
            if signals[symbol][t] == 1.0
        }
        candidates = [
            symbol
            for symbol in panel.symbols
            if signals[symbol][t] == 1.0 and panel.tradable[panel.index_of(symbol), t]
        ]
        if not candidates:
            return
        for symbol in list(candidates):
            if symbol in book:
                result.record_discard(PortfolioDiscard(signal_ids[symbol], Skipped.ALREADY_HELD))
                candidates.remove(symbol)

        free_slots = self._risk.max_open_positions - len(book)
        if free_slots > 0 and len(candidates) > free_slots:
            # Only a day that actually *chose* can have chosen ambiguously. When the book is full
            # there is no selection to be arbitrary about — every candidate is refused for the same
            # reason — so counting it would mix two different meanings into the one number and make
            # it non-comparable between a ranked strategy and an unranked one, which is its only
            # use (2g-3 code review).
            if ranks is None:
                result.ambiguous_selection_days += 1
            else:
                candidates.sort(key=lambda s: (-_rank_of(ranks[s], t), s))
        if free_slots <= 0:
            # Counted, not dropped: "the strategy fired 900 times and we could take 300 of them" is
            # a fact about the strategy, and a simulator that silently discards the other 600
            # reports a hit rate measured on a sample it chose.
            for symbol in candidates:
                result.record_discard(PortfolioDiscard(signal_ids[symbol], Skipped.NO_SLOT))
            return

        heat_used = sum((p.open_risk for p in book.values()), Decimal(0))
        heat_cap = _dec(self._risk.max_portfolio_heat) * equity
        risk_budget = _dec(strategy.sizing.risk_r) * equity
        position_cap = _dec(self._risk.max_position_pct_of_equity) * equity
        committed = _committed_cash(book)
        if committed > equity:
            # Cannot happen by construction — cash falls only by an outlay this method has already
            # checked, and rises on every close — which is exactly why it is cheap to assert. A
            # future refactor that broke the identity would otherwise show up as a slightly
            # optimistic equity curve and nothing else (invariant #10: fail safe, not silent).
            raise ValueError(
                f"the book holds {committed} of stock against a {equity} account — cash is "
                f"negative, which the entry path is supposed to make unreachable"
            )

        # Slots are filled by what can actually be taken, in rank order — not by position in the
        # list. Recording the overflow up front (the old shape) meant a top-ranked candidate
        # refused for cash left its slot **empty** while a cheaper one behind it had already been
        # written off as having no room. Latent while the only refusals were rare; routine once
        # the cash gate exists, because at the tight-stop end the most expensive candidate is
        # systematically the one that blocks the slot.
        taken = 0
        last_taken_rank: float | None = None
        tie_decided_the_cut = False
        for symbol in candidates:
            if taken >= free_slots:
                # **Where the ranking actually ran out.** The first candidate refused purely for
                # want of a slot is the best-ranked loser; `last_taken_rank` is the worst-ranked
                # winner. Equal, and the symbol name in the sort key chose between them — a
                # declared `rank_by` that resolved nothing here (finding F25).
                #
                # Measured at this point rather than at index `free_slots` because the loop below
                # skips candidates for stop distance, whole shares, concentration, heat, cash and
                # unfilled entries, and keeps filling from further down the list. The cut is
                # wherever `taken` ran out, which is not a fixed position (2g-3 code review).
                #
                # A loser that would have been refused anyway is still counted, because whether it
                # would have been is unknowable from here — it never got the chance. For a counter
                # whose job is to say "do not trust this selection", over-reporting is the safe
                # direction and silent under-reporting is the failure being fixed.
                if (
                    ranks is not None
                    and not tie_decided_the_cut
                    and last_taken_rank == _rank_of(ranks[symbol], t)
                ):
                    result.ambiguous_selection_days += 1
                    tie_decided_the_cut = True
                result.record_discard(PortfolioDiscard(signal_ids[symbol], Skipped.NO_SLOT))
                continue
            index = panel.index_of(symbol)
            bar = _sim_bar(panel, index, t + 1, _ts_at(panel, t + 1))
            stop_distance = _dec(float(stops[symbol][t]))
            if bar is None:
                result.record_discard(
                    PortfolioDiscard(signal_ids[symbol], PortfolioOmission.NO_EXECUTION_BAR)
                )
                continue
            if not np.isfinite(stops[symbol][t]) or stop_distance <= 0:
                result.record_discard(
                    PortfolioDiscard(signal_ids[symbol], Skipped.NO_STOP_DISTANCE)
                )
                continue
            quantity = int((risk_budget / stop_distance).to_integral_value(rounding=ROUND_DOWN))
            if quantity <= 0:
                # Whole shares only. At seed capital this is common, and it is a trade that did
                # not happen rather than a fractional one that did (task 2.1b).
                result.record_discard(PortfolioDiscard(signal_ids[symbol], Skipped.ROUNDS_TO_ZERO))
                continue

            # **The concentration cap (finding F34, decision D11).** The fourth term in the
            # `min(...)` CLAUDE.md §4 defines sizing to be, so it *reduces* the position rather
            # than refusing it — unlike the cash gate below, which skips. The two differ because
            # cash is scale-dependent (more money fixes it, which is the signal D9 reads) and
            # concentration is not: a strategy wanting 40% of the book wants 40% at any account
            # size, so shrinking is the answer and a skip counter would say nothing.
            #
            # Priced with `marketable_price`, not `bar.open`, so the cap holds on what is actually
            # paid. Sizing off the open leaves the filled value a few basis points over — a limit
            # that nearly holds, which is the whole family of bug this file keeps finding.
            price = self._fills.marketable_price(bar.open, side=OrderSide.BUY)
            affordable = int((position_cap / price).to_integral_value(rounding=ROUND_DOWN))
            if affordable <= 0:
                result.record_discard(
                    PortfolioDiscard(signal_ids[symbol], Skipped.CONCENTRATION_CAP)
                )
                continue
            # Noted here, counted only if this candidate becomes a position. Incrementing on the
            # spot counted resized *candidates*, and the heat check, the fill and the cash gate
            # below can each still refuse one — so a single candidate could be reported as both a
            # resized entry and an `insufficient_cash` skip, and the counter could exceed the trade
            # count. That defeats the reading its own docstring prescribes.
            was_capped = affordable < quantity
            quantity = min(quantity, affordable)
            if heat_used + stop_distance * quantity > heat_cap:
                # Four trades each inside the per-trade cap can still breach the book-level one,
                # which is why this is re-checked here and not only at parse time (invariant #4).
                result.record_discard(PortfolioDiscard(signal_ids[symbol], Skipped.HEAT_CAP))
                continue

            fill = self._fills.execute(
                Intent(OrderSide.BUY, OrderKind.MARKETABLE_LIMIT, quantity, ts), bar
            )
            if not fill.filled or fill.price is None or fill.ts is None:
                result.record_discard(
                    PortfolioDiscard(signal_ids[symbol], Skipped.ENTRY_NOT_FILLED)
                )
                continue
            filled = fill.filled_quantity
            if fill.price * filled > position_cap:
                # Cannot happen: `affordable` was derived from this exact price and a partial fill
                # only reduces the count. Asserted anyway, because the alternative to an assert
                # here is a concentration limit that is breached silently and shows up only as a
                # drawdown nobody can explain (invariant #4, invariant #10).
                raise ValueError(
                    f"{symbol} filled {filled} at {fill.price} = {fill.price * filled}, over the "
                    f"{position_cap} concentration cap — sizing and fill priced differently"
                )
            entry_charges = self._costs.charges(
                self._segment, OrderSide.BUY, fill.price, Decimal(filled)
            )
            outlay = fill.price * filled + entry_charges.total
            if committed + outlay > equity:
                # **The account cannot buy what it cannot pay for.** Nothing checked this before:
                # slots, heat, whole shares and the fill were all tested, and the rupee cost was
                # not. Size is `risk_budget / stop_distance`, which has no upper bound — the
                # narrower the stop the larger the position — and the heat cap cannot catch it
                # because stop distance *cancels* out of heat, leaving every position at exactly
                # `risk_r` however big it is. Measured on this panel, the widest single position a
                # 2x-ATR stop would ask for is 77 times the account, and 0.45% of tradable
                # symbol-days would produce one over 100% of it. This is the delivery segment,
                # where leverage is not merely unwise but unavailable (finding F6).
                result.record_discard(
                    PortfolioDiscard(signal_ids[symbol], Skipped.INSUFFICIENT_CASH)
                )
                continue
            committed += outlay
            taken += 1
            if ranks is not None:
                last_taken_rank = _rank_of(ranks[symbol], t)
            result.concentration_capped += int(was_capped)
            book[symbol] = OpenPosition(
                symbol=symbol,
                quantity=filled,
                entry_price=fill.price,
                entry_ts=fill.ts,
                decided_at=ts,
                entry_charges=entry_charges,
                entry_quantity=filled,
                stop_price=fill.price - stop_distance,
                risk_per_share=stop_distance,
                take_profit=plan.target_for(fill.price, stop_distance),
                time_stop_bars=plan.time_stop_bars,
                trailing=plan.trailing,
                peak_close=fill.price,
            )
            result.accepted_signal_ids.append(signal_ids[symbol])
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
            # A dark session used to drop the position out of the mark entirely, which is not
            # "unknown", it is **zero**: a holding up 20,000 rupees vanished from equity the day
            # its symbol stopped printing and reappeared as realised P&L up to twenty sessions
            # later. Two invented daily returns of about 2%, a genuine peak-to-trough between
            # them, and both feed the volatility, the Sharpe and the max-drawdown the stop gate
            # reads. Carrying the last traded price is what a broker statement does, and it makes
            # the curve flat across the gap instead of a hole with a spike after it.
            price, _at = _last_traded_close(panel, panel.index_of(symbol), t)
            total += (price - position.entry_price) * position.quantity
        return total


def _committed_cash(book: Mapping[str, OpenPosition]) -> Decimal:
    """Rupees spent on what is held and not yet returned — cost basis plus acquisition charges.

    ``equity`` in the simulator is the *realised* book: cash plus the cost of open positions. So
    cash is ``equity - committed``, and the identity is exact only if the entry charge is
    pro-rated the same way :func:`_scaled` pro-rates it on the way out. A position half sold has
    already had half its entry charge deducted from equity through ``net_pnl``; counting the whole
    charge here would deduct that half twice and understate cash — a small, conservative error, and
    still an error, capable of refusing a position at the margin that the account could pay for.
    """
    return sum(
        (
            p.entry_price * p.quantity
            + p.entry_charges.total * Decimal(p.quantity) / Decimal(p.entry_quantity)
            for p in book.values()
        ),
        Decimal(0),
    )


def _scaled(charges: Charges, fraction: Decimal) -> Charges:
    """``charges`` scaled by the fraction of the position this trade actually covers.

    A position drained by partial fills becomes several ``ClosedTrade`` rows, and each was being
    handed the entry charge for the **whole** entry. A 2,500-share position closing in nine chunks
    booked ₹2,673 of entry cost against ₹297 actually paid — straight into net P&L, expectancy and
    the tax ledger, in the direction that understates the strategy.
    """
    return replace(
        charges,
        brokerage=charges.brokerage * fraction,
        stt=charges.stt * fraction,
        exchange_txn=charges.exchange_txn * fraction,
        sebi_fee=charges.sebi_fee * fraction,
        gst=charges.gst * fraction,
        stamp_duty=charges.stamp_duty * fraction,
        dp_charge=charges.dp_charge * fraction,
        turnover=charges.turnover * fraction,
    )


def _rank_of(column: Column, t: int) -> float:
    value = float(column[t])
    return value if np.isfinite(value) else float("-inf")
