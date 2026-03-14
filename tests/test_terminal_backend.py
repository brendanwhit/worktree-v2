"""Tests for TerminalBackend (Protocol, Mock, DryRun, Real)."""

from pathlib import Path

from superintendent.backends.terminal import (
    DryRunTerminalBackend,
    MockTerminalBackend,
    RealTerminalBackend,
    TerminalBackend,
)


class TestTerminalBackendProtocol:
    """Verify all implementations satisfy the TerminalBackend protocol."""

    def test_real_satisfies_protocol(self):
        assert isinstance(RealTerminalBackend(), TerminalBackend)

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


class TestRealTerminalBackend:
    """Test RealTerminalBackend delegates to _spawn_terminal."""

    def test_spawn_calls_spawn_terminal(self, tmp_path, monkeypatch):
        spawned: list[tuple[str, Path | None]] = []
        monkeypatch.setattr(
            "superintendent.backends.terminal._spawn_terminal",
            lambda cmd, cwd=None: spawned.append((cmd, cwd)) or True,
        )
        backend = RealTerminalBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is True
        assert len(spawned) == 1
        assert spawned[0] == ("echo hello", tmp_path)

    def test_spawn_returns_false_on_failure(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "superintendent.backends.terminal._spawn_terminal",
            lambda cmd, cwd=None: False,  # noqa: ARG005
        )
        backend = RealTerminalBackend()
        result = backend.spawn("echo hello", tmp_path)
        assert result is False

    def test_wait_returns_zero(self):
        backend = RealTerminalBackend()
        assert backend.wait() == 0

    def test_is_running_returns_false(self):
        backend = RealTerminalBackend()
        assert backend.is_running() is False
