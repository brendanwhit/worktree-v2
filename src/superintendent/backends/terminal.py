"""TerminalBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class TerminalBackend(Protocol):
    """Protocol for terminal spawn operations."""

    def spawn(self, cmd: str, workspace: Path) -> bool: ...

    def wait(self, timeout: int | None = None) -> int: ...

    def is_running(self) -> bool: ...


class RealTerminalBackend:
    """Spawns processes in a real terminal."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[str] | None = None

    def spawn(self, cmd: str, workspace: Path) -> bool:
        try:
            self._process = subprocess.Popen(
                cmd,
                shell=True,
                cwd=str(workspace),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            return True
        except OSError:
            return False

    def wait(self, timeout: int | None = None) -> int:
        if self._process is None:
            return -1
        try:
            self._process.wait(timeout=timeout)
            return self._process.returncode
        except subprocess.TimeoutExpired:
            return -1

    def is_running(self) -> bool:
        if self._process is None:
            return False
        return self._process.poll() is None


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
