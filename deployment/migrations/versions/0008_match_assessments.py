"""EP-03.04 immutable evidence-bound match assessments."""

from alembic import op

revision = "0008_match_assessments"
down_revision = "0007_model_routing"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.match_assessments (
            assessment_id uuid PRIMARY KEY,
            assessment_sha256 text NOT NULL CHECK (assessment_sha256 ~ '^[a-f0-9]{64}$'),
            profile_variant_id uuid NOT NULL,
            profile_variant_version bigint NOT NULL CHECK (profile_variant_version>0),
            goals_id uuid NOT NULL,
            goals_version bigint NOT NULL CHECK (goals_version>0),
            opportunity_id uuid NOT NULL,
            opportunity_version bigint NOT NULL CHECK (opportunity_version>0),
            opportunity_sha256 text NOT NULL CHECK (opportunity_sha256 ~ '^[a-f0-9]{64}$'),
            policy_version text NOT NULL,
            classification text NOT NULL CHECK (classification IN
                ('fit','research_required','low_priority','excluded')),
            result jsonb NOT NULL,
            valid_until timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""CREATE INDEX match_assessments_opportunity
        ON acoa.match_assessments(opportunity_id,opportunity_version,recorded_at)""")
    op.execute("REVOKE UPDATE, DELETE ON acoa.match_assessments FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Match assessment history removal requires an approved recovery procedure.")
