"""Backend factory for constructing backends based on execution mode."""

from dataclasses import dataclass
from enum import Enum, auto

from backends.docker import (
    DockerBackend,
    DryRunDockerBackend,
    MockDockerBackend,
    RealDockerBackend,
)
from backends.git import (
    DryRunGitBackend,
    GitBackend,
    MockGitBackend,
    RealGitBackend,
)
from backends.terminal import (
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


def create_backends(mode: BackendMode) -> Backends:
    """Create all backends for the given execution mode."""
    if mode == BackendMode.REAL:
        return Backends(
            docker=RealDockerBackend(),
            git=RealGitBackend(),
            terminal=RealTerminalBackend(),
        )
    elif mode == BackendMode.MOCK:
        return Backends(
            docker=MockDockerBackend(),
            git=MockGitBackend(),
            terminal=MockTerminalBackend(),
        )
    elif mode == BackendMode.DRYRUN:
        return Backends(
            docker=DryRunDockerBackend(),
            git=DryRunGitBackend(),
            terminal=DryRunTerminalBackend(),
        )
    else:
        raise ValueError(f"Unknown backend mode: {mode}")
