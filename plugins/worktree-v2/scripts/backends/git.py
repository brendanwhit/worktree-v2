"""GitBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


def _extract_repo_name(url: str) -> str:
    """Extract repo name from a URL (e.g. 'worktree-v2' from a GitHub URL)."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


@runtime_checkable
class GitBackend(Protocol):
    """Protocol for git operations."""

    def clone(self, url: str, path: Path) -> bool: ...

    def create_worktree(self, repo: Path, branch: str, target: Path) -> bool: ...

    def fetch(self, repo: Path) -> bool: ...

    def checkout(self, repo: Path, branch: str) -> bool: ...

    def ensure_local(self, repo: str | None) -> Path | None: ...


class RealGitBackend:
    """Executes actual git commands via subprocess."""

    def clone(self, url: str, path: Path) -> bool:
        result = subprocess.run(
            ["git", "clone", url, str(path)],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def create_worktree(self, repo: Path, branch: str, target: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", str(target), "-b", branch],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def fetch(self, repo: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "fetch", "--all"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def checkout(self, repo: Path, branch: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "checkout", branch],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def ensure_local(self, repo: str | None) -> Path | None:
        """Ensure repo is available locally. Clone if URL, validate if path.

        For URLs, parses out the repo name and checks if a local clone
        exists in the current working directory.
        """
        if repo is None:
            return None

        if repo.startswith(("https://", "http://", "git@")):
            repo_name = _extract_repo_name(repo)
            candidate = Path.cwd() / repo_name
            if candidate.is_dir() and (candidate / ".git").exists():
                return candidate
            return None

        path = Path(repo)
        if path.is_dir() and (path / ".git").exists():
            return path
        return None


@dataclass
class MockGitBackend:
    """Returns canned responses for testing."""

    cloned: list[tuple[str, Path]] = field(default_factory=list)
    worktrees: list[tuple[Path, str, Path]] = field(default_factory=list)
    fetched: list[Path] = field(default_factory=list)
    checkouts: list[tuple[Path, str]] = field(default_factory=list)

    fail_on: str | None = None
    local_repos: dict[str, Path] = field(default_factory=dict)

    def clone(self, url: str, path: Path) -> bool:
        if self.fail_on == "clone":
            return False
        self.cloned.append((url, path))
        return True

    def create_worktree(self, repo: Path, branch: str, target: Path) -> bool:
        if self.fail_on == "create_worktree":
            return False
        self.worktrees.append((repo, branch, target))
        return True

    def fetch(self, repo: Path) -> bool:
        if self.fail_on == "fetch":
            return False
        self.fetched.append(repo)
        return True

    def checkout(self, repo: Path, branch: str) -> bool:
        if self.fail_on == "checkout":
            return False
        self.checkouts.append((repo, branch))
        return True

    def ensure_local(self, repo: str | None) -> Path | None:
        if repo is None:
            return None
        if self.fail_on == "ensure_local":
            return None
        return self.local_repos.get(repo)


class DryRunGitBackend:
    """Prints commands that would be run without executing them."""

    def __init__(self) -> None:
        self.commands: list[str] = []

    def clone(self, url: str, path: Path) -> bool:
        self.commands.append(f"git clone {url} {path}")
        return True

    def create_worktree(self, repo: Path, branch: str, target: Path) -> bool:
        self.commands.append(f"git -C {repo} worktree add {target} -b {branch}")
        return True

    def fetch(self, repo: Path) -> bool:
        self.commands.append(f"git -C {repo} fetch --all")
        return True

    def checkout(self, repo: Path, branch: str) -> bool:
        self.commands.append(f"git -C {repo} checkout {branch}")
        return True

    def ensure_local(self, repo: str | None) -> Path | None:
        if repo is None:
            return None
        self.commands.append(f"# ensure_local: validate {repo}")
        return Path(repo)
