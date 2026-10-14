"""Durable deduplicated user-review incidents; this outbox never sends notifications."""

from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.submission_evidence import IncidentKind
from acoa.domain.values import require_identifier
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)


class IncidentStore:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def open(self, attempt_id: UUID, kind: IncidentKind) -> UUID:
        """State, incident and pending review commit in one caller-owned transaction."""
        require_identifier(attempt_id)
        require_transaction(self.connection)
        if not isinstance(kind, IncidentKind):
            raise ValueError("Incident kind must be explicit.")
        incident_id: UUID = self.connection.execute(
            text("""
            INSERT INTO acoa.incidents(incident_id, attempt_id, kind) VALUES (:id, :attempt, :kind)
            ON CONFLICT (attempt_id, kind) WHERE resolved_at IS NULL
                DO UPDATE SET kind = EXCLUDED.kind RETURNING incident_id
        """),
            {"id": uuid4(), "attempt": attempt_id, "kind": kind.value},
        ).scalar_one()
        self.connection.execute(
            text("""INSERT INTO acoa.review_outbox(incident_id) VALUES (:id)
            ON CONFLICT (incident_id) DO NOTHING"""),
            {"id": incident_id},
        )
        return incident_id

    def resolve_unknown(self, attempt_id: UUID, evidence_id: UUID) -> None:
        require_transaction(self.connection)
        for identifier in (attempt_id, evidence_id):
            require_identifier(identifier)
        matched: bool = self.connection.execute(
            text("""SELECT EXISTS (
            SELECT 1 FROM acoa.submission_evidence WHERE evidence_id=:evidence
                AND attempt_id=:attempt)"""),
            {"attempt": attempt_id, "evidence": evidence_id},
        ).scalar_one()
        if not matched:
            raise DatabaseBoundaryError(
                "Incident resolution requires evidence for the same attempt."
            )
        self.connection.execute(
            text("""WITH resolved AS (
            UPDATE acoa.incidents SET resolved_at = clock_timestamp(),
                resolution_evidence_id = :evidence
            WHERE attempt_id = :attempt AND resolved_at IS NULL
                AND kind IN ('unknown_submission','abandoned_dispatch') RETURNING incident_id)
            UPDATE acoa.review_outbox SET state = 'resolved'
            WHERE incident_id IN (SELECT incident_id FROM resolved)
        """),
            {"attempt": attempt_id, "evidence": evidence_id},
        )
