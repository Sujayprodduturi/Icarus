"""The LIMIT fill model — did this order actually happen? (task 1.7b, PRD §30.1-30.3).

**The dominant error in retail backtesting is assuming you got filled.** Every other kind of
optimism — a cost model that is a little light, a slightly generous starting date — moves the
result by a few percent. This one inverts the sign of whole strategies, and it does so *while
looking correct*, which is why it gets its own module and its own invariant (#12).

The mechanism is worth stating plainly, because "the price touched my limit so I was filled" sounds
harmless. Put a buy limit at 100 and suppose the day's low is exactly 100. Almost certainly nobody
filled you: price came down, printed one trade at 100 to people already ahead of you in the queue,
and left. But the damage is not that some fills are imaginary — it is *which* ones. You get handed
precisely the days where price reached your level and reversed hard in your favour, and you are
spared the days where it kept going straight through you. The invented trades are systematically
the winners. A strategy can be built entirely out of that artefact and show a beautiful equity
curve made of trades that never occurred.

So: **a resting limit fills only if the bar traded strictly through it**, and **no-fill is a real
modelled outcome** rather than an error case.

**Three order kinds, because they lie in different ways:**

=====================  ==========================================================================
``MARKETABLE_LIMIT``   Crosses the spread at the next bar's open. Nearly always fills, and pays
                       ``slippage_bps`` for the privilege. This is what the live Execution agent
                       places (PRD §5 — marketable limit with protection), so the simulation and
                       the live path model the same order type.
``RESTING_LIMIT``      Passive. Pays no spread, and fills only on a strict trade-through with a
                       pessimistic queue assumption. Take-profits are these.
``STOP``               Dormant until price trades through the trigger, then behaves as a
                       marketable order. **A stop does not guarantee the stop price**, which is
                       the second-biggest free lunch in backtesting after touch-equals-fill.
=====================  ==========================================================================

**Gaps are where stops actually cost money.** If the trigger is 95 and the bar opens at 88, the
fill is 88 — not 95. Modelling a stop as always filling at its trigger quietly removes overnight
gap risk from the entire backtest, and overnight gap risk is most of the risk in Indian cash
equity, where a large share of the move happens between sessions. The stop is filled at the
*worse* of the trigger and the open, always.

**Latency does nothing here, which is stated rather than hidden.** ``latency_ms`` (750ms) is a
real constraint on intraday bars. On daily bars, next-bar execution already imposes a delay six
orders of magnitude larger, so the latency term cannot bind and this model does not consult it.
It stays in the config — validated there, unused here — so the day the engine runs on 5-minute
bars the number already exists and has been thought about, rather than being discovered missing.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING

from icarus.common.types import OrderSide

if TYPE_CHECKING:
    from datetime import datetime

    from icarus.common.config import ExecutionRealism

_BPS = Decimal(10_000)


class OrderKind(enum.StrEnum):
    """How an order reaches the market. See the table in the module docstring."""

    MARKETABLE_LIMIT = "marketable_limit"
    RESTING_LIMIT = "resting_limit"
    STOP = "stop"


class NoFillReason(enum.StrEnum):
    """Why an order did not fill. A first-class outcome, never an exception.

    Recorded rather than collapsed into a single "unfilled" flag: a strategy that never fills
    because its limits are unreachable is a different problem from one that never fills because it
    is too large for the book, and the metric sheet should be able to say which.
    """

    NOT_TRADED_THROUGH = "not_traded_through"
    QUEUE_TOO_DEEP = "queue_too_deep"
    TOO_LARGE_FOR_BAR = "too_large_for_bar"
    NOT_TRIGGERED = "not_triggered"
    NO_VOLUME = "no_volume"


@dataclass(frozen=True, slots=True)
class SimBar:
    """One bar, in the money type. Converted once at the boundary out of the float columns.

    The library computes signals in ``float64`` because that is what whole-series arithmetic wants;
    money is ``Decimal`` because a paisa lost to binary rounding is a paisa the contract note will
    disagree about. The conversion happens here, once per execution event, of which there are
    hundreds — not per bar, of which there are millions.
    """

    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass(frozen=True, slots=True)
class Intent:
    """What the strategy asked for, and *when it was decided*.

    ``decided_at`` is carried separately from the bar the order executes on and asserted against it
    (PRD §30.2). Two fields rather than one because the whole class of same-bar look-ahead bugs
    reduces to the two silently being equal.
    """

    side: OrderSide
    kind: OrderKind
    quantity: int
    decided_at: datetime
    limit_price: Decimal | None = None

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError(f"intent quantity must be positive, got {self.quantity}")
        if self.kind is not OrderKind.MARKETABLE_LIMIT and self.limit_price is None:
            raise ValueError(f"{self.kind} needs a limit_price")


@dataclass(frozen=True, slots=True)
class FillResult:
    """What happened. ``filled_quantity == 0`` is a normal, expected answer.

    ``requested_quantity`` is kept alongside so the caller can size risk on what actually filled
    (PRD §30.3) without having to hold the intent to know it was short-filled.
    """

    filled_quantity: int
    requested_quantity: int
    price: Decimal | None
    reason: NoFillReason | None
    ts: datetime | None

    @property
    def filled(self) -> bool:
        return self.filled_quantity > 0

    @property
    def partial(self) -> bool:
        return 0 < self.filled_quantity < self.requested_quantity


class FillModel:
    """Turns an :class:`Intent` and the bar it executes on into a :class:`FillResult`.

    Stateless and pure — same inputs, same outputs, no I/O — so it is safe in a backtest inner loop
    and, later, in the live decision path where it will be used to sanity-check real fills against
    modelled ones (PRD §30.5).
    """

    def __init__(self, config: ExecutionRealism) -> None:
        self._cfg = config
        self._slippage = Decimal(str(config.slippage_bps)) / _BPS
        self._tick = Decimal(str(config.tick_size_inr))
        self._participation = Decimal(str(config.max_participation_of_depth))
        self._queue_k = Decimal(str(config.queue_volume_multiple_k))

    def execute(self, intent: Intent, bar: SimBar) -> FillResult:
        """Execute ``intent`` against ``bar``, which must be strictly after the decision bar."""
        if bar.ts <= intent.decided_at:
            raise ValueError(
                f"execution bar {bar.ts} is not after the decision at {intent.decided_at} — a "
                f"signal computed on a bar's close cannot trade on that same bar (invariant #13)"
            )
        if bar.volume <= 0:
            return self._nothing(intent, NoFillReason.NO_VOLUME)

        if intent.kind is OrderKind.MARKETABLE_LIMIT:
            return self._marketable(intent, bar, reference=bar.open)
        if intent.kind is OrderKind.STOP:
            return self._stop(intent, bar)
        return self._resting(intent, bar)

    # -- the three kinds -------------------------------------------------------------------

    def _marketable(self, intent: Intent, bar: SimBar, *, reference: Decimal) -> FillResult:
        """Cross the spread at ``reference``, paying slippage in the direction that hurts."""
        signed = self._slippage if intent.side is OrderSide.BUY else -self._slippage
        price = self._to_tick(reference * (Decimal(1) + signed), side=intent.side)
        return self._sized(intent, bar, price)

    def _resting(self, intent: Intent, bar: SimBar) -> FillResult:
        """Fill only on a strict trade-through, with a pessimistic queue position.

        Strictness is the whole invariant. ``bar.low <= limit`` for a buy would fill on a bar that
        merely printed one trade at the level; ``bar.low < limit`` requires price to have gone
        *past* it, which is the honest proxy for "the queue ahead of me was cleared".
        """
        limit = intent.limit_price
        assert limit is not None  # guaranteed by Intent.__post_init__
        through = bar.low < limit if intent.side is OrderSide.BUY else bar.high > limit
        if not through:
            return self._nothing(intent, NoFillReason.NOT_TRADED_THROUGH)
        if bar.volume < self._queue_k * intent.quantity:
            return self._nothing(intent, NoFillReason.QUEUE_TOO_DEEP)
        # A resting order gets its own price, never better: the improvement belongs to whoever was
        # already there. Awarding the bar's extreme instead is a second helping of the same bias
        # touch-equals-fill produces.
        return self._sized(intent, bar, limit)

    def _stop(self, intent: Intent, bar: SimBar) -> FillResult:
        """Trigger on a trade-through, then fill at the **worse** of the trigger and the open.

        A sell stop at 95 on a bar that opens at 88 fills at 88. Filling it at 95 would delete
        overnight gap risk from the whole backtest — and on NSE cash equity a large share of the
        move happens between sessions, so that is not a rounding error, it is the risk.
        """
        trigger = intent.limit_price
        assert trigger is not None
        # A sell stop sits below the market and triggers on the way down; a buy stop above it.
        if intent.side is OrderSide.SELL:
            triggered = bar.low <= trigger
            reference = min(trigger, bar.open)
        else:
            triggered = bar.high >= trigger
            reference = max(trigger, bar.open)
        if not triggered:
            return self._nothing(intent, NoFillReason.NOT_TRIGGERED)
        return self._marketable(intent, bar, reference=reference)

    # -- shared -----------------------------------------------------------------------------

    def _sized(self, intent: Intent, bar: SimBar, price: Decimal) -> FillResult:
        """Cap the fill at our share of the bar's volume (PRD §30.4), then report it.

        The participation cap applies **always**. ``model_partial_fills`` only decides what happens
        to the remainder: fill what fits, or take nothing. It must not be able to switch the cap
        off — that reading would let a 500-share order clear a 1,000-share bar and call it a fill,
        which is touch-equals-fill wearing a size instead of a price.
        """
        cap = int((bar.volume * self._participation).to_integral_value(rounding=ROUND_DOWN))
        if cap < intent.quantity and not self._cfg.model_partial_fills:
            return self._nothing(intent, NoFillReason.TOO_LARGE_FOR_BAR)
        quantity = min(intent.quantity, cap)
        if quantity <= 0:
            return self._nothing(intent, NoFillReason.TOO_LARGE_FOR_BAR)
        return FillResult(
            filled_quantity=quantity,
            requested_quantity=intent.quantity,
            price=price,
            reason=None,
            ts=bar.ts,
        )

    def _nothing(self, intent: Intent, reason: NoFillReason) -> FillResult:
        return FillResult(
            filled_quantity=0,
            requested_quantity=intent.quantity,
            price=None,
            reason=reason,
            ts=None,
        )

    def _to_tick(self, price: Decimal, *, side: OrderSide) -> Decimal:
        """Round to a real tradable price, away from us.

        A fill at 123.4567 is not a price anyone could have got. Rounding *away* — up for a buy,
        down for a sell — keeps the sub-tick remainder on the pessimistic side rather than handing
        it back as a fraction of a paisa of free edge on every one of thousands of trades.
        """
        ticks = price / self._tick
        rounded = ticks.to_integral_value(rounding=ROUND_HALF_UP)
        if side is OrderSide.BUY and rounded < ticks:
            rounded += 1
        elif side is OrderSide.SELL and rounded > ticks:
            rounded -= 1
        return rounded * self._tick
