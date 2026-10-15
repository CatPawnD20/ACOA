"""EP-03.01 close nullable target semantics in the shared resource registry."""

from alembic import op

revision = "0006_resource_target_guard"
down_revision = "0005_model_gateway"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """SQL CHECK treats NULL as unknown; require the selected FK explicitly nonnull."""
    op.execute("""ALTER TABLE acoa.resource_attempts ADD CONSTRAINT resource_attempt_target
        CHECK ((kind='external' AND external_attempt_id IS NOT NULL
                AND external_attempt_id=attempt_id AND model_call_id IS NULL)
            OR (kind='model' AND model_call_id IS NOT NULL
                AND model_call_id=attempt_id AND external_attempt_id IS NULL))""")
    op.execute("ALTER TABLE acoa.resource_attempts DROP CONSTRAINT resource_attempts_check")


def downgrade() -> None:
    raise RuntimeError("Resource target integrity must not be weakened by automatic downgrade.")
