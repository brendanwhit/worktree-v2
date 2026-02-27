"""Superintendent CLI for agent orchestration.

Subcommands:
    run       — Create a workspace and spawn an agent
    list      — List all active entries
    resume    — Resume an existing entry
    cleanup   — Remove stale entries
    token     — Manage scoped GitHub tokens
"""

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import typer

from superintendent.backends.factory import BackendMode, create_backends
from superintendent.backends.git import DEFAULT_STALE_DAYS, GitBackend, RealGitBackend
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry
from superintendent.state.token_store import DEFAULT_KEY, TokenStore

app = typer.Typer(name="superintendent", no_args_is_help=True)
token_app = typer.Typer(name="token", help="Manage scoped GitHub tokens.")
app.add_typer(token_app)


def get_default_registry() -> WorktreeRegistry:
    """Return the default global registry."""
    return WorktreeRegistry(Path.home() / ".claude" / "superintendent-registry.json")


def list_entries(registry: WorktreeRegistry) -> list[WorktreeEntry]:
    """List all entries from the registry."""
    return registry.list_all()


def _branch_to_slug(branch: str) -> str:
    """Convert a branch name to a filesystem-safe slug."""
    slug = branch.replace("/", "-")
    slug = re.sub(r"[^a-zA-Z0-9_\-.]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def _default_worktrees_dir() -> Path:
    """Return the default worktrees base directory."""
    return Path.home() / ".claude-worktrees"


def _extract_repo_name(repo: str) -> str:
    """Extract the repo name from a path or URL."""
    name = repo.rstrip("/").rsplit("/", 1)[-1]
    if name.endswith(".git"):
        name = name[:-4]
    return name


def resume_entry(
    name: str,
    registry: WorktreeRegistry,
) -> WorktreeEntry | None:
    """Look up an entry by name or branch and verify it still exists.

    Tries name lookup first, then falls back to branch lookup.
    Returns the entry if found and its worktree_path exists, else None.
    """
    # Try by name first
    entry = registry.get(name)
    if entry is None:
        # Fall back to branch lookup
        entry = registry.get_by_branch(name)
    if entry is None:
        return None
    if not Path(entry.worktree_path).exists():
        return None
    return entry


def auto_create_worktree(
    branch: str,
    repo: str,
    registry: WorktreeRegistry,
    git_backend: GitBackend,
) -> WorktreeEntry | None:
    """Auto-create a worktree for an existing branch.

    If the branch exists in the repo, creates a worktree at the standard
    location (~/.claude-worktrees/<repo>/<branch-slug>), registers it,
    and returns the entry. Returns None if the branch doesn't exist or
    worktree creation fails.
    """
    # Resolve repo to a local path
    repo_path = git_backend.ensure_local(repo)
    if repo_path is None:
        return None

    if not git_backend.branch_exists(repo_path, branch):
        return None

    repo_name = _extract_repo_name(repo)
    slug = _branch_to_slug(branch)
    worktree_path = _default_worktrees_dir() / repo_name / slug

    if worktree_path.exists():
        # Worktree directory already exists — just register it
        entry = WorktreeEntry(
            name=slug,
            repo=repo,
            branch=branch,
            worktree_path=str(worktree_path),
        )
        registry.add(entry)
        return entry

    if not git_backend.create_worktree_from_existing(repo_path, branch, worktree_path):
        return None

    entry = WorktreeEntry(
        name=slug,
        repo=repo,
        branch=branch,
        worktree_path=str(worktree_path),
    )
    registry.add(entry)
    return entry


def check_and_merge_stale(
    entry: WorktreeEntry,
    git_backend: GitBackend,
    stale_days: float = DEFAULT_STALE_DAYS,
) -> str | None:
    """Check if a branch is stale and merge main if so.

    Returns a status message describing what happened, or None if
    the branch is not stale.
    """
    worktree_path = Path(entry.worktree_path)
    if not worktree_path.exists():
        return None

    age = git_backend.get_branch_age_days(worktree_path, entry.branch)
    if age is None:
        return None

    if age < stale_days:
        return None

    # Branch is stale — try to merge the default branch
    age_str = f"{age:.0f}"
    if not git_backend.fetch(worktree_path):
        return f"Branch '{entry.branch}' is {age_str} days stale, but fetch failed"

    default_branch = git_backend.get_default_branch(worktree_path)
    remote_ref = f"origin/{default_branch}"

    if git_backend.merge_branch(worktree_path, remote_ref):
        return (
            f"Branch '{entry.branch}' was {age_str} days stale; "
            f"merged {default_branch} successfully"
        )
    else:
        return (
            f"Branch '{entry.branch}' is {age_str} days stale; "
            f"merge from {default_branch} had conflicts (auto-aborted)"
        )


def cleanup_by_name(
    name: str,
    registry: WorktreeRegistry,
    dry_run: bool = False,
) -> bool:
    """Remove a specific entry by name.

    Returns True if the entry was found (and removed unless dry_run).
    """
    entry = registry.get(name)
    if entry is None:
        return False
    if not dry_run:
        registry.remove(name)
    return True


def cleanup_all(
    registry: WorktreeRegistry,
    dry_run: bool = False,
) -> list[str]:
    """Remove all stale entries (worktree_path no longer exists).

    Returns list of removed entry names.
    """
    entries = registry.list_all()
    stale: list[str] = []
    for entry in entries:
        if not Path(entry.worktree_path).exists():
            stale.append(entry.name)

    if stale and not dry_run:
        registry.cleanup()

    return stale


@dataclass
class CleanupCandidate:
    """An entry that qualifies for cleanup, with reasons and warnings."""

    entry: WorktreeEntry
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    force_required: bool = False


def analyze_entry(
    entry: WorktreeEntry,
    git: GitBackend,
    stale_days: int = 30,
) -> CleanupCandidate | None:
    """Analyze an entry for cleanup eligibility.

    Returns a CleanupCandidate if the entry qualifies, else None.
    """
    candidate = CleanupCandidate(entry=entry)
    worktree_path = Path(entry.worktree_path)

    # Check cleanup qualifications
    if not worktree_path.exists():
        candidate.reasons.append("path does not exist")
    else:
        repo_path = worktree_path
        if git.has_merged_pr(repo_path, entry.branch):
            candidate.reasons.append("branch has merged PR")
        age = git.get_branch_age_days(repo_path, entry.branch)
        if age is not None and age > stale_days:
            candidate.reasons.append(
                f"branch is stale (no commits in {stale_days} days)"
            )
        if not git.remote_branch_exists(repo_path, entry.branch):
            candidate.reasons.append("remote branch no longer exists")

    if not candidate.reasons:
        return None

    # Safety checks (only if the path exists)
    if worktree_path.exists():
        if git.has_uncommitted_changes(worktree_path):
            candidate.warnings.append("has uncommitted changes")
            candidate.force_required = True
        if git.has_unpushed_commits(worktree_path, entry.branch):
            candidate.warnings.append("has unpushed commits")
            candidate.force_required = True

    return candidate


def smart_cleanup(
    registry: WorktreeRegistry,
    git: GitBackend,
    dry_run: bool = False,
    force: bool = False,
    stale_days: int = 30,
) -> list[CleanupCandidate]:
    """Analyze and optionally remove cleanup-eligible entries.

    Returns all candidates found. Only removes entries if not dry_run,
    and only removes force_required entries if force is True.
    """
    entries = registry.list_all()
    candidates: list[CleanupCandidate] = []

    for entry in entries:
        candidate = analyze_entry(entry, git, stale_days=stale_days)
        if candidate is not None:
            candidates.append(candidate)

    if not dry_run:
        for candidate in candidates:
            if candidate.force_required and not force:
                continue
            registry.remove(candidate.entry.name)

    return candidates


@app.command()
def run(
    mode: Mode = typer.Argument(
        ..., help="Interaction mode: interactive or autonomous"
    ),
    target: Target = typer.Argument(
        ..., help="Execution target: sandbox, container, or local"
    ),
    repo: str = typer.Option(..., help="Path or URL to the repository."),
    task: str = typer.Option(..., help="Task description for the agent."),
    branch: str | None = typer.Option(None, help="Git branch name for the worktree."),
    context_file: str | None = typer.Option(
        None, help="Path to a context file for the agent."
    ),
    template_dockerfile: str | None = typer.Option(  # noqa: ARG001
        None, help="Custom Dockerfile template."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show the plan without executing."
    ),
    force: bool = typer.Option(
        False, help="Force recreation of existing sandbox/worktree."
    ),
    sandbox_name: str | None = typer.Option(
        None, help="Custom name for the Docker sandbox."
    ),
    dangerously_skip_isolation: bool = typer.Option(
        False,
        "--dangerously-skip-isolation",
        help="Required for autonomous + local (no sandbox isolation).",
    ),
) -> None:
    """Create a workspace and spawn an agent."""
    if (
        mode == Mode.autonomous
        and target == Target.local
        and not dangerously_skip_isolation
    ):
        typer.echo("Error: autonomous + local requires --dangerously-skip-isolation")
        raise typer.Exit(code=1)

    planner = Planner()

    if dry_run:
        backends = create_backends(BackendMode.DRYRUN)
    else:
        backends = create_backends(BackendMode.REAL)

    context = ExecutionContext(backends=backends)
    handler = RealStepHandler(context)
    executor = Executor(handler=handler)

    planner_input = PlannerInput(
        repo=repo,
        task=task,
        mode=mode.value,
        target=target.value,
        branch=branch,
        context_file=context_file,
        sandbox_name=sandbox_name,
        force=force,
    )

    plan = planner.create_plan(planner_input)

    if dry_run:
        typer.echo("=== Dry Run: Workflow Plan ===")
        typer.echo(plan.to_json())
        return

    result = executor.run(plan)

    if hasattr(result, "state") and result.state.name == "FAILED":
        typer.echo(f"Error: {result.error}", err=True)
        if result.failed_step:
            typer.echo(f"Failed at step: {result.failed_step}", err=True)
        raise typer.Exit(code=1)


@app.command(name="list")
def list_cmd() -> None:
    """List all active entries."""
    registry = get_default_registry()
    entries = list_entries(registry)
    if not entries:
        typer.echo("No entries found.")
    else:
        for entry in entries:
            sandbox_info = (
                f" (sandbox: {entry.sandbox_name})" if entry.sandbox_name else ""
            )
            typer.echo(
                f"  {entry.name}: {entry.repo} [{entry.branch}]"
                f" {entry.worktree_path}{sandbox_info}"
            )


@app.command()
def resume(
    name: str = typer.Option(..., help="Name or branch of the entry to resume."),
    repo: str | None = typer.Option(
        None, help="Repository path/URL (enables auto-create worktree for branches)."
    ),
    no_merge: bool = typer.Option(
        False, "--no-merge", help="Skip auto-merging main into stale branches."
    ),
) -> None:
    """Resume an existing entry."""
    registry = get_default_registry()
    entry = resume_entry(name, registry)

    # Auto-create worktree if not found in registry but repo is provided
    if entry is None and repo is not None:
        git_backend = RealGitBackend()
        entry = auto_create_worktree(name, repo, registry, git_backend)
        if entry is not None:
            typer.echo(f"Auto-created worktree for branch '{name}'")

    if entry is None:
        typer.echo(
            f"Error: no entry found for '{name}' (searched by name and branch)",
            err=True,
        )
        if repo is not None:
            typer.echo(
                f"Branch '{name}' not found in repo '{repo}'",
                err=True,
            )
        # List available entries as a hint
        all_entries = registry.list_all()
        if all_entries:
            typer.echo("Available entries:", err=True)
            for e in all_entries:
                typer.echo(f"  {e.name} [{e.branch}]", err=True)
        raise typer.Exit(code=1)

    # Check for stale branch and auto-merge main
    if not no_merge:
        git_backend = RealGitBackend()
        merge_msg = check_and_merge_stale(entry, git_backend)
        if merge_msg:
            typer.echo(merge_msg)

    sandbox_info = f" (sandbox: {entry.sandbox_name})" if entry.sandbox_name else ""
    typer.echo(f"Resuming: {entry.name} at {entry.worktree_path}{sandbox_info}")


@app.command()
def cleanup(
    name: str | None = typer.Option(None, help="Remove a specific entry by name."),
    cleanup_all_entries: bool = typer.Option(
        False, "--all", help="Clean up all stale entries."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show what would be removed."
    ),
    force: bool = typer.Option(
        False, "--force", help="Force removal of entries with local-only work."
    ),
    stale_days: int = typer.Option(
        30, "--stale-days", help="Days without commits before a branch is stale."
    ),
    smart: bool = typer.Option(
        False, "--smart", help="Use smart cleanup (check PRs, staleness, remotes)."
    ),
) -> None:
    """Remove stale entries from the registry."""
    registry = get_default_registry()

    if not name and not cleanup_all_entries:
        typer.echo("Error: specify --name NAME or --all", err=True)
        raise typer.Exit(code=1)

    if name:
        removed = cleanup_by_name(name, registry, dry_run=dry_run)
        if not removed:
            typer.echo(f"Error: entry '{name}' not found", err=True)
            raise typer.Exit(code=1)
        action = "Would remove" if dry_run else "Removed"
        typer.echo(f"{action}: {name}")
        return

    # --all
    if smart:
        git = RealGitBackend()
        candidates = smart_cleanup(
            registry, git, dry_run=dry_run, force=force, stale_days=stale_days
        )
        if not candidates:
            typer.echo("No cleanup candidates found.")
        else:
            for candidate in candidates:
                reasons = ", ".join(candidate.reasons)
                skipped = ""
                if candidate.force_required and not force and not dry_run:
                    skipped = " [SKIPPED - use --force]"
                action = "Would remove" if dry_run else "Removed"
                if candidate.force_required and not force and not dry_run:
                    action = "Skipped"
                typer.echo(f"  {action}: {candidate.entry.name} ({reasons}){skipped}")
                for warning in candidate.warnings:
                    typer.echo(f"    WARNING: {warning}")
    else:
        removed_names = cleanup_all(registry, dry_run=dry_run)
        if not removed_names:
            typer.echo("No stale entries found.")
        else:
            action = "Would remove" if dry_run else "Removed"
            for entry_name in removed_names:
                typer.echo(f"  {action}: {entry_name}")


def get_default_token_store() -> TokenStore:
    """Return the default token store."""
    return TokenStore()


@token_app.command("add")
def token_add(
    repo: str = typer.Argument(..., help="Repository in owner/repo format."),
    token: str = typer.Option(..., prompt=True, hide_input=True, help="GitHub token."),
    permissions: list[str] | None = typer.Option(
        None, "--permission", "-p", help="Token permission scopes."
    ),
) -> None:
    """Add a GitHub token for a repository."""
    store = get_default_token_store()
    existing = store.get(repo)
    if existing is not None:
        typer.echo(f"Token already exists for {repo}. Use 'token update' to replace.")
        raise typer.Exit(code=1)
    store.add(repo, token, permissions=permissions or [])
    typer.echo(f"Token added for {repo}")


@token_app.command("update")
def token_update(
    repo: str = typer.Argument(..., help="Repository in owner/repo format."),
    token: str = typer.Option(
        ..., prompt=True, hide_input=True, help="New GitHub token."
    ),
    permissions: list[str] | None = typer.Option(
        None, "--permission", "-p", help="Token permission scopes."
    ),
) -> None:
    """Update an existing GitHub token for a repository."""
    store = get_default_token_store()
    existing = store.get(repo)
    if existing is None:
        typer.echo(f"No token found for {repo}. Use 'token add' first.")
        raise typer.Exit(code=1)
    store.add(repo, token, permissions=permissions or existing.permissions)
    typer.echo(f"Token updated for {repo}")


@token_app.command("remove")
def token_remove(
    repo: str = typer.Argument(..., help="Repository in owner/repo format."),
) -> None:
    """Remove a GitHub token for a repository."""
    store = get_default_token_store()
    if not store.remove(repo):
        typer.echo(f"No token found for {repo}", err=True)
        raise typer.Exit(code=1)
    typer.echo(f"Token removed for {repo}")


@token_app.command("set-default")
def token_set_default(
    token: str = typer.Option(..., prompt=True, hide_input=True, help="GitHub token."),
) -> None:
    """Set the default personal GitHub token.

    Validates the token by calling `gh api user` and stores the
    associated GitHub username for owner-based resolution.
    """
    env = {**os.environ, "GH_TOKEN": token}
    try:
        result = subprocess.run(
            ["gh", "api", "user", "--jq", ".login"],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        typer.echo(f"Error: could not validate token: {exc}", err=True)
        raise typer.Exit(code=1) from exc

    if result.returncode != 0:
        typer.echo(f"Error: token validation failed: {result.stderr.strip()}", err=True)
        raise typer.Exit(code=1)

    github_user = result.stdout.strip()
    if not github_user:
        typer.echo("Error: could not determine GitHub username from token", err=True)
        raise typer.Exit(code=1)

    store = get_default_token_store()
    store.add(DEFAULT_KEY, token, github_user=github_user)
    typer.echo(f"Default token set for user '{github_user}'")


@token_app.command("remove-default")
def token_remove_default() -> None:
    """Remove the default personal GitHub token."""
    store = get_default_token_store()
    if not store.remove(DEFAULT_KEY):
        typer.echo("No default token configured", err=True)
        raise typer.Exit(code=1)
    typer.echo("Default token removed")


@token_app.command("status")
def token_status() -> None:
    """Show all stored tokens with metadata."""
    store = get_default_token_store()
    tokens = store.list_all()
    if not tokens:
        typer.echo("No tokens stored.")
        return
    for key, entry in tokens.items():
        masked = (
            entry.token[:4] + "..." + entry.token[-4:]
            if len(entry.token) > 8
            else "****"
        )
        if key == DEFAULT_KEY:
            typer.echo(
                f"  Default: {masked} (user: {entry.github_user}, "
                f"created: {entry.created_at})"
            )
        else:
            perms = (
                ", ".join(entry.permissions) if entry.permissions else "none specified"
            )
            typer.echo(
                f"  {key}: {masked} (created: {entry.created_at}, permissions: {perms})"
            )


if __name__ == "__main__":
    app()
