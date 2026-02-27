"""Superintendent CLI for agent orchestration.

Subcommands:
    run       — Create a workspace and spawn an agent
    list      — List all active entries
    resume    — Resume an existing entry
    cleanup   — Remove stale entries
    token     — Manage scoped GitHub tokens
"""

from dataclasses import dataclass, field
from pathlib import Path

import typer

from superintendent.backends.factory import BackendMode, create_backends
from superintendent.backends.git import GitBackend, RealGitBackend
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry
from superintendent.state.token_store import TokenStore

app = typer.Typer(name="superintendent", no_args_is_help=True)
token_app = typer.Typer(name="token", help="Manage scoped GitHub tokens.")
app.add_typer(token_app)


def get_default_registry() -> WorktreeRegistry:
    """Return the default global registry."""
    return WorktreeRegistry(Path.home() / ".claude" / "superintendent-registry.json")


def list_entries(registry: WorktreeRegistry) -> list[WorktreeEntry]:
    """List all entries from the registry."""
    return registry.list_all()


def resume_entry(
    name: str,
    registry: WorktreeRegistry,
) -> WorktreeEntry | None:
    """Look up an entry and verify it still exists.

    Returns the entry if found and its worktree_path exists, else None.
    """
    entry = registry.get(name)
    if entry is None:
        return None
    if not Path(entry.worktree_path).exists():
        return None
    return entry


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
        if git.is_branch_stale(repo_path, entry.branch, days=stale_days):
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
    name: str = typer.Option(..., help="Name of the entry to resume."),
) -> None:
    """Resume an existing entry."""
    registry = get_default_registry()
    entry = resume_entry(name, registry)
    if entry is None:
        typer.echo(f"Error: entry '{name}' not found or path missing", err=True)
        raise typer.Exit(code=1)

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


@token_app.command("status")
def token_status() -> None:
    """Show all stored tokens with metadata."""
    store = get_default_token_store()
    tokens = store.list_all()
    if not tokens:
        typer.echo("No tokens stored.")
        return
    for repo, entry in tokens.items():
        masked = (
            entry.token[:4] + "..." + entry.token[-4:]
            if len(entry.token) > 8
            else "****"
        )
        perms = ", ".join(entry.permissions) if entry.permissions else "none specified"
        typer.echo(
            f"  {repo}: {masked} (created: {entry.created_at}, permissions: {perms})"
        )


if __name__ == "__main__":
    app()
