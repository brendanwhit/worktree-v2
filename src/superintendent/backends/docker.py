"""DockerBackend protocol and implementations (Real, Mock, DryRun)."""

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from superintendent.backends.terminal import detect_terminal


@runtime_checkable
class DockerBackend(Protocol):
    """Protocol for Docker sandbox and container operations."""

    # -- Sandbox operations (docker sandbox) ----------------------------------

    def sandbox_exists(self, name: str) -> bool:
        """Check if a named sandbox exists (running or stopped)."""
        ...

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        """Create a sandbox with the workspace mounted at /workspace."""
        ...

    def start_sandbox(self, name: str) -> bool:
        """Start an existing stopped sandbox."""
        ...

    def stop_sandbox(self, name: str) -> bool:
        """Stop a running sandbox."""
        ...

    def remove_sandbox(self, name: str) -> bool:
        """Remove a sandbox (must be stopped first, or handles both)."""
        ...

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        """Run a shell command inside a sandbox. Returns (exit_code, output)."""
        ...

    def run_agent(
        self, name: str, prompt: str, autonomous: bool = False, cwd: Path | None = None
    ) -> bool:
        """Launch a Claude agent inside the sandbox with the given prompt."""
        ...

    def list_sandboxes(self) -> list[str]:
        """Return names of all known sandboxes."""
        ...

    # -- Template operations ---------------------------------------------------

    def build_template(self, dockerfile_content: str, tag: str) -> bool:
        """Build a Docker template image from Dockerfile content."""
        ...

    def template_exists(self, tag: str) -> bool:
        """Check if a template image exists locally."""
        ...

    # -- Container operations (docker run) ------------------------------------

    def container_exists(self, name: str) -> bool:
        """Check if a named container exists (running or stopped)."""
        ...

    def create_container(self, name: str, workspace: Path) -> bool:
        """Create an ephemeral container with the workspace mounted."""
        ...

    def stop_container(self, name: str) -> bool:
        """Force-remove a container."""
        ...


class RealDockerBackend:
    """Executes actual docker sandbox commands via subprocess."""

    def __init__(self, stream_output: bool = False) -> None:
        self._stream_output = stream_output

    def sandbox_exists(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "sandbox", "ls", "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return name in result.stdout.splitlines()

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        cmd = ["docker", "sandbox", "create"]
        if template:
            cmd.extend(["-t", template])
        cmd.extend(["--name", name, "claude", str(workspace)])
        if self._stream_output:
            result = subprocess.run(cmd, text=True)
        else:
            result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode == 0

    def start_sandbox(self, name: str) -> bool:
        # docker sandbox has no explicit "start" — use "run" to restart a stopped sandbox
        result = subprocess.run(
            ["docker", "sandbox", "run", name],
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

    def remove_sandbox(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "sandbox", "rm", name],
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

    def run_agent(
        self, name: str, prompt: str, autonomous: bool = False, cwd: Path | None = None
    ) -> bool:
        escaped_prompt = prompt.replace("'", "'\\''")
        skip = " --dangerously-skip-permissions" if autonomous else ""
        agent_cmd = f"docker sandbox run '{name}' --{skip} '{escaped_prompt}'"
        terminal = detect_terminal()
        workspace = cwd or Path.cwd()

        if not shutil.which("tmux"):
            return terminal.spawn(agent_cmd, workspace)

        # Run inside tmux so the agent survives terminal disconnects.
        # The terminal window just attaches to the tmux session — if it
        # closes or crashes, the agent keeps running and you can reattach.
        session = f"sup-{name}"
        subprocess.run(
            ["tmux", "kill-session", "-t", session],
            capture_output=True,
        )
        result = subprocess.run(
            ["tmux", "new-session", "-d", "-s", session, "sh", "-c", agent_cmd],
            capture_output=True,
        )
        if result.returncode != 0:
            # tmux failed — fall back to direct terminal spawn
            return terminal.spawn(agent_cmd, workspace)

        # Keep pane open after command exits so user can see what happened
        subprocess.run(
            ["tmux", "set-option", "-t", session, "remain-on-exit", "on"],
            capture_output=True,
        )
        return terminal.spawn(f"tmux attach -t {session}", workspace)

    def list_sandboxes(self) -> list[str]:
        result = subprocess.run(
            ["docker", "sandbox", "ls", "-q"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]

    # -- Template operations --------------------------------------------------

    def template_exists(self, tag: str) -> bool:
        result = subprocess.run(
            ["docker", "image", "inspect", tag],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def build_template(self, dockerfile_content: str, tag: str) -> bool:
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".dockerfile", delete=False
        ) as f:
            f.write(dockerfile_content)
            dockerfile_path = f.name
        try:
            build_cmd = ["docker", "build", "-t", tag, "-f", dockerfile_path, "."]
            if self._stream_output:
                result = subprocess.run(build_cmd, text=True, timeout=600)
            else:
                result = subprocess.run(
                    build_cmd, capture_output=True, text=True, timeout=600
                )
            return result.returncode == 0
        finally:
            Path(dockerfile_path).unlink(missing_ok=True)

    # -- Container operations -------------------------------------------------

    def container_exists(self, name: str) -> bool:
        result = subprocess.run(
            [
                "docker",
                "ps",
                "-a",
                "--filter",
                f"name=^{name}$",
                "--format",
                "{{.Names}}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        return name in result.stdout.splitlines()

    def create_container(self, name: str, workspace: Path) -> bool:
        result = subprocess.run(
            [
                "docker",
                "run",
                "-d",
                "--name",
                name,
                "-v",
                f"{workspace}:/workspace",
                "-w",
                "/workspace",
                "ubuntu:latest",
                "sleep",
                "infinity",
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def stop_container(self, name: str) -> bool:
        result = subprocess.run(
            ["docker", "rm", "-f", name],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


@dataclass
class MockDockerBackend:
    """Returns canned responses for testing."""

    sandboxes: dict[str, bool] = field(default_factory=dict)
    containers: dict[str, bool] = field(default_factory=dict)
    created: list[tuple[str, Path, str | None]] = field(default_factory=list)
    containers_created: list[tuple[str, Path]] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    stopped: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    containers_stopped: list[str] = field(default_factory=list)
    executed: list[tuple[str, str]] = field(default_factory=list)
    agents_run: list[tuple[str, str, bool, Path | None]] = field(default_factory=list)
    templates_built: list[tuple[str, str]] = field(default_factory=list)
    existing_templates: set[str] = field(default_factory=set)

    fail_on: str | None = None
    exec_results: dict[str, tuple[int, str]] = field(default_factory=dict)

    # -- Sandbox operations ---------------------------------------------------

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

    def remove_sandbox(self, name: str) -> bool:
        if self.fail_on == "remove_sandbox":
            return False
        self.removed.append(name)
        self.sandboxes.pop(name, None)
        return True

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        self.executed.append((name, cmd))
        if self.fail_on == "exec_in_sandbox":
            return (1, "mock failure")
        return self.exec_results.get(cmd, (0, ""))

    def run_agent(
        self,
        name: str,
        prompt: str,
        autonomous: bool = False,
        cwd: Path | None = None,
    ) -> bool:
        if self.fail_on == "run_agent":
            return False
        self.agents_run.append((name, prompt, autonomous, cwd))
        return True

    def list_sandboxes(self) -> list[str]:
        return list(self.sandboxes.keys())

    # -- Template operations --------------------------------------------------

    def template_exists(self, tag: str) -> bool:
        return tag in self.existing_templates

    def build_template(self, dockerfile_content: str, tag: str) -> bool:
        if self.fail_on == "build_template":
            return False
        self.templates_built.append((dockerfile_content, tag))
        self.existing_templates.add(tag)
        return True

    # -- Container operations -------------------------------------------------

    def container_exists(self, name: str) -> bool:
        return name in self.containers

    def create_container(self, name: str, workspace: Path) -> bool:
        if self.fail_on == "create_container":
            return False
        self.containers_created.append((name, workspace))
        self.containers[name] = True
        return True

    def stop_container(self, name: str) -> bool:
        if self.fail_on == "stop_container":
            return False
        self.containers_stopped.append(name)
        self.containers.pop(name, None)
        return True


class DryRunDockerBackend:
    """Prints commands that would be run without executing them."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def sandbox_exists(self, name: str) -> bool:
        self.commands.append(f"docker sandbox ls -q | grep -q {name}")
        return False

    def create_sandbox(
        self, name: str, workspace: Path, template: str | None = None
    ) -> bool:
        cmd = "docker sandbox create"
        if template:
            cmd += f" -t {template}"
        cmd += f" --name {name} claude {workspace}"
        self.commands.append(cmd)
        return True

    def start_sandbox(self, name: str) -> bool:
        self.commands.append(f"docker sandbox run {name}")
        return True

    def stop_sandbox(self, name: str) -> bool:
        self.commands.append(f"docker sandbox stop {name}")
        return True

    def remove_sandbox(self, name: str) -> bool:
        self.commands.append(f"docker sandbox rm {name}")
        return True

    def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
        self.commands.append(f"docker sandbox exec {name} sh -c '{cmd}'")
        return (0, "")

    def run_agent(
        self,
        name: str,
        prompt: str,  # noqa: ARG002
        autonomous: bool = False,
        cwd: Path | None = None,
    ) -> bool:
        skip = " --dangerously-skip-permissions" if autonomous else ""
        session = f"sup-{name}"
        self.commands.append(
            f"tmux new-session -d -s {session} sh -c "
            f"'docker sandbox run {name} --{skip} ...'"
        )
        self.commands.append(f"tmux set-option -t {session} remain-on-exit on")
        cmd = f"tmux attach -t {session}"
        if cwd:
            cmd += f"  # cwd={cwd}"
        self.commands.append(cmd)
        return True

    def list_sandboxes(self) -> list[str]:
        self.commands.append("docker sandbox ls -q")
        return []

    # -- Template operations --------------------------------------------------

    def template_exists(self, tag: str) -> bool:
        self.commands.append(f"docker image inspect {tag}")
        return False

    def build_template(self, dockerfile_content: str, tag: str) -> bool:  # noqa: ARG002
        self.commands.append(f"docker build -t {tag} -f <generated>.dockerfile .")
        return True

    # -- Container operations -------------------------------------------------

    def container_exists(self, name: str) -> bool:
        self.commands.append(
            f"docker ps -a --filter 'name=^{name}$' --format '{{{{.Names}}}}'"
        )
        return False

    def create_container(self, name: str, workspace: Path) -> bool:
        self.commands.append(
            f"docker run -d --name {name} -v {workspace}:/workspace "
            f"-w /workspace ubuntu:latest sleep infinity"
        )
        return True

    def stop_container(self, name: str) -> bool:
        self.commands.append(f"docker rm -f {name}")
        return True
