"""MarkdownSource — parse tasks from a markdown checklist file."""

import re
from pathlib import Path

from .models import Task, TaskStatus
from .protocol import TaskSource

# Matches lines like: "- [ ] Task" or "- [x] Task" or "- [ ] [T001] Task"
_TASK_PATTERN = re.compile(r"^(\s*)-\s+\[([ xX])\]\s+(?:\[([^\]]+)\]\s+)?(.+)$")


_MARKDOWN_CANDIDATES = ["tasks.md", "TODO.md"]


class MarkdownSource(TaskSource):
    """Parse tasks from a markdown checklist file.

    Supports:
    - ``- [ ] Task description`` format
    - Optional explicit IDs: ``- [ ] [T001] Task description``
    - Nested tasks infer parent dependencies via indentation
    - Status update toggles checkboxes in the file
    """

    source_name = "markdown"

    @classmethod
    def can_handle(cls, repo_root: Path) -> bool:
        return any((repo_root / name).exists() for name in _MARKDOWN_CANDIDATES)

    @classmethod
    def create(cls, repo_root: Path) -> "MarkdownSource":
        for name in _MARKDOWN_CANDIDATES:
            path = repo_root / name
            if path.exists():
                return cls(path)
        raise FileNotFoundError("No markdown task file found")

    def __init__(self, path: Path) -> None:
        self._path = path

    def get_tasks(self) -> list[Task]:
        """Parse all checklist items from the markdown file."""
        content = self._path.read_text()
        return self._parse_tasks(content)

    def get_ready_tasks(self) -> list[Task]:
        """Return unchecked tasks whose parent dependencies are completed."""
        tasks = self.get_tasks()
        completed_ids = {t.task_id for t in tasks if t.status == TaskStatus.completed}
        return [
            t
            for t in tasks
            if t.status != TaskStatus.completed and not t.is_blocked(completed_ids)
        ]

    def update_status(self, task_id: str, status: TaskStatus) -> None:
        """Toggle the checkbox in the markdown file to reflect new status."""
        content = self._path.read_text()
        lines = content.splitlines()
        new_lines: list[str] = []
        changed = False

        for line in lines:
            match = _TASK_PATTERN.match(line)
            if match:
                indent, _checkbox, explicit_id, text = match.groups()
                line_task_id = explicit_id or self._make_id(text)
                if line_task_id == task_id:
                    check = "x" if status == TaskStatus.completed else " "
                    id_part = f"[{explicit_id}] " if explicit_id else ""
                    line = f"{indent}- [{check}] {id_part}{text}"
                    changed = True
            new_lines.append(line)

        if changed:
            self._path.write_text("\n".join(new_lines) + "\n")

    # task_id is required by the ABC interface but unused in this no-op impl
    def claim_task(self, task_id: str) -> bool:  # noqa: ARG002
        return True

    def _parse_tasks(self, content: str) -> list[Task]:
        tasks: list[Task] = []
        # Stack of (indent_level, task_id) to track nesting
        parent_stack: list[tuple[int, str]] = []

        for line in content.splitlines():
            match = _TASK_PATTERN.match(line)
            if not match:
                continue

            indent, checkbox, explicit_id, text = match.groups()
            indent_level = len(indent)
            task_id = explicit_id or self._make_id(text)
            status = (
                TaskStatus.completed if checkbox in ("x", "X") else TaskStatus.pending
            )

            # Pop parents that are at the same or deeper indent level
            while parent_stack and parent_stack[-1][0] >= indent_level:
                parent_stack.pop()

            dependencies: list[str] = []
            if parent_stack:
                dependencies = [parent_stack[-1][1]]

            tasks.append(
                Task(
                    task_id=task_id,
                    title=text.strip(),
                    description=text.strip(),
                    status=status,
                    dependencies=dependencies,
                    source_ref=str(self._path),
                )
            )

            parent_stack.append((indent_level, task_id))

        return tasks

    @staticmethod
    def _make_id(text: str) -> str:
        """Generate a stable ID from task text."""
        import hashlib

        digest = hashlib.sha256(text.strip().encode()).hexdigest()[:8]
        return f"md-{digest}"
