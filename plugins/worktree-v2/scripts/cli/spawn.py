"""spawn.py CLI: simpler agent spawning without Docker sandbox.

Uses local mode with --dangerously-skip-permissions instead of Docker.
For local development and quick tasks.

Usage:
    python -m cli.spawn --repo /path/to/repo --task "fix the bug"
    python -m cli.spawn --repo /path/to/repo --task "add feature" --dry-run
"""

import argparse
import sys
from typing import Any

from orchestrator.executor import Executor
from orchestrator.planner import Planner, PlannerInput


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the spawn CLI."""
    parser = argparse.ArgumentParser(
        prog="spawn",
        description="Spawn an agent locally without Docker sandbox.",
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path or URL to the repository.",
    )
    parser.add_argument(
        "--task",
        required=True,
        help="Task description for the agent.",
    )
    parser.add_argument(
        "--branch",
        default=None,
        help="Git branch name for the worktree (default: auto-generated).",
    )
    parser.add_argument(
        "--context-file",
        default=None,
        help="Path to a context file to include in the agent workspace.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the plan without executing it.",
    )
    return parser


def run(
    args: argparse.Namespace,
    planner: "Planner | None" = None,
    executor: "Executor | None" = None,
) -> Any:
    """Run the spawn workflow in local mode (no Docker).

    Returns ExecutionResult on normal run, or WorkflowPlan on dry-run.
    """
    if planner is None:
        planner = Planner()
    if executor is None:
        executor = Executor()

    planner_input = PlannerInput(
        repo=args.repo,
        task=args.task,
        mode="local",
        branch=args.branch,
        context_file=args.context_file,
    )

    plan = planner.create_plan(planner_input)

    if args.dry_run:
        print("=== Dry Run: Workflow Plan ===")
        print(plan.to_json())
        return plan

    result = executor.run(plan)
    return result


def main() -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args()
    result = run(args)

    if args.dry_run:
        return 0

    if hasattr(result, "state") and result.state.name == "FAILED":
        print(f"Error: {result.error}", file=sys.stderr)
        if result.failed_step:
            print(f"Failed at step: {result.failed_step}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
