"""Phase-0 exit proof: the system can place NOTHING (invariant #11, PRD §22 Phase-0 gate).

Two independent proofs:

1. **Static scan** — no module under ``icarus/`` contains a real broker order-placement call
   (place_order / create_order / /v2/orders / bracket, etc.). Phase 0 has no order path *by
   construction*; this test fails loudly if one is ever added before Phase 2 intentionally does so.
2. **Behavioral** — every concrete BrokerAdapter's place/modify/cancel/kill_switch RAISE.

Together these turn "we're careful" into "the build won't pass if an order path exists."
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from icarus.brokers.base import WriteNotEnabledError
from icarus.brokers.delta_india import DeltaIndiaAdapter
from icarus.brokers.upstox import UpstoxAdapter
from icarus.brokers.zerodha import ZerodhaAdapter
from icarus.common.types import AssetClass, OrderSide, OrderType, SizedOrder

ICARUS_SRC = Path(__file__).resolve().parent.parent.parent / "icarus"

# Real broker order-placement API calls. NOT our own method names (place/modify/cancel are the
# raise-stubs); these are the actual venue SDK/REST endpoints that would send an order.
FORBIDDEN_ORDER_CALLS = (
    "place_order",
    "modify_order",
    "cancel_order",
    "create_order",
    "create_limit_order",
    "/v2/orders",
    "/orders/bracket",
)


def test_no_order_placement_call_anywhere() -> None:
    offenders: list[str] = []
    for py in ICARUS_SRC.rglob("*.py"):
        text = py.read_text(encoding="utf-8")
        for pattern in FORBIDDEN_ORDER_CALLS:
            if pattern in text:
                offenders.append(f"{py.relative_to(ICARUS_SRC.parent)}: {pattern!r}")
    assert not offenders, "order-placement call found in Phase 0 (invariant #11):\n" + "\n".join(
        offenders
    )


# --- behavioral: every adapter's write methods raise --------------------------------
class _NullClient:
    """Stand-in client — never used, since writes raise before touching it."""

    def __getattr__(self, _name: str) -> object:
        raise AssertionError("read client must not be called by a write method")


def _order() -> SizedOrder:
    return SizedOrder(
        client_order_id="c1",
        strategy_id="s1",
        symbol="INFY",
        asset_class=AssetClass.EQUITY,
        side=OrderSide.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal(1),
        limit_price=Decimal("100"),
    )


def _adapters() -> list[object]:
    client: Any = _NullClient()  # never called (writes raise first); Any fits every adapter
    return [
        ZerodhaAdapter("k", "s", client),
        DeltaIndiaAdapter("k", "s", client),
        UpstoxAdapter(client),
    ]


@pytest.mark.asyncio
async def test_every_adapter_write_raises() -> None:
    for adapter in _adapters():
        with pytest.raises(WriteNotEnabledError):
            await adapter.place(_order())  # type: ignore[attr-defined]
        with pytest.raises(WriteNotEnabledError):
            await adapter.modify("o")  # type: ignore[attr-defined]
        with pytest.raises(WriteNotEnabledError):
            await adapter.cancel("o")  # type: ignore[attr-defined]
        with pytest.raises(WriteNotEnabledError):
            await adapter.kill_switch()  # type: ignore[attr-defined]
