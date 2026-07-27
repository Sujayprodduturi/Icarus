"""Read-only adapter tests (tasks 0.7/0.8/0.9).

The load-bearing Phase-0 guarantee: every adapter's write methods RAISE (invariant #11). Plus
read-path normalization with injected fakes, and Delta's HMAC signer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from icarus.brokers.base import WriteNotEnabledError
from icarus.brokers.delta_india import DeltaIndiaAdapter, delta_signature
from icarus.brokers.upstox import UpstoxAdapter
from icarus.brokers.zerodha import ZerodhaAdapter
from icarus.common.types import AssetClass, OrderSide, OrderType, SizedOrder


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


# --- Zerodha ------------------------------------------------------------------------
class _FakeKite:
    def generate_session(self, request_token: str, api_secret: str) -> dict[str, Any]:
        return {"access_token": "tok123"}

    def set_access_token(self, access_token: str) -> None:
        self.token = access_token

    def historical_data(
        self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str
    ) -> list[dict[str, Any]]:
        return [
            {
                "date": datetime(2026, 7, 27, tzinfo=UTC),
                "open": 100,
                "high": 110,
                "low": 99,
                "close": 105,
                "volume": 1000,
            }
        ]

    def positions(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "net": [
                {
                    "tradingsymbol": "INFY",
                    "quantity": 5,
                    "average_price": 101.5,
                    "last_price": 106.0,
                }
            ]
        }

    def margins(self) -> dict[str, Any]:
        return {"equity": {"available": {"cash": 5000}, "utilised": {"debits": 200}}}


def _zerodha() -> ZerodhaAdapter:
    return ZerodhaAdapter("k", "s", _FakeKite(), token_map={"INFY": 408065})


@pytest.mark.asyncio
async def test_zerodha_authenticate() -> None:
    sess = await _zerodha().authenticate("req")
    assert sess.authenticated and sess.broker == "zerodha"


@pytest.mark.asyncio
async def test_zerodha_historical_normalizes() -> None:
    candles = await _zerodha().historical(
        "INFY", "day", datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 27, tzinfo=UTC)
    )
    assert candles[0].ohlcv.close == Decimal("105")


@pytest.mark.asyncio
async def test_zerodha_unknown_symbol_raises() -> None:
    with pytest.raises(KeyError):
        await _zerodha().historical(
            "UNKNOWN", "day", datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 27, tzinfo=UTC)
        )


@pytest.mark.asyncio
async def test_zerodha_positions_and_funds() -> None:
    z = _zerodha()
    pos = await z.positions()
    assert pos[0].symbol == "INFY" and pos[0].quantity == Decimal("5")
    funds = await z.funds()
    assert funds.available_cash == Decimal("5000")


@pytest.mark.asyncio
async def test_zerodha_write_methods_raise() -> None:
    z = _zerodha()
    for coro in (z.place(_order()), z.modify("o"), z.cancel("o"), z.kill_switch()):
        with pytest.raises(WriteNotEnabledError):
            await coro


# --- Delta India --------------------------------------------------------------------
def test_delta_signature_is_deterministic() -> None:
    a = delta_signature("secret", "GET", "1700000000", "/v2/profile", "", "")
    b = delta_signature("secret", "GET", "1700000000", "/v2/profile", "", "")
    assert a == b and len(a) == 64  # sha256 hex


def test_delta_signature_changes_with_timestamp() -> None:
    # A different timestamp -> different signature (why the 5s window matters).
    a = delta_signature("secret", "GET", "1700000000", "/v2/profile", "", "")
    b = delta_signature("secret", "GET", "1700000005", "/v2/profile", "", "")
    assert a != b


class _FakeDeltaHttp:
    def __init__(self) -> None:
        self.last_headers: dict[str, str] = {}

    async def get(self, path: str, *, headers: dict[str, str]) -> dict[str, Any]:
        self.last_headers = headers
        if "positions" in path:
            return {"result": [{"product_symbol": "BTCUSD", "size": 2, "entry_price": 5000000}]}
        if "balances" in path:
            return {"result": [{"available_balance": 10000}]}
        return {"result": {}}


@pytest.mark.asyncio
async def test_delta_authenticate_signs_request() -> None:
    http = _FakeDeltaHttp()
    adapter = DeltaIndiaAdapter("key", "secret", http, now_fn=lambda: 1700000000.0)
    await adapter.authenticate()
    assert http.last_headers["api-key"] == "key"
    assert http.last_headers["timestamp"] == "1700000000"
    assert len(http.last_headers["signature"]) == 64


@pytest.mark.asyncio
async def test_delta_positions_crypto() -> None:
    adapter = DeltaIndiaAdapter("key", "secret", _FakeDeltaHttp())
    pos = await adapter.positions()
    assert pos[0].asset_class is AssetClass.CRYPTO
    assert pos[0].quantity == Decimal("2")


@pytest.mark.asyncio
async def test_delta_write_methods_raise() -> None:
    adapter = DeltaIndiaAdapter("key", "secret", _FakeDeltaHttp())
    with pytest.raises(WriteNotEnabledError):
        await adapter.place(_order())


# --- Upstox -------------------------------------------------------------------------
class _FakeUpstox:
    def get_historical_candle(self, symbol: str, interval: str) -> list[dict[str, Any]]:
        return [
            {
                "ts": datetime(2026, 7, 27, tzinfo=UTC),
                "open": 1,
                "high": 2,
                "low": 1,
                "close": 2,
                "volume": 10,
            }
        ]


@pytest.mark.asyncio
async def test_upstox_historical_backup_feed() -> None:
    candles = await UpstoxAdapter(_FakeUpstox()).historical(
        "INFY", "day", datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 27, tzinfo=UTC)
    )
    assert candles[0].ohlcv.close == Decimal("2")


@pytest.mark.asyncio
async def test_upstox_write_methods_raise() -> None:
    adapter = UpstoxAdapter(_FakeUpstox())
    with pytest.raises(WriteNotEnabledError):
        await adapter.place(_order())
