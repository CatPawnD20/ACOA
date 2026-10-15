"""EP-05.02 durable form-question handoff and approved-answer evidence."""

from alembic import op

revision = "0014_form_question_handoff"
down_revision = "0013_cross_source_resolution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.form_question_requests (
            question_id uuid PRIMARY KEY,
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            opportunity_id uuid NOT NULL,
            opportunity_version integer NOT NULL CHECK (opportunity_version>0),
            opportunity_sha256 text NOT NULL CHECK (opportunity_sha256 ~ '^[a-f0-9]{64}$'),
            prompt_sha256 text NOT NULL CHECK (prompt_sha256 ~ '^[a-f0-9]{64}$'),
            required_fact_kind text NOT NULL CHECK
                (required_fact_kind ~ '^[a-z][a-z0-9_]{0,99}$'),
            requested_at timestamptz NOT NULL,
            request jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            UNIQUE (question_id,application_id),
            FOREIGN KEY (opportunity_id,opportunity_version)
                REFERENCES acoa.opportunity_versions(opportunity_id,version)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.approved_form_answers (
            answer_id uuid NOT NULL,
            version integer NOT NULL CHECK (version>0),
            question_id uuid NOT NULL,
            application_id uuid NOT NULL,
            answer_sha256 text NOT NULL CHECK (answer_sha256 ~ '^[a-f0-9]{64}$'),
            approved_at timestamptz NOT NULL,
            answer jsonb NOT NULL,
            record_sha256 text NOT NULL CHECK (record_sha256 ~ '^[a-f0-9]{64}$'),
            persisted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY (answer_id,version),
            UNIQUE (question_id),
            FOREIGN KEY (question_id,application_id)
                REFERENCES acoa.form_question_requests(question_id,application_id)
        )
    """)
    op.execute("""CREATE INDEX form_questions_application
        ON acoa.form_question_requests(application_id,requested_at)""")
    for table in ("form_question_requests", "approved_form_answers"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Form-question and answer history removal requires approved recovery.")
