"""Ralph state (.ralph/ directory) management."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def init_ralph_state(
    ralph_dir: Path,
    task: str,
    execution_mode: str = "unknown",
    bead_id: str | None = None,
) -> None:
    """Initialize the .ralph/ directory with default files.

    Idempotent: does not overwrite existing files.
    """
    ralph_dir.mkdir(parents=True, exist_ok=True)

    # config.json
    config_path = ralph_dir / "config.json"
    if not config_path.exists():
        config = {
            "execution_mode": execution_mode,
            "task": task,
            "bead_id": bead_id,
            "created_at": _now_iso(),
        }
        config_path.write_text(json.dumps(config, indent=2))

    # progress.md
    progress_path = ralph_dir / "progress.md"
    if not progress_path.exists():
        progress_path.write_text("# Progress\n\n")

    # guardrails.md
    guardrails_path = ralph_dir / "guardrails.md"
    if not guardrails_path.exists():
        guardrails_path.write_text(
            "# Guardrails\n\nLearned failure patterns and things to avoid.\n"
        )

    # worktree-task.md
    task_path = ralph_dir / "worktree-task.md"
    if not task_path.exists():
        task_path.write_text(f"# Task\n\n{task}\n")


def reset_ralph_state(ralph_dir: Path) -> None:
    """Remove the .ralph/ directory entirely for sandbox reuse."""
    if ralph_dir.exists():
        shutil.rmtree(ralph_dir)


def save_ralph_config(config: dict[str, Any], path: Path) -> None:
    """Save a config dict to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2))


def load_ralph_config(path: Path) -> dict[str, Any] | None:
    """Load config from a JSON file. Returns None if file doesn't exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text())


def update_progress(ralph_dir: Path, entry: str) -> None:
    """Append a timestamped entry to progress.md."""
    progress_path = ralph_dir / "progress.md"
    timestamp = _now_iso()
    with open(progress_path, "a") as f:
        f.write(f"- [{timestamp}] {entry}\n")


class RalphState:
    """Convenience wrapper for .ralph/ directory operations."""

    def __init__(self, ralph_dir: Path) -> None:
        self.ralph_dir = ralph_dir

    @property
    def is_initialized(self) -> bool:
        return self.ralph_dir.is_dir()

    @property
    def config(self) -> dict[str, Any] | None:
        return load_ralph_config(self.ralph_dir / "config.json")

    def init(
        self,
        task: str,
        execution_mode: str = "unknown",
        bead_id: str | None = None,
    ) -> None:
        init_ralph_state(
            self.ralph_dir,
            task=task,
            execution_mode=execution_mode,
            bead_id=bead_id,
        )

    def reset(self) -> None:
        reset_ralph_state(self.ralph_dir)

    def update_progress(self, entry: str) -> None:
        update_progress(self.ralph_dir, entry)
