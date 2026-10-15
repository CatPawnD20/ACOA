"""Private immutable route/quality audit with current task/pause checks."""

import json
from dataclasses import asdict
from decimal import Decimal
from uuid import UUID, uuid5

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from acoa.application.model_router import RouteDecision, route_decision_json
from acoa.application.model_workflow import ModelRunInput
from acoa.domain.model_quality import QualityReport, quality_passes
from acoa.domain.values import require_identifier, require_sha256, require_text
from acoa.infrastructure.policy_authority import AuthorityStore
from acoa.infrastructure.policy_codec import encode_record
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection


class RoutingAuditRepository:
    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def _task_is_current(self, run: ModelRunInput) -> bool:
        _, authority = AuthorityStore(self.connection).lock_current()
        if authority.paused:
            return False
        exists: bool = self.connection.execute(
            text("""SELECT EXISTS (
            SELECT 1 FROM acoa.task_runs WHERE task_id=:task AND state='running'
                AND lease_owner=:owner AND lease_token=:token
                AND lease_until>clock_timestamp())"""),
            {"task": run.task_id, "owner": run.lease_owner, "token": run.lease_token},
        ).scalar_one()
        return exists

    def route(self, run: ModelRunInput, input_sha256: str, decision: RouteDecision) -> bool:
        require_sha256(input_sha256)
        if not self._task_is_current(run):
            return False
        encoded = route_decision_json(decision)
        prior = self.connection.execute(
            text("SELECT input_sha256,result FROM acoa.model_routes WHERE route_id=:id"),
            {"id": run.route_id},
        ).one_or_none()
        if prior is not None:
            if prior.input_sha256 != input_sha256 or prior.result != json.loads(encoded):
                raise DatabaseBoundaryError("A route ID must retain its exact inputs and decision.")
            return True
        self.connection.execute(
            text("""INSERT INTO acoa.model_routes
            (route_id,task_id,input_sha256,policy_version,result)
            VALUES (:id,:task,:hash,:version,CAST(:result AS jsonb))"""),
            {
                "id": run.route_id,
                "task": run.task_id,
                "hash": input_sha256,
                "version": decision.routing_policy_version,
                "result": encoded,
            },
        )
        return True

    def quality(
        self, call_id: UUID, policy_version: str, report: QualityReport, passed: bool
    ) -> None:
        require_identifier(call_id)
        require_text(policy_version)
        AuthorityStore(self.connection).lock_current()
        check_id = uuid5(
            call_id, f"{policy_version}:{report.evaluator_version}:{report.output_sha256}"
        )
        payload = {**asdict(report), "passed": passed}
        encoded = encode_record(payload)
        prior: object = self.connection.execute(
            text("SELECT result FROM acoa.model_quality_checks WHERE check_id=:id"),
            {"id": check_id},
        ).scalar_one_or_none()
        if prior is not None:
            if prior != json.loads(encoded):
                raise DatabaseBoundaryError("A quality receipt cannot be silently rewritten.")
            return
        source = self.connection.execute(
            text("""SELECT m.output_sha256,m.request_sha256,r.policy_version,
            r.result->>'required_quality' AS required_quality FROM acoa.model_calls m
            JOIN acoa.model_routes r ON r.route_id=(m.metadata->>'route_id')::uuid
            WHERE m.call_id=:id"""),
            {"id": call_id},
        ).one_or_none()
        if source is None or source.required_quality is None:
            raise DatabaseBoundaryError("Quality audit requires the recorded route target.")
        if source.policy_version != policy_version:
            raise DatabaseBoundaryError("The quality report targets another routing policy.")
        if source.output_sha256 != report.output_sha256:
            raise DatabaseBoundaryError("The quality report targets another model response.")
        if source.request_sha256 != report.request_sha256:
            raise DatabaseBoundaryError("The quality report targets another request context.")
        if not isinstance(passed, bool) or passed != quality_passes(
            report, source.output_sha256, source.request_sha256, Decimal(source.required_quality)
        ):
            raise DatabaseBoundaryError(
                "Quality approval conflicts with the recorded target or checks."
            )
        self.connection.execute(
            text("""INSERT INTO acoa.model_quality_checks
            (check_id,call_id,policy_version,result)
            VALUES (:id,:call,:version,CAST(:result AS jsonb))"""),
            {"id": check_id, "call": call_id, "version": policy_version, "result": encoded},
        )


class PostgresRoutingAudit:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def route(self, run: ModelRunInput, input_sha256: str, decision: RouteDecision) -> bool:
        with self.engine.begin() as connection:
            return RoutingAuditRepository(connection).route(run, input_sha256, decision)

    def quality(
        self, call_id: UUID, policy_version: str, report: QualityReport, passed: bool
    ) -> None:
        with self.engine.begin() as connection:
            RoutingAuditRepository(connection).quality(call_id, policy_version, report, passed)
