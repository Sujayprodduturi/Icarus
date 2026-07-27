"""Postgres state models (task 0.4, PRD §9.3, §19).

The state store is the source of truth for positions, trades, the strategy registry,
hypotheses, metrics, and the append-only audit log (which doubles as the tax ledger, §6/§19).

The ``audit_log`` table is **append-only**, enforced at the DB level (a trigger blocking
UPDATE/DELETE) in the Alembic migration — not by convention. See ``state/migrations``.
Timestamps are ``timezone=True`` and stored UTC (invariant #22).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utc_col() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class Position(Base):
    """Current open positions (internal truth; reconciled against broker each cycle, §35.1)."""

    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    average_price: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    opened_at: Mapped[datetime] = _utc_col()

    __table_args__ = (Index("ix_positions_symbol", "symbol"),)


class Trade(Base):
    """Closed/settled trades — the per-trade record feeding P&L, metrics, and the tax ledger."""

    __tablename__ = "trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False)
    asset_class: Mapped[str] = mapped_column(String(16), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    entry_price: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(30, 10), nullable=True)
    opened_at: Mapped[datetime] = _utc_col()
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (Index("ix_trades_strategy", "strategy_id"),)


class Strategy(Base):
    """Versioned strategy registry — the ONLY bridge between planes (invariant #3, §13)."""

    __tablename__ = "strategies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False)  # lifecycle state (§34.1)
    spec: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)  # white-box DSL spec
    created_at: Mapped[datetime] = _utc_col()

    hypotheses: Mapped[list[Hypothesis]] = relationship(back_populates="strategy")

    __table_args__ = (Index("ix_strategies_id_version", "strategy_id", "version", unique=True),)


class Hypothesis(Base):
    """Inventor hypothesis -> verdict -> live outcome (meta-learning store, §12.3)."""

    __tablename__ = "hypotheses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_pk: Mapped[int | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    predicted_delta: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    verdict: Mapped[str | None] = mapped_column(String(24), nullable=True)
    created_at: Mapped[datetime] = _utc_col()

    strategy: Mapped[Strategy | None] = relationship(back_populates="hypotheses")


class Metric(Base):
    """Per-strategy metric snapshots (the gate's metric sheet + live rolling metrics, §13.2)."""

    __tablename__ = "metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    strategy_id: Mapped[str] = mapped_column(String(128), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    value: Mapped[Decimal] = mapped_column(Numeric(30, 10), nullable=False)
    computed_at: Mapped[datetime] = _utc_col()

    __table_args__ = (Index("ix_metrics_strategy_name", "strategy_id", "name"),)


class AuditLog(Base):
    """Append-only audit trail: every decision/order/fill/veto/halt/diff/hypothesis/verdict.

    Retained >= 5 years (SEBI, §19); also the tax/Schedule-VDA ledger. UPDATE and DELETE are
    blocked by a DB trigger in the migration — appends only.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(48), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = _utc_col()

    __table_args__ = (
        Index("ix_audit_event_type", "event_type"),
        Index("ix_audit_correlation", "correlation_id"),
    )
