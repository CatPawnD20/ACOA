"""EP-03.04 explicit least-privilege application grants for match assessments."""

from alembic import op

revision = "0009_match_assessment_grants"
down_revision = "0008_match_assessments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("GRANT SELECT, INSERT ON acoa.match_assessments TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.match_assessments FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Match assessment access changes require an approved recovery procedure.")
