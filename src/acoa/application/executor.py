"""EP-02.03 one automatic provider invocation after committed current authorization."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Protocol
from uuid import UUID

from acoa.application.policy import GateDecision, request_binding_sha256
from acoa.domain.actions import ActionState, DispatchLimits, PreparedAction
from acoa.domain.values import DomainError, require_identifier, require_sha256


@dataclass(frozen=True, slots=True)
class ActionCheck:
    state: ActionState
    decision_id: UUID | None = None
    decision: GateDecision | None = None
    execution_token: UUID | None = None
    limits: DispatchLimits | None = None


@dataclass(frozen=True, slots=True)
class DispatchTicket:
    prepared: PreparedAction
    result: ActionCheck


class ExecutionStore(Protocol):
    """Persist dispatch before returning; record outcomes without invoking providers."""

    def begin_execution(self, attempt_id: UUID, providers: frozenset[UUID]) -> DispatchTicket: ...

    def record_response(
        self, attempt_id: UUID, token: UUID, receipt_ref: UUID | None
    ) -> ActionState: ...


@dataclass(frozen=True, slots=True)
class ProviderAcknowledgement:
    """Transport acknowledgement only; verification requires separate read-only evidence."""

    attempt_id: UUID
    request_sha256: str
    receipt_ref: UUID

    def __post_init__(self) -> None:
        require_identifier(self.attempt_id)
        require_identifier(self.receipt_ref)
        require_sha256(self.request_sha256)


class InteractionAdapter(Protocol):
    """Trusted adapters must verify exact material hashes and never retry a submission."""

    def execute_once(
        self, prepared: PreparedAction, limits: DispatchLimits
    ) -> ProviderAcknowledgement | None: ...


def invoke_once(
    adapter: InteractionAdapter, prepared: PreparedAction, limits: DispatchLimits
) -> UUID | None:
    """Treat all provider exceptions, malformed/foreign replies and missing replies as unknown."""
    try:
        if datetime.now(UTC) >= limits.deadline:
            return None
        acknowledgement = adapter.execute_once(prepared, limits)
        if (
            not isinstance(acknowledgement, ProviderAcknowledgement)
            or acknowledgement.attempt_id != prepared.attempt_id
            or acknowledgement.request_sha256 != request_binding_sha256(prepared.request)
        ):
            return None
        return acknowledgement.receipt_ref
    except Exception:
        return None


class ExternalActionExecutor:
    """Only trusted composition code supplies adapters; no real provider is included here."""

    def __init__(self, store: ExecutionStore, providers: Mapping[UUID, InteractionAdapter]) -> None:
        for identifier in providers:
            require_identifier(identifier)
        self.store = store
        self.providers = MappingProxyType(dict(providers))

    def execute_once(self, attempt_id: UUID) -> ActionCheck:
        """Commit the fenced dispatch before provider I/O, then persist its uncertain outcome."""
        ticket = self.store.begin_execution(attempt_id, frozenset(self.providers))
        prepared, result = ticket.prepared, ticket.result
        if result.execution_token is None:
            return result
        if result.limits is None:
            raise DomainError("Committed dispatch must include bounded provider resource limits.")
        receipt_ref = invoke_once(self.providers[prepared.provider_id], prepared, result.limits)
        state = self.store.record_response(attempt_id, result.execution_token, receipt_ref)
        return ActionCheck(state, result.decision_id, result.decision)
