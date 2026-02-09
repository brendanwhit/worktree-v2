Spawn a Ralph autonomous agent in a Docker sandbox.

Run the ralph CLI to create a worktree, Docker sandbox, and start an agent:

```bash
python scripts/cli/ralph.py $ARGUMENTS
```

## Available flags

- `--repo REPO` (required) — Path or URL to the repository
- `--task TASK` (required) — Task description for the agent
- `--branch BRANCH` — Git branch name for the worktree
- `--context-file FILE` — Path to a context file for the agent
- `--template-dockerfile FILE` — Custom Dockerfile template for the sandbox
- `--dry-run` — Show the plan without executing it
- `--force` — Force recreation of existing sandbox/worktree
- `--sandbox-name NAME` — Custom name for the Docker sandbox

## Examples

```
/worktree:ralph --repo /path/to/repo --task "fix the login bug"
/worktree:ralph --repo https://github.com/user/repo --task "add tests" --dry-run
/worktree:ralph --repo /path/to/repo --task "refactor auth" --branch auth-refactor --force
```
