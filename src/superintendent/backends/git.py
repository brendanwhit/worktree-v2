"""GitBackend protocol and implementations (Real, Mock, DryRun)."""

import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, runtime_checkable

DEFAULT_STALE_DAYS = 7


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


@dataclass
class WorktreeInfo:
    """Information about a git worktree."""

    path: Path
    branch: str | None


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

    def list_worktrees(self, repo: Path) -> list["WorktreeInfo"]:
        """List all worktrees for a repository."""
        ...

    def branch_exists(self, repo: Path, branch: str) -> bool:
        """Check if a branch exists (local or remote)."""
        ...

    def create_worktree_from_existing(
        self, repo: Path, branch: str, target: Path
    ) -> bool:
        """Create a worktree from an existing branch (no -b flag)."""
        ...

    def get_branch_age_days(self, repo: Path, branch: str) -> float | None:
        """Get the age of the last commit on a branch in days.

        Returns None if the branch doesn't exist or age can't be determined.
        """
        ...

    def merge_branch(self, repo: Path, source: str) -> bool:
        """Merge source branch into the current branch.

        Returns True on success, False on failure (e.g. merge conflict).
        On conflict, the merge is automatically aborted.
        """
        ...

    def get_default_branch(self, repo: Path) -> str:
        """Get the default branch name for the remote (e.g. 'main' or 'master')."""
        ...

    def has_merged_pr(self, repo: Path, branch: str) -> bool:
        """Check if the branch has a merged PR (via gh CLI)."""
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

    def list_worktrees(self, repo: Path) -> list[WorktreeInfo]:
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        worktrees: list[WorktreeInfo] = []
        current_path: Path | None = None
        current_branch: str | None = None
        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                if current_path is not None:
                    worktrees.append(
                        WorktreeInfo(path=current_path, branch=current_branch)
                    )
                current_path = Path(line.split(" ", 1)[1])
                current_branch = None
            elif line.startswith("branch "):
                ref = line.split(" ", 1)[1]
                current_branch = ref.removeprefix("refs/heads/")
        if current_path is not None:
            worktrees.append(WorktreeInfo(path=current_path, branch=current_branch))
        return worktrees

    def branch_exists(self, repo: Path, branch: str) -> bool:
        # Check local branches
        result = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "--verify", f"refs/heads/{branch}"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True
        # Check remote branches
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "rev-parse",
                "--verify",
                f"refs/remotes/origin/{branch}",
            ],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def create_worktree_from_existing(
        self, repo: Path, branch: str, target: Path
    ) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "worktree", "add", str(target), branch],
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def get_branch_age_days(self, repo: Path, branch: str) -> float | None:
        result = subprocess.run(
            [
                "git",
                "-C",
                str(repo),
                "log",
                "-1",
                "--format=%ct",
                f"refs/heads/{branch}",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        try:
            timestamp = int(result.stdout.strip())
        except ValueError:
            return None
        commit_time = datetime.fromtimestamp(timestamp, tz=UTC)
        age = datetime.now(UTC) - commit_time
        return age.total_seconds() / 86400

    def merge_branch(self, repo: Path, source: str) -> bool:
        result = subprocess.run(
            ["git", "-C", str(repo), "merge", source, "--no-edit"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Abort the failed merge
            subprocess.run(
                ["git", "-C", str(repo), "merge", "--abort"],
                capture_output=True,
                text=True,
            )
            return False
        return True

    def get_default_branch(self, repo: Path) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo), "symbolic-ref", "refs/remotes/origin/HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            # Output is like "refs/remotes/origin/main"
            return result.stdout.strip().removeprefix("refs/remotes/origin/")
        # Fallback: check for common branch names
        for candidate in ("main", "master"):
            check = subprocess.run(
                [
                    "git",
                    "-C",
                    str(repo),
                    "rev-parse",
                    "--verify",
                    f"refs/remotes/origin/{candidate}",
                ],
                capture_output=True,
                text=True,
            )
            if check.returncode == 0:
                return candidate
        return "main"

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
    merges: list[tuple[Path, str]] = field(default_factory=list)

    fail_on: str | None = None
    local_repos: dict[str, Path] = field(default_factory=dict)
    known_worktrees: list["WorktreeInfo"] = field(default_factory=list)
    known_branches: set[str] = field(default_factory=set)
    branch_ages: dict[str, float] = field(default_factory=dict)
    default_branch: str = "main"

    # Smart cleanup mock state
    merged_branches: set[str] = field(default_factory=set)
    remote_branches: set[str] = field(default_factory=set)
    dirty_worktrees: set[str] = field(default_factory=set)
    unpushed_branches: set[str] = field(default_factory=set)

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

    def list_worktrees(self, repo: Path) -> list["WorktreeInfo"]:  # noqa: ARG002
        if self.fail_on == "list_worktrees":
            return []
        return self.known_worktrees

    def branch_exists(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        if self.fail_on == "branch_exists":
            return False
        return branch in self.known_branches

    def create_worktree_from_existing(
        self, repo: Path, branch: str, target: Path
    ) -> bool:
        if self.fail_on == "create_worktree_from_existing":
            return False
        self.worktrees.append((repo, branch, target))
        return True

    def get_branch_age_days(self, repo: Path, branch: str) -> float | None:  # noqa: ARG002
        if self.fail_on == "get_branch_age_days":
            return None
        return self.branch_ages.get(branch)

    def merge_branch(self, repo: Path, source: str) -> bool:
        if self.fail_on == "merge_branch":
            return False
        self.merges.append((repo, source))
        return True

    def get_default_branch(self, repo: Path) -> str:  # noqa: ARG002
        return self.default_branch

    def has_merged_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        return branch in self.merged_branches

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

    def list_worktrees(self, repo: Path) -> list[WorktreeInfo]:
        self.commands.append(f"git -C {repo} worktree list --porcelain")
        return []

    def branch_exists(self, repo: Path, branch: str) -> bool:
        self.commands.append(f"git -C {repo} rev-parse --verify refs/heads/{branch}")
        return True

    def create_worktree_from_existing(
        self, repo: Path, branch: str, target: Path
    ) -> bool:
        self.commands.append(f"git -C {repo} worktree add {target} {branch}")
        return True

    def get_branch_age_days(self, repo: Path, branch: str) -> float | None:
        self.commands.append(f"git -C {repo} log -1 --format=%ct refs/heads/{branch}")
        return 0.0

    def merge_branch(self, repo: Path, source: str) -> bool:
        self.commands.append(f"git -C {repo} merge {source} --no-edit")
        return True

    def get_default_branch(self, repo: Path) -> str:
        self.commands.append(f"git -C {repo} symbolic-ref refs/remotes/origin/HEAD")
        return "main"

    def has_merged_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
        self.commands.append(f"gh pr list --head {branch} --state merged --json number")
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
