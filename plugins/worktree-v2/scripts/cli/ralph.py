"""ralph.py CLI: main entry point for Ralph autonomous agent spawning.

Usage:
    python -m cli.ralph --repo /path/to/repo --task "fix the bug"
    python -m cli.ralph --repo https://github.com/user/repo --task "add feature" --dry-run
"""

import argparse
import sys
from typing import Any

from orchestrator.executor import Executor
from orchestrator.planner import Planner, PlannerInput


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ralph CLI."""
    parser = argparse.ArgumentParser(
        prog="ralph",
        description="Spawn a Ralph autonomous agent in a Docker sandbox.",
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
        "--template-dockerfile",
        default=None,
        help="Path to a custom Dockerfile template for the sandbox.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show the plan without executing it.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Force recreation of existing sandbox/worktree.",
    )
    parser.add_argument(
        "--sandbox-name",
        default=None,
        help="Custom name for the Docker sandbox (default: auto-generated).",
    )
    return parser


def run(
    args: argparse.Namespace,
    planner: "Planner | None" = None,
    executor: "Executor | None" = None,
) -> Any:
    """Run the ralph workflow: create plan, then execute or dry-run.

    Returns ExecutionResult on normal run, or WorkflowPlan on dry-run.
    """
    if planner is None:
        planner = Planner()
    if executor is None:
        executor = Executor()

    planner_input = PlannerInput(
        repo=args.repo,
        task=args.task,
        mode="sandbox",
        branch=args.branch,
        context_file=args.context_file,
        sandbox_name=args.sandbox_name,
        force=args.force,
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

    # Dry-run returns a plan, not an ExecutionResult
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
