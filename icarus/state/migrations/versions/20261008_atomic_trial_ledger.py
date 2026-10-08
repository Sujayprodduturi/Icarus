"""Atomic append-only lifetime trial ledger.

Revision ID: 20261008_trial_ledger
Revises: d8847faf5e20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261008_trial_ledger"
down_revision: str | None = "d8847faf5e20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "trial_ledger_activation",
        sa.Column("id", sa.SmallInteger(), primary_key=True),
        sa.Column("legacy_schema", sa.Integer(), nullable=False),
        sa.Column("legacy_entry_count", sa.Integer(), nullable=False),
        sa.Column("legacy_sha256", sa.String(64), nullable=False),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_trial_activation_singleton"),
        sa.CheckConstraint("legacy_schema = 1", name="ck_trial_activation_schema"),
        sa.CheckConstraint("legacy_entry_count >= 0", name="ck_trial_activation_count"),
    )
    op.create_table(
        "trial_batches",
        sa.Column("run_group_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reservation_sha256", sa.String(64), nullable=False),
        sa.Column("origin", sa.String(16), nullable=False),
        sa.Column("source", sa.String(24), nullable=False),
        sa.Column("strategy_name", sa.String(128), nullable=False),
        sa.Column("strategy_version", sa.Integer(), nullable=False),
        sa.Column("strategy_sha256", sa.String(64), nullable=True),
        sa.Column("panel_sha256", sa.String(64), nullable=True),
        sa.Column("config_sha256", sa.String(64), nullable=True),
        sa.Column("primitives", postgresql.JSONB(), nullable=False),
        sa.Column("expected_evaluations", sa.Integer(), nullable=False),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("origin IN ('operator','inventor')", name="ck_trial_batch_origin"),
        sa.CheckConstraint("source IN ('native','legacy_json_v1')", name="ck_trial_batch_source"),
        sa.CheckConstraint("expected_evaluations > 0", name="ck_trial_batch_expected"),
        sa.CheckConstraint(
            "source <> 'native' OR "
            "(strategy_sha256 IS NOT NULL AND panel_sha256 IS NOT NULL "
            "AND config_sha256 IS NOT NULL)",
            name="ck_trial_batch_native_hashes",
        ),
    )
    op.create_index("ix_trial_batches_reserved_at", "trial_batches", ["reserved_at"])
    op.create_table(
        "trial_evaluations",
        sa.Column("evaluation_id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "run_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trial_batches.run_group_id"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("fold_index", sa.Integer(), nullable=True),
        sa.Column("start_index", sa.Integer(), nullable=True),
        sa.Column("end_index_exclusive", sa.Integer(), nullable=True),
        sa.Column("start_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("end_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reset_identity", sa.String(64), nullable=False),
        sa.UniqueConstraint("run_group_id", "ordinal", name="uq_trial_evaluation_ordinal"),
        sa.CheckConstraint("ordinal >= 0", name="ck_trial_evaluation_ordinal"),
        sa.CheckConstraint(
            "kind IN ('portfolio','signal_full','signal_fold')", name="ck_trial_evaluation_kind"
        ),
        sa.CheckConstraint(
            "(start_index IS NULL AND end_index_exclusive IS NULL "
            "AND start_ts IS NULL AND end_ts IS NULL) OR "
            "(start_index >= 0 AND end_index_exclusive > start_index "
            "AND start_ts IS NOT NULL AND end_ts IS NOT NULL AND end_ts >= start_ts)",
            name="ck_trial_evaluation_span",
        ),
        sa.CheckConstraint(
            "(kind = 'signal_fold' AND ordinal >= 1 AND fold_index = ordinal - 1) OR "
            "(kind <> 'signal_fold' AND fold_index IS NULL)",
            name="ck_trial_evaluation_fold",
        ),
    )
    op.create_table(
        "trial_results",
        sa.Column(
            "evaluation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trial_evaluations.evaluation_id"),
            primary_key=True,
        ),
        sa.Column("result_sha256", sa.String(64), nullable=False),
        sa.Column("oos_sharpe", sa.Numeric(), nullable=True),
        sa.Column("oos_sharpe_after_tax", sa.Numeric(), nullable=True),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("observation_count >= 0", name="ck_trial_result_observations"),
    )
    op.create_table(
        "trial_batch_terminals",
        sa.Column(
            "run_group_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("trial_batches.run_group_id"),
            primary_key=True,
        ),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("results_sha256", sa.String(64), nullable=True),
        sa.Column("failure_code", sa.String(64), nullable=True),
        sa.Column(
            "recorded_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('completed','failed')", name="ck_trial_terminal_state"),
        sa.CheckConstraint(
            "(state = 'completed' AND results_sha256 IS NOT NULL AND failure_code IS NULL) OR "
            "(state = 'failed' AND results_sha256 IS NULL AND failure_code IS NOT NULL)",
            name="ck_trial_terminal_shape",
        ),
    )
    op.create_index("ix_trial_batch_terminals_state", "trial_batch_terminals", ["state"])

    op.execute(
        """
        CREATE FUNCTION icarus_block_trial_mutation() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'trial ledger is append-only: % on % blocked', TG_OP, TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for table in (
        "trial_ledger_activation",
        "trial_batches",
        "trial_evaluations",
        "trial_results",
        "trial_batch_terminals",
    ):
        op.execute(
            f"CREATE TRIGGER {table}_no_mutation BEFORE UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION icarus_block_trial_mutation();"
        )
        op.execute(
            f"CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table} "
            "FOR EACH STATEMENT EXECUTE FUNCTION icarus_block_trial_mutation();"
        )

    op.execute(
        """
        CREATE FUNCTION icarus_trial_batch_requires_activation() RETURNS trigger AS $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM trial_ledger_activation WHERE id = 1) THEN
                RAISE EXCEPTION 'trial ledger is not activated';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trial_batch_requires_activation
        BEFORE INSERT ON trial_batches FOR EACH ROW
        EXECUTE FUNCTION icarus_trial_batch_requires_activation();
        """
    )
    op.execute(
        """
        CREATE FUNCTION icarus_trial_batch_cardinality() RETURNS trigger AS $$
        BEGIN
            IF (SELECT count(*) FROM trial_evaluations WHERE run_group_id = NEW.run_group_id)
               <> NEW.expected_evaluations THEN
                RAISE EXCEPTION 'trial batch evaluation cardinality mismatch';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER trial_batch_cardinality
        AFTER INSERT ON trial_batches DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION icarus_trial_batch_cardinality();
        """
    )
    op.execute(
        """
        CREATE FUNCTION icarus_trial_evaluation_insert_guard() RETURNS trigger AS $$
        DECLARE expected integer;
        BEGIN
            SELECT expected_evaluations INTO expected FROM trial_batches
            WHERE run_group_id = NEW.run_group_id;
            IF expected IS NULL OR NEW.ordinal >= expected THEN
                RAISE EXCEPTION 'trial evaluation ordinal outside reserved batch';
            END IF;
            IF EXISTS (SELECT 1 FROM trial_batch_terminals WHERE run_group_id = NEW.run_group_id)
            THEN RAISE EXCEPTION 'trial evaluation inserted after terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trial_evaluation_insert_guard
        BEFORE INSERT ON trial_evaluations FOR EACH ROW
        EXECUTE FUNCTION icarus_trial_evaluation_insert_guard();
        """
    )
    op.execute(
        """
        CREATE FUNCTION icarus_trial_result_insert_guard() RETURNS trigger AS $$
        DECLARE group_id uuid;
        BEGIN
            SELECT run_group_id INTO group_id FROM trial_evaluations
            WHERE evaluation_id = NEW.evaluation_id;
            IF EXISTS (SELECT 1 FROM trial_batch_terminals WHERE run_group_id = group_id)
            THEN RAISE EXCEPTION 'trial result inserted after terminal';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trial_result_insert_guard
        BEFORE INSERT ON trial_results FOR EACH ROW
        EXECUTE FUNCTION icarus_trial_result_insert_guard();
        """
    )
    op.execute(
        """
        CREATE FUNCTION icarus_trial_terminal_guard() RETURNS trigger AS $$
        DECLARE expected integer; actual integer;
        BEGIN
            SELECT expected_evaluations INTO expected FROM trial_batches
            WHERE run_group_id = NEW.run_group_id;
            SELECT count(*) INTO actual FROM trial_results r JOIN trial_evaluations e
            ON e.evaluation_id = r.evaluation_id WHERE e.run_group_id = NEW.run_group_id;
            IF (NEW.state = 'completed' AND actual <> expected)
               OR (NEW.state = 'failed' AND actual <> 0) THEN
                RAISE EXCEPTION 'trial terminal/result cardinality mismatch';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        CREATE TRIGGER trial_terminal_guard
        BEFORE INSERT ON trial_batch_terminals FOR EACH ROW
        EXECUTE FUNCTION icarus_trial_terminal_guard();
        """
    )
    op.execute(
        """
        CREATE FUNCTION icarus_trial_result_consistency() RETURNS trigger AS $$
        DECLARE group_id uuid; expected integer; actual integer; terminal_state text;
        BEGIN
            SELECT e.run_group_id, b.expected_evaluations INTO group_id, expected
            FROM trial_evaluations e JOIN trial_batches b ON b.run_group_id = e.run_group_id
            WHERE e.evaluation_id = NEW.evaluation_id;
            SELECT state INTO terminal_state FROM trial_batch_terminals
            WHERE run_group_id = group_id;
            SELECT count(*) INTO actual FROM trial_results r JOIN trial_evaluations e
            ON e.evaluation_id = r.evaluation_id WHERE e.run_group_id = group_id;
            IF terminal_state IS DISTINCT FROM 'completed' OR actual <> expected THEN
                RAISE EXCEPTION 'trial results require one complete terminal batch';
            END IF;
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
        CREATE CONSTRAINT TRIGGER trial_result_consistency
        AFTER INSERT ON trial_results DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION icarus_trial_result_consistency();
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    activated = connection.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM trial_ledger_activation)")
    ).scalar()
    if activated:
        raise RuntimeError("downgrade refuses to destroy activated trial ledger history")
    for name in (
        "icarus_trial_result_consistency",
        "icarus_trial_terminal_guard",
        "icarus_trial_result_insert_guard",
        "icarus_trial_evaluation_insert_guard",
        "icarus_trial_batch_cardinality",
        "icarus_trial_batch_requires_activation",
        "icarus_block_trial_mutation",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {name}() CASCADE")
    op.drop_index("ix_trial_batch_terminals_state", table_name="trial_batch_terminals")
    op.drop_table("trial_batch_terminals")
    op.drop_table("trial_results")
    op.drop_table("trial_evaluations")
    op.drop_index("ix_trial_batches_reserved_at", table_name="trial_batches")
    op.drop_table("trial_batches")
    op.drop_table("trial_ledger_activation")
