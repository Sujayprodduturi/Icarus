"""Zerodha Kite adapter — READ-ONLY in Phase 0 (task 0.7, PRD §11.2).

Reads: authenticate, historical, positions, funds (stream_quotes wired to the live KiteTicker in
Phase 1's Data agent). Writes (place/modify/cancel/kill_switch) RAISE via ReadOnlyBrokerAdapter —
Phase 0 has no order path (invariant #11).

The Kite client is injected so the read paths are unit-testable without live creds. The PyPI
package is ``kiteconnect`` (NOT pykiteconnect); the client is synchronous, so its calls are wrapped
with ``asyncio.to_thread`` to avoid blocking the event loop.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from icarus.brokers.base import ReadOnlyBrokerAdapter
from icarus.common.types import (
    OHLCV,
    AssetClass,
    Candle,
    Funds,
    MarketData,
    Position,
    Session,
)


class KiteClient(Protocol):
    """The slice of kiteconnect.KiteConnect the adapter uses (lets tests inject a fake)."""

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, Any]: ...
    def set_access_token(self, access_token: str) -> None: ...
    def historical_data(
        self, instrument_token: int, from_date: datetime, to_date: datetime, interval: str
    ) -> list[dict[str, Any]]: ...
    def positions(self) -> dict[str, list[dict[str, Any]]]: ...
    def margins(self) -> dict[str, Any]: ...


class ZerodhaAdapter(ReadOnlyBrokerAdapter):
    """Zerodha equities adapter (read-only in Phase 0)."""

    _BROKER = "zerodha"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        client: KiteClient,
        token_map: dict[str, int] | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._client = client
        # tradingsymbol -> instrument token. The full instrument dump loads in the Data agent
        # (Phase 1, task 1.1); Phase 0 accepts an explicit map so historical() is testable.
        self._token_map = token_map or {}

    async def authenticate(self, request_token: str = "") -> Session:
        """Exchange a request token for a daily access token (Kite token expires ~6 AM next day)."""
        data = await asyncio.to_thread(
            self._client.generate_session, request_token, self._api_secret
        )
        await asyncio.to_thread(self._client.set_access_token, data["access_token"])
        return Session(broker=self._BROKER, authenticated=True)

    def stream_quotes(self, symbols: list[str]) -> AsyncIterator[MarketData]:
        """Live quotes via KiteTicker — wired in Phase 1's Data agent (needs live creds)."""
        raise NotImplementedError(f"stream_quotes({symbols}) wired in Phase 1 (task 1.1)")

    async def historical(self, symbol: str, tf: str, frm: datetime, to: datetime) -> list[Candle]:
        token = self._token_map.get(symbol)
        if token is None:
            raise KeyError(f"no instrument token for {symbol!r} (load the dump in the Data agent)")
        rows = await asyncio.to_thread(self._client.historical_data, token, frm, to, tf)
        return [
            Candle(
                ts=row["date"],
                ohlcv=OHLCV(
                    open=Decimal(str(row["open"])),
                    high=Decimal(str(row["high"])),
                    low=Decimal(str(row["low"])),
                    close=Decimal(str(row["close"])),
                    volume=Decimal(str(row["volume"])),
                ),
            )
            for row in rows
        ]

    async def positions(self) -> list[Position]:
        data = await asyncio.to_thread(self._client.positions)
        return [
            Position(
                symbol=p["tradingsymbol"],
                asset_class=AssetClass.EQUITY,
                quantity=Decimal(str(p["quantity"])),
                average_price=Decimal(str(p["average_price"])),
                last_price=Decimal(str(p["last_price"])),
            )
            for p in data.get("net", [])
        ]

    async def funds(self) -> Funds:
        margins = await asyncio.to_thread(self._client.margins)
        equity = margins.get("equity", {})
        return Funds(
            available_cash=Decimal(str(equity.get("available", {}).get("cash", 0))),
            used_margin=Decimal(str(equity.get("utilised", {}).get("debits", 0))),
        )
