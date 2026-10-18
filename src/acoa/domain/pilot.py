"""Controlled live-pilot target authorization; EP-10.05, G4."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from uuid import UUID

from acoa.domain.mail import require_email
from acoa.domain.reviews import ReviewDecision, UserReview, content_digest, validate_review_target
from acoa.domain.values import DomainError, require_identifier, require_sha256, require_timestamp


@dataclass(frozen=True, slots=True)
class ControlledMailTarget:
    """An exact, user-controlled address approved only for the bounded pilot."""

    target_id: UUID = field(repr=False)
    version: int
    account_id: UUID = field(repr=False)
    recipient_id: UUID = field(repr=False)
    sender_email: str = field(repr=False)
    recipient_email: str = field(repr=False)
    control_evidence_sha256: str = field(repr=False)
    created_at: datetime
    expires_at: datetime
    approval: UserReview | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        for identifier in (self.target_id, self.account_id, self.recipient_id):
            require_identifier(identifier)
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise DomainError("A controlled pilot target requires a positive version.")
        require_email(self.sender_email)
        require_email(self.recipient_email)
        require_sha256(self.control_evidence_sha256)
        require_timestamp(self.created_at)
        require_timestamp(self.expires_at)
        if self.expires_at <= self.created_at:
            raise DomainError("A controlled pilot target requires a finite future expiry.")
        if self.approval is not None:
            validate_controlled_mail_target_approval(self, self.approval)

    def is_current(self, now: datetime) -> bool:
        require_timestamp(now)
        return (
            self.approval is not None
            and self.created_at <= self.approval.reviewed_at <= now < self.expires_at
        )


def controlled_mail_target_sha256(target: ControlledMailTarget) -> str:
    """Bind approval to both addresses, opaque policy IDs and control evidence."""
    return content_digest(
        {
            "schema": "acoa-controlled-mail-target/1",
            "target_id": str(target.target_id),
            "version": target.version,
            "account_id": str(target.account_id),
            "recipient_id": str(target.recipient_id),
            "sender_email": target.sender_email,
            "recipient_email": target.recipient_email,
            "control_evidence_sha256": target.control_evidence_sha256,
            "created_at": target.created_at.astimezone(UTC).isoformat(),
            "expires_at": target.expires_at.astimezone(UTC).isoformat(),
        }
    )


def validate_controlled_mail_target_approval(
    target: ControlledMailTarget, review: UserReview
) -> None:
    validate_review_target(
        review,
        target.target_id,
        target.version,
        target.created_at,
        controlled_mail_target_sha256(target),
    )
    if review.decision is not ReviewDecision.APPROVE:
        raise DomainError("A controlled pilot target requires affirmative user approval.")


def approve_controlled_mail_target(
    target: ControlledMailTarget, review: UserReview
) -> ControlledMailTarget:
    """Attach trusted human approval to the exact controlled target content."""
    validate_controlled_mail_target_approval(target, review)
    return replace(target, approval=review)
