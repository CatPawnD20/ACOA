"""EP-01.01: F-01.01–07; P-03/P-05/P-18; ADR-001/002."""

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from acoa.domain.reviews import ReviewDecision as ReviewDecision
from acoa.domain.reviews import UserReview as UserReview
from acoa.domain.reviews import content_digest
from acoa.domain.reviews import validate_review_target as validate_review_target
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_text,
    require_timestamp,
    require_version,
)


class SourceKind(StrEnum):
    USER_STATEMENT = "user_statement"
    DOCUMENT = "document"
    EXTERNAL = "external"


class VerificationStatus(StrEnum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    CONFLICTED = "conflicted"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_id: UUID = field(repr=False)
    kind: SourceKind
    observed_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.source_id)
        require_timestamp(self.observed_at)
        if not isinstance(self.kind, SourceKind):
            raise DomainError("A source kind must be explicit.")


def validate_sources(sources: tuple[SourceReference, ...], updated_at: datetime) -> None:
    """Require immutable, unique source references available when the fact was recorded."""
    if not isinstance(sources, tuple) or any(
        not isinstance(source, SourceReference) for source in sources
    ):
        raise DomainError("Fact sources must be an immutable tuple of source references.")
    if len({source.source_id for source in sources}) != len(sources):
        raise DomainError("A fact must not repeat a source reference.")
    if any(source.observed_at > updated_at for source in sources):
        raise DomainError("A fact cannot predate its source observations.")


@dataclass(frozen=True, slots=True)
class ProfileFact:
    fact_id: UUID = field(repr=False)
    kind: str = field(repr=False)
    value: str = field(repr=False)
    updated_at: datetime
    sources: tuple[SourceReference, ...] = field(default=(), repr=False)
    version: int = 1
    status: VerificationStatus = VerificationStatus.UNVERIFIED
    review: UserReview | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.fact_id)
        require_text(self.kind)
        require_text(self.value)
        require_timestamp(self.updated_at)
        require_version(self.version)
        validate_sources(self.sources, self.updated_at)
        validate_fact_verification(self)


def fact_content_sha256(fact: ProfileFact) -> str:
    """Bind approval to exact claim content and source references, not status metadata."""
    payload = {
        "fact_id": str(fact.fact_id),
        "version": fact.version,
        "kind": fact.kind,
        "value": fact.value,
        "sources": [
            [
                str(source.source_id),
                source.kind.value,
                source.observed_at.astimezone(UTC).isoformat(),
            ]
            for source in fact.sources
        ],
    }
    return content_digest(payload)


def validate_fact_verification(fact: ProfileFact) -> None:
    """Reject source-only verification and inconsistent persisted review state."""
    if not isinstance(fact.status, VerificationStatus):
        raise DomainError("A fact verification status must be explicit.")
    if fact.status in (VerificationStatus.UNVERIFIED, VerificationStatus.CONFLICTED):
        if fact.review is not None:
            raise DomainError("An unresolved fact must not retain an approval record.")
        return
    if fact.review is None or not isinstance(fact.review, UserReview):
        raise DomainError("A resolved fact requires its user review record.")
    validate_review_target(
        fact.review, fact.fact_id, fact.version, fact.updated_at, fact_content_sha256(fact)
    )
    if fact.review.reviewed_at != fact.updated_at:
        raise DomainError("A resolved fact update must match its review timestamp.")
    expected = (
        ReviewDecision.APPROVE
        if fact.status is VerificationStatus.VERIFIED
        else ReviewDecision.REJECT
    )
    if fact.review.decision is not expected:
        raise DomainError("Fact status conflicts with the user decision.")
    if fact.status is VerificationStatus.VERIFIED and not fact.sources:
        raise DomainError("A verified fact requires a source reference.")


def review_fact(fact: ProfileFact, review: UserReview) -> ProfileFact:
    """Apply an exact user decision; repeated delivery of the same review is harmless."""
    if not isinstance(review, UserReview):
        raise DomainError("A trusted user review record is required.")
    if fact.review == review:
        return fact
    if fact.status not in (VerificationStatus.UNVERIFIED, VerificationStatus.CONFLICTED):
        raise DomainError("A resolved fact must be revised before another review.")
    validate_review_target(
        review, fact.fact_id, fact.version, fact.updated_at, fact_content_sha256(fact)
    )
    status = (
        VerificationStatus.VERIFIED
        if review.decision is ReviewDecision.APPROVE
        else VerificationStatus.REJECTED
    )
    return replace(fact, status=status, review=review, updated_at=review.reviewed_at)


def revise_fact(
    fact: ProfileFact, value: str, sources: tuple[SourceReference, ...], updated_at: datetime
) -> ProfileFact:
    """Preserve the prior immutable version and require fresh approval for a correction."""
    require_timestamp(updated_at)
    if updated_at < fact.updated_at:
        raise DomainError("A fact correction must not be backdated.")
    return replace(
        fact,
        value=value,
        sources=sources,
        updated_at=updated_at,
        version=fact.version + 1,
        status=VerificationStatus.UNVERIFIED,
        review=None,
    )


def mark_fact_conflicted(fact: ProfileFact, updated_at: datetime) -> ProfileFact:
    """Invalidate approval when a claim is disputed, without erasing its old version."""
    require_timestamp(updated_at)
    if updated_at < fact.updated_at:
        raise DomainError("A conflict observation must not be backdated.")
    return replace(
        fact,
        updated_at=updated_at,
        version=fact.version + 1,
        status=VerificationStatus.CONFLICTED,
        review=None,
    )


@dataclass(frozen=True, slots=True)
class ProfileVariant:
    variant_id: UUID = field(repr=False)
    facts: tuple[ProfileFact, ...] = field(repr=False)
    updated_at: datetime
    version: int = 1
    review: UserReview | None = field(default=None, repr=False)
    active: bool = False
    valid_until: datetime | None = None

    def __post_init__(self) -> None:
        require_identifier(self.variant_id)
        require_version(self.version)
        require_timestamp(self.updated_at)
        validate_variant_facts(self.facts, self.updated_at)
        validate_variant_review(self)


def validate_variant_facts(facts: tuple[ProfileFact, ...], updated_at: datetime) -> None:
    """Reject mutable, duplicate or future-dated facts in a profile snapshot."""
    if not isinstance(facts, tuple) or any(not isinstance(fact, ProfileFact) for fact in facts):
        raise DomainError("Variant facts must be an immutable tuple of profile facts.")
    if len({fact.fact_id for fact in facts}) != len(facts):
        raise DomainError("A profile variant must not repeat a fact identifier.")
    if any(fact.updated_at > updated_at for fact in facts):
        raise DomainError("A profile variant cannot predate its facts.")


def variant_content_sha256(variant: ProfileVariant) -> str:
    """Bind variant approval to exact claim versions, approvals and validity."""
    payload = {
        "variant_id": str(variant.variant_id),
        "version": variant.version,
        "valid_until": variant.valid_until.astimezone(UTC).isoformat()
        if variant.valid_until
        else None,
        "facts": [
            [
                fact_content_sha256(fact),
                fact.status.value,
                str(fact.review.review_id) if fact.review else None,
            ]
            for fact in variant.facts
        ],
    }
    return content_digest(payload)


def validate_variant_review(variant: ProfileVariant) -> None:
    """Require approved facts and an exact review before a variant can be active."""
    if not isinstance(variant.active, bool):
        raise DomainError("Variant activity must be a boolean.")
    if variant.valid_until is not None:
        require_timestamp(variant.valid_until)
        if variant.valid_until <= variant.updated_at:
            raise DomainError("A variant validity deadline must follow its update.")
    if variant.review is not None:
        validate_review_target(
            variant.review,
            variant.variant_id,
            variant.version,
            variant.updated_at,
            variant_content_sha256(variant),
        )
    if variant.active and (
        variant.review is None
        or variant.review.decision is not ReviewDecision.APPROVE
        or not variant.facts
        or any(fact.status is not VerificationStatus.VERIFIED for fact in variant.facts)
    ):
        raise DomainError("An active variant requires exact approval and verified facts.")


def activate_variant(variant: ProfileVariant, review: UserReview) -> ProfileVariant:
    """Activate only the exact approved snapshot; changing facts requires a new version."""
    validate_review_target(
        review,
        variant.variant_id,
        variant.version,
        variant.updated_at,
        variant_content_sha256(variant),
    )
    if review.decision is not ReviewDecision.APPROVE:
        raise DomainError("A rejected variant cannot be activated.")
    return replace(variant, review=review, active=True, updated_at=review.reviewed_at)


def revise_variant(
    variant: ProfileVariant,
    facts: tuple[ProfileFact, ...],
    updated_at: datetime,
    valid_until: datetime | None = None,
) -> ProfileVariant:
    """Replace a snapshot's content with a new inactive version requiring fresh review."""
    require_timestamp(updated_at)
    if updated_at < variant.updated_at:
        raise DomainError("A variant correction must not be backdated.")
    return replace(
        variant,
        facts=facts,
        updated_at=updated_at,
        version=variant.version + 1,
        active=False,
        review=None,
        valid_until=valid_until,
    )


def variant_is_usable(variant: ProfileVariant, now: datetime) -> bool:
    """Evaluate activity and expiration at use time without choosing another variant."""
    require_timestamp(now)
    return (
        variant.active
        and variant.review is not None
        and variant.review.reviewed_at <= now
        and variant.updated_at <= now
        and (variant.valid_until is None or now < variant.valid_until)
    )
