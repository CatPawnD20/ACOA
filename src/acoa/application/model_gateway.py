"""EP-03.01 offline structured gateway; all responses remain untrusted model data."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic_ns
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from acoa.domain.model_calls import (
    ModelCallLimits,
    ModelCallRequest,
    ModelCallState,
    StructuredModelOutput,
    output_matches_request,
)
from acoa.domain.values import DomainError, require_identifier


@dataclass(frozen=True, slots=True)
class ModelCallTicket:
    state: ModelCallState
    execution_token: UUID | None = field(default=None, repr=False)
    limits: ModelCallLimits | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelGatewayResult:
    state: ModelCallState
    output: StructuredModelOutput | None = None
    reason: str | None = None


class OfflineModelProvider(Protocol):
    """Trusted local simulation only: no network, secrets, tools, SDK retries or permissions."""

    def complete(
        self, request: ModelCallRequest, limits: ModelCallLimits
    ) -> StructuredModelOutput: ...


class ModelCallStore(Protocol):
    def begin(self, request: ModelCallRequest) -> ModelCallTicket: ...

    def finish(
        self,
        request: ModelCallRequest,
        token: UUID,
        output: StructuredModelOutput | None,
        elapsed_seconds: Decimal,
    ) -> ModelCallState: ...


def complete_offline(
    provider: OfflineModelProvider, request: ModelCallRequest, limits: ModelCallLimits
) -> StructuredModelOutput | None:
    """Do not infer success, free usage or schema validity from malformed provider output."""
    try:
        if datetime.now(UTC) >= limits.deadline:
            return None
        output = provider.complete(request, limits)
        if not isinstance(output, StructuredModelOutput) or not output_matches_request(
            request, output
        ):
            return None
        return output
    except Exception:
        return None


class ModelGateway:
    """Only trusted composition may register offline providers; no live adapter is included."""

    def __init__(
        self, store: ModelCallStore, providers: Mapping[UUID, OfflineModelProvider]
    ) -> None:
        for identifier in providers:
            require_identifier(identifier)
        self.store = store
        self.providers = MappingProxyType(dict(providers))

    def complete(self, request: ModelCallRequest) -> ModelGatewayResult:
        if not isinstance(request, ModelCallRequest):
            raise DomainError("Gateway calls require a validated structured request.")
        provider = self.providers.get(request.provider_id)
        if provider is None:
            return ModelGatewayResult(ModelCallState.BLOCKED, reason="provider_not_registered")
        ticket = self.store.begin(request)
        if ticket.execution_token is None:
            return ModelGatewayResult(ticket.state, reason=ticket.reason)
        if ticket.limits is None:
            raise DomainError("A started model call requires bounded resource limits.")
        started = monotonic_ns()
        output = complete_offline(provider, request, ticket.limits)
        # Decimal construction preserves nanoseconds regardless of ambient precision.
        elapsed = Decimal(f"{monotonic_ns() - started}e-9")
        state = self.store.finish(request, ticket.execution_token, output, elapsed)
        return ModelGatewayResult(state, output if state is ModelCallState.SUCCEEDED else None)
