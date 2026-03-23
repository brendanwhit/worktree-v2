"""Tests for check_agent_status helper and `superintendent status` CLI command."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from superintendent.cli.main import (
    _format_duration,
    _format_status_line,
    app,
    check_agent_status,
)
from superintendent.state.registry import WorktreeEntry

runner = CliRunner()


class TestFormatDuration:
    def test_seconds(self):
        assert _format_duration(45) == "45s"

    def test_minutes(self):
        assert _format_duration(300) == "5m"

    def test_hours_and_minutes(self):
        assert _format_duration(5400) == "1h 30m"

    def test_exact_hours(self):
        assert _format_duration(7200) == "2h"


class TestCheckAgentStatus:
    def _make_entry(self, tmp_path: Path) -> WorktreeEntry:
        return WorktreeEntry(
            name="test-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
            sandbox_name="claude-test",
        )

    def test_not_started_no_ralph_dir(self, tmp_path: Path):
        entry = self._make_entry(tmp_path)
        status, details = check_agent_status(entry)
        assert status == "not_started"
        assert details == {}

    def test_not_started_no_marker(self, tmp_path: Path):
        (tmp_path / ".ralph").mkdir()
        entry = self._make_entry(tmp_path)
        status, details = check_agent_status(entry)
        assert status == "not_started"
        assert details == {}

    def test_completed_exit_zero(self, tmp_path: Path):
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")
        (ralph / "agent-done").write_text("2026-03-23T10:45:00Z\n")
        (ralph / "agent-exit-code").write_text("0\n")

        entry = self._make_entry(tmp_path)
        status, details = check_agent_status(entry)
        assert status == "completed"
        assert details["exit_code"] == "0"
        assert details["duration"] == "45m"
        assert details["start_time"] == "2026-03-23T10:00:00Z"
        assert details["end_time"] == "2026-03-23T10:45:00Z"

    def test_failed_nonzero_exit(self, tmp_path: Path):
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")
        (ralph / "agent-done").write_text("2026-03-23T10:03:00Z\n")
        (ralph / "agent-exit-code").write_text("1\n")

        entry = self._make_entry(tmp_path)
        status, details = check_agent_status(entry)
        assert status == "failed"
        assert details["exit_code"] == "1"
        assert details["duration"] == "3m"

    def test_running_started_but_not_done(self, tmp_path: Path):
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")

        entry = self._make_entry(tmp_path)
        status, details = check_agent_status(entry)
        assert status == "running"
        assert "start_time" in details


class TestFormatStatusLine:
    def test_not_started(self):
        line = _format_status_line("my-entry", "not_started", {})
        assert "my-entry" in line
        assert "not_started" in line

    def test_completed_with_details(self):
        details = {
            "exit_code": "0",
            "duration": "45m",
            "end_time": "2026-03-23T10:45:00Z",
        }
        line = _format_status_line("my-entry", "completed", details)
        assert "exit 0" in line
        assert "ran 45m" in line

    def test_failed_with_details(self):
        details = {
            "exit_code": "1",
            "duration": "3m",
            "end_time": "2026-03-23T10:03:00Z",
        }
        line = _format_status_line("my-entry", "failed", details)
        assert "exit 1" in line
        assert "ran 3m" in line

    def test_running_with_details(self):
        details = {"start_time": "2026-03-23T10:00:00Z"}
        line = _format_status_line("my-entry", "running", details)
        assert "started" in line


class TestStatusCommand:
    def _registry_data(self, entries: list[WorktreeEntry]) -> dict:
        """Build registry JSON data."""
        return {"entries": [e.to_dict() for e in entries]}

    @patch("superintendent.cli.main.get_default_registry")
    def test_no_entries(self, mock_registry):
        mock_registry.return_value.list_all.return_value = []
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "No entries found" in result.output

    @patch("superintendent.cli.main.check_agent_status")
    @patch("superintendent.cli.main.get_default_registry")
    def test_shows_completed_entry(self, mock_registry, mock_status, tmp_path: Path):
        entry = WorktreeEntry(
            name="claude-repo",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
        )
        mock_registry.return_value.list_all.return_value = [entry]
        mock_status.return_value = (
            "completed",
            {"exit_code": "0", "duration": "45m", "end_time": "2026-03-23T10:45:00Z"},
        )
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "claude-repo" in result.output
        assert "completed" in result.output

    @patch("superintendent.cli.main.get_default_registry")
    def test_nonexistent_worktree_shows_no_sandbox(self, mock_registry):
        entry = WorktreeEntry(
            name="gone-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/nonexistent/path",
        )
        mock_registry.return_value.list_all.return_value = [entry]
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "no sandbox" in result.output

    @patch("superintendent.cli.main.get_default_registry")
    def test_name_filter_not_found(self, mock_registry):
        mock_registry.return_value.list_all.return_value = [
            WorktreeEntry(
                name="other",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/wt",
            )
        ]
        result = runner.invoke(app, ["status", "--name", "nope"])
        assert result.exit_code == 1

    @patch("superintendent.cli.main.check_agent_status")
    @patch("superintendent.cli.main.get_default_registry")
    def test_name_filter_matches(self, mock_registry, mock_status, tmp_path: Path):
        entry = WorktreeEntry(
            name="target",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
        )
        other = WorktreeEntry(
            name="other",
            repo="/tmp/repo2",
            branch="dev",
            worktree_path=str(tmp_path),
        )
        mock_registry.return_value.list_all.return_value = [entry, other]
        mock_status.return_value = ("running", {"start_time": "2026-03-23T10:00:00Z"})
        result = runner.invoke(app, ["status", "--name", "target"])
        assert result.exit_code == 0
        assert "target" in result.output
        # check_agent_status should only be called once (for the filtered entry)
        assert mock_status.call_count == 1
