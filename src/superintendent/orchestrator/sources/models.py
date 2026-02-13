"""Task model and status enum for task source abstractions."""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class TaskStatus(StrEnum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"
    failed = "failed"


@dataclass
class Task:
    """A unified task representation across all task sources."""

    task_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.pending
    dependencies: list[str] = field(default_factory=list)
    labels: dict[str, str] = field(default_factory=dict)
    source_ref: str = ""

    def is_blocked(self, completed_ids: set[str]) -> bool:
        """Return True if this task has unmet dependencies."""
        return bool(set(self.dependencies) - completed_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": str(self.status),
            "dependencies": self.dependencies,
            "labels": self.labels,
            "source_ref": self.source_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(
            task_id=data["task_id"],
            title=data["title"],
            description=data["description"],
            status=TaskStatus(data.get("status", "pending")),
            dependencies=data.get("dependencies", []),
            labels=data.get("labels", {}),
            source_ref=data.get("source_ref", ""),
        )
