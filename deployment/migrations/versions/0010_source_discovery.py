"""EP-04.01 immutable source policies, access observations and snapshot metadata."""

from alembic import op

revision = "0010_source_discovery"
down_revision = "0009_match_assessment_grants"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.source_policies (
            source_id uuid NOT NULL,
            policy_version text NOT NULL,
            policy_sha256 text NOT NULL CHECK (policy_sha256 ~ '^[a-f0-9]{64}$'),
            source_kind text NOT NULL CHECK (source_kind IN
                ('official_api','search_api','public_http')),
            access_allowed boolean NOT NULL,
            valid_until timestamptz NOT NULL,
            policy jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (source_id,policy_version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.source_batches (
            batch_id uuid PRIMARY KEY,
            batch_sha256 text NOT NULL CHECK (batch_sha256 ~ '^[a-f0-9]{64}$'),
            source_id uuid NOT NULL,
            source_policy_version text NOT NULL,
            query_sha256 text NOT NULL CHECK (query_sha256 ~ '^[a-f0-9]{64}$'),
            observed_at timestamptz NOT NULL,
            batch jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            FOREIGN KEY (source_id,source_policy_version)
                REFERENCES acoa.source_policies(source_id,policy_version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.source_snapshots (
            snapshot_id uuid PRIMARY KEY,
            snapshot_sha256 text NOT NULL CHECK (snapshot_sha256 ~ '^[a-f0-9]{64}$'),
            source_id uuid NOT NULL,
            source_policy_version text NOT NULL,
            resource_sha256 text NOT NULL CHECK (resource_sha256 ~ '^[a-f0-9]{64}$'),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            observed_at timestamptz NOT NULL,
            valid_until timestamptz NOT NULL,
            snapshot jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (valid_until>observed_at),
            FOREIGN KEY (source_id,source_policy_version)
                REFERENCES acoa.source_policies(source_id,policy_version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.source_access_observations (
            observation_id uuid PRIMARY KEY,
            observation_sha256 text NOT NULL CHECK (observation_sha256 ~ '^[a-f0-9]{64}$'),
            source_id uuid NOT NULL,
            source_policy_version text NOT NULL,
            operation text NOT NULL CHECK (operation IN ('discover','fetch')),
            status text NOT NULL CHECK (status IN
                ('succeeded','blocked','timeout','unavailable','not_found','access_challenge',
                 'invalid_response')),
            target_sha256 text NOT NULL CHECK (target_sha256 ~ '^[a-f0-9]{64}$'),
            result_sha256 text CHECK (result_sha256 IS NULL OR
                result_sha256 ~ '^[a-f0-9]{64}$'),
            observed_at timestamptz NOT NULL,
            observation jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((status='succeeded')=(result_sha256 IS NOT NULL)),
            FOREIGN KEY (source_id,source_policy_version)
                REFERENCES acoa.source_policies(source_id,policy_version)
        )
    """)
    op.execute("""CREATE INDEX source_batches_query
        ON acoa.source_batches(source_id,query_sha256,observed_at)""")
    op.execute("""CREATE INDEX source_snapshots_resource
        ON acoa.source_snapshots(source_id,resource_sha256,observed_at)""")
    op.execute("""CREATE INDEX source_access_status
        ON acoa.source_access_observations(source_id,status,observed_at)""")
    for table in (
        "source_policies",
        "source_batches",
        "source_snapshots",
        "source_access_observations",
    ):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Source discovery history removal requires an approved recovery procedure.")
