"""Tests for BeadsSource adapter."""

import json
from pathlib import Path
from unittest.mock import patch

from superintendent.orchestrator.sources.beads import BeadsSource
from superintendent.orchestrator.sources.models import TaskStatus

SAMPLE_BD_READY_JSON = json.dumps(
    [
        {
            "id": "sup-1",
            "title": "Fix login bug",
            "description": "The login page crashes on submit",
            "status": "open",
            "priority": 1,
            "issue_type": "task",
            "owner": "user@example.com",
            "labels": ["phase:auth", "priority:P0"],
            "dependencies": [],
            "dependency_count": 0,
        },
        {
            "id": "sup-2",
            "title": "Add dark mode",
            "description": "Implement dark mode toggle",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "owner": "",
            "labels": ["phase:ui"],
            "dependencies": [
                {
                    "issue_id": "sup-2",
                    "depends_on_id": "sup-1",
                    "type": "blocks",
                }
            ],
            "dependency_count": 1,
        },
    ]
)

SAMPLE_BD_LIST_JSON = json.dumps(
    [
        {
            "id": "sup-1",
            "title": "Fix login bug",
            "description": "The login page crashes on submit",
            "status": "closed",
            "priority": 1,
            "issue_type": "task",
            "owner": "user@example.com",
            "labels": ["phase:auth"],
            "dependencies": [],
            "dependency_count": 0,
        },
        {
            "id": "sup-2",
            "title": "Add dark mode",
            "description": "Implement dark mode toggle",
            "status": "open",
            "priority": 2,
            "issue_type": "task",
            "owner": "",
            "labels": ["phase:ui"],
            "dependencies": [
                {
                    "issue_id": "sup-2",
                    "depends_on_id": "sup-1",
                    "type": "blocks",
                }
            ],
            "dependency_count": 1,
        },
        {
            "id": "sup-3",
            "title": "Write tests",
            "description": "Add unit tests",
            "status": "open",
            "priority": 1,
            "issue_type": "task",
            "owner": "",
            "labels": [],
            "dependencies": [],
            "dependency_count": 0,
        },
    ]
)


def _make_result(returncode: int = 0, stdout: str = "", stderr: str = ""):
    return type(
        "Result", (), {"returncode": returncode, "stdout": stdout, "stderr": stderr}
    )()


class TestBeadsSourceGetTasks:
    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_parses_tasks_from_bd_list(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        assert len(tasks) == 3

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_maps_task_fields(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        t1 = tasks[0]
        assert t1.task_id == "sup-1"
        assert t1.title == "Fix login bug"
        assert t1.description == "The login page crashes on submit"
        assert t1.source_ref == "sup-1"

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_maps_status_closed_to_completed(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        assert tasks[0].status == TaskStatus.completed  # "closed" → completed

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_maps_status_open_to_pending(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        assert tasks[1].status == TaskStatus.pending  # "open" → pending

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_maps_dependencies(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        t2 = tasks[1]
        assert t2.dependencies == ["sup-1"]

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_maps_labels(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_LIST_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        t1 = tasks[0]
        assert t1.labels == {"phase": "auth"}

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_empty_result(self, mock_run):
        mock_run.return_value = type(
            "Result", (), {"returncode": 0, "stdout": "[]", "stderr": ""}
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        assert tasks == []

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_bd_failure_returns_empty(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 1, "stdout": "", "stderr": "bd not found"},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        tasks = source.get_tasks()
        assert tasks == []


class TestBeadsSourceGetReadyTasks:
    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_uses_bd_ready(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 0, "stdout": SAMPLE_BD_READY_JSON, "stderr": ""},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        ready = source.get_ready_tasks()
        assert len(ready) == 2
        # Verify bd ready was called (not bd list)
        cmd = mock_run.call_args[0][0]
        assert "ready" in cmd

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_bd_ready_failure_returns_empty(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 1, "stdout": "", "stderr": "error"},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        ready = source.get_ready_tasks()
        assert ready == []


class TestBeadsSourceUpdateStatus:
    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_completed_calls_bd_close(self, mock_run):
        mock_run.return_value = _make_result()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        source.update_status("sup-1", TaskStatus.completed)
        cmd = mock_run.call_args[0][0]
        assert "close" in cmd
        assert "sup-1" in cmd

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_in_progress_calls_bd_update(self, mock_run):
        mock_run.return_value = _make_result()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        source.update_status("sup-1", TaskStatus.in_progress)
        cmd = mock_run.call_args[0][0]
        assert "update" in cmd
        assert "sup-1" in cmd


class TestBeadsSourceClaim:
    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_claim_calls_bd_update_claim(self, mock_run):
        mock_run.return_value = type(
            "Result", (), {"returncode": 0, "stdout": "", "stderr": ""}
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        result = source.claim_task("sup-1")
        assert result is True
        cmd = mock_run.call_args[0][0]
        assert "update" in cmd
        assert "--claim" in cmd
        assert "sup-1" in cmd

    @patch("superintendent.orchestrator.sources.beads.subprocess.run")
    def test_claim_failure_returns_false(self, mock_run):
        mock_run.return_value = type(
            "Result",
            (),
            {"returncode": 1, "stdout": "", "stderr": "already claimed"},
        )()
        source = BeadsSource(repo_root=Path("/fake/repo"))
        result = source.claim_task("sup-1")
        assert result is False
