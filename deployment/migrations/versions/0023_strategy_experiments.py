"""EP-09.01 immutable bounded strategy experiment plans and checkpoints."""

from alembic import op

revision = "0023_strategy_experiments"
down_revision = "0022_career_accounts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.strategy_experiments (
            experiment_id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            plan_sha256 text NOT NULL CHECK (plan_sha256 ~ '^[a-f0-9]{64}$'),
            mode text NOT NULL CHECK (mode IN ('replay','limited_real')),
            baseline_strategy_version text NOT NULL,
            candidate_strategy_version text NOT NULL,
            maximum_cases bigint NOT NULL CHECK (maximum_cases > 0),
            maximum_external_impact bigint NOT NULL CHECK (
                maximum_external_impact >= 0 AND maximum_external_impact <= maximum_cases),
            maximum_cost numeric NOT NULL CHECK (maximum_cost >= 0),
            currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
            expires_at timestamptz NOT NULL,
            payload jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.experiment_checkpoints (
            checkpoint_id uuid PRIMARY KEY,
            experiment_id uuid NOT NULL REFERENCES acoa.strategy_experiments(experiment_id),
            sequence bigint NOT NULL CHECK (sequence > 0),
            checkpoint_sha256 text NOT NULL CHECK (checkpoint_sha256 ~ '^[a-f0-9]{64}$'),
            state text NOT NULL CHECK (state IN
                ('planned','running','ready_for_comparison','stopped','rolled_back','promoted')),
            completed_cases bigint NOT NULL CHECK (completed_cases >= 0),
            external_impact bigint NOT NULL CHECK (external_impact >= 0),
            actual_cost numeric NOT NULL CHECK (actual_cost >= 0),
            currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
            payload jsonb NOT NULL,
            observed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (experiment_id, sequence)
        )
    """)
    op.execute("""CREATE INDEX experiment_checkpoints_lookup
        ON acoa.experiment_checkpoints(experiment_id,sequence DESC)""")
    op.execute("REVOKE UPDATE, DELETE ON acoa.strategy_experiments FROM acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.experiment_checkpoints FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Experiment audit history removal requires an approved recovery procedure.")
