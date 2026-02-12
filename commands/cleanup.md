Clean up stale entries, sandboxes, and registry entries.

Run the superintendent CLI cleanup command:

```bash
superintendent cleanup $ARGUMENTS
```

## Available flags

- `--name NAME` — Remove a specific entry by name
- `--all` — Clean up all stale entries (merged branches, missing paths)
- `--dry-run` — Show what would be removed without actually removing

Removes merged entries, stops and removes stale Docker sandboxes,
and cleans up orphaned registry entries.

## Examples

```
/superintendent:cleanup --all
/superintendent:cleanup --name old-entry
/superintendent:cleanup --all --dry-run
```
