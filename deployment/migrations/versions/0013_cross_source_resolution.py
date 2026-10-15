"""EP-04.04 cross-source deduplication and authorized fallback decisions."""

from alembic import op

revision = "0013_cross_source_resolution"
down_revision = "0012_employer_verification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.entity_deduplication_decisions (
            decision_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            entity_kind text NOT NULL CHECK (entity_kind IN ('organization','opportunity')),
            left_entity_id uuid NOT NULL,
            right_entity_id uuid NOT NULL,
            outcome text NOT NULL CHECK (outcome IN ('canonical','possible_duplicate','distinct')),
            basis text NOT NULL,
            canonical_entity_id uuid,
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            decided_at timestamptz NOT NULL,
            valid_until timestamptz NOT NULL CHECK (valid_until>decided_at),
            decision jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (decision_id,version),
            CHECK ((outcome='canonical')=(canonical_entity_id IS NOT NULL)),
            CHECK (left_entity_id::text<=right_entity_id::text)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.source_fallback_plans (
            plan_id uuid PRIMARY KEY,
            failed_observation_id uuid NOT NULL
                REFERENCES acoa.source_access_observations(observation_id),
            failed_source_id uuid NOT NULL,
            status text NOT NULL CHECK (status IN ('selected','no_allowed_alternative')),
            selected_source_id uuid,
            selected_policy_version text,
            selected_permit_id uuid,
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            planned_at timestamptz NOT NULL,
            valid_until timestamptz NOT NULL,
            plan jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((status='selected')=(selected_source_id IS NOT NULL)),
            CHECK ((status='selected')=(selected_policy_version IS NOT NULL)),
            CHECK ((status='selected')=(selected_permit_id IS NOT NULL)),
            CHECK ((status='selected' AND valid_until>planned_at)
                OR (status='no_allowed_alternative' AND valid_until=planned_at)),
            CHECK (selected_source_id IS NULL OR selected_source_id<>failed_source_id),
            FOREIGN KEY (selected_source_id,selected_policy_version)
                REFERENCES acoa.source_policies(source_id,policy_version)
        )
    """)
    op.execute("""CREATE INDEX deduplication_entity_pair
        ON acoa.entity_deduplication_decisions(entity_kind,left_entity_id,right_entity_id)""")
    op.execute("""CREATE INDEX source_fallback_failure
        ON acoa.source_fallback_plans(failed_observation_id,status)""")
    for table in ("entity_deduplication_decisions", "source_fallback_plans"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Cross-source decision history removal requires approved recovery.")
