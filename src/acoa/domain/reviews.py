"""Exact human-decision records shared by profile and permissions; P-17/P-18."""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"


@dataclass(frozen=True, slots=True)
class UserReview:
    """A recorded user decision supplied only by a trusted human-input adapter."""

    review_id: UUID = field(repr=False)
    target_id: UUID = field(repr=False)
    target_version: int
    content_sha256: str = field(repr=False)
    decision: ReviewDecision
    reviewed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.review_id)
        require_identifier(self.target_id)
        require_version(self.target_version)
        require_sha256(self.content_sha256)
        require_timestamp(self.reviewed_at)
        if not isinstance(self.decision, ReviewDecision):
            raise DomainError("A review decision must be explicit.")


def validate_review_target(
    review: UserReview, target_id: UUID, version: int, updated_at: datetime, content_sha256: str
) -> None:
    """Bind human review to an exact object version/content and prohibit backdating."""
    if not isinstance(review, UserReview):
        raise DomainError("A trusted user review record is required.")
    if review.target_id != target_id or review.target_version != version:
        raise DomainError("The review targets another object or a stale version.")
    if review.content_sha256 != content_sha256:
        raise DomainError("The reviewed content differs from the current object.")
    if review.reviewed_at < updated_at:
        raise DomainError("The review predates the reviewed version.")


def content_digest(payload: dict[str, object]) -> str:
    """Hash canonical review content locally without logging or transmitting values."""
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
