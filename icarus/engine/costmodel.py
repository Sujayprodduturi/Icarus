"""Statutory + broker cost model (task 1.5, PRD §7, CLAUDE.md §5).

Every backtest and every live decision runs through this. Gross-only numbers are a bug: at seed
capital the charges below are routinely **larger than the edge**, so a strategy that looks
profitable on price alone is usually a losing strategy in fact.

**Charges only — deliberately not slippage.** Whether an order would have filled at all, and at
what price, is the fill model's job (§30.1, task 1.7b: touch != fill, queue position, no-fill as a
real outcome). Keeping the two apart is what stops the same friction being counted twice, in
either direction.

**The fixed-rupee problem.** Most charges are proportional, so they scale with position size and
their *percentage* bite is constant. One is not: the **DP charge of ₹15.34 per scrip on every
delivery sell**. It does not shrink with position size, so it lands hardest on the smallest
accounts — 0.77% one-way on a ₹2,000 position, 0.06% on ₹25,000. Most of the seed-capital
cold-start risk (BUILD_MAP C1) is this one line, and :meth:`CostModel.breakeven_move` is what puts
a number on it.

**Rates live in ``goal.yaml``, not here** (CLAUDE.md §2, PRD Appendix B: re-pull the circulars,
never hard-code). That file carries the full source list and as-of dates, including the resolution
of the NSE cash transaction-charge / IPFT convention.

**Precision.** Exact :class:`~decimal.Decimal` arithmetic throughout, with no rounding. Real
contract notes round STT and stamp duty to the nearest rupee, so a live note will differ from this
by under ₹1 per side, in either direction. That is deliberately *not* modelled: conservatism
belongs in ``stress_multiplier`` (§13 re-runs the gate at 1.5x modelled cost), where it is visible,
rather than hidden in a rounding rule that quietly biases every number.

**The Kite subscription is not here.** PRD §7.1 suggests amortizing the ₹500/month API fee into
the per-strategy hurdle. The operator decided (2026-07-30) to treat it as a capital investment in
the business — the same bucket as the PC — because it is fixed whether or not Icarus ever trades,
and charging it against a strategy's edge makes every per-trade figure depend on an assumed
monthly trade count. So the numbers here are **before infrastructure cost**; the ₹500 is tracked
in BUILD_MAP §5 and reported as its own line, never netted into strategy P&L.

**Crypto is not here.** Delta's fee schedule needs live verification and crypto is deferred
(BUILD_MAP D1); funding accrual and futures roll are task 1.5b (§33). Asking this model for a
crypto cost raises rather than returning a plausible-looking guess.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from icarus.common.types import AssetClass, OrderSide

if TYPE_CHECKING:
    from icarus.common.config import Costs, SegmentSchedule

# Fixed-point passes for breakeven. Sell-side charges depend on the exit price, which depends on
# the breakeven move, which depends on the charges. The recursion contracts by roughly the
# sell-side rate (~0.1%), so a handful of passes lands well inside a paisa.
_BREAKEVEN_PASSES = 4


class Segment(enum.StrEnum):
    """A tradable segment. Each has its own charge schedule in ``goal.yaml``.

    Equity delivery is the seed-tier live surface (zero brokerage). Futures and options are
    simulation-only at seed — margin-impossible on this capital — but are modelled so the sim
    does not flatter them.
    """

    EQUITY_DELIVERY = "equity_delivery"
    EQUITY_INTRADAY = "equity_intraday"
    EQUITY_FUTURES = "equity_futures"
    EQUITY_OPTIONS = "equity_options"


@dataclass(frozen=True)
class Charges:
    """The itemised cost of **one side** of a trade, in rupees.

    Itemised rather than a single number so a contract note can be reconciled against it line by
    line, and so the audit log records *why* a trade cost what it did (PRD §19).
    """

    brokerage: Decimal
    stt: Decimal
    exchange_txn: Decimal
    sebi_fee: Decimal
    gst: Decimal
    stamp_duty: Decimal
    dp_charge: Decimal
    turnover: Decimal

    @property
    def total(self) -> Decimal:
        return (
            self.brokerage
            + self.stt
            + self.exchange_txn
            + self.sebi_fee
            + self.gst
            + self.stamp_duty
            + self.dp_charge
        )


@dataclass(frozen=True)
class RoundTripCost:
    """Both sides of a complete trade — the number the cost-hurdle rule (§7.3) is tested against."""

    buy: Charges
    sell: Charges

    @property
    def total(self) -> Decimal:
        return self.buy.total + self.sell.total

    @property
    def as_fraction_of_entry(self) -> Decimal:
        """Round-trip cost as a fraction of the money put at work — the honest 'cost %' figure."""
        return self.total / self.buy.turnover if self.buy.turnover else Decimal(0)


class CostModel:
    """Computes statutory + broker charges from the ``goal.yaml`` schedule.

    Stateless and pure: same inputs, same outputs, no I/O. Safe to call inside a backtest inner
    loop and inside the live decision path.

    ``stress_multiplier`` scales every charge, implementing the §13 gate stage that re-runs a
    backtest at 1.5x modelled cost. A strategy whose edge evaporates under it was never really
    profitable — it was living inside the error bars of the cost estimate.
    """

    def __init__(self, config: Costs, *, stress_multiplier: Decimal | float | int = 1) -> None:
        self._cfg = config
        self._stress = _dec(stress_multiplier)
        if self._stress <= 0:
            raise ValueError(f"stress_multiplier must be positive, got {stress_multiplier}")

    def charges(
        self, segment: Segment, side: OrderSide, price: Decimal, quantity: Decimal
    ) -> Charges:
        """Charges for one side of one order.

        For options, pass the **premium** as ``price`` and total contracts as ``quantity`` — STT
        and the exchange transaction charge are both levied on premium turnover, not on notional.
        """
        if price <= 0 or quantity <= 0:
            raise ValueError(f"price and quantity must be positive, got {price} x {quantity}")
        schedule = self._schedule(segment)
        turnover = price * quantity
        buying = side is OrderSide.BUY

        brokerage = _dec(schedule.brokerage_flat_inr) + min(
            _dec(schedule.brokerage_pct) * turnover, _dec(schedule.brokerage_cap_inr)
        )
        stt_pct = schedule.stt_buy_pct if buying else schedule.stt_sell_pct
        stt = _dec(stt_pct) * turnover
        exchange_txn = _dec(schedule.exchange_txn_pct) * turnover
        sebi_fee = _dec(self._cfg.sebi_turnover_pct) * turnover
        # GST applies to the *service* charges only — never to STT or stamp duty (they are taxes,
        # not services), and never to the DP charge, whose ₹15.34 is already GST-inclusive.
        gst = _dec(self._cfg.gst_rate) * (brokerage + exchange_txn + sebi_fee)
        stamp_duty = _dec(schedule.stamp_buy_pct) * turnover if buying else Decimal(0)
        dp_charge = (
            _dec(self._cfg.dp_charge_inr)
            if (not buying and schedule.dp_charge_on_sell)
            else Decimal(0)
        )

        return Charges(
            brokerage=brokerage * self._stress,
            stt=stt * self._stress,
            exchange_txn=exchange_txn * self._stress,
            sebi_fee=sebi_fee * self._stress,
            gst=gst * self._stress,
            stamp_duty=stamp_duty * self._stress,
            dp_charge=dp_charge * self._stress,
            turnover=turnover,
        )

    def round_trip(
        self, segment: Segment, buy_price: Decimal, sell_price: Decimal, quantity: Decimal
    ) -> RoundTripCost:
        """Both sides of a complete trade. Sell-side charges are levied on the **exit** turnover."""
        return RoundTripCost(
            buy=self.charges(segment, OrderSide.BUY, buy_price, quantity),
            sell=self.charges(segment, OrderSide.SELL, sell_price, quantity),
        )

    def breakeven_move(self, segment: Segment, price: Decimal, quantity: Decimal) -> Decimal:
        """The fractional price rise a long trade needs just to net zero.

        This is the number that tells you whether a strategy is *possible* at a given size, before
        any question of whether it is any good. Solved by fixed point because the sell-side charges
        scale with the exit price, which is what we are solving for.
        """
        notional = price * quantity
        move = Decimal(0)
        for _ in range(_BREAKEVEN_PASSES):
            cost = self.round_trip(segment, price, price * (1 + move), quantity).total
            move = cost / notional
        return move

    def _schedule(self, segment: Segment) -> SegmentSchedule:
        schedule: SegmentSchedule = getattr(self._cfg.segments, segment.value)
        return schedule


def clears_hurdle(
    expected_net_edge_inr: Decimal, round_trip_cost_inr: Decimal, multiplier: float
) -> bool:
    """The §7.3 cost-hurdle rule: ``edge >= multiplier x round_trip_cost``.

    ``multiplier`` comes from ``goal.yaml`` ``risk.cost_hurdle_multiplier`` (default 1.5). It is a
    risk limit rather than a property of the cost schedule, so the caller passes it in and this
    stays a free function. Rejecting most small trades at seed tier is the intended behaviour.
    """
    return expected_net_edge_inr >= _dec(multiplier) * round_trip_cost_inr


def segment_for(asset_class: AssetClass, *, intraday: bool) -> Segment:
    """Map an asset class to its cash-market segment.

    Crypto raises rather than guessing: Delta's fee schedule is unverified and crypto is deferred
    (BUILD_MAP D1). Funding accrual and futures roll are task 1.5b (§33). A plausible-looking
    invented fee would be worse than no crypto backtest at all.
    """
    if asset_class is AssetClass.CRYPTO:
        raise NotImplementedError(
            "crypto costs are task 1.5b (§33): fees, funding accrual and roll must be verified "
            "against the live Delta schedule before any crypto backtest is trustworthy"
        )
    return Segment.EQUITY_INTRADAY if intraday else Segment.EQUITY_DELIVERY


def _dec(value: Decimal | float | int) -> Decimal:
    """Convert a config float to Decimal via ``str`` so 0.00015 does not arrive as 0.000149999..."""
    return value if isinstance(value, Decimal) else Decimal(str(value))
