"""EP-01.03 typed snapshots supplied by trusted adapters, never by agent plans."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.config import Settings
from acoa.domain.action_requests import PolicyRequest as PolicyRequest
from acoa.domain.authorization import (
    AuthorizationGrant,
    DataCategory,
    SensitiveDataConsent,
    validate_scope,
)
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)


class CommunicationPurpose(StrEnum):
    UNKNOWN = "unknown"
    INITIAL_APPLICATION = "initial_application"
    INITIAL_OUTREACH = "initial_outreach"
    EMPLOYER_REPLY = "employer_reply"
    FOLLOWUP = "followup"
    CAREER_ACCOUNT = "career_account"


class EvidenceStatus(StrEnum):
    UNKNOWN = "unknown"
    SATISFIED = "satisfied"
    VIOLATED = "violated"


class Requirement(StrEnum):
    AUTHORIZATION_CURRENT = "authorization_current"
    HARD_CONSTRAINTS = "hard_constraints"
    COMPANY_CHANNEL_TRUST = "company_channel_trust"
    ACCOUNT_OWNERSHIP = "account_ownership"
    CORPORATE_RECIPIENT = "corporate_recipient"
    OPT_OUT_CLEAR = "opt_out_clear"
    DUPLICATE_CLEAR = "duplicate_clear"
    SUBMISSION_STATE_CLEAR = "submission_state_clear"
    ARTIFACT_INTEGRITY = "artifact_integrity"
    PROFILE_VERSION_CURRENT = "profile_version_current"
    PERSONAL_ANSWERS_COMPLETE = "personal_answers_complete"
    SOURCE_ACCESS_ALLOWED = "source_access_allowed"
    SANDBOX_VERIFIED = "sandbox_verified"
    ACCESS_CHALLENGES_CLEAR = "access_challenges_clear"
    NONBINDING_TERMS = "nonbinding_terms"


@dataclass(frozen=True, slots=True)
class PolicyEvidence:
    requirement: Requirement
    status: EvidenceStatus

    def __post_init__(self) -> None:
        if not isinstance(self.requirement, Requirement) or not isinstance(
            self.status, EvidenceStatus
        ):
            raise DomainError("Policy evidence must use explicit requirement and status values.")


def validate_optional_usage(value: object, monetary: bool = False) -> None:
    """Keep unknown usage explicit and reject coercion, negative or nonfinite counters."""
    if value is None:
        return
    if monetary:
        if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
            raise DomainError("Money usage must be a finite nonnegative Decimal or unknown.")
    elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise DomainError("Usage must be a nonnegative integer or unknown.")


@dataclass(frozen=True, slots=True)
class QuotaUsage:
    """Authoritative usage before this initial-action reservation; no invented zero defaults."""

    limit_policy_id: UUID | None = field(default=None, repr=False)
    applications_today: int | None = None
    applications_this_week: int | None = None
    company_outreach: int | None = None
    contact_outreach: int | None = None

    def __post_init__(self) -> None:
        if self.limit_policy_id is not None:
            require_identifier(self.limit_policy_id)
        for value in (
            self.applications_today,
            self.applications_this_week,
            self.company_outreach,
            self.contact_outreach,
        ):
            validate_optional_usage(value)


@dataclass(frozen=True, slots=True)
class BudgetUsage:
    currency: str | None = None
    spent_today: Decimal | None = None
    spent_this_month: Decimal | None = None
    estimated_cost: Decimal | None = None
    estimated_tokens: int | None = None
    estimated_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.currency is not None:
            require_text(self.currency)
        for amount in (self.spent_today, self.spent_this_month, self.estimated_cost):
            validate_optional_usage(amount, monetary=True)
        for count in (self.estimated_tokens, self.estimated_seconds):
            validate_optional_usage(count)


@dataclass(frozen=True, slots=True)
class PolicyContext:
    """Trusted evaluated facts; never deserialize this snapshot from an agent/browser body."""

    now: datetime
    snapshot_at: datetime
    request_binding_sha256: str | None = field(default=None, repr=False)
    artifact_content_sha256: str | None = field(default=None, repr=False)
    artifact_categories: tuple[DataCategory, ...] = ()
    settings: Settings = field(default_factory=Settings, repr=False)
    purpose: CommunicationPurpose = CommunicationPurpose.UNKNOWN
    paused: bool = False
    grant: AuthorizationGrant | None = field(default=None, repr=False)
    sensitive_consents: tuple[SensitiveDataConsent, ...] = field(default=(), repr=False)
    account_email: str | None = field(default=None, repr=False)
    quota: QuotaUsage = field(default_factory=QuotaUsage)
    budget: BudgetUsage = field(default_factory=BudgetUsage)
    evidence: tuple[PolicyEvidence, ...] = ()

    def __post_init__(self) -> None:
        require_timestamp(self.now)
        require_timestamp(self.snapshot_at)
        for digest in (self.request_binding_sha256, self.artifact_content_sha256):
            if digest is not None:
                require_sha256(digest)
        validate_scope(self.artifact_categories, DataCategory)
        if not isinstance(self.settings, Settings) or not isinstance(self.paused, bool):
            raise DomainError("Policy safe-mode settings and pause state must be explicit.")
        if not isinstance(self.purpose, CommunicationPurpose):
            raise DomainError("Communication purpose must be an authoritative explicit value.")
        if self.grant is not None and not isinstance(self.grant, AuthorizationGrant):
            raise DomainError("Policy grants must be resolved domain records.")
        if self.account_email is not None:
            require_text(self.account_email)
        if not isinstance(self.quota, QuotaUsage) or not isinstance(self.budget, BudgetUsage):
            raise DomainError("Policy usage must be a validated authoritative snapshot.")
        validate_scope(self.sensitive_consents, SensitiveDataConsent)
        if len({consent.consent_id for consent in self.sensitive_consents}) != len(
            self.sensitive_consents
        ):
            raise DomainError("A context must contain only one authoritative version per consent.")
        validate_scope(self.evidence, PolicyEvidence)
        if len({item.requirement for item in self.evidence}) != len(self.evidence):
            raise DomainError("A policy requirement must not have duplicate evidence states.")


def evidence_status(context: PolicyContext, requirement: Requirement) -> EvidenceStatus:
    """Missing facts remain unknown rather than silently satisfying a gate."""
    return next(
        (item.status for item in context.evidence if item.requirement is requirement),
        EvidenceStatus.UNKNOWN,
    )
