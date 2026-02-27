"""SingleTaskSource — wraps a single task string into a TaskSource."""

import hashlib

from .models import Task, TaskStatus
from .protocol import TaskSource


class SingleTaskSource(TaskSource):
    """The simplest task source: a single ad-hoc task string.

    Used for: `superintendent run --task 'fix the login bug'`
    Status updates are no-ops since this is ephemeral.
    Not auto-detected — used as explicit fallback when a task string is provided.
    """

    source_name = "single"

    def __init__(self, description: str, task_id: str | None = None) -> None:
        self._description = description
        self._task_id = task_id or self._generate_id(description)

    @staticmethod
    def _generate_id(description: str) -> str:
        digest = hashlib.sha256(description.encode()).hexdigest()[:8]
        return f"single-{digest}"

    def get_tasks(self) -> list[Task]:
        """Return the single wrapped task."""
        return [
            Task(
                task_id=self._task_id,
                title=self._description,
                description=self._description,
                status=TaskStatus.pending,
                source_ref="single",
            )
        ]

    def get_ready_tasks(self) -> list[Task]:
        """A single task is always ready."""
        return self.get_tasks()

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        pass

    # task_id is required by the ABC interface but unused in this no-op impl
    def claim_task(self, task_id: str) -> bool:  # noqa: ARG002
        return True
