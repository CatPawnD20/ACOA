"""EP-09.02 immutable fixed-scope comparisons and reversible strategy selections."""

from alembic import op

revision = "0024_experiment_comparisons"
down_revision = "0023_strategy_experiments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.experiment_comparisons (
            comparison_id uuid PRIMARY KEY,
            experiment_id uuid NOT NULL REFERENCES acoa.strategy_experiments(experiment_id),
            comparison_sha256 text NOT NULL CHECK (comparison_sha256 ~ '^[a-f0-9]{64}$'),
            gate_version text NOT NULL,
            dataset_sha256 text NOT NULL CHECK (dataset_sha256 ~ '^[a-f0-9]{64}$'),
            sample_count bigint NOT NULL CHECK (sample_count > 0),
            payload jsonb NOT NULL,
            compared_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.strategy_selections (
            selection_id uuid PRIMARY KEY,
            comparison_id uuid NOT NULL UNIQUE
                REFERENCES acoa.experiment_comparisons(comparison_id),
            experiment_id uuid NOT NULL REFERENCES acoa.strategy_experiments(experiment_id),
            selection_sha256 text NOT NULL CHECK (selection_sha256 ~ '^[a-f0-9]{64}$'),
            kind text NOT NULL CHECK (kind IN
                ('promote_candidate','keep_baseline','rollback_baseline')),
            selected_strategy_version text NOT NULL,
            restore_strategy_version text NOT NULL,
            payload jsonb NOT NULL,
            selected_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.experiment_comparisons FROM acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.strategy_selections FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Experiment comparison history requires an approved recovery procedure.")
