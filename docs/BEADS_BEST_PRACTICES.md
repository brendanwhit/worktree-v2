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
bd init --branch beads-sync   # Enable daemon + worktree support
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
# Types of dependencies
bd dep add <child> blocks:<parent>        # Child blocks parent
bd dep add <child> related:<other>        # Associated but independent
bd dep add <child> parent:<epic>          # Hierarchical nesting
bd dep add <child> discovered-from:<task> # Found while working on task
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

Beads shares one database across all worktrees:

```bash
# Recommended: use sync branch for multi-worktree development
bd init --branch beads-sync

# This enables:
# - Daemon auto-syncs to beads-sync branch
# - Safe concurrent access via SQLite locking
# - No per-worktree database copies
```

## Docker Sandbox Configuration

SQLite doesn't work reliably in Docker sandbox filesystems (corrupts immediately
or shortly after creation). For agents running in Docker sandboxes, configure
beads to use JSONL-only mode:

```yaml
# .beads/config.yaml
no-db: true           # Use JSONL backend instead of SQLite
no-daemon: true       # Avoid 5-second daemon startup timeout
issue-prefix: <repo>  # Required for no-db mode
```

### Additional Setup for Sandbox Agents

1. **Clear assume-unchanged flag** so JSONL changes can be committed:
   ```bash
   git update-index --no-assume-unchanged .beads/issues.jsonl
   ```

2. **Install beads in the sandbox template** (not at runtime):
   ```dockerfile
   RUN npm install -g @beads/bd
   ```

3. **Pre-commit hooks still work** - they use `bd sync --flush-only` which
   succeeds in no-db mode since there's nothing to flush.

### Why These Settings?

| Issue | Symptom | Fix |
|-------|---------|-----|
| SQLite corruption | `database disk image is malformed` | `no-db: true` |
| Daemon timeout | 5-second delay on every command | `no-daemon: true` |
| JSONL not committed | `git add` silently ignores file | Clear assume-unchanged |
| no-db mode fails | "mixed prefixes" error | Set `issue-prefix` |

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
