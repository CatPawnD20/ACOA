"""Immutable PostgreSQL records for employer verification and company opt-out."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.verification import CompanyContactControlEvent, EmployerVerification
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(value: EmployerVerification | CompanyContactControlEvent) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(prior: Sequence[object] | None, digest: str, payload: str, message: str) -> None:
    if prior is None:
        raise DatabaseBoundaryError("An immutable verification record disappeared after conflict.")
    if prior[0] != digest or prior[1] != json.loads(payload):
        raise DatabaseBoundaryError(message)


class VerificationRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_verification(self, verification: EmployerVerification) -> None:
        if not isinstance(verification, EmployerVerification):
            raise DatabaseBoundaryError("A validated employer verification is required.")
        payload, digest = _encoded(verification)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.employer_verification_versions
                (verification_id,version,organization_id,depth,risk,status,content_sha256,
                 assessed_at,valid_until,verification,record_sha256)
                VALUES (:id,:version,:organization,:depth,:risk,:status,:content,
                    :assessed,:valid_until,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (verification_id,version) DO NOTHING RETURNING verification_id"""),
            {
                "id": verification.verification_id,
                "version": verification.version,
                "organization": verification.organization_id,
                "depth": verification.depth.value,
                "risk": verification.risk.value,
                "status": verification.status.value,
                "content": verification.content_sha256,
                "assessed": verification.assessed_at,
                "valid_until": verification.valid_until,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT record_sha256,verification
                FROM acoa.employer_verification_versions
                WHERE verification_id=:id AND version=:version"""),
            {"id": verification.verification_id, "version": verification.version},
        ).one_or_none()
        _require_exact(
            prior,
            digest,
            payload,
            "An employer verification version must retain its exact evidence.",
        )

    def record_contact_control(self, event: CompanyContactControlEvent) -> None:
        if not isinstance(event, CompanyContactControlEvent):
            raise DatabaseBoundaryError("A validated company contact control event is required.")
        payload, digest = _encoded(event)
        self._lock_contact_stream(event.organization_id)
        existing = self._contact_control_record(event)
        if existing is not None:
            _require_exact(
                existing,
                digest,
                payload,
                "A company contact control sequence must retain its exact event.",
            )
            return
        self._require_append_position(event)
        self._insert_contact_control(event, payload, digest)

    def _lock_contact_stream(self, organization_id: UUID) -> None:
        self.connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(CAST(:id AS text),0))"),
            {"id": organization_id},
        )

    def _contact_control_record(self, event: CompanyContactControlEvent) -> Sequence[object] | None:
        return self.connection.execute(
            text("""SELECT record_sha256,event FROM acoa.company_contact_control_events
                WHERE organization_id=:organization AND sequence=:sequence"""),
            {"organization": event.organization_id, "sequence": event.sequence},
        ).one_or_none()

    def _require_append_position(self, event: CompanyContactControlEvent) -> None:
        organization_exists = self.connection.execute(
            text("SELECT 1 FROM acoa.organizations WHERE organization_id=:id"),
            {"id": event.organization_id},
        ).scalar_one_or_none()
        if organization_exists is None:
            raise DatabaseBoundaryError(
                "A company contact control requires a recorded organization."
            )
        last_sequence = self.connection.execute(
            text("""SELECT COALESCE(MAX(sequence),0)
                FROM acoa.company_contact_control_events WHERE organization_id=:organization"""),
            {"organization": event.organization_id},
        ).scalar_one()
        if event.sequence != last_sequence + 1:
            raise DatabaseBoundaryError("Company contact control events must be appended in order.")

    def _insert_contact_control(
        self, event: CompanyContactControlEvent, payload: str, digest: str
    ) -> None:
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.company_contact_control_events
                (event_id,organization_id,sequence,actor,action,effective_at,recorded_at,
                 event,record_sha256)
                VALUES (:id,:organization,:sequence,:actor,:action,:effective,:recorded,
                    CAST(:payload AS jsonb),:digest)
                ON CONFLICT (organization_id,sequence) DO NOTHING RETURNING event_id"""),
            {
                "id": event.event_id,
                "organization": event.organization_id,
                "sequence": event.sequence,
                "actor": event.actor.value,
                "action": event.action.value,
                "effective": event.effective_at,
                "recorded": event.recorded_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        _require_exact(
            self._contact_control_record(event),
            digest,
            payload,
            "A company contact control sequence must retain its exact event.",
        )
