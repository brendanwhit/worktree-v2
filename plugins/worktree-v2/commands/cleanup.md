Clean up stale worktrees, sandboxes, and registry entries.

Run the cleanup CLI to remove merged worktrees and stale resources:

```bash
python scripts/cli/cleanup.py $ARGUMENTS
```

## Available flags

- `--name NAME` — Remove a specific worktree entry by name
- `--all` — Clean up all stale entries (merged branches, missing paths)
- `--dry-run` — Show what would be removed without actually removing

Removes merged worktrees, stops and removes stale Docker sandboxes,
and cleans up orphaned registry entries.

## Examples

```
/worktree:cleanup --all
/worktree:cleanup --name old-worktree
/worktree:cleanup --all --dry-run
```
