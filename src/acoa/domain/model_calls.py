"""EP-03.01 structured offline gateway contracts; E-01/E-02, ADR-004/015."""

import json
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from acoa.domain.authorization import DataCategory
from acoa.domain.model_privacy import DataSensitivity, validate_data_scope
from acoa.domain.reviews import content_digest
from acoa.domain.values import (
    DomainError,
    require_identifier,
    require_sha256,
    require_text,
    require_timestamp,
    require_version,
)


class ModelCallState(StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    BLOCKED = "blocked"


def require_amount(value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise DomainError("A resource amount must be a finite nonnegative Decimal.")


def require_currency(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 3
        or any(c not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for c in value)
    ):
        raise DomainError("Model currency must be an explicit uppercase label.")


def reject_nonfinite_json(value: str) -> None:
    raise DomainError("Structured model output must not contain nonfinite numbers.")


def unique_json_fields(pairs: list[tuple[str, object]]) -> dict[str, object]:
    """Do not silently choose between contradictory duplicate output keys."""
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise DomainError("Structured model output must not contain duplicate keys.")
        result[key] = value
    return result


def validate_output_object(payload: str) -> None:
    if not isinstance(payload, str):
        raise DomainError("Structured model output must be a JSON object string.")
    try:
        payload.encode("utf-8")
        value = json.loads(
            payload,
            parse_constant=reject_nonfinite_json,
            parse_float=Decimal,
            object_pairs_hook=unique_json_fields,
        )
    except (ValueError, TypeError, ArithmeticError):
        raise DomainError("Structured model output is invalid.") from None
    if not isinstance(value, dict):
        raise DomainError("Structured model output must be a JSON object.")


@dataclass(frozen=True, slots=True)
class ModelCallRequest:
    """Only offline simulation is supported by this first gateway; no live adapter exists."""

    call_id: UUID
    task_id: UUID
    lease_owner: UUID = field(repr=False)
    lease_token: UUID = field(repr=False)
    provider_id: UUID
    model_alias: str
    prompt_version: str
    output_schema_version: str
    prompt: str = field(repr=False)
    input_token_limit: int
    output_token_limit: int
    timeout_seconds: int
    max_cost: Decimal
    currency: str
    simulation: bool = True
    routing_policy_version: str | None = None
    data_sensitivity: DataSensitivity = DataSensitivity.UNKNOWN
    data_categories: tuple[DataCategory, ...] = ()
    route_id: UUID | None = None

    def __post_init__(self) -> None:
        for identifier in (
            self.call_id,
            self.task_id,
            self.lease_owner,
            self.lease_token,
            self.provider_id,
        ):
            require_identifier(identifier)
        for value in (self.model_alias, self.prompt_version, self.output_schema_version):
            require_text(value)
        if not isinstance(self.prompt, str) or not self.prompt.strip():
            raise DomainError("A model prompt must be explicit nonempty text.")
        for count in (self.input_token_limit, self.output_token_limit, self.timeout_seconds):
            require_version(count)
        require_amount(self.max_cost)
        require_currency(self.currency)
        if self.simulation is not True:
            raise DomainError("Live model integration is not available in the offline gateway.")
        if self.routing_policy_version is not None:
            require_text(self.routing_policy_version)
        validate_data_scope(self.data_sensitivity, self.data_categories)
        if self.route_id is not None:
            require_identifier(self.route_id)


def model_request_sha256(request: ModelCallRequest) -> str:
    payload: dict[str, object] = {
        "call_id": str(request.call_id),
        "task_id": str(request.task_id),
        "lease_owner": str(request.lease_owner),
        "lease_token": str(request.lease_token),
        "provider_id": str(request.provider_id),
        "model_alias": request.model_alias,
        "prompt_version": request.prompt_version,
        "schema": request.output_schema_version,
        "prompt": request.prompt,
        "input_token_limit": request.input_token_limit,
        "output_token_limit": request.output_token_limit,
        "timeout": request.timeout_seconds,
        "max_cost": str(request.max_cost),
        "currency": request.currency,
        "simulation": True,
    }
    if (
        request.routing_policy_version is not None
        or request.data_sensitivity is not DataSensitivity.UNKNOWN
        or request.data_categories
        or request.route_id is not None
    ):
        payload.update(
            {
                "routing_policy_version": request.routing_policy_version,
                "data_sensitivity": request.data_sensitivity.value,
                "data_categories": [item.value for item in request.data_categories],
                "route_id": str(request.route_id) if request.route_id else None,
            }
        )
    return content_digest(payload)


@dataclass(frozen=True, slots=True)
class ModelCallLimits:
    deadline: datetime
    input_tokens: int
    output_tokens: int
    max_cost: Decimal
    currency: str

    def __post_init__(self) -> None:
        require_timestamp(self.deadline)
        require_version(self.input_tokens)
        require_version(self.output_tokens)
        require_amount(self.max_cost)
        require_currency(self.currency)


@dataclass(frozen=True, slots=True)
class StructuredModelOutput:
    call_id: UUID
    provider_id: UUID
    request_sha256: str = field(repr=False)
    model_alias: str
    prompt_version: str
    output_schema_version: str
    output_json: str = field(repr=False)
    input_tokens: int
    output_tokens: int
    actual_cost: Decimal
    currency: str
    simulation: bool = True

    def __post_init__(self) -> None:
        require_identifier(self.call_id)
        require_identifier(self.provider_id)
        require_sha256(self.request_sha256)
        for value in (self.model_alias, self.prompt_version, self.output_schema_version):
            require_text(value)
        validate_output_object(self.output_json)
        for count in (self.input_tokens, self.output_tokens):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DomainError("Actual model tokens must be nonnegative integers.")
        require_amount(self.actual_cost)
        require_currency(self.currency)
        if self.simulation is not True:
            raise DomainError("Offline gateway outputs must be explicitly marked simulated.")


def output_matches_request(request: ModelCallRequest, output: StructuredModelOutput) -> bool:
    return (
        output.call_id == request.call_id
        and output.provider_id == request.provider_id
        and output.request_sha256 == model_request_sha256(request)
        and output.model_alias == request.model_alias
        and output.prompt_version == request.prompt_version
        and output.output_schema_version == request.output_schema_version
        and output.currency == request.currency
        and output.simulation
    )


def output_exceeds_limits(
    request: ModelCallRequest, output: StructuredModelOutput, elapsed_seconds: Decimal
) -> bool:
    """Reported usage must fit both token directions, money and elapsed-time bounds."""
    return (
        output.input_tokens > request.input_token_limit
        or output.output_tokens > request.output_token_limit
        or output.actual_cost > request.max_cost
        or elapsed_seconds > request.timeout_seconds
    )
