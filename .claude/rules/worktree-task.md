# Ralph Autonomous Agent Task

## Overview
You are running as a Ralph autonomous agent. You have permission to execute tasks without user prompts.
Work autonomously, commit frequently, and update your progress.

## Setup (MUST complete before investigating the task)
1. Read `.ralph/config.json` to understand your execution context
2. Read `.ralph/guardrails.md` for learned failure patterns to avoid

## Task Description
Implement resume features for V1 parity: resume by branch name, auto-create worktree, auto-merge stale branches

## Context
# Task Context

## Beads Epic
worktree-v2-22: Epic: V1 Feature Parity (resume subtasks)

## Goal
Implement the resume-related features for V1 parity: resume by branch name, auto-create worktree for existing branches, and auto-merge main into stale branches.

## Subtasks (implement in order)
1. **worktree-v2-10**: Resume by branch name — allow resume to find worktrees by branch name, not just registry name
2. **worktree-v2-23**: Auto-create worktree for existing branch on resume — if branch exists but no worktree, create one
3. **worktree-v2-24**: Auto-merge main into stale branches on resume — detect stale branches (>7 days) and offer to merge main

## Relevant Files/Areas
- `src/superintendent/cli/main.py` - CLI entry point (typer), resume command
- `src/superintendent/state/registry.py` - WorktreeRegistry for tracking entries
- `src/superintendent/backends/git.py` - GitBackend protocol and implementations
- `tests/` - Test files

## Architecture
The CLI dispatches to the Planner/Executor pipeline. The registry tracks worktree entries.
Each backend has Real, Mock, and DryRun implementations.
GitBackend handles clone, worktree, fetch, checkout operations.

## Implementation Notes

### Task 10: Resume by branch name
- Add lookup-by-branch to WorktreeRegistry (currently only looks up by name)
- Scan ~/.claude-worktrees/<repo>/ directories for matching branch
- Check `git worktree list` output as fallback
- Add helpful error message if branch not found anywhere

### Task 23: Auto-create worktree on resume
- After registry lookup fails and branch name found in git
- Create worktree at ~/.claude-worktrees/<repo>/<branch-slug>
- Register it automatically
- Continue with resume flow

### Task 24: Auto-merge main on resume
- Add get_branch_age_days() to GitBackend protocol + all implementations
- Check branch age on resume
- If >7 days stale, merge main into branch
- Handle merge conflicts gracefully (abort and warn)
- Support --no-merge flag to skip

## Constraints
- Do NOT use `from __future__ import annotations`
- Do NOT use `Path.cwd()` in module-level constants
- Follow existing backend patterns (Real, Mock, DryRun)
- All new GitBackend methods need all three implementations
- Write tests for all new functionality

## Completion Criteria

### Must pass (automated checks)
- [ ] All existing tests pass (`uv run pytest`)
- [ ] Linting passes (`uv run ruff check src/ tests/`)
- [ ] Formatting passes (`uv run ruff format --check src/ tests/`)

### Must verify (inspect by reading)
- [ ] Resume works with branch name when not in registry
- [ ] Worktree auto-created at standard location
- [ ] Stale branch detection with configurable threshold
- [ ] Merge conflicts handled gracefully
- [ ] All new backend methods have Real/Mock/DryRun implementations
- [ ] Tests cover happy path and error cases

### Out of scope (do NOT do these)
- Do not modify the Planner or Executor
- Do not change the WorkflowState enum
- Do not add new CLI commands (only enhance resume)
- Do not modify documentation files

## Beads Workflow
- Run `bd update worktree-v2-22 --status=in_progress` when starting
- Close subtasks as completed: `bd close worktree-v2-10` etc.
- Run `bd sync` at the end


## GitHub Authentication

You are running in a Docker sandbox. GitHub authentication setup:

**First, export the token** (required before any gh/git operations):
```bash
export GH_TOKEN=$(cat /run/secrets/gh_token)
gh auth setup-git  # configures git credential helper
```

After this:
- `gh` CLI will work for all GitHub operations
- Git push/pull will use the credential helper
- Git identity is pre-configured as "Claude (Ralph Agent)" <noreply@anthropic.com>

**If you encounter permission denied errors:**
1. This is a token permissions issue - you cannot fix it autonomously
2. Document the error in `.ralph/progress.md`
3. Note the specific permission needed (e.g., `actions:write`, `secrets`)
4. Stop and report - the orchestrator will need to update the token

**Token scope:** This agent is authorized for `brendanwhit/superintendent` only.
Tokens are managed by the orchestrator using `ralph-token` CLI.
If you need access to other repos, that requires orchestrator intervention.

## Ralph Protocol

### Progress Tracking
- Update `.ralph/progress.md` after completing each significant step
- Use Beads (`bd`) to track task status if available:
  - `bd ready` to see available tasks
  - `bd start <id>` to claim a task
  - `bd done <id>` to mark complete

### Git Workflow
- Commit frequently with descriptive messages
- Each commit should represent a logical unit of work
- Push to remote when you have stable progress

### Guardrails
- Before attempting risky operations, check `.ralph/guardrails.md`
- If you encounter a failure, add it to guardrails for future reference
- Learn from past mistakes to avoid repeating them

### Completion
- When task is complete, update progress.md with final status
- Create a PR if appropriate (use `gh pr create`)
- Mark Beads task as done if used
