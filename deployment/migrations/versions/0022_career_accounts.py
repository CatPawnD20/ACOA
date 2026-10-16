"""EP-08.03 career-account plans and secret-reference-only outcomes."""

from alembic import op

revision = "0022_career_accounts"
down_revision = "0021_dashboard_controls"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.career_account_plans (
            plan_id uuid PRIMARY KEY,
            account_id uuid NOT NULL UNIQUE,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            provider_id uuid NOT NULL,
            browser_permit_id uuid NOT NULL,
            allowed_origin text NOT NULL CHECK (allowed_origin ~ '^https://[^/]+$'),
            login_sha256 text NOT NULL CHECK (login_sha256 ~ '^[a-f0-9]{64}$'),
            terms_sha256 text NOT NULL CHECK (terms_sha256 ~ '^[a-f0-9]{64}$'),
            data_categories jsonb NOT NULL CHECK (
                jsonb_typeof(data_categories) = 'array'
                AND jsonb_array_length(data_categories) > 0),
            created_at timestamptz NOT NULL,
            expires_at timestamptz NOT NULL CHECK (expires_at > created_at),
            UNIQUE (allowed_origin, login_sha256)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.career_account_events (
            event_id uuid PRIMARY KEY,
            plan_id uuid NOT NULL REFERENCES acoa.career_account_plans(plan_id),
            attempt_id uuid NOT NULL UNIQUE REFERENCES acoa.external_action_attempts(attempt_id),
            secret_ref_id uuid NOT NULL UNIQUE,
            result_kind text NOT NULL CHECK (
                result_kind IN ('created','waiting_user','failed','unconfirmed')),
            obstacles jsonb NOT NULL CHECK (jsonb_typeof(obstacles) = 'array'),
            provider_account_sha256 text CHECK (
                provider_account_sha256 IS NULL OR
                provider_account_sha256 ~ '^[a-f0-9]{64}$'),
            observed_at timestamptz NOT NULL,
            CHECK ((result_kind = 'created') = (provider_account_sha256 IS NOT NULL)),
            CHECK ((result_kind = 'waiting_user') = (jsonb_array_length(obstacles) > 0))
        )
    """)
    for table in ("career_account_plans", "career_account_events"):
        op.execute(f"GRANT SELECT, INSERT ON acoa.{table} TO acoa_app")
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Career-account history removal requires approved recovery.")
