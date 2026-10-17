"""EP-10.03 append-only operational health, assessments and pending alerts."""

from alembic import op

revision = "0026_operational_health"
down_revision = "0025_generated_tool_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.operational_health_events (
            observation_id uuid PRIMARY KEY,
            dependency text NOT NULL CHECK (dependency IN
                ('database','artifact_store','mail_provider','model_provider',
                 'source_provider','browser_worker')),
            state text NOT NULL CHECK (state IN
                ('healthy','degraded','unavailable','systemic_risk')),
            evidence_sha256 text NOT NULL CHECK (evidence_sha256 ~ '^[a-f0-9]{64}$'),
            payload jsonb NOT NULL,
            observed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.operational_assessments (
            assessment_id uuid PRIMARY KEY,
            dependency text NOT NULL CHECK (dependency IN
                ('database','artifact_store','mail_provider','model_provider',
                 'source_provider','browser_worker')),
            response text NOT NULL CHECK (response IN
                ('continue','alert','isolate_dependency','enter_safe_mode')),
            failure_count integer NOT NULL CHECK (failure_count >= 0),
            maximum_failures integer NOT NULL CHECK (maximum_failures > 0),
            window_seconds integer NOT NULL CHECK (window_seconds > 0),
            payload jsonb NOT NULL,
            assessed_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.operational_alerts (
            assessment_id uuid PRIMARY KEY
                REFERENCES acoa.operational_assessments(assessment_id),
            scope text NOT NULL CHECK (scope IN ('dependency','system')),
            severity text NOT NULL CHECK (severity IN ('warning','critical')),
            state text NOT NULL DEFAULT 'pending' CHECK (state='pending'),
            created_at timestamptz NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    for table in (
        "operational_health_events",
        "operational_assessments",
        "operational_alerts",
    ):
        op.execute(f"REVOKE UPDATE, DELETE ON acoa.{table} FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Operational audit removal requires an approved recovery procedure.")
