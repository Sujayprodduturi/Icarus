"""Add the counted descriptive daily-pilot trial kind.

Revision ID: 20261016_descriptive_pilot
Revises: 20261008_trial_ledger
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261016_descriptive_pilot"
down_revision: str | None = "20261008_trial_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BATCH_GEOMETRY_SQL = """
CREATE OR REPLACE FUNCTION icarus_trial_batch_cardinality() RETURNS trigger AS $$
DECLARE
    actual integer;
    portfolios integer;
    fulls integer;
    folds integer;
    pilots integer;
BEGIN
    SELECT count(*),
           count(*) FILTER (WHERE kind = 'portfolio'),
           count(*) FILTER (WHERE kind = 'signal_full'),
           count(*) FILTER (WHERE kind = 'signal_fold'),
           count(*) FILTER (WHERE kind = 'descriptive_pilot')
    INTO actual, portfolios, fulls, folds, pilots
    FROM trial_evaluations WHERE run_group_id = NEW.run_group_id;
    IF actual <> NEW.expected_evaluations THEN
        RAISE EXCEPTION 'trial batch evaluation cardinality mismatch';
    END IF;
    IF NEW.source <> 'native' AND pilots <> 0 THEN
        RAISE EXCEPTION 'legacy trial batch cannot contain descriptive pilot evaluations';
    END IF;
    IF NEW.source <> 'native' THEN
        RETURN NULL;
    END IF;
    IF pilots = 1 AND actual = 1 THEN
        IF NOT EXISTS (
            SELECT 1 FROM trial_evaluations
            WHERE run_group_id = NEW.run_group_id
              AND ordinal = 0 AND fold_index IS NULL
              AND start_index IS NOT NULL AND end_index_exclusive IS NOT NULL
              AND start_ts IS NOT NULL AND end_ts IS NOT NULL
              AND reset_identity = 'daily_descriptive_pilot_v1'
        ) THEN
            RAISE EXCEPTION 'descriptive pilot trial geometry mismatch';
        END IF;
    ELSIF portfolios = 1 AND actual = 1 THEN
        IF NOT EXISTS (
            SELECT 1 FROM trial_evaluations
            WHERE run_group_id = NEW.run_group_id
              AND ordinal = 0 AND fold_index IS NULL
              AND reset_identity = 'walk_forward_portfolio_v1'
        ) THEN
            RAISE EXCEPTION 'portfolio trial geometry mismatch';
        END IF;
    ELSIF pilots = 0 AND portfolios = 0 AND fulls = 1
          AND folds = actual - 1 AND folds >= 1 THEN
        IF NOT EXISTS (
            SELECT 1 FROM trial_evaluations
            WHERE run_group_id = NEW.run_group_id
              AND kind = 'signal_full' AND ordinal = 0 AND fold_index IS NULL
              AND reset_identity = 'continuous_full_development_v1'
        ) OR EXISTS (
            SELECT 1 FROM trial_evaluations
            WHERE run_group_id = NEW.run_group_id AND kind = 'signal_fold'
              AND reset_identity <> 'fresh_signal_simulator_per_fold_v1'
        ) THEN
            RAISE EXCEPTION 'signal trial geometry mismatch';
        END IF;
    ELSE
        RAISE EXCEPTION 'trial batch kind geometry mismatch';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_RESULT_GUARD_SQL = """
CREATE OR REPLACE FUNCTION icarus_trial_result_insert_guard() RETURNS trigger AS $$
DECLARE group_id uuid; evaluation_kind text;
BEGIN
    SELECT run_group_id, kind INTO group_id, evaluation_kind FROM trial_evaluations
    WHERE evaluation_id = NEW.evaluation_id;
    IF group_id IS NULL THEN
        RAISE EXCEPTION 'trial result has no evaluation';
    END IF;
    IF EXISTS (SELECT 1 FROM trial_batch_terminals WHERE run_group_id = group_id)
    THEN RAISE EXCEPTION 'trial result inserted after terminal';
    END IF;
    IF evaluation_kind <> 'portfolio'
       AND (NEW.oos_sharpe IS NOT NULL OR NEW.oos_sharpe_after_tax IS NOT NULL) THEN
        RAISE EXCEPTION 'signal trial result cannot contain Sharpe';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

_OLD_BATCH_CARDINALITY_SQL = """
CREATE OR REPLACE FUNCTION icarus_trial_batch_cardinality() RETURNS trigger AS $$
BEGIN
    IF (SELECT count(*) FROM trial_evaluations WHERE run_group_id = NEW.run_group_id)
       <> NEW.expected_evaluations THEN
        RAISE EXCEPTION 'trial batch evaluation cardinality mismatch';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
"""

_OLD_RESULT_GUARD_SQL = """
CREATE OR REPLACE FUNCTION icarus_trial_result_insert_guard() RETURNS trigger AS $$
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
"""


def _replace_kind_constraint(expression: str) -> None:
    op.drop_constraint("ck_trial_evaluation_kind", "trial_evaluations", type_="check")
    op.create_check_constraint("ck_trial_evaluation_kind", "trial_evaluations", expression)


def upgrade() -> None:
    _replace_kind_constraint(
        "kind IN ('portfolio','signal_full','signal_fold','descriptive_pilot')"
    )
    op.execute(_BATCH_GEOMETRY_SQL)
    op.execute(_RESULT_GUARD_SQL)


def downgrade() -> None:
    connection = op.get_bind()
    descriptive_count = connection.execute(
        sa.text("SELECT count(*) FROM trial_evaluations WHERE kind='descriptive_pilot'")
    ).scalar_one()
    if descriptive_count:
        raise RuntimeError("downgrade refuses to discard descriptive pilot trial history")
    op.execute(_OLD_BATCH_CARDINALITY_SQL)
    op.execute(_OLD_RESULT_GUARD_SQL)
    _replace_kind_constraint("kind IN ('portfolio','signal_full','signal_fold')")
