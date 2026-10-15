"""Deterministic normalization for sourced opportunities and corporate channels."""

import re
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from ipaddress import ip_address
from urllib.parse import urlsplit, urlunsplit
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from acoa.domain.research import (
    ContactChannel,
    ContactChannelKind,
    ContactPurpose,
    ContactResearch,
    ContactResearchStatus,
    ContactVisibility,
    Opportunity,
    OpportunityField,
    OpportunityKind,
    OpportunityStatus,
    Organization,
    ResearchEvidence,
    contact_channel_binding_sha256,
    evidence_is_current,
    opportunity_content_sha256,
    organization_identity_sha256,
)
from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_timestamp

_DOMAIN_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?")
_EMAIL_LOCAL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+")


@dataclass(frozen=True, slots=True)
class ContactCandidate:
    kind: ContactChannelKind
    endpoint: str = field(repr=False)
    visibility: ContactVisibility
    purpose: ContactPurpose
    source_observed: bool
    evidence: ResearchEvidence
    version: int = 1
    professional_name: str | None = field(default=None, repr=False)
    professional_role: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, ContactChannelKind)
            or not isinstance(self.visibility, ContactVisibility)
            or not isinstance(self.purpose, ContactPurpose)
            or not isinstance(self.source_observed, bool)
            or not isinstance(self.evidence, ResearchEvidence)
        ):
            raise DomainError("A contact candidate requires explicit typed source context.")
        if not isinstance(self.endpoint, str) or not self.endpoint or len(self.endpoint) > 4096:
            raise DomainError("A contact candidate endpoint must be bounded text.")
        if (self.professional_name is None) != (self.professional_role is None):
            raise DomainError("A named contact candidate requires a professional role.")
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DomainError("A contact candidate requires a positive version.")


def _canonical_domain(value: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 253:
        raise DomainError("A verified organization domain must be bounded canonical text.")
    try:
        domain = value.encode("idna").decode("ascii").lower().rstrip(".")
        ip_address(domain)
    except UnicodeError as error:
        raise DomainError("A verified organization domain is malformed.") from error
    except ValueError:
        pass
    else:
        raise DomainError("An organization domain cannot be an IP address.")
    labels = domain.split(".")
    if "." not in domain or any(_DOMAIN_LABEL.fullmatch(label) is None for label in labels):
        raise DomainError("A verified organization domain requires a public-style hostname.")
    return domain


def _canonical_https_url(value: str, allowed_hosts: tuple[str, ...]) -> str:
    if not isinstance(value, str) or not value or value != value.strip() or len(value) > 4096:
        raise DomainError("A research URL must be bounded canonical text.")
    try:
        parsed = urlsplit(value)
        host = parsed.hostname
        port = parsed.port
    except ValueError as error:
        raise DomainError("A research URL is malformed.") from error
    if (
        parsed.scheme != "https"
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or port not in (None, 443)
    ):
        raise DomainError("Research URLs require HTTPS without credentials, query or fragments.")
    canonical_host = _canonical_domain(host)
    if canonical_host not in allowed_hosts:
        raise DomainError("A research URL host lacks verified organization evidence.")
    return urlunsplit(("https", canonical_host, parsed.path or "/", "", ""))


def create_organization(
    legal_name: str,
    canonical_domain: str,
    official_url: str,
    verified_email_domains: tuple[str, ...],
    verified_channel_hosts: tuple[str, ...],
    evidence: ResearchEvidence,
    now: datetime,
) -> Organization:
    require_timestamp(now)
    if not evidence_is_current(evidence, now):
        raise DomainError("Organization evidence is stale or future-dated.")
    domain = _canonical_domain(canonical_domain)
    email_domains = tuple(_canonical_domain(item) for item in verified_email_domains)
    channel_hosts = tuple(_canonical_domain(item) for item in verified_channel_hosts)
    url = _canonical_https_url(official_url, channel_hosts)
    identity = organization_identity_sha256(domain)
    return Organization(
        uuid5(NAMESPACE_URL, f"acoa:organization:{identity}"),
        identity,
        legal_name,
        domain,
        url,
        email_domains,
        channel_hosts,
        evidence,
        evidence.observed_at,
    )


def normalize_opportunity(
    organization: Organization,
    kind: OpportunityKind,
    status: OpportunityStatus,
    source_resource_sha256: str,
    fields: tuple[OpportunityField, ...],
    publication_evidence: ResearchEvidence,
    version: int,
    now: datetime,
) -> Opportunity:
    require_timestamp(now)
    _require_opportunity_evidence(
        organization, source_resource_sha256, fields, publication_evidence, now
    )
    if kind is OpportunityKind.PUBLISHED_JOB:
        _require_published_fields(organization, fields)
    seed = _opportunity_seed(organization, kind, source_resource_sha256, fields)
    identity = content_digest(
        {
            "schema": "acoa-opportunity/1",
            "organization": organization.identity_sha256,
            "kind": kind.value,
            "seed": seed,
        }
    )
    content = opportunity_content_sha256(identity, version, status, fields)
    return Opportunity(
        uuid5(NAMESPACE_URL, f"acoa:opportunity:{identity}"),
        version,
        identity,
        content,
        organization.organization_id,
        kind,
        status,
        source_resource_sha256,
        fields,
        publication_evidence,
        publication_evidence.observed_at,
    )


def _require_opportunity_evidence(
    organization: Organization,
    source_resource_sha256: str,
    fields: tuple[OpportunityField, ...],
    publication_evidence: ResearchEvidence,
    now: datetime,
) -> None:
    if not isinstance(organization, Organization) or not evidence_is_current(
        publication_evidence, now
    ):
        raise DomainError("Opportunity normalization requires current organization evidence.")
    if publication_evidence.resource_sha256 != source_resource_sha256:
        raise DomainError("Opportunity evidence must bind its source resource.")
    if not isinstance(fields, tuple) or any(
        not isinstance(item, OpportunityField) for item in fields
    ):
        raise DomainError("Opportunity normalization requires immutable sourced fields.")
    if any(
        item.evidence is not None and not evidence_is_current(item.evidence, now) for item in fields
    ):
        raise DomainError("Opportunity fields require current source evidence.")


def _require_published_fields(
    organization: Organization, fields: tuple[OpportunityField, ...]
) -> None:
    values = {item.name: item.value for item in fields}
    required = ("employer", "role_title", "application_url")
    if any(not values.get(name) for name in required):
        raise DomainError("A published job requires sourced employer, role and application URL.")
    application_url = values["application_url"]
    assert application_url is not None
    if (
        _canonical_https_url(application_url, organization.verified_channel_hosts)
        != application_url
    ):
        raise DomainError("A published application URL must use canonical verified form.")


def _opportunity_seed(
    organization: Organization,
    kind: OpportunityKind,
    source_resource_sha256: str,
    fields: tuple[OpportunityField, ...],
) -> str:
    return (
        source_resource_sha256
        if kind is OpportunityKind.PUBLISHED_JOB
        else content_digest(
            {
                "organization": organization.identity_sha256,
                "role_context": next(
                    (item.value for item in fields if item.name == "role_context"), None
                ),
            }
        )
    )


def _canonical_email(value: str, organization: Organization) -> str:
    if not isinstance(value, str) or value != value.strip() or value.count("@") != 1:
        raise DomainError("A corporate email candidate is malformed.")
    local, raw_domain = value.rsplit("@", 1)
    if (
        not local
        or len(value) > 320
        or _EMAIL_LOCAL.fullmatch(local) is None
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
    ):
        raise DomainError("A corporate email candidate is malformed.")
    domain = _canonical_domain(raw_domain)
    if domain not in organization.verified_email_domains:
        raise DomainError("A contact email domain lacks organization verification.")
    return f"{local}@{domain}"


def _normalize_contact_endpoint(candidate: ContactCandidate, organization: Organization) -> str:
    if candidate.kind in (
        ContactChannelKind.GENERAL_APPLICATION_EMAIL,
        ContactChannelKind.PUBLIC_CORPORATE_EMAIL,
    ):
        return _canonical_email(candidate.endpoint, organization)
    return _canonical_https_url(candidate.endpoint, organization.verified_channel_hosts)


def _candidate_rejection_code(
    candidate: ContactCandidate, organization: Organization, now: datetime
) -> str | None:
    if not isinstance(candidate, ContactCandidate):
        return "invalid_candidate"
    if not candidate.source_observed:
        return "inferred_endpoint_prohibited"
    if candidate.visibility is ContactVisibility.PRIVATE_PERSONAL:
        return "private_personal_contact_prohibited"
    if candidate.visibility is ContactVisibility.UNKNOWN:
        return "unknown_contact_visibility"
    if not evidence_is_current(candidate.evidence, now):
        return "stale_contact_evidence"
    try:
        _normalize_contact_endpoint(candidate, organization)
    except DomainError:
        return "unverified_contact_endpoint"
    return None


def research_contact_channels(
    organization: Organization,
    candidates: tuple[ContactCandidate, ...],
    now: datetime,
    identifier_factory: Callable[[], UUID] = uuid4,
) -> ContactResearch:
    require_timestamp(now)
    if not isinstance(organization, Organization) or not isinstance(candidates, tuple):
        raise DomainError("Contact research requires an organization and immutable candidates.")
    channels: list[ContactChannel] = []
    rejection_codes: set[str] = set()
    for candidate in candidates:
        rejection = _candidate_rejection_code(candidate, organization, now)
        if rejection is not None:
            rejection_codes.add(rejection)
            continue
        channels.append(_channel_from_candidate(candidate, organization))
    ordered = _deduplicate_channels(channels)
    return ContactResearch(
        identifier_factory(),
        organization.organization_id,
        _contact_research_status(ordered),
        ordered,
        tuple(sorted(rejection_codes)),
        now,
    )


def _channel_from_candidate(
    candidate: ContactCandidate, organization: Organization
) -> ContactChannel:
    endpoint = _normalize_contact_endpoint(candidate, organization)
    endpoint_hash = sha256(endpoint.encode("utf-8")).hexdigest()
    eligible = (
        candidate.purpose
        in (
            ContactPurpose.RECRUITING,
            ContactPurpose.HUMAN_RESOURCES,
            ContactPurpose.RELEVANT_DEPARTMENT,
            ContactPurpose.GENERAL_APPLICATION,
        )
        and candidate.kind is not ContactChannelKind.SUPPORT_FORM
    )
    channel_id = uuid5(
        NAMESPACE_URL,
        f"acoa:contact:{organization.identity_sha256}:{candidate.kind.value}:{endpoint_hash}",
    )
    return ContactChannel(
        channel_id=channel_id,
        version=candidate.version,
        organization_id=organization.organization_id,
        kind=candidate.kind,
        endpoint_sha256=endpoint_hash,
        content_sha256=contact_channel_binding_sha256(
            channel_id,
            candidate.version,
            organization.organization_id,
            candidate.kind,
            endpoint_hash,
            candidate.visibility,
            candidate.purpose,
            eligible,
            candidate.professional_name,
            candidate.professional_role,
            candidate.evidence,
        ),
        endpoint=endpoint,
        visibility=candidate.visibility,
        purpose=candidate.purpose,
        eligible_for_initial_contact=eligible,
        professional_name=candidate.professional_name,
        professional_role=candidate.professional_role,
        evidence=candidate.evidence,
    )


def _deduplicate_channels(channels: list[ContactChannel]) -> tuple[ContactChannel, ...]:
    unique: dict[tuple[UUID, int], ContactChannel] = {}
    for channel in channels:
        key = (channel.channel_id, channel.version)
        prior = unique.get(key)
        if prior is not None and prior != channel:
            raise DomainError("Conflicting contact candidates reuse one channel version.")
        unique[key] = channel
    return tuple(unique[key] for key in sorted(unique, key=lambda item: (str(item[0]), item[1])))


def _contact_research_status(
    channels: tuple[ContactChannel, ...],
) -> ContactResearchStatus:
    return (
        ContactResearchStatus.VERIFIED_CHANNELS
        if any(channel.eligible_for_initial_contact for channel in channels)
        else ContactResearchStatus.NO_SUITABLE_CHANNEL
        if channels
        else ContactResearchStatus.NO_CHANNEL
    )
