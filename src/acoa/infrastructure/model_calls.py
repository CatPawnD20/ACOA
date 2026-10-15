"""PostgreSQL offline model-call accounting using shared monetary reservations."""

from collections.abc import Sequence
from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from hashlib import sha256
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine, RowMapping

from acoa.application.model_gateway import ModelCallTicket
from acoa.application.policy import check_budget
from acoa.application.policy_inputs import PolicyContext
from acoa.domain.budgets import LimitCheck, check_decimal_limit
from acoa.domain.model_calls import (
    ModelCallLimits,
    ModelCallRequest,
    ModelCallState,
    StructuredModelOutput,
    model_request_sha256,
    output_exceeds_limits,
    output_matches_request,
    require_amount,
)
from acoa.domain.values import require_version
from acoa.infrastructure.action_usage import budget_usage
from acoa.infrastructure.model_permissions import ModelPermissionStore
from acoa.infrastructure.policy_authority import AuthorityStore, PolicyAuthority
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection
from acoa.infrastructure.resource_budget import register_resource_attempt


def model_trace_metadata(request: ModelCallRequest, revision: int) -> dict[str, object]:
    """Explicit trace allowlist: new request fields must not automatically disclose private data."""
    return {
        "call_id": request.call_id,
        "task_id": request.task_id,
        "provider_id": request.provider_id,
        "model_alias": request.model_alias,
        "prompt_version": request.prompt_version,
        "output_schema_version": request.output_schema_version,
        "input_token_limit": request.input_token_limit,
        "output_token_limit": request.output_token_limit,
        "timeout_seconds": request.timeout_seconds,
        "max_cost": request.max_cost,
        "currency": request.currency,
        "simulation": True,
        "routing_policy_version": request.routing_policy_version,
        "data_sensitivity": request.data_sensitivity.value,
        "data_categories": [item.value for item in request.data_categories],
        "route_id": request.route_id,
        "context_valid_until": request.context_valid_until,
        "authority_revision": revision,
    }


class ModelCallRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def _event(self, call_id: UUID, kind: str) -> None:
        self.connection.execute(
            text("""INSERT INTO acoa.model_call_events(event_id,call_id,kind)
            VALUES (:event,:call,:kind)"""),
            {"event": uuid4(), "call": call_id, "kind": kind},
        )

    def _task_capacity(
        self,
        request: ModelCallRequest,
        authority: PolicyAuthority,
        now: datetime,
    ) -> tuple[str | None, datetime | None]:
        task = self.connection.execute(
            text("""SELECT lease_until FROM acoa.task_runs
            WHERE task_id=:task AND state='running' AND lease_owner=:owner AND lease_token=:token
                AND lease_until>clock_timestamp() FOR UPDATE"""),
            {"task": request.task_id, "owner": request.lease_owner, "token": request.lease_token},
        ).one_or_none()
        if task is None:
            return "task_lease_not_current", None
        usage = self.connection.execute(
            text("""SELECT
            COALESCE(sum(COALESCE(consumed_tokens,reserved_tokens)),0) AS tokens,
            COALESCE(sum(COALESCE(consumed_seconds,reserved_seconds)),0) AS seconds
            FROM acoa.model_calls WHERE task_id=:task"""),
            {"task": request.task_id},
        ).one()
        caps = authority.settings.budget
        if caps.max_tokens_per_task is None or caps.max_time_per_task is None:
            return "task_budget_unknown", None
        if (
            int(usage.tokens) + request.input_token_limit + request.output_token_limit
            > caps.max_tokens_per_task
        ):
            return "task_token_budget_exceeded", None
        time_check = check_decimal_limit(
            usage.seconds, Decimal(request.timeout_seconds), Decimal(caps.max_time_per_task)
        )
        if time_check is not LimitCheck.WITHIN:
            return "task_time_budget_exceeded", None
        deadline = min(
            cast(datetime, task.lease_until), now + timedelta(seconds=request.timeout_seconds)
        )
        return None, deadline

    def _money_capacity(
        self,
        request: ModelCallRequest,
        authority: PolicyAuthority,
        now: datetime,
    ) -> str | None:
        usage = budget_usage(
            self.connection,
            authority,
            request.call_id,
            {
                "currency": request.currency,
                "quoted_cost": request.max_cost,
                "estimated_tokens": request.input_token_limit + request.output_token_limit,
                "estimated_seconds": request.timeout_seconds,
            },
            now,
        )
        reason = check_budget(PolicyContext(now, now, settings=authority.settings, budget=usage))
        return reason.value if reason is not None else None

    def begin(self, request: ModelCallRequest) -> ModelCallTicket:
        if not isinstance(request, ModelCallRequest):
            raise DatabaseBoundaryError("Model accounting requires a validated offline request.")
        revision, authority = AuthorityStore(self.connection).lock_current()
        prior = self.connection.execute(
            text("SELECT request_sha256,state FROM acoa.model_calls WHERE call_id=:id FOR UPDATE"),
            {"id": request.call_id},
        ).one_or_none()
        if prior is not None:
            if prior.request_sha256 != model_request_sha256(request):
                raise DatabaseBoundaryError("A model call ID must retain its exact request.")
            return ModelCallTicket(ModelCallState(prior.state), reason="call_already_started")
        if authority.paused:
            return ModelCallTicket(ModelCallState.BLOCKED, reason="user_paused")
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        if request.context_valid_until is not None and now >= request.context_valid_until:
            return ModelCallTicket(ModelCallState.BLOCKED, reason="model_context_stale")
        scope = ModelPermissionStore(self.connection).current(request.provider_id)
        if scope is None or not scope[1].covers(
            request.data_sensitivity, request.data_categories, now
        ):
            return ModelCallTicket(
                ModelCallState.BLOCKED, reason="provider_data_scope_not_authorized"
            )
        if (
            request.routing_policy_version is not None
            and request.routing_policy_version != scope[1].policy_version
        ):
            return ModelCallTicket(ModelCallState.BLOCKED, reason="routing_policy_version_changed")
        reason, deadline = self._task_capacity(request, authority, now)
        if reason is None:
            reason = self._money_capacity(request, authority, now)
        if reason is not None or deadline is None:
            return ModelCallTicket(ModelCallState.BLOCKED, reason=reason)
        deadline = min(deadline, scope[1].expires_at)
        token = uuid4()
        limits = ModelCallLimits(
            deadline,
            request.input_token_limit,
            request.output_token_limit,
            request.max_cost,
            request.currency,
        )
        self._record_start(request, token, limits, revision, scope[0], scope[1].policy_version)
        return ModelCallTicket(ModelCallState.RUNNING, token, limits)

    def _record_start(
        self,
        request: ModelCallRequest,
        token: UUID,
        limits: ModelCallLimits,
        revision: int,
        provider_revision: int,
        provider_policy_version: str,
    ) -> None:
        metadata = model_trace_metadata(request, revision)
        metadata["provider_permission_revision"] = provider_revision
        metadata["provider_policy_version"] = provider_policy_version
        self.connection.execute(
            text("""INSERT INTO acoa.model_calls
            (call_id,task_id,request_sha256,metadata,state,execution_token,
             reserved_tokens,reserved_seconds,deadline)
            VALUES (:id,:task,:hash,CAST(:metadata AS jsonb),
                'running',:token,:tokens,:seconds,:deadline)
        """),
            {
                "id": request.call_id,
                "task": request.task_id,
                "hash": model_request_sha256(request),
                "metadata": encode_record(metadata),
                "token": token,
                "tokens": limits.input_tokens + limits.output_tokens,
                "seconds": request.timeout_seconds,
                "deadline": limits.deadline,
            },
        )
        register_resource_attempt(self.connection, request.call_id, "model")
        self.connection.execute(
            text("""INSERT INTO acoa.budget_ledger
            (attempt_id,currency,estimated,reserved) VALUES (:id,:currency,:cost,:cost)"""),
            {"id": request.call_id, "currency": request.currency, "cost": request.max_cost},
        )
        self._event(request.call_id, "started")

    def _lock_call(self, request: ModelCallRequest, token: UUID) -> RowMapping:
        AuthorityStore(self.connection).lock_current()
        row = (
            self.connection.execute(
                text(
                    "SELECT * FROM acoa.model_calls "
                    "WHERE call_id=:id AND execution_token=:token FOR UPDATE"
                ),
                {"id": request.call_id, "token": token},
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["request_sha256"] != model_request_sha256(request):
            raise DatabaseBoundaryError("Model result does not match the started request/fence.")
        return row

    def finish(
        self,
        request: ModelCallRequest,
        token: UUID,
        output: StructuredModelOutput | None,
        elapsed_seconds: Decimal,
    ) -> ModelCallState:
        require_amount(elapsed_seconds)
        row = self._lock_call(request, token)
        state = ModelCallState(row["state"])
        if state not in (ModelCallState.RUNNING, ModelCallState.UNKNOWN):
            return state
        if not isinstance(output, StructuredModelOutput) or not output_matches_request(
            request, output
        ):
            if state is ModelCallState.RUNNING:
                self._mark_unknown(request.call_id)
            return ModelCallState.UNKNOWN
        now: datetime = self.connection.execute(text("SELECT clock_timestamp()")).scalar_one()
        exceeded = (
            state is ModelCallState.UNKNOWN
            or now >= row["deadline"]
            or output_exceeds_limits(request, output, elapsed_seconds)
        )
        if exceeded:
            self._record_violation(request.call_id)
        return self._record_output(request, output, elapsed_seconds, exceeded)

    def _mark_unknown(self, call_id: UUID) -> None:
        self.connection.execute(
            text("""UPDATE acoa.model_calls SET state='unknown',
            completed_at=clock_timestamp() WHERE call_id=:id"""),
            {"id": call_id},
        )
        self._event(call_id, "unknown")

    def _record_violation(self, call_id: UUID) -> None:
        store = AuthorityStore(self.connection)
        revision, authority = store.lock_current()
        if not authority.paused:
            store.replace(revision, replace(authority, paused=True), call_id)
        self._event(call_id, "limit_violation")

    def _record_output(
        self,
        request: ModelCallRequest,
        output: StructuredModelOutput,
        elapsed: Decimal,
        exceeded: bool,
    ) -> ModelCallState:
        target = ModelCallState.FAILED if exceeded else ModelCallState.SUCCEEDED
        usage = {
            "actual_input_tokens": output.input_tokens,
            "actual_output_tokens": output.output_tokens,
        }
        self.connection.execute(
            text("""UPDATE acoa.model_calls SET state=:state,
            consumed_tokens=:tokens,consumed_seconds=:seconds,output_sha256=:hash,
            metadata=metadata || CAST(:usage AS jsonb),
            completed_at=clock_timestamp() WHERE call_id=:id"""),
            {
                "id": request.call_id,
                "state": target.value,
                "tokens": output.input_tokens + output.output_tokens,
                "seconds": elapsed,
                "hash": sha256(output.output_json.encode("utf-8")).hexdigest(),
                "usage": encode_record(usage),
            },
        )
        self.connection.execute(
            text("""UPDATE acoa.budget_ledger SET consumed=:cost,reserved=0,
            released=GREATEST(estimated-:cost,0),settled_at=clock_timestamp()
            WHERE attempt_id=:id"""),
            {"id": request.call_id, "cost": output.actual_cost},
        )
        self._event(request.call_id, "completed")
        return target

    def recover_expired(self, limit: int) -> tuple[UUID, ...]:
        """Do not retry potentially billed calls; retain their monetary/token/time holds."""
        require_version(limit)
        AuthorityStore(self.connection).lock_current()
        ids: Sequence[UUID] = (
            self.connection.execute(
                text("""SELECT call_id FROM acoa.model_calls
            WHERE state='running' AND deadline<=clock_timestamp()
            ORDER BY deadline FOR UPDATE SKIP LOCKED LIMIT :limit"""),
                {"limit": limit},
            )
            .scalars()
            .all()
        )
        for call_id in ids:
            self._mark_unknown(call_id)
        return tuple(ids)


class PostgresModelCallStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def begin(self, request: ModelCallRequest) -> ModelCallTicket:
        with self.engine.begin() as connection:
            return ModelCallRepository(connection).begin(request)

    def finish(
        self,
        request: ModelCallRequest,
        token: UUID,
        output: StructuredModelOutput | None,
        elapsed_seconds: Decimal,
    ) -> ModelCallState:
        with self.engine.begin() as connection:
            return ModelCallRepository(connection).finish(request, token, output, elapsed_seconds)

    def recover_expired(self, limit: int) -> tuple[UUID, ...]:
        with self.engine.begin() as connection:
            return ModelCallRepository(connection).recover_expired(limit)
