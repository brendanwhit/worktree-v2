"""resume.py CLI: reattach to an existing worktree and its sandbox.

Usage:
    python -m cli.resume --name my-worktree
    python -m cli.resume --list
"""

import argparse
import sys
from pathlib import Path

from state.registry import WorktreeEntry, WorktreeRegistry


def get_default_registry() -> WorktreeRegistry:
    """Return the default global worktree registry."""
    return WorktreeRegistry(Path.home() / ".claude" / "worktree-registry.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the resume CLI."""
    parser = argparse.ArgumentParser(
        prog="resume",
        description="Resume or list existing worktree entries.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Name of the worktree entry to resume.",
    )
    parser.add_argument(
        "--list",
        dest="list_entries",
        action="store_true",
        default=False,
        help="List all active worktree entries.",
    )
    return parser


def list_worktrees(registry: WorktreeRegistry) -> list[WorktreeEntry]:
    """List all worktree entries from the registry."""
    return registry.list_all()


def resume_worktree(
    name: str,
    registry: WorktreeRegistry,
) -> WorktreeEntry | None:
    """Look up a worktree entry and verify it still exists.

    Returns the entry if found and its worktree_path exists, else None.
    """
    entry = registry.get(name)
    if entry is None:
        return None
    if not Path(entry.worktree_path).exists():
        return None
    return entry


def main() -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.name and not args.list_entries:
        print("Error: specify --name NAME or --list", file=sys.stderr)
        return 1

    registry = get_default_registry()

    if args.list_entries:
        entries = list_worktrees(registry)
        if not entries:
            print("No worktree entries found.")
        else:
            for entry in entries:
                sandbox_info = (
                    f" (sandbox: {entry.sandbox_name})" if entry.sandbox_name else ""
                )
                print(
                    f"  {entry.name}: {entry.repo} [{entry.branch}] {entry.worktree_path}{sandbox_info}"
                )
        return 0

    entry = resume_worktree(args.name, registry)
    if entry is None:
        print(
            f"Error: worktree '{args.name}' not found or path missing", file=sys.stderr
        )
        return 1

    sandbox_info = f" (sandbox: {entry.sandbox_name})" if entry.sandbox_name else ""
    print(f"Resuming: {entry.name} at {entry.worktree_path}{sandbox_info}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
