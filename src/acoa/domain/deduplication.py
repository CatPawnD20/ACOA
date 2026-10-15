"""Conservative cross-source identity and fallback decisions; F-02/F-03/P-07."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.discovery import SourceAccessStatus, SourceKind, SourceOperation
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class EntityKind(StrEnum):
    ORGANIZATION = "organization"
    OPPORTUNITY = "opportunity"


class MatchBasis(StrEnum):
    SAME_IDENTITY = "same_identity"
    VERIFIED_LEGAL_ENTITY_ALIAS = "verified_legal_entity_alias"
    SAME_EXTERNAL_JOB_ID = "same_external_job_id"
    SAME_ROLE_AND_LOCATION = "same_role_and_location"
    POSSIBLE_NAME_ALIAS = "possible_name_alias"
    CONFLICTING_LOCATION = "conflicting_location"
    CONFLICTING_ORGANIZATION = "conflicting_organization"
    DISTINCT_ATTRIBUTES = "distinct_attributes"


class DeduplicationOutcome(StrEnum):
    CANONICAL = "canonical"
    POSSIBLE_DUPLICATE = "possible_duplicate"
    DISTINCT = "distinct"


class AliasRelation(StrEnum):
    VERIFIED_SAME_LEGAL_ENTITY = "verified_same_legal_entity"
    POSSIBLE_ALIAS = "possible_alias"
    NOT_SAME = "not_same"


class FallbackStatus(StrEnum):
    SELECTED = "selected"
    NO_ALLOWED_ALTERNATIVE = "no_allowed_alternative"


@dataclass(frozen=True, slots=True)
class DeduplicationDecision:
    decision_id: UUID
    version: int
    entity_kind: EntityKind
    left_entity_id: UUID
    right_entity_id: UUID
    outcome: DeduplicationOutcome
    basis: MatchBasis
    canonical_entity_id: UUID | None
    evidence_sha256: tuple[str, ...]
    content_sha256: str
    decided_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        require_identifier(self.decision_id)
        require_version(self.version)
        require_identifier(self.left_entity_id)
        require_identifier(self.right_entity_id)
        if str(self.left_entity_id) > str(self.right_entity_id):
            raise DomainError("Deduplication entities must use deterministic order.")
        require_sha256(self.content_sha256)
        require_timestamp(self.decided_at)
        require_timestamp(self.valid_until)
        if not isinstance(self.entity_kind, EntityKind) or not isinstance(
            self.outcome, DeduplicationOutcome
        ):
            raise DomainError("A deduplication decision requires explicit entity and outcome.")
        if not isinstance(self.basis, MatchBasis):
            raise DomainError("A deduplication decision requires a structured match basis.")
        if not isinstance(self.evidence_sha256, tuple) or not self.evidence_sha256:
            raise DomainError("A deduplication decision requires immutable evidence hashes.")
        for digest in self.evidence_sha256:
            require_sha256(digest)
        if len(set(self.evidence_sha256)) != len(self.evidence_sha256):
            raise DomainError("Deduplication evidence hashes must not repeat.")
        if self.valid_until <= self.decided_at:
            raise DomainError("A deduplication decision requires a future validity bound.")
        allowed_bases = {
            DeduplicationOutcome.CANONICAL: (
                MatchBasis.SAME_IDENTITY,
                MatchBasis.VERIFIED_LEGAL_ENTITY_ALIAS,
                MatchBasis.SAME_EXTERNAL_JOB_ID,
            ),
            DeduplicationOutcome.POSSIBLE_DUPLICATE: (
                MatchBasis.SAME_ROLE_AND_LOCATION,
                MatchBasis.POSSIBLE_NAME_ALIAS,
            ),
            DeduplicationOutcome.DISTINCT: (
                MatchBasis.CONFLICTING_LOCATION,
                MatchBasis.CONFLICTING_ORGANIZATION,
                MatchBasis.DISTINCT_ATTRIBUTES,
            ),
        }
        if self.basis not in allowed_bases[self.outcome]:
            raise DomainError("A deduplication outcome requires a compatible match basis.")
        if self.outcome is DeduplicationOutcome.CANONICAL:
            if self.canonical_entity_id not in (self.left_entity_id, self.right_entity_id):
                raise DomainError("A canonical record must be one of the compared records.")
        elif self.canonical_entity_id is not None:
            raise DomainError("Uncertain or distinct records cannot claim a canonical identity.")
        if self.content_sha256 != deduplication_decision_sha256(self):
            raise DomainError("Deduplication digest must bind the exact decision and evidence.")


@dataclass(frozen=True, slots=True)
class SourceFallbackPlan:
    plan_id: UUID
    failed_observation_id: UUID
    failed_source_id: UUID
    failed_status: SourceAccessStatus
    operation: SourceOperation
    query_sha256: str
    attempted_source_ids: tuple[UUID, ...]
    status: FallbackStatus
    selected_source_id: UUID | None
    selected_policy_version: str | None
    selected_source_kind: SourceKind | None
    selected_permit_id: UUID | None
    content_sha256: str
    planned_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        for identifier in (self.plan_id, self.failed_observation_id, self.failed_source_id):
            require_identifier(identifier)
        require_sha256(self.query_sha256)
        require_sha256(self.content_sha256)
        require_timestamp(self.planned_at)
        require_timestamp(self.valid_until)
        if not isinstance(self.failed_status, SourceAccessStatus) or not isinstance(
            self.operation, SourceOperation
        ):
            raise DomainError("A fallback plan requires the exact failed access result.")
        if self.failed_status is SourceAccessStatus.SUCCEEDED:
            raise DomainError("A successful source access cannot create a fallback plan.")
        if not isinstance(self.attempted_source_ids, tuple) or not self.attempted_source_ids:
            raise DomainError("A fallback plan requires immutable attempted source identities.")
        for identifier in self.attempted_source_ids:
            require_identifier(identifier)
        if len(set(self.attempted_source_ids)) != len(self.attempted_source_ids):
            raise DomainError("A fallback plan cannot repeat an attempted source.")
        if self.failed_source_id not in self.attempted_source_ids:
            raise DomainError("A fallback plan must retain the failed source in its history.")
        if not isinstance(self.status, FallbackStatus):
            raise DomainError("A fallback plan requires an explicit result status.")
        selected = (
            self.selected_source_id,
            self.selected_policy_version,
            self.selected_source_kind,
            self.selected_permit_id,
        )
        if self.status is FallbackStatus.SELECTED:
            if any(value is None for value in selected):
                raise DomainError("A selected fallback requires an exact source policy.")
            assert self.selected_source_id is not None
            assert self.selected_policy_version is not None
            assert self.selected_permit_id is not None
            require_identifier(self.selected_source_id)
            require_identifier(self.selected_permit_id)
            require_text(self.selected_policy_version)
            if not isinstance(self.selected_source_kind, SourceKind):
                raise DomainError("A selected fallback requires an explicit source kind.")
            if self.selected_source_id in self.attempted_source_ids:
                raise DomainError("A fallback cannot retry a source already attempted.")
        elif any(value is not None for value in selected):
            raise DomainError("An exhausted fallback cannot claim a selected source.")
        if self.status is FallbackStatus.SELECTED and self.valid_until <= self.planned_at:
            raise DomainError("A selected fallback requires a future validity bound.")
        if (
            self.status is FallbackStatus.NO_ALLOWED_ALTERNATIVE
            and self.valid_until != self.planned_at
        ):
            raise DomainError("An exhausted fallback must be terminal at its planning time.")
        if self.content_sha256 != source_fallback_plan_sha256(self):
            raise DomainError("Fallback digest must bind the exact failure and selected policy.")


def deduplication_decision_sha256(decision: DeduplicationDecision) -> str:
    return deduplication_binding_sha256(
        decision.decision_id,
        decision.version,
        decision.entity_kind,
        decision.left_entity_id,
        decision.right_entity_id,
        decision.outcome,
        decision.basis,
        decision.canonical_entity_id,
        decision.evidence_sha256,
        decision.decided_at,
        decision.valid_until,
    )


def deduplication_binding_sha256(
    decision_id: UUID,
    version: int,
    entity_kind: EntityKind,
    left_entity_id: UUID,
    right_entity_id: UUID,
    outcome: DeduplicationOutcome,
    basis: MatchBasis,
    canonical_entity_id: UUID | None,
    evidence_sha256: tuple[str, ...],
    decided_at: datetime,
    valid_until: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-deduplication-decision/1",
            "decision_id": str(decision_id),
            "version": version,
            "entity_kind": entity_kind.value,
            "left_entity_id": str(left_entity_id),
            "right_entity_id": str(right_entity_id),
            "outcome": outcome.value,
            "basis": basis.value,
            "canonical_entity_id": (
                str(canonical_entity_id) if canonical_entity_id is not None else None
            ),
            "evidence_sha256": list(evidence_sha256),
            "decided_at": decided_at.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
    )


def source_fallback_plan_sha256(plan: SourceFallbackPlan) -> str:
    return source_fallback_binding_sha256(
        plan.plan_id,
        plan.failed_observation_id,
        plan.failed_source_id,
        plan.failed_status,
        plan.operation,
        plan.query_sha256,
        plan.attempted_source_ids,
        plan.status,
        plan.selected_source_id,
        plan.selected_policy_version,
        plan.selected_source_kind,
        plan.selected_permit_id,
        plan.planned_at,
        plan.valid_until,
    )


def source_fallback_binding_sha256(
    plan_id: UUID,
    failed_observation_id: UUID,
    failed_source_id: UUID,
    failed_status: SourceAccessStatus,
    operation: SourceOperation,
    query_sha256: str,
    attempted_source_ids: tuple[UUID, ...],
    status: FallbackStatus,
    selected_source_id: UUID | None,
    selected_policy_version: str | None,
    selected_source_kind: SourceKind | None,
    selected_permit_id: UUID | None,
    planned_at: datetime,
    valid_until: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-source-fallback-plan/1",
            "plan_id": str(plan_id),
            "failed_observation_id": str(failed_observation_id),
            "failed_source_id": str(failed_source_id),
            "failed_status": failed_status.value,
            "operation": operation.value,
            "query_sha256": query_sha256,
            "attempted_source_ids": [str(item) for item in attempted_source_ids],
            "status": status.value,
            "selected_source_id": (
                str(selected_source_id) if selected_source_id is not None else None
            ),
            "selected_policy_version": selected_policy_version,
            "selected_source_kind": (
                selected_source_kind.value if selected_source_kind is not None else None
            ),
            "selected_permit_id": (
                str(selected_permit_id) if selected_permit_id is not None else None
            ),
            "planned_at": planned_at.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
    )
