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

# Dry-run a workflow
superintendent run --repo /path/to/repo --task "test" --dry-run
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
See `docs/BEADS_BEST_PRACTICES.md` for complete guide.

## Architecture

```
Orchestrator (stateless) → Executor (stateful) → Backends (abstractions)
                                                    ├── DockerBackend
                                                    ├── GitBackend
                                                    ├── TerminalBackend
                                                    └── AuthBackend
```

Each backend has Real, Mock, and DryRun implementations.

## Directory Structure

```
superintendent/
├── src/
│   └── superintendent/
│       ├── orchestrator/     # Planner and Executor
│       ├── backends/         # Docker, Git, Terminal, Auth abstractions
│       ├── state/            # Workflow state, .ralph/, registry
│       └── cli/              # Entry point (main.py)
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

## Key Files

- `src/superintendent/orchestrator/models.py` - WorkflowStep, WorkflowPlan dataclasses
- `src/superintendent/orchestrator/planner.py` - Creates plan from inputs
- `src/superintendent/orchestrator/executor.py` - Runs plan, manages state
- `src/superintendent/backends/docker.py` - DockerBackend protocol and implementations
- `src/superintendent/state/workflow.py` - WorkflowState enum and transitions
