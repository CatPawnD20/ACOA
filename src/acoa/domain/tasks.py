"""EP-02.01 durable task values and safe recovery policy; E-03, P-11, ADR-003."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from uuid import UUID

from acoa.domain.authorization import validate_scope
from acoa.domain.values import DomainError, require_identifier, require_timestamp, require_version


class TaskKind(StrEnum):
    DISCOVER_SOURCES = "discover_sources"
    DISCOVER_ORGANIZATIONS = "discover_organizations"
    EXTRACT_OPPORTUNITIES = "extract_opportunities"
    VERIFY_COMPANY = "verify_company"
    EVALUATE_MATCH = "evaluate_match"
    PLAN_APPLICATION = "plan_application"
    COMPOSE_ARTIFACT = "compose_artifact"
    PREPARE_ACTION = "prepare_action"
    EXECUTE_INITIAL_ACTION = "execute_initial_action"
    VERIFY_EXTERNAL_RESULT = "verify_external_result"
    SYNC_INBOX = "sync_inbox"
    DRAFT_REPLY = "draft_reply"
    DRAFT_FOLLOWUP = "draft_followup"
    DAILY_DIGEST = "daily_digest"
    PROFILE_PROPOSAL = "profile_proposal"
    EXPERIMENT_STRATEGY = "experiment_strategy"


class TaskState(StrEnum):
    QUEUED = "queued"
    LEASED = "leased"
    RUNNING = "running"
    COMPLETED = "completed"
    WAITING_USER = "waiting_user"
    RETRY_SCHEDULED = "retry_scheduled"
    PAUSED = "paused"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetryMode(StrEnum):
    NEVER = "never"
    SAFE = "safe"


class TaskErrorClass(StrEnum):
    TRANSIENT = "transient"
    PERMANENT = "permanent"
    AMBIGUOUS_EXTERNAL = "ambiguous_external"
    LEASE_EXPIRED = "lease_expired"


REPLAY_SAFE_KINDS = frozenset(
    (
        TaskKind.DISCOVER_SOURCES,
        TaskKind.DISCOVER_ORGANIZATIONS,
        TaskKind.EXTRACT_OPPORTUNITIES,
        TaskKind.VERIFY_COMPANY,
        TaskKind.EVALUATE_MATCH,
        TaskKind.PLAN_APPLICATION,
        TaskKind.VERIFY_EXTERNAL_RESULT,
        TaskKind.PROFILE_PROPOSAL,
    )
)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    mode: RetryMode = RetryMode.NEVER
    max_attempts: int = 1
    base_delay_seconds: int = 1
    max_delay_seconds: int = 60

    def __post_init__(self) -> None:
        if not isinstance(self.mode, RetryMode):
            raise DomainError("Task retry mode must be explicit.")
        for value in (self.max_attempts, self.base_delay_seconds, self.max_delay_seconds):
            require_version(value)
        if self.max_delay_seconds < self.base_delay_seconds:
            raise DomainError("Maximum retry delay must cover the base delay.")


@dataclass(frozen=True, slots=True)
class TaskSpec:
    task_id: UUID
    kind: TaskKind
    input_ref: UUID
    retry: RetryPolicy = RetryPolicy()
    dependencies: tuple[UUID, ...] = ()

    def __post_init__(self) -> None:
        require_identifier(self.task_id)
        require_identifier(self.input_ref)
        if not isinstance(self.kind, TaskKind) or not isinstance(self.retry, RetryPolicy):
            raise DomainError("Tasks require explicit kind and retry policy values.")
        validate_scope(self.dependencies, UUID)
        if self.task_id in self.dependencies:
            raise DomainError("A task cannot depend on itself.")
        object.__setattr__(
            self, "dependencies", tuple(sorted(self.dependencies, key=lambda x: x.int))
        )
        if self.retry.mode is RetryMode.SAFE and self.kind not in REPLAY_SAFE_KINDS:
            raise DomainError("This task kind cannot be automatically replayed.")


@dataclass(frozen=True, slots=True)
class TaskSnapshot:
    spec: TaskSpec
    state: TaskState
    attempt_count: int
    phase_attempt_count: int
    next_run_at: datetime
    lease_owner: UUID | None
    lease_token: UUID | None
    lease_until: datetime | None
    waiting_question_id: UUID | None
    last_error_class: TaskErrorClass | None

    def __post_init__(self) -> None:
        if not isinstance(self.spec, TaskSpec) or not isinstance(self.state, TaskState):
            raise DomainError("Task snapshots require validated specifications and states.")
        for count in (self.attempt_count, self.phase_attempt_count):
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise DomainError("Task attempt counts must be nonnegative integers.")
        if self.phase_attempt_count > self.attempt_count:
            raise DomainError("Phase attempts must not exceed the total attempt count.")
        require_timestamp(self.next_run_at)
        active = self.state in (TaskState.LEASED, TaskState.RUNNING)
        lease_values = (self.lease_owner, self.lease_token, self.lease_until)
        if (active and any(value is None for value in lease_values)) or (
            not active and any(value is not None for value in lease_values)
        ):
            raise DomainError("Active task states require a complete fenced lease.")
        for identifier in (self.lease_owner, self.lease_token, self.waiting_question_id):
            if identifier is not None:
                require_identifier(identifier)
        if self.lease_until is not None:
            require_timestamp(self.lease_until)
        if (self.state is TaskState.WAITING_USER) != (self.waiting_question_id is not None):
            raise DomainError("Waiting tasks require an exact question reference.")
        if self.last_error_class is not None and not isinstance(
            self.last_error_class, TaskErrorClass
        ):
            raise DomainError("Task snapshots require structured error classes.")


@dataclass(frozen=True, slots=True)
class TaskOutcome:
    state: TaskState
    error_class: TaskErrorClass | None = None
    question_id: UUID | None = None
    next_run_at: datetime | None = None

    def __post_init__(self) -> None:
        if self.state not in (
            TaskState.COMPLETED,
            TaskState.WAITING_USER,
            TaskState.RETRY_SCHEDULED,
            TaskState.BLOCKED,
            TaskState.FAILED,
            TaskState.CANCELLED,
        ) or not isinstance(self.state, TaskState):
            raise DomainError("A worker outcome must be an explicit inactive task state.")
        if self.error_class is not None and not isinstance(self.error_class, TaskErrorClass):
            raise DomainError("Task errors require a structured class, never raw exception text.")
        if (self.state is TaskState.WAITING_USER) != (self.question_id is not None):
            raise DomainError("Only waiting-user outcomes require an exact question reference.")
        if self.question_id is not None:
            require_identifier(self.question_id)
        if (self.state is TaskState.RETRY_SCHEDULED) != (self.next_run_at is not None):
            raise DomainError("Only retry outcomes require a next-run timestamp.")
        if self.next_run_at is not None:
            require_timestamp(self.next_run_at)


def retry_delay(policy: RetryPolicy, attempt_count: int) -> timedelta:
    """Bound exponential backoff without constructing an unbounded exponent."""
    require_version(attempt_count)
    delay = policy.base_delay_seconds
    for _ in range(min(attempt_count - 1, policy.max_delay_seconds.bit_length())):
        delay = min(delay * 2, policy.max_delay_seconds)
        if delay == policy.max_delay_seconds:
            break
    return timedelta(seconds=delay)


def failure_outcome(task: TaskSnapshot, error: TaskErrorClass, now: datetime) -> TaskOutcome:
    """Only explicit replay-safe work may retry; ambiguous external work always blocks."""
    require_timestamp(now)
    if not isinstance(error, TaskErrorClass):
        raise DomainError("Task failure must use a structured error class.")
    if error is TaskErrorClass.AMBIGUOUS_EXTERNAL:
        return TaskOutcome(TaskState.BLOCKED, error)
    if error is TaskErrorClass.LEASE_EXPIRED and task.spec.retry.mode is RetryMode.NEVER:
        return TaskOutcome(TaskState.BLOCKED, error)
    if (
        error in (TaskErrorClass.TRANSIENT, TaskErrorClass.LEASE_EXPIRED)
        and task.spec.retry.mode is RetryMode.SAFE
        and task.phase_attempt_count < task.spec.retry.max_attempts
    ):
        return TaskOutcome(
            TaskState.RETRY_SCHEDULED,
            error,
            next_run_at=now + retry_delay(task.spec.retry, task.phase_attempt_count),
        )
    return TaskOutcome(TaskState.FAILED, error)
