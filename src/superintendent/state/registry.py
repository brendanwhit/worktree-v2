"""Global registry for tracking active entries."""

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class WorktreeEntry:
    """A single entry in the global registry."""

    name: str
    repo: str
    branch: str
    worktree_path: str
    sandbox_name: str | None = None
    created_at: str = field(default_factory=_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "repo": self.repo,
            "branch": self.branch,
            "worktree_path": self.worktree_path,
            "sandbox_name": self.sandbox_name,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorktreeEntry":
        return cls(
            name=data["name"],
            repo=data["repo"],
            branch=data["branch"],
            worktree_path=data["worktree_path"],
            sandbox_name=data.get("sandbox_name"),
            created_at=data.get("created_at", _now_iso()),
        )


class WorktreeRegistry:
    """Manages the global registry at ~/.claude/superintendent-registry.json."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def _load(self) -> list["WorktreeEntry"]:
        if not self._path.exists():
            return []
        data = json.loads(self._path.read_text())
        return [WorktreeEntry.from_dict(w) for w in data.get("entries", [])]

    def _save(self, entries: list["WorktreeEntry"]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {"entries": [e.to_dict() for e in entries]}
        self._path.write_text(json.dumps(data, indent=2))

    def list_all(self) -> list["WorktreeEntry"]:
        """Return all registered entries."""
        return self._load()

    def get(self, name: str) -> WorktreeEntry | None:
        """Look up an entry by name."""
        for entry in self._load():
            if entry.name == name:
                return entry
        return None

    def add(self, entry: WorktreeEntry) -> None:
        """Add or replace an entry (keyed by name)."""
        entries = [e for e in self._load() if e.name != entry.name]
        entries.append(entry)
        self._save(entries)

    def remove(self, name: str) -> bool:
        """Remove an entry by name. Returns True if it was found."""
        entries = self._load()
        filtered = [e for e in entries if e.name != name]
        if len(filtered) == len(entries):
            return False
        self._save(filtered)
        return True

    def cleanup(self) -> list[str]:
        """Remove entries whose worktree_path no longer exists. Returns removed names."""
        entries = self._load()
        keep: list[WorktreeEntry] = []
        removed: list[str] = []
        for entry in entries:
            if Path(entry.worktree_path).exists():
                keep.append(entry)
            else:
                removed.append(entry.name)
        if removed:
            self._save(keep)
        return removed
