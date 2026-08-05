"""The LIMIT fill model — task 1.7b, PRD §30.1-30.3.

Every test here exists because the opposite behaviour is what a naive backtester does, and each
one of those defaults flatters a result in the same direction. The three that matter most:

* **Touch is not a fill** (invariant #12). Filling on a touch hands the strategy precisely the
  bars where price reached its level and reversed — the invented trades are systematically the
  winners, so the bias does not average out, it compounds.
* **A stop does not guarantee the stop price.** Filling a gapped stop at its trigger deletes
  overnight gap risk from the entire backtest, and on NSE cash equity that is most of the risk.
* **A signal cannot trade on the bar that produced it** (invariant #13). The model raises rather
  than quietly executing, because a same-bar fill is indistinguishable from a correct one in the
  output.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from icarus.common.config import ExecutionRealism
from icarus.common.types import OrderSide
from icarus.engine.fills import (
    FillModel,
    Intent,
    NoFillReason,
    OrderKind,
    SimBar,
)

DECIDED = datetime(2024, 3, 1, tzinfo=UTC)
NEXT = DECIDED + timedelta(days=1)


def _config(**overrides: object) -> ExecutionRealism:
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


def _model(**overrides: object) -> FillModel:
    return FillModel(_config(**overrides))


def _bar(o: str, h: str, low: str, c: str, volume: str = "1000000", ts: datetime = NEXT) -> SimBar:
    return SimBar(
        ts=ts,
        open=Decimal(o),
        high=Decimal(h),
        low=Decimal(low),
        close=Decimal(c),
        volume=Decimal(volume),
    )


def _intent(
    kind: OrderKind,
    side: OrderSide = OrderSide.BUY,
    quantity: int = 10,
    limit: str | None = None,
) -> Intent:
    return Intent(
        side=side,
        kind=kind,
        quantity=quantity,
        decided_at=DECIDED,
        limit_price=None if limit is None else Decimal(limit),
    )


# --------------------------------------------------------------------------------------
# Next-bar execution
# --------------------------------------------------------------------------------------


def test_a_signal_cannot_execute_on_the_bar_that_produced_it() -> None:
    """Invariant #13. It raises rather than filling, because a same-bar fill looks identical to a
    correct one in the trade ledger — there is nothing downstream that could catch it."""
    with pytest.raises(ValueError, match="cannot trade on that same bar"):
        _model().execute(
            _intent(OrderKind.MARKETABLE_LIMIT), _bar("100", "101", "99", "100", ts=DECIDED)
        )


def test_a_bar_strictly_after_the_decision_is_allowed() -> None:
    result = _model().execute(_intent(OrderKind.MARKETABLE_LIMIT), _bar("100", "101", "99", "100"))
    assert result.filled


# --------------------------------------------------------------------------------------
# Touch != fill — the invariant this module exists for
# --------------------------------------------------------------------------------------


def test_a_resting_buy_limit_does_not_fill_when_price_merely_touches_it() -> None:
    """The day's low is exactly the limit. Price printed there and left; the queue ahead of us
    took the shares. Filling here is the single most expensive default in backtesting."""
    result = _model().execute(
        _intent(OrderKind.RESTING_LIMIT, limit="100"), _bar("102", "103", "100", "101")
    )
    assert not result.filled
    assert result.reason is NoFillReason.NOT_TRADED_THROUGH


def test_a_resting_buy_limit_fills_when_price_trades_strictly_through_it() -> None:
    result = _model().execute(
        _intent(OrderKind.RESTING_LIMIT, limit="100"), _bar("102", "103", "99.5", "101")
    )
    assert result.filled
    assert result.price == Decimal("100")


def test_a_resting_sell_limit_is_the_mirror_image() -> None:
    model = _model()
    touched = model.execute(
        _intent(OrderKind.RESTING_LIMIT, OrderSide.SELL, limit="105"),
        _bar("102", "105", "101", "103"),
    )
    through = model.execute(
        _intent(OrderKind.RESTING_LIMIT, OrderSide.SELL, limit="105"),
        _bar("102", "105.5", "101", "103"),
    )
    assert not touched.filled
    assert through.filled and through.price == Decimal("105")


def test_a_resting_fill_never_gets_a_better_price_than_it_asked_for() -> None:
    """Price traded far through the limit, but the improvement belongs to whoever was already
    resting there. Awarding the bar's low is a second helping of the touch-equals-fill bias."""
    result = _model().execute(
        _intent(OrderKind.RESTING_LIMIT, limit="100"), _bar("102", "103", "90", "95")
    )
    assert result.price == Decimal("100")


def test_a_resting_order_too_big_for_the_bar_does_not_fill() -> None:
    """Pessimistic queue position: the bar must trade at least k times our size before we can
    assume the queue ahead of us cleared."""
    result = _model().execute(
        _intent(OrderKind.RESTING_LIMIT, quantity=1000, limit="100"),
        _bar("102", "103", "99", "101", volume="1500"),
    )
    assert not result.filled
    assert result.reason is NoFillReason.QUEUE_TOO_DEEP


# --------------------------------------------------------------------------------------
# Marketable limits — the order the live Execution agent actually places
# --------------------------------------------------------------------------------------


def test_a_marketable_buy_pays_the_spread_and_rounds_away_from_us() -> None:
    """Open 100, 5bps slippage -> 100.05, which is already on a 0.05 tick."""
    result = _model().execute(_intent(OrderKind.MARKETABLE_LIMIT), _bar("100", "101", "99", "100"))
    assert result.price == Decimal("100.05")


def test_a_marketable_sell_pays_the_spread_in_the_other_direction() -> None:
    result = _model().execute(
        _intent(OrderKind.MARKETABLE_LIMIT, OrderSide.SELL), _bar("100", "101", "99", "100")
    )
    assert result.price == Decimal("99.95")


def test_slippage_is_never_a_gift_in_either_direction() -> None:
    """The buy pays more than the open and the sell receives less. A model where one side gains is
    a model that pays you to trade."""
    model = _model()
    bar = _bar("250.13", "252", "249", "251")
    buy = model.execute(_intent(OrderKind.MARKETABLE_LIMIT), bar)
    sell = model.execute(_intent(OrderKind.MARKETABLE_LIMIT, OrderSide.SELL), bar)
    assert buy.price is not None and sell.price is not None
    assert buy.price > bar.open
    assert sell.price < bar.open


def test_every_fill_price_lands_on_a_real_tick() -> None:
    model = _model()
    tick = Decimal("0.05")
    for open_price in ("100.02", "1234.56", "77.77", "9.99"):
        for side in (OrderSide.BUY, OrderSide.SELL):
            result = model.execute(
                _intent(OrderKind.MARKETABLE_LIMIT, side), _bar(open_price, "9999", "0.01", "100")
            )
            assert result.price is not None
            assert result.price % tick == 0, f"{result.price} is not a tradable price"


# --------------------------------------------------------------------------------------
# Stops — where the gap risk actually lives
# --------------------------------------------------------------------------------------


def test_a_stop_that_gaps_fills_at_the_open_not_at_the_trigger() -> None:
    """Sell stop at 95, bar opens at 88. You get 88.

    Filling this at 95 removes overnight gap risk from the whole backtest — and on NSE cash equity
    a large share of the move happens between sessions, so it is not a rounding error.
    """
    result = _model().execute(
        _intent(OrderKind.STOP, OrderSide.SELL, limit="95"), _bar("88", "90", "86", "89")
    )
    assert result.filled
    assert result.price is not None
    assert result.price < Decimal("89")  # 88 minus slippage, nowhere near the 95 trigger


def test_a_stop_that_does_not_gap_fills_near_its_trigger() -> None:
    result = _model().execute(
        _intent(OrderKind.STOP, OrderSide.SELL, limit="95"), _bar("99", "100", "94", "96")
    )
    assert result.filled
    assert result.price is not None
    assert Decimal("94.9") <= result.price <= Decimal("95")


def test_an_untriggered_stop_does_nothing() -> None:
    result = _model().execute(
        _intent(OrderKind.STOP, OrderSide.SELL, limit="95"), _bar("99", "100", "96", "98")
    )
    assert not result.filled
    assert result.reason is NoFillReason.NOT_TRIGGERED


def test_a_buy_stop_is_the_mirror_image_and_gaps_the_other_way() -> None:
    result = _model().execute(
        _intent(OrderKind.STOP, OrderSide.BUY, limit="105"), _bar("112", "114", "111", "113")
    )
    assert result.filled
    assert result.price is not None
    assert result.price > Decimal("112")  # the gap hurts a buy stop upward


# --------------------------------------------------------------------------------------
# Size, participation and no-fill as a real outcome
# --------------------------------------------------------------------------------------


def test_an_order_larger_than_our_share_of_the_bar_fills_only_partially() -> None:
    """5% participation cap on 1,000 traded shares is 50, however many we asked for."""
    result = _model().execute(
        _intent(OrderKind.MARKETABLE_LIMIT, quantity=500),
        _bar("100", "101", "99", "100", volume="1000"),
    )
    assert result.partial
    assert result.filled_quantity == 50
    assert result.requested_quantity == 500


def test_turning_off_partial_fills_takes_nothing_rather_than_taking_everything() -> None:
    """The participation cap applies whatever `model_partial_fills` says.

    The tempting reading is that disabling partial fills means "fill it all" — which would let a
    500-share order clear a 1,000-share bar and call it done. That is touch-equals-fill wearing a
    size instead of a price, so the flag only chooses between filling what fits and taking nothing.
    """
    intent = _intent(OrderKind.MARKETABLE_LIMIT, quantity=500)
    bar = _bar("100", "101", "99", "100", volume="1000")
    assert _model().execute(intent, bar).filled_quantity == 50
    all_or_nothing = _model(model_partial_fills=False).execute(intent, bar)
    assert all_or_nothing.filled_quantity == 0
    assert all_or_nothing.reason is NoFillReason.TOO_LARGE_FOR_BAR


def test_a_bar_with_no_volume_fills_nothing() -> None:
    """A session where the symbol did not trade is not a session where we got our price."""
    result = _model().execute(
        _intent(OrderKind.MARKETABLE_LIMIT), _bar("100", "100", "100", "100", volume="0")
    )
    assert not result.filled
    assert result.reason is NoFillReason.NO_VOLUME


def test_no_fill_is_a_result_not_an_exception() -> None:
    """The engine has to be able to account for the trade that did not happen — including any
    exposure left unmanaged because an exit did not fill."""
    result = _model().execute(
        _intent(OrderKind.RESTING_LIMIT, limit="1"), _bar("100", "101", "99", "100")
    )
    assert result.filled_quantity == 0
    assert result.requested_quantity == 10
    assert result.price is None
    assert result.ts is None


def test_an_intent_must_ask_for_something() -> None:
    with pytest.raises(ValueError, match="quantity must be positive"):
        Intent(
            side=OrderSide.BUY,
            kind=OrderKind.MARKETABLE_LIMIT,
            quantity=0,
            decided_at=DECIDED,
        )


def test_a_resting_order_without_a_price_is_rejected() -> None:
    with pytest.raises(ValueError, match="needs a limit_price"):
        Intent(
            side=OrderSide.BUY,
            kind=OrderKind.RESTING_LIMIT,
            quantity=10,
            decided_at=DECIDED,
        )


# --------------------------------------------------------------------------------------
# The config refusals
# --------------------------------------------------------------------------------------


def test_touch_equals_fill_cannot_be_configured_back_on() -> None:
    with pytest.raises(ValueError, match="invariant #12"):
        _config(fill_requires_trade_through=False)


def test_same_bar_execution_cannot_be_configured_back_on() -> None:
    with pytest.raises(ValueError, match="invariant #13"):
        _config(next_bar_execution=False)


def test_zero_slippage_is_rejected() -> None:
    """A marketable order that crosses the spread for free is the same class of lie as a fill on
    a touch, and it would be an easy thing to set to zero 'just to see'."""
    with pytest.raises(ValueError):
        _config(slippage_bps=0.0)
