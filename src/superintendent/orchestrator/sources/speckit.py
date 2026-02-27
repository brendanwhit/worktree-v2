"""SpecKitSource — parse tasks from spec-kit's tasks.md format."""

import re
from pathlib import Path

from .models import Task, TaskStatus
from .protocol import TaskSource

# Matches: - [ ] [T001] [P] [US1] Task description
# or:      - [x] [T002] [US1] Task description (no parallel marker)
# Groups: checkbox, task_id, rest_of_line
_SPECKIT_LINE = re.compile(r"^-\s+\[([ xX])\]\s+\[([^\]]+)\]\s+(.+)$")

# Detect [P] parallel marker at the start of rest_of_line
_PARALLEL_MARKER = re.compile(r"^\[P\]\s+(.+)$")

# Detect [USN] story label
_STORY_LABEL = re.compile(r"^\[US(\d+)\]\s+(.+)$")

# Phase header: ## Phase N: Name or ## Setup, ## Foundation, etc.
_PHASE_HEADER = re.compile(r"^##\s+(?:Phase\s+\d+:\s+)?(.+)$")

# Full spec-kit detection: at least one line matching the full pattern
_SPECKIT_DETECT = re.compile(r"^-\s+\[[ xX]\]\s+\[T\d+\]\s+", re.MULTILINE)


class SpecKitSource(TaskSource):
    """Parse tasks from spec-kit's tasks.md format.

    Supports:
    - Task IDs: ``[T001]``
    - Parallel markers: ``[P]`` means no sibling dependencies
    - Story labels: ``[US1]`` for grouping by user story
    - Phase structure: ``## Phase 1: Setup`` headers
    - Dependency inference: sequential tasks within a story depend on predecessors
    """

    source_name = "speckit"

    @classmethod
    def can_handle(cls, repo_root: Path) -> bool:
        """Detect spec-kit format by checking tasks.md for [T001] patterns."""
        tasks_md = repo_root / "tasks.md"
        if not tasks_md.exists():
            return False
        try:
            content = tasks_md.read_text()
        except OSError:
            return False
        return bool(_SPECKIT_DETECT.search(content))

    @classmethod
    def create(cls, repo_root: Path) -> "SpecKitSource":
        return cls(repo_root / "tasks.md")

    def __init__(self, path: Path) -> None:
        self._path = path

    def get_tasks(self) -> list[Task]:
        content = self._path.read_text()
        return self._parse_tasks(content)

    def get_ready_tasks(self) -> list[Task]:
        tasks = self.get_tasks()
        completed_ids = {t.task_id for t in tasks if t.status == TaskStatus.completed}
        return [
            t
            for t in tasks
            if t.status != TaskStatus.completed and not t.is_blocked(completed_ids)
        ]

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        content = self._path.read_text()
        lines = content.splitlines()
        new_lines: list[str] = []
        changed = False

        for line in lines:
            match = _SPECKIT_LINE.match(line)
            if match:
                _checkbox, line_id, rest = match.groups()
                if line_id == task_id:
                    check = "x" if status == TaskStatus.completed else " "
                    line = f"- [{check}] [{line_id}] {rest}"
                    changed = True
            new_lines.append(line)

        if changed:
            self._path.write_text("\n".join(new_lines) + "\n")

    def claim_task(self, task_id: str) -> bool:  # noqa: ARG002
        return True

    def _parse_tasks(self, content: str) -> list[Task]:
        tasks: list[Task] = []
        current_phase = ""
        # Track last sequential (non-parallel) task per story for dependency chaining
        last_sequential: dict[str, str] = {}

        for line in content.splitlines():
            # Check for phase headers
            phase_match = _PHASE_HEADER.match(line)
            if phase_match:
                current_phase = phase_match.group(1).strip()
                continue

            # Check for task lines
            task_match = _SPECKIT_LINE.match(line)
            if not task_match:
                continue

            checkbox, task_id, rest = task_match.groups()
            status = (
                TaskStatus.completed if checkbox in ("x", "X") else TaskStatus.pending
            )

            # Parse parallel marker
            is_parallel = False
            parallel_match = _PARALLEL_MARKER.match(rest)
            if parallel_match:
                is_parallel = True
                rest = parallel_match.group(1)

            # Parse story label
            story = ""
            story_match = _STORY_LABEL.match(rest)
            if story_match:
                story = f"US{story_match.group(1)}"
                rest = story_match.group(2)

            description = rest.strip()

            # Build labels
            labels: dict[str, str] = {}
            if story:
                labels["story"] = story
            if current_phase:
                labels["phase"] = current_phase
            if is_parallel:
                labels["parallel"] = "true"

            # Determine dependencies: sequential tasks within same story
            # depend on the previous sequential task in that story
            dependencies: list[str] = []
            if story and not is_parallel:
                prev = last_sequential.get(story)
                if prev is not None:
                    dependencies.append(prev)

            tasks.append(
                Task(
                    task_id=task_id,
                    title=description,
                    description=description,
                    status=status,
                    dependencies=dependencies,
                    labels=labels,
                    source_ref=str(self._path),
                )
            )

            # Update tracking: sequential tasks update the chain
            if story and not is_parallel:
                last_sequential[story] = task_id

        return tasks
