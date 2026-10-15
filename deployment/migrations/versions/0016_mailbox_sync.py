"""EP-06.02 atomic mailbox cursor and immutable event reconciliation."""

from alembic import op

revision = "0016_mailbox_sync"
down_revision = "0015_artifact_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.mailbox_sync_state (
            account_id uuid NOT NULL,
            provider text NOT NULL CHECK (provider ~ '^[a-z][a-z0-9_]{0,99}$'),
            cursor text NOT NULL CHECK (length(cursor) BETWEEN 1 AND 512),
            revision bigint NOT NULL CHECK (revision>0),
            updated_at timestamptz NOT NULL,
            PRIMARY KEY (account_id,provider)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.mailbox_sync_runs (
            sync_id uuid PRIMARY KEY,
            account_id uuid NOT NULL,
            provider text NOT NULL,
            status text NOT NULL CHECK (status IN ('completed','full_sync_required')),
            start_cursor text CHECK (length(start_cursor) BETWEEN 1 AND 512),
            final_cursor text CHECK (length(final_cursor) BETWEEN 1 AND 512),
            fetched_count integer NOT NULL CHECK (fetched_count>=0),
            inserted_count integer NOT NULL CHECK
                (inserted_count>=0 AND inserted_count<=fetched_count),
            started_at timestamptz NOT NULL,
            completed_at timestamptz NOT NULL CHECK (completed_at>=started_at),
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (
                (status='completed' AND start_cursor IS NOT NULL AND final_cursor IS NOT NULL)
                OR (status='full_sync_required' AND final_cursor IS NULL
                    AND fetched_count=0 AND inserted_count=0)
            )
        )
    """)
    op.execute("""
        CREATE TABLE acoa.mailbox_events (
            account_id uuid NOT NULL,
            provider text NOT NULL,
            provider_event_id text NOT NULL CHECK
                (length(provider_event_id) BETWEEN 1 AND 512),
            provider_message_id text NOT NULL CHECK
                (length(provider_message_id) BETWEEN 1 AND 512),
            provider_thread_id text NOT NULL CHECK
                (length(provider_thread_id) BETWEEN 1 AND 512),
            kind text NOT NULL CHECK (kind='message_added'),
            observed_cursor text NOT NULL CHECK
                (length(observed_cursor) BETWEEN 1 AND 512),
            sync_id uuid NOT NULL,
            recorded_at timestamptz NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (account_id,provider,provider_event_id),
            FOREIGN KEY (account_id,provider)
                REFERENCES acoa.mailbox_sync_state(account_id,provider),
            FOREIGN KEY (sync_id) REFERENCES acoa.mailbox_sync_runs(sync_id)
                DEFERRABLE INITIALLY DEFERRED
        )
    """)
    op.execute("""CREATE INDEX mailbox_events_message
        ON acoa.mailbox_events(account_id,provider,provider_message_id)""")
    op.execute("""CREATE INDEX mailbox_events_thread
        ON acoa.mailbox_events(account_id,provider,provider_thread_id)""")
    op.execute("GRANT SELECT, INSERT, UPDATE ON acoa.mailbox_sync_state TO acoa_app")
    op.execute("REVOKE DELETE ON acoa.mailbox_sync_state FROM acoa_app")
    for table in ("mailbox_sync_runs", "mailbox_events"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Mailbox cursors and event history removal requires approved recovery.")
