"""EP-02.03 action preparation and one-attempt state rules; P-11, ADR-007."""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.action_requests import PolicyRequest, request_binding_sha256
from acoa.domain.applications import (
    ApplicationKind,
    ApplicationSnapshot,
    ApplicationState,
    SubmissionState,
    semantic_operation_key,
)
from acoa.domain.authorization import ActionKind
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_timestamp,
    require_version,
)


class ActionState(StrEnum):
    PREPARED = "prepared"
    RESERVED = "reserved"
    EXECUTING = "executing"
    RECONCILING = "reconciling"
    VERIFIED = "verified"
    FAILED = "failed"
    UNCONFIRMED = "unconfirmed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class PreparedAction:
    """Opaque material references only; this value cannot authorize an external call."""

    attempt_id: UUID
    application_id: UUID
    semantic_key: str = field(repr=False)
    request: PolicyRequest
    plan_id: UUID = field(repr=False)
    artifact_id: UUID = field(repr=False)
    artifact_version: int
    provider_id: UUID

    def __post_init__(self) -> None:
        for identifier in (
            self.attempt_id,
            self.application_id,
            self.plan_id,
            self.artifact_id,
            self.provider_id,
        ):
            require_identifier(identifier)
        require_sha256(self.semantic_key)
        require_version(self.artifact_version)
        if not isinstance(self.request, PolicyRequest) or self.request.action not in (
            ActionKind.SUBMIT_INITIAL_APPLICATION,
            ActionKind.SEND_INITIAL_OUTREACH,
        ):
            raise DomainError("Initial-action execution requires an explicit supported request.")


@dataclass(frozen=True, slots=True)
class DispatchLimits:
    """Mandatory provider contract: deadline, bounded I/O timeout and reserved maximum cost."""

    deadline: datetime
    timeout_seconds: int
    max_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        require_timestamp(self.deadline)
        require_version(self.timeout_seconds)
        if (
            not isinstance(self.max_cost, Decimal)
            or not self.max_cost.is_finite()
            or self.max_cost < 0
        ):
            raise DomainError("Dispatch cost must be a finite nonnegative Decimal.")
        if (
            not isinstance(self.currency, str)
            or len(self.currency) != 3
            or any(character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for character in self.currency)
        ):
            raise DomainError("Dispatch currency must be an explicit uppercase currency label.")


def validate_prepared_application(
    prepared: PreparedAction, application: ApplicationSnapshot
) -> None:
    """Bind initial action kind and semantic identity to an open unsent canonical episode."""
    expected = (
        ActionKind.SUBMIT_INITIAL_APPLICATION
        if application.spec.identity.kind is ApplicationKind.INITIAL_APPLICATION
        else ActionKind.SEND_INITIAL_OUTREACH
    )
    if (
        prepared.application_id != application.spec.application_id
        or prepared.semantic_key != semantic_operation_key(application.spec)
        or prepared.request.action is not expected
        or application.state is not ApplicationState.OPEN
        or application.submission_state is not SubmissionState.NOT_STARTED
    ):
        raise DomainError("Prepared action does not match an open unsent canonical application.")


def prepared_binding_sha256(prepared: PreparedAction) -> str:
    """Bind facts to the exact application, plan, material, provider and request identity."""
    request = prepared.request
    return content_digest(
        {
            "attempt_id": str(prepared.attempt_id),
            "application_id": str(prepared.application_id),
            "semantic_key": prepared.semantic_key,
            "plan_id": str(prepared.plan_id),
            "artifact_id": str(prepared.artifact_id),
            "artifact_version": prepared.artifact_version,
            "provider_id": str(prepared.provider_id),
            "request_sha256": request_binding_sha256(request),
        }
    )
