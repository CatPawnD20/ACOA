"""EP-02.04 evidence-bound submission outcomes; E-04.03/04, P-11, ADR-007/014."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.actions import PreparedAction, prepared_binding_sha256
from acoa.domain.values import DomainError, require_identifier, require_sha256, require_timestamp


class SubmissionClaim(StrEnum):
    PROVIDER_ACCEPTED = "provider_accepted"
    DELIVERED = "delivered"
    READ = "read"
    NOT_PERFORMED = "confirmed_not_performed"
    UNKNOWN = "unknown"


class EvidenceSource(StrEnum):
    SENT_RECORD = "sent_record"
    CONFIRMATION_PAGE = "confirmation_page"
    AUTHORITATIVE_STATUS = "authoritative_status"
    DELIVERY_RECEIPT = "delivery_receipt"
    READ_RECEIPT = "read_receipt"
    INCONCLUSIVE_LOOKUP = "inconclusive_lookup"


@dataclass(frozen=True, slots=True)
class SubmissionEvidence:
    """Trusted read-only verifier output, never an LLM assertion or transport acknowledgement."""

    evidence_id: UUID
    attempt_id: UUID
    provider_id: UUID
    prepared_sha256: str = field(repr=False)
    source_ref: UUID = field(repr=False)
    snapshot_sha256: str = field(repr=False)
    observed_at: datetime
    claim: SubmissionClaim
    source: EvidenceSource
    verified_by_adapter: bool = False
    actual_cost: Decimal | None = None
    currency: str | None = None

    def __post_init__(self) -> None:
        for identifier in (self.evidence_id, self.attempt_id, self.provider_id, self.source_ref):
            require_identifier(identifier)
        require_sha256(self.prepared_sha256)
        require_sha256(self.snapshot_sha256)
        require_timestamp(self.observed_at)
        if not isinstance(self.claim, SubmissionClaim) or not isinstance(
            self.source, EvidenceSource
        ):
            raise DomainError("Submission evidence requires explicit claim and source values.")
        if not isinstance(self.verified_by_adapter, bool):
            raise DomainError("Adapter verification must be explicit.")
        if (self.actual_cost is None) != (self.currency is None):
            raise DomainError("Actual cost requires both amount and currency, or both unknown.")
        if self.actual_cost is not None and (
            not isinstance(self.actual_cost, Decimal)
            or not self.actual_cost.is_finite()
            or self.actual_cost < 0
        ):
            raise DomainError("Actual cost must be a finite nonnegative Decimal.")
        if self.currency is not None and (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for character in self.currency)
        ):
            raise DomainError("Evidence currency must be an explicit uppercase label.")


def claim_is_supported(evidence: SubmissionEvidence) -> bool:
    """Missing search results never prove non-delivery; acceptance never proves read/delivery."""
    sources = {
        SubmissionClaim.PROVIDER_ACCEPTED: (
            EvidenceSource.SENT_RECORD,
            EvidenceSource.CONFIRMATION_PAGE,
            EvidenceSource.AUTHORITATIVE_STATUS,
        ),
        SubmissionClaim.DELIVERED: (EvidenceSource.DELIVERY_RECEIPT,),
        SubmissionClaim.READ: (EvidenceSource.READ_RECEIPT,),
        SubmissionClaim.NOT_PERFORMED: (EvidenceSource.AUTHORITATIVE_STATUS,),
        SubmissionClaim.UNKNOWN: tuple(EvidenceSource),
    }
    return evidence.verified_by_adapter and evidence.source in sources[evidence.claim]


def evidence_matches_attempt(
    evidence: SubmissionEvidence,
    prepared: PreparedAction,
    execution_started_at: datetime,
    now: datetime,
) -> bool:
    require_timestamp(execution_started_at)
    require_timestamp(now)
    return (
        evidence.attempt_id == prepared.attempt_id
        and evidence.provider_id == prepared.provider_id
        and evidence.prepared_sha256 == prepared_binding_sha256(prepared)
        and execution_started_at <= evidence.observed_at <= now
        and claim_is_supported(evidence)
    )


class IncidentKind(StrEnum):
    UNKNOWN_SUBMISSION = "unknown_submission"
    ABANDONED_DISPATCH = "abandoned_dispatch"
    INVALID_EVIDENCE = "invalid_evidence"
    CONFLICTING_EVIDENCE = "conflicting_evidence"
    BUDGET_OVERRUN = "budget_overrun"
