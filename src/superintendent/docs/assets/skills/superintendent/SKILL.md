---
name: superintendent
description: Use when you need to spawn an autonomous Claude agent on a specific task — fire-and-forget work, parallel subtasks, or work that needs isolation (Docker sandbox, container, or clean worktree) from your current session. Not for interactive collaboration in your current session.
---

# Superintendent

Spawns Claude agents in isolated workspaces. One sandbox per repo (auth persists). State lives in `.superintendent/`.

## When to use — and when NOT to

**Use when:**
- Task can run to completion without your ongoing direction
- N independent subtasks can run in parallel
- Work needs isolation (risky operations, dependency experiments)
- You need a clean worktree separate from current branch

**Don't use when:**
- You want to iterate conversationally (just keep working in this session)
- Task is small enough to finish here
- You need to watch and redirect mid-run (interactive mode exists, but a normal session is usually simpler)

## Before spawning anything

Run `--explain` to see the mode × target decision for your task:

    superintendent run <mode> <target> --explain --repo <repo> --task <task>

Then dry-run to preview the exact plan:

    superintendent run <mode> <target> ... --dry-run

**Never skip both.** Guessing at mode/target wastes a sandbox spin-up.

## Recovering from failures

Agent failed mid-run? Don't re-spawn blindly.

1. `superintendent list` — find the entry
2. `superintendent status <name>` — check exit state and what step failed
3. Fix the underlying issue
4. `superintendent run ... --force` — reuses the worktree, rebuilds state

## Critical rules

- **Never** pass `--dangerously-skip-isolation` without understanding what you're skipping. It's required for `autonomous + local` only because that combo has no sandbox.
- **Before `cleanup --all --smart`**, always dry-run first — it will remove merged/stale branches.
- **After spawning autonomous**, check back with `status` — the parent session doesn't know when the child finishes.

## Full command and flag reference

See [CLI_REFERENCE.md](./CLI_REFERENCE.md) — auto-generated from the CLI, always current.
