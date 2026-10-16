"""EP-02.01 transaction-scoped PostgreSQL queue; E-03/E-05, ADR-002/003/013."""

from collections.abc import Mapping
from datetime import datetime
from typing import cast
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping, ScalarResult

from acoa.domain.tasks import (
    RetryMode,
    RetryPolicy,
    TaskErrorClass,
    TaskKind,
    TaskOutcome,
    TaskSnapshot,
    TaskSpec,
    TaskState,
    failure_outcome,
)
from acoa.domain.values import DomainError, require_identifier, require_version
from acoa.infrastructure.postgres import DatabaseBoundaryError as QueueError
from acoa.infrastructure.postgres import require_transaction as require_transaction
from acoa.infrastructure.postgres import (
    validate_application_connection as validate_queue_connection,
)


class LeaseLost(QueueError):
    """The worker no longer owns a current fenced lease."""


def snapshot_from_row(row: RowMapping, dependencies: tuple[UUID, ...] = ()) -> TaskSnapshot:
    """Decode constraint-checked database values into immutable domain snapshots."""
    spec = TaskSpec(
        cast(UUID, row["task_id"]),
        TaskKind(row["kind"]),
        cast(UUID, row["input_ref"]),
        RetryPolicy(
            RetryMode(row["retry_mode"]),
            cast(int, row["max_attempts"]),
            cast(int, row["base_delay_seconds"]),
            cast(int, row["max_delay_seconds"]),
        ),
        dependencies,
    )
    return TaskSnapshot(
        spec,
        TaskState(row["state"]),
        cast(int, row["attempt_count"]),
        cast(int, row["phase_attempt_count"]),
        cast(datetime, row["next_run_at"]),
        cast(UUID | None, row["lease_owner"]),
        cast(UUID | None, row["lease_token"]),
        cast(datetime | None, row["lease_until"]),
        cast(UUID | None, row["waiting_question_id"]),
        TaskErrorClass(row["last_error_class"]) if row["last_error_class"] else None,
    )


class TaskQueue:
    """No connection discovery, provider calls, credentials or transaction ownership."""

    def __init__(self, connection: Connection) -> None:
        validate_queue_connection(connection)
        self.connection = connection

    def _execute(
        self, statement: str, parameters: Mapping[str, object] | None = None
    ) -> RowMapping | None:
        require_transaction(self.connection)
        return self.connection.execute(text(statement), parameters or {}).mappings().one_or_none()

    def _dependencies(self, task_id: UUID) -> tuple[UUID, ...]:
        require_transaction(self.connection)
        rows: ScalarResult[UUID] = self.connection.execute(
            text("SELECT dependency_id FROM acoa.task_dependencies WHERE task_id = :id"),
            {"id": task_id},
        ).scalars()
        return tuple(rows)

    def _snapshot(self, row: RowMapping) -> TaskSnapshot:
        return snapshot_from_row(row, self._dependencies(cast(UUID, row["task_id"])))

    def _event(
        self,
        task: TaskSnapshot,
        previous: TaskState | None,
        evidence_id: UUID | None = None,
    ) -> None:
        require_transaction(self.connection)
        self.connection.execute(
            text("""
                INSERT INTO acoa.task_events
                    (event_id, task_id, previous_state, new_state, error_class, evidence_id)
                VALUES (:event, :task, :previous, :state, :error, :evidence)
            """),
            {
                "event": uuid4(),
                "task": task.spec.task_id,
                "previous": previous.value if previous else None,
                "state": task.state.value,
                "error": task.last_error_class.value if task.last_error_class else None,
                "evidence": evidence_id,
            },
        )

    def get(self, task_id: UUID) -> TaskSnapshot | None:
        require_identifier(task_id)
        row = self._execute("SELECT * FROM acoa.task_runs WHERE task_id = :id", {"id": task_id})
        return self._snapshot(row) if row is not None else None

    def enqueue(self, spec: TaskSpec) -> TaskSnapshot:
        """Insert immutable task identity/dependencies; repeated exact enqueue is idempotent."""
        if not isinstance(spec, TaskSpec):
            raise DomainError("Queue insertion requires a validated task specification.")
        row = self._execute(
            """
            INSERT INTO acoa.task_runs
                (task_id, kind, input_ref, retry_mode, max_attempts,
                 base_delay_seconds, max_delay_seconds)
            VALUES (:id, :kind, :input, :retry, :attempts, :base, :maximum)
            ON CONFLICT (task_id) DO NOTHING RETURNING *
            """,
            {
                "id": spec.task_id,
                "kind": spec.kind.value,
                "input": spec.input_ref,
                "retry": spec.retry.mode.value,
                "attempts": spec.retry.max_attempts,
                "base": spec.retry.base_delay_seconds,
                "maximum": spec.retry.max_delay_seconds,
            },
        )
        if row is None:
            existing = self.get(spec.task_id)
            if existing is None or (
                existing.spec.kind != spec.kind
                or existing.spec.input_ref != spec.input_ref
                or existing.spec.retry != spec.retry
                or set(existing.spec.dependencies) != set(spec.dependencies)
            ):
                raise QueueError("An existing task ID must retain its original specification.")
            return existing
        for dependency in spec.dependencies:
            self.connection.execute(
                text("INSERT INTO acoa.task_dependencies VALUES (:task, :dependency)"),
                {"task": spec.task_id, "dependency": dependency},
            )
        task = self._snapshot(row)
        self._event(task, None)
        return task

    def claim(self, owner: UUID, lease_seconds: int) -> TaskSnapshot | None:
        """Atomically claim one due task whose dependencies have completed."""
        require_identifier(owner)
        require_version(lease_seconds)
        row = self._execute(
            """
            WITH candidate AS (
                SELECT t.task_id, t.state FROM acoa.task_runs t
                WHERE t.state IN ('queued', 'retry_scheduled')
                  AND (SELECT payload->>'paused' = 'false'
                       FROM acoa.policy_authority WHERE singleton)
                  AND t.next_run_at <= clock_timestamp() AND t.phase_attempt_count < t.max_attempts
                  AND NOT EXISTS (
                      SELECT 1 FROM acoa.task_dependencies d JOIN acoa.task_runs p
                      ON p.task_id = d.dependency_id
                      WHERE d.task_id = t.task_id AND p.state <> 'completed')
                ORDER BY t.next_run_at, t.created_at, t.task_id
                FOR UPDATE OF t SKIP LOCKED LIMIT 1
            )
            UPDATE acoa.task_runs t SET state = 'leased', lease_owner = :owner,
                lease_token = :token,
                lease_until = clock_timestamp() + :seconds * interval '1 second',
                attempt_count = attempt_count + 1, phase_attempt_count = phase_attempt_count + 1,
                updated_at = clock_timestamp()
            FROM candidate c WHERE t.task_id = c.task_id RETURNING t.*, c.state AS previous_state
            """,
            {"owner": owner, "token": uuid4(), "seconds": lease_seconds},
        )
        if row is None:
            return None
        task = self._snapshot(row)
        previous = TaskState(row["previous_state"])
        self._event(task, previous)
        return task

    def _owned(self, task_id: UUID, owner: UUID, token: UUID) -> TaskSnapshot:
        for identifier in (task_id, owner, token):
            require_identifier(identifier)
        row = self._execute(
            """SELECT * FROM acoa.task_runs WHERE task_id = :id
               AND lease_owner = :owner AND lease_token = :token
               AND state IN ('leased', 'running') AND lease_until > clock_timestamp()
               FOR UPDATE""",
            {"id": task_id, "owner": owner, "token": token},
        )
        if row is None:
            raise LeaseLost("The task lease is missing, expired or owned by another worker.")
        return self._snapshot(row)

    def start(self, task_id: UUID, owner: UUID, token: UUID) -> TaskSnapshot:
        task = self._owned(task_id, owner, token)
        row = self._execute(
            """UPDATE acoa.task_runs SET state = 'running', updated_at = clock_timestamp()
               WHERE task_id = :id AND lease_until > clock_timestamp() RETURNING *""",
            {"id": task_id},
        )
        if row is None:
            raise LeaseLost("The lease expired before task start.")
        updated = self._snapshot(row)
        if task.state is not TaskState.RUNNING:
            self._event(updated, task.state)
        return updated

    def heartbeat(
        self, task_id: UUID, owner: UUID, token: UUID, lease_seconds: int
    ) -> TaskSnapshot:
        require_version(lease_seconds)
        self._owned(task_id, owner, token)
        row = self._execute(
            """UPDATE acoa.task_runs SET
               lease_until = GREATEST(lease_until,
                   clock_timestamp() + :seconds * interval '1 second'),
               updated_at = clock_timestamp()
               WHERE task_id = :id AND lease_until > clock_timestamp() RETURNING *""",
            {"id": task_id, "seconds": lease_seconds},
        )
        if row is None:
            raise LeaseLost("The lease expired before heartbeat.")
        return self._snapshot(row)

    def _apply_outcome(self, task: TaskSnapshot, outcome: TaskOutcome) -> TaskSnapshot:
        row = self._execute(
            """UPDATE acoa.task_runs SET state = :state, last_error_class = :error,
               waiting_question_id = :question, next_run_at = COALESCE(:next, next_run_at),
               lease_owner = NULL, lease_token = NULL, lease_until = NULL,
               updated_at = clock_timestamp() WHERE task_id = :id AND lease_token = :token
               AND CASE WHEN :expired THEN lease_until <= clock_timestamp()
                   ELSE lease_until > clock_timestamp() END RETURNING *""",
            {
                "id": task.spec.task_id,
                "state": outcome.state.value,
                "error": outcome.error_class.value if outcome.error_class else None,
                "question": outcome.question_id,
                "next": outcome.next_run_at,
                "token": task.lease_token,
                "expired": outcome.error_class is TaskErrorClass.LEASE_EXPIRED,
            },
        )
        if row is None:
            raise LeaseLost("The lease no longer permits this task transition.")
        updated = self._snapshot(row)
        self._event(updated, task.state)
        return updated

    def complete(self, task_id: UUID, owner: UUID, token: UUID) -> TaskSnapshot:
        task = self._owned(task_id, owner, token)
        return self._apply_outcome(task, TaskOutcome(TaskState.COMPLETED))

    def wait_for_user(
        self, task_id: UUID, owner: UUID, token: UUID, question_id: UUID
    ) -> TaskSnapshot:
        outcome = TaskOutcome(TaskState.WAITING_USER, question_id=question_id)
        task = self._owned(task_id, owner, token)
        return self._apply_outcome(task, outcome)

    def fail(self, task_id: UUID, owner: UUID, token: UUID, error: TaskErrorClass) -> TaskSnapshot:
        task = self._owned(task_id, owner, token)
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        return self._apply_outcome(task, failure_outcome(task, error, now))

    def resume(self, task_id: UUID, question_id: UUID, answer_evidence_id: UUID) -> TaskSnapshot:
        """Trusted user-answer adapter only; evidence UUID itself does not prove approval."""
        for identifier in (task_id, question_id, answer_evidence_id):
            require_identifier(identifier)
        row = self._execute(
            """UPDATE acoa.task_runs SET state = 'queued', waiting_question_id = NULL,
               next_run_at = clock_timestamp(), phase_attempt_count = 0,
               updated_at = clock_timestamp()
               WHERE task_id = :id AND state = 'waiting_user' AND waiting_question_id = :question
               RETURNING *""",
            {"id": task_id, "question": question_id},
        )
        if row is None:
            raise QueueError("No waiting task matches the answered question.")
        task = self._snapshot(row)
        self._event(task, TaskState.WAITING_USER, answer_evidence_id)
        return task

    def pause(self, task_id: UUID, evidence_id: UUID) -> TaskSnapshot:
        """Pause only work that has not started; an active lease must be resolved separately."""
        for identifier in (task_id, evidence_id):
            require_identifier(identifier)
        row = self._execute(
            "SELECT * FROM acoa.task_runs WHERE task_id = :id FOR UPDATE", {"id": task_id}
        )
        if row is None:
            raise QueueError("The task to pause is missing.")
        task = self._snapshot(row)
        if task.state is TaskState.PAUSED:
            return task
        if task.state not in (TaskState.QUEUED, TaskState.RETRY_SCHEDULED):
            raise QueueError("Only queued work can be paused without racing an active worker.")
        updated_row = self._execute(
            """UPDATE acoa.task_runs SET state = 'paused', updated_at = clock_timestamp()
               WHERE task_id = :id RETURNING *""",
            {"id": task_id},
        )
        if updated_row is None:
            raise QueueError("The locked task is missing.")
        updated = self._snapshot(updated_row)
        self._event(updated, task.state, evidence_id)
        return updated

    def resume_paused(self, task_id: UUID, evidence_id: UUID) -> TaskSnapshot:
        """Return an explicitly paused task to the queue without fabricating user answers."""
        for identifier in (task_id, evidence_id):
            require_identifier(identifier)
        row = self._execute(
            """UPDATE acoa.task_runs SET state = 'queued', next_run_at = clock_timestamp(),
               phase_attempt_count = 0, updated_at = clock_timestamp()
               WHERE task_id = :id AND state = 'paused' RETURNING *""",
            {"id": task_id},
        )
        if row is None:
            raise QueueError("Only an explicitly paused task can be resumed from the dashboard.")
        task = self._snapshot(row)
        self._event(task, TaskState.PAUSED, evidence_id)
        return task

    def cancel(self, task_id: UUID, evidence_id: UUID | None = None) -> TaskSnapshot:
        """Cancel unfinished work and fence its worker; no external action is undone."""
        require_identifier(task_id)
        if evidence_id is not None:
            require_identifier(evidence_id)
        row = self._execute(
            "SELECT * FROM acoa.task_runs WHERE task_id = :id FOR UPDATE", {"id": task_id}
        )
        if row is None:
            raise QueueError("The task to cancel is missing.")
        task = self._snapshot(row)
        if task.state is TaskState.CANCELLED:
            return task
        if task.state in (TaskState.COMPLETED, TaskState.FAILED):
            raise QueueError("Finished task history cannot be cancelled.")
        updated_row = self._execute(
            """UPDATE acoa.task_runs SET state = 'cancelled', waiting_question_id = NULL,
               lease_owner = NULL, lease_token = NULL, lease_until = NULL,
               updated_at = clock_timestamp() WHERE task_id = :id RETURNING *""",
            {"id": task_id},
        )
        if updated_row is None:
            raise QueueError("The locked task is missing.")
        updated = self._snapshot(updated_row)
        self._event(updated, task.state, evidence_id)
        return updated

    def reclaim(self, limit: int) -> tuple[TaskSnapshot, ...]:
        """Fence expired workers; unsafe work blocks for reconciliation instead of retrying."""
        require_version(limit)
        require_transaction(self.connection)
        rows = (
            self.connection.execute(
                text("""SELECT * FROM acoa.task_runs WHERE state IN ('leased', 'running')
                 AND lease_until <= clock_timestamp() ORDER BY lease_until, task_id
                 FOR UPDATE SKIP LOCKED LIMIT :limit"""),
                {"limit": limit},
            )
            .mappings()
            .all()
        )
        now = cast(datetime, self.connection.execute(text("SELECT clock_timestamp()")).scalar_one())
        tasks = tuple(self._snapshot(row) for row in rows)
        return tuple(
            self._apply_outcome(task, failure_outcome(task, TaskErrorClass.LEASE_EXPIRED, now))
            for task in tasks
        )
