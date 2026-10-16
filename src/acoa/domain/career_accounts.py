"""Career-account plans, secret references and fail-closed outcomes; EP-08.03."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from uuid import UUID

from acoa.domain.authorization import DataCategory, validate_scope
from acoa.domain.browser import public_https_origin
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
)


class CareerAccountObstacle(StrEnum):
    CAPTCHA = "captcha"
    MFA = "mfa"
    ADDITIONAL_DATA = "additional_data"
    BINDING_TERMS = "binding_terms"
    ACCESS_DENIED = "access_denied"


class CareerAccountResultKind(StrEnum):
    CREATED = "created"
    WAITING_USER = "waiting_user"
    FAILED = "failed"
    UNCONFIRMED = "unconfirmed"


@dataclass(frozen=True, slots=True)
class CareerAccountPlan:
    plan_id: UUID = field(repr=False)
    account_id: UUID = field(repr=False)
    task_id: UUID = field(repr=False)
    application_id: UUID = field(repr=False)
    provider_id: UUID = field(repr=False)
    browser_permit_id: UUID = field(repr=False)
    allowed_origin: str
    login_sha256: str = field(repr=False)
    terms_sha256: str = field(repr=False)
    data_categories: tuple[DataCategory, ...]
    created_at: datetime
    expires_at: datetime

    def __post_init__(self) -> None:
        for identifier in (
            self.plan_id,
            self.account_id,
            self.task_id,
            self.application_id,
            self.provider_id,
            self.browser_permit_id,
        ):
            require_identifier(identifier)
        if self.allowed_origin != public_https_origin(self.allowed_origin):
            raise DomainError("A career-account plan requires a canonical trusted origin.")
        require_sha256(self.login_sha256)
        require_sha256(self.terms_sha256)
        validate_scope(self.data_categories, DataCategory)
        if not self.data_categories:
            raise DomainError("A career-account plan requires explicit data categories.")
        require_timestamp(self.created_at)
        require_timestamp(self.expires_at)
        if self.expires_at <= self.created_at:
            raise DomainError("Career-account plan expiry must follow creation.")


def career_account_plan_sha256(plan: CareerAccountPlan) -> str:
    return content_digest(
        {
            "schema": "acoa-career-account-plan/1",
            "plan_id": str(plan.plan_id),
            "account_id": str(plan.account_id),
            "task_id": str(plan.task_id),
            "application_id": str(plan.application_id),
            "provider_id": str(plan.provider_id),
            "browser_permit_id": str(plan.browser_permit_id),
            "allowed_origin": plan.allowed_origin,
            "login_sha256": plan.login_sha256,
            "terms_sha256": plan.terms_sha256,
            "data_categories": [item.value for item in plan.data_categories],
            "created_at": plan.created_at.astimezone(UTC).isoformat(),
            "expires_at": plan.expires_at.astimezone(UTC).isoformat(),
        }
    )


@dataclass(frozen=True, slots=True)
class CareerAccountMaterial:
    plan_id: UUID = field(repr=False)
    login_identifier: str = field(repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.plan_id)
        require_text(self.login_identifier)


@dataclass(frozen=True, slots=True)
class AccountCredential:
    secret_ref_id: UUID = field(repr=False)
    login_identifier: str = field(repr=False)
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        require_identifier(self.secret_ref_id)
        require_text(self.login_identifier)
        require_text(self.password)
        if len(self.password) < 32:
            raise DomainError("Generated career-account credentials require high entropy.")


@dataclass(frozen=True, slots=True)
class CareerAccountProviderResult:
    kind: CareerAccountResultKind
    obstacles: tuple[CareerAccountObstacle, ...] = ()
    provider_account_sha256: str | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CareerAccountResultKind):
            raise DomainError("A career-account result requires an explicit kind.")
        validate_scope(self.obstacles, CareerAccountObstacle)
        if self.kind is CareerAccountResultKind.CREATED:
            if self.obstacles or self.provider_account_sha256 is None:
                raise DomainError("Created accounts require exact provider evidence.")
            require_sha256(self.provider_account_sha256)
        elif self.kind is CareerAccountResultKind.WAITING_USER:
            if not self.obstacles or self.provider_account_sha256 is not None:
                raise DomainError("Account handoff requires obstacles without success evidence.")
        elif self.obstacles or self.provider_account_sha256 is not None:
            raise DomainError("Failed or uncertain account results cannot claim provider evidence.")


@dataclass(frozen=True, slots=True)
class CareerAccountEvent:
    event_id: UUID = field(repr=False)
    plan_id: UUID = field(repr=False)
    attempt_id: UUID = field(repr=False)
    secret_ref_id: UUID = field(repr=False)
    result: CareerAccountProviderResult
    observed_at: datetime

    def __post_init__(self) -> None:
        for identifier in (self.event_id, self.plan_id, self.attempt_id, self.secret_ref_id):
            require_identifier(identifier)
        if not isinstance(self.result, CareerAccountProviderResult):
            raise DomainError("A career-account event requires a validated result.")
        require_timestamp(self.observed_at)


def login_identifier_sha256(value: str) -> str:
    require_text(value)
    return sha256(value.encode()).hexdigest()
