# Dolt-in-Sandbox Design

> Beads v0.50+ removed JSONL and SQLite backends. Dolt SQL server is now the
> only storage backend. Sandboxes must run a Dolt server for beads to function.

## Goal

Enable autonomous sandbox agents to use beads for task tracking by running a
Dolt SQL server inside each sandbox. Phase 1 is per-sandbox Dolt; multi-agent
coordination via shared Dolt is deferred to a future design.

## Template Image Changes

Extend the sandbox template with the Dolt binary via multi-stage build:

```dockerfile
FROM dolthub/dolt:latest AS dolt-binary
FROM docker/sandbox-templates:claude-code
COPY --from=dolt-binary /usr/local/bin/dolt /usr/local/bin/dolt
RUN npm install -g @beads/bd
```

This adds ~100MB for the Dolt binary. The existing image tag hashing in
`_handle_prepare_template()` handles cache invalidation automatically.

## Beads Init Step

The current `_init_beads_no_db()` method is replaced. The new flow during the
`initialize_state` workflow step:

1. **Start Dolt server** inside the sandbox:
   ```bash
   docker sandbox exec {name} sh -c 'bd dolt start'
   ```

2. **Health-check** — poll until Dolt responds on port 3307:
   ```bash
   docker sandbox exec {name} sh -c \
     'dolt --host 127.0.0.1 --port 3307 --no-tls sql -q "select 1;"'
   ```
   Retry with backoff, fail the step on timeout.

3. **Init beads in server mode**:
   ```bash
   docker sandbox exec {name} sh -c \
     'bd init --sandbox --skip-hooks -p {repo_name} -q'
   ```
   Beads auto-detects the running Dolt server on port 3307.

4. **Agent convention** — all `bd` calls by the agent use `--sandbox --json`
   for structured output and disabled auto-sync.

## Workflow State Machine

No new workflow states. All changes are within the existing `INITIALIZING_STATE`
step:

- Rename `_init_beads_no_db()` → `_init_beads()`
- Sub-steps: create `.ralph/`, start Dolt, health-check, `bd init`
- Failure: if Dolt fails to start or health check times out → `FAILED`

## Backend / Testing Impact

**No protocol changes.** `exec_in_sandbox()` handles all new commands.

**Mock/DryRun:**
- `MockStepHandler` — returns canned success (same as today)
- `DryRunStepHandler` — prints the new commands

**Tests to update:**
- `test_step_handler.py` — assert Dolt startup + `bd init --sandbox` sequence
- `test_dry_run.py` — update expected dry-run output
- `test_integration.py` / `test_e2e.py` — update beads init assertions if applicable

**Untouched:**
- `DockerBackend` protocol (no new methods)
- `AuthBackend`, `GitBackend`, `TerminalBackend`
- `BackendMode` enum, `create_backends()` factory
- Planner, Executor, WorkflowState enum

## Documentation Cleanup

- `CLAUDE.md` — remove `no-db: true` / `no-daemon: true` guidance
- `docs/BEADS_BEST_PRACTICES.md` — rewrite Docker sandbox section
- Memory files — update beads architecture notes

## Key beads flags

| Flag | Scope | Purpose |
|------|-------|---------|
| `--sandbox` | Global | Disables auto-sync |
| `--json` | Global | Structured JSON output for agent parsing |
| `--skip-hooks` | `bd init` | Skip git hooks installation |
| `-p {prefix}` | `bd init` | Set issue prefix |
| `-q` | `bd init` | Quiet mode |
| `--server` | `bd init` | No-op (server mode always on), can omit |
