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
from uuid import UUID

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    Uuid,
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


class TrialLedgerActivation(Base):
    """One immutable row switches the lifetime count from legacy JSON to PostgreSQL."""

    __tablename__ = "trial_ledger_activation"

    id: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    legacy_schema: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_entry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    legacy_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    activated_at: Mapped[datetime] = _utc_col()

    __table_args__ = (
        CheckConstraint("id = 1", name="ck_trial_activation_singleton"),
        CheckConstraint("legacy_schema = 1", name="ck_trial_activation_schema"),
        CheckConstraint("legacy_entry_count >= 0", name="ck_trial_activation_count"),
    )


class TrialBatch(Base):
    """Immutable pre-evaluation reservation for one counted run group."""

    __tablename__ = "trial_batches"

    run_group_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    reservation_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source: Mapped[str] = mapped_column(String(24), nullable=False)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    strategy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    strategy_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    panel_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    config_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primitives: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    expected_evaluations: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_at: Mapped[datetime] = _utc_col()

    __table_args__ = (
        CheckConstraint("origin IN ('operator','inventor')", name="ck_trial_batch_origin"),
        CheckConstraint("source IN ('native','legacy_json_v1')", name="ck_trial_batch_source"),
        CheckConstraint("expected_evaluations > 0", name="ck_trial_batch_expected"),
        CheckConstraint(
            "source <> 'native' OR "
            "(strategy_sha256 IS NOT NULL AND panel_sha256 IS NOT NULL "
            "AND config_sha256 IS NOT NULL)",
            name="ck_trial_batch_native_hashes",
        ),
        Index("ix_trial_batches_reserved_at", "reserved_at"),
    )


class TrialEvaluation(Base):
    """One raw counted trial within a reserved run group."""

    __tablename__ = "trial_evaluations"

    evaluation_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    run_group_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trial_batches.run_group_id"), nullable=False
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    fold_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_index_exclusive: Mapped[int | None] = mapped_column(Integer, nullable=True)
    start_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reset_identity: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("run_group_id", "ordinal", name="uq_trial_evaluation_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_trial_evaluation_ordinal"),
        CheckConstraint(
            "kind IN ('portfolio','signal_full','signal_fold')", name="ck_trial_evaluation_kind"
        ),
        CheckConstraint(
            "(start_index IS NULL AND end_index_exclusive IS NULL "
            "AND start_ts IS NULL AND end_ts IS NULL) OR "
            "(start_index >= 0 AND end_index_exclusive > start_index "
            "AND start_ts IS NOT NULL AND end_ts IS NOT NULL AND end_ts >= start_ts)",
            name="ck_trial_evaluation_span",
        ),
        CheckConstraint(
            "(kind = 'signal_fold' AND ordinal >= 1 AND fold_index = ordinal - 1) OR "
            "(kind <> 'signal_fold' AND fold_index IS NULL)",
            name="ck_trial_evaluation_fold",
        ),
    )


class TrialResult(Base):
    """Result rows arrive as one complete transaction after evaluation."""

    __tablename__ = "trial_results"

    evaluation_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trial_evaluations.evaluation_id"), primary_key=True
    )
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    oos_sharpe: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    oos_sharpe_after_tax: Mapped[Decimal | None] = mapped_column(Numeric(), nullable=True)
    observation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    recorded_at: Mapped[datetime] = _utc_col()

    __table_args__ = (
        CheckConstraint("observation_count >= 0", name="ck_trial_result_observations"),
    )


class TrialBatchTerminal(Base):
    """Exactly one immutable terminal: complete full batch or known failure."""

    __tablename__ = "trial_batch_terminals"

    run_group_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("trial_batches.run_group_id"), primary_key=True
    )
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    results_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    recorded_at: Mapped[datetime] = _utc_col()

    __table_args__ = (
        CheckConstraint("state IN ('completed','failed')", name="ck_trial_terminal_state"),
        CheckConstraint(
            "(state = 'completed' AND results_sha256 IS NOT NULL AND failure_code IS NULL) OR "
            "(state = 'failed' AND results_sha256 IS NULL AND failure_code IS NOT NULL)",
            name="ck_trial_terminal_shape",
        ),
        Index("ix_trial_batch_terminals_state", "state"),
    )
