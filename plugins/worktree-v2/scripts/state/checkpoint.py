"""Workflow checkpoint save/load for resume support."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from state.workflow import WorkflowState


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class WorkflowCheckpoint:
    """Persistent workflow state for checkpoint/resume."""

    workflow_id: str
    current_state: WorkflowState
    completed_steps: list[str]
    sandbox_name: str
    worktree_path: str
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)

    def update(
        self,
        current_state: WorkflowState | None = None,
        completed_steps: list[str] | None = None,
    ) -> None:
        """Update checkpoint fields and refresh updated_at timestamp."""
        if current_state is not None:
            self.current_state = current_state
        if completed_steps is not None:
            self.completed_steps = completed_steps
        self.updated_at = _now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "current_state": self.current_state.name,
            "completed_steps": self.completed_steps,
            "sandbox_name": self.sandbox_name,
            "worktree_path": self.worktree_path,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowCheckpoint":
        return cls(
            workflow_id=data["workflow_id"],
            current_state=WorkflowState[data["current_state"]],
            completed_steps=data["completed_steps"],
            sandbox_name=data["sandbox_name"],
            worktree_path=data["worktree_path"],
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
        )


def save_checkpoint(checkpoint: WorkflowCheckpoint, path: Path) -> None:
    """Save a checkpoint to a JSON file, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(checkpoint.to_dict(), indent=2))


def load_checkpoint(path: Path) -> WorkflowCheckpoint | None:
    """Load a checkpoint from a JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return WorkflowCheckpoint.from_dict(data)


def checkpoint_exists(path: Path) -> bool:
    """Check if a checkpoint file exists."""
    return path.exists()
