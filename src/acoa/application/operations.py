"""Operational orchestration boundaries for health and graceful shutdown."""

from typing import Protocol
from uuid import UUID

from acoa.domain.tasks import TaskErrorClass, TaskSnapshot


class ShutdownQueue(Protocol):
    def fail(
        self, task_id: UUID, owner: UUID, token: UUID, error: TaskErrorClass
    ) -> TaskSnapshot: ...


def preserve_task_for_shutdown(
    queue: ShutdownQueue, task_id: UUID, owner: UUID, token: UUID
) -> TaskSnapshot:
    """Release owned work through the durable retry/block policy before process exit."""
    return queue.fail(task_id, owner, token, TaskErrorClass.LEASE_EXPIRED)
