"""EP-10.04 immutable pre-activation configuration readiness evidence."""

from alembic import op

revision = "0027_activation_readiness"
down_revision = "0026_operational_health"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.activation_readiness_assessments (
            assessment_id uuid PRIMARY KEY,
            authority_revision bigint NOT NULL CHECK (authority_revision >= 0),
            state text NOT NULL CHECK (state IN ('blocked','ready_for_pilot')),
            profile_variant_id uuid,
            profile_variant_version bigint CHECK (profile_variant_version > 0),
            profile_sha256 text CHECK (profile_sha256 ~ '^[a-f0-9]{64}$'),
            goals_id uuid,
            goals_version bigint CHECK (goals_version > 0),
            goals_sha256 text CHECK (goals_sha256 ~ '^[a-f0-9]{64}$'),
            payload jsonb NOT NULL,
            assessed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((profile_variant_id IS NULL AND profile_variant_version IS NULL
                    AND profile_sha256 IS NULL) OR
                   (profile_variant_id IS NOT NULL AND profile_variant_version IS NOT NULL
                    AND profile_sha256 IS NOT NULL)),
            CHECK ((goals_id IS NULL AND goals_version IS NULL AND goals_sha256 IS NULL) OR
                   (goals_id IS NOT NULL AND goals_version IS NOT NULL
                    AND goals_sha256 IS NOT NULL))
        )
    """)
    op.execute("""
        GRANT SELECT, INSERT ON acoa.activation_readiness_assessments TO acoa_app
    """)
    op.execute("""
        REVOKE UPDATE, DELETE ON acoa.activation_readiness_assessments FROM acoa_app
    """)


def downgrade() -> None:
    raise RuntimeError("Readiness audit removal requires an approved recovery procedure.")
