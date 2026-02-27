"""Superintendent CLI for agent orchestration.

Subcommands:
    run       — Create a workspace and spawn an agent
    list      — List all active entries
    resume    — Resume an existing entry
    cleanup   — Remove stale entries
"""

import re
from pathlib import Path

import typer

from superintendent.backends.factory import BackendMode, create_backends
from superintendent.backends.git import GitBackend, RealGitBackend
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.models import Mode, Target
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry

app = typer.Typer(name="superintendent", no_args_is_help=True)


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
    removed_names = cleanup_all(registry, dry_run=dry_run)
    if not removed_names:
        typer.echo("No stale entries found.")
    else:
        action = "Would remove" if dry_run else "Removed"
        for entry_name in removed_names:
            typer.echo(f"  {action}: {entry_name}")


if __name__ == "__main__":
    app()
