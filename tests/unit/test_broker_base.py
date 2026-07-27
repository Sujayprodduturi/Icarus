"""Tests for the BrokerAdapter contract + the Phase-0 read-only write-raising (tasks 0.6, 0.7-0.9).

The four write methods raising IS the Phase-0 "can place nothing" guarantee (invariant #11).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from icarus.brokers.base import (
    BrokerAdapter,
    ReadOnlyBrokerAdapter,
    WriteNotEnabledError,
)
from icarus.common.types import AssetClass, OrderSide, OrderType, SizedOrder


class _RO(ReadOnlyBrokerAdapter):
    _BROKER = "test-ro"


def _sized_order() -> SizedOrder:
    return SizedOrder(
        client_order_id="cid-1",
        strategy_id="strat-1",
        symbol="INFY",
        asset_class=AssetClass.EQUITY,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(1),
        limit_price=Decimal("1500.00"),
    )


@pytest.mark.asyncio
async def test_place_raises() -> None:
    with pytest.raises(WriteNotEnabledError, match="invariant #11"):
        await _RO().place(_sized_order())


@pytest.mark.asyncio
async def test_modify_raises() -> None:
    with pytest.raises(WriteNotEnabledError):
        await _RO().modify("oid-1")


@pytest.mark.asyncio
async def test_cancel_raises() -> None:
    with pytest.raises(WriteNotEnabledError):
        await _RO().cancel("oid-1")


@pytest.mark.asyncio
async def test_kill_switch_raises() -> None:
    with pytest.raises(WriteNotEnabledError):
        await _RO().kill_switch()


def test_write_not_enabled_is_notimplemented() -> None:
    # Subclass of NotImplementedError so generic handlers still treat it as "not available".
    assert issubclass(WriteNotEnabledError, NotImplementedError)


def test_sized_order_rejects_nonpositive_qty() -> None:
    with pytest.raises(ValueError, match="positive"):
        SizedOrder(
            client_order_id="c",
            strategy_id="s",
            symbol="INFY",
            asset_class=AssetClass.EQUITY,
            side=OrderSide.BUY,
            quantity=Decimal(0),
            limit_price=Decimal("100"),
        )


def test_readonly_adapter_is_not_full_broker_adapter() -> None:
    # A bare ReadOnlyBrokerAdapter lacks the read methods, so it is NOT a complete BrokerAdapter.
    # (Concrete adapters add authenticate/stream_quotes/etc. and then satisfy the Protocol.)
    assert not isinstance(_RO(), BrokerAdapter)
