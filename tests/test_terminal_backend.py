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
    detect_terminal,
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
