# Test Suite Audit Report

**Date:** 2026-04-08
**Codebase:** v0.3.0 (post PRs #21–#25)
**Test count:** 944 (938 existing + 6 CLI registration + 6 token resolution — post this PR)
**Trigger:** superintendent-388 — `superintendent run` never registered entries in WorktreeRegistry, but all tests passed. Root cause: CLI tests mocked Planner+Executor, so registration code ran against MagicMocks instead of real step_outputs.

## Executive Summary

The test suite has strong unit-level coverage (87–100% for most modules) but suffers from two systemic patterns that allow production bugs to hide:

1. **CLI tests mock the orchestration layer** — Planner and Executor are replaced with MagicMocks, so the registration, output, and error handling code in `run()` executes against fake data.

2. **Step handler bypasses its own backend abstraction** — `_resolve_token()`, `_get_repo_identifier()`, and `_gather_branch_context()` call `subprocess.run` directly instead of going through the git backend. Mock backends are therefore blind to these code paths.

This PR adds 12 new tests fixing the two critical gaps.

---

## Critical Gaps Found and Fixed

### Gap 1: CLI `run()` registration never tested end-to-end (CRITICAL) — FIXED

**Problem:** `test_cli.py::TestRunCommand` mocks both `Planner` and `Executor`. Registration code (lines 397–422 of main.py) executes against MagicMock metadata, not real plan/context outputs. `step_outputs` is never populated, so `worktree_path` extraction returns empty string.

**Root cause of original bug:** Registration depended on `context.step_outputs["create_worktree"]["worktree_path"]`, but since Executor was mocked, `step_outputs` was never populated.

**Fix:** `TestCLIRunRegistration` (6 tests in test_integration.py) — exercises `main.run()` via CliRunner with real Planner/Executor/StepHandler but mock backends. Verifies registry entries on disk for all targets, failure cases, and custom names.

### Gap 2: Token resolution and repo identification completely untested (CRITICAL) — FIXED

**Problem:** `_get_repo_identifier()` (step_handler.py:407-432) calls `subprocess.run(["git", "remote", "get-url", "origin"])` directly — not through the git backend. `_resolve_token()` (step_handler.py:372-405) chains through `_get_repo_identifier()` → `TokenStore.resolve()` for repo-specific token lookup. `_handle_validate_auth()` (step_handler.py:113-158) has a whole branch (lines 126-142) for repo-specific tokens that was never exercised.

This means:
- SSH URL parsing (`git@github.com:owner/repo.git`) — **untested**
- HTTPS URL parsing (`https://github.com/owner/repo.git`) — **untested**
- Non-GitHub remote handling — **untested**
- `org_requires_explicit` guard (prevents using personal token for org repos) — **untested**
- Auth fallback when no token AND `setup_git_auth` fails — **untested**

**Fix:** `TestResolveTokenChain` (6 tests in test_step_handler.py) — mocks `subprocess.run` at the process level to test URL parsing, repo-specific token resolution, org guard, and auth fallback failure.

### Gap 3: `TestRegistrationIntegration` duplicates rather than tests CLI logic (HIGH)

**Problem:** `test_integration.py::TestRegistrationIntegration._run_and_register()` copies the registration logic from `main.run()` rather than calling it. Validates the *pattern* but not the CLI's actual implementation.

**Status:** Mitigated by Gap 1 fix. TestRegistrationIntegration remains as a secondary check.

### Gap 4: `_gather_branch_context()` bypasses git backend (MEDIUM)

**Problem:** `_gather_branch_context()` (step_handler.py:543-612) calls `subprocess.run` directly for `git log` and `gh pr list`. These calls bypass the git backend mock entirely. The function is never tested because MockGitBackend repos don't have real git histories.

**Status:** Acknowledged but not fixed — this is informational context for agent prompts, not workflow-critical. A bug here would produce a worse prompt, not a broken workflow.

### Gap 5: Executor checkpoints never persisted to disk (MEDIUM)

**Problem:** `Executor._save_checkpoint()` appends to an in-memory list. `checkpoint.py` has disk persistence functions, but the Executor never calls them.

**Status:** Acknowledged — design decision, not a test gap. If checkpoint-based resume is built, this needs testing.

---

## Audit by Test File

### test_auth_backend.py (24 tests)
- **Tests:** AuthBackend protocol, Mock/DryRun/Real implementations
- **Mocks:** subprocess.run for Real; MockDockerBackend for token injection
- **Severity:** Low — appropriate mock level

### test_backend_factory.py (7 tests)
- **Tests:** BackendMode enum, `create_backends()` factory
- **Gaps:** None
- **Severity:** N/A

### test_beads_source.py (17 tests)
- **Tests:** BeadsSource adapter wrapping `bd` CLI
- **Mocks:** subprocess.run
- **Gaps:** Mock JSON may diverge from real `bd` output
- **Severity:** Low

### test_checkpoint.py (17 tests)
- **Tests:** WorkflowCheckpoint save/load to filesystem
- **Mocks:** None — real filesystem
- **Gaps:** None
- **Severity:** N/A

### test_cli.py (53 tests)
- **Tests:** CLI subcommands, helper functions, safety gates
- **Mocks:** **Planner and Executor fully mocked** in run tests
- **Gaps:** **CRITICAL** — registration code runs against MagicMock metadata
- **Severity:** CRITICAL — fixed by TestCLIRunRegistration

### test_detect_source.py (16 tests)
- **Gaps:** None
- **Severity:** N/A

### test_docker_backend.py (36 tests)
- **Tests:** DockerBackend protocol, all implementations
- **Gaps:** RealDockerBackend uncovered (requires Docker daemon — acceptable)
- **Severity:** Low

### test_dry_run.py (28 tests)
- **Tests:** Full pipeline with DryRun backends
- **Gaps:** DryRun commands not validated as executable
- **Severity:** Medium

### test_e2e.py (28 tests)
- **Tests:** CLI dry-run flow with real Planner
- **Gaps:** Name implies E2E but only tests dry-run
- **Severity:** Medium — consider renaming

### test_executor.py (24 tests)
- **Tests:** Executor state machine, checkpoints
- **Mocks:** MockHandler returns canned StepResults
- **Gaps:** MockHandler does nothing — no real side effects
- **Severity:** High — mitigated by test_integration.py

### test_explain_flag.py (10 tests)
- **Gaps:** None
- **Severity:** Low

### test_git_backend.py (76+ tests)
- **Tests:** GitBackend protocol, URL parsing, Mock/DryRun/Real
- **Gaps:** RealGitBackend.clone_for_sandbox (125 lines) fully uncovered — but requires real git (acceptable)
- **Severity:** Low

### test_integration.py (36+ tests, post this PR)
- **Tests:** Full Planner → Executor → StepHandler → MockBackends pipeline
- **Mocks:** All mock backends
- **Gaps:** TestRegistrationIntegration duplicates CLI logic (mitigated by TestCLIRunRegistration)
- **Severity:** High → mitigated

### test_markdown_source.py (25 tests)
- **Gaps:** None
- **Severity:** N/A

### test_models.py (34 tests)
- **Gaps:** None
- **Severity:** N/A

### test_orchestrator.py (30+ tests)
- **Tests:** Multi-agent orchestration
- **Gaps:** All backends mocked
- **Severity:** Medium — newer code, less production exposure

### test_planner.py (25+ tests)
- **Gaps:** None
- **Severity:** N/A

### test_ralph_state.py (22 tests)
- **Gaps:** None
- **Severity:** N/A

### test_registry.py (20+ tests)
- **Gaps:** None — thorough with real filesystem
- **Severity:** N/A

### test_repo_info.py (23 tests)
- **Gaps:** None
- **Severity:** N/A

### test_reporter.py (30+ tests)
- **Gaps:** None
- **Severity:** N/A

### test_single_source.py (11 tests)
- **Gaps:** None
- **Severity:** N/A

### test_slash_commands.py (8 tests)
- **Gaps:** Checks file existence only
- **Severity:** Low

### test_smart_cleanup.py (20+ tests)
- **Gaps:** None
- **Severity:** Low

### test_speckit_source.py (20+ tests)
- **Gaps:** None
- **Severity:** N/A

### test_status.py (40+ tests)
- **Tests:** Status command, liveness checks, git tags, caching
- **Mocks:** `_is_sandbox_alive`, subprocess, git backend
- **Gaps:** Sandbox liveness doesn't test real `docker sandbox ls` parsing
- **Severity:** Medium

### test_step_handler.py (76+ tests, post this PR)
- **Tests:** All 9 step handlers, worktree reuse logic, token resolution chain
- **Mocks:** Mock backends + subprocess mocking for token tests
- **Gaps:**
  - `_gather_branch_context()` calls subprocess directly — untested (medium)
  - Merge conflict/fetch failure messages uncovered (acceptable)
- **Severity:** Medium → improved by TestResolveTokenChain

### test_strategy.py (10+ tests)
- **Gaps:** None
- **Severity:** N/A

### test_task_source.py (15+ tests)
- **Gaps:** None
- **Severity:** N/A

### test_terminal_backend.py (20+ tests)
- **Gaps:** Real terminal spawning (requires GUI — acceptable)
- **Severity:** Low

### test_token_store.py (20+ tests)
- **Gaps:** `introspect_token_permissions()` (lines 162-186) untested — calls GitHub API
- **Severity:** Medium — token CLI commands untested, but they're manual operations

### test_verbosity.py (15+ tests)
- **Gaps:** None
- **Severity:** Low

### test_workflow.py (25+ tests)
- **Gaps:** None
- **Severity:** N/A

---

## Systemic Patterns

### Pattern: subprocess.run bypassing backend abstraction

The step handler has 4 direct `subprocess.run` calls that bypass the git backend:

| Line | Function | What it calls | Risk |
|------|----------|--------------|------|
| 393 | `_resolve_token()` | `gh auth token` | Low — fallback chain |
| 410 | `_get_repo_identifier()` | `git remote get-url origin` | **High** — URL parsing |
| 557 | `_gather_branch_context()` | `git log origin/main..HEAD` | Medium — informational |
| 578 | `_gather_branch_context()` | `gh pr list --head <branch>` | Medium — informational |

Mock backends are blind to these. The first two are now tested via `TestResolveTokenChain`. The latter two are informational and lower priority.

### Pattern: CLI tests mock orchestration instead of backends

`test_cli.py::TestRunCommand` patches `Planner` and `Executor` at the class level. This tests CLI argument parsing and output formatting, but not the actual orchestration flow. The registration code, error handling, and output logic run against MagicMock objects.

This is now mitigated by `TestCLIRunRegistration` which patches only `create_backends` and `get_default_registry` — leaving the real orchestration chain intact.

---

## Remaining Acceptable Gaps

These are uncovered code paths that are acceptable to leave untested:

- **RealDockerBackend / RealGitBackend implementations** — require Docker daemon and real git repos
- **CLI token add/update/remove commands** — manual user operations with immediate feedback
- **`_gather_branch_context()`** — informational prompt enrichment, not workflow-critical
- **Exception handlers** for missing `gh` CLI, timeouts, permission errors — defensive fallbacks
- **`--version` flag**, entry point, empty-store messages — trivial UI
