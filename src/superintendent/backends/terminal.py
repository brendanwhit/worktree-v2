"""TerminalBackend protocol and implementations.

Real backends: WezTermBackend, ITermBackend, TerminalAppBackend
Testing backends: MockTerminalBackend, DryRunTerminalBackend
Factory: detect_terminal() picks the right backend from $TERM_PROGRAM.
"""

import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


def _escape_for_applescript(s: str) -> str:
    """Escape a string for use inside AppleScript double-quoted strings."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


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


class RealTerminalBackend(ABC):
    """Abstract base for real terminal backends with shared process-tracking."""

    def __init__(self) -> None:
        self._process: subprocess.Popen[bytes] | None = None

    @abstractmethod
    def _launch(self, cmd: str, workspace: Path) -> subprocess.Popen[bytes] | None:
        """Subclasses implement this to spawn in their specific terminal."""

    def spawn(self, cmd: str, workspace: Path) -> bool:
        self._process = self._launch(cmd, workspace)
        return self._process is not None

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


class WezTermBackend(RealTerminalBackend):
    """Spawns a new WezTerm window."""

    def _launch(self, cmd: str, workspace: Path) -> subprocess.Popen[bytes] | None:
        shell = os.environ.get("SHELL", "/bin/bash")
        spawn_args = ["wezterm", "cli", "spawn", "--new-window"]
        spawn_args.extend(["--cwd", str(workspace)])
        spawn_args.extend(["--", shell, "-lic", cmd])
        return subprocess.Popen(spawn_args)


class ITermBackend(RealTerminalBackend):
    """Spawns a new iTerm2 window via AppleScript."""

    def _launch(self, cmd: str, workspace: Path) -> subprocess.Popen[bytes] | None:  # noqa: ARG002
        escaped = _escape_for_applescript(cmd)
        script = f'''
        tell application "iTerm2"
            create window with default profile
            tell current session of current window
                write text "{escaped}"
            end tell
        end tell
        '''
        return subprocess.Popen(["osascript", "-e", script])


class TerminalAppBackend(RealTerminalBackend):
    """Spawns a new Terminal.app window via AppleScript (macOS fallback)."""

    def _launch(self, cmd: str, workspace: Path) -> subprocess.Popen[bytes] | None:  # noqa: ARG002
        escaped = _escape_for_applescript(cmd)
        script = f'''
        tell application "Terminal"
            do script "{escaped}"
            activate
        end tell
        '''
        return subprocess.Popen(["osascript", "-e", script])


def detect_terminal() -> RealTerminalBackend:
    """Pick the right terminal backend based on $TERM_PROGRAM."""
    term = os.environ.get("TERM_PROGRAM", "")
    if term == "WezTerm":
        return WezTermBackend()
    elif term == "iTerm.app":
        return ITermBackend()
    return TerminalAppBackend()


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
