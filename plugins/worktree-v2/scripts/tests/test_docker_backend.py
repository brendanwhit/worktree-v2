"""Tests for DockerBackend (Protocol, Mock, DryRun, Real integration)."""

from pathlib import Path

import pytest

from backends.docker import (
    DockerBackend,
    DryRunDockerBackend,
    MockDockerBackend,
    RealDockerBackend,
)


class TestDockerBackendProtocol:
    """Verify all implementations satisfy the DockerBackend protocol."""

    def test_real_satisfies_protocol(self):
        assert isinstance(RealDockerBackend(), DockerBackend)

    def test_mock_satisfies_protocol(self):
        assert isinstance(MockDockerBackend(), DockerBackend)

    def test_dryrun_satisfies_protocol(self):
        assert isinstance(DryRunDockerBackend(), DockerBackend)


class TestMockDockerBackend:
    """Test MockDockerBackend recording and failure injection."""

    def test_sandbox_exists_when_created(self):
        backend = MockDockerBackend(sandboxes={"test-sandbox": True})
        assert backend.sandbox_exists("test-sandbox") is True

    def test_sandbox_not_exists(self):
        backend = MockDockerBackend()
        assert backend.sandbox_exists("nonexistent") is False

    def test_create_sandbox_records_call(self):
        backend = MockDockerBackend()
        result = backend.create_sandbox("test", Path("/workspace"))
        assert result is True
        assert len(backend.created) == 1
        assert backend.created[0] == ("test", Path("/workspace"), None)
        assert backend.sandbox_exists("test") is True

    def test_create_sandbox_with_template(self):
        backend = MockDockerBackend()
        result = backend.create_sandbox("test", Path("/ws"), template="python")
        assert result is True
        assert backend.created[0] == ("test", Path("/ws"), "python")

    def test_create_sandbox_failure(self):
        backend = MockDockerBackend(fail_on="create_sandbox")
        result = backend.create_sandbox("test", Path("/ws"))
        assert result is False
        assert len(backend.created) == 0

    def test_start_sandbox_records_call(self):
        backend = MockDockerBackend()
        result = backend.start_sandbox("test")
        assert result is True
        assert backend.started == ["test"]

    def test_start_sandbox_failure(self):
        backend = MockDockerBackend(fail_on="start_sandbox")
        result = backend.start_sandbox("test")
        assert result is False

    def test_stop_sandbox_records_call(self):
        backend = MockDockerBackend(sandboxes={"test": True})
        result = backend.stop_sandbox("test")
        assert result is True
        assert backend.stopped == ["test"]
        assert backend.sandbox_exists("test") is False

    def test_stop_sandbox_failure(self):
        backend = MockDockerBackend(fail_on="stop_sandbox")
        result = backend.stop_sandbox("test")
        assert result is False

    def test_exec_in_sandbox_records_call(self):
        backend = MockDockerBackend()
        code, output = backend.exec_in_sandbox("test", "echo hello")
        assert code == 0
        assert output == ""
        assert backend.executed == [("test", "echo hello")]

    def test_exec_in_sandbox_with_custom_result(self):
        backend = MockDockerBackend(exec_results={"whoami": (0, "root\n")})
        code, output = backend.exec_in_sandbox("test", "whoami")
        assert code == 0
        assert output == "root\n"

    def test_exec_in_sandbox_failure(self):
        backend = MockDockerBackend(fail_on="exec_in_sandbox")
        code, output = backend.exec_in_sandbox("test", "cmd")
        assert code == 1
        assert output == "mock failure"

    def test_run_agent_records_call(self):
        backend = MockDockerBackend()
        result = backend.run_agent("test", Path("/ws"), "do stuff")
        assert result is True
        assert backend.agents_run == [("test", Path("/ws"), "do stuff")]

    def test_run_agent_failure(self):
        backend = MockDockerBackend(fail_on="run_agent")
        result = backend.run_agent("test", Path("/ws"), "do stuff")
        assert result is False

    def test_list_sandboxes_empty(self):
        backend = MockDockerBackend()
        assert backend.list_sandboxes() == []

    def test_list_sandboxes_with_entries(self):
        backend = MockDockerBackend(sandboxes={"a": True, "b": True})
        result = backend.list_sandboxes()
        assert sorted(result) == ["a", "b"]

    def test_create_then_list(self):
        backend = MockDockerBackend()
        backend.create_sandbox("s1", Path("/w1"))
        backend.create_sandbox("s2", Path("/w2"))
        assert sorted(backend.list_sandboxes()) == ["s1", "s2"]

    def test_create_then_stop_removes(self):
        backend = MockDockerBackend()
        backend.create_sandbox("s1", Path("/w1"))
        assert backend.sandbox_exists("s1") is True
        backend.stop_sandbox("s1")
        assert backend.sandbox_exists("s1") is False


class TestDryRunDockerBackend:
    """Test DryRunDockerBackend command recording."""

    def test_sandbox_exists_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.sandbox_exists("test")
        assert result is False
        assert len(backend.commands) == 1
        assert "test" in backend.commands[0]

    def test_create_sandbox_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.create_sandbox("test", Path("/workspace"))
        assert result is True
        assert "docker sandbox create" in backend.commands[0]
        assert "--name test" in backend.commands[0]
        assert "/workspace:/workspace" in backend.commands[0]

    def test_create_sandbox_with_template(self):
        backend = DryRunDockerBackend()
        backend.create_sandbox("test", Path("/ws"), template="python")
        assert "--template python" in backend.commands[0]

    def test_start_sandbox_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.start_sandbox("test")
        assert result is True
        assert "docker sandbox start test" in backend.commands[0]

    def test_stop_sandbox_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.stop_sandbox("test")
        assert result is True
        assert "docker sandbox stop test" in backend.commands[0]

    def test_exec_in_sandbox_records_command(self):
        backend = DryRunDockerBackend()
        code, output = backend.exec_in_sandbox("test", "echo hello")
        assert code == 0
        assert output == ""
        assert "docker sandbox exec test" in backend.commands[0]
        assert "echo hello" in backend.commands[0]

    def test_run_agent_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.run_agent("test", Path("/ws"), "implement feature")
        assert result is True
        assert "docker sandbox run" in backend.commands[0]
        assert "implement feature" in backend.commands[0]

    def test_list_sandboxes_records_command(self):
        backend = DryRunDockerBackend()
        result = backend.list_sandboxes()
        assert result == []
        assert "docker sandbox ls" in backend.commands[0]

    def test_all_operations_accumulate(self):
        backend = DryRunDockerBackend()
        backend.sandbox_exists("test")
        backend.create_sandbox("test", Path("/ws"))
        backend.start_sandbox("test")
        backend.exec_in_sandbox("test", "echo hello")
        backend.run_agent("test", Path("/ws"), "task")
        backend.stop_sandbox("test")
        backend.list_sandboxes()
        assert len(backend.commands) == 7


class TestRealDockerBackendIntegration:
    """Integration tests for RealDockerBackend using actual Docker.

    These tests require Docker to be available and are marked
    with @pytest.mark.integration for selective running.
    """

    @pytest.mark.integration
    def test_list_sandboxes_returns_list(self):
        """Verify list_sandboxes returns a list (even if empty)."""
        backend = RealDockerBackend()
        result = backend.list_sandboxes()
        assert isinstance(result, list)

    @pytest.mark.integration
    def test_sandbox_exists_for_nonexistent(self):
        """Verify sandbox_exists returns False for nonexistent sandbox."""
        backend = RealDockerBackend()
        assert backend.sandbox_exists("nonexistent-sandbox-xyz-123") is False
