"""Evidence-bound organizations, opportunities and professional contact channels."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.discovery import SourceSnapshot
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class OpportunityKind(StrEnum):
    PUBLISHED_JOB = "published_job"
    UNADVERTISED_PROSPECT = "unadvertised_prospect"


class OpportunityStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REMOVED = "removed"
    UNVERIFIED = "unverified"


class FieldConfidence(StrEnum):
    SOURCE_SUPPORTED = "source_supported"
    CONFLICTING = "conflicting"
    MISSING = "missing"


class ContactChannelKind(StrEnum):
    CAREER_PORTAL = "career_portal"
    GENERAL_APPLICATION_EMAIL = "general_application_email"
    PUBLIC_CORPORATE_EMAIL = "public_corporate_email"
    CAREER_CONTACT_FORM = "career_contact_form"
    SUPPORT_FORM = "support_form"


class ContactVisibility(StrEnum):
    PUBLIC_CORPORATE = "public_corporate"
    PUBLIC_PROFESSIONAL = "public_professional"
    PRIVATE_PERSONAL = "private_personal"
    UNKNOWN = "unknown"


class ContactPurpose(StrEnum):
    RECRUITING = "recruiting"
    HUMAN_RESOURCES = "human_resources"
    RELEVANT_DEPARTMENT = "relevant_department"
    GENERAL_APPLICATION = "general_application"
    SUPPORT = "support"
    OTHER = "other"


class ContactResearchStatus(StrEnum):
    VERIFIED_CHANNELS = "verified_channels"
    NO_SUITABLE_CHANNEL = "no_suitable_channel"
    NO_CHANNEL = "no_channel"


def _require_bounded_text(value: object, maximum: int = 4096) -> None:
    require_text(value)
    if not isinstance(value, str) or len(value) > maximum:
        raise DomainError("Research text exceeds its bounded contract.")


@dataclass(frozen=True, slots=True)
class ResearchEvidence:
    snapshot_id: UUID
    source_id: UUID = field(repr=False)
    resource_sha256: str
    content_sha256: str
    observed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        require_identifier(self.snapshot_id)
        require_identifier(self.source_id)
        require_sha256(self.resource_sha256)
        require_sha256(self.content_sha256)
        require_timestamp(self.observed_at)
        require_timestamp(self.valid_until)
        if self.valid_until <= self.observed_at:
            raise DomainError("Research evidence requires a future validity bound.")


def evidence_from_snapshot(snapshot: SourceSnapshot) -> ResearchEvidence:
    if not isinstance(snapshot, SourceSnapshot):
        raise DomainError("Research evidence requires a validated source snapshot.")
    return ResearchEvidence(
        snapshot.snapshot_id,
        snapshot.resource.source_id,
        snapshot.resource.canonical_sha256,
        snapshot.content_sha256,
        snapshot.observed_at,
        snapshot.valid_until,
    )


def evidence_is_current(evidence: ResearchEvidence, now: datetime) -> bool:
    require_timestamp(now)
    return (
        isinstance(evidence, ResearchEvidence)
        and evidence.observed_at <= now < evidence.valid_until
    )


@dataclass(frozen=True, slots=True)
class Organization:
    organization_id: UUID
    identity_sha256: str
    legal_name: str
    canonical_domain: str
    official_url: str = field(repr=False)
    verified_email_domains: tuple[str, ...]
    verified_channel_hosts: tuple[str, ...]
    evidence: ResearchEvidence
    observed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.organization_id)
        require_sha256(self.identity_sha256)
        _require_bounded_text(self.legal_name, 512)
        _require_bounded_text(self.canonical_domain, 253)
        _require_bounded_text(self.official_url)
        for scope in (self.verified_email_domains, self.verified_channel_hosts):
            if not isinstance(scope, tuple) or not scope:
                raise DomainError("An organization requires immutable verified domain scopes.")
            if len(set(scope)) != len(scope):
                raise DomainError("Verified organization domain scopes must not repeat values.")
            for domain in scope:
                _require_bounded_text(domain, 253)
                if domain != domain.lower() or domain.endswith("."):
                    raise DomainError("Verified organization domains must be canonical lowercase.")
        if self.canonical_domain not in self.verified_email_domains:
            raise DomainError("The canonical organization domain must be email-verified.")
        if self.canonical_domain not in self.verified_channel_hosts:
            raise DomainError("The canonical organization domain must be channel-verified.")
        if self.identity_sha256 != organization_identity_sha256(self.canonical_domain):
            raise DomainError("Organization identity must bind its canonical domain.")
        if not isinstance(self.evidence, ResearchEvidence):
            raise DomainError("An organization requires source evidence.")
        require_timestamp(self.observed_at)
        if self.observed_at != self.evidence.observed_at:
            raise DomainError("Organization observation must bind its evidence time.")


def organization_identity_sha256(canonical_domain: str) -> str:
    _require_bounded_text(canonical_domain, 253)
    if canonical_domain != canonical_domain.lower() or canonical_domain.endswith("."):
        raise DomainError("Organization identity requires a canonical domain.")
    return content_digest({"schema": "acoa-organization/1", "domain": canonical_domain})


@dataclass(frozen=True, slots=True)
class OpportunityField:
    name: str
    value: str | None = field(repr=False)
    confidence: FieldConfidence
    evidence: ResearchEvidence | None = None

    def __post_init__(self) -> None:
        _require_bounded_text(self.name, 100)
        if not isinstance(self.confidence, FieldConfidence):
            raise DomainError("An opportunity field requires explicit confidence.")
        if self.value is None:
            if self.confidence is not FieldConfidence.MISSING or self.evidence is not None:
                raise DomainError("A missing opportunity field cannot claim source evidence.")
            return
        _require_bounded_text(self.value)
        if self.confidence is FieldConfidence.MISSING or not isinstance(
            self.evidence, ResearchEvidence
        ):
            raise DomainError("An observed opportunity field requires source evidence.")


@dataclass(frozen=True, slots=True)
class Opportunity:
    opportunity_id: UUID
    version: int
    identity_sha256: str
    content_sha256: str
    organization_id: UUID
    kind: OpportunityKind
    status: OpportunityStatus
    source_resource_sha256: str
    fields: tuple[OpportunityField, ...]
    publication_evidence: ResearchEvidence
    observed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.opportunity_id)
        require_identifier(self.organization_id)
        require_version(self.version)
        require_sha256(self.identity_sha256)
        require_sha256(self.content_sha256)
        require_sha256(self.source_resource_sha256)
        if not isinstance(self.kind, OpportunityKind) or not isinstance(
            self.status, OpportunityStatus
        ):
            raise DomainError("An opportunity requires explicit kind and status.")
        if not isinstance(self.fields, tuple) or not self.fields:
            raise DomainError("An opportunity requires immutable sourced fields.")
        if any(not isinstance(item, OpportunityField) for item in self.fields):
            raise DomainError("Opportunity fields must be validated.")
        names = tuple(item.name for item in self.fields)
        if len(set(names)) != len(names):
            raise DomainError("An opportunity must not repeat a field name.")
        if not isinstance(self.publication_evidence, ResearchEvidence):
            raise DomainError("An opportunity requires publication or prospect evidence.")
        require_timestamp(self.observed_at)
        if self.observed_at != self.publication_evidence.observed_at:
            raise DomainError("Opportunity observation must bind publication evidence time.")
        if self.kind is OpportunityKind.UNADVERTISED_PROSPECT:
            if self.status is not OpportunityStatus.UNVERIFIED:
                raise DomainError("An unadvertised prospect cannot claim an active listing.")
            forbidden = {"application_url", "deadline"}
            if any(item.name in forbidden and item.value is not None for item in self.fields):
                raise DomainError("An unadvertised prospect cannot claim listing-only fields.")
        if self.content_sha256 != opportunity_content_sha256(
            self.identity_sha256, self.version, self.status, self.fields
        ):
            raise DomainError("Opportunity content digest must bind its exact version and fields.")


def opportunity_content_sha256(
    identity_sha256: str,
    version: int,
    status: OpportunityStatus,
    fields: tuple[OpportunityField, ...],
) -> str:
    require_sha256(identity_sha256)
    require_version(version)
    return content_digest(
        {
            "schema": "acoa-opportunity-content/1",
            "identity_sha256": identity_sha256,
            "version": version,
            "status": status.value,
            "fields": [
                {
                    "name": item.name,
                    "value": item.value,
                    "confidence": item.confidence.value,
                    "evidence_content_sha256": (
                        item.evidence.content_sha256 if item.evidence is not None else None
                    ),
                }
                for item in sorted(fields, key=lambda field: field.name)
            ],
        }
    )


@dataclass(frozen=True, slots=True)
class ContactChannel:
    channel_id: UUID
    version: int
    organization_id: UUID
    kind: ContactChannelKind
    endpoint_sha256: str
    content_sha256: str
    endpoint: str = field(repr=False)
    visibility: ContactVisibility
    purpose: ContactPurpose
    eligible_for_initial_contact: bool
    professional_name: str | None = field(default=None, repr=False)
    professional_role: str | None = None
    evidence: ResearchEvidence | None = None

    def __post_init__(self) -> None:
        require_identifier(self.channel_id)
        require_version(self.version)
        require_identifier(self.organization_id)
        require_sha256(self.endpoint_sha256)
        require_sha256(self.content_sha256)
        _require_bounded_text(self.endpoint)
        if not isinstance(self.kind, ContactChannelKind):
            raise DomainError("A contact channel requires an explicit kind.")
        if self.visibility not in (
            ContactVisibility.PUBLIC_CORPORATE,
            ContactVisibility.PUBLIC_PROFESSIONAL,
        ):
            raise DomainError("Private, unknown or personal contact channels are prohibited.")
        if not isinstance(self.purpose, ContactPurpose) or not isinstance(
            self.eligible_for_initial_contact, bool
        ):
            raise DomainError("A contact channel requires explicit purpose and eligibility.")
        if not isinstance(self.evidence, ResearchEvidence):
            raise DomainError("A contact channel requires public source evidence.")
        if (self.professional_name is None) != (self.professional_role is None):
            raise DomainError(
                "A named professional contact requires an explicit professional role."
            )
        for value in (self.professional_name, self.professional_role):
            if value is not None:
                _require_bounded_text(value, 512)
        suitable = (
            self.purpose
            in (
                ContactPurpose.RECRUITING,
                ContactPurpose.HUMAN_RESOURCES,
                ContactPurpose.RELEVANT_DEPARTMENT,
                ContactPurpose.GENERAL_APPLICATION,
            )
            and self.kind is not ContactChannelKind.SUPPORT_FORM
        )
        if self.eligible_for_initial_contact != suitable:
            raise DomainError("Contact eligibility must follow the deterministic purpose rule.")
        if self.content_sha256 != contact_channel_binding_sha256(
            self.channel_id,
            self.version,
            self.organization_id,
            self.kind,
            self.endpoint_sha256,
            self.visibility,
            self.purpose,
            self.eligible_for_initial_contact,
            self.professional_name,
            self.professional_role,
            self.evidence,
        ):
            raise DomainError("Contact channel digest must bind its exact version and evidence.")


def contact_channel_binding_sha256(
    channel_id: UUID,
    version: int,
    organization_id: UUID,
    kind: ContactChannelKind,
    endpoint_sha256: str,
    visibility: ContactVisibility,
    purpose: ContactPurpose,
    eligible: bool,
    professional_name: str | None,
    professional_role: str | None,
    evidence: ResearchEvidence,
) -> str:
    return content_digest(
        {
            "schema": "acoa-contact-channel/1",
            "channel_id": str(channel_id),
            "version": version,
            "organization_id": str(organization_id),
            "kind": kind.value,
            "endpoint_sha256": endpoint_sha256,
            "visibility": visibility.value,
            "purpose": purpose.value,
            "eligible": eligible,
            "professional_name": professional_name,
            "professional_role": professional_role,
            "evidence_content_sha256": evidence.content_sha256,
        }
    )


@dataclass(frozen=True, slots=True)
class ContactResearch:
    research_id: UUID
    organization_id: UUID
    status: ContactResearchStatus
    channels: tuple[ContactChannel, ...]
    rejection_codes: tuple[str, ...]
    observed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.research_id)
        require_identifier(self.organization_id)
        if not isinstance(self.status, ContactResearchStatus):
            raise DomainError("Contact research requires an explicit result status.")
        if not isinstance(self.channels, tuple) or any(
            not isinstance(channel, ContactChannel) for channel in self.channels
        ):
            raise DomainError("Contact research requires immutable validated channels.")
        if any(channel.organization_id != self.organization_id for channel in self.channels):
            raise DomainError("Every contact channel must belong to the researched organization.")
        if len({(channel.channel_id, channel.version) for channel in self.channels}) != len(
            self.channels
        ):
            raise DomainError("Contact research must not repeat a channel.")
        if not isinstance(self.rejection_codes, tuple) or any(
            not isinstance(code, str) or not code for code in self.rejection_codes
        ):
            raise DomainError("Contact rejection reasons require immutable structured codes.")
        if len(set(self.rejection_codes)) != len(self.rejection_codes):
            raise DomainError("Contact rejection reason codes must not repeat.")
        require_timestamp(self.observed_at)
        has_eligible = any(channel.eligible_for_initial_contact for channel in self.channels)
        expected = (
            ContactResearchStatus.VERIFIED_CHANNELS
            if has_eligible
            else ContactResearchStatus.NO_SUITABLE_CHANNEL
            if self.channels
            else ContactResearchStatus.NO_CHANNEL
        )
        if self.status is not expected:
            raise DomainError("Contact research status must follow its accepted channel set.")
