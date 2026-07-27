"""Delta Exchange India adapter — READ-ONLY, TESTNET in Phase 0 (task 0.8, PRD §11.4).

INR-settled crypto derivatives only (never spot, never USDT-settled — PRD §6). Writes RAISE via
ReadOnlyBrokerAdapter (invariant #11). The live testnet smoke test is deferred (operator item O3).

Auth is HMAC-SHA256 over (method + timestamp + path + query + body); the signature is valid only
5s (PRD §11.4). The signer is pure and unit-tested; HTTP is delegated to an injected async client.
"""

from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Callable
from decimal import Decimal
from typing import Any, Protocol

from icarus.brokers.base import ReadOnlyBrokerAdapter
from icarus.common.types import AssetClass, Funds, Position, Session

TESTNET_BASE = "https://cdn-ind.testnet.deltaex.org"
PROD_BASE = "https://api.india.delta.exchange"


def delta_signature(
    api_secret: str, method: str, timestamp: str, path: str, query: str, body: str
) -> str:
    """HMAC-SHA256 signature per Delta's scheme. Pure — the security-critical, tested core."""
    message = f"{method}{timestamp}{path}{query}{body}"
    return hmac.new(api_secret.encode(), message.encode(), hashlib.sha256).hexdigest()


class DeltaHttp(Protocol):
    """Minimal async HTTP surface the adapter needs (lets tests inject a fake)."""

    async def get(self, path: str, *, headers: dict[str, str]) -> dict[str, Any]: ...


class DeltaIndiaAdapter(ReadOnlyBrokerAdapter):
    """Delta India crypto adapter (read-only testnet in Phase 0)."""

    _BROKER = "delta_india"

    def __init__(
        self,
        api_key: str,
        api_secret: str,
        http: DeltaHttp,
        *,
        base_url: str = TESTNET_BASE,
        now_fn: Callable[[], float] = time.time,
    ) -> None:
        self._api_key = api_key
        self._api_secret = api_secret
        self._http = http
        self._base_url = base_url
        # injectable clock for deterministic signature tests; defaults to real time.
        self._now_fn = now_fn

    def _auth_headers(
        self, method: str, path: str, query: str = "", body: str = ""
    ) -> dict[str, str]:
        ts = str(int(self._now_fn()))
        sig = delta_signature(self._api_secret, method, ts, path, query, body)
        return {"api-key": self._api_key, "timestamp": ts, "signature": sig}

    async def authenticate(self) -> Session:
        """Validate keys by reading an authenticated endpoint. HMAC keys, no daily OAuth token."""
        headers = self._auth_headers("GET", "/v2/profile")
        await self._http.get(f"{self._base_url}/v2/profile", headers=headers)
        return Session(broker=self._BROKER, authenticated=True)

    async def positions(self) -> list[Position]:
        headers = self._auth_headers("GET", "/v2/positions")
        data = await self._http.get(f"{self._base_url}/v2/positions", headers=headers)
        return [
            Position(
                symbol=p["product_symbol"],
                asset_class=AssetClass.CRYPTO,
                quantity=Decimal(str(p["size"])),
                average_price=Decimal(str(p["entry_price"])),
            )
            for p in data.get("result", [])
        ]

    async def funds(self) -> Funds:
        headers = self._auth_headers("GET", "/v2/wallet/balances")
        data = await self._http.get(f"{self._base_url}/v2/wallet/balances", headers=headers)
        balances = data.get("result", [])
        cash = balances[0]["available_balance"] if balances else 0
        return Funds(account_currency="INR", available_cash=Decimal(str(cash)))
