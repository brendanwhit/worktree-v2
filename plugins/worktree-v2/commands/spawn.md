Spawn an agent locally without Docker sandbox (no Docker required).

Run the spawn CLI to create a worktree and start a local agent:

```bash
python scripts/cli/spawn.py $ARGUMENTS
```

## Available flags

- `--repo REPO` (required) — Path or URL to the repository
- `--task TASK` (required) — Task description for the agent
- `--branch BRANCH` — Git branch name for the worktree
- `--context-file FILE` — Path to a context file for the agent
- `--dry-run` — Show the plan without executing it

## Examples

```
/worktree:spawn --repo /path/to/repo --task "fix the bug"
/worktree:spawn --repo https://github.com/user/repo --task "add feature" --dry-run
/worktree:spawn --repo /path/to/repo --task "update docs" --branch docs-update
```
