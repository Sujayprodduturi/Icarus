"""Shared domain types for Icarus (broker-agnostic).

These are the contracts the :class:`~icarus.brokers.base.BrokerAdapter` speaks and the
execution plane passes around. Kept broker-neutral so no venue detail leaks upward
(CLAUDE.md §2: one responsibility per module; type everything).

Money-path safety notes baked into the types:

* :class:`OrderType` can *represent* MARKET, but the Compliance agent rejects it — NSE bars
  market orders via algo, so Execution places marketable-LIMIT only (invariant #5, PRD §8).
* :class:`AssetClass` distinguishes equity vs crypto so tax/leverage rules pick the right path.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, field_validator

from icarus.common.schemas import Msg


class AssetClass(enum.StrEnum):
    EQUITY = "equity"
    CRYPTO = "crypto"


class Plane(enum.StrEnum):
    """The two independent state machines (PRD §9.5).

    Equity sleeps outside NSE hours; crypto is 24/7.
    """

    EQUITY = "equity"
    CRYPTO = "crypto"


class OrderSide(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(enum.StrEnum):
    """Order types. LIMIT is the only type Execution may place (invariant #5).

    MARKET exists so the Compliance layer has something to *reject*; it is never sent.
    """

    LIMIT = "limit"
    MARKET = "market"  # forbidden on the live path — Compliance rejects (PRD §8, §14)


class OrderStatus(enum.StrEnum):
    PENDING = "pending"
    OPEN = "open"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# --------------------------------------------------------------------------------------
# Market data (bus message)
# --------------------------------------------------------------------------------------
class OHLCV(BaseModel):
    model_config = ConfigDict(frozen=True)
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class MarketData(Msg):
    """Canonical normalized market data (PRD §10, agent #1). One schema across all venues."""

    SCHEMA_VERSION = "1.0"
    symbol: str
    asset_class: AssetClass
    ohlcv: OHLCV
    # depth is venue-specific and optional at Phase 0; modeled as a shallow bid/ask list later.
    depth: tuple[tuple[Decimal, Decimal], ...] | None = None


class Candle(BaseModel):
    """A single historical OHLCV bar (result of ``BrokerAdapter.historical``)."""

    model_config = ConfigDict(frozen=True)
    ts: datetime
    ohlcv: OHLCV

    @field_validator("ts")
    @classmethod
    def _ts_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("Candle.ts must be tz-aware UTC (PRD §29.5)")
        return v.astimezone(UTC)


# --------------------------------------------------------------------------------------
# Order / position / account types
# --------------------------------------------------------------------------------------
class SizedOrder(BaseModel):
    """An order the Risk agent has sized and approved, ready for Compliance + Execution.

    ``client_order_id`` is the deterministic UUID v5 of (strategy_id, signal_id, bar_ts) that
    makes orders exactly-once across restarts/redelivery (PRD §35.2, invariant #15). It is set
    upstream; the type carries it so Execution can scan broker history before sending.
    """

    model_config = ConfigDict(frozen=True)

    client_order_id: str
    strategy_id: str
    symbol: str
    asset_class: AssetClass
    side: OrderSide
    order_type: OrderType = OrderType.LIMIT
    quantity: Decimal
    limit_price: Decimal
    # Protective stop at the broker (bracket/GTT). Required for a live open position (§35.1).
    stop_loss: Decimal | None = None
    target: Decimal | None = None
    algo_id: str | None = None  # exchange-required tag, attached by Execution (invariant #6)

    @field_validator("quantity", "limit_price")
    @classmethod
    def _must_be_positive(cls, v: Decimal) -> Decimal:
        if v <= 0:
            raise ValueError("quantity and limit_price must be positive")
        return v


class OrderResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    client_order_id: str
    broker_order_id: str | None
    status: OrderStatus
    filled_quantity: Decimal = Decimal(0)
    average_price: Decimal | None = None
    message: str | None = None


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str
    asset_class: AssetClass
    quantity: Decimal
    average_price: Decimal
    last_price: Decimal | None = None


class Funds(BaseModel):
    model_config = ConfigDict(frozen=True)
    account_currency: str = "INR"
    available_cash: Decimal
    used_margin: Decimal = Decimal(0)


class Session(BaseModel):
    """Result of ``BrokerAdapter.authenticate`` — a daily broker session (PRD §11.1)."""

    model_config = ConfigDict(frozen=True)
    broker: str
    authenticated: bool
    # Kite access_token expires ~6 AM next day (regulatory); crypto uses HMAC keys, no daily token.
    expires_at: datetime | None = None

    @field_validator("expires_at")
    @classmethod
    def _exp_utc_aware(cls, v: datetime | None) -> datetime | None:
        if v is not None and v.tzinfo is None:
            raise ValueError("Session.expires_at must be tz-aware UTC")
        return v.astimezone(UTC) if v is not None else None
