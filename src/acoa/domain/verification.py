"""Evidence-bound employer risk and company-wide contact controls; F-04/P-16."""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.research import ResearchEvidence, evidence_is_current
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


class VerificationDepth(StrEnum):
    BASIC = "basic"
    DEEP = "deep"


class VerificationSubject(StrEnum):
    ORGANIZATION = "organization"
    CAREER_PORTAL = "career_portal"


class VerificationSignalKind(StrEnum):
    OFFICIAL_DOMAIN_CONTROL = "official_domain_control"
    CORPORATE_REGISTRY_MATCH = "corporate_registry_match"
    PORTAL_LINKED_FROM_OFFICIAL_SITE = "portal_linked_from_official_site"
    DOMAIN_MISMATCH = "domain_mismatch"
    CORPORATE_REGISTRY_MISMATCH = "corporate_registry_mismatch"
    UNLINKED_CAREER_PORTAL = "unlinked_career_portal"
    SENSITIVE_DOCUMENT_REQUEST = "sensitive_document_request"
    PAYMENT_REQUEST = "payment_request"
    DECEPTIVE_IDENTITY = "deceptive_identity"


class SignalDisposition(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"


class EmployerRisk(StrEnum):
    LOW = "low"
    ELEVATED = "elevated"
    HIGH = "high"
    CRITICAL = "critical"


class VerificationStatus(StrEnum):
    VERIFIED = "verified"
    DEEP_RESEARCH_REQUIRED = "deep_research_required"
    USER_REVIEW_REQUIRED = "user_review_required"
    BLOCKED = "blocked"


class ContactControlActor(StrEnum):
    EMPLOYER = "employer"
    USER = "user"


class ContactControlAction(StrEnum):
    BLOCK = "block"
    RETRACT = "retract"


@dataclass(frozen=True, slots=True)
class VerificationSignal:
    signal_id: UUID
    kind: VerificationSignalKind
    subject: VerificationSubject
    subject_sha256: str
    disposition: SignalDisposition
    evidence: ResearchEvidence

    def __post_init__(self) -> None:
        require_identifier(self.signal_id)
        require_sha256(self.subject_sha256)
        if (
            not isinstance(self.kind, VerificationSignalKind)
            or not isinstance(self.subject, VerificationSubject)
            or not isinstance(self.disposition, SignalDisposition)
            or not isinstance(self.evidence, ResearchEvidence)
        ):
            raise DomainError("A verification signal requires typed evidence and disposition.")
        if self.kind in POSITIVE_SIGNALS and self.disposition is not SignalDisposition.ACTIVE:
            raise DomainError("A positive verification signal cannot be marked resolved.")


@dataclass(frozen=True, slots=True)
class EmployerVerification:
    verification_id: UUID
    version: int
    organization_id: UUID
    organization_identity_sha256: str
    depth: VerificationDepth
    risk: EmployerRisk
    status: VerificationStatus
    signals: tuple[VerificationSignal, ...]
    content_sha256: str
    assessed_at: datetime
    valid_until: datetime

    def __post_init__(self) -> None:
        require_identifier(self.verification_id)
        require_version(self.version)
        require_identifier(self.organization_id)
        require_sha256(self.organization_identity_sha256)
        require_sha256(self.content_sha256)
        require_timestamp(self.assessed_at)
        require_timestamp(self.valid_until)
        if (
            not isinstance(self.depth, VerificationDepth)
            or not isinstance(self.risk, EmployerRisk)
            or not isinstance(self.status, VerificationStatus)
        ):
            raise DomainError("Employer verification requires explicit depth, risk and status.")
        if not isinstance(self.signals, tuple) or not self.signals:
            raise DomainError("Employer verification requires immutable sourced signals.")
        if any(not isinstance(signal, VerificationSignal) for signal in self.signals):
            raise DomainError("Employer verification signals must be validated.")
        keys = {(signal.kind, signal.subject, signal.subject_sha256) for signal in self.signals}
        if len(keys) != len(self.signals):
            raise DomainError("Employer verification must not repeat a signal subject.")
        if any(
            signal.subject is VerificationSubject.ORGANIZATION
            and signal.subject_sha256 != self.organization_identity_sha256
            for signal in self.signals
        ):
            raise DomainError("Organization signals must bind the verified organization identity.")
        if any(
            not evidence_is_current(signal.evidence, self.assessed_at) for signal in self.signals
        ):
            raise DomainError("Employer verification requires current signal evidence.")
        if self.valid_until != min(signal.evidence.valid_until for signal in self.signals):
            raise DomainError(
                "Employer verification validity must use its earliest evidence expiry."
            )
        expected_risk = classify_employer_risk(self.organization_identity_sha256, self.signals)
        if self.risk is not expected_risk:
            raise DomainError("Employer risk must follow the deterministic signal matrix.")
        if self.status is not verification_status(self.depth, self.risk):
            raise DomainError("Verification status must follow depth and risk.")
        if self.content_sha256 != employer_verification_sha256(self):
            raise DomainError("Employer verification digest must bind its exact evidence.")


@dataclass(frozen=True, slots=True)
class CompanyContactControlEvent:
    event_id: UUID
    organization_id: UUID
    sequence: int
    actor: ContactControlActor
    action: ContactControlAction
    content_sha256: str
    effective_at: datetime
    recorded_at: datetime
    evidence: ResearchEvidence | None = None

    def __post_init__(self) -> None:
        require_identifier(self.event_id)
        require_identifier(self.organization_id)
        require_version(self.sequence)
        require_sha256(self.content_sha256)
        require_timestamp(self.effective_at)
        require_timestamp(self.recorded_at)
        if not isinstance(self.actor, ContactControlActor) or not isinstance(
            self.action, ContactControlAction
        ):
            raise DomainError("A contact control event requires an explicit actor and action.")
        if self.recorded_at < self.effective_at:
            raise DomainError("A contact control event cannot be recorded before it is effective.")
        if self.actor is ContactControlActor.EMPLOYER:
            if not isinstance(self.evidence, ResearchEvidence):
                raise DomainError("An employer contact control requires source evidence.")
            if self.effective_at != self.evidence.observed_at:
                raise DomainError("Employer contact control time must bind its evidence.")
            if not evidence_is_current(self.evidence, self.recorded_at):
                raise DomainError("Employer contact control requires current source evidence.")
        elif self.evidence is not None:
            raise DomainError(
                "A user contact control must use trusted user input, not web evidence."
            )
        if self.content_sha256 != company_contact_event_sha256(self):
            raise DomainError("Contact control digest must bind the exact event.")


@dataclass(frozen=True, slots=True)
class CompanyContactState:
    organization_id: UUID
    blocked: bool
    active_actors: tuple[ContactControlActor, ...]
    last_sequence: int
    evaluated_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.organization_id)
        require_timestamp(self.evaluated_at)
        if (
            isinstance(self.last_sequence, bool)
            or not isinstance(self.last_sequence, int)
            or self.last_sequence < 0
        ):
            raise DomainError("A company contact state requires a nonnegative sequence.")
        if not isinstance(self.active_actors, tuple) or len(set(self.active_actors)) != len(
            self.active_actors
        ):
            raise DomainError("Active contact control actors must be immutable and unique.")
        if any(not isinstance(actor, ContactControlActor) for actor in self.active_actors):
            raise DomainError("A company contact state requires typed actors.")
        if self.blocked != bool(self.active_actors):
            raise DomainError("Company contact blocking must follow its active controls.")


POSITIVE_SIGNALS = frozenset(
    {
        VerificationSignalKind.OFFICIAL_DOMAIN_CONTROL,
        VerificationSignalKind.CORPORATE_REGISTRY_MATCH,
        VerificationSignalKind.PORTAL_LINKED_FROM_OFFICIAL_SITE,
    }
)

ELEVATED_SIGNALS = frozenset(
    {
        VerificationSignalKind.UNLINKED_CAREER_PORTAL,
        VerificationSignalKind.SENSITIVE_DOCUMENT_REQUEST,
    }
)

HIGH_SIGNALS = frozenset(
    {
        VerificationSignalKind.DOMAIN_MISMATCH,
        VerificationSignalKind.CORPORATE_REGISTRY_MISMATCH,
    }
)

CRITICAL_SIGNALS = frozenset(
    {
        VerificationSignalKind.PAYMENT_REQUEST,
        VerificationSignalKind.DECEPTIVE_IDENTITY,
    }
)


def classify_employer_risk(
    organization_identity_sha256: str, signals: tuple[VerificationSignal, ...]
) -> EmployerRisk:
    require_sha256(organization_identity_sha256)
    active = {signal.kind for signal in signals if signal.disposition is SignalDisposition.ACTIVE}
    official_identity = any(
        signal.kind is VerificationSignalKind.OFFICIAL_DOMAIN_CONTROL
        and signal.subject is VerificationSubject.ORGANIZATION
        and signal.subject_sha256 == organization_identity_sha256
        for signal in signals
    )
    if active & CRITICAL_SIGNALS:
        return EmployerRisk.CRITICAL
    if active & HIGH_SIGNALS or not official_identity:
        return EmployerRisk.HIGH
    if active & ELEVATED_SIGNALS:
        return EmployerRisk.ELEVATED
    return EmployerRisk.LOW


def verification_status(depth: VerificationDepth, risk: EmployerRisk) -> VerificationStatus:
    if depth is VerificationDepth.BASIC:
        return (
            VerificationStatus.VERIFIED
            if risk is EmployerRisk.LOW
            else VerificationStatus.DEEP_RESEARCH_REQUIRED
        )
    if risk is EmployerRisk.CRITICAL:
        return VerificationStatus.BLOCKED
    if risk in (EmployerRisk.ELEVATED, EmployerRisk.HIGH):
        return VerificationStatus.USER_REVIEW_REQUIRED
    return VerificationStatus.VERIFIED


def employer_verification_sha256(verification: EmployerVerification) -> str:
    return employer_verification_binding_sha256(
        verification.verification_id,
        verification.version,
        verification.organization_id,
        verification.organization_identity_sha256,
        verification.depth,
        verification.risk,
        verification.status,
        verification.signals,
        verification.assessed_at,
        verification.valid_until,
    )


def employer_verification_binding_sha256(
    verification_id: UUID,
    version: int,
    organization_id: UUID,
    organization_identity_sha256: str,
    depth: VerificationDepth,
    risk: EmployerRisk,
    status: VerificationStatus,
    signals: tuple[VerificationSignal, ...],
    assessed_at: datetime,
    valid_until: datetime,
) -> str:
    return content_digest(
        {
            "schema": "acoa-employer-verification/1",
            "verification_id": str(verification_id),
            "version": version,
            "organization_id": str(organization_id),
            "organization_identity_sha256": organization_identity_sha256,
            "depth": depth.value,
            "risk": risk.value,
            "status": status.value,
            "signals": [
                {
                    "signal_id": str(signal.signal_id),
                    "kind": signal.kind.value,
                    "subject": signal.subject.value,
                    "subject_sha256": signal.subject_sha256,
                    "disposition": signal.disposition.value,
                    "evidence_content_sha256": signal.evidence.content_sha256,
                }
                for signal in signals
            ],
            "assessed_at": assessed_at.isoformat(),
            "valid_until": valid_until.isoformat(),
        }
    )


def company_contact_event_sha256(event: CompanyContactControlEvent) -> str:
    return company_contact_event_binding_sha256(
        event.event_id,
        event.organization_id,
        event.sequence,
        event.actor,
        event.action,
        event.effective_at,
        event.recorded_at,
        event.evidence,
    )


def company_contact_event_binding_sha256(
    event_id: UUID,
    organization_id: UUID,
    sequence: int,
    actor: ContactControlActor,
    action: ContactControlAction,
    effective_at: datetime,
    recorded_at: datetime,
    evidence: ResearchEvidence | None,
) -> str:
    return content_digest(
        {
            "schema": "acoa-company-contact-control/1",
            "event_id": str(event_id),
            "organization_id": str(organization_id),
            "sequence": sequence,
            "actor": actor.value,
            "action": action.value,
            "effective_at": effective_at.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "evidence_content_sha256": (evidence.content_sha256 if evidence is not None else None),
        }
    )
