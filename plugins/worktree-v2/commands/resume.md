Resume or reattach to an existing worktree and its sandbox.

Run the worktree CLI resume command:

```bash
python scripts/cli/worktree.py resume $ARGUMENTS
```

## Available flags

- `--name NAME` (required) — Name of the worktree entry to resume

Looks up the worktree in the global registry, verifies the worktree path
and sandbox still exist, then reattaches to the running agent.

## Examples

```
/worktree:resume --name my-repo
```
