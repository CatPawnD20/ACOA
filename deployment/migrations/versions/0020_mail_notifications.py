"""EP-06.05 immutable reply classifications, notifications and mail digests."""

from alembic import op

revision = "0020_mail_notifications"
down_revision = "0019_mail_sent_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.mail_reply_classifications (
            classification_id uuid PRIMARY KEY,
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            account_id uuid NOT NULL,
            provider text NOT NULL,
            provider_event_id text NOT NULL,
            provider_message_id text NOT NULL,
            provider_thread_id text NOT NULL,
            kind text NOT NULL CHECK (kind IN ('positive','negative','information_request',
                'interview_request','automatic_reply','ambiguous','opt_out')),
            message_snapshot_sha256 text NOT NULL CHECK
                (message_snapshot_sha256 ~ '^[a-f0-9]{64}$'),
            relation_evidence_id uuid NOT NULL,
            classified_at timestamptz NOT NULL,
            classification jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(account_id,provider,provider_event_id)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.notification_items (
            notification_id uuid PRIMARY KEY,
            kind text NOT NULL CHECK (kind='important_reply'),
            urgency text NOT NULL CHECK (urgency='immediate'),
            dedupe_key text NOT NULL UNIQUE CHECK (dedupe_key ~ '^[a-f0-9]{64}$'),
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            classification_id uuid NOT NULL UNIQUE
                REFERENCES acoa.mail_reply_classifications(classification_id),
            state text NOT NULL CHECK (state IN ('pending','delivered','read')),
            created_at timestamptz NOT NULL,
            delivered_at timestamptz,
            read_at timestamptz,
            CHECK ((state='pending' AND delivered_at IS NULL AND read_at IS NULL)
                OR (state='delivered' AND delivered_at IS NOT NULL AND read_at IS NULL)
                OR (state='read' AND delivered_at IS NOT NULL AND read_at IS NOT NULL))
        )
    """)
    op.execute("""
        CREATE TABLE acoa.mail_daily_digests (
            digest_id uuid PRIMARY KEY,
            window_start timestamptz NOT NULL,
            window_end timestamptz NOT NULL CHECK (window_end>window_start),
            created_at timestamptz NOT NULL CHECK (created_at>=window_end),
            incoming_count integer NOT NULL CHECK (incoming_count>=0),
            classified_count integer NOT NULL CHECK (classified_count>=0),
            immediate_count integer NOT NULL CHECK (immediate_count>=0),
            reply_draft_count integer NOT NULL CHECK (reply_draft_count>=0),
            followup_draft_count integer NOT NULL CHECK (followup_draft_count>=0),
            digest jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE(window_start,window_end)
        )
    """)
    for table in (
        "mail_reply_classifications",
        "notification_items",
        "mail_daily_digests",
    ):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Mail notification history removal requires approved recovery.")
