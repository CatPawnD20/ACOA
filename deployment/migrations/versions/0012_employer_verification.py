"""EP-04.03 employer verification and company-wide contact controls."""

from alembic import op

revision = "0012_employer_verification"
down_revision = "0011_opportunity_research"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.employer_verification_versions (
            verification_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            depth text NOT NULL CHECK (depth IN ('basic','deep')),
            risk text NOT NULL CHECK (risk IN ('low','elevated','high','critical')),
            status text NOT NULL CHECK (status IN
                ('verified','deep_research_required','user_review_required','blocked')),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            assessed_at timestamptz NOT NULL,
            valid_until timestamptz NOT NULL CHECK (valid_until>assessed_at),
            verification jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (verification_id,version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.company_contact_control_events (
            event_id uuid PRIMARY KEY,
            organization_id uuid NOT NULL REFERENCES acoa.organizations(organization_id),
            sequence integer NOT NULL CHECK (sequence>0),
            actor text NOT NULL CHECK (actor IN ('employer','user')),
            action text NOT NULL CHECK (action IN ('block','retract')),
            effective_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL CHECK (recorded_at>=effective_at),
            event jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (organization_id,sequence)
        )
    """)
    op.execute("""CREATE INDEX employer_verification_organization
        ON acoa.employer_verification_versions(organization_id,status,valid_until)""")
    op.execute("""CREATE INDEX company_contact_control_organization
        ON acoa.company_contact_control_events(organization_id,sequence)""")
    for table in ("employer_verification_versions", "company_contact_control_events"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Employer verification history removal requires approved recovery.")
