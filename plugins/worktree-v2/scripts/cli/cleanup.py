"""cleanup.py CLI: remove stale worktrees, sandboxes, and registry entries.

Usage:
    python -m cli.cleanup --all
    python -m cli.cleanup --name old-worktree
    python -m cli.cleanup --all --dry-run
"""

import argparse
import sys
from pathlib import Path

from state.registry import WorktreeRegistry


def get_default_registry() -> WorktreeRegistry:
    """Return the default global worktree registry."""
    return WorktreeRegistry(Path.home() / ".claude" / "worktree-registry.json")


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the cleanup CLI."""
    parser = argparse.ArgumentParser(
        prog="cleanup",
        description="Clean up stale worktrees and registry entries.",
    )
    parser.add_argument(
        "--name",
        default=None,
        help="Remove a specific worktree entry by name.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        default=False,
        help="Clean up all stale entries (missing worktree paths).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Show what would be removed without actually removing.",
    )
    return parser


def cleanup_by_name(
    name: str,
    registry: WorktreeRegistry,
    dry_run: bool = False,
) -> bool:
    """Remove a specific worktree entry by name.

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


def main() -> int:
    """CLI entry point. Returns exit code."""
    parser = build_parser()
    args = parser.parse_args()

    if not args.name and not args.all:
        print("Error: specify --name NAME or --all", file=sys.stderr)
        return 1

    registry = get_default_registry()

    if args.name:
        removed = cleanup_by_name(args.name, registry, dry_run=args.dry_run)
        if not removed:
            print(f"Error: worktree '{args.name}' not found", file=sys.stderr)
            return 1
        action = "Would remove" if args.dry_run else "Removed"
        print(f"{action}: {args.name}")
        return 0

    # --all
    removed = cleanup_all(registry, dry_run=args.dry_run)
    if not removed:
        print("No stale entries found.")
    else:
        action = "Would remove" if args.dry_run else "Removed"
        for name in removed:
            print(f"  {action}: {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
