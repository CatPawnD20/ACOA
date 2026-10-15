"""EP-04.02 evidence-bound organizations, opportunities and corporate channels."""

from alembic import op

revision = "0011_opportunity_research"
down_revision = "0010_source_discovery"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.organizations (
            organization_id uuid PRIMARY KEY,
            identity_sha256 text NOT NULL UNIQUE CHECK (identity_sha256 ~ '^[a-f0-9]{64}$'),
            canonical_domain text NOT NULL UNIQUE,
            observed_at timestamptz NOT NULL,
            organization jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.opportunity_versions (
            opportunity_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            identity_sha256 text NOT NULL CHECK (identity_sha256 ~ '^[a-f0-9]{64}$'),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            kind text NOT NULL CHECK (kind IN ('published_job','unadvertised_prospect')),
            status text NOT NULL CHECK (status IN ('active','expired','removed','unverified')),
            source_resource_sha256 text NOT NULL CHECK
                (source_resource_sha256 ~ '^[a-f0-9]{64}$'),
            observed_at timestamptz NOT NULL,
            opportunity jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (opportunity_id,version),
            UNIQUE (identity_sha256,version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.contact_channel_versions (
            channel_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            kind text NOT NULL CHECK (kind IN ('career_portal','general_application_email',
                'public_corporate_email','career_contact_form','support_form')),
            endpoint_sha256 text NOT NULL CHECK (endpoint_sha256 ~ '^[a-f0-9]{64}$'),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            eligible_for_initial_contact boolean NOT NULL,
            channel jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (channel_id,version),
            UNIQUE (organization_id,kind,endpoint_sha256,version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.contact_research (
            research_id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            status text NOT NULL CHECK
                (status IN ('verified_channels','no_suitable_channel','no_channel')),
            observed_at timestamptz NOT NULL,
            research jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""CREATE INDEX opportunity_versions_organization
        ON acoa.opportunity_versions(organization_id,kind,status,observed_at)""")
    op.execute("""CREATE INDEX contact_channels_organization
        ON acoa.contact_channel_versions(organization_id,eligible_for_initial_contact)""")
    for table in (
        "organizations",
        "opportunity_versions",
        "contact_channel_versions",
        "contact_research",
    ):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Opportunity research history removal requires approved recovery.")
