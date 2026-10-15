"""EP-03.01 offline model calls and shared monetary reservations; ADR-004/015."""

from alembic import op

revision = "0005_model_gateway"
down_revision = "0004_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.model_calls (
            call_id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
            metadata jsonb NOT NULL,
            state text NOT NULL CHECK (state IN ('running','succeeded','failed','unknown')),
            execution_token uuid NOT NULL UNIQUE,
            reserved_tokens bigint NOT NULL CHECK (reserved_tokens > 0),
            reserved_seconds integer NOT NULL CHECK (reserved_seconds > 0),
            consumed_tokens bigint CHECK (consumed_tokens >= 0),
            consumed_seconds numeric CHECK (consumed_seconds >= 0
                AND consumed_seconds < 'Infinity'::numeric),
            output_sha256 text CHECK (output_sha256 ~ '^[a-f0-9]{64}$'),
            started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            deadline timestamptz NOT NULL,
            completed_at timestamptz
        )
    """)
    op.execute("CREATE INDEX model_calls_task_usage ON acoa.model_calls(task_id)")
    op.execute("""
        CREATE TABLE acoa.resource_attempts (
            attempt_id uuid PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN ('external','model')),
            external_attempt_id uuid UNIQUE REFERENCES acoa.external_action_attempts(attempt_id),
            model_call_id uuid UNIQUE REFERENCES acoa.model_calls(call_id),
            CHECK ((kind='external' AND external_attempt_id=attempt_id AND model_call_id IS NULL)
                OR (kind='model' AND model_call_id=attempt_id AND external_attempt_id IS NULL))
        )
    """)
    op.execute("""INSERT INTO acoa.resource_attempts(attempt_id, kind, external_attempt_id)
        SELECT attempt_id, 'external', attempt_id FROM acoa.budget_ledger""")
    op.execute("ALTER TABLE acoa.budget_ledger DROP CONSTRAINT budget_ledger_attempt_id_fkey")
    op.execute("""ALTER TABLE acoa.budget_ledger ADD CONSTRAINT budget_ledger_attempt_id_fkey
        FOREIGN KEY (attempt_id) REFERENCES acoa.resource_attempts(attempt_id)""")
    op.execute("""
        CREATE TABLE acoa.model_call_events (
            event_id uuid PRIMARY KEY,
            call_id uuid NOT NULL REFERENCES acoa.model_calls(call_id),
            kind text NOT NULL CHECK (kind IN ('started','completed','unknown','limit_violation')),
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.model_call_events FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Model/resource history removal requires an approved recovery procedure.")
