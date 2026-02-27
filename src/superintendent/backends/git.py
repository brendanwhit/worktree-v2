"""GitBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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

    def clone(self, url: str, path: Path) -> bool:
        """Clone a remote repository to a local path."""
        ...

    def create_worktree(self, repo: Path, branch: str, target: Path) -> bool:
        """Create a new git worktree with a new branch."""
        ...

    def fetch(self, repo: Path) -> bool:
        """Fetch all remotes for a repository."""
        ...

    def checkout(self, repo: Path, branch: str) -> bool:
        """Check out a branch in the repository."""
        ...

    def ensure_local(self, repo: str | None) -> Path | None:
        """Resolve a repo string (path or URL) to a local Path, cloning if needed."""
        ...

    def has_merged_pr(self, repo: Path, branch: str) -> bool:
        """Check if the branch has a merged PR (via gh CLI)."""
        ...

    def is_branch_stale(self, repo: Path, branch: str, days: int = 30) -> bool:
        """Check if the branch has had no commits in the last N days."""
        ...

    def remote_branch_exists(self, repo: Path, branch: str) -> bool:
        """Check if the remote tracking branch still exists."""
        ...

    def has_uncommitted_changes(self, worktree_path: Path) -> bool:
        """Check if the worktree has uncommitted changes."""
        ...

    def has_unpushed_commits(self, repo: Path, branch: str) -> bool:
        """Check if the branch has commits not pushed to the remote."""
        ...


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

    def has_merged_pr(self, repo: Path, branch: str) -> bool:
        result = subprocess.run(
            [
                "gh",
                "pr",
                "list",
                "--head",
                branch,
                "--state",
                "merged",
                "--json",
                "number",
            ],
            capture_output=True,
            text=True,
            cwd=str(repo),
        )
        if result.returncode != 0:
            return False
        try:
            import json

            prs = json.loads(result.stdout)
            return len(prs) > 0
        except (json.JSONDecodeError, TypeError):
            return False

    def is_branch_stale(self, repo: Path, branch: str, days: int = 30) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", "-1", "--format=%aI", branch],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return False
        try:
            last_commit = datetime.fromisoformat(result.stdout.strip())
            cutoff = datetime.now(UTC) - timedelta(days=days)
            return last_commit < cutoff
        except (ValueError, TypeError):
            return False

    def remote_branch_exists(self, repo: Path, branch: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "ls-remote", "--heads", "origin", branch],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and branch in result.stdout

    def has_uncommitted_changes(self, worktree_path: Path) -> bool:
        result = subprocess.run(
            ["git", "-C", str(worktree_path), "status", "--porcelain"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and len(result.stdout.strip()) > 0

    def has_unpushed_commits(self, repo: Path, branch: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "log", f"origin/{branch}..{branch}", "--oneline"],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and len(result.stdout.strip()) > 0


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

    # Smart cleanup mock state
    merged_branches: set[str] = field(default_factory=set)
    stale_branches: set[str] = field(default_factory=set)
    remote_branches: set[str] = field(default_factory=set)
    dirty_worktrees: set[str] = field(default_factory=set)
    unpushed_branches: set[str] = field(default_factory=set)

    def has_merged_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        return branch in self.merged_branches

    def is_branch_stale(self, repo: Path, branch: str, days: int = 30) -> bool:  # noqa: ARG002
        return branch in self.stale_branches

    def remote_branch_exists(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        return branch in self.remote_branches

    def has_uncommitted_changes(self, worktree_path: Path) -> bool:
        return str(worktree_path) in self.dirty_worktrees

    def has_unpushed_commits(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        return branch in self.unpushed_branches


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

    def has_merged_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        self.commands.append(f"gh pr list --head {branch} --state merged --json number")
        return False

    def is_branch_stale(self, repo: Path, branch: str, days: int = 30) -> bool:  # noqa: ARG002
        self.commands.append(f"git -C {repo} log -1 --format=%aI {branch}")
        return False

    def remote_branch_exists(self, repo: Path, branch: str) -> bool:
        self.commands.append(f"git -C {repo} ls-remote --heads origin {branch}")
        return True

    def has_uncommitted_changes(self, worktree_path: Path) -> bool:
        self.commands.append(f"git -C {worktree_path} status --porcelain")
        return False

    def has_unpushed_commits(self, repo: Path, branch: str) -> bool:
        self.commands.append(f"git -C {repo} log origin/{branch}..{branch} --oneline")
        return False
