"""Fail-closed persistence for dynamically approved production recipients."""

import json
from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.domain.authorization import RecipientClass, grant_is_active
from acoa.domain.production_targets import ProductionRecipientEnrollment
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    validate_application_connection,
)

_ENROLLMENT_SOURCE = """
SELECT
    o.kind AS target_kind,
    o.status AS target_status,
    o.organization_id AS target_organization_id,
    o.content_sha256 AS target_content_sha256,
    (o.opportunity->'publication_evidence'->>'observed_at')::timestamptz
        AS target_observed_at,
    (o.opportunity->'publication_evidence'->>'valid_until')::timestamptz
        AS target_valid_until,
    c.organization_id AS channel_organization_id,
    c.kind AS channel_kind,
    c.endpoint_sha256,
    c.content_sha256 AS channel_content_sha256,
    c.eligible_for_initial_contact,
    c.channel->>'visibility' AS channel_visibility,
    c.channel->>'purpose' AS channel_purpose,
    (c.channel->'evidence'->>'observed_at')::timestamptz AS channel_observed_at,
    (c.channel->'evidence'->>'valid_until')::timestamptz AS channel_valid_until,
    v.organization_id AS verification_organization_id,
    v.status AS verification_status,
    v.content_sha256 AS verification_content_sha256,
    v.assessed_at,
    v.valid_until AS verification_valid_until
FROM acoa.opportunity_versions o
JOIN acoa.contact_channel_versions c ON c.channel_id = :channel
    AND c.version = :channel_version
JOIN acoa.employer_verification_versions v ON v.verification_id = :verification
    AND v.version = :verification_version
WHERE o.opportunity_id = :target AND o.version = :target_version
  AND NOT EXISTS (SELECT 1 FROM acoa.opportunity_versions newer
      WHERE newer.opportunity_id=o.opportunity_id AND newer.version>o.version)
  AND NOT EXISTS (SELECT 1 FROM acoa.contact_channel_versions newer
      WHERE newer.channel_id=c.channel_id AND newer.version>c.version)
  AND NOT EXISTS (SELECT 1 FROM acoa.employer_verification_versions newer
      WHERE newer.verification_id=v.verification_id AND newer.version>v.version)
"""


class ProductionTargetRepository:
    """Records immutable enrollments after rechecking every trusted source record."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record(self, enrollment: ProductionRecipientEnrollment) -> None:
        if not isinstance(enrollment, ProductionRecipientEnrollment):
            raise DatabaseBoundaryError("A validated production recipient enrollment is required.")
        _, authority = AuthorityStore(self.connection).lock_current()
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        grant = authority.grant
        if (
            grant is None
            or grant.grant_id != enrollment.grant_id
            or grant.version != enrollment.grant_version
            or enrollment.recipient_class not in grant.recipient_classes
            or not grant_is_active(grant, now)
        ):
            raise DatabaseBoundaryError("Recipient enrollment requires the current active grant.")
        source = self._source(enrollment)
        self._validate_source(enrollment, source, now, grant.expires_at)
        if self._company_is_blocked(enrollment.organization_id, now):
            raise DatabaseBoundaryError(
                "Recipient enrollment is blocked by company contact control."
            )
        self._insert(enrollment)

    def _source(self, enrollment: ProductionRecipientEnrollment) -> RowMapping:
        row = (
            self.connection.execute(
                text(_ENROLLMENT_SOURCE),
                {
                    "target": enrollment.target_id,
                    "target_version": enrollment.target_version,
                    "channel": enrollment.channel_id,
                    "channel_version": enrollment.channel_version,
                    "verification": enrollment.employer_verification_id,
                    "verification_version": enrollment.employer_verification_version,
                },
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatabaseBoundaryError("Recipient enrollment evidence is incomplete.")
        return row

    def _validate_source(
        self,
        enrollment: ProductionRecipientEnrollment,
        source: RowMapping,
        now: datetime,
        grant_expires_at: datetime,
    ) -> None:
        expected_target_kind, expected_channel_kind, allowed_purposes = _class_rules(
            enrollment.recipient_class
        )
        if (
            source["target_kind"] != expected_target_kind
            or source["target_status"] != "active"
            or source["target_organization_id"] != enrollment.organization_id
            or source["target_content_sha256"] != enrollment.target_content_sha256
            or source["channel_organization_id"] != enrollment.organization_id
            or source["channel_kind"] != expected_channel_kind
            or source["endpoint_sha256"] != enrollment.endpoint_sha256
            or source["channel_content_sha256"] != enrollment.channel_content_sha256
            or source["eligible_for_initial_contact"] is not True
            or source["channel_visibility"] != "public_corporate"
            or source["channel_purpose"] not in allowed_purposes
            or source["verification_organization_id"] != enrollment.organization_id
            or source["verification_status"] != "verified"
            or source["verification_content_sha256"] != enrollment.employer_verification_sha256
        ):
            raise DatabaseBoundaryError("Recipient enrollment evidence is outside approved scope.")
        deadlines = (
            grant_expires_at,
            cast(datetime, source["target_valid_until"]),
            cast(datetime, source["channel_valid_until"]),
            cast(datetime, source["verification_valid_until"]),
        )
        observations = (
            cast(datetime, source["target_observed_at"]),
            cast(datetime, source["channel_observed_at"]),
            cast(datetime, source["assessed_at"]),
        )
        if (
            any(observed_at > now for observed_at in observations)
            or any(now >= deadline for deadline in deadlines)
            or enrollment.enrolled_at < max(observations)
            or enrollment.enrolled_at > now
            or enrollment.valid_until > min(deadlines)
        ):
            raise DatabaseBoundaryError("Recipient enrollment requires current bounded evidence.")

    def _company_is_blocked(self, organization_id: UUID, now: datetime) -> bool:
        return cast(
            bool,
            self.connection.execute(
                text("""SELECT EXISTS (
                    SELECT 1 FROM (
                        SELECT DISTINCT ON (actor) actor, action
                        FROM acoa.company_contact_control_events
                        WHERE organization_id = :organization AND effective_at <= :now
                        ORDER BY actor, sequence DESC
                    ) latest WHERE action = 'block'
                )"""),
                {"organization": organization_id, "now": now},
            ).scalar_one(),
        )

    def _insert(self, enrollment: ProductionRecipientEnrollment) -> None:
        payload = encode_record(asdict(enrollment))
        record_sha256 = sha256(payload.encode("utf-8")).hexdigest()
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.production_recipient_enrollments
                (enrollment_id,recipient_id,recipient_class,grant_id,grant_version,
                 organization_id,target_id,target_version,target_content_sha256,
                 channel_id,channel_version,channel_content_sha256,endpoint_sha256,
                 employer_verification_id,employer_verification_version,
                 employer_verification_sha256,enrolled_at,valid_until,content_sha256,
                 enrollment,record_sha256)
                VALUES (:enrollment,:recipient,:recipient_class,:grant,:grant_version,
                 :organization,:target,:target_version,:target_content,:channel,
                 :channel_version,:channel_content,:endpoint,:verification,
                 :verification_version,:verification_content,:enrolled_at,:valid_until,
                 :content,CAST(:payload AS jsonb),:record)
                ON CONFLICT DO NOTHING RETURNING enrollment_id"""),
            {
                "enrollment": enrollment.enrollment_id,
                "recipient": enrollment.recipient_id,
                "recipient_class": enrollment.recipient_class.value,
                "grant": enrollment.grant_id,
                "grant_version": enrollment.grant_version,
                "organization": enrollment.organization_id,
                "target": enrollment.target_id,
                "target_version": enrollment.target_version,
                "target_content": enrollment.target_content_sha256,
                "channel": enrollment.channel_id,
                "channel_version": enrollment.channel_version,
                "channel_content": enrollment.channel_content_sha256,
                "endpoint": enrollment.endpoint_sha256,
                "verification": enrollment.employer_verification_id,
                "verification_version": enrollment.employer_verification_version,
                "verification_content": enrollment.employer_verification_sha256,
                "enrolled_at": enrollment.enrolled_at,
                "valid_until": enrollment.valid_until,
                "content": enrollment.content_sha256,
                "payload": payload,
                "record": record_sha256,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT record_sha256,enrollment
                FROM acoa.production_recipient_enrollments WHERE enrollment_id=:id"""),
            {"id": enrollment.enrollment_id},
        ).one_or_none()
        if prior is None or prior[0] != record_sha256 or prior[1] != json.loads(payload):
            raise DatabaseBoundaryError(
                "A production recipient enrollment must retain its exact content."
            )


def _class_rules(recipient_class: RecipientClass) -> tuple[str, str, frozenset[str]]:
    if recipient_class is RecipientClass.VERIFIED_OFFICIAL_APPLICATION_EMAIL:
        return "published_job", "general_application_email", frozenset({"general_application"})
    if recipient_class is RecipientClass.VERIFIED_PUBLIC_CORPORATE_RECRUITING_CONTACT:
        return (
            "unadvertised_prospect",
            "public_corporate_email",
            frozenset({"recruiting", "human_resources", "relevant_department"}),
        )
    raise DatabaseBoundaryError("The production recipient class is unsupported.")
