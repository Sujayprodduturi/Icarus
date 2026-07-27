"""Upstox adapter — STUB, data-only in Phase 0 (task 0.9, PRD §11.3).

Upstox is the failover equities venue + free backup data feed. Data endpoints are IP-exempt, so
it doubles as a zero-cost backup market-data source if Zerodha's stream drops. Order methods RAISE
via ReadOnlyBrokerAdapter (invariant #11); post-Mar-2026 order pricing is unpublished anyway
(§11.3), so Upstox is data/failover only until verified.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from decimal import Decimal
from typing import Any, Protocol

from icarus.brokers.base import ReadOnlyBrokerAdapter
from icarus.common.types import OHLCV, Candle, Funds, MarketData, Position, Session


class UpstoxClient(Protocol):
    """The read-only data slice of the Upstox SDK the adapter uses (injectable for tests)."""

    def get_historical_candle(self, symbol: str, interval: str) -> list[dict[str, Any]]: ...


class UpstoxAdapter(ReadOnlyBrokerAdapter):
    """Upstox failover/data adapter (data-only stub in Phase 0)."""

    _BROKER = "upstox"

    def __init__(self, client: UpstoxClient) -> None:
        self._client = client

    async def authenticate(self) -> Session:
        # Data endpoints don't need the daily order-auth; a data session is always "authenticated".
        return Session(broker=self._BROKER, authenticated=True)

    def stream_quotes(self, symbols: list[str]) -> AsyncIterator[MarketData]:
        """Backup live feed — wired in Phase 4 failover drills (task O2)."""
        raise NotImplementedError(f"stream_quotes({symbols}) wired in Phase 4 failover (task O2)")

    async def historical(self, symbol: str, tf: str, frm: datetime, to: datetime) -> list[Candle]:
        rows = self._client.get_historical_candle(symbol, tf)
        return [
            Candle(
                ts=row["ts"],
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
        return []  # failover/data only in Phase 0

    async def funds(self) -> Funds:
        return Funds(available_cash=Decimal(0))
