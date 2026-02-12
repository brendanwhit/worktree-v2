"""Backend factory for constructing backends based on execution mode."""

from dataclasses import dataclass
from enum import Enum, auto

from superintendent.backends.auth import (
    AuthBackend,
    DryRunAuthBackend,
    MockAuthBackend,
    RealAuthBackend,
)
from superintendent.backends.docker import (
    DockerBackend,
    DryRunDockerBackend,
    MockDockerBackend,
    RealDockerBackend,
)
from superintendent.backends.git import (
    DryRunGitBackend,
    GitBackend,
    MockGitBackend,
    RealGitBackend,
)
from superintendent.backends.terminal import (
    DryRunTerminalBackend,
    MockTerminalBackend,
    RealTerminalBackend,
    TerminalBackend,
)


class BackendMode(Enum):
    """Execution mode for backend selection."""

    REAL = auto()
    MOCK = auto()
    DRYRUN = auto()


@dataclass
class Backends:
    """Container for all backend instances."""

    docker: DockerBackend
    git: GitBackend
    terminal: TerminalBackend
    auth: AuthBackend


def create_backends(mode: BackendMode) -> Backends:
    """Create all backends for the given execution mode."""
    if mode == BackendMode.REAL:
        docker = RealDockerBackend()
        return Backends(
            docker=docker,
            git=RealGitBackend(),
            terminal=RealTerminalBackend(),
            auth=RealAuthBackend(docker=docker),
        )
    elif mode == BackendMode.MOCK:
        return Backends(
            docker=MockDockerBackend(),
            git=MockGitBackend(),
            terminal=MockTerminalBackend(),
            auth=MockAuthBackend(),
        )
    elif mode == BackendMode.DRYRUN:
        return Backends(
            docker=DryRunDockerBackend(),
            git=DryRunGitBackend(),
            terminal=DryRunTerminalBackend(),
            auth=DryRunAuthBackend(),
        )
    else:
        raise ValueError(f"Unknown backend mode: {mode}")
