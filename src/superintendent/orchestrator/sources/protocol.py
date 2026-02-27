"""TaskSource abstract base class definition."""

from abc import ABC, abstractmethod
from pathlib import Path

from .models import Task, TaskStatus


class TaskSource(ABC):
    """Base class for task source backends.

    All task sources must subclass this. The orchestrator is agnostic
    about where tasks come from — it only cares about getting tasks
    and updating their status.

    Subclasses should define ``source_name`` and implement ``can_handle``
    to participate in auto-detection via ``detect_source()``.
    """

    source_name: str = ""

    @classmethod
    # repo_root is needed by subclass overrides but unused in the default impl
    def can_handle(cls, repo_root: Path) -> bool:  # noqa: ARG003
        """Return True if this source can provide tasks for the given repo.

        Override in subclasses to participate in auto-detection.
        The default returns False (opt-in).
        """
        return False

    @classmethod
    def create(cls, repo_root: Path) -> "TaskSource":
        """Create an instance for the given repo.

        Override in subclasses that need custom construction.
        The default passes repo_root to __init__.
        """
        return cls(repo_root=repo_root)  # type: ignore[call-arg]

    @abstractmethod
    def get_tasks(self) -> list[Task]:
        """Return all tasks from this source."""
        ...

    @abstractmethod
    def get_ready_tasks(self) -> list[Task]:
        """Return tasks that are unblocked and ready to work on."""
        ...

    @abstractmethod
    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Update the status of a task in the backing store."""
        ...

    @abstractmethod
    def claim_task(self, task_id: str) -> bool:
        """Claim a task for this agent. Returns True on success."""
        ...
