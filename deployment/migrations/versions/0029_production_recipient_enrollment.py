"""EP-10.06 immutable, evidence-bound production recipient enrollment."""

from alembic import op

revision = "0029_production_targets"
down_revision = "0028_controlled_pilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.production_recipient_enrollments (
            enrollment_id uuid PRIMARY KEY,
            recipient_id uuid NOT NULL,
            recipient_class text NOT NULL CHECK (recipient_class IN
                ('verified_official_application_email',
                 'verified_public_corporate_recruiting_contact')),
            grant_id uuid NOT NULL,
            grant_version integer NOT NULL CHECK (grant_version > 0),
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            target_id uuid NOT NULL,
            target_version integer NOT NULL CHECK (target_version > 0),
            target_content_sha256 text NOT NULL
                CHECK (target_content_sha256 ~ '^[a-f0-9]{64}$'),
            channel_id uuid NOT NULL,
            channel_version integer NOT NULL CHECK (channel_version > 0),
            channel_content_sha256 text NOT NULL
                CHECK (channel_content_sha256 ~ '^[a-f0-9]{64}$'),
            endpoint_sha256 text NOT NULL CHECK (endpoint_sha256 ~ '^[a-f0-9]{64}$'),
            employer_verification_id uuid NOT NULL,
            employer_verification_version integer NOT NULL
                CHECK (employer_verification_version > 0),
            employer_verification_sha256 text NOT NULL
                CHECK (employer_verification_sha256 ~ '^[a-f0-9]{64}$'),
            enrolled_at timestamptz NOT NULL,
            valid_until timestamptz NOT NULL CHECK (valid_until > enrolled_at),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            enrollment jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK (recipient_id = channel_id),
            FOREIGN KEY (target_id,target_version)
                REFERENCES acoa.opportunity_versions(opportunity_id,version),
            FOREIGN KEY (channel_id,channel_version)
                REFERENCES acoa.contact_channel_versions(channel_id,version),
            FOREIGN KEY (employer_verification_id,employer_verification_version)
                REFERENCES acoa.employer_verification_versions(verification_id,version),
            UNIQUE (grant_id,grant_version,target_id,target_version,channel_id,channel_version,
                employer_verification_id,employer_verification_version,recipient_class)
        )
    """)
    op.execute("""CREATE INDEX production_recipient_current
        ON acoa.production_recipient_enrollments
        (recipient_id,grant_id,grant_version,recipient_class,valid_until)""")
    op.execute("GRANT SELECT, INSERT ON acoa.production_recipient_enrollments TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.production_recipient_enrollments FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Production recipient enrollment evidence requires approved recovery.")
