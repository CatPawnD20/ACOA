"""EP-05.03 immutable artifact metadata and portable storage binding."""

from alembic import op

revision = "0015_artifact_versions"
down_revision = "0014_form_question_handoff"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.application_artifacts (
            artifact_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            kind text NOT NULL CHECK (kind IN ('resume','cover_letter','form_answer')),
            source_draft_id uuid NOT NULL,
            source_binding_sha256 text NOT NULL
                CHECK (source_binding_sha256 ~ '^[a-f0-9]{64}$'),
            media_type text NOT NULL CHECK (length(media_type) BETWEEN 1 AND 255),
            content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
            content_size integer NOT NULL CHECK (content_size BETWEEN 1 AND 10000000),
            storage_key text NOT NULL UNIQUE CHECK (length(storage_key) BETWEEN 1 AND 500),
            created_at timestamptz NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            metadata jsonb NOT NULL,
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (artifact_id,version)
        )
    """)
    op.execute("""CREATE INDEX application_artifacts_application
        ON acoa.application_artifacts(application_id,created_at)""")
    op.execute("GRANT SELECT, INSERT ON acoa.application_artifacts TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.application_artifacts FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Artifact version history removal requires approved recovery.")
