"""Ralph state (.ralph/ directory) management."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class RalphState:
    """Manages the .ralph/ directory for an agent."""

    def __init__(self, ralph_dir: Path) -> None:
        self.ralph_dir = ralph_dir

    @property
    def is_initialized(self) -> bool:
        return self.ralph_dir.is_dir()

    @property
    def config(self) -> dict[str, Any] | None:
        """Load config from config.json. Returns None if not initialized."""
        config_path = self.ralph_dir / "config.json"
        if not config_path.exists():
            return None
        result: dict[str, Any] = json.loads(config_path.read_text())
        return result

    def init(
        self,
        task: str,
        execution_mode: str = "unknown",
        bead_id: str | None = None,
    ) -> None:
        """Initialize the .ralph/ directory with default files.

        Idempotent: does not overwrite existing files.
        """
        self.ralph_dir.mkdir(parents=True, exist_ok=True)

        config_path = self.ralph_dir / "config.json"
        if not config_path.exists():
            config = {
                "execution_mode": execution_mode,
                "task": task,
                "bead_id": bead_id,
                "created_at": _now_iso(),
            }
            config_path.write_text(json.dumps(config, indent=2))

        progress_path = self.ralph_dir / "progress.md"
        if not progress_path.exists():
            progress_path.write_text("# Progress\n\n")

        guardrails_path = self.ralph_dir / "guardrails.md"
        if not guardrails_path.exists():
            guardrails_path.write_text(
                "# Guardrails\n\nLearned failure patterns and things to avoid.\n"
            )

        task_path = self.ralph_dir / "worktree-task.md"
        if not task_path.exists():
            task_path.write_text(f"# Task\n\n{task}\n")

    def reset(self) -> None:
        """Remove the .ralph/ directory entirely for sandbox reuse."""
        if self.ralph_dir.exists():
            shutil.rmtree(self.ralph_dir)

    def save_config(self, config: dict[str, Any]) -> None:
        """Save a config dict to config.json."""
        self.ralph_dir.mkdir(parents=True, exist_ok=True)
        (self.ralph_dir / "config.json").write_text(json.dumps(config, indent=2))

    def update_progress(self, entry: str) -> None:
        """Append a timestamped entry to progress.md."""
        progress_path = self.ralph_dir / "progress.md"
        timestamp = _now_iso()
        with open(progress_path, "a") as f:
            f.write(f"- [{timestamp}] {entry}\n")
