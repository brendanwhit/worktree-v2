"""SingleTaskSource — wraps a single task string into the TaskSource protocol."""

import hashlib

from superintendent.orchestrator.sources.models import Task, TaskStatus


class SingleTaskSource:
    """The simplest task source: a single ad-hoc task string.

    Used for: `superintendent run --task 'fix the login bug'`
    Status updates are no-ops since this is ephemeral.
    """

    def __init__(self, description: str, task_id: str | None = None) -> None:
        self._description = description
        self._task_id = task_id or self._generate_id(description)

    @staticmethod
    def _generate_id(description: str) -> str:
        digest = hashlib.sha256(description.encode()).hexdigest()[:8]
        return f"single-{digest}"

    def get_tasks(self) -> list[Task]:
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
        return self.get_tasks()

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        pass

    def claim_task(self, _task_id: str, _agent_id: str) -> bool:
        return True
