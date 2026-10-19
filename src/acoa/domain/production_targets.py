"""Content-bound production recipient enrollment; EP-10.06, P-01/P-02/P-17."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from acoa.domain.authorization import RecipientClass
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


@dataclass(frozen=True, slots=True)
class ProductionRecipientEnrollment:
    """Immutable proof binding one recipient and target to the current approved grant."""

    enrollment_id: UUID
    recipient_id: UUID = field(repr=False)
    recipient_class: RecipientClass
    grant_id: UUID = field(repr=False)
    grant_version: int
    organization_id: UUID
    target_id: UUID
    target_version: int
    target_content_sha256: str = field(repr=False)
    channel_id: UUID
    channel_version: int
    channel_content_sha256: str = field(repr=False)
    endpoint_sha256: str = field(repr=False)
    employer_verification_id: UUID
    employer_verification_version: int
    employer_verification_sha256: str = field(repr=False)
    enrolled_at: datetime
    valid_until: datetime
    content_sha256: str = field(repr=False)

    def __post_init__(self) -> None:
        for identifier in (
            self.enrollment_id,
            self.recipient_id,
            self.grant_id,
            self.organization_id,
            self.target_id,
            self.channel_id,
            self.employer_verification_id,
        ):
            require_identifier(identifier)
        for version in (
            self.grant_version,
            self.target_version,
            self.channel_version,
            self.employer_verification_version,
        ):
            require_version(version)
        for digest in (
            self.target_content_sha256,
            self.channel_content_sha256,
            self.endpoint_sha256,
            self.employer_verification_sha256,
            self.content_sha256,
        ):
            require_sha256(digest)
        require_timestamp(self.enrolled_at)
        require_timestamp(self.valid_until)
        if not isinstance(self.recipient_class, RecipientClass):
            raise DomainError("A production recipient requires an approved recipient class.")
        if self.recipient_id != self.channel_id:
            raise DomainError("A production recipient must use its canonical channel identifier.")
        if self.valid_until <= self.enrolled_at:
            raise DomainError("A production recipient enrollment requires a future expiry.")
        if self.content_sha256 != production_recipient_enrollment_sha256(self):
            raise DomainError("A production recipient digest must bind its exact evidence.")


def production_recipient_enrollment_sha256(
    enrollment: ProductionRecipientEnrollment,
) -> str:
    """Bind the enrollment to exact authority, target, channel and verification versions."""
    return production_recipient_enrollment_binding_sha256(
        enrollment.enrollment_id,
        enrollment.recipient_id,
        enrollment.recipient_class,
        enrollment.grant_id,
        enrollment.grant_version,
        enrollment.organization_id,
        enrollment.target_id,
        enrollment.target_version,
        enrollment.target_content_sha256,
        enrollment.channel_id,
        enrollment.channel_version,
        enrollment.channel_content_sha256,
        enrollment.endpoint_sha256,
        enrollment.employer_verification_id,
        enrollment.employer_verification_version,
        enrollment.employer_verification_sha256,
        enrollment.enrolled_at,
        enrollment.valid_until,
    )


def production_recipient_enrollment_binding_sha256(
    enrollment_id: UUID,
    recipient_id: UUID,
    recipient_class: RecipientClass,
    grant_id: UUID,
    grant_version: int,
    organization_id: UUID,
    target_id: UUID,
    target_version: int,
    target_content_sha256: str,
    channel_id: UUID,
    channel_version: int,
    channel_content_sha256: str,
    endpoint_sha256: str,
    employer_verification_id: UUID,
    employer_verification_version: int,
    employer_verification_sha256: str,
    enrolled_at: datetime,
    valid_until: datetime,
) -> str:
    """Create the digest before constructing the immutable enrollment value."""
    return content_digest(
        {
            "schema": "acoa-production-recipient-enrollment/1",
            "enrollment_id": str(enrollment_id),
            "recipient_id": str(recipient_id),
            "recipient_class": recipient_class.value,
            "grant_id": str(grant_id),
            "grant_version": grant_version,
            "organization_id": str(organization_id),
            "target_id": str(target_id),
            "target_version": target_version,
            "target_content_sha256": target_content_sha256,
            "channel_id": str(channel_id),
            "channel_version": channel_version,
            "channel_content_sha256": channel_content_sha256,
            "endpoint_sha256": endpoint_sha256,
            "employer_verification_id": str(employer_verification_id),
            "employer_verification_version": employer_verification_version,
            "employer_verification_sha256": employer_verification_sha256,
            "enrolled_at": enrolled_at.astimezone(UTC).isoformat(),
            "valid_until": valid_until.astimezone(UTC).isoformat(),
        }
    )
