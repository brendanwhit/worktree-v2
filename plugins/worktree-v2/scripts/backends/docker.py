"""DockerBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class DockerBackend(Protocol):
    """Protocol for Docker sandbox operations."""

    def sandbox_exists(self, name: str) -> bool: ...

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool: ...

    def start_sandbox(self, name: str) -> bool: ...

    def stop_sandbox(self, name: str) -> bool: ...

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]: ...

    def run_agent(self, name: str, workspace: Path, prompt: str) -> bool: ...

    def list_sandboxes(self) -> list[str]: ...


class RealDockerBackend:
    """Executes actual docker sandbox commands via subprocess."""

    def sandbox_exists(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "sandbox", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return name in result.stdout.splitlines()

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        cmd = [
            "docker",
            "sandbox",
            "create",
            "--name",
            name,
            "-v",
            f"{workspace}:/workspace",
        ]
        if template:
            cmd.extend(["--template", template])
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    def start_sandbox(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "sandbox", "start", name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def stop_sandbox(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "sandbox", "stop", name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        result = subprocess.run(
            ["docker", "sandbox", "exec", name, "sh", "-c", cmd],
            capture_output=True,
            text=True,
        )
        output = result.stdout
        if result.stderr:
            output += result.stderr
        return (result.returncode, output)

    def run_agent(self, name: str, workspace: Path, prompt: str) -> bool:
        result = subprocess.run(
            [
                "docker",
                "sandbox",
                "run",
                "--name",
                name,
                "-v",
                f"{workspace}:/workspace",
                "--",
                "claude",
                "--prompt",
                prompt,
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def list_sandboxes(self) -> list[str]:
        result = subprocess.run(
            ["docker", "sandbox", "ls", "--format", "{{.Name}}"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]


@dataclass
class MockDockerBackend:
    """Returns canned responses for testing."""

    sandboxes: dict[str, bool] = field(default_factory=dict)
    created: list[tuple[str, Path, str | None]] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    executed: list[tuple[str, str]] = field(default_factory=list)
    agents_run: list[tuple[str, Path, str]] = field(default_factory=list)

    fail_on: str | None = None
    exec_results: dict[str, tuple[int, str]] = field(default_factory=dict)

    def sandbox_exists(self, name: str) -> bool:
        return name in self.sandboxes

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        if self.fail_on == "create_sandbox":
            return False
        self.created.append((name, workspace, template))
        self.sandboxes[name] = True
        return True

    def start_sandbox(self, name: str) -> bool:
        if self.fail_on == "start_sandbox":
            return False
        self.started.append(name)
        return True

    def stop_sandbox(self, name: str) -> bool:
        if self.fail_on == "stop_sandbox":
            return False
        self.stopped.append(name)
        self.sandboxes.pop(name, None)
        return True

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        self.executed.append((name, cmd))
        if self.fail_on == "exec_in_sandbox":
            return (1, "mock failure")
        return self.exec_results.get(cmd, (0, ""))

    def run_agent(self, name: str, workspace: Path, prompt: str) -> bool:
        if self.fail_on == "run_agent":
            return False
        self.agents_run.append((name, workspace, prompt))
        return True

    def list_sandboxes(self) -> list[str]:
        return list(self.sandboxes.keys())


class DryRunDockerBackend:
    """Prints commands that would be run without executing them."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def sandbox_exists(self, name: str) -> bool:
        self.commands.append(
            f"docker sandbox ls --format '{{{{.Name}}}}' | grep -q {name}"
        )
        return False

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        cmd = f"docker sandbox create --name {name} -v {workspace}:/workspace"
        if template:
            cmd += f" --template {template}"
        self.commands.append(cmd)
        return True

    def start_sandbox(self, name: str) -> bool:
        self.commands.append(f"docker sandbox start {name}")
        return True

    def stop_sandbox(self, name: str) -> bool:
        self.commands.append(f"docker sandbox stop {name}")
        return True

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        self.commands.append(f"docker sandbox exec {name} sh -c '{cmd}'")
        return (0, "")

    def run_agent(self, name: str, workspace: Path, prompt: str) -> bool:
        self.commands.append(
            f"docker sandbox run --name {name} -v {workspace}:/workspace "
            f"-- claude --prompt '{prompt}'"
        )
        return True

    def list_sandboxes(self) -> list[str]:
        self.commands.append("docker sandbox ls --format '{{.Name}}'")
        return []
