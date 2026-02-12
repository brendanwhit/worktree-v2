Spawn a Ralph autonomous agent in a Docker sandbox.

Run the superintendent CLI in autonomous sandbox mode:

```bash
superintendent run autonomous sandbox $ARGUMENTS
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
/superintendent:ralph --repo /path/to/repo --task "fix the login bug"
/superintendent:ralph --repo https://github.com/user/repo --task "add tests" --dry-run
/superintendent:ralph --repo /path/to/repo --task "refactor auth" --branch auth-refactor --force
```
