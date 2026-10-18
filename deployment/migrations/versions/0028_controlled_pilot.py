"""EP-10.05 immutable cancellation evidence for the controlled live pilot."""

from alembic import op

revision = "0028_controlled_pilot"
down_revision = "0027_activation_readiness"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.external_action_cancellations (
            cancellation_id uuid PRIMARY KEY,
            attempt_id uuid NOT NULL UNIQUE
                REFERENCES acoa.external_action_attempts(attempt_id),
            prior_state text NOT NULL CHECK (prior_state IN ('prepared','reserved')),
            evidence_id uuid NOT NULL,
            cancelled_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("GRANT SELECT, INSERT ON acoa.external_action_cancellations TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.external_action_cancellations FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("External-action cancellation evidence requires approved recovery.")
