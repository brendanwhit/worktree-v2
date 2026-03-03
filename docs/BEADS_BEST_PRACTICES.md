# Beads Best Practices for AI Agents

> This document captures best practices for using [Beads](https://github.com/steveyegge/beads) -
> a git-backed issue tracker designed for AI coding agents.

## Quick Reference

```bash
# Daily workflow
bd ready                      # Find unblocked work
bd update <id> --claim        # Claim and start task
bd close <id> "Summary"       # Complete with summary
bd doctor                     # Check for issues

# Project setup
bd init                       # Initialize beads (starts Dolt server)
bd setup claude               # Install Claude Code hooks

# Maintenance
bd cleanup                    # Remove stale issues
bd compact                    # Summarize old closed issues
```

## Core Principles

### 1. Hierarchical Task Structure

Beads uses hash-based IDs that support nesting:
- `wt-a3f8` → Epic (large feature)
- `wt-a3f8.1` → Task (implementable unit)
- `wt-a3f8.1.1` → Subtask (if needed)

This prevents merge conflicts and enables parallel agent work.

### 2. Dependencies Are First-Class

```bash
# Managing dependencies (use `bd dep`, not `bd update --blocked-by`)
bd dep add <issue> <depends-on>           # Issue depends on depends-on
bd dep add <child> blocks:<parent>        # Child blocks parent
bd dep add <child> related:<other>        # Associated but independent
bd dep add <child> parent:<epic>          # Hierarchical nesting
bd dep add <child> discovered-from:<task> # Found while working on task

# Viewing dependencies
bd show <id>                              # See blocks/blocked-by
bd blocked                                # Show all blocked issues
```

Always define dependencies before starting work. `bd ready` only shows unblocked tasks.

### 3. Fine-Grained Tasks

Smaller tasks = better outcomes:
- Each session is cheaper (less context)
- Agents make better decisions (near start of context window)
- Less likely to take shortcuts
- Easier to parallelize

**Rule of thumb**: If a task takes more than one session, break it down.

### 4. Epic Planning Workflow

For large projects:

1. **File all epics and tasks first**
   ```bash
   bd create "Epic: Core Architecture" --type epic --priority 0
   bd create "Implement Orchestrator" --parent wt-xxx --priority 1
   ```

2. **Review and refine** (second pass)
   - Check dependencies with `bd dep tree`
   - Identify parallelizable work
   - Polish descriptions

3. **Then execute** with `bd ready` loop

### 5. Session Handoffs ("Land the Plane")

Every session must end properly:

1. Update task status: `bd update <id> --status blocked --reason "needs X"`
2. Create handoff summary in task notes
3. `git push` - the plane isn't landed until push succeeds

> **Note:** `bd sync` is deprecated. Use `bd dolt push` / `bd dolt pull` instead.
> `bd dolt push` requires a configured Dolt remote — in sandboxes without one,
> beads state is local-only, and that's fine since the host manages task tracking.

The handoff should contain:
- What was accomplished
- What's left to do
- Any blockers or discoveries
- Ready-to-paste context for next agent

### 6. Track Discovered Work

When you find issues while working on something else:

```bash
bd create "Memory leak in auth service" \
  --deps discovered-from:wt-abc123 \
  --priority 2
```

This preserves context about how the issue was found.

## Workflow Patterns

### Starting Work

```bash
bd ready                           # What's available?
bd show wt-abc.1                   # Read the details
bd update wt-abc.1 --claim         # Atomically claim it
# ... do the work ...
bd close wt-abc.1 "Implemented X, tested with Y"
```

### Blocked? Create a Subtask

```bash
bd update wt-abc.1 --status blocked --reason "Needs API endpoint first"
bd create "Add /users endpoint" --parent wt-abc.1 --priority 0
```

### Daily Maintenance

```bash
bd doctor           # Check for issues (run daily)
bd cleanup          # Remove stale items (run weekly)
bd compact          # Summarize old closed issues (run monthly)
```

## Git Worktree Integration

Beads v0.50+ uses a Dolt SQL server shared across all worktrees:

```bash
# Dolt server runs on port 3307; beads auto-detects it
bd dolt start          # Start server (if not already running)
bd dolt push           # Push beads state to Dolt remote
bd dolt pull           # Pull beads state from Dolt remote
```

## Docker Sandbox Configuration

Superintendent automatically sets up beads with a Dolt SQL server inside each
sandbox during the `initialize_state` workflow step. The setup:

1. **Dolt binary** is baked into the sandbox template image (multi-stage build)
2. **Dolt server** is started inside the sandbox via `bd dolt start`
3. **Beads is initialized** with `bd init --sandbox --skip-hooks -p {name} --database {name} -q`
   (repo name is sanitized: dots → underscores, non-alphanumeric stripped)
4. Beads auto-detects the running Dolt server on port 3307
5. **Automatic retry**: If init fails (e.g. Dolt fsync error on overlay fs),
   superintendent cleans up and retries once after a 2-second delay

### Agent Conventions

Agents inside sandboxes should use these flags with all `bd` commands:

- `--sandbox` — disables auto-sync (sandbox-safe)
- `--json` — structured JSON output for reliable parsing

### Sandbox Network Limitations

Docker sandboxes have restricted network access:

- **No SSH**: Superintendent automatically converts SSH remote URLs
  (`git@github.com:...`) to HTTPS when cloning for sandboxes
- **HTTPS + gh CLI only**: All git operations must use HTTPS remotes
- **Agents should commit and push**: Configure agents to `git push` and
  create PRs via `gh pr create` before finishing, since the sandbox is
  ephemeral

### Branch Divergence Handling

When a previous agent session has already pushed to the same branch,
superintendent handles this automatically during `clone_for_sandbox`:

1. Checks if the branch exists on the remote
2. If so, checks out the existing branch instead of creating a new one
3. Rebases onto the default branch to pick up upstream changes

This prevents "branch diverged" errors when agents resume work on existing branches.

### Troubleshooting

| Issue | Symptom | Fix |
|-------|---------|-----|
| Dolt not starting | `bd` commands fail with connection error | Check `dolt` binary is in template image |
| Dolt fsync error | Init fails on first try, succeeds on retry | Normal in containers; superintendent retries automatically |
| Health check timeout | `initialize_state` step fails | Dolt may need more startup time; check container resources |
| Init fails | `bd init` returns non-zero | Verify `--sandbox` flag and repo name prefix |
| Invalid DB name | Dots in repo name cause Dolt errors | Superintendent sanitizes names automatically (dots → underscores) |

## Claude Code Integration

Prefer CLI + hooks over MCP (10-50x more context efficient):

```bash
bd setup claude              # Install hooks
bd setup claude --check      # Verify installation
```

Hooks automatically run `bd prime` on:
- Session start
- Before context compaction

## Anti-Patterns to Avoid

1. **Giant tasks** - Break them down
2. **Missing dependencies** - Always define before work
3. **Orphan discoveries** - Use `discovered-from` to track context
4. **Abandoned sessions** - Always land the plane
5. **Manual status tracking** - Use `bd update`, not comments
6. **Skipping review** - Always review epics before executing

## Sources

- [Beads GitHub](https://github.com/steveyegge/beads)
- [Beads Best Practices (Steve Yegge)](https://steve-yegge.medium.com/beads-best-practices-2db636b9760c)
- [Better Stack Guide](https://betterstack.com/community/guides/ai/beads-issue-tracker-ai-agents/)
- [Beads Worktrees Doc](https://github.com/steveyegge/beads/blob/main/docs/WORKTREES.md)
