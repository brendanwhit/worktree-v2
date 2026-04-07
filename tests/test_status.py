"""Tests for check_agent_status helper and `superintendent status` CLI command."""

import subprocess
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from superintendent.cli.main import (
    _format_duration,
    _format_status_line,
    _is_sandbox_alive,
    app,
    check_agent_status,
)
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry

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
        with patch("superintendent.cli.main._is_sandbox_alive", return_value=True):
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
    def test_nonexistent_worktree_shows_worktree_missing(self, mock_registry):
        entry = WorktreeEntry(
            name="gone-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/nonexistent/path",
        )
        mock_registry.return_value.list_all.return_value = [entry]
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "worktree missing" in result.output

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

    @patch("superintendent.cli.main.get_default_registry")
    def test_nonexistent_worktree_sandbox_shows_worktree_removed(self, mock_registry):
        entry = WorktreeEntry(
            name="gone-sandbox",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/nonexistent/path",
            sandbox_name="claude-repo",
        )
        mock_registry.return_value.list_all.return_value = [entry]
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "worktree removed" in result.output

    @patch("superintendent.cli.main.get_default_registry")
    def test_nonexistent_worktree_local_shows_worktree_missing(self, mock_registry):
        entry = WorktreeEntry(
            name="gone-local",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/nonexistent/path",
        )
        mock_registry.return_value.list_all.return_value = [entry]
        result = runner.invoke(app, ["status"])
        assert result.exit_code == 0
        assert "worktree missing" in result.output


class TestIsSandboxAlive:
    def test_sandbox_alive(self, monkeypatch):
        def mock_run(*args, **_kwargs):
            result = subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="claude-repo\nother-sandbox\n"
            )
            return result

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert _is_sandbox_alive("claude-repo") is True

    def test_sandbox_not_alive(self, monkeypatch):
        def mock_run(*args, **_kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=0, stdout="other-sandbox\n"
            )

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert _is_sandbox_alive("claude-repo") is False

    def test_sandbox_check_docker_error(self, monkeypatch):
        def mock_run(*args, **_kwargs):
            return subprocess.CompletedProcess(
                args=args[0], returncode=1, stdout="", stderr="error"
            )

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert _is_sandbox_alive("claude-repo") is False

    def test_sandbox_alive_empty_output(self, monkeypatch):
        def mock_run(*args, **_kwargs):
            return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="")

        monkeypatch.setattr(subprocess, "run", mock_run)
        assert _is_sandbox_alive("claude-repo") is False


class TestCheckAgentStatusWithLiveness:
    def test_running_but_sandbox_gone(self, tmp_path: Path):
        """When markers say running but sandbox is gone, return sandbox_stopped."""
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")

        entry = WorktreeEntry(
            name="test-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
            sandbox_name="claude-test",
        )
        with patch("superintendent.cli.main._is_sandbox_alive", return_value=False):
            status, details = check_agent_status(entry)

        assert status == "sandbox_stopped"
        assert "start_time" in details

    def test_running_and_sandbox_alive(self, tmp_path: Path):
        """When markers say running and sandbox is alive, return running."""
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")

        entry = WorktreeEntry(
            name="test-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
            sandbox_name="claude-test",
        )
        with patch("superintendent.cli.main._is_sandbox_alive", return_value=True):
            status, details = check_agent_status(entry)

        assert status == "running"
        assert "start_time" in details

    def test_running_local_no_liveness_check(self, tmp_path: Path):
        """Local entries (no sandbox_name) skip liveness check."""
        ralph = tmp_path / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")

        entry = WorktreeEntry(
            name="test-entry",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(tmp_path),
        )
        # No mock needed — _is_sandbox_alive should not be called
        status, details = check_agent_status(entry)
        assert status == "running"


class TestFormatStatusLineSandboxStopped:
    def test_sandbox_stopped_with_start_time(self):
        details = {"start_time": "2026-03-23T10:00:00Z"}
        line = _format_status_line("my-entry", "sandbox_stopped", details)
        assert "sandbox_stopped" in line
        assert "started" in line

    def test_sandbox_stopped_no_details(self):
        line = _format_status_line("my-entry", "sandbox_stopped", {})
        assert "sandbox_stopped" in line


class TestRoundTrip:
    def test_register_then_list(self, tmp_path: Path):
        """Write an entry to registry, then read it back."""
        registry = WorktreeRegistry(tmp_path / "registry.json")
        entry = WorktreeEntry(
            name="test-agent",
            repo="/tmp/repo",
            branch="agent/repo",
            worktree_path=str(tmp_path / "worktree"),
            sandbox_name="claude-repo",
        )
        registry.add(entry)

        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].name == "test-agent"
        assert entries[0].repo == "/tmp/repo"
        assert entries[0].branch == "agent/repo"
        assert entries[0].sandbox_name == "claude-repo"

    def test_register_then_check_status_local(self, tmp_path: Path):
        """Register an entry with markers, then check status."""
        worktree_dir = tmp_path / "worktree"
        worktree_dir.mkdir()
        ralph = worktree_dir / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")
        (ralph / "agent-done").write_text("2026-03-23T10:30:00Z\n")
        (ralph / "agent-exit-code").write_text("0\n")

        registry = WorktreeRegistry(tmp_path / "registry.json")
        entry = WorktreeEntry(
            name="local-agent",
            repo="/tmp/repo",
            branch="agent/repo",
            worktree_path=str(worktree_dir),
        )
        registry.add(entry)

        entries = registry.list_all()
        status, details = check_agent_status(entries[0])
        assert status == "completed"
        assert details["exit_code"] == "0"
        assert details["duration"] == "30m"

    def test_register_then_check_status_running_sandbox(self, tmp_path: Path):
        """Register a sandbox entry with only started marker, check liveness."""
        worktree_dir = tmp_path / "worktree"
        worktree_dir.mkdir()
        ralph = worktree_dir / ".ralph"
        ralph.mkdir()
        (ralph / "agent-started").write_text("2026-03-23T10:00:00Z\n")

        registry = WorktreeRegistry(tmp_path / "registry.json")
        entry = WorktreeEntry(
            name="sandbox-agent",
            repo="/tmp/repo",
            branch="agent/repo",
            worktree_path=str(worktree_dir),
            sandbox_name="claude-repo",
        )
        registry.add(entry)

        entries = registry.list_all()
        with patch("superintendent.cli.main._is_sandbox_alive", return_value=False):
            status, details = check_agent_status(entries[0])
        assert status == "sandbox_stopped"
        assert "start_time" in details
