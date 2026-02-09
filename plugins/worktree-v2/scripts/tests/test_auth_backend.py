"""Tests for AuthBackend (Protocol, Mock, DryRun, Real)."""

from pathlib import Path

from backends.auth import (
    AuthBackend,
    DryRunAuthBackend,
    MockAuthBackend,
    RealAuthBackend,
)
from backends.docker import MockDockerBackend


class TestAuthBackendProtocol:
    """Verify all implementations satisfy the AuthBackend protocol."""

    def test_real_satisfies_protocol(self):
        docker = MockDockerBackend()
        assert isinstance(RealAuthBackend(docker=docker), AuthBackend)

    def test_mock_satisfies_protocol(self):
        assert isinstance(MockAuthBackend(), AuthBackend)

    def test_dryrun_satisfies_protocol(self):
        assert isinstance(DryRunAuthBackend(), AuthBackend)


class TestMockAuthBackend:
    """Test MockAuthBackend recording and failure injection."""

    def test_setup_git_auth_records_call(self):
        backend = MockAuthBackend()
        result = backend.setup_git_auth("my-sandbox")
        assert result is True
        assert len(backend.git_auths) == 1
        assert backend.git_auths[0] == "my-sandbox"

    def test_setup_git_auth_failure(self):
        backend = MockAuthBackend(fail_on="setup_git_auth")
        result = backend.setup_git_auth("my-sandbox")
        assert result is False
        assert len(backend.git_auths) == 0

    def test_inject_token_records_call(self):
        backend = MockAuthBackend()
        result = backend.inject_token("my-sandbox", "ghp_abc123")
        assert result is True
        assert len(backend.tokens_injected) == 1
        assert backend.tokens_injected[0] == ("my-sandbox", "ghp_abc123")

    def test_inject_token_failure(self):
        backend = MockAuthBackend(fail_on="inject_token")
        result = backend.inject_token("my-sandbox", "ghp_abc123")
        assert result is False
        assert len(backend.tokens_injected) == 0

    def test_validate_token_records_call(self):
        backend = MockAuthBackend()
        result = backend.validate_token("ghp_abc123", ["repo", "workflow"])
        assert result is True
        assert len(backend.tokens_validated) == 1
        assert backend.tokens_validated[0] == ("ghp_abc123", ["repo", "workflow"])

    def test_validate_token_failure(self):
        backend = MockAuthBackend(fail_on="validate_token")
        result = backend.validate_token("ghp_abc123", ["repo"])
        assert result is False
        assert len(backend.tokens_validated) == 0

    def test_setup_ssh_key_records_call(self):
        backend = MockAuthBackend()
        result = backend.setup_ssh_key("my-sandbox", Path("/keys/id_rsa"))
        assert result is True
        assert len(backend.ssh_keys) == 1
        assert backend.ssh_keys[0] == ("my-sandbox", Path("/keys/id_rsa"))

    def test_setup_ssh_key_failure(self):
        backend = MockAuthBackend(fail_on="setup_ssh_key")
        result = backend.setup_ssh_key("my-sandbox", Path("/keys/id_rsa"))
        assert result is False
        assert len(backend.ssh_keys) == 0

    def test_multiple_operations_recorded(self):
        backend = MockAuthBackend()
        backend.setup_git_auth("sandbox-1")
        backend.inject_token("sandbox-1", "token1")
        backend.validate_token("token1", ["repo"])
        backend.setup_ssh_key("sandbox-1", Path("/keys/id"))
        assert len(backend.git_auths) == 1
        assert len(backend.tokens_injected) == 1
        assert len(backend.tokens_validated) == 1
        assert len(backend.ssh_keys) == 1


class TestDryRunAuthBackend:
    """Test DryRunAuthBackend command recording."""

    def test_setup_git_auth_records_command(self):
        backend = DryRunAuthBackend()
        result = backend.setup_git_auth("my-sandbox")
        assert result is True
        assert len(backend.commands) == 1
        assert "my-sandbox" in backend.commands[0]
        assert "gh auth setup-git" in backend.commands[0]

    def test_inject_token_records_command(self):
        backend = DryRunAuthBackend()
        result = backend.inject_token("my-sandbox", "ghp_abc123")
        assert result is True
        assert len(backend.commands) == 1
        assert "my-sandbox" in backend.commands[0]
        assert "GH_TOKEN" in backend.commands[0]
        assert "ghp_***" in backend.commands[0]

    def test_validate_token_records_command(self):
        backend = DryRunAuthBackend()
        result = backend.validate_token("ghp_abc123", ["repo", "workflow"])
        assert result is True
        assert len(backend.commands) == 1
        assert "repo" in backend.commands[0]
        assert "workflow" in backend.commands[0]
        assert "ghp_***" in backend.commands[0]

    def test_setup_ssh_key_records_command(self):
        backend = DryRunAuthBackend()
        result = backend.setup_ssh_key("my-sandbox", Path("/keys/id_rsa"))
        assert result is True
        assert len(backend.commands) == 1
        assert "my-sandbox" in backend.commands[0]
        assert "/keys/id_rsa" in backend.commands[0]

    def test_all_operations_succeed(self):
        backend = DryRunAuthBackend()
        assert backend.setup_git_auth("sb") is True
        assert backend.inject_token("sb", "tok") is True
        assert backend.validate_token("tok", ["repo"]) is True
        assert backend.setup_ssh_key("sb", Path("/k")) is True

    def test_commands_accumulate(self):
        backend = DryRunAuthBackend()
        backend.setup_git_auth("sb")
        backend.inject_token("sb", "tok")
        backend.validate_token("tok", ["repo"])
        backend.setup_ssh_key("sb", Path("/k"))
        assert len(backend.commands) == 4


class TestRealAuthBackend:
    """Test RealAuthBackend delegates to DockerBackend."""

    def test_setup_git_auth_calls_exec(self):
        docker = MockDockerBackend()
        docker.sandboxes["my-sandbox"] = True
        backend = RealAuthBackend(docker=docker)
        result = backend.setup_git_auth("my-sandbox")
        assert result is True
        assert len(docker.executed) == 1
        assert docker.executed[0][0] == "my-sandbox"
        assert "gh auth setup-git" in docker.executed[0][1]

    def test_setup_git_auth_failure(self):
        docker = MockDockerBackend(fail_on="exec_in_sandbox")
        backend = RealAuthBackend(docker=docker)
        result = backend.setup_git_auth("my-sandbox")
        assert result is False

    def test_inject_token_calls_exec(self):
        docker = MockDockerBackend()
        backend = RealAuthBackend(docker=docker)
        result = backend.inject_token("my-sandbox", "ghp_abc123")
        assert result is True
        assert len(docker.executed) == 1
        assert docker.executed[0][0] == "my-sandbox"
        assert "GH_TOKEN" in docker.executed[0][1]
        assert "ghp_abc123" in docker.executed[0][1]

    def test_inject_token_failure(self):
        docker = MockDockerBackend(fail_on="exec_in_sandbox")
        backend = RealAuthBackend(docker=docker)
        result = backend.inject_token("my-sandbox", "ghp_abc123")
        assert result is False

    def test_validate_token_success(self):
        docker = MockDockerBackend()
        docker.exec_results["GH_TOKEN=ghp_abc123 gh auth status"] = (
            0,
            "Token scopes: repo, workflow",
        )
        backend = RealAuthBackend(docker=docker)
        result = backend.validate_token("ghp_abc123", ["repo", "workflow"])
        assert result is True

    def test_validate_token_missing_scope(self):
        docker = MockDockerBackend()
        docker.exec_results["GH_TOKEN=ghp_abc123 gh auth status"] = (
            0,
            "Token scopes: repo",
        )
        backend = RealAuthBackend(docker=docker)
        result = backend.validate_token("ghp_abc123", ["repo", "workflow"])
        assert result is False

    def test_validate_token_exec_failure(self):
        docker = MockDockerBackend(fail_on="exec_in_sandbox")
        backend = RealAuthBackend(docker=docker)
        result = backend.validate_token("ghp_abc123", ["repo"])
        assert result is False

    def test_setup_ssh_key_calls_exec(self):
        docker = MockDockerBackend()
        backend = RealAuthBackend(docker=docker)
        result = backend.setup_ssh_key("my-sandbox", Path("/keys/id_rsa"))
        assert result is True
        assert len(docker.executed) >= 1
        # Should copy key and set permissions
        cmds = [e[1] for e in docker.executed]
        assert any("/keys/id_rsa" in c for c in cmds)

    def test_setup_ssh_key_failure(self):
        docker = MockDockerBackend(fail_on="exec_in_sandbox")
        backend = RealAuthBackend(docker=docker)
        result = backend.setup_ssh_key("my-sandbox", Path("/keys/id_rsa"))
        assert result is False
