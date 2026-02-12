"""Superintendent CLI for agent orchestration.

Subcommands:
    run       — Create a workspace and spawn an agent
    list      — List all active entries
    resume    — Resume an existing entry
    cleanup   — Remove stale entries
"""

from pathlib import Path

import typer

from superintendent.backends.factory import BackendMode, create_backends
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
