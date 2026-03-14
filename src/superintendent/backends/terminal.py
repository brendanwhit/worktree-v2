"""TerminalBackend protocol and implementations (Real, Mock, DryRun)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from superintendent.backends.docker import _spawn_terminal


@runtime_checkable
class TerminalBackend(Protocol):
    """Protocol for terminal spawn operations."""

    def spawn(self, cmd: str, workspace: Path) -> bool:
        """Spawn a process in the given workspace directory."""
        ...

    def wait(self, timeout: int | None = None) -> int:
        """Wait for the spawned process. Returns exit code, or -1 on timeout."""
        ...

    def is_running(self) -> bool:
        """Check if the spawned process is still running."""
        ...


class RealTerminalBackend:
    """Spawns a visible terminal window for interactive agent sessions."""

    def spawn(self, cmd: str, workspace: Path) -> bool:
        return _spawn_terminal(cmd, cwd=workspace)

    def wait(self, timeout: int | None = None) -> int:  # noqa: ARG002
        # Terminal windows are managed by the OS; nothing to wait on.
        return 0

    def is_running(self) -> bool:
        # Cannot track OS-managed terminal windows.
        return False


@dataclass
class MockTerminalBackend:
    """Returns canned responses for testing."""

    spawned: list[tuple[str, Path]] = field(default_factory=list)
    waited: list[int | None] = field(default_factory=list)

    fail_on: str | None = None
    exit_code: int = 0
    running: bool = False

    def spawn(self, cmd: str, workspace: Path) -> bool:
        if self.fail_on == "spawn":
            return False
        self.spawned.append((cmd, workspace))
        self.running = True
        return True

    def wait(self, timeout: int | None = None) -> int:
        self.waited.append(timeout)
        self.running = False
        if self.fail_on == "wait":
            return -1
        return self.exit_code

    def is_running(self) -> bool:
        return self.running


class DryRunTerminalBackend:
    """Prints commands that would be run without executing them."""

    def __init__(self) -> None:
        self.commands: list[str] = []
        self._running = False

    def spawn(self, cmd: str, workspace: Path) -> bool:
        self.commands.append(f"cd {workspace} && {cmd}")
        self._running = True
        return True

    def wait(self, timeout: int | None = None) -> int:
        timeout_str = f" (timeout={timeout}s)" if timeout is not None else ""
        self.commands.append(f"# wait for process{timeout_str}")
        self._running = False
        return 0

    def is_running(self) -> bool:
        return self._running
