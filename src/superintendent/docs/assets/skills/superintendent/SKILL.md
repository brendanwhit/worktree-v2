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

## Mode × target: picking the right combo

| Mode | Target | Use when | Notes |
|------|--------|----------|-------|
| `autonomous` | `sandbox` | **Default choice.** Fire-and-forget work on a repo you have tokens for. | Full Docker isolation, persistent auth, agent creates branch + PR. |
| `autonomous` | `container` | One-off disposable task, no state to preserve. | Ephemeral — container is removed after exit. |
| `autonomous` | `local` | You trust the task and don't need Docker. | Requires `--dangerously-skip-isolation` because there's no sandbox boundary. |
| `interactive` | `sandbox` | You want to watch or debug agent behavior in an isolated environment. | Opens a terminal session inside the sandbox. |
| `interactive` | `container` | Quick interactive experiment in a throwaway container. | Same as sandbox but ephemeral. |
| `interactive` | `local` | Fast local debugging, no Docker overhead. | Runs in a git worktree on your machine. |

When in doubt, start with `autonomous sandbox`.

## Worked example

Spawn an autonomous agent to add tests in an isolated sandbox:

```bash
# 1. See what the orchestrator would decide
superintendent run autonomous sandbox \
  --repo /Users/you/projects/myapp \
  --task "Add unit tests for the auth module" \
  --explain

# 2. Preview the exact plan
superintendent run autonomous sandbox \
  --repo /Users/you/projects/myapp \
  --task "Add unit tests for the auth module" \
  --dry-run

# 3. Launch it
superintendent run autonomous sandbox \
  --repo /Users/you/projects/myapp \
  --task "Add unit tests for the auth module"

# 4. Check on it later
superintendent status
```

**What happens when it finishes:** The agent works in a git worktree, commits to a branch, pushes, and opens a PR via `gh pr create`. Use `superintendent status` to see whether it completed or failed, then review the PR.

## Token setup

Tokens are only needed for **private repos** or repos requiring authenticated git operations.

- **Most users:** Run `superintendent token set-default` once with a GitHub PAT. This covers any repo you own.
- **Per-repo tokens:** Use `superintendent token add owner/repo` for fine-grained access to specific repositories.
- **Public repos:** No token setup needed.

If you skip token setup and the agent needs auth, it will fail at the `authenticate` step — run `superintendent status` to see this and then configure tokens.

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
