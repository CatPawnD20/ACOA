"""EP-02.01 durable queue and event history; E-03/E-05; ADR-002/003/013."""

from alembic import op

revision = "0001_task_queue"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Create only ACOA application objects under the migration role."""
    op.execute("""
        CREATE TABLE acoa.task_runs (
            task_id uuid PRIMARY KEY,
            kind text NOT NULL CHECK (kind IN (
                'discover_sources', 'discover_organizations', 'extract_opportunities',
                'verify_company', 'evaluate_match', 'plan_application', 'compose_artifact',
                'prepare_action', 'execute_initial_action', 'verify_external_result',
                'sync_inbox', 'draft_reply', 'draft_followup', 'daily_digest',
                'profile_proposal', 'experiment_strategy')),
            input_ref uuid NOT NULL,
            state text NOT NULL DEFAULT 'queued' CHECK (state IN (
                'queued', 'leased', 'running', 'completed', 'waiting_user',
                'retry_scheduled', 'blocked', 'failed', 'cancelled')),
            retry_mode text NOT NULL CHECK (retry_mode IN ('never', 'safe')),
            max_attempts integer NOT NULL CHECK (max_attempts > 0),
            base_delay_seconds integer NOT NULL CHECK (base_delay_seconds > 0),
            max_delay_seconds integer NOT NULL CHECK (max_delay_seconds >= base_delay_seconds),
            attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
            phase_attempt_count integer NOT NULL DEFAULT 0 CHECK (phase_attempt_count >= 0),
            next_run_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            lease_owner uuid,
            lease_token uuid,
            lease_until timestamptz,
            waiting_question_id uuid,
            last_error_class text CHECK (last_error_class IN (
                'transient', 'permanent', 'ambiguous_external', 'lease_expired')),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (retry_mode = 'never' OR kind IN (
                'discover_sources', 'discover_organizations', 'extract_opportunities',
                'verify_company', 'evaluate_match', 'plan_application',
                'verify_external_result', 'profile_proposal')),
            CHECK ((state IN ('leased', 'running') AND lease_owner IS NOT NULL
                AND lease_token IS NOT NULL AND lease_until IS NOT NULL)
                OR (state NOT IN ('leased', 'running') AND lease_owner IS NULL
                AND lease_token IS NULL AND lease_until IS NULL)),
            CHECK ((state = 'waiting_user') = (waiting_question_id IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE INDEX task_runs_ready ON acoa.task_runs (next_run_at, created_at, task_id)
        WHERE state IN ('queued', 'retry_scheduled')
    """)
    op.execute("""
        CREATE INDEX task_runs_expired ON acoa.task_runs (lease_until)
        WHERE state IN ('leased', 'running')
    """)
    op.execute("""
        CREATE TABLE acoa.task_dependencies (
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            dependency_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            PRIMARY KEY (task_id, dependency_id),
            CHECK (task_id <> dependency_id)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.task_events (
            event_id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            previous_state text,
            new_state text NOT NULL,
            error_class text,
            evidence_id uuid,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("CREATE INDEX task_events_by_task ON acoa.task_events(task_id, recorded_at)")
    op.execute("REVOKE UPDATE, DELETE ON acoa.task_events FROM acoa_app")


def downgrade() -> None:
    """Do not silently destroy retained task and audit history."""
    raise RuntimeError("Task history removal requires an explicitly approved recovery procedure.")
