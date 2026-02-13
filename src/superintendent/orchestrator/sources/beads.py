"""BeadsSource — native, first-class task source backed by the beads CLI."""

import json
import subprocess
from pathlib import Path
from typing import Any

from superintendent.orchestrator.sources.models import Task, TaskStatus

# Map beads status strings to TaskStatus
_STATUS_MAP: dict[str, TaskStatus] = {
    "open": TaskStatus.pending,
    "closed": TaskStatus.completed,
    "in_progress": TaskStatus.in_progress,
}


class BeadsSource:
    """Task source backed by the beads (bd) CLI.

    This is the native, first-class task source with full status sync.
    All operations delegate to the bd CLI, which must be available on PATH.
    """

    def __init__(self, repo_root: Path) -> None:
        self._repo_root = repo_root

    def get_tasks(self) -> list[Task]:
        """Get all tasks via ``bd list --json``."""
        result = self._run_bd(["list", "--json"])
        if result is None:
            return []
        return [self._parse_bead(bead) for bead in result]

    def get_ready_tasks(self) -> list[Task]:
        """Get ready (unblocked) tasks via ``bd ready --json``."""
        result = self._run_bd(["ready", "--json"])
        if result is None:
            return []
        return [self._parse_bead(bead) for bead in result]

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Update task status via bd commands."""
        if status == TaskStatus.completed:
            self._run_bd_raw(["close", task_id, "--message", "Completed by agent"])
        elif status == TaskStatus.in_progress:
            self._run_bd_raw(["update", task_id, "--claim"])
        elif status == TaskStatus.failed:
            self._run_bd_raw(["update", task_id, "--set", "status=failed"])

    def claim_task(self, task_id: str, _agent_id: str) -> bool:
        """Claim a task via ``bd update --claim``."""
        result = subprocess.run(
            ["bd", "update", task_id, "--claim"],
            capture_output=True,
            text=True,
            cwd=self._repo_root,
        )
        return result.returncode == 0

    def _run_bd(self, args: list[str]) -> list[dict[str, Any]] | None:
        """Run a bd command that returns JSON, parse and return the result."""
        result = subprocess.run(
            ["bd", *args],
            capture_output=True,
            text=True,
            cwd=self._repo_root,
        )
        if result.returncode != 0:
            return None
        try:
            return json.loads(result.stdout)
        except (json.JSONDecodeError, ValueError):
            return None

    def _run_bd_raw(self, args: list[str]) -> bool:
        """Run a bd command and return success/failure."""
        result = subprocess.run(
            ["bd", *args],
            capture_output=True,
            text=True,
            cwd=self._repo_root,
        )
        return result.returncode == 0

    @staticmethod
    def _parse_bead(bead: dict[str, Any]) -> Task:
        """Convert a bead JSON object to a Task."""
        bead_id = bead["id"]
        status = _STATUS_MAP.get(bead.get("status", "open"), TaskStatus.pending)

        # Parse dependencies from the bead dependency list
        dependencies: list[str] = []
        for dep in bead.get("dependencies", []):
            depends_on = dep.get("depends_on_id", "")
            if depends_on:
                dependencies.append(depends_on)

        # Parse labels: beads uses "key:value" format in label list
        labels: dict[str, str] = {}
        for label in bead.get("labels", []):
            if ":" in label:
                key, value = label.split(":", 1)
                labels[key] = value

        return Task(
            task_id=bead_id,
            title=bead["title"],
            description=bead.get("description", ""),
            status=status,
            dependencies=dependencies,
            labels=labels,
            source_ref=bead_id,
        )
