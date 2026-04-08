**Deprecated:** Use `run --branch` instead, which reuses existing worktrees
and auto-merges stale branches.

```bash
# Instead of: superintendent resume --name my-branch
superintendent run <mode> <target> --repo <repo> --task <task> --branch my-branch
```

The `run` command now handles all resume scenarios:
- Reuses existing worktrees when the branch already exists
- Auto-merges main into stale branches (disable with `--no-merge`)
- Use `--force` to recreate from scratch
