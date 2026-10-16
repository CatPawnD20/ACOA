"""EP-06.03 immutable mail drafts distinct from sent correspondence."""

from alembic import op

revision = "0018_mail_drafts"
down_revision = "0017_mailbox_sync_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.mail_drafts (
            draft_id uuid PRIMARY KEY,
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            account_id uuid NOT NULL,
            recipient_id uuid NOT NULL,
            kind text NOT NULL CHECK (kind IN ('initial_application','reply','followup')),
            policy_action text NOT NULL CHECK (policy_action IN
                ('submit_initial_application','draft_reply','draft_followup')),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            provider_thread_id text CHECK (length(provider_thread_id) BETWEEN 1 AND 512),
            source_message_id text CHECK (length(source_message_id) BETWEEN 1 AND 512),
            prepared_at timestamptz NOT NULL,
            draft jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (kind='initial_application' AND policy_action='submit_initial_application'
                    AND provider_thread_id IS NULL AND source_message_id IS NULL)
                OR (kind='reply' AND policy_action='draft_reply'
                    AND provider_thread_id IS NOT NULL AND source_message_id IS NOT NULL)
                OR (kind='followup' AND policy_action='draft_followup'
                    AND provider_thread_id IS NOT NULL AND source_message_id IS NOT NULL)
            )
        )
    """)
    op.execute("""CREATE INDEX mail_drafts_application
        ON acoa.mail_drafts(application_id,prepared_at)""")
    op.execute("""
        CREATE TABLE acoa.mail_provider_draft_receipts (
            draft_id uuid PRIMARY KEY REFERENCES acoa.mail_drafts(draft_id),
            provider text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]{0,99}$'),
            provider_draft_id text NOT NULL CHECK
                (length(provider_draft_id) BETWEEN 1 AND 512),
            provider_message_id text NOT NULL CHECK
                (length(provider_message_id) BETWEEN 1 AND 512),
            provider_thread_id text NOT NULL CHECK
                (length(provider_thread_id) BETWEEN 1 AND 512),
            recorded_at timestamptz NOT NULL,
            receipt jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(provider,provider_draft_id),
            UNIQUE(provider,provider_message_id)
        )
    """)
    for table in ("mail_drafts", "mail_provider_draft_receipts"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Mail draft history removal requires approved recovery.")
