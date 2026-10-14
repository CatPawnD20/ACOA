"""EP-02.02 canonical application identity and reapplication; F-10, P-11/P-15."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.reviews import content_digest
from acoa.domain.values import DomainError, require_identifier, require_sha256, require_timestamp


class ApplicationKind(StrEnum):
    INITIAL_APPLICATION = "initial_application"
    INITIAL_CONTACT = "initial_contact"


class ApplicationState(StrEnum):
    OPEN = "open"
    REJECTED = "rejected"
    CLOSED = "closed"
    WITHDRAWN = "withdrawn"


class SubmissionState(StrEnum):
    NOT_STARTED = "not_started"
    VERIFIED = "submission_verified"
    FAILED = "submission_failed"
    UNCONFIRMED = "submission_unconfirmed"


@dataclass(frozen=True, slots=True)
class ApplicationIdentity:
    """IDs resolved by trusted canonicalization; a URL/channel is not opportunity identity."""

    owner_id: UUID = field(repr=False)
    company_id: UUID = field(repr=False)
    target_id: UUID = field(repr=False)
    campaign_id: UUID = field(repr=False)
    kind: ApplicationKind

    def __post_init__(self) -> None:
        for identifier in (self.owner_id, self.company_id, self.target_id, self.campaign_id):
            require_identifier(identifier)
        if not isinstance(self.kind, ApplicationKind):
            raise DomainError("Application identity requires an explicit operation kind.")


@dataclass(frozen=True, slots=True)
class ApplicationSpec:
    application_id: UUID
    identity: ApplicationIdentity
    identity_evidence_id: UUID = field(repr=False)
    reapplication_episode_id: UUID | None = None
    previous_application_id: UUID | None = None

    def __post_init__(self) -> None:
        require_identifier(self.application_id)
        require_identifier(self.identity_evidence_id)
        if not isinstance(self.identity, ApplicationIdentity):
            raise DomainError("Applications require resolved canonical identity values.")
        if (self.reapplication_episode_id is None) != (self.previous_application_id is None):
            raise DomainError("Reapplications require both a new episode and previous application.")
        for identifier in (self.reapplication_episode_id, self.previous_application_id):
            if identifier is not None:
                require_identifier(identifier)
        if self.previous_application_id == self.application_id:
            raise DomainError("An application cannot be its own predecessor.")


def semantic_operation_key(spec: ApplicationSpec) -> str:
    """Exclude attempts, URLs, account/channel and document versions from operation identity."""
    identity = spec.identity
    fields: dict[str, object] = {
        "owner": str(identity.owner_id),
        "company": str(identity.company_id),
        "target": str(identity.target_id),
        "campaign": str(identity.campaign_id),
        "kind": identity.kind.value,
    }
    if spec.reapplication_episode_id is not None:
        fields["reapplication_episode_id"] = str(spec.reapplication_episode_id)
    return content_digest(fields)


@dataclass(frozen=True, slots=True)
class ReapplicationEvidence:
    """Trusted policy-adapter output bound to an exact new spec; not proof of origin."""

    evidence_id: UUID
    previous_application_id: UUID
    new_application_sha256: str
    policy_id: UUID | None = None
    change_evidence_id: UUID | None = None
    authorization_decision_id: UUID | None = None
    cooldown_until: datetime | None = None
    evaluated_at: datetime | None = None
    expires_at: datetime | None = None
    meaningful_change_confirmed: bool = False
    channel_policy_confirmed: bool = False
    fresh_authorization_confirmed: bool = False
    canonical_identity_confirmed: bool = False

    def __post_init__(self) -> None:
        require_identifier(self.evidence_id)
        require_identifier(self.previous_application_id)
        require_sha256(self.new_application_sha256)
        for identifier in (self.policy_id, self.change_evidence_id, self.authorization_decision_id):
            if identifier is not None:
                require_identifier(identifier)
        for timestamp in (self.cooldown_until, self.evaluated_at, self.expires_at):
            if timestamp is not None:
                require_timestamp(timestamp)
        for confirmation in (
            self.meaningful_change_confirmed,
            self.channel_policy_confirmed,
            self.fresh_authorization_confirmed,
            self.canonical_identity_confirmed,
        ):
            if not isinstance(confirmation, bool):
                raise DomainError("Reapplication evidence confirmations must be explicit booleans.")


def application_spec_digest(spec: ApplicationSpec) -> str:
    """Bind evidence to the episode, predecessor and canonical-resolution evidence too."""
    return content_digest(
        {
            "application_id": str(spec.application_id),
            "semantic_key": semantic_operation_key(spec),
            "previous_application_id": str(spec.previous_application_id),
            "identity_evidence_id": str(spec.identity_evidence_id),
        }
    )


def reapplication_evidence_is_valid(
    spec: ApplicationSpec, evidence: ReapplicationEvidence, now: datetime
) -> bool:
    """Unknown policy thresholds or confirmations fail closed without invented defaults."""
    require_timestamp(now)
    return (
        spec.reapplication_episode_id is not None
        and evidence.previous_application_id == spec.previous_application_id
        and evidence.new_application_sha256 == application_spec_digest(spec)
        and evidence.policy_id is not None
        and evidence.change_evidence_id is not None
        and evidence.authorization_decision_id is not None
        and evidence.evaluated_at is not None
        and evidence.expires_at is not None
        and evidence.cooldown_until is not None
        and evidence.evaluated_at <= now < evidence.expires_at
        and evidence.cooldown_until <= now
        and evidence.meaningful_change_confirmed
        and evidence.channel_policy_confirmed
        and evidence.fresh_authorization_confirmed
        and evidence.canonical_identity_confirmed
    )


@dataclass(frozen=True, slots=True)
class ApplicationSnapshot:
    spec: ApplicationSpec
    state: ApplicationState
    submission_state: SubmissionState
    created_at: datetime
    closed_at: datetime | None
    closure_evidence_id: UUID | None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, ApplicationSpec) or not isinstance(
            self.state, ApplicationState
        ):
            raise DomainError("Application snapshots require explicit specification and state.")
        if not isinstance(self.submission_state, SubmissionState):
            raise DomainError(
                "Submission state must be explicit and separate from application state."
            )
        require_timestamp(self.created_at)
        closed = self.state is not ApplicationState.OPEN
        if closed != (self.closed_at is not None) or closed != (
            self.closure_evidence_id is not None
        ):
            raise DomainError("Closed application states require time and evidence references.")
        if self.closed_at is not None:
            require_timestamp(self.closed_at)
            if self.closed_at < self.created_at:
                raise DomainError("Application closure must not predate creation.")
        if self.closure_evidence_id is not None:
            require_identifier(self.closure_evidence_id)
