"""GitBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


def _extract_repo_name(url: str) -> str:
    """Extract repo name from a URL (e.g. 'my-repo' from a GitHub URL)."""
    name = url.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def _is_git_repo(path: Path) -> bool:
    """Check if a path is a git repository."""
    return path.is_dir() and (path / ".git").exists()


def _find_local_clone(repo_name: str, search_paths: list[Path]) -> Path | None:
    """Search for a local git clone matching repo_name.

    Checks each search path directly (search_path/repo_name) and one level
    deeper (search_path/*/repo_name) to cover layouts like ~/projects/repo_name.
    """
    for search_path in search_paths:
        if not search_path.is_dir():
            continue

        # Direct child: search_path/repo_name
        candidate = search_path / repo_name
        if _is_git_repo(candidate):
            return candidate

        # One level deeper: search_path/*/repo_name
        try:
            for child in search_path.iterdir():
                if child.is_dir() and not child.name.startswith("."):
                    candidate = child / repo_name
                    if _is_git_repo(candidate):
                        return candidate
        except PermissionError:
            continue

    return None


def _default_search_paths() -> list[Path]:
    """Compute default search paths lazily so CWD is evaluated at call time."""
    return [Path.cwd(), Path.home()]


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

    def __init__(self, search_paths: list[Path] | None = None) -> None:
        self._search_paths = search_paths

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

        For URLs, parses out the repo name and searches CWD, home directory,
        and common subdirectories (one level deep) for an existing clone.
        """
        if repo is None:
            return None

        if repo.startswith(("https://", "http://", "git@")):
            repo_name = _extract_repo_name(repo)
            paths = self._search_paths or _default_search_paths()
            return _find_local_clone(repo_name, paths)

        path = Path(repo)
        if _is_git_repo(path):
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
