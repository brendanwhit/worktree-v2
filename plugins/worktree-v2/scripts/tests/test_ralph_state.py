"""Tests for Ralph state (.ralph/ directory) management."""

import json
from pathlib import Path

from state.ralph import (
    RalphState,
    init_ralph_state,
    load_ralph_config,
    reset_ralph_state,
    save_ralph_config,
    update_progress,
)


class TestInitRalphState:
    """Test initializing the .ralph/ directory."""

    def test_creates_directory(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        assert ralph_dir.is_dir()

    def test_creates_progress_md(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        assert (ralph_dir / "progress.md").exists()
        content = (ralph_dir / "progress.md").read_text()
        assert "# Progress" in content

    def test_creates_config_json(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        config_path = ralph_dir / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["task"] == "test task"

    def test_creates_guardrails_md(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        assert (ralph_dir / "guardrails.md").exists()
        content = (ralph_dir / "guardrails.md").read_text()
        assert "Guardrails" in content

    def test_creates_worktree_task_md(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        assert (ralph_dir / "worktree-task.md").exists()
        content = (ralph_dir / "worktree-task.md").read_text()
        assert "test task" in content

    def test_config_includes_execution_mode(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test", execution_mode="docker-sandbox")
        data = json.loads((ralph_dir / "config.json").read_text())
        assert data["execution_mode"] == "docker-sandbox"

    def test_config_includes_bead_id(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test", bead_id="wt-v2-9qs")
        data = json.loads((ralph_dir / "config.json").read_text())
        assert data["bead_id"] == "wt-v2-9qs"

    def test_idempotent_does_not_overwrite(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="original task")
        # Modify progress
        (ralph_dir / "progress.md").write_text("# Custom progress")
        # Re-init should not overwrite existing files
        init_ralph_state(ralph_dir, task="new task")
        content = (ralph_dir / "progress.md").read_text()
        assert content == "# Custom progress"


class TestResetRalphState:
    """Test resetting .ralph/ directory for sandbox reuse."""

    def test_removes_all_files(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        assert ralph_dir.is_dir()
        reset_ralph_state(ralph_dir)
        assert not ralph_dir.exists()

    def test_reset_nonexistent_is_safe(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        # Should not raise
        reset_ralph_state(ralph_dir)

    def test_reset_then_reinit(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="first task")
        reset_ralph_state(ralph_dir)
        init_ralph_state(ralph_dir, task="second task")
        data = json.loads((ralph_dir / "config.json").read_text())
        assert data["task"] == "second task"


class TestRalphConfig:
    """Test loading and saving Ralph config."""

    def test_save_and_load(self, tmp_path: Path):
        config_path = tmp_path / "config.json"
        config = {
            "task": "my task",
            "execution_mode": "local",
            "bead_id": None,
        }
        save_ralph_config(config, config_path)
        loaded = load_ralph_config(config_path)
        assert loaded["task"] == "my task"
        assert loaded["execution_mode"] == "local"

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        config_path = tmp_path / "nope.json"
        result = load_ralph_config(config_path)
        assert result is None


class TestUpdateProgress:
    """Test updating progress.md."""

    def test_appends_entry(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        update_progress(ralph_dir, "Completed step 1")
        content = (ralph_dir / "progress.md").read_text()
        assert "Completed step 1" in content

    def test_multiple_entries(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        update_progress(ralph_dir, "Step 1 done")
        update_progress(ralph_dir, "Step 2 done")
        content = (ralph_dir / "progress.md").read_text()
        assert "Step 1 done" in content
        assert "Step 2 done" in content

    def test_entry_includes_timestamp(self, tmp_path: Path):
        ralph_dir = tmp_path / ".ralph"
        init_ralph_state(ralph_dir, task="test task")
        update_progress(ralph_dir, "Something happened")
        content = (ralph_dir / "progress.md").read_text()
        # Should have ISO-ish timestamp
        assert "202" in content  # Year prefix


class TestRalphState:
    """Test the RalphState convenience class."""

    def test_init_creates_directory(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task")
        assert rs.ralph_dir.is_dir()

    def test_config_property(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task", execution_mode="docker-sandbox")
        config = rs.config
        assert config is not None
        assert config["task"] == "my task"

    def test_reset(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task")
        rs.reset()
        assert not rs.ralph_dir.exists()

    def test_update_progress(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task")
        rs.update_progress("Did something")
        content = (rs.ralph_dir / "progress.md").read_text()
        assert "Did something" in content

    def test_is_initialized_true(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task")
        assert rs.is_initialized is True

    def test_is_initialized_false(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        assert rs.is_initialized is False
