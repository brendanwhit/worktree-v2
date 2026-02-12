"""Tests for Ralph state (.ralph/ directory) management."""

import json
from pathlib import Path

from superintendent.state.ralph import RalphState


class TestRalphStateInit:
    """Test initializing the .ralph/ directory."""

    def test_creates_directory(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        assert rs.ralph_dir.is_dir()

    def test_creates_progress_md(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        assert (rs.ralph_dir / "progress.md").exists()
        content = (rs.ralph_dir / "progress.md").read_text()
        assert "# Progress" in content

    def test_creates_config_json(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        config_path = rs.ralph_dir / "config.json"
        assert config_path.exists()
        data = json.loads(config_path.read_text())
        assert data["task"] == "test task"

    def test_creates_guardrails_md(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        assert (rs.ralph_dir / "guardrails.md").exists()
        content = (rs.ralph_dir / "guardrails.md").read_text()
        assert "Guardrails" in content

    def test_creates_worktree_task_md(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        assert (rs.ralph_dir / "worktree-task.md").exists()
        content = (rs.ralph_dir / "worktree-task.md").read_text()
        assert "test task" in content

    def test_config_includes_execution_mode(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test", execution_mode="docker-sandbox")
        data = json.loads((rs.ralph_dir / "config.json").read_text())
        assert data["execution_mode"] == "docker-sandbox"

    def test_config_includes_bead_id(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test", bead_id="wt-v2-9qs")
        data = json.loads((rs.ralph_dir / "config.json").read_text())
        assert data["bead_id"] == "wt-v2-9qs"

    def test_idempotent_does_not_overwrite(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="original task")
        (rs.ralph_dir / "progress.md").write_text("# Custom progress")
        rs.init(task="new task")
        content = (rs.ralph_dir / "progress.md").read_text()
        assert content == "# Custom progress"


class TestRalphStateReset:
    """Test resetting .ralph/ directory for sandbox reuse."""

    def test_removes_all_files(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        assert rs.ralph_dir.is_dir()
        rs.reset()
        assert not rs.ralph_dir.exists()

    def test_reset_nonexistent_is_safe(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.reset()

    def test_reset_then_reinit(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="first task")
        rs.reset()
        rs.init(task="second task")
        data = json.loads((rs.ralph_dir / "config.json").read_text())
        assert data["task"] == "second task"


class TestRalphStateConfig:
    """Test loading and saving Ralph config."""

    def test_config_property(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task", execution_mode="docker-sandbox")
        config = rs.config
        assert config is not None
        assert config["task"] == "my task"
        assert config["execution_mode"] == "docker-sandbox"

    def test_config_not_initialized_returns_none(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        assert rs.config is None

    def test_save_config(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.save_config({"task": "saved task", "execution_mode": "local"})
        loaded = rs.config
        assert loaded is not None
        assert loaded["task"] == "saved task"
        assert loaded["execution_mode"] == "local"


class TestRalphStateProgress:
    """Test updating progress.md."""

    def test_appends_entry(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        rs.update_progress("Completed step 1")
        content = (rs.ralph_dir / "progress.md").read_text()
        assert "Completed step 1" in content

    def test_multiple_entries(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        rs.update_progress("Step 1 done")
        rs.update_progress("Step 2 done")
        content = (rs.ralph_dir / "progress.md").read_text()
        assert "Step 1 done" in content
        assert "Step 2 done" in content

    def test_entry_includes_timestamp(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="test task")
        rs.update_progress("Something happened")
        content = (rs.ralph_dir / "progress.md").read_text()
        assert "202" in content


class TestRalphStateIsInitialized:
    """Test the is_initialized property."""

    def test_true_after_init(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        rs.init(task="my task")
        assert rs.is_initialized is True

    def test_false_before_init(self, tmp_path: Path):
        rs = RalphState(tmp_path / ".ralph")
        assert rs.is_initialized is False
