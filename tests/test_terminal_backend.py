"""Tests for TerminalBackend (Protocol, Mock, DryRun, Real per-terminal backends)."""

import subprocess
from pathlib import Path

from superintendent.backends.terminal import (
    DryRunTerminalBackend,
    ITermBackend,
    MockTerminalBackend,
    TerminalAppBackend,
    TerminalBackend,
    WezTermBackend,
    build_agent_command,
    detect_terminal,
    wrap_with_lifecycle,
)


class TestTerminalBackendProtocol:
    """Verify all implementations satisfy the TerminalBackend protocol."""

    def test_wezterm_satisfies_protocol(self):
        assert isinstance(WezTermBackend(), TerminalBackend)

    def test_iterm_satisfies_protocol(self):
        assert isinstance(ITermBackend(), TerminalBackend)

    def test_terminal_app_satisfies_protocol(self):
        assert isinstance(TerminalAppBackend(), TerminalBackend)

    def test_mock_satisfies_protocol(self):
        assert isinstance(MockTerminalBackend(), TerminalBackend)

    def test_dryrun_satisfies_protocol(self):
        assert isinstance(DryRunTerminalBackend(), TerminalBackend)


class TestMockTerminalBackend:
    """Test MockTerminalBackend recording and failure injection."""

    def test_spawn_records_call(self):
        backend = MockTerminalBackend()
        result = backend.spawn("echo hello", Path("/workspace"))
        assert result is True
        assert len(backend.spawned) == 1
        assert backend.spawned[0] == ("echo hello", Path("/workspace"))

    def test_spawn_sets_running(self):
        backend = MockTerminalBackend()
        assert backend.is_running() is False
        backend.spawn("echo hello", Path("/workspace"))
        assert backend.is_running() is True

    def test_spawn_failure(self):
        backend = MockTerminalBackend(fail_on="spawn")
        result = backend.spawn("echo hello", Path("/workspace"))
        assert result is False
        assert len(backend.spawned) == 0

    def test_wait_returns_exit_code(self):
        backend = MockTerminalBackend(exit_code=42)
        backend.spawn("cmd", Path("/ws"))
        code = backend.wait()
        assert code == 42
        assert backend.is_running() is False

    def test_wait_with_timeout(self):
        backend = MockTerminalBackend()
        backend.spawn("cmd", Path("/ws"))
        code = backend.wait(timeout=30)
        assert code == 0
        assert backend.waited == [30]

    def test_wait_failure(self):
        backend = MockTerminalBackend(fail_on="wait")
        backend.spawn("cmd", Path("/ws"))
        code = backend.wait()
        assert code == -1

    def test_is_running_false_initially(self):
        backend = MockTerminalBackend()
        assert backend.is_running() is False

    def test_is_running_after_wait(self):
        backend = MockTerminalBackend()
        backend.spawn("cmd", Path("/ws"))
        assert backend.is_running() is True
        backend.wait()
        assert backend.is_running() is False


class TestDryRunTerminalBackend:
    """Test DryRunTerminalBackend command recording."""

    def test_spawn_records_command(self):
        backend = DryRunTerminalBackend()
        result = backend.spawn("claude --task test", Path("/workspace"))
        assert result is True
        assert len(backend.commands) == 1
        assert "claude --task test" in backend.commands[0]
        assert "/workspace" in backend.commands[0]

    def test_spawn_sets_running(self):
        backend = DryRunTerminalBackend()
        assert backend.is_running() is False
        backend.spawn("cmd", Path("/ws"))
        assert backend.is_running() is True

    def test_wait_records_command(self):
        backend = DryRunTerminalBackend()
        backend.spawn("cmd", Path("/ws"))
        code = backend.wait()
        assert code == 0
        assert len(backend.commands) == 2
        assert "wait" in backend.commands[1]

    def test_wait_with_timeout(self):
        backend = DryRunTerminalBackend()
        backend.spawn("cmd", Path("/ws"))
        backend.wait(timeout=60)
        assert "timeout=60s" in backend.commands[1]

    def test_wait_clears_running(self):
        backend = DryRunTerminalBackend()
        backend.spawn("cmd", Path("/ws"))
        assert backend.is_running() is True
        backend.wait()
        assert backend.is_running() is False

    def test_all_operations_succeed(self):
        backend = DryRunTerminalBackend()
        assert backend.spawn("cmd", Path("/ws")) is True
        assert backend.wait() == 0


def _fake_launch(self, cmd, workspace=None):  # noqa: ARG001
    """Return a real subprocess instead of opening a terminal window."""
    return subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )


class TestWezTermBackend:
    """Test WezTermBackend with actual processes (via patched _launch)."""

    def test_spawn_and_wait(self, tmp_path, monkeypatch):
        monkeypatch.setattr(WezTermBackend, "_launch", _fake_launch)
        backend = WezTermBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is True
        assert backend.is_running() is True
        code = backend.wait()
        assert code == 0
        assert backend.is_running() is False

    def test_spawn_failing_command(self, tmp_path, monkeypatch):
        monkeypatch.setattr(WezTermBackend, "_launch", _fake_launch)
        backend = WezTermBackend()
        result = backend.spawn("exit 1", tmp_path)
        assert result is True
        code = backend.wait()
        assert code == 1

    def test_spawn_returns_false_on_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            WezTermBackend,
            "_launch",
            lambda self, cmd, workspace=None: None,  # noqa: ARG005
        )
        backend = WezTermBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is False

    def test_is_running_before_spawn(self):
        backend = WezTermBackend()
        assert backend.is_running() is False

    def test_wait_before_spawn(self):
        backend = WezTermBackend()
        code = backend.wait()
        assert code == -1

    def test_spawn_with_timeout(self, tmp_path, monkeypatch):
        monkeypatch.setattr(WezTermBackend, "_launch", _fake_launch)
        backend = WezTermBackend()
        backend.spawn("sleep 10", tmp_path)
        code = backend.wait(timeout=0)
        assert code == -1
        assert backend.is_running() is True
        # Clean up
        backend._process.kill()  # type: ignore[union-attr]
        backend._process.wait()  # type: ignore[union-attr]


class TestITermBackend:
    """Test ITermBackend with actual processes (via patched _launch)."""

    def test_spawn_and_wait(self, tmp_path, monkeypatch):
        monkeypatch.setattr(ITermBackend, "_launch", _fake_launch)
        backend = ITermBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is True
        code = backend.wait()
        assert code == 0

    def test_is_running_before_spawn(self):
        backend = ITermBackend()
        assert backend.is_running() is False


class TestTerminalAppBackend:
    """Test TerminalAppBackend with actual processes (via patched _launch)."""

    def test_spawn_and_wait(self, tmp_path, monkeypatch):
        monkeypatch.setattr(TerminalAppBackend, "_launch", _fake_launch)
        backend = TerminalAppBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is True
        code = backend.wait()
        assert code == 0

    def test_is_running_before_spawn(self):
        backend = TerminalAppBackend()
        assert backend.is_running() is False


class TestDetectTerminal:
    """Test detect_terminal() factory picks the right backend."""

    def test_detects_wezterm(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "WezTerm")
        terminal = detect_terminal()
        assert isinstance(terminal, WezTermBackend)

    def test_detects_iterm(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
        terminal = detect_terminal()
        assert isinstance(terminal, ITermBackend)

    def test_falls_back_to_terminal_app(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "")
        terminal = detect_terminal()
        assert isinstance(terminal, TerminalAppBackend)

    def test_unknown_terminal_falls_back(self, monkeypatch):
        monkeypatch.setenv("TERM_PROGRAM", "SomeOtherTerminal")
        terminal = detect_terminal()
        assert isinstance(terminal, TerminalAppBackend)


class TestBuildAgentCommand:
    """Test build_agent_command() for both local and sandbox targets."""

    def test_local_interactive(self):
        cmd = build_agent_command("do something")
        assert "claude" in cmd
        assert "--dangerously-skip-permissions" not in cmd
        assert "do something" in cmd
        assert cmd.startswith("unset CLAUDECODE && claude")

    def test_local_autonomous(self):
        cmd = build_agent_command("do something", autonomous=True)
        assert "--dangerously-skip-permissions" in cmd
        assert "claude" in cmd

    def test_sandbox_interactive(self):
        cmd = build_agent_command("do something", sandbox_name="my-sandbox")
        assert "docker sandbox run" in cmd
        assert "'my-sandbox'" in cmd
        assert "--dangerously-skip-permissions" not in cmd

    def test_sandbox_autonomous(self):
        cmd = build_agent_command(
            "do something", sandbox_name="my-sandbox", autonomous=True
        )
        assert "docker sandbox run" in cmd
        assert "--dangerously-skip-permissions" in cmd

    def test_escapes_single_quotes(self):
        cmd = build_agent_command("it's a test")
        assert "it" in cmd
        assert "'" not in cmd or "\\'" in cmd or "'\\''".replace("\\", "") not in cmd

    def test_local_no_docker(self):
        """Local commands must not reference docker."""
        cmd = build_agent_command("task", autonomous=True)
        assert "docker" not in cmd

    def test_sandbox_no_unset(self):
        """Sandbox commands should not unset CLAUDECODE."""
        cmd = build_agent_command("task", sandbox_name="sb")
        assert "unset CLAUDECODE" not in cmd


class TestWrapWithLifecycle:
    """Test wrap_with_lifecycle() marker wrapping."""

    def test_wraps_command(self, tmp_path):
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir()
        result = wrap_with_lifecycle("my-cmd", ralph_dir)
        assert "agent-started" in result
        assert "agent-done" in result
        assert "agent-exit-code" in result
        assert "my-cmd" in result

    def test_preserves_exit_code(self, tmp_path):
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir()
        result = wrap_with_lifecycle("my-cmd", ralph_dir)
        assert "_exit=$?" in result
        assert "exit $_exit" in result

    def test_marker_order(self, tmp_path):
        """Markers must be written in order: started, cmd, exit-code, done."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir()
        result = wrap_with_lifecycle("my-cmd", ralph_dir)
        started_pos = result.index("agent-started")
        cmd_pos = result.index("my-cmd")
        exit_pos = result.index("agent-exit-code")
        done_pos = result.index("agent-done")
        assert started_pos < cmd_pos < exit_pos < done_pos
