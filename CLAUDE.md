# Superintendent - Agent Orchestration CLI

## Quick Reference

```bash
# Setup
uv sync --dev

# Run tests
uv run pytest                           # All tests
uv run pytest tests/test_models.py -v   # Specific file

# Linting and type checking
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/

# Check Beads status
bd ready                    # Find unblocked work
bd show <id>                # Full task details
bd doctor                   # Check for issues

# Dry-run a workflow (sup is an alias for superintendent)
superintendent run autonomous sandbox --repo /path/to/repo --task "test" --dry-run
```

## Project Overview

An orchestration CLI for spawning autonomous Claude agents in isolated Docker sandboxes, designed with:
- **Testability first**: Backends are abstracted for mocking
- **Explicit state machine**: Workflow states are clearly defined
- **One sandbox per repo**: Auth persists across runs
- **Proper feedback**: Terminal spawn returns success/failure

See `docs/ARCHITECTURE.md` for full architecture.

## Beads Integration

This project uses [Beads](https://github.com/steveyegge/beads) for task tracking.

**Before starting work:**
```bash
bd ready                    # What's available?
bd show <id>               # Read task details
bd update <id> --claim     # Claim the task
```

**After completing work:**
```bash
bd close <id> "Summary of what was done"
git push                   # Land the plane!
```

**If you discover new work:**
```bash
bd create "New issue" --deps discovered-from:<current-task>
```

**Docker sandbox agents:** Use `no-db: true` and `no-daemon: true` in config.yaml.
Sandboxes have no SSH — use HTTPS git remotes and `gh` CLI only.
Agents should commit, push, and create PRs via `gh pr create` before exiting.
See `docs/BEADS_BEST_PRACTICES.md` for complete guide.

## Architecture

```
CLI (typer)
  → Planner (stateless) → creates WorkflowPlan
  → Executor (stateful) → runs plan through state machine
    → StepHandler → dispatches to backends
      ├── DockerBackend   (sandbox/container lifecycle)
      ├── GitBackend      (clone, worktree, checkout)
      ├── TerminalBackend (spawn agent process)
      └── AuthBackend     (token injection, git auth)
```

Each backend has Real, Mock, and DryRun implementations.
Task sources (Beads, Markdown, Single) are pluggable via the TaskSource protocol.

## Directory Structure

```
superintendent/
├── src/
│   └── superintendent/
│       ├── cli/              # Typer entry point (main.py)
│       ├── orchestrator/     # Planner, Executor, StepHandler, sources/
│       ├── backends/         # Docker, Git, Terminal, Auth abstractions
│       └── state/            # WorkflowState, .ralph/, registry, checkpoints
├── tests/                    # Unit, integration, e2e tests
├── commands/                 # Slash command .md files
└── docs/                     # Design docs and guides
```

## Development Guidelines

1. **No external calls without abstraction** - All Docker, git, and terminal operations go through backends
2. **State is explicit** - Use the WorkflowState enum, save checkpoints
3. **Errors are handled** - Backends return success/failure, never silently fail
4. **Dry-run is comprehensive** - Should show exact commands that would run
5. **Tests before implementation** - Write the test, then the code

## Code Patterns to Follow

**DO NOT use `from __future__ import annotations`** - Use quoted strings for forward references instead:
```python
# Good
def create() -> "MyClass": ...

# Bad - don't add this import
from __future__ import annotations
```

**DO NOT use `Path.cwd()` in module-level constants** - Wrap in a function for lazy evaluation:
```python
# Good
def get_default_dir() -> Path:
    return Path.cwd() / "data"

# Bad - evaluated at import time
DEFAULT_DIR = Path.cwd() / "data"
```

## CI Checklist

Before pushing, run all checks locally:
```bash
uv run pytest                              # Tests pass
uv run ruff check src/ tests/              # Lint clean
uv run ruff format --check src/ tests/     # Format clean (not same as lint!)
```

**Note:** Integration tests that run `git commit` need `user.name` and `user.email` configured in test setup.

## Autonomous Agent Rules

These rules apply when running as an unsupervised autonomous agent (e.g. Ralph in a Docker sandbox).

**Scope discipline:**
- Only work on the assigned task. Do not refactor unrelated code or add unrequested features.
- If you discover adjacent work, create a beads issue (`bd create`) — do not do it yourself.

**Git hygiene:**
- Commit, push, and create a PR via `gh pr create` before exiting. Work that isn't pushed is lost.
- Use HTTPS remotes only. SSH is not available in sandboxes.
- Do not commit `.claude/`, editor configs, or other local artifacts.
- Do not commit `.beads/` changes — the main repo manages its own beads state.

**Beads in sandboxes:**
- Use `no-db: true` and `no-daemon: true` in beads config (no Dolt in containers).
- Do not include `.beads/` files in your PR branch. Task tracking is managed externally.

**PR expectations:**
- PR title should be concise and describe the change, not the task ID.
- PR body should summarize what changed and include a test plan.
- Run the full CI checklist (pytest, ruff check, ruff format) before creating the PR.

## Key Files

- `src/superintendent/cli/main.py` - Typer CLI with run/list/resume/cleanup commands
- `src/superintendent/orchestrator/models.py` - WorkflowStep, WorkflowPlan, Mode, Target
- `src/superintendent/orchestrator/planner.py` - Creates WorkflowPlan from PlannerInput
- `src/superintendent/orchestrator/executor.py` - Runs plan through state machine
- `src/superintendent/orchestrator/step_handler.py` - Dispatches steps to backends
- `src/superintendent/orchestrator/strategy.py` - Decides mode, target, parallelism
- `src/superintendent/orchestrator/sources/protocol.py` - TaskSource ABC
- `src/superintendent/backends/docker.py` - DockerBackend protocol and implementations
- `src/superintendent/backends/factory.py` - BackendMode enum, create_backends()
- `src/superintendent/state/workflow.py` - WorkflowState enum and transitions
- `src/superintendent/state/registry.py` - WorktreeRegistry for tracking entries
