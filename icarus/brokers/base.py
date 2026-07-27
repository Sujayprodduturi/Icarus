"""The broker-agnostic execution contract (PRD §11.1).

Every venue (Zerodha, Upstox, Delta India) implements :class:`BrokerAdapter`. Nothing above
this line hard-couples to a broker (CLAUDE.md §2). This module is a *contract only* — no
concrete logic (Phase 0 task 0.6 AC: protocol type-checks, mypy clean).

Money-path invariants this contract exists to protect:

* ``place`` MUST attach the exchange algo-ID and place LIMIT-with-protection, never MARKET
  (invariants #5, #6). In Phase 0 every adapter's write methods raise (see
  :class:`ReadOnlyBrokerAdapter`).
* Only the Execution agent ever holds a write-capable adapter (invariant #2).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from icarus.common.types import (
    Candle,
    Funds,
    MarketData,
    OrderResult,
    Position,
    Session,
    SizedOrder,
)


@runtime_checkable
class BrokerAdapter(Protocol):
    """Broker-agnostic execution + data interface. See PRD §11.1."""

    async def authenticate(self) -> Session:
        """OAuth + 2FA + daily token (equities) or HMAC key validation (crypto)."""
        ...

    def stream_quotes(self, symbols: list[str]) -> AsyncIterator[MarketData]:
        """Live normalized market data. Data endpoints are static-IP-exempt (PRD §8)."""
        ...

    async def historical(self, symbol: str, tf: str, frm: datetime, to: datetime) -> list[Candle]:
        """Historical OHLCV for backtests. Respect venue rate limits (Kite historical 3/s)."""
        ...

    async def place(self, order: SizedOrder) -> OrderResult:
        """Place an order — tags algo-ID, LIMIT + marketable protection (never MARKET).

        WRITE credential path. Phase 0 adapters raise ``NotImplementedError`` here.
        """
        ...

    async def modify(self, order_id: str, **kwargs: object) -> OrderResult:
        """Modify a resting order. WRITE path — raises in Phase 0."""
        ...

    async def cancel(self, order_id: str) -> OrderResult:
        """Cancel a resting order. WRITE path — raises in Phase 0."""
        ...

    async def positions(self) -> list[Position]:
        """Current broker-truth positions (read). Feeds reconciliation (PRD §35.1)."""
        ...

    async def funds(self) -> Funds:
        """Available cash / margin (read)."""
        ...

    async def kill_switch(self) -> None:
        """Broker-native kill where available (Delta yes; Kite has none — enforced in-app, §14)."""
        ...


class WriteNotEnabledError(NotImplementedError):
    """Raised by any read-only adapter when an order-placement method is called.

    Phase 0 has **no live order path** (invariant #11). This error IS the enforcement:
    a write method that raises cannot place, modify, or cancel anything.
    """


class ReadOnlyBrokerAdapter:
    """Mixin giving an adapter Phase-0-safe write methods that always raise.

    Concrete adapters (Zerodha, Delta, Upstox) inherit this so ``place``/``modify``/``cancel``/
    ``kill_switch`` raise :class:`WriteNotEnabledError` until Phase 2 promotes them. Keeping the
    raise in one place makes "can place nothing" a single, testable guarantee.
    """

    _BROKER: str = "read-only"

    async def place(self, order: SizedOrder) -> OrderResult:
        raise WriteNotEnabledError(
            f"{self._BROKER}: order placement is disabled in Phase 0 (invariant #11)"
        )

    async def modify(self, order_id: str, **kwargs: object) -> OrderResult:
        raise WriteNotEnabledError(
            f"{self._BROKER}: order modification is disabled in Phase 0 (invariant #11)"
        )

    async def cancel(self, order_id: str) -> OrderResult:
        raise WriteNotEnabledError(
            f"{self._BROKER}: order cancellation is disabled in Phase 0 (invariant #11)"
        )

    async def kill_switch(self) -> None:
        raise WriteNotEnabledError(
            f"{self._BROKER}: broker-native kill is disabled in Phase 0 (invariant #11)"
        )
