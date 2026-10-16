"""PostgreSQL career-account plan and result records without secret values; EP-08.03."""

import json
from datetime import datetime
from typing import cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from acoa.domain.authorization import DataCategory
from acoa.domain.career_accounts import (
    CareerAccountEvent,
    CareerAccountObstacle,
    CareerAccountPlan,
    CareerAccountProviderResult,
    CareerAccountResultKind,
)
from acoa.domain.values import require_identifier
from acoa.infrastructure.postgres import (
    DatabaseBoundaryError,
    require_transaction,
    validate_application_connection,
)


class PostgresCareerAccountStore:
    """Append plans/events; the referenced secret lives only in an external secret store."""

    def __init__(self, connection: Connection) -> None:
        validate_application_connection(connection)
        self.connection = connection

    def add_plan(self, plan: CareerAccountPlan) -> None:
        if not isinstance(plan, CareerAccountPlan):
            raise DatabaseBoundaryError("A validated career-account plan is required.")
        require_transaction(self.connection)
        self.connection.execute(
            text("""INSERT INTO acoa.career_account_plans
                (plan_id,account_id,task_id,application_id,provider_id,browser_permit_id,
                 allowed_origin,login_sha256,terms_sha256,data_categories,created_at,expires_at)
                VALUES (:plan,:account,:task,:application,:provider,:permit,:origin,:login,
                        :terms,CAST(:categories AS jsonb),:created,:expires)
                ON CONFLICT (plan_id) DO NOTHING"""),
            {
                "plan": plan.plan_id,
                "account": plan.account_id,
                "task": plan.task_id,
                "application": plan.application_id,
                "provider": plan.provider_id,
                "permit": plan.browser_permit_id,
                "origin": plan.allowed_origin,
                "login": plan.login_sha256,
                "terms": plan.terms_sha256,
                "categories": json.dumps([item.value for item in plan.data_categories]),
                "created": plan.created_at,
                "expires": plan.expires_at,
            },
        )
        if self.read_plan(plan.plan_id) != plan:
            raise DatabaseBoundaryError("A career-account plan identity cannot change.")

    def read_plan(self, plan_id: UUID) -> CareerAccountPlan:
        require_identifier(plan_id)
        require_transaction(self.connection)
        row = (
            self.connection.execute(
                text("SELECT * FROM acoa.career_account_plans WHERE plan_id=:plan"),
                {"plan": plan_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatabaseBoundaryError("The career-account plan is missing.")
        return self._plan_from_row(row)

    def append(self, event: CareerAccountEvent) -> None:
        if not isinstance(event, CareerAccountEvent):
            raise DatabaseBoundaryError("A validated career-account event is required.")
        require_transaction(self.connection)
        self.connection.execute(
            text("""INSERT INTO acoa.career_account_events
                (event_id,plan_id,attempt_id,secret_ref_id,result_kind,obstacles,
                 provider_account_sha256,observed_at)
                VALUES (:event,:plan,:attempt,:secret,:kind,CAST(:obstacles AS jsonb),
                        :provider_account,:observed)
                ON CONFLICT (event_id) DO NOTHING"""),
            {
                "event": event.event_id,
                "plan": event.plan_id,
                "attempt": event.attempt_id,
                "secret": event.secret_ref_id,
                "kind": event.result.kind.value,
                "obstacles": json.dumps([item.value for item in event.result.obstacles]),
                "provider_account": event.result.provider_account_sha256,
                "observed": event.observed_at,
            },
        )
        if self.read_event(event.event_id) != event:
            raise DatabaseBoundaryError("A career-account event identity cannot change.")

    def read_event(self, event_id: UUID) -> CareerAccountEvent:
        require_identifier(event_id)
        require_transaction(self.connection)
        row = (
            self.connection.execute(
                text("SELECT * FROM acoa.career_account_events WHERE event_id=:event"),
                {"event": event_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise DatabaseBoundaryError("The career-account event is missing.")
        return self._event_from_row(row)

    @staticmethod
    def _plan_from_row(row: RowMapping) -> CareerAccountPlan:
        categories = row["data_categories"]
        if not isinstance(categories, list):
            raise DatabaseBoundaryError("Career-account data categories are malformed.")
        return CareerAccountPlan(
            cast(UUID, row["plan_id"]),
            cast(UUID, row["account_id"]),
            cast(UUID, row["task_id"]),
            cast(UUID, row["application_id"]),
            cast(UUID, row["provider_id"]),
            cast(UUID, row["browser_permit_id"]),
            cast(str, row["allowed_origin"]),
            cast(str, row["login_sha256"]),
            cast(str, row["terms_sha256"]),
            tuple(DataCategory(cast(str, item)) for item in categories),
            cast(datetime, row["created_at"]),
            cast(datetime, row["expires_at"]),
        )

    @staticmethod
    def _event_from_row(row: RowMapping) -> CareerAccountEvent:
        obstacles = row["obstacles"]
        if not isinstance(obstacles, list):
            raise DatabaseBoundaryError("Career-account obstacles are malformed.")
        result = CareerAccountProviderResult(
            CareerAccountResultKind(cast(str, row["result_kind"])),
            tuple(CareerAccountObstacle(cast(str, item)) for item in obstacles),
            cast(str | None, row["provider_account_sha256"]),
        )
        return CareerAccountEvent(
            cast(UUID, row["event_id"]),
            cast(UUID, row["plan_id"]),
            cast(UUID, row["attempt_id"]),
            cast(UUID, row["secret_ref_id"]),
            result,
            cast(datetime, row["observed_at"]),
        )
