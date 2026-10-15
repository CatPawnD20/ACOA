"""Immutable PostgreSQL persistence for organizations, opportunities and channels."""

import json
from collections.abc import Sequence
from dataclasses import asdict
from hashlib import sha256

from sqlalchemy import text
from sqlalchemy.engine import Connection

from acoa.domain.research import ContactChannel, ContactResearch, Opportunity, Organization
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


def _encoded(
    value: Organization | Opportunity | ContactChannel | ContactResearch,
) -> tuple[str, str]:
    payload = encode_record(asdict(value))
    return payload, sha256(payload.encode("utf-8")).hexdigest()


def _require_exact(prior: Sequence[object] | None, digest: str, payload: str, message: str) -> None:
    if prior is None:
        raise DatabaseBoundaryError("An immutable research record disappeared after conflict.")
    if prior[0] != digest or prior[1] != json.loads(payload):
        raise DatabaseBoundaryError(message)


class ResearchRecordRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def record_organization(self, organization: Organization) -> None:
        if not isinstance(organization, Organization):
            raise DatabaseBoundaryError("A validated organization is required.")
        payload, digest = _encoded(organization)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.organizations
                (organization_id,identity_sha256,canonical_domain,observed_at,
                 organization,record_sha256)
                VALUES (:id,:identity,:domain,:observed,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (organization_id) DO NOTHING RETURNING organization_id"""),
            {
                "id": organization.organization_id,
                "identity": organization.identity_sha256,
                "domain": organization.canonical_domain,
                "observed": organization.observed_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text(
                """SELECT record_sha256,organization FROM acoa.organizations
                WHERE organization_id=:id"""
            ),
            {"id": organization.organization_id},
        ).one_or_none()
        _require_exact(prior, digest, payload, "An organization identity must remain immutable.")

    def record_opportunity(self, opportunity: Opportunity) -> None:
        if not isinstance(opportunity, Opportunity):
            raise DatabaseBoundaryError("A validated opportunity is required.")
        payload, _ = _encoded(opportunity)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.opportunity_versions
                (opportunity_id,version,identity_sha256,content_sha256,organization_id,
                 kind,status,source_resource_sha256,observed_at,opportunity)
                VALUES (:id,:version,:identity,:content,:organization,:kind,:status,
                    :resource,:observed,CAST(:payload AS jsonb))
                ON CONFLICT (opportunity_id,version) DO NOTHING RETURNING opportunity_id"""),
            {
                "id": opportunity.opportunity_id,
                "version": opportunity.version,
                "identity": opportunity.identity_sha256,
                "content": opportunity.content_sha256,
                "organization": opportunity.organization_id,
                "kind": opportunity.kind.value,
                "status": opportunity.status.value,
                "resource": opportunity.source_resource_sha256,
                "observed": opportunity.observed_at,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT content_sha256,opportunity FROM acoa.opportunity_versions
                WHERE opportunity_id=:id AND version=:version"""),
            {"id": opportunity.opportunity_id, "version": opportunity.version},
        ).one_or_none()
        _require_exact(
            prior,
            opportunity.content_sha256,
            payload,
            "An opportunity version must retain its exact sourced fields.",
        )

    def record_contact_research(self, research: ContactResearch) -> None:
        if not isinstance(research, ContactResearch):
            raise DatabaseBoundaryError("Validated contact research is required.")
        for channel in research.channels:
            self._record_channel(channel)
        payload, digest = _encoded(research)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.contact_research
                (research_id,organization_id,status,observed_at,research,record_sha256)
                VALUES (:id,:organization,:status,:observed,CAST(:payload AS jsonb),:digest)
                ON CONFLICT (research_id) DO NOTHING RETURNING research_id"""),
            {
                "id": research.research_id,
                "organization": research.organization_id,
                "status": research.status.value,
                "observed": research.observed_at,
                "payload": payload,
                "digest": digest,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("SELECT record_sha256,research FROM acoa.contact_research WHERE research_id=:id"),
            {"id": research.research_id},
        ).one_or_none()
        _require_exact(prior, digest, payload, "A contact research result must remain immutable.")

    def _record_channel(self, channel: ContactChannel) -> None:
        payload, _ = _encoded(channel)
        inserted = self.connection.execute(
            text("""INSERT INTO acoa.contact_channel_versions
                (channel_id,version,organization_id,kind,endpoint_sha256,content_sha256,
                 eligible_for_initial_contact,channel)
                VALUES (:id,:version,:organization,:kind,:endpoint,:content,:eligible,
                    CAST(:payload AS jsonb))
                ON CONFLICT (channel_id,version) DO NOTHING RETURNING channel_id"""),
            {
                "id": channel.channel_id,
                "version": channel.version,
                "organization": channel.organization_id,
                "kind": channel.kind.value,
                "endpoint": channel.endpoint_sha256,
                "content": channel.content_sha256,
                "eligible": channel.eligible_for_initial_contact,
                "payload": payload,
            },
        ).scalar_one_or_none()
        if inserted is not None:
            return
        prior = self.connection.execute(
            text("""SELECT content_sha256,channel FROM acoa.contact_channel_versions
                WHERE channel_id=:id AND version=:version"""),
            {"id": channel.channel_id, "version": channel.version},
        ).one_or_none()
        _require_exact(
            prior,
            channel.content_sha256,
            payload,
            "A contact channel version must retain its exact source and purpose.",
        )
