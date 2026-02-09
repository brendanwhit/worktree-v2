"""AuthBackend protocol and implementations (Real, Mock, DryRun)."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from backends.docker import DockerBackend


@runtime_checkable
class AuthBackend(Protocol):
    """Protocol for authentication operations inside sandboxes."""

    def setup_git_auth(self, sandbox_name: str) -> bool: ...

    def inject_token(self, sandbox_name: str, token: str) -> bool: ...

    def validate_token(self, token: str, required_scopes: list[str]) -> bool: ...

    def setup_ssh_key(self, sandbox_name: str, key_path: Path) -> bool: ...


class RealAuthBackend:
    """Executes auth commands inside Docker sandboxes via DockerBackend."""

    def __init__(self, docker: DockerBackend) -> None:
        self._docker = docker

    def setup_git_auth(self, sandbox_name: str) -> bool:
        exit_code, _ = self._docker.exec_in_sandbox(sandbox_name, "gh auth setup-git")
        return exit_code == 0

    def inject_token(self, sandbox_name: str, token: str) -> bool:
        exit_code, _ = self._docker.exec_in_sandbox(
            sandbox_name,
            f"export GH_TOKEN={token} && gh auth setup-git",
        )
        return exit_code == 0

    def validate_token(self, token: str, required_scopes: list[str]) -> bool:
        exit_code, output = self._docker.exec_in_sandbox(
            "validate", f"GH_TOKEN={token} gh auth status"
        )
        if exit_code != 0:
            return False
        return all(scope in output for scope in required_scopes)

    def setup_ssh_key(self, sandbox_name: str, key_path: Path) -> bool:
        exit_code, _ = self._docker.exec_in_sandbox(
            sandbox_name,
            f"mkdir -p ~/.ssh && cp {key_path} ~/.ssh/ && chmod 600 ~/.ssh/{key_path.name}",
        )
        return exit_code == 0


@dataclass
class MockAuthBackend:
    """Returns canned responses for testing."""

    git_auths: list[str] = field(default_factory=list)
    tokens_injected: list[tuple[str, str]] = field(default_factory=list)
    tokens_validated: list[tuple[str, list[str]]] = field(default_factory=list)
    ssh_keys: list[tuple[str, Path]] = field(default_factory=list)

    fail_on: str | None = None

    def setup_git_auth(self, sandbox_name: str) -> bool:
        if self.fail_on == "setup_git_auth":
            return False
        self.git_auths.append(sandbox_name)
        return True

    def inject_token(self, sandbox_name: str, token: str) -> bool:
        if self.fail_on == "inject_token":
            return False
        self.tokens_injected.append((sandbox_name, token))
        return True

    def validate_token(self, token: str, required_scopes: list[str]) -> bool:
        if self.fail_on == "validate_token":
            return False
        self.tokens_validated.append((token, required_scopes))
        return True

    def setup_ssh_key(self, sandbox_name: str, key_path: Path) -> bool:
        if self.fail_on == "setup_ssh_key":
            return False
        self.ssh_keys.append((sandbox_name, key_path))
        return True


class DryRunAuthBackend:
    """Prints commands that would be run without executing them."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def setup_git_auth(self, sandbox_name: str) -> bool:
        self.commands.append(
            f"docker sandbox exec {sandbox_name} sh -c 'gh auth setup-git'"
        )
        return True

    def inject_token(self, sandbox_name: str, token: str) -> bool:
        masked = token[:4] + "***" if len(token) > 4 else "***"
        self.commands.append(
            f"docker sandbox exec {sandbox_name} sh -c "
            f"'export GH_TOKEN={masked} && gh auth setup-git'"
        )
        return True

    def validate_token(self, token: str, required_scopes: list[str]) -> bool:
        masked = token[:4] + "***" if len(token) > 4 else "***"
        scopes_str = ", ".join(required_scopes)
        self.commands.append(
            f"GH_TOKEN={masked} gh auth status # verify scopes: {scopes_str}"
        )
        return True

    def setup_ssh_key(self, sandbox_name: str, key_path: Path) -> bool:
        self.commands.append(
            f"docker sandbox exec {sandbox_name} sh -c "
            f"'mkdir -p ~/.ssh && cp {key_path} ~/.ssh/ && chmod 600 ~/.ssh/{key_path.name}'"
        )
        return True
