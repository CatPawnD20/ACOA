"""EP-02.03 current authority, decisions and atomic action reservations; ADR-006/007."""

from alembic import op

revision = "0003_action_protocol"
down_revision = "0002_application_ledger"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep current authority, immutable history and one-attempt dispatch state in PostgreSQL."""
    op.execute("""
        CREATE TABLE acoa.policy_authority (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            revision bigint NOT NULL CHECK (revision >= 0),
            payload jsonb NOT NULL,
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("""INSERT INTO acoa.policy_authority(singleton, revision, payload) VALUES
        (true, 0, '{"settings": {"dry_run": true, "external_actions_enabled": false},
                   "grant": null, "consents": [], "timezone": null, "paused": false}')""")
    op.execute("""
        CREATE TABLE acoa.policy_authority_versions (
            revision bigint PRIMARY KEY,
            payload jsonb NOT NULL,
            change_evidence_id uuid NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.policy_authority_versions FROM acoa_app")
    op.execute("""
        CREATE TABLE acoa.action_evidence (
            request_id uuid PRIMARY KEY,
            request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
            payload jsonb NOT NULL,
            evidence_id uuid NOT NULL,
            expires_at timestamptz NOT NULL,
            quoted_cost numeric CHECK (quoted_cost >= 0 AND quoted_cost < 'Infinity'::numeric),
            currency text,
            estimated_tokens bigint CHECK (estimated_tokens >= 0),
            estimated_seconds bigint CHECK (estimated_seconds >= 0)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.external_action_attempts (
            attempt_id uuid PRIMARY KEY,
            application_id uuid NOT NULL REFERENCES acoa.applications(application_id),
            semantic_key text NOT NULL CHECK (semantic_key ~ '^[a-f0-9]{64}$'),
            prepared jsonb NOT NULL,
            request_id uuid NOT NULL REFERENCES acoa.action_evidence(request_id),
            state text NOT NULL CHECK (state IN ('prepared', 'reserved', 'executing',
                'reconciling', 'verified', 'failed', 'unconfirmed', 'cancelled')),
            created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            reserved_at timestamptz,
            execution_started_at timestamptz,
            execution_token uuid UNIQUE,
            provider_receipt_ref uuid,
            updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
            CHECK ((execution_started_at IS NULL) = (execution_token IS NULL)),
            CHECK (state <> 'cancelled' OR execution_started_at IS NULL),
            CHECK (state NOT IN ('executing', 'reconciling', 'verified', 'unconfirmed')
                OR execution_started_at IS NOT NULL)
        )
    """)
    op.execute("""CREATE UNIQUE INDEX action_one_automatic_attempt
        ON acoa.external_action_attempts(semantic_key)
        WHERE state <> 'cancelled' OR execution_started_at IS NOT NULL""")
    op.execute("""
        CREATE TABLE acoa.budget_ledger (
            attempt_id uuid PRIMARY KEY REFERENCES acoa.external_action_attempts(attempt_id),
            currency text NOT NULL,
            estimated numeric NOT NULL CHECK (estimated >= 0 AND estimated < 'Infinity'::numeric),
            reserved numeric NOT NULL CHECK (reserved >= 0 AND reserved < 'Infinity'::numeric),
            consumed numeric NOT NULL DEFAULT 0
                CHECK (consumed >= 0 AND consumed < 'Infinity'::numeric),
            released numeric NOT NULL DEFAULT 0
                CHECK (released >= 0 AND released < 'Infinity'::numeric),
            settled_at timestamptz,
            CHECK (reserved + released + LEAST(consumed, estimated) = estimated)
        )
    """)
    op.execute("""
        CREATE TABLE acoa.policy_decisions (
            decision_id uuid PRIMARY KEY,
            attempt_id uuid NOT NULL REFERENCES acoa.external_action_attempts(attempt_id),
            authority_revision bigint NOT NULL,
            stage text NOT NULL CHECK (stage IN ('reserve', 'execute')),
            result jsonb NOT NULL,
            recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
        )
    """)
    op.execute("REVOKE UPDATE, DELETE ON acoa.policy_decisions FROM acoa_app")


def downgrade() -> None:
    raise RuntimeError("Action/authority history removal requires an approved recovery procedure.")
