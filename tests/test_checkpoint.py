"""Tests for workflow checkpoint/resume."""

import json
from datetime import UTC, datetime
from pathlib import Path

from superintendent.state.checkpoint import (
    WorkflowCheckpoint,
    checkpoint_exists,
    load_checkpoint,
    save_checkpoint,
)
from superintendent.state.workflow import WorkflowState


class TestWorkflowCheckpoint:
    """Test the WorkflowCheckpoint dataclass."""

    def test_create_checkpoint(self):
        cp = WorkflowCheckpoint(
            workflow_id="wf-123",
            current_state=WorkflowState.CREATING_WORKTREE,
            completed_steps=["validate_repo"],
            sandbox_name="test-sandbox",
            worktree_path="/tmp/worktrees/test",
        )
        assert cp.workflow_id == "wf-123"
        assert cp.current_state == WorkflowState.CREATING_WORKTREE
        assert cp.completed_steps == ["validate_repo"]
        assert cp.sandbox_name == "test-sandbox"
        assert cp.worktree_path == "/tmp/worktrees/test"

    def test_timestamps_auto_populated(self):
        before = datetime.now(UTC)
        cp = WorkflowCheckpoint(
            workflow_id="wf-123",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        after = datetime.now(UTC)
        assert before <= cp.created_at <= after
        assert before <= cp.updated_at <= after

    def test_to_dict(self):
        cp = WorkflowCheckpoint(
            workflow_id="wf-abc",
            current_state=WorkflowState.AUTHENTICATING,
            completed_steps=["validate_repo", "create_worktree", "prepare_sandbox"],
            sandbox_name="my-sandbox",
            worktree_path="/home/user/worktrees/proj",
        )
        d = cp.to_dict()
        assert d["workflow_id"] == "wf-abc"
        assert d["current_state"] == "AUTHENTICATING"
        assert d["completed_steps"] == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
        ]
        assert d["sandbox_name"] == "my-sandbox"
        assert d["worktree_path"] == "/home/user/worktrees/proj"
        assert "created_at" in d
        assert "updated_at" in d

    def test_from_dict(self):
        d = {
            "workflow_id": "wf-xyz",
            "current_state": "PREPARING_SANDBOX",
            "completed_steps": ["validate_repo", "create_worktree"],
            "sandbox_name": "sb-1",
            "worktree_path": "/tmp/wt/proj",
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": "2026-01-01T00:05:00+00:00",
        }
        cp = WorkflowCheckpoint.from_dict(d)
        assert cp.workflow_id == "wf-xyz"
        assert cp.current_state == WorkflowState.PREPARING_SANDBOX
        assert cp.completed_steps == ["validate_repo", "create_worktree"]
        assert cp.sandbox_name == "sb-1"
        assert cp.worktree_path == "/tmp/wt/proj"
        assert cp.created_at.year == 2026
        assert cp.updated_at.minute == 5

    def test_roundtrip(self):
        cp = WorkflowCheckpoint(
            workflow_id="wf-round",
            current_state=WorkflowState.STARTING_AGENT,
            completed_steps=["validate_repo", "create_worktree", "initialize_state"],
            sandbox_name="round-sb",
            worktree_path="/tmp/wt/round",
        )
        d = cp.to_dict()
        cp2 = WorkflowCheckpoint.from_dict(d)
        assert cp2.workflow_id == cp.workflow_id
        assert cp2.current_state == cp.current_state
        assert cp2.completed_steps == cp.completed_steps
        assert cp2.sandbox_name == cp.sandbox_name
        assert cp2.worktree_path == cp.worktree_path

    def test_update_refreshes_timestamp(self):
        cp = WorkflowCheckpoint(
            workflow_id="wf-1",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        original_updated = cp.updated_at
        cp.update(
            current_state=WorkflowState.ENSURING_REPO,
            completed_steps=["validate_repo"],
        )
        assert cp.current_state == WorkflowState.ENSURING_REPO
        assert cp.completed_steps == ["validate_repo"]
        assert cp.updated_at >= original_updated

    def test_empty_completed_steps(self):
        cp = WorkflowCheckpoint(
            workflow_id="wf-empty",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        assert cp.completed_steps == []
        d = cp.to_dict()
        assert d["completed_steps"] == []


class TestSaveLoadCheckpoint:
    """Test saving and loading checkpoints to/from disk."""

    def test_save_creates_file(self, tmp_path: Path):
        cp = WorkflowCheckpoint(
            workflow_id="wf-save",
            current_state=WorkflowState.CREATING_WORKTREE,
            completed_steps=["validate_repo"],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        filepath = tmp_path / ".ralph" / "workflow_state.json"
        save_checkpoint(cp, filepath)
        assert filepath.exists()

    def test_save_creates_parent_dirs(self, tmp_path: Path):
        cp = WorkflowCheckpoint(
            workflow_id="wf-dirs",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        filepath = tmp_path / "deep" / "nested" / "workflow_state.json"
        save_checkpoint(cp, filepath)
        assert filepath.exists()

    def test_save_writes_valid_json(self, tmp_path: Path):
        cp = WorkflowCheckpoint(
            workflow_id="wf-json",
            current_state=WorkflowState.AUTHENTICATING,
            completed_steps=["validate_repo", "create_worktree"],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        filepath = tmp_path / "workflow_state.json"
        save_checkpoint(cp, filepath)
        data = json.loads(filepath.read_text())
        assert data["workflow_id"] == "wf-json"

    def test_load_roundtrip(self, tmp_path: Path):
        cp = WorkflowCheckpoint(
            workflow_id="wf-load",
            current_state=WorkflowState.STARTING_AGENT,
            completed_steps=["validate_repo", "create_worktree", "prepare_sandbox"],
            sandbox_name="load-sb",
            worktree_path="/tmp/wt/load",
        )
        filepath = tmp_path / "workflow_state.json"
        save_checkpoint(cp, filepath)
        loaded = load_checkpoint(filepath)
        assert loaded.workflow_id == cp.workflow_id
        assert loaded.current_state == cp.current_state
        assert loaded.completed_steps == cp.completed_steps
        assert loaded.sandbox_name == cp.sandbox_name
        assert loaded.worktree_path == cp.worktree_path

    def test_load_nonexistent_returns_none(self, tmp_path: Path):
        filepath = tmp_path / "does_not_exist.json"
        result = load_checkpoint(filepath)
        assert result is None

    def test_checkpoint_exists_true(self, tmp_path: Path):
        cp = WorkflowCheckpoint(
            workflow_id="wf-exists",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        filepath = tmp_path / "workflow_state.json"
        save_checkpoint(cp, filepath)
        assert checkpoint_exists(filepath) is True

    def test_checkpoint_exists_false(self, tmp_path: Path):
        filepath = tmp_path / "nope.json"
        assert checkpoint_exists(filepath) is False

    def test_save_overwrites_existing(self, tmp_path: Path):
        filepath = tmp_path / "workflow_state.json"
        cp1 = WorkflowCheckpoint(
            workflow_id="wf-v1",
            current_state=WorkflowState.INIT,
            completed_steps=[],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        save_checkpoint(cp1, filepath)

        cp2 = WorkflowCheckpoint(
            workflow_id="wf-v1",
            current_state=WorkflowState.CREATING_WORKTREE,
            completed_steps=["validate_repo"],
            sandbox_name="sb",
            worktree_path="/tmp/wt",
        )
        save_checkpoint(cp2, filepath)

        loaded = load_checkpoint(filepath)
        assert loaded is not None
        assert loaded.current_state == WorkflowState.CREATING_WORKTREE
        assert loaded.completed_steps == ["validate_repo"]
