"""EP-03.02 current provider scopes and versioned route/quality audit."""

from alembic import op

revision = "0007_model_routing"
down_revision = "0006_resource_target_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE acoa.model_provider_permissions (
            provider_id uuid PRIMARY KEY,
            revision bigint NOT NULL CHECK (revision>0),
            payload jsonb NOT NULL,
            change_evidence_id uuid NOT NULL
        )
    """)
    op.execute("""
        CREATE TABLE acoa.model_provider_permission_versions (
            provider_id uuid NOT NULL,
            revision bigint NOT NULL CHECK (revision>0),
            payload jsonb NOT NULL,
            change_evidence_id uuid NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            PRIMARY KEY(provider_id,revision)
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.model_provider_permission_versions FROM acoa_app")
    op.execute("""
        CREATE TABLE acoa.model_routes (
            route_id uuid PRIMARY KEY,
            task_id uuid NOT NULL REFERENCES acoa.task_runs(task_id),
            input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
            policy_version text NOT NULL,
            result jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""
        CREATE TABLE acoa.model_quality_checks (
            check_id uuid PRIMARY KEY,
            call_id uuid NOT NULL REFERENCES acoa.model_calls(call_id),
            policy_version text NOT NULL,
            result jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute(
        "REVOKE UPDATE, DELETE ON acoa.model_routes, acoa.model_quality_checks FROM acoa_app"
    )


def downgrade() -> None:
    raise RuntimeError(
        "Provider/route/quality history removal requires an approved recovery procedure."
    )
