"""Compliance gate tests (task 0.10) — the hard limits MUST be unexceedable (CLAUDE.md §6).

Covers the AC: 3rd order/sec blocked, IP mismatch -> HALT, MARKET order rejected; plus
white-box, algo-tag, market-hours, and the per-minute HALT tripwire.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from icarus.agents.compliance.core import ComplianceGate, PolicyDecision, RateGovernor
from icarus.common.config import Compliance
from icarus.common.types import AssetClass, OrderSide, OrderType, SizedOrder

REGISTERED_IP = "203.0.113.10"


def _cfg(**over: object) -> Compliance:
    base: dict[str, object] = {
        "max_orders_per_sec": 2,
        "max_orders_per_min": 20,
        "max_orders_per_day": 200,
        "white_box_only": True,
        "static_ip_required": True,
        "limit_orders_only": True,
        "algo_id_tagging_required": True,
    }
    base.update(over)
    return Compliance.model_validate(base)


def _order(
    order_type: OrderType = OrderType.LIMIT, algo_id: str | None = "444444444444X"
) -> SizedOrder:
    return SizedOrder(
        client_order_id="c1",
        strategy_id="s1",
        symbol="INFY",
        asset_class=AssetClass.CRYPTO,  # crypto = always open, isolates the rule under test
        side=OrderSide.BUY,
        order_type=order_type,
        quantity=Decimal(1),
        limit_price=Decimal("100"),
        algo_id=algo_id,
    )


def _gate() -> ComplianceGate:
    return ComplianceGate(_cfg(), REGISTERED_IP)


_NOW = datetime(2026, 7, 27, 6, 0, 0, tzinfo=UTC)  # crypto open regardless


def _open(_ac: AssetClass, _ts: datetime) -> bool:
    return True


def _check(gate: ComplianceGate, order: SizedOrder, now: datetime) -> PolicyDecision:
    """check_order with the fixed happy-path context (registered IP, white-box, market open)."""
    return gate.check_order(
        order, egress_ip=REGISTERED_IP, now=now, white_box=True, market_open_fn=_open
    )


def test_market_order_rejected() -> None:
    d = _gate().check_order(
        _order(order_type=OrderType.MARKET),
        egress_ip=REGISTERED_IP,
        now=_NOW,
        white_box=True,
        market_open_fn=_open,
    )
    assert not d.allowed and not d.halt
    assert "non-LIMIT" in d.reason


def test_ip_mismatch_halts() -> None:
    d = _gate().check_order(
        _order(), egress_ip="198.51.100.7", now=_NOW, white_box=True, market_open_fn=_open
    )
    assert d.halt
    assert "egress IP" in d.reason


def test_missing_algo_tag_rejected() -> None:
    d = _gate().check_order(
        _order(algo_id=None),
        egress_ip=REGISTERED_IP,
        now=_NOW,
        white_box=True,
        market_open_fn=_open,
    )
    assert not d.allowed
    assert "algo-ID" in d.reason


def test_non_white_box_rejected() -> None:
    d = _gate().check_order(
        _order(), egress_ip=REGISTERED_IP, now=_NOW, white_box=False, market_open_fn=_open
    )
    assert not d.allowed
    assert "white-box" in d.reason


def test_third_order_in_a_second_blocked() -> None:
    gate = _gate()
    d1 = _check(gate, _order(), _NOW)
    d2 = _check(gate, _order(), _NOW + timedelta(milliseconds=100))
    d3 = _check(gate, _order(), _NOW + timedelta(milliseconds=200))
    assert d1.allowed and d2.allowed
    assert not d3.allowed and not d3.halt  # throttled, not halted
    assert "throttle" in d3.reason


def test_rate_recovers_after_a_second() -> None:
    gate = _gate()
    _check(gate, _order(), _NOW)
    _check(gate, _order(), _NOW + timedelta(milliseconds=100))
    later = _check(gate, _order(), _NOW + timedelta(seconds=1, milliseconds=1))
    assert later.allowed


def test_per_minute_tripwire_halts() -> None:
    # per_min=5, per_sec=2 (max allowed). Space orders 2s apart so the /sec throttle never fires;
    # the 6th within the minute trips the per-minute HALT.
    gov = RateGovernor(_cfg(max_orders_per_min=5))
    base = _NOW
    for i in range(5):
        assert gov.try_admit(base + timedelta(seconds=2 * i)).admitted
    tripped = gov.try_admit(base + timedelta(seconds=10))
    assert tripped.halt
    assert "per-minute" in tripped.reason


def test_equity_market_closed_rejected_via_real_calendar() -> None:
    # Republic Day 11:00 IST -> equity closed. Uses the real calendar (default market_open_fn).
    from icarus.common.calendar import IST

    holiday_11am = datetime(2026, 1, 26, 11, 0, tzinfo=IST).astimezone(UTC)
    equity_order = _order().model_copy(update={"asset_class": AssetClass.EQUITY})
    d = _gate().check_order(equity_order, egress_ip=REGISTERED_IP, now=holiday_11am, white_box=True)
    assert not d.allowed
    assert "market closed" in d.reason
