"""Tests for BackendFactory and dependency injection."""

from backends.auth import (
    DryRunAuthBackend,
    MockAuthBackend,
    RealAuthBackend,
)
from backends.docker import (
    DryRunDockerBackend,
    MockDockerBackend,
    RealDockerBackend,
)
from backends.factory import BackendMode, Backends, create_backends
from backends.git import DryRunGitBackend, MockGitBackend, RealGitBackend
from backends.terminal import (
    DryRunTerminalBackend,
    MockTerminalBackend,
    RealTerminalBackend,
)


class TestBackendMode:
    """Test BackendMode enum."""

    def test_all_modes_exist(self):
        assert BackendMode.REAL is not None
        assert BackendMode.MOCK is not None
        assert BackendMode.DRYRUN is not None

    def test_mode_count(self):
        assert len(BackendMode) == 3


class TestCreateBackends:
    """Test create_backends factory function."""

    def test_real_mode_creates_real_backends(self):
        backends = create_backends(BackendMode.REAL)
        assert isinstance(backends.docker, RealDockerBackend)
        assert isinstance(backends.git, RealGitBackend)
        assert isinstance(backends.terminal, RealTerminalBackend)
        assert isinstance(backends.auth, RealAuthBackend)

    def test_mock_mode_creates_mock_backends(self):
        backends = create_backends(BackendMode.MOCK)
        assert isinstance(backends.docker, MockDockerBackend)
        assert isinstance(backends.git, MockGitBackend)
        assert isinstance(backends.terminal, MockTerminalBackend)
        assert isinstance(backends.auth, MockAuthBackend)

    def test_dryrun_mode_creates_dryrun_backends(self):
        backends = create_backends(BackendMode.DRYRUN)
        assert isinstance(backends.docker, DryRunDockerBackend)
        assert isinstance(backends.git, DryRunGitBackend)
        assert isinstance(backends.terminal, DryRunTerminalBackend)
        assert isinstance(backends.auth, DryRunAuthBackend)


class TestBackends:
    """Test Backends container."""

    def test_backends_hold_all_types(self):
        backends = create_backends(BackendMode.MOCK)
        assert hasattr(backends, "docker")
        assert hasattr(backends, "git")
        assert hasattr(backends, "terminal")
        assert hasattr(backends, "auth")

    def test_backends_are_independent(self):
        b1 = create_backends(BackendMode.MOCK)
        b2 = create_backends(BackendMode.MOCK)
        assert b1.docker is not b2.docker
        assert b1.git is not b2.git
        assert b1.terminal is not b2.terminal
        assert b1.auth is not b2.auth

    def test_custom_backends(self):
        """Backends can be constructed with custom instances."""
        docker = MockDockerBackend()
        git = MockGitBackend()
        terminal = MockTerminalBackend()
        auth = MockAuthBackend()
        backends = Backends(docker=docker, git=git, terminal=terminal, auth=auth)
        assert backends.docker is docker
        assert backends.git is git
        assert backends.terminal is terminal
        assert backends.auth is auth

    def test_mixed_backends(self):
        """Backends can mix real and mock implementations."""
        backends = Backends(
            docker=MockDockerBackend(),
            git=RealGitBackend(),
            terminal=DryRunTerminalBackend(),
            auth=MockAuthBackend(),
        )
        assert isinstance(backends.docker, MockDockerBackend)
        assert isinstance(backends.git, RealGitBackend)
        assert isinstance(backends.terminal, DryRunTerminalBackend)
        assert isinstance(backends.auth, MockAuthBackend)
