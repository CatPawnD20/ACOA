"""EP-02.02 semantic application identity; F-10, P-11/P-15, ADR-007/013."""

from alembic import op

revision = "0002_application_ledger"
down_revision = "0001_task_queue"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Separate canonical series, application episodes and append-only lifecycle evidence."""
    op.execute("""
        CREATE TABLE acoa.application_series (
            series_id uuid PRIMARY KEY,
            owner_id uuid NOT NULL,
            company_id uuid NOT NULL,
            target_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('initial_application', 'initial_contact')),
            UNIQUE(owner_id, company_id, target_id, kind)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.applications (
            application_id uuid PRIMARY KEY,
            series_id uuid NOT NULL REFERENCES acoa.application_series(series_id),
            campaign_id uuid NOT NULL,
            identity_evidence_id uuid NOT NULL,
            semantic_key text NOT NULL UNIQUE CHECK (semantic_key ~ '^[a-f0-9]{64}$'),
            reapplication_episode_id uuid,
            previous_application_id uuid UNIQUE,
            reapplication_evidence jsonb,
            state text NOT NULL DEFAULT 'open'
                CHECK (state IN ('open', 'rejected', 'closed', 'withdrawn')),
            submission_state text NOT NULL DEFAULT 'not_started' CHECK (submission_state IN (
                'not_started', 'submission_verified', 'submission_failed',
                'submission_unconfirmed')),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            closed_at timestamptz,
            closure_evidence_id uuid,
            UNIQUE(series_id, application_id),
            UNIQUE(series_id, reapplication_episode_id),
            FOREIGN KEY (series_id, previous_application_id)
                REFERENCES acoa.applications(series_id, application_id),
            CHECK (previous_application_id <> application_id),
            CHECK ((reapplication_episode_id IS NULL AND previous_application_id IS NULL
                AND reapplication_evidence IS NULL) OR (reapplication_episode_id IS NOT NULL
                AND previous_application_id IS NOT NULL AND reapplication_evidence IS NOT NULL)),
            CHECK ((state = 'open' AND closed_at IS NULL AND closure_evidence_id IS NULL)
                OR (state <> 'open' AND closed_at IS NOT NULL AND closure_evidence_id IS NOT NULL)),
            CHECK (closed_at IS NULL OR closed_at >= created_at)
        )
    """)
    op.execute("""CREATE UNIQUE INDEX application_initial_episode ON acoa.applications(series_id)
                  WHERE reapplication_episode_id IS NULL""")
    op.execute("""
        CREATE TABLE acoa.application_events (
            event_id uuid PRIMARY KEY,
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            previous_state text,
            new_state text NOT NULL,
            evidence_id uuid NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""CREATE INDEX application_events_history
                  ON acoa.application_events(application_id, recorded_at)""")
    op.execute("REVOKE UPDATE, DELETE ON acoa.application_events FROM acoa_app")


def downgrade() -> None:
    """Application evidence is retained; no automatic destructive downgrade."""
    raise RuntimeError("Application history removal requires an approved recovery procedure.")
