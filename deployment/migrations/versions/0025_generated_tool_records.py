"""EP-09.04 immutable generated-tool requests, executions and mediated proposals."""

from alembic import op

revision = "0025_generated_tool_records"
down_revision = "0024_experiment_comparisons"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.generated_tool_requests (
            request_id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            experiment_id uuid NOT NULL REFERENCES acoa.strategy_experiments(experiment_id),
            source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
            input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
            request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
            payload jsonb NOT NULL,
            expires_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.generated_tool_executions (
            execution_id uuid PRIMARY KEY,
            request_id uuid NOT NULL REFERENCES acoa.generated_tool_requests(request_id),
            execution_sha256 text NOT NULL CHECK (execution_sha256 ~ '^[a-f0-9]{64}$'),
            state text NOT NULL CHECK (state IN ('succeeded','rejected','failed')),
            output_sha256 text NOT NULL CHECK (output_sha256 ~ '^[a-f0-9]{64}$'),
            worker_image_sha256 text NOT NULL CHECK (worker_image_sha256 ~ '^[a-f0-9]{64}$'),
            payload jsonb NOT NULL,
            observed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.generated_tool_proposals (
            proposal_id uuid PRIMARY KEY,
            request_id uuid NOT NULL REFERENCES acoa.generated_tool_requests(request_id),
            execution_id uuid NOT NULL REFERENCES acoa.generated_tool_executions(execution_id),
            proposal_sha256 text NOT NULL CHECK (proposal_sha256 ~ '^[a-f0-9]{64}$'),
            kind text NOT NULL CHECK (kind IN
                ('source_query','research_priority','strategy_note')),
            subject text NOT NULL,
            payload jsonb NOT NULL,
            proposed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (execution_id,kind,subject)
        )
    """)
    for table in (
        "generated_tool_requests",
        "generated_tool_executions",
        "generated_tool_proposals",
    ):
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Generated-tool audit removal requires an approved recovery procedure.")
