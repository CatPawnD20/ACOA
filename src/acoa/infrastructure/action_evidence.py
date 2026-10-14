"""Trusted current evidence and quoted resource estimates for exact prepared requests."""

from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.application.policy import request_binding_sha256
from acoa.application.policy_inputs import PolicyContext
from acoa.domain.actions import PreparedAction, prepared_binding_sha256
from acoa.domain.values import require_identifier, require_timestamp
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import encode_evidence_context
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class ActionEvidenceStore:
    """Only trusted validation adapters publish facts; no agent/browser ingestion endpoint."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def publish(
        self,
        prepared: PreparedAction,
        context: PolicyContext,
        evidence_id: UUID,
        expires_at: datetime,
    ) -> None:
        require_identifier(evidence_id)
        require_timestamp(expires_at)
        if not isinstance(prepared, PreparedAction) or not isinstance(context, PolicyContext):
            raise DatabaseBoundaryError("Validation requires an exact prepared action.")
        request = prepared.request
        prepared_binding = prepared_binding_sha256(prepared)
        AuthorityStore(self.connection).lock_current()
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        binding = request_binding_sha256(request)
        if (
            context.request_binding_sha256 != binding
            or context.snapshot_at > now
            or context.now > now
            or expires_at <= now
            or expires_at <= context.snapshot_at
        ):
            raise DatabaseBoundaryError("Evidence must be current and bound to the exact request.")
        prior = self.connection.execute(
            text("""SELECT request_sha256, payload->>'prepared_sha256' AS prepared_sha256,
            (payload->>'snapshot_at')::timestamptz AS snapshot_at
            FROM acoa.action_evidence WHERE request_id = :id FOR UPDATE"""),
            {"id": request.request_id},
        ).one_or_none()
        if prior is not None and (
            prior.request_sha256 != binding
            or prior.snapshot_at > context.snapshot_at
            or prior.prepared_sha256 != prepared_binding
        ):
            raise DatabaseBoundaryError("Request identity or evidence time cannot be rolled back.")
        self.connection.execute(
            text("""INSERT INTO acoa.action_evidence
            (request_id, request_sha256, payload, evidence_id, expires_at,
             quoted_cost, currency, estimated_tokens, estimated_seconds)
            VALUES (:id, :binding, CAST(:payload AS jsonb), :evidence, :expiry,
                    :cost, :currency, :tokens, :seconds)
            ON CONFLICT (request_id) DO UPDATE SET payload = EXCLUDED.payload,
                evidence_id = EXCLUDED.evidence_id, expires_at = EXCLUDED.expires_at,
                quoted_cost = EXCLUDED.quoted_cost, currency = EXCLUDED.currency,
                estimated_tokens = EXCLUDED.estimated_tokens,
                estimated_seconds = EXCLUDED.estimated_seconds"""),
            {
                "id": request.request_id,
                "binding": binding,
                "payload": encode_evidence_context(context, prepared_binding),
                "evidence": evidence_id,
                "expiry": expires_at,
                "cost": context.budget.estimated_cost,
                "currency": context.budget.currency,
                "tokens": context.budget.estimated_tokens,
                "seconds": context.budget.estimated_seconds,
            },
        )
