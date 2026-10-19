"""Transactional PostgreSQL adapter for authenticated dashboard controls; EP-07.02."""

import json
from collections.abc import Callable
from dataclasses import asdict, replace
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from acoa.application.dashboard_controls import (
    DashboardControlCommand,
    DashboardControlResult,
    DashboardLimitValues,
)
from acoa.config import ApplicationLimits, BudgetLimits, OutreachLimits
from acoa.infrastructure.policy_authority import AuthorityStore, PolicyAuthority
from acoa.infrastructure.postgres import DatabaseBoundaryError, validate_application_connection
from acoa.infrastructure.task_queue import TaskQueue

AuthorityChange = Callable[[PolicyAuthority], PolicyAuthority]


def _enter_safe_mode(authority: PolicyAuthority) -> PolicyAuthority:
    settings = replace(authority.settings, dry_run=True, external_actions_enabled=False)
    return replace(authority, settings=settings, paused=True)


def _resume_system(authority: PolicyAuthority) -> PolicyAuthority:
    return replace(authority, paused=False)


def _replace_limits(authority: PolicyAuthority, values: DashboardLimitValues) -> PolicyAuthority:
    settings = replace(
        authority.settings,
        applications=ApplicationLimits(values.applications_per_day, values.applications_per_week),
        outreach=OutreachLimits(values.outreach_per_company, values.outreach_per_contact),
        budget=BudgetLimits(
            currency=values.currency,
            max_currency_per_day=values.currency_per_day,
            max_currency_per_month=values.currency_per_month,
            max_tokens_per_task=values.tokens_per_task,
            max_time_per_task=values.seconds_per_task,
            paid_services_enabled=values.paid_services_enabled,
            progress_stall_timeout=values.progress_stall_timeout,
        ),
    )
    return replace(authority, settings=settings)


class PostgresDashboardController:
    """Own short transactions so state transitions and audit evidence commit together."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    @staticmethod
    def _existing(
        connection: Connection,
        command: DashboardControlCommand,
        action: str,
        task_id: UUID | None,
    ) -> DashboardControlResult | None:
        row = (
            connection.execute(
                text("""SELECT actor_sha256,action,task_id,authority_revision,result
                FROM acoa.dashboard_control_events WHERE request_id=:request"""),
                {"request": command.request_id},
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return None
        if (
            row["actor_sha256"] != command.actor_sha256
            or row["action"] != action
            or row["task_id"] != task_id
        ):
            raise DatabaseBoundaryError("A control request identifier is already in use.")
        result = cast(dict[str, object], row["result"])
        return DashboardControlResult(
            action=cast(str, row["action"]),
            state=cast(str, result["state"]),
            task_id=cast(UUID | None, row["task_id"]),
            authority_revision=cast(int | None, row["authority_revision"]),
        )

    @staticmethod
    def _record(
        connection: Connection,
        command: DashboardControlCommand,
        event_id: UUID,
        result: DashboardControlResult,
    ) -> None:
        connection.execute(
            text("""INSERT INTO acoa.dashboard_control_events
                (event_id,request_id,actor_sha256,action,task_id,authority_revision,result)
                VALUES (:event,:request,:actor,:action,:task,:revision,CAST(:result AS jsonb))"""),
            {
                "event": event_id,
                "request": command.request_id,
                "actor": command.actor_sha256,
                "action": result.action,
                "task": result.task_id,
                "revision": result.authority_revision,
                "result": json.dumps(asdict(result), default=str, sort_keys=True),
            },
        )

    def _authority_change(
        self,
        command: DashboardControlCommand,
        action: str,
        change: AuthorityChange,
    ) -> DashboardControlResult:
        with self.engine.begin() as connection:
            validate_application_connection(connection)
            existing = self._existing(connection, command, action, None)
            if existing is not None:
                return existing
            event_id = uuid4()
            store = AuthorityStore(connection)
            revision, current = store.lock_current()
            updated = change(current)
            new_revision = store.replace(revision, updated, event_id)
            result = DashboardControlResult(action, "applied", authority_revision=new_revision)
            self._record(connection, command, event_id, result)
            return result

    def enter_safe_mode(self, command: DashboardControlCommand) -> DashboardControlResult:
        return self._authority_change(command, "enter_safe_mode", _enter_safe_mode)

    def resume_system(self, command: DashboardControlCommand) -> DashboardControlResult:
        return self._authority_change(command, "resume_system", _resume_system)

    def replace_limits(
        self, command: DashboardControlCommand, values: DashboardLimitValues
    ) -> DashboardControlResult:
        return self._authority_change(
            command,
            "replace_limits",
            lambda authority: _replace_limits(authority, values),
        )

    def _task_change(
        self,
        command: DashboardControlCommand,
        task_id: UUID,
        action: str,
    ) -> DashboardControlResult:
        with self.engine.begin() as connection:
            validate_application_connection(connection)
            existing = self._existing(connection, command, action, task_id)
            if existing is not None:
                return existing
            event_id = uuid4()
            queue = TaskQueue(connection)
            if action == "pause_task":
                task = queue.pause(task_id, event_id)
            elif action == "resume_task":
                task = queue.resume_paused(task_id, event_id)
            elif action == "cancel_task":
                task = queue.cancel(task_id, event_id)
            else:
                raise ValueError("Unsupported dashboard task control.")
            result = DashboardControlResult(action, task.state.value, task_id=task_id)
            self._record(connection, command, event_id, result)
            return result

    def pause_task(self, command: DashboardControlCommand, task_id: UUID) -> DashboardControlResult:
        return self._task_change(command, task_id, "pause_task")

    def resume_task(
        self, command: DashboardControlCommand, task_id: UUID
    ) -> DashboardControlResult:
        return self._task_change(command, task_id, "resume_task")

    def cancel_task(
        self, command: DashboardControlCommand, task_id: UUID
    ) -> DashboardControlResult:
        return self._task_change(command, task_id, "cancel_task")
