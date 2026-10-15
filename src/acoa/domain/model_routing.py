"""EP-03.02 provider scopes and deterministic routing contracts; ADR-004/015."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import IntEnum, StrEnum
from uuid import UUID

from acoa.domain.authorization import DataCategory, validate_scope
from acoa.domain.model_calls import require_amount, require_currency
from acoa.domain.model_privacy import DataSensitivity, ProviderPermission, validate_data_scope
from acoa.domain.model_quality import require_quality
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_text,
    require_timestamp,
    require_version,
)


class Severity(IntEnum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3


class ProcessingTier(IntEnum):
    T0 = 0
    T1 = 1
    T2 = 2
    T3 = 3


class RoutingStrategy(StrEnum):
    DETERMINISTIC = "deterministic"
    MODEL = "model"
    HUMAN = "human"
    DEFER = "defer"


@dataclass(frozen=True, slots=True)
class ModelOption:
    provider_id: UUID
    model_alias: str
    tier: ProcessingTier
    input_token_limit: int
    output_token_limit: int
    timeout_seconds: int
    max_cost: Decimal
    currency: str
    estimated_quality: Decimal
    estimate_evidence_id: UUID
    expires_at: datetime

    def __post_init__(self) -> None:
        require_identifier(self.provider_id)
        require_identifier(self.estimate_evidence_id)
        require_text(self.model_alias)
        if not isinstance(self.tier, ProcessingTier) or self.tier is ProcessingTier.T0:
            raise DomainError("Model options require T1, T2 or T3.")
        for value in (self.input_token_limit, self.output_token_limit, self.timeout_seconds):
            require_version(value)
        require_amount(self.max_cost)
        require_currency(self.currency)
        require_quality(self.estimated_quality)
        require_timestamp(self.expires_at)


@dataclass(frozen=True, slots=True)
class RoutingTask:
    task_type: str
    deterministic_adequate: bool = False
    requires_user_decision: bool = False
    risk: Severity | None = None
    uncertainty: Severity | None = None
    complexity: Severity | None = None
    required_quality: Decimal | None = None
    latency_budget: int | None = None
    remaining_tokens: int | None = None
    remaining_currency: Decimal | None = None
    currency: str | None = None
    sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    categories: tuple[DataCategory, ...] = ()
    required_input_tokens: int | None = None

    def __post_init__(self) -> None:
        require_text(self.task_type)
        if not isinstance(self.deterministic_adequate, bool) or not isinstance(
            self.requires_user_decision, bool
        ):
            raise DomainError("Routing adequacy and user-decision requirements must be explicit.")
        for value in (self.risk, self.uncertainty, self.complexity):
            if value is not None and not isinstance(value, Severity):
                raise DomainError("Routing severity must be explicit or unknown.")
        if self.required_quality is not None:
            require_quality(self.required_quality)
        for count in (self.latency_budget, self.remaining_tokens, self.required_input_tokens):
            if count is not None and (
                isinstance(count, bool) or not isinstance(count, int) or count < 0
            ):
                raise DomainError(
                    "Routing resource counts must be nonnegative integers or unknown."
                )
        if self.remaining_currency is not None:
            require_amount(self.remaining_currency)
        if self.currency is not None:
            require_currency(self.currency)
        validate_data_scope(self.sensitivity, self.categories)


@dataclass(frozen=True, slots=True)
class RoutingPolicy:
    policy_version: str
    permissions: tuple[ProviderPermission, ...] = ()
    max_escalations: int | None = None

    def __post_init__(self) -> None:
        require_text(self.policy_version)
        validate_scope(self.permissions, ProviderPermission)
        if len({item.provider_id for item in self.permissions}) != len(self.permissions):
            raise DomainError("A routing policy must select one current permission per provider.")
        if self.max_escalations is not None and (
            isinstance(self.max_escalations, bool)
            or not isinstance(self.max_escalations, int)
            or self.max_escalations < 0
        ):
            raise DomainError("The escalation limit must be nonnegative or unknown.")
