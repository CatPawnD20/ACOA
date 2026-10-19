"""EP-01.02: bounded user grants and sharing scopes; P-01/P-02/P-17; ADR-006."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.reviews import ReviewDecision, UserReview, content_digest, validate_review_target
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class ActionKind(StrEnum):
    READ_PUBLIC_SOURCE = "read_public_source"
    SUBMIT_INITIAL_APPLICATION = "submit_initial_application"
    SEND_INITIAL_OUTREACH = "send_initial_outreach"
    CREATE_CAREER_ACCOUNT = "create_career_account"
    UPLOAD_CV = "upload_cv_for_initial_application"
    DRAFT_REPLY = "draft_reply"
    DRAFT_FOLLOWUP = "draft_followup"
    SEND_REPLY = "send_reply"
    SEND_FOLLOWUP = "send_followup"
    ACCEPT_OFFER = "accept_offer"
    SIGN_CONTRACT = "sign_contract"
    SHARE_SENSITIVE_DOCUMENT = "share_sensitive_id_or_financial_document"
    APPROVE_PROFILE_CLAIM = "approve_profile_claim"
    RUN_GENERATED_TOOL = "run_generated_tool"
    MODIFY_PRODUCTION_CODE = "modify_production_code"


class Channel(StrEnum):
    EMAIL = "email"
    WEB = "web"


class DataCategory(StrEnum):
    PROFESSIONAL_PROFILE = "professional_profile"
    CONTACT_DETAILS = "contact_details"
    CV = "cv"
    COVER_LETTER = "cover_letter"
    APPROVED_ANSWER = "approved_answer"
    IDENTITY_DOCUMENT = "identity_document"
    FINANCIAL_DOCUMENT = "financial_document"
    HEALTH_DATA = "health_data"
    BIOMETRIC_DATA = "biometric_data"
    OTHER_SENSITIVE_DOCUMENT = "other_sensitive_document"


SENSITIVE_CATEGORIES = frozenset(
    (
        DataCategory.IDENTITY_DOCUMENT,
        DataCategory.FINANCIAL_DOCUMENT,
        DataCategory.HEALTH_DATA,
        DataCategory.BIOMETRIC_DATA,
        DataCategory.OTHER_SENSITIVE_DOCUMENT,
    )
)


class PermissionMode(StrEnum):
    AUTO_ALLOWED = "auto_allowed"
    APPROVAL_REQUIRED = "approval_required"
    USER_SENDS = "user_sends"
    USER_ONLY = "user_only"
    SANDBOX_ONLY = "sandbox_only"
    DENY = "deny"


class RecipientClass(StrEnum):
    VERIFIED_OFFICIAL_APPLICATION_EMAIL = "verified_official_application_email"
    VERIFIED_PUBLIC_CORPORATE_RECRUITING_CONTACT = (
        "verified_public_corporate_recruiting_contact"
    )


def validate_scope(values: tuple[object, ...], item_type: type) -> None:
    """Reject wildcard coercion, mutable scopes, duplicates and unknown enum values."""
    if not isinstance(values, tuple) or any(not isinstance(value, item_type) for value in values):
        raise DomainError("A permission scope must be an immutable tuple of explicit values.")
    if len(set(values)) != len(values):
        raise DomainError("A permission scope must not contain duplicates.")


def validate_permission_window(
    starts_at: datetime, expires_at: datetime, revoked_at: datetime | None
) -> None:
    """Require a finite ordered window and an explicit revocation timestamp."""
    require_timestamp(starts_at)
    require_timestamp(expires_at)
    if expires_at <= starts_at:
        raise DomainError("Permission expiry must follow its start.")
    if revoked_at is not None:
        require_timestamp(revoked_at)


@dataclass(frozen=True, slots=True)
class AuthorizationGrant:
    """A declaration, never proof of authenticated origin or executor authority by itself."""

    grant_id: UUID = field(repr=False)
    version: int
    policy_version: str
    starts_at: datetime
    expires_at: datetime
    actions: tuple[ActionKind, ...]
    channels: tuple[Channel, ...]
    recipient_ids: tuple[UUID, ...] = field(repr=False)
    account_ids: tuple[UUID, ...] = field(repr=False)
    data_categories: tuple[DataCategory, ...]
    limit_policy_id: UUID = field(repr=False)
    created_at: datetime
    approval: UserReview | None = field(default=None, repr=False)
    revoked_at: datetime | None = None
    recipient_classes: tuple[RecipientClass, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.grant_id)
        require_identifier(self.limit_policy_id)
        require_version(self.version)
        require_text(self.policy_version)
        require_timestamp(self.created_at)
        validate_permission_window(self.starts_at, self.expires_at, self.revoked_at)
        validate_scope(self.actions, ActionKind)
        validate_scope(self.channels, Channel)
        validate_scope(self.recipient_ids, UUID)
        validate_scope(self.account_ids, UUID)
        validate_scope(self.data_categories, DataCategory)
        validate_scope(self.recipient_classes, RecipientClass)
        if self.approval is not None:
            validate_grant_approval(self, self.approval)


def grant_content_sha256(grant: AuthorizationGrant) -> str:
    """Bind approval to exact action/account/recipient/data/limit-policy declarations."""
    payload: dict[str, object] = {
        "grant_id": str(grant.grant_id),
        "version": grant.version,
        "policy_version": grant.policy_version,
        "starts_at": grant.starts_at.astimezone(UTC).isoformat(),
        "expires_at": grant.expires_at.astimezone(UTC).isoformat(),
        "actions": [action.value for action in grant.actions],
        "channels": [channel.value for channel in grant.channels],
        "recipients": [str(identifier) for identifier in grant.recipient_ids],
        "accounts": [str(identifier) for identifier in grant.account_ids],
        "data_categories": [category.value for category in grant.data_categories],
        "limit_policy_id": str(grant.limit_policy_id),
    }
    if grant.recipient_classes:
        payload["recipient_classes"] = [item.value for item in grant.recipient_classes]
    return content_digest(payload)


def validate_grant_approval(grant: AuthorizationGrant, review: UserReview) -> None:
    """Require exact, affirmative user approval and a nonempty bounded sending scope."""
    validate_review_target(
        review, grant.grant_id, grant.version, grant.created_at, grant_content_sha256(grant)
    )
    if review.decision is not ReviewDecision.APPROVE:
        raise DomainError("A grant requires affirmative user approval.")
    if grant.revoked_at is not None:
        raise DomainError("A revoked grant must not retain executable approval.")
    if not all((grant.actions, grant.channels, grant.account_ids)) or not (
        grant.recipient_ids or grant.recipient_classes
    ):
        raise DomainError("An approved external-action grant requires complete bounded scopes.")


def approve_grant(grant: AuthorizationGrant, review: UserReview) -> AuthorizationGrant:
    """Attach an exact recorded approval without activating any external integration."""
    validate_grant_approval(grant, review)
    return replace(grant, approval=review)


def revoke_grant(grant: AuthorizationGrant, revoked_at: datetime) -> AuthorizationGrant:
    """Advance the authoritative version and remove approval on revocation."""
    require_timestamp(revoked_at)
    if revoked_at < grant.created_at or (
        grant.approval is not None and revoked_at < grant.approval.reviewed_at
    ):
        raise DomainError("A revocation must not predate grant creation or approval.")
    if grant.revoked_at is not None:
        return grant
    return replace(grant, version=grant.version + 1, approval=None, revoked_at=revoked_at)


def grant_is_active(grant: AuthorizationGrant, now: datetime) -> bool:
    """Evaluate the selected authoritative snapshot at execution time, never an old cache."""
    require_timestamp(now)
    return (
        grant.approval is not None
        and grant.revoked_at is None
        and grant.created_at <= now
        and grant.approval.reviewed_at <= now
        and grant.starts_at <= now < grant.expires_at
    )


@dataclass(frozen=True, slots=True)
class SensitiveDataConsent:
    """Separate content-bound approval for sensitive categories within one exact grant."""

    consent_id: UUID = field(repr=False)
    version: int
    grant_id: UUID = field(repr=False)
    grant_version: int
    grant_sha256: str = field(repr=False)
    categories: tuple[DataCategory, ...]
    starts_at: datetime
    expires_at: datetime
    created_at: datetime
    approval: UserReview | None = field(default=None, repr=False)
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        require_identifier(self.consent_id)
        require_identifier(self.grant_id)
        require_version(self.version)
        require_version(self.grant_version)
        require_sha256(self.grant_sha256)
        require_timestamp(self.created_at)
        validate_permission_window(self.starts_at, self.expires_at, self.revoked_at)
        validate_scope(self.categories, DataCategory)
        if not self.categories or not set(self.categories) <= SENSITIVE_CATEGORIES:
            raise DomainError("Sensitive consent must name explicit sensitive categories.")
        if self.approval is not None:
            validate_sensitive_approval(self, self.approval)


def consent_content_sha256(consent: SensitiveDataConsent) -> str:
    """Bind separate consent to the exact parent grant and a finite category window."""
    return content_digest(
        {
            "consent_id": str(consent.consent_id),
            "version": consent.version,
            "grant_id": str(consent.grant_id),
            "grant_version": consent.grant_version,
            "grant_sha256": consent.grant_sha256,
            "categories": [category.value for category in consent.categories],
            "starts_at": consent.starts_at.astimezone(UTC).isoformat(),
            "expires_at": consent.expires_at.astimezone(UTC).isoformat(),
        }
    )


def validate_sensitive_approval(consent: SensitiveDataConsent, review: UserReview) -> None:
    """Require a distinct user decision; general profile approval is insufficient."""
    validate_review_target(
        review,
        consent.consent_id,
        consent.version,
        consent.created_at,
        consent_content_sha256(consent),
    )
    if review.decision is not ReviewDecision.APPROVE or consent.revoked_at is not None:
        raise DomainError("Sensitive consent requires affirmative, unrevoked approval.")


def approve_sensitive_consent(
    consent: SensitiveDataConsent, review: UserReview
) -> SensitiveDataConsent:
    """Attach the separately recorded human decision to the exact consent contents."""
    validate_sensitive_approval(consent, review)
    return replace(consent, approval=review)


def revoke_sensitive_consent(
    consent: SensitiveDataConsent, revoked_at: datetime
) -> SensitiveDataConsent:
    """Remove separate sensitive authority and retain the old immutable decision record."""
    require_timestamp(revoked_at)
    if revoked_at < consent.created_at or (
        consent.approval is not None and revoked_at < consent.approval.reviewed_at
    ):
        raise DomainError("A revocation must not predate consent creation or approval.")
    if consent.revoked_at is not None:
        return consent
    return replace(consent, version=consent.version + 1, approval=None, revoked_at=revoked_at)


def sensitive_consent_covers(
    consent: SensitiveDataConsent,
    grant: AuthorizationGrant,
    categories: tuple[DataCategory, ...],
    now: datetime,
) -> bool:
    """Reject expired, revoked, stale-parent or incomplete sensitive consent."""
    require_timestamp(now)
    validate_scope(categories, DataCategory)
    return (
        grant_is_active(grant, now)
        and consent.approval is not None
        and consent.revoked_at is None
        and consent.created_at <= now
        and consent.approval.reviewed_at <= now
        and consent.starts_at <= now < consent.expires_at
        and consent.grant_id == grant.grant_id
        and consent.grant_version == grant.version
        and consent.grant_sha256 == grant_content_sha256(grant)
        and set(categories) <= set(consent.categories)
        and set(categories) <= set(grant.data_categories)
    )
