"""EP-06.02 restrict mailbox cursor updates to mutable columns."""

from alembic import op

revision = "0017_mailbox_sync_grants"
down_revision = "0016_mailbox_sync"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("REVOKE UPDATE ON acoa.mailbox_sync_state FROM acoa_app")
    op.execute("""GRANT UPDATE (cursor,revision,updated_at)
        ON acoa.mailbox_sync_state TO acoa_app""")


def downgrade() -> None:
    raise RuntimeError("Mailbox cursor privilege widening requires explicit approval.")
