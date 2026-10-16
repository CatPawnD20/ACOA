"""EP-06.04 immutable sent-message/thread evidence for initial mail."""

from alembic import op

revision = "0019_mail_sent_records"
down_revision = "0018_mail_drafts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.mail_sent_records (
            source_ref uuid PRIMARY KEY,
            attempt_id uuid NOT NULL UNIQUE
                REFERENCES acoa.external_action_attempts(attempt_id),
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            draft_id uuid NOT NULL UNIQUE REFERENCES acoa.mail_drafts(draft_id),
            provider_id uuid NOT NULL,
            provider text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]{0,99}$'),
            provider_message_id text NOT NULL CHECK
                (length(provider_message_id) BETWEEN 1 AND 512),
            provider_thread_id text NOT NULL CHECK
                (length(provider_thread_id) BETWEEN 1 AND 512),
            observed_at timestamptz NOT NULL,
            snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
            record jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""CREATE UNIQUE INDEX mail_sent_records_provider_message
        ON acoa.mail_sent_records(provider,provider_message_id)""")
    op.execute("""CREATE INDEX mail_sent_records_thread
        ON acoa.mail_sent_records(application_id,provider,provider_thread_id)""")
    op.execute("GRANT SELECT, INSERT ON acoa.mail_sent_records TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.mail_sent_records FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Mail sent-record history removal requires approved recovery.")
