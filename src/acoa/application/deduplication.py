"""Conservative multi-source deduplication and authorized source fallback; EP-04.04."""

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from acoa.domain.deduplication import (
    AliasRelation,
    DeduplicationDecision,
    DeduplicationOutcome,
    EntityKind,
    FallbackStatus,
    MatchBasis,
    SourceFallbackPlan,
    deduplication_binding_sha256,
    source_fallback_binding_sha256,
)
from acoa.domain.discovery import (
    DiscoveryQuery,
    SourceAccessPermit,
    SourceKind,
    SourceObservation,
    SourceOperation,
    SourcePolicy,
    source_access_is_current,
)
from acoa.domain.research import Opportunity, Organization, ResearchEvidence, evidence_is_current
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_timestamp,
    require_version,
)


@dataclass(frozen=True, slots=True)
class OrganizationAliasClaim:
    left_organization_id: UUID
    right_organization_id: UUID
    relation: AliasRelation
    evidence: ResearchEvidence

    def __post_init__(self) -> None:
        require_identifier(self.left_organization_id)
        require_identifier(self.right_organization_id)
        if not isinstance(self.relation, AliasRelation) or not isinstance(
            self.evidence, ResearchEvidence
        ):
            raise DomainError("An organization alias claim requires typed source evidence.")


@dataclass(frozen=True, slots=True)
class OpportunityFingerprint:
    opportunity: Opportunity
    external_job_id: str | None
    evidence: ResearchEvidence

    def __post_init__(self) -> None:
        if not isinstance(self.opportunity, Opportunity) or not isinstance(
            self.evidence, ResearchEvidence
        ):
            raise DomainError("An opportunity fingerprint requires a sourced opportunity.")
        if self.evidence.resource_sha256 != self.opportunity.source_resource_sha256:
            raise DomainError("Opportunity fingerprint evidence must bind its source resource.")
        if self.external_job_id is not None and (
            not isinstance(self.external_job_id, str)
            or not self.external_job_id
            or self.external_job_id != self.external_job_id.strip()
            or len(self.external_job_id) > 512
        ):
            raise DomainError("An external job identifier must be bounded exact text.")


def deduplicate_organizations(
    left: Organization,
    right: Organization,
    claim: OrganizationAliasClaim | None,
    now: datetime,
    version: int = 1,
) -> DeduplicationDecision:
    require_timestamp(now)
    require_version(version)
    if not isinstance(left, Organization) or not isinstance(right, Organization):
        raise DomainError("Organization deduplication requires validated organizations.")
    evidence_items = [left.evidence, right.evidence]
    valid_until = min(item.valid_until for item in evidence_items)
    if any(not evidence_is_current(item, now) for item in evidence_items):
        raise DomainError("Organization deduplication requires current source evidence.")
    if left.organization_id == right.organization_id:
        outcome, basis = DeduplicationOutcome.CANONICAL, MatchBasis.SAME_IDENTITY
    elif claim is not None:
        _validate_alias_claim(claim, left, right, now)
        evidence_items.append(claim.evidence)
        valid_until = min(valid_until, claim.evidence.valid_until)
        outcome, basis = _alias_outcome(claim.relation)
    elif _normalized(left.legal_name) == _normalized(right.legal_name):
        outcome, basis = (
            DeduplicationOutcome.POSSIBLE_DUPLICATE,
            MatchBasis.POSSIBLE_NAME_ALIAS,
        )
    else:
        outcome, basis = DeduplicationOutcome.DISTINCT, MatchBasis.DISTINCT_ATTRIBUTES
    return _decision(
        EntityKind.ORGANIZATION,
        left.organization_id,
        right.organization_id,
        outcome,
        basis,
        tuple(item.content_sha256 for item in evidence_items),
        now,
        valid_until,
        version,
    )


def deduplicate_opportunities(
    left: OpportunityFingerprint,
    right: OpportunityFingerprint,
    organization_decision: DeduplicationDecision | None,
    now: datetime,
    version: int = 1,
) -> DeduplicationDecision:
    require_timestamp(now)
    require_version(version)
    _validate_fingerprint(left, now)
    _validate_fingerprint(right, now)
    opportunities = (left.opportunity, right.opportunity)
    evidence = (left.evidence, right.evidence)
    evidence_sha256 = [item.content_sha256 for item in evidence]
    valid_until = min(item.valid_until for item in evidence)
    same_organization = opportunities[0].organization_id == opportunities[1].organization_id
    if not same_organization:
        same_organization = _organization_decision_matches(
            organization_decision, opportunities, now
        )
        if same_organization and organization_decision is not None:
            valid_until = min(valid_until, organization_decision.valid_until)
            evidence_sha256.append(organization_decision.content_sha256)
    outcome, basis = _opportunity_outcome(left, right, same_organization)
    return _decision(
        EntityKind.OPPORTUNITY,
        opportunities[0].opportunity_id,
        opportunities[1].opportunity_id,
        outcome,
        basis,
        tuple(evidence_sha256),
        now,
        valid_until,
        version,
    )


def choose_alternative_source(
    failed: SourceObservation,
    query: DiscoveryQuery,
    policies: tuple[SourcePolicy, ...],
    permits: tuple[SourceAccessPermit, ...],
    attempted_source_ids: tuple[UUID, ...],
    now: datetime,
) -> SourceFallbackPlan:
    require_timestamp(now)
    if not isinstance(failed, SourceObservation) or not isinstance(query, DiscoveryQuery):
        raise DomainError("Source fallback requires an exact observation and query.")
    if not isinstance(policies, tuple) or any(
        not isinstance(policy, SourcePolicy) for policy in policies
    ):
        raise DomainError("Source fallback requires immutable validated policies.")
    if not isinstance(permits, tuple) or any(
        not isinstance(permit, SourceAccessPermit) for permit in permits
    ):
        raise DomainError("Source fallback requires immutable validated access permits.")
    if failed.operation is not SourceOperation.DISCOVER:
        raise DomainError("A discovery fallback requires a failed discovery observation.")
    if failed.observed_at > now or query.requested_at > now:
        raise DomainError("Source fallback inputs cannot be future-dated.")
    if failed.target_sha256 != query.text_sha256:
        raise DomainError("Source fallback must bind the failed query.")
    attempted = _attempted_sources(failed, attempted_source_ids)
    candidates = _eligible_sources(policies, permits, query, attempted, now)
    selected = candidates[0] if candidates else None
    status = (
        FallbackStatus.SELECTED if selected is not None else FallbackStatus.NO_ALLOWED_ALTERNATIVE
    )
    valid_until = min(selected[0].valid_until, selected[1].expires_at) if selected else now
    plan_id = uuid5(
        NAMESPACE_URL,
        f"acoa:fallback:{failed.observation_id}:{query.text_sha256}:"
        + ",".join(str(item) for item in attempted),
    )
    selected_policy = selected[0] if selected is not None else None
    selected_permit = selected[1] if selected is not None else None
    selected_id = selected_policy.source_id if selected_policy is not None else None
    selected_version = selected_policy.policy_version if selected_policy is not None else None
    selected_kind = selected_policy.kind if selected_policy is not None else None
    selected_permit_id = selected_permit.decision_id if selected_permit is not None else None
    digest = source_fallback_binding_sha256(
        plan_id,
        failed.observation_id,
        failed.source_id,
        failed.status,
        failed.operation,
        query.text_sha256,
        attempted,
        status,
        selected_id,
        selected_version,
        selected_kind,
        selected_permit_id,
        now,
        valid_until,
    )
    return SourceFallbackPlan(
        plan_id,
        failed.observation_id,
        failed.source_id,
        failed.status,
        failed.operation,
        query.text_sha256,
        attempted,
        status,
        selected_id,
        selected_version,
        selected_kind,
        selected_permit_id,
        digest,
        now,
        valid_until,
    )


def _validate_alias_claim(
    claim: OrganizationAliasClaim, left: Organization, right: Organization, now: datetime
) -> None:
    if not isinstance(claim, OrganizationAliasClaim):
        raise DomainError("Organization alias evidence must be validated.")
    if {claim.left_organization_id, claim.right_organization_id} != {
        left.organization_id,
        right.organization_id,
    }:
        raise DomainError("Organization alias evidence targets another pair.")
    if not evidence_is_current(claim.evidence, now):
        raise DomainError("Organization alias evidence is stale or future-dated.")


def _alias_outcome(relation: AliasRelation) -> tuple[DeduplicationOutcome, MatchBasis]:
    if relation is AliasRelation.VERIFIED_SAME_LEGAL_ENTITY:
        return DeduplicationOutcome.CANONICAL, MatchBasis.VERIFIED_LEGAL_ENTITY_ALIAS
    if relation is AliasRelation.POSSIBLE_ALIAS:
        return DeduplicationOutcome.POSSIBLE_DUPLICATE, MatchBasis.POSSIBLE_NAME_ALIAS
    return DeduplicationOutcome.DISTINCT, MatchBasis.DISTINCT_ATTRIBUTES


def _validate_fingerprint(fingerprint: OpportunityFingerprint, now: datetime) -> None:
    if not isinstance(fingerprint, OpportunityFingerprint) or not evidence_is_current(
        fingerprint.evidence, now
    ):
        raise DomainError("Opportunity deduplication requires a current fingerprint.")


def _organization_decision_matches(
    decision: DeduplicationDecision | None,
    opportunities: tuple[Opportunity, Opportunity],
    now: datetime,
) -> bool:
    if decision is None:
        return False
    expected = {item.organization_id for item in opportunities}
    return (
        decision.entity_kind is EntityKind.ORGANIZATION
        and decision.outcome is DeduplicationOutcome.CANONICAL
        and {decision.left_entity_id, decision.right_entity_id} == expected
        and decision.decided_at <= now < decision.valid_until
    )


def _opportunity_outcome(
    left: OpportunityFingerprint,
    right: OpportunityFingerprint,
    same_organization: bool,
) -> tuple[DeduplicationOutcome, MatchBasis]:
    if not same_organization:
        return DeduplicationOutcome.DISTINCT, MatchBasis.CONFLICTING_ORGANIZATION
    if left.opportunity.identity_sha256 == right.opportunity.identity_sha256:
        return DeduplicationOutcome.CANONICAL, MatchBasis.SAME_IDENTITY
    if left.external_job_id is not None and left.external_job_id == right.external_job_id:
        return DeduplicationOutcome.CANONICAL, MatchBasis.SAME_EXTERNAL_JOB_ID
    left_role, right_role = (
        _field(left.opportunity, "role_title"),
        _field(right.opportunity, "role_title"),
    )
    left_location, right_location = (
        _field(left.opportunity, "location"),
        _field(right.opportunity, "location"),
    )
    if (
        left_role == right_role
        and left_location == right_location
        and left_role is not None
        and left_location is not None
    ):
        return DeduplicationOutcome.POSSIBLE_DUPLICATE, MatchBasis.SAME_ROLE_AND_LOCATION
    if left_role == right_role and left_location and right_location:
        return DeduplicationOutcome.DISTINCT, MatchBasis.CONFLICTING_LOCATION
    return DeduplicationOutcome.DISTINCT, MatchBasis.DISTINCT_ATTRIBUTES


def _decision(
    kind: EntityKind,
    left_id: UUID,
    right_id: UUID,
    outcome: DeduplicationOutcome,
    basis: MatchBasis,
    evidence: tuple[str, ...],
    now: datetime,
    valid_until: datetime,
    version: int,
) -> DeduplicationDecision:
    ordered = tuple(sorted((left_id, right_id), key=str))
    hashes = tuple(sorted(set(evidence)))
    decision_id = uuid5(NAMESPACE_URL, f"acoa:dedup:{kind.value}:{ordered[0]}:{ordered[1]}")
    canonical = ordered[0] if outcome is DeduplicationOutcome.CANONICAL else None
    digest = deduplication_binding_sha256(
        decision_id,
        version,
        kind,
        ordered[0],
        ordered[1],
        outcome,
        basis,
        canonical,
        hashes,
        now,
        valid_until,
    )
    return DeduplicationDecision(
        decision_id,
        version,
        kind,
        ordered[0],
        ordered[1],
        outcome,
        basis,
        canonical,
        hashes,
        digest,
        now,
        valid_until,
    )


def _field(opportunity: Opportunity, name: str) -> str | None:
    value = next((item.value for item in opportunity.fields if item.name == name), None)
    return _normalized(value) if value is not None else None


def _normalized(value: str) -> str:
    return " ".join(value.casefold().split())


def _attempted_sources(
    failed: SourceObservation, attempted_source_ids: tuple[UUID, ...]
) -> tuple[UUID, ...]:
    if not isinstance(attempted_source_ids, tuple):
        raise DomainError("Fallback history must be immutable.")
    for source_id in attempted_source_ids:
        require_identifier(source_id)
    if len(set(attempted_source_ids)) != len(attempted_source_ids):
        raise DomainError("Fallback history must not contain duplicate sources.")
    if failed.source_id in attempted_source_ids:
        return attempted_source_ids
    return (*attempted_source_ids, failed.source_id)


def _policy_is_eligible(
    policy: SourcePolicy,
    query: DiscoveryQuery,
    attempted: tuple[UUID, ...],
) -> bool:
    return policy.source_id not in attempted and set(query.data_categories).issubset(
        policy.allowed_data_categories
    )


def _eligible_sources(
    policies: tuple[SourcePolicy, ...],
    permits: tuple[SourceAccessPermit, ...],
    query: DiscoveryQuery,
    attempted: tuple[UUID, ...],
    now: datetime,
) -> tuple[tuple[SourcePolicy, SourceAccessPermit], ...]:
    candidates: list[tuple[SourcePolicy, SourceAccessPermit]] = []
    for policy in policies:
        matching = tuple(
            permit for permit in permits if source_access_is_current(policy, permit, now)
        )
        if len(matching) > 1:
            raise DomainError("A source policy cannot have multiple current access permits.")
        if matching and _policy_is_eligible(policy, query, attempted):
            candidates.append((policy, matching[0]))
    source_ids = tuple(policy.source_id for policy, _ in candidates)
    if len(set(source_ids)) != len(source_ids):
        raise DomainError("A source cannot have multiple current fallback policies.")
    return tuple(
        sorted(
            candidates,
            key=lambda item: (
                _source_priority(item[0].kind),
                item[0].name,
                str(item[0].source_id),
            ),
        )
    )


def _source_priority(kind: SourceKind) -> int:
    return {
        SourceKind.OFFICIAL_API: 0,
        SourceKind.SEARCH_API: 1,
        SourceKind.PUBLIC_HTTP: 2,
    }[kind]
