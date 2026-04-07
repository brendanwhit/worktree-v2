# Status Tracker Fix — Design Spec

## Problem

`superintendent run` never registers entries in the `WorktreeRegistry`. The registry file (`~/.claude/superintendent-registry.json`) is never created, so `superintendent list`, `superintendent status`, `superintendent resume`, and `superintendent cleanup` all show nothing — regardless of target (sandbox, container, local).

Tests don't catch this because executor/integration tests use mock handlers that never touch the registry, and status tests only exercise the read/format side.

### Marker files are on the host (not in the container)

The `run_agent` method in `docker.py` (line 152-165) wraps the agent command with shell that writes `.ralph/agent-started`, `.ralph/agent-done`, and `.ralph/agent-exit-code` to the **host filesystem** via `terminal.spawn()`. The `date` and `echo` commands run on the host, not inside the container. This means:

- The existing `check_agent_status()` logic (reading from `entry.worktree_path/.ralph/`) will work for all targets once entries are registered.
- No `docker sandbox exec` is needed to read markers.
- However, for sandbox entries showing "running" status, we should verify the sandbox is actually alive (vs. the terminal being killed). And when the worktree has been cleaned up, we should distinguish "worktree missing" from "sandbox stopped."

## Fix 1: Register entries in `run()`

**File:** `src/superintendent/cli/main.py`, `run()` function

After `executor.run(plan)` succeeds (line 494) and after the failure-exit check (line 500), but before the success output (line 502), add registration:

```python
# Register the entry
registry = get_default_registry()
worktree_path = context.step_outputs.get("create_worktree", {}).get("worktree_path", "")
branch_name = plan.metadata.get("branch", "")
repo_name = plan.metadata.get("repo_name", _extract_repo_name(repo))
name = _branch_to_slug(branch_name) if branch_name else repo_name

# Only set sandbox_name for sandbox/container targets
target_val = plan.metadata.get("target")
if target_val == "sandbox":
    env_name = plan.metadata.get("sandbox_name")
elif target_val == "container":
    env_name = plan.metadata.get("container_name")
else:
    env_name = None

entry = WorktreeEntry(
    name=name,
    repo=repo,
    branch=branch_name,
    worktree_path=worktree_path,
    sandbox_name=env_name,
)
registry.add(entry)
```

This ensures:
- Dry runs skip registration (early return on line 492)
- Failed runs skip registration (early exit on line 500)
- Only successful runs register
- Local targets don't get a spurious `sandbox_name` (the planner sets `metadata["sandbox_name"]` for ALL non-container targets including local, line 47-48 of planner.py)

### Slug consistency

The step handler uses `branch.replace("/", "-")` (line 173 of step_handler.py) to create the worktree directory name. The CLI's `_branch_to_slug()` does additional sanitization (strips non-alphanumeric chars, collapses dashes). For typical branch names like `agent/repo-name`, both produce the same result. But for branches with special characters, the entry `name` may not match the directory name.

This is acceptable — the entry `name` is a display/lookup key, not a filesystem path. The `worktree_path` field holds the actual path.

## Fix 2: Sandbox liveness check

**File:** `src/superintendent/cli/main.py`

When `check_agent_status()` returns `"running"` and the entry has a `sandbox_name`, verify the sandbox is actually alive by checking `docker sandbox ls`. This distinguishes:

- **Agent truly running**: sandbox appears in `docker sandbox ls` output
- **Terminal killed**: sandbox is gone but `agent-done` marker was never written

Add a lightweight helper:

```python
def _is_sandbox_alive(sandbox_name: str) -> bool:
    """Check if a sandbox is still listed by Docker."""
    result = subprocess.run(
        ["docker", "sandbox", "ls", "-q"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return False
    return sandbox_name in result.stdout.splitlines()
```

Update `check_agent_status()`:

```python
def check_agent_status(entry: WorktreeEntry) -> tuple[str, dict[str, str]]:
    # ... existing marker-reading logic ...

    # If markers say "running" but sandbox is gone, it was killed
    if status == "running" and entry.sandbox_name:
        if not _is_sandbox_alive(entry.sandbox_name):
            return ("sandbox_stopped", details)

    return (status, details)
```

Also update `_format_status_line()` to handle the new `"sandbox_stopped"` status:

```python
elif status == "sandbox_stopped":
    if "start_time" in details:
        info_parts.append(f"started {_time_ago(details['start_time'])}")
```

And update the `status` command's worktree-missing check (line 897) to show a more useful message for sandbox entries:

```python
if not worktree.exists():
    if entry.sandbox_name:
        typer.echo(f"{entry.name}:  worktree removed")
    else:
        typer.echo(f"{entry.name}:  worktree missing")
    continue
```

## Fix 3: Tests

### Test 1 — `run()` registers entry

**File:** `tests/test_integration.py`

Test that executing the `run` flow with mock backends results in a `WorktreeEntry` in the registry:

```python
def test_run_registers_entry(tmp_path):
    # Set up: mock backends, real registry pointing at tmp_path
    # Build a plan via Planner for sandbox target
    # Execute via Executor + RealStepHandler (with mock backends)
    # Then run the same registration code from run()
    # Assert: registry contains one entry with correct name, repo, branch, worktree_path, sandbox_name
    # Assert: registry file exists on disk
```

Also test that `sandbox_name` is NOT set for local target:

```python
def test_run_local_no_sandbox_name(tmp_path):
    # Same as above but target=local
    # Assert: entry.sandbox_name is None
```

### Test 2 — Sandbox liveness check

**File:** `tests/test_status.py`

Test `_is_sandbox_alive()`:

```python
def test_sandbox_alive(monkeypatch):
    # Mock subprocess.run to return sandbox name in output
    # Assert: returns True

def test_sandbox_not_alive(monkeypatch):
    # Mock subprocess.run to return empty output
    # Assert: returns False

def test_sandbox_check_docker_error(monkeypatch):
    # Mock subprocess.run to return non-zero exit
    # Assert: returns False
```

Test that `check_agent_status()` returns `"sandbox_stopped"` when markers say running but sandbox is gone:

```python
def test_running_but_sandbox_gone(tmp_path, monkeypatch):
    # Create .ralph/agent-started marker (no agent-done)
    # Entry has sandbox_name set
    # Mock _is_sandbox_alive to return False
    # Assert: check_agent_status returns ("sandbox_stopped", ...)
```

### Test 3 — Round-trip (register then status)

**File:** `tests/test_status.py`

Test the write-then-read path end to end:

```python
def test_register_then_list(tmp_path):
    # Create registry at tmp_path, add entry
    # Call list_entries()
    # Assert: entry appears with correct fields

def test_register_then_check_status_local(tmp_path):
    # Create registry + entry with worktree_path pointing at tmp_path
    # Write .ralph/ markers to tmp_path
    # Call check_agent_status(entry)
    # Assert: returns correct status based on markers
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
| `src/superintendent/cli/main.py` | Add registration in `run()`, add `_is_sandbox_alive()`, update `check_agent_status()` with liveness check, update `_format_status_line()` for `sandbox_stopped`, update `status` command worktree-missing message |
| `tests/test_status.py` | Add sandbox liveness tests, round-trip tests |
| `tests/test_integration.py` | Add registration tests for sandbox and local targets |

## Out of Scope

- Broader test audit (separate bead)
- Changing backend abstractions
- Volume-mount or push-based status approaches
- Checkpoint resume
- `docker sandbox exec` for reading markers (unnecessary — markers are on host)
