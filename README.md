# Superintendent

Agent orchestration CLI for spawning autonomous Claude agents in isolated Docker sandboxes.

## Overview

Superintendent manages the full lifecycle of agent workspaces: cloning repos into
git worktrees, provisioning Docker sandboxes or containers, injecting auth credentials,
initializing agent state, and spawning Claude Code sessions. It supports interactive
and autonomous modes with dry-run previews of every operation.

Key design principles:

- **Backend abstraction** — Docker, Git, Terminal, and Auth operations go through
  Protocol interfaces with Real, Mock, and DryRun implementations
- **Explicit state machine** — Workflow progresses through validated state transitions
  with checkpoints for resumability
- **Pluggable task sources** — Read tasks from Beads, Markdown checklists, or ad-hoc strings
- **Dry-run first** — Every workflow can be previewed before execution

## Installation

**Prerequisites:**
- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (for sandbox/container targets)
- Git

```bash
# Clone the repo
git clone https://github.com/brendanwhit/superintendent.git
cd superintendent

# Install dependencies
uv sync --dev

# Verify installation
uv run superintendent --help
```

The CLI is available as both `superintendent` and `sup`:

```bash
uv run sup --help
```

## Quick Start

**Preview a workflow (dry-run):**

```bash
uv run superintendent run autonomous sandbox \
  --repo /path/to/your/repo \
  --task "Fix the login bug" \
  --dry-run
```

**Spawn an autonomous agent in a Docker sandbox:**

```bash
uv run superintendent run autonomous sandbox \
  --repo /path/to/your/repo \
  --task "Implement the feature described in TODO.md"
```

**Run interactively (opens a terminal session):**

```bash
uv run superintendent run interactive sandbox \
  --repo /path/to/your/repo \
  --task "Explore and debug the test failures"
```

## CLI Reference

### `superintendent run`

Create a workspace and spawn an agent.

```bash
superintendent run <mode> <target> [options]
```

**Arguments:**
| Argument | Values | Description |
|----------|--------|-------------|
| `mode` | `interactive`, `autonomous` | Interaction mode |
| `target` | `sandbox`, `container`, `local` | Execution target |

**Options:**
| Option | Required | Description |
|--------|----------|-------------|
| `--repo` | Yes | Path or URL to the repository |
| `--task` | Yes | Task description for the agent |
| `--branch` | No | Git branch name for the worktree |
| `--context-file` | No | Path to a context file for the agent |
| `--template-dockerfile` | No | Custom Dockerfile template |
| `--sandbox-name` | No | Custom name for the Docker sandbox |
| `--dry-run` | No | Show the plan without executing |
| `--force` | No | Force recreation of existing sandbox/worktree |
| `--dangerously-skip-isolation` | No | Required for `autonomous` + `local` |

**Examples:**

```bash
# Dry-run to preview the workflow plan
superintendent run autonomous sandbox --repo ./my-project --task "Add tests" --dry-run

# Custom branch and sandbox name
superintendent run autonomous sandbox \
  --repo https://github.com/user/repo \
  --task "Refactor auth module" \
  --branch feature/auth-refactor \
  --sandbox-name my-sandbox

# Interactive local session (no Docker)
superintendent run interactive local --repo ./my-project --task "Debug issue #42"
```

### `superintendent list`

List all active worktree entries.

```bash
superintendent list
```

### `superintendent resume`

Resume an existing worktree entry.

```bash
superintendent resume --name <entry-name>
```

### `superintendent cleanup`

Remove stale entries from the registry.

```bash
# Remove a specific entry
superintendent cleanup --name <entry-name>

# Remove all stale entries (worktree path no longer exists)
superintendent cleanup --all

# Preview what would be removed
superintendent cleanup --all --dry-run
```

## Modes and Targets

### Modes

| Mode | Description | Use when |
|------|-------------|----------|
| `interactive` | Opens a terminal session for the agent | You want to observe and interact with the agent |
| `autonomous` | Agent runs headlessly to completion | You want fire-and-forget task execution |

### Targets

| Target | Description | Use when |
|--------|-------------|----------|
| `sandbox` | Docker sandbox with persistent auth | Default choice — full isolation with auth reuse |
| `container` | Ephemeral Docker container | One-off tasks that don't need persistent state |
| `local` | No Docker isolation | Development/debugging only (requires `--dangerously-skip-isolation` for autonomous mode) |

### Choosing the right combination

- **`autonomous sandbox`** — Production use. Agent works in an isolated Docker sandbox with
  git auth, checkpoints, and .ralph/ state management.
- **`interactive sandbox`** — Debugging agent behavior. Same isolation but you can watch/interact.
- **`autonomous container`** — Disposable tasks. Container is cleaned up after execution.
- **`interactive local`** — Quick local debugging without Docker overhead.

## Troubleshooting

**`uv run superintendent` not found:**
```bash
uv sync --dev  # Reinstall dependencies
```

**Docker sandbox won't start:**
- Verify Docker is running: `docker info`
- Check if the sandbox already exists: `docker ps -a | grep <sandbox-name>`
- Use `--force` to recreate: `superintendent run ... --force`

**"autonomous + local requires --dangerously-skip-isolation":**
This is a safety check. Autonomous agents running locally have no sandbox isolation.
Add `--dangerously-skip-isolation` only if you understand the risks.

**Workflow fails at a specific step:**
- Run with `--dry-run` first to preview the plan
- Check the error message for which step failed
- The state machine saves checkpoints, so you can resume after fixing the issue

**Tests failing:**
```bash
uv run pytest -v --tb=long    # Verbose output with full tracebacks
uv run pytest -k "test_name"  # Run a specific test
```

**Lint/format issues:**
```bash
uv run ruff check src/ tests/ --fix   # Auto-fix lint issues
uv run ruff format src/ tests/        # Auto-format code
```
