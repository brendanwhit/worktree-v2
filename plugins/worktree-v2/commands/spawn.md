Spawn an agent locally without Docker sandbox (no Docker required).

Run the worktree CLI in interactive local mode:

```bash
python scripts/cli/worktree.py run interactive local $ARGUMENTS
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
