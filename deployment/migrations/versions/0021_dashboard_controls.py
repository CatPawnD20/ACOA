"""EP-07.02 authenticated dashboard controls and paused queue state."""

from alembic import op

revision = "0021_dashboard_controls"
down_revision = "0020_mail_notifications"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE acoa.task_runs DROP CONSTRAINT task_runs_state_check")
    op.execute("""
        ALTER TABLE acoa.task_runs ADD CONSTRAINT task_runs_state_check CHECK (state IN (
            'queued','leased','running','completed','waiting_user','retry_scheduled',
            'paused','blocked','failed','cancelled'))
    """)
    op.execute("""
        CREATE TABLE acoa.dashboard_control_events (
            event_id uuid PRIMARY KEY,
            request_id uuid NOT NULL UNIQUE,
            actor_sha256 text NOT NULL CHECK (actor_sha256 ~ '^[a-f0-9]{64}$'),
            action text NOT NULL CHECK (action IN (
                'enter_safe_mode','resume_system','replace_limits',
                'pause_task','resume_task','cancel_task')),
            task_id uuid REFERENCES acoa.task_runs(task_id),
            authority_revision bigint CHECK (authority_revision >= 0),
            result jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((action IN ('pause_task','resume_task','cancel_task')) = (task_id IS NOT NULL)),
            CHECK ((action IN ('enter_safe_mode','resume_system','replace_limits')) =
                (authority_revision IS NOT NULL))
        )
    """)
    op.execute("GRANT SELECT, INSERT ON acoa.dashboard_control_events TO acoa_app")
    op.execute("REVOKE UPDATE, DELETE ON acoa.dashboard_control_events FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Dashboard control history removal requires approved recovery.")
