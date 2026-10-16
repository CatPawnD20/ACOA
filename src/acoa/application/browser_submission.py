"""Evidence-bound browser submission and read-only recheck contracts; EP-08.04."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from acoa.application.executor import ProviderAcknowledgement
from acoa.application.policy import request_binding_sha256
from acoa.domain.actions import DispatchLimits, PreparedAction, prepared_binding_sha256
from acoa.domain.authorization import ActionKind, Channel
from acoa.domain.submission_evidence import EvidenceSource, SubmissionClaim, SubmissionEvidence
from acoa.domain.values import DomainError, require_identifier, require_sha256, require_timestamp


class BrowserSubmissionOutcome(StrEnum):
    PROVIDER_ACCEPTED = "provider_accepted"
    NOT_PERFORMED = "not_performed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class BrowserSubmissionObservation:
    """Trusted status result for one exact prepared browser attempt."""

    attempt_id: UUID
    provider_id: UUID
    prepared_sha256: str = field(repr=False)
    source_ref: UUID = field(repr=False)
    snapshot_sha256: str = field(repr=False)
    observed_at: datetime
    outcome: BrowserSubmissionOutcome

    def __post_init__(self) -> None:
        for identifier in (self.attempt_id, self.provider_id, self.source_ref):
            require_identifier(identifier)
        require_sha256(self.prepared_sha256)
        require_sha256(self.snapshot_sha256)
        require_timestamp(self.observed_at)
        if not isinstance(self.outcome, BrowserSubmissionOutcome):
            raise DomainError("Browser submission observations require an explicit outcome.")


class BrowserSubmissionProvider(Protocol):
    """Perform one bounded submit; exceptions remain an uncertain transport result."""

    def submit_once(self, prepared: PreparedAction, limits: DispatchLimits) -> UUID: ...


class BrowserSubmissionStatusReader(Protocol):
    """Read status without navigating to, clicking or resubmitting the form."""

    def read_status(
        self, prepared: PreparedAction, observed_at: datetime
    ) -> BrowserSubmissionObservation: ...


def require_web_submission(prepared: PreparedAction) -> None:
    if (
        not isinstance(prepared, PreparedAction)
        or prepared.request.action is not ActionKind.SUBMIT_INITIAL_APPLICATION
        or prepared.request.channel is not Channel.WEB
    ):
        raise DomainError("Browser submission requires an exact prepared web application.")


class BrowserSubmissionAdapter:
    """Central-executor adapter that delegates exactly one call to a trusted browser provider."""

    def __init__(self, provider: BrowserSubmissionProvider) -> None:
        self.provider = provider

    def execute_once(
        self, prepared: PreparedAction, limits: DispatchLimits
    ) -> ProviderAcknowledgement:
        require_web_submission(prepared)
        receipt_ref = self.provider.submit_once(prepared, limits)
        require_identifier(receipt_ref)
        return ProviderAcknowledgement(
            prepared.attempt_id,
            request_binding_sha256(prepared.request),
            receipt_ref,
        )


def build_browser_submission_evidence(
    evidence_id: UUID,
    prepared: PreparedAction,
    observation: BrowserSubmissionObservation,
) -> SubmissionEvidence:
    """Convert an exact read-only browser status into reconciliation evidence."""
    require_identifier(evidence_id)
    require_web_submission(prepared)
    if (
        not isinstance(observation, BrowserSubmissionObservation)
        or observation.attempt_id != prepared.attempt_id
        or observation.provider_id != prepared.provider_id
        or observation.prepared_sha256 != prepared_binding_sha256(prepared)
    ):
        raise DomainError("Browser status does not match the prepared action.")
    claims = {
        BrowserSubmissionOutcome.PROVIDER_ACCEPTED: SubmissionClaim.PROVIDER_ACCEPTED,
        BrowserSubmissionOutcome.NOT_PERFORMED: SubmissionClaim.NOT_PERFORMED,
        BrowserSubmissionOutcome.UNKNOWN: SubmissionClaim.UNKNOWN,
    }
    sources = {
        BrowserSubmissionOutcome.PROVIDER_ACCEPTED: EvidenceSource.AUTHORITATIVE_STATUS,
        BrowserSubmissionOutcome.NOT_PERFORMED: EvidenceSource.AUTHORITATIVE_STATUS,
        BrowserSubmissionOutcome.UNKNOWN: EvidenceSource.INCONCLUSIVE_LOOKUP,
    }
    return SubmissionEvidence(
        evidence_id,
        prepared.attempt_id,
        prepared.provider_id,
        prepared_binding_sha256(prepared),
        observation.source_ref,
        observation.snapshot_sha256,
        observation.observed_at,
        claims[observation.outcome],
        sources[observation.outcome],
        True,
    )


def recheck_browser_submission(
    evidence_id: UUID,
    prepared: PreparedAction,
    reader: BrowserSubmissionStatusReader,
    observed_at: datetime,
) -> SubmissionEvidence:
    """Perform one read-only status lookup and bind its result for reconciliation."""
    require_timestamp(observed_at)
    observation = reader.read_status(prepared, observed_at)
    return build_browser_submission_evidence(evidence_id, prepared, observation)
