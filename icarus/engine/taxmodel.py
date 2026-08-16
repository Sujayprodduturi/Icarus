"""After-tax P&L (task 1.6, PRD §6, CLAUDE.md §5).

**Tax is annual and applies to the aggregate — this is the whole reason it cannot be bolted onto
the cost model.** Cost is a property of a trade: you buy, you pay charges, done. Tax is a property
of a *year*: the bill depends on everything else that happened between 1 April and 31 March, so a
per-trade tax figure is a fiction. This module therefore consumes a **ledger of closed trades** and
returns **one bill per financial year**.

**The same rupee of profit is taxed differently depending on how it was earned.** That is not a
detail — it decides which strategies are worth running at all:

===========================  =======================  ==============  ==========================
How it was traded            Bucket                   Rate            Carry-forward
===========================  =======================  ==============  ==========================
Equity intraday              speculative business     slab            4 years
Equity delivery (business)   non-speculative          slab            8 years
Equity delivery (CG, <=12m)  STCG                     20%             8 years
Equity delivery (CG, >12m)   LTCG                     12.5% > ₹1.25L  8 years
F&O                          non-speculative          slab            8 years
Crypto INR derivatives       speculative business     slab            4 years
Crypto as VDA (**stress**)   flat VDA                 30%             **never**
===========================  =======================  ==============  ==========================

**Read the last row carefully — it is the trap the stress scenario exists to expose.** Under the
VDA reading, losses buy you *nothing*: tax lands on the **winning trades alone**, not on the year's
net, so a loss cannot even offset another VDA gain. Nothing carries forward either. A strategy
winning 60% of its trades and comfortably profitable gross can be **net negative after tax**, and
its effective rate on net profit can be multiples of the 30% headline. §6 requires flagging any
strategy that survives only the optimistic reading, and :class:`Scenario` is how the gate does it.

*Known slight understatement in the VDA path:* the statute allows no deduction except cost of
acquisition, so transaction fees are not deductible — but the ``pnl`` fed in here is already net of
them. The VDA bill is therefore marginally lower than the true one. Left as-is because crypto is
deferred and this is a stress scenario, but it errs in our favour, so it is written down.

**Marginal, not slab.** ``operator_slab_rate`` is applied as a single marginal rate. This is
correct rather than lazy: trading profit sits *on top* of the operator's other income, so the
marginal rate is what one more rupee of profit actually costs. Computing slabs from zero would
yield the *average* rate and understate the bill.

**The one simplification, stated rather than assumed: no inter-bucket set-off.** Real law lets a
loss in one bucket offset gains in another, in specific patterns. Here each bucket nets and carries
its own losses alone. That is safe in a specific, checkable direction — declining to offset can only
ever compute a bill **greater than or equal to** the true one, never smaller. And the loss is not
discarded: it carries forward inside its own bucket, which is exactly the stricter rule the statute
already applies to *carried-forward* losses. The price is that a genuinely favourable effect goes
unclaimed once several strategies run in different buckets simultaneously; that is a real
understatement of edge, and it is deliberate.

Rates live in ``goal.yaml`` with their sources and as-of dates. FY 2026-27 is the first year under
the **new Income-tax Act, 2025**, so section numbers moved (speculative business: s.43(5) of the
1961 Act → s.66 of the 2025 Act).
"""

from __future__ import annotations

import calendar
import enum
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from icarus.common.calendar import IST
from icarus.engine.costmodel import Segment

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from icarus.common.config import Tax as TaxConfig

# India's financial year runs 1 April - 31 March. Determined on the IST calendar date, never UTC:
# a trade closing 31 Mar 21:00 IST is 15:30 UTC the same day, but one closing at 00:30 IST on 1 Apr
# is 19:00 UTC on 31 Mar — the wrong financial year if you read the UTC date (invariant #22).
_FY_START_MONTH = 4


def _ist_date(ts: datetime, *, what: str) -> date:
    """A tz-aware UTC timestamp as its **IST calendar date** (invariant #22).

    Every tax boundary is an IST-calendar boundary, and UTC is half a day out at the wrong end of
    it. One function rather than the conversion written at each site, because the two sites are the
    financial year and the holding period and they must never disagree about what day it was.
    """
    if ts.tzinfo is None:
        raise ValueError(f"{what} must be tz-aware UTC to resolve an IST date (PRD §29.5)")
    return ts.astimezone(IST).date()


def _add_months(day: date, months: int) -> date:
    """The same day-of-month, ``months`` calendar months later, clamped to a short month.

    31 January plus one month is 28 February (29 in a leap year), which is the ordinary convention
    and the one that keeps the result inside the month it names.
    """
    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


class Bucket(enum.StrEnum):
    """A tax bucket: a rate, a set of set-off rules, and a carry-forward window.

    Buckets exist because Indian law taxes the *manner* of trading, not just the profit.
    """

    EQUITY_SPECULATIVE = "equity_speculative"  # intraday equity — s.66 (was s.43(5))
    NONSPECULATIVE = "nonspeculative"  # F&O, and delivery if classified as business
    STCG = "stcg"  # delivery as capital gains, held <= ltcg_holding_months
    LTCG = "ltcg"  # delivery as capital gains, held longer
    CRYPTO_SPECULATIVE = "crypto_speculative"  # INR-settled derivatives, optimistic reading
    CRYPTO_VDA = "crypto_vda"  # the reclassification stress: flat, no relief


class Scenario(enum.StrEnum):
    """Which tax reading to compute under.

    ``CRYPTO_RECLASSIFIED`` is the §6 stress: crypto derivative P&L is re-bucketed to flat-rate VDA
    with no loss relief whatsoever. The gate runs both and flags anything that only survives
    ``DEFAULT``.
    """

    DEFAULT = "default"
    CRYPTO_RECLASSIFIED = "crypto_reclassified"


@dataclass(frozen=True)
class RealizedTrade:
    """One closed trade, already net of costs (the CostModel ran first).

    ``pnl`` is the realised rupee result — negative for a loss. ``exit_ts`` must be tz-aware UTC;
    the financial year is derived from its **IST** date.
    """

    bucket: Bucket
    pnl: Decimal
    exit_ts: datetime

    def __post_init__(self) -> None:
        if self.exit_ts.tzinfo is None:
            raise ValueError("RealizedTrade.exit_ts must be tz-aware UTC (PRD §29.5)")


@dataclass(frozen=True)
class BucketOutcome:
    """What one bucket did in one financial year, and what it owes."""

    bucket: Bucket
    net_pnl: Decimal  # this year's realised result, before any carried-forward relief
    loss_absorbed: Decimal  # carried-forward loss actually used this year
    exempt: Decimal  # statutory exemption applied (LTCG only)
    taxable: Decimal
    tax: Decimal  # before cess
    loss_carried_out: Decimal  # positive number = loss available to future years


@dataclass(frozen=True)
class FinancialYearTax:
    """The bill for one financial year, itemised by bucket so it can be audited."""

    fy_start_year: int  # 2026 means FY 2026-27
    buckets: tuple[BucketOutcome, ...]
    cess: Decimal

    @property
    def label(self) -> str:
        return f"{self.fy_start_year}-{(self.fy_start_year + 1) % 100:02d}"

    @property
    def tax_before_cess(self) -> Decimal:
        return sum((b.tax for b in self.buckets), Decimal(0))

    @property
    def total_tax(self) -> Decimal:
        return self.tax_before_cess + self.cess

    @property
    def gross_pnl(self) -> Decimal:
        return sum((b.net_pnl for b in self.buckets), Decimal(0))

    @property
    def net_pnl(self) -> Decimal:
        """After-tax P&L — the only number a strategy should ever be scored on (CLAUDE.md §5)."""
        return self.gross_pnl - self.total_tax


class TaxModel:
    """Turns a ledger of closed trades into a per-financial-year tax bill.

    Stateless and pure. Carry-forward is threaded through the years *inside* one call, because a
    year's bill genuinely depends on the years before it — splitting the call per year would lose
    that and systematically overstate tax.
    """

    def __init__(self, config: TaxConfig, *, scenario: Scenario = Scenario.DEFAULT) -> None:
        self._cfg = config
        self._scenario = scenario

    def annual_tax(self, trades: Iterable[RealizedTrade]) -> list[FinancialYearTax]:
        """One :class:`FinancialYearTax` per financial year that saw a trade, oldest first.

        Years with no trades are skipped, but carried-forward losses still age across them — an
        expiring loss must expire on the calendar, not on trade activity.
        """
        # Two accumulators, because VDA needs the winners *alone*: under a strict reading of the
        # no-set-off rule a VDA loss cannot even offset another VDA gain, so netting the bucket
        # first would silently grant relief the statute denies. Every other bucket does net.
        net_by: dict[int, dict[Bucket, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        wins_by: dict[int, dict[Bucket, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        for trade in trades:
            bucket = self._apply_scenario(trade.bucket)
            fy = financial_year(trade.exit_ts)
            net_by[fy][bucket] += trade.pnl
            if trade.pnl > 0:
                wins_by[fy][bucket] += trade.pnl

        # (loss_amount, fy_it_arose_in) per bucket, oldest first — the queue we draw relief from.
        pending: dict[Bucket, list[tuple[Decimal, int]]] = defaultdict(list)
        results: list[FinancialYearTax] = []

        for fy in sorted(net_by):
            outcomes = [
                self._settle_bucket(bucket, net, wins_by[fy][bucket], fy, pending)
                for bucket, net in sorted(net_by[fy].items())
            ]
            tax_before_cess = sum((o.tax for o in outcomes), Decimal(0))
            results.append(
                FinancialYearTax(
                    fy_start_year=fy,
                    buckets=tuple(outcomes),
                    cess=tax_before_cess * _dec(self._cfg.cess_rate),
                )
            )
        return results

    def _settle_bucket(
        self,
        bucket: Bucket,
        net: Decimal,
        wins: Decimal,
        fy: int,
        pending: dict[Bucket, list[tuple[Decimal, int]]],
    ) -> BucketOutcome:
        """Net one bucket for one year: expire stale losses, absorb relief, apply the rate."""
        if bucket is Bucket.CRYPTO_VDA:
            # VDA is taxed on the WINNERS ALONE — not the year's net. A losing trade grants no
            # relief against a winning one, so the effective rate on net profit can far exceed the
            # 30% headline. Nothing is ever queued: VDA losses do not carry forward either.
            return BucketOutcome(
                bucket=bucket,
                net_pnl=net,
                loss_absorbed=Decimal(0),
                exempt=Decimal(0),
                taxable=wins,
                tax=wins * _dec(self._cfg.vda_flat_rate),
                loss_carried_out=Decimal(0),
            )

        window = self._carry_forward_years(bucket)
        # A loss from FY X is usable in FY X+1 .. X+window. Drop anything older, on the calendar.
        queue = [(amount, arose) for amount, arose in pending[bucket] if fy - arose <= window]

        if net < 0:
            queue.append((-net, fy))
            pending[bucket] = queue
            return BucketOutcome(
                bucket=bucket,
                net_pnl=net,
                loss_absorbed=Decimal(0),
                exempt=Decimal(0),
                taxable=Decimal(0),
                tax=Decimal(0),
                loss_carried_out=sum((amount for amount, _ in queue), Decimal(0)),
            )

        remaining = net
        absorbed = Decimal(0)
        survivors: list[tuple[Decimal, int]] = []
        for amount, arose in queue:  # oldest first: spend the losses closest to expiring
            used = min(amount, remaining)
            absorbed += used
            remaining -= used
            if amount > used:
                survivors.append((amount - used, arose))
        pending[bucket] = survivors

        exempt = Decimal(0)
        if bucket is Bucket.LTCG:
            exempt = min(remaining, _dec(self._cfg.ltcg_exemption_inr))
            remaining -= exempt

        return BucketOutcome(
            bucket=bucket,
            net_pnl=net,
            loss_absorbed=absorbed,
            exempt=exempt,
            taxable=remaining,
            tax=remaining * self._rate(bucket),
            loss_carried_out=sum((amount for amount, _ in survivors), Decimal(0)),
        )

    def _rate(self, bucket: Bucket) -> Decimal:
        if bucket is Bucket.STCG:
            return _dec(self._cfg.stcg_rate)
        if bucket is Bucket.LTCG:
            return _dec(self._cfg.ltcg_rate)
        if bucket is Bucket.CRYPTO_VDA:
            return _dec(self._cfg.vda_flat_rate)
        # Everything else is business income at the operator's marginal slab rate.
        return _dec(self._cfg.operator_slab_rate)

    def _carry_forward_years(self, bucket: Bucket) -> int:
        if bucket in (Bucket.EQUITY_SPECULATIVE, Bucket.CRYPTO_SPECULATIVE):
            return self._cfg.carry_forward_years_speculative
        if bucket in (Bucket.STCG, Bucket.LTCG):
            return self._cfg.carry_forward_years_capital
        return self._cfg.carry_forward_years_nonspeculative

    def _apply_scenario(self, bucket: Bucket) -> Bucket:
        """Re-bucket crypto derivatives to VDA under the §6 reclassification stress."""
        if self._scenario is Scenario.CRYPTO_RECLASSIFIED and bucket is Bucket.CRYPTO_SPECULATIVE:
            return Bucket.CRYPTO_VDA
        return bucket

    def bucket_for(self, segment: Segment, *, entry_ts: datetime, exit_ts: datetime) -> Bucket:
        """The bucket a closed equity trade falls into.

        Delivery is the only ambiguous case (§6.1): under a business-income classification it is
        non-speculative regardless of holding period; under capital gains the holding period splits
        STCG from LTCG.

        **The split is in calendar months, and takes the two dates rather than a day count, because
        a day count cannot express it.** s.2(42A) asks whether the asset was held for more than
        twelve *months*; twelve months is 365 or 366 days depending on where the leap day falls.
        This used to approximate a month as 30 days, making the threshold 360, so every delivery
        trade held 361 to 365 days was mis-bucketed. A fold's test window is about 365 calendar
        days and the baseline control holds to the end of the fold, so it sits in that band.

        **It was wrong in both directions, which is why no single word describes it.** A *gain* in
        the band was booked long-term at 12.5% with the ₹1.25L exemption instead of 20% with none —
        cheaper, flattering. A *loss* in the band was booked as an LTCG loss, and with no
        inter-bucket set-off (:meth:`_settle_bucket`) an LTCG loss only shelters future gains at
        12.5% where an STCG loss shelters them at 20%: a ₹100,000 loss followed by a ₹100,000 STCG
        gain the next year cost ₹20,800 under the old classification and nothing under this one.
        Which way a given strategy was flattered therefore depends on its win/loss mix inside those
        five days, and is not knowable without measuring it.

        That two-sidedness is the point. The reason this survived was the comment above the old
        constant, which asserted the approximation "errs toward STCG (the higher rate) more often
        than not" — a confident, absolute, untested claim about direction. The first draft of *this*
        docstring replaced it with "in our favour, always", which is the same mistake with the sign
        flipped, and a review caught it. **Where a comment claims a bias, the bias needs a test.**

        **The anniversary itself is treated as short-term**, which is one day more conservative
        than the common reading (holding period counted from the day *after* acquisition would make
        the anniversary day 366, and therefore long-term). The boundary is genuinely ambiguous by a
        day; STCG is the higher rate, so that is the direction to be wrong in. Flagged for the CA
        alongside O7.
        """
        # Validated before the branches, not inside the one branch that happens to need the dates.
        # Sitting below them made both guards reachable only under the capital-gains reading — and
        # TASKS.md O7 describes the business-income flip as "one config word away", so a naive or
        # transposed pair would have started passing silently the day the CA came back.
        bought = _ist_date(entry_ts, what="entry_ts")
        sold = _ist_date(exit_ts, what="exit_ts")
        if sold < bought:
            raise ValueError(f"a trade cannot be sold ({sold}) before it was bought ({bought})")

        if segment is Segment.EQUITY_INTRADAY:
            return Bucket.EQUITY_SPECULATIVE
        if segment in (Segment.EQUITY_FUTURES, Segment.EQUITY_OPTIONS):
            return Bucket.NONSPECULATIVE
        if self._cfg.equity_delivery == "nonspeculative_business":
            return Bucket.NONSPECULATIVE
        return (
            Bucket.LTCG
            if sold > _add_months(bought, self._cfg.ltcg_holding_months)
            else Bucket.STCG
        )


def financial_year(ts: datetime) -> int:
    """The Indian financial year containing ``ts``: 2026 means FY 2026-27 (1 Apr 26 - 31 Mar 27).

    Resolved on the **IST** calendar date. Reading the UTC date instead misfiles trades near the
    year boundary: 00:30 IST on 1 April is 19:00 UTC on 31 March — the previous financial year.
    """
    ist_date = _ist_date(ts, what="financial_year()")
    return ist_date.year if ist_date.month >= _FY_START_MONTH else ist_date.year - 1


def effective_tax_rate(years: Sequence[FinancialYearTax]) -> Decimal:
    """Total tax as a fraction of total gross profit across ``years``.

    Returns 0 when there was no profit to tax. Note this can exceed the headline rate: a losing
    year followed by a winning one pays on the winner while relief is capped by the carry-forward
    rules — and under VDA the loss buys nothing at all. That gap is the number worth looking at.
    """
    gross = sum((y.gross_pnl for y in years), Decimal(0))
    if gross <= 0:
        return Decimal(0)
    return sum((y.total_tax for y in years), Decimal(0)) / gross


def _dec(value: Decimal | float | int) -> Decimal:
    """Convert a config float to Decimal via ``str`` so 0.125 does not arrive as 0.1249999..."""
    return value if isinstance(value, Decimal) else Decimal(str(value))
