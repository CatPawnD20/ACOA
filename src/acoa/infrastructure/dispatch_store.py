"""Committed PostgreSQL dispatch boundary for the application executor."""

from uuid import UUID

from sqlalchemy.engine import Engine

from acoa.application.executor import DispatchTicket
from acoa.domain.actions import ActionState
from acoa.infrastructure.action_protocol import ActionProtocol
from acoa.infrastructure.postgres import DatabaseBoundaryError


class PostgresDispatchStore:
    """Complete each transaction before handing control to provider orchestration."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def begin_execution(self, attempt_id: UUID, providers: frozenset[UUID]) -> DispatchTicket:
        with self.engine.begin() as connection:
            protocol = ActionProtocol(connection)
            prepared = protocol.read_prepared(attempt_id)
            if prepared.provider_id not in providers:
                raise DatabaseBoundaryError("The provider has no registered trusted adapter.")
            result = protocol.begin_execution(attempt_id)
        return DispatchTicket(prepared, result)

    def record_response(
        self, attempt_id: UUID, token: UUID, receipt_ref: UUID | None
    ) -> ActionState:
        with self.engine.begin() as connection:
            return ActionProtocol(connection).record_response(attempt_id, token, receipt_ref)
