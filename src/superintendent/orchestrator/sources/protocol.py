"""TaskSource protocol definition."""

from typing import Protocol, runtime_checkable

from superintendent.orchestrator.sources.models import Task, TaskStatus


@runtime_checkable
class TaskSource(Protocol):
    """Protocol for task source backends.

    All task sources must implement this interface. The orchestrator
    is agnostic about where tasks come from — it only cares about
    getting tasks and updating their status.
    """

    def get_tasks(self) -> list[Task]: ...

    def get_ready_tasks(self) -> list[Task]: ...

    def update_status(self, task_id: str, status: TaskStatus) -> None: ...

    def claim_task(self, task_id: str, agent_id: str) -> bool: ...
