"""Deterministic employer verification and company opt-out projection; EP-04.03."""

from dataclasses import dataclass
from datetime import datetime
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from acoa.application.policy_inputs import EvidenceStatus, PolicyEvidence, Requirement
from acoa.domain.research import ContactChannel, ContactChannelKind, Organization, ResearchEvidence
from acoa.domain.values import DomainError, require_timestamp, require_version
from acoa.domain.verification import (
    CompanyContactControlEvent,
    CompanyContactState,
    ContactControlAction,
    ContactControlActor,
    EmployerRisk,
    EmployerVerification,
    SignalDisposition,
    VerificationDepth,
    VerificationSignal,
    VerificationSignalKind,
    VerificationStatus,
    VerificationSubject,
    classify_employer_risk,
    company_contact_event_binding_sha256,
    employer_verification_binding_sha256,
    verification_status,
)


@dataclass(frozen=True, slots=True)
class VerificationFinding:
    kind: VerificationSignalKind
    disposition: SignalDisposition
    evidence: ResearchEvidence
    career_portal: ContactChannel | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.kind, VerificationSignalKind)
            or not isinstance(self.disposition, SignalDisposition)
            or not isinstance(self.evidence, ResearchEvidence)
        ):
            raise DomainError("A verification finding requires typed source evidence.")
        if self.career_portal is not None and not isinstance(self.career_portal, ContactChannel):
            raise DomainError("A verification finding portal must be a validated channel.")


PORTAL_SIGNALS = frozenset(
    {
        VerificationSignalKind.PORTAL_LINKED_FROM_OFFICIAL_SITE,
        VerificationSignalKind.DOMAIN_MISMATCH,
        VerificationSignalKind.UNLINKED_CAREER_PORTAL,
        VerificationSignalKind.SENSITIVE_DOCUMENT_REQUEST,
        VerificationSignalKind.PAYMENT_REQUEST,
    }
)


def assess_employer(
    organization: Organization,
    findings: tuple[VerificationFinding, ...],
    depth: VerificationDepth,
    assessed_at: datetime,
    version: int = 1,
) -> EmployerVerification:
    require_timestamp(assessed_at)
    require_version(version)
    if not isinstance(organization, Organization) or not isinstance(findings, tuple):
        raise DomainError("Employer assessment requires an organization and immutable findings.")
    if not findings or not isinstance(depth, VerificationDepth):
        raise DomainError("Employer assessment requires findings and an explicit depth.")
    signals = tuple(
        sorted(
            (_signal_from_finding(organization, finding, assessed_at) for finding in findings),
            key=lambda item: (item.kind.value, item.subject.value, item.subject_sha256),
        )
    )
    risk = classify_employer_risk(organization.identity_sha256, signals)
    verification_id = uuid5(
        NAMESPACE_URL, f"acoa:employer-verification:{organization.identity_sha256}"
    )
    status = verification_status(depth, risk)
    valid_until = min(signal.evidence.valid_until for signal in signals)
    digest = employer_verification_binding_sha256(
        verification_id,
        version,
        organization.organization_id,
        organization.identity_sha256,
        depth,
        risk,
        status,
        signals,
        assessed_at,
        valid_until,
    )
    return EmployerVerification(
        verification_id,
        version,
        organization.organization_id,
        organization.identity_sha256,
        depth,
        risk,
        status,
        signals,
        digest,
        assessed_at,
        valid_until,
    )


def _signal_from_finding(
    organization: Organization, finding: VerificationFinding, assessed_at: datetime
) -> VerificationSignal:
    if not isinstance(finding, VerificationFinding):
        raise DomainError("Employer assessment findings must be validated.")
    if not (finding.evidence.observed_at <= assessed_at < finding.evidence.valid_until):
        raise DomainError("Employer assessment findings require current evidence.")
    requires_portal = finding.kind in PORTAL_SIGNALS
    if requires_portal != (finding.career_portal is not None):
        raise DomainError("Portal risk signals must bind exactly one career portal channel.")
    if finding.career_portal is None:
        subject = VerificationSubject.ORGANIZATION
        subject_sha256 = organization.identity_sha256
    else:
        portal = finding.career_portal
        if (
            portal.organization_id != organization.organization_id
            or portal.kind is not ContactChannelKind.CAREER_PORTAL
        ):
            raise DomainError("A portal risk signal must bind this organization's career portal.")
        subject = VerificationSubject.CAREER_PORTAL
        subject_sha256 = portal.content_sha256
    signal_id = uuid5(
        NAMESPACE_URL,
        ":".join(
            (
                "acoa",
                "verification-signal",
                organization.identity_sha256,
                finding.kind.value,
                subject_sha256,
                finding.evidence.content_sha256,
            )
        ),
    )
    return VerificationSignal(
        signal_id,
        finding.kind,
        subject,
        subject_sha256,
        finding.disposition,
        finding.evidence,
    )


def create_company_contact_event(
    organization: Organization,
    prior_events: tuple[CompanyContactControlEvent, ...],
    actor: ContactControlActor,
    action: ContactControlAction,
    effective_at: datetime,
    recorded_at: datetime,
    evidence: ResearchEvidence | None = None,
    event_id: UUID | None = None,
) -> CompanyContactControlEvent:
    require_timestamp(effective_at)
    require_timestamp(recorded_at)
    if not isinstance(organization, Organization) or not isinstance(prior_events, tuple):
        raise DomainError("Company contact control requires an organization and event history.")
    state = project_company_contact_state(organization, prior_events, recorded_at)
    if not isinstance(actor, ContactControlActor) or not isinstance(action, ContactControlAction):
        raise DomainError("Company contact control requires an explicit actor and action.")
    _require_contact_transition(state, actor, action)
    resolved_event_id = event_id or uuid4()
    sequence = state.last_sequence + 1
    digest = company_contact_event_binding_sha256(
        resolved_event_id,
        organization.organization_id,
        sequence,
        actor,
        action,
        effective_at,
        recorded_at,
        evidence,
    )
    event = CompanyContactControlEvent(
        resolved_event_id,
        organization.organization_id,
        sequence,
        actor,
        action,
        digest,
        effective_at,
        recorded_at,
        evidence,
    )
    project_company_contact_state(organization, prior_events + (event,), recorded_at)
    return event


def _require_contact_transition(
    state: CompanyContactState,
    actor: ContactControlActor,
    action: ContactControlAction,
) -> None:
    actor_is_active = actor in state.active_actors
    if action is ContactControlAction.BLOCK and actor_is_active:
        raise DomainError("This actor already has an active company contact block.")
    if action is ContactControlAction.RETRACT and not actor_is_active:
        raise DomainError("A company contact block can only retract the same actor's block.")


def project_company_contact_state(
    organization: Organization,
    events: tuple[CompanyContactControlEvent, ...],
    evaluated_at: datetime,
) -> CompanyContactState:
    require_timestamp(evaluated_at)
    if not isinstance(organization, Organization) or not isinstance(events, tuple):
        raise DomainError("Company contact state requires an organization and immutable history.")
    active: dict[ContactControlActor, CompanyContactControlEvent] = {}
    for expected, event in enumerate(events, start=1):
        if not isinstance(event, CompanyContactControlEvent):
            raise DomainError("Company contact history contains an invalid event.")
        if event.organization_id != organization.organization_id or event.sequence != expected:
            raise DomainError(
                "Company contact history must be complete and ordered for one company."
            )
        if event.recorded_at > evaluated_at or event.effective_at > evaluated_at:
            raise DomainError("Company contact history cannot include future events.")
        if event.action is ContactControlAction.BLOCK:
            if event.actor in active:
                raise DomainError("Company contact history repeats an active block.")
            active[event.actor] = event
        else:
            blocked_by = active.get(event.actor)
            if blocked_by is None:
                raise DomainError("Company contact history retracts an absent block.")
            if event.actor is ContactControlActor.EMPLOYER:
                _require_new_employer_retraction_evidence(blocked_by, event)
            del active[event.actor]
    actors = tuple(sorted(active, key=lambda item: item.value))
    return CompanyContactState(
        organization.organization_id,
        bool(actors),
        actors,
        len(events),
        evaluated_at,
    )


def _require_new_employer_retraction_evidence(
    block: CompanyContactControlEvent, retraction: CompanyContactControlEvent
) -> None:
    assert block.evidence is not None and retraction.evidence is not None
    if (
        retraction.evidence.observed_at <= block.evidence.observed_at
        or retraction.evidence.content_sha256 == block.evidence.content_sha256
    ):
        raise DomainError("Employer opt-out retraction requires newer independent evidence.")


def company_channel_policy_evidence(
    verification: EmployerVerification,
    channel: ContactChannel,
    contact_state: CompanyContactState,
    now: datetime,
) -> tuple[PolicyEvidence, PolicyEvidence]:
    require_timestamp(now)
    if (
        not isinstance(verification, EmployerVerification)
        or not isinstance(channel, ContactChannel)
        or not isinstance(contact_state, CompanyContactState)
        or verification.organization_id != channel.organization_id
        or verification.organization_id != contact_state.organization_id
    ):
        raise DomainError("Policy evidence requires one employer, channel and contact state.")
    trust_satisfied = (
        verification.status is VerificationStatus.VERIFIED
        and verification.risk is EmployerRisk.LOW
        and verification.assessed_at <= now < verification.valid_until
        and _channel_is_verified(verification, channel)
    )
    opt_out_clear = contact_state.evaluated_at == now and not contact_state.blocked
    return (
        PolicyEvidence(
            Requirement.COMPANY_CHANNEL_TRUST,
            EvidenceStatus.SATISFIED if trust_satisfied else EvidenceStatus.VIOLATED,
        ),
        PolicyEvidence(
            Requirement.OPT_OUT_CLEAR,
            EvidenceStatus.SATISFIED if opt_out_clear else EvidenceStatus.VIOLATED,
        ),
    )


def _channel_is_verified(verification: EmployerVerification, channel: ContactChannel) -> bool:
    if channel.kind is not ContactChannelKind.CAREER_PORTAL:
        return channel.eligible_for_initial_contact
    linked = any(
        signal.kind is VerificationSignalKind.PORTAL_LINKED_FROM_OFFICIAL_SITE
        and signal.subject_sha256 == channel.content_sha256
        and signal.disposition is SignalDisposition.ACTIVE
        for signal in verification.signals
    )
    active_adverse = any(
        signal.kind
        not in (
            VerificationSignalKind.OFFICIAL_DOMAIN_CONTROL,
            VerificationSignalKind.CORPORATE_REGISTRY_MATCH,
            VerificationSignalKind.PORTAL_LINKED_FROM_OFFICIAL_SITE,
        )
        and signal.subject_sha256 == channel.content_sha256
        and signal.disposition is SignalDisposition.ACTIVE
        for signal in verification.signals
    )
    return linked and not active_adverse
