# Status Tracker Fix — Design Spec

## Problem

`superintendent run` never registers entries in the `WorktreeRegistry`. The registry file (`~/.claude/superintendent-registry.json`) is never created, so `superintendent list`, `superintendent status`, `superintendent resume`, and `superintendent cleanup` all show nothing — regardless of target (sandbox, container, local).

Additionally, for sandbox/container targets, `check_agent_status()` only reads `.ralph/` markers from the local filesystem. Since those markers live inside the container, status would remain `not_started` even after registration is fixed.

Tests don't catch either bug because executor/integration tests use mock handlers that never touch the registry, and status tests only exercise the read/format side.

## Fix 1: Register entries in `run()`

**File:** `src/superintendent/cli/main.py`, `run()` function (line ~494)

After `executor.run(plan)` succeeds and before the success output, add:

```python
registry = get_default_registry()
worktree_path = context.step_outputs.get("create_worktree", {}).get("worktree_path", "")
branch_name = plan.metadata.get("branch", "")
sandbox_name = plan.metadata.get("sandbox_name")
container_name = plan.metadata.get("container_name")
repo_name = plan.metadata.get("repo_name", _extract_repo_name(repo))
name = _branch_to_slug(branch_name) if branch_name else repo_name

entry = WorktreeEntry(
    name=name,
    repo=repo,
    branch=branch_name,
    worktree_path=worktree_path,
    sandbox_name=sandbox_name or container_name,
)
registry.add(entry)
```

**Placement:** After the failure-exit check (line ~500) but before the success output (line ~502). This ensures:
- Dry runs skip registration (early return on line 492)
- Failed runs skip registration (early exit on line 500)
- Only successful runs register

**Entry fields:**
- `name`: branch slug (via `_branch_to_slug`), falling back to repo name
- `repo`: the repo arg as passed by the user
- `branch`: from plan metadata
- `worktree_path`: from step outputs
- `sandbox_name`: from plan metadata (`sandbox_name` or `container_name`)

## Fix 2: Sandbox status querying

**File:** `src/superintendent/cli/main.py`

### Refactor `check_agent_status()`

Split into a dispatcher that routes based on whether the entry has a sandbox:

```python
def check_agent_status(entry: WorktreeEntry) -> tuple[str, dict]:
    if entry.sandbox_name:
        return _check_sandbox_agent_status(entry)
    return _check_local_agent_status(entry)
```

### New `_check_sandbox_agent_status()`

Runs a single `docker sandbox exec` to read all three marker files:

```bash
docker sandbox exec <sandbox_name> -- sh -c \
  'cat .ralph/agent-started 2>/dev/null; echo "---SEP---"; \
   cat .ralph/agent-done 2>/dev/null; echo "---SEP---"; \
   cat .ralph/agent-exit-code 2>/dev/null'
```

Parse the three sections split by `---SEP---`. Apply the same status logic as the local version:

| agent-started | agent-done | exit-code | Status |
|---|---|---|---|
| missing | missing | missing | `not_started` |
| present | missing | missing | `running` |
| present | present | `0` | `completed` |
| present | present | non-zero | `failed` |

**Edge cases:**
- `docker sandbox exec` fails (subprocess error) -> return `("sandbox_stopped", {})`
- `.ralph/` doesn't exist yet -> all sections empty -> `not_started`

### New status string: `sandbox_stopped`

Add handling in `_format_status_line()`:

```python
if status == "sandbox_stopped":
    return f"  {name}:  sandbox stopped"
```

### Existing `_check_local_agent_status()`

Rename the current `check_agent_status()` body to `_check_local_agent_status()`. No logic changes — just extracted into its own function.

## Fix 3: Tests

### Test 1 — `run()` registers entry (integration)

**File:** `tests/test_integration.py` (or new file if cleaner)

Test that executing the `run` flow with mock backends results in a `WorktreeEntry` in the registry:

```python
def test_run_registers_entry(tmp_path):
    # Set up: mock backends, real registry pointing at tmp_path
    # Execute: run the full planner -> executor -> handler flow
    # Assert: registry contains one entry with correct fields
    # Assert: registry file exists on disk
```

Uses mock backends (acceptable here — we're testing the CLI glue, not the backends). The key assertion is that `registry.add()` gets called with correct data.

### Test 2 — Sandbox status querying

**File:** `tests/test_status.py`

Test `_check_sandbox_agent_status()` with mocked `subprocess.run`:

```python
def test_sandbox_status_completed(tmp_path):
    # Mock subprocess to return all three markers
    # Assert: returns ("completed", {started, ended, duration, exit_code})

def test_sandbox_status_running(tmp_path):
    # Mock subprocess to return only agent-started
    # Assert: returns ("running", {started})

def test_sandbox_status_not_started(tmp_path):
    # Mock subprocess to return empty sections
    # Assert: returns ("not_started", {})

def test_sandbox_status_stopped(tmp_path):
    # Mock subprocess to raise CalledProcessError
    # Assert: returns ("sandbox_stopped", {})

def test_sandbox_status_failed(tmp_path):
    # Mock subprocess to return exit code 1
    # Assert: returns ("failed", {started, ended, duration, exit_code})
```

### Test 3 — Round-trip (register then status)

**File:** `tests/test_status.py`

Test the write-then-read path:

```python
def test_register_then_list(tmp_path):
    # Create registry, add entry via same code path as run()
    # Call list_entries()
    # Assert: entry appears with correct fields

def test_register_then_check_status_local(tmp_path):
    # Create registry + entry with worktree_path pointing at tmp_path
    # Write .ralph/ markers to tmp_path
    # Call check_agent_status(entry)
    # Assert: returns correct status
```

### Deferred (separate audit bead)

- Replace mock handlers with real backends in executor tests
- Test checkpoint persistence and resume
- Test concurrent registry access
- Test error recovery/rollback
- Audit all test files for mock-hiding-real-bugs patterns

## Files Changed

| File | Change |
|---|---|
| `src/superintendent/cli/main.py` | Add registration in `run()`, refactor `check_agent_status()`, add `_check_sandbox_agent_status()`, add `_check_local_agent_status()`, update `_format_status_line()` |
| `tests/test_status.py` | Add sandbox status tests, round-trip tests |
| `tests/test_integration.py` | Add registration test |

## Out of Scope

- Broader test audit (separate bead)
- Changing backend abstractions
- Volume-mount or push-based status approaches
- Checkpoint resume
