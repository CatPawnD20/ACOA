"""EP-02.04 immutable submission evidence, incidents and review outbox; P-11."""

from alembic import op

revision = "0004_reconciliation"
down_revision = "0003_action_protocol"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.submission_evidence (
            evidence_id uuid PRIMARY KEY,
            attempt_id uuid NOT NULL REFERENCES acoa.external_action_attempts(attempt_id),
            payload jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.submission_evidence FROM acoa_app")
    op.execute("""
        CREATE TABLE acoa.incidents (
            incident_id uuid PRIMARY KEY,
            attempt_id uuid NOT NULL REFERENCES acoa.external_action_attempts(attempt_id),
            kind text NOT NULL CHECK (kind IN ('unknown_submission', 'abandoned_dispatch',
                'invalid_evidence', 'conflicting_evidence', 'budget_overrun')),
            opened_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            resolved_at timestamptz,
            resolution_evidence_id uuid REFERENCES acoa.submission_evidence(evidence_id),
            CHECK ((resolved_at IS NULL) = (resolution_evidence_id IS NULL))
        )
    """)
    op.execute("""CREATE UNIQUE INDEX incident_open_once ON acoa.incidents(attempt_id, kind)
                  WHERE resolved_at IS NULL""")
    op.execute("""
        CREATE TABLE acoa.review_outbox (
            incident_id uuid PRIMARY KEY REFERENCES acoa.incidents(incident_id),
            state text NOT NULL DEFAULT 'pending' CHECK (state IN ('pending','resolved')),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.reconciliation_events (
            event_id uuid PRIMARY KEY,
            attempt_id uuid NOT NULL REFERENCES acoa.external_action_attempts(attempt_id),
            previous_state text NOT NULL,
            new_state text NOT NULL,
            evidence_id uuid REFERENCES acoa.submission_evidence(evidence_id),
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.reconciliation_events FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError(
        "Submission evidence/incident removal requires an approved recovery procedure."
    )
