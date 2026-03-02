# Dolt-in-Sandbox Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable autonomous sandbox agents to use beads with a Dolt SQL server running inside each sandbox, replacing the defunct JSONL/no-db mode.

**Architecture:** Modify the sandbox template Dockerfile to include the Dolt binary, then replace `_init_beads_no_db()` with a new `_init_beads()` that starts a Dolt server inside the sandbox and runs `bd init --sandbox`. All changes are in step_handler.py and its tests — no protocol or state machine changes.

**Tech Stack:** Python (subprocess), Docker multi-stage builds, Dolt SQL server, beads CLI

---

### Task 1: Update template Dockerfile to include Dolt binary

**Files:**
- Modify: `src/superintendent/orchestrator/step_handler.py:152-170`
- Test: `tests/test_step_handler.py:438-520`

**Step 1: Write the failing test**

Update the existing template test to verify the Dockerfile includes the Dolt multi-stage copy. Add a new test in `TestPrepareTemplateHandler`:

```python
def test_template_dockerfile_includes_dolt(self):
    """Template Dockerfile includes Dolt binary via multi-stage copy."""
    docker = MockDockerBackend()
    ctx = ExecutionContext(backends=_mock_backends(docker=docker))
    handler = RealStepHandler(ctx)

    step = WorkflowStep(
        id="prepare_template",
        action="prepare_template",
        params={},
        depends_on=["create_worktree"],
    )
    handler.execute(step)

    assert len(docker.templates_built) == 1
    dockerfile_content = docker.templates_built[0][0]
    assert "dolthub/dolt" in dockerfile_content
    assert "COPY --from=" in dockerfile_content
    assert "/usr/local/bin/dolt" in dockerfile_content
```

**Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_step_handler.py::TestPrepareTemplateHandler::test_template_dockerfile_includes_dolt -v`
Expected: FAIL — current Dockerfile doesn't include Dolt

**Step 3: Write minimal implementation**

In `step_handler.py`, update `_handle_prepare_template()` at line 153:

```python
def _handle_prepare_template(self, step: WorkflowStep) -> StepResult:
    dockerfile = (
        "FROM dolthub/dolt:latest AS dolt-binary\n"
        f"FROM {SANDBOX_BASE_IMAGE}\n"
        "COPY --from=dolt-binary /usr/local/bin/dolt /usr/local/bin/dolt\n"
        "RUN npm install -g @beads/bd\n"
    )
    tag = "supt-sandbox:" + hashlib.sha256(dockerfile.encode()).hexdigest()[:12]

    docker = self._context.backends.docker
    if not docker.template_exists(tag) and not docker.build_template(
        dockerfile, tag
    ):
        return StepResult(
            success=False,
            step_id=step.id,
            message=f"Failed to build template: {tag}",
        )

    return StepResult(
        success=True,
        step_id=step.id,
        data={"template": tag},
    )
```

**Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_step_handler.py::TestPrepareTemplateHandler -v`
Expected: ALL PASS

**Step 5: Fix the cache-hit test**

The existing `test_skips_build_on_cache_hit` computes the old tag hash. Update it to use the new Dockerfile content:

```python
def test_skips_build_on_cache_hit(self):
    """When template already exists, skip the build."""
    import hashlib

    from superintendent.orchestrator.step_handler import SANDBOX_BASE_IMAGE

    dockerfile = (
        "FROM dolthub/dolt:latest AS dolt-binary\n"
        f"FROM {SANDBOX_BASE_IMAGE}\n"
        "COPY --from=dolt-binary /usr/local/bin/dolt /usr/local/bin/dolt\n"
        "RUN npm install -g @beads/bd\n"
    )
    tag = "supt-sandbox:" + hashlib.sha256(dockerfile.encode()).hexdigest()[:12]

    docker = MockDockerBackend(existing_templates={tag})
    ctx = ExecutionContext(backends=_mock_backends(docker=docker))
    handler = RealStepHandler(ctx)

    step = WorkflowStep(
        id="prepare_template",
        action="prepare_template",
        params={},
        depends_on=["create_worktree"],
    )
    result = handler.execute(step)

    assert result.success is True
    assert result.data["template"] == tag
    assert len(docker.templates_built) == 0  # no build needed
```

**Step 6: Run all template tests**

Run: `uv run pytest tests/test_step_handler.py::TestPrepareTemplateHandler -v`
Expected: ALL PASS

**Step 7: Commit**

```bash
git add src/superintendent/orchestrator/step_handler.py tests/test_step_handler.py
git commit -m "feat: add Dolt binary to sandbox template via multi-stage build"
```

---

### Task 2: Replace `_init_beads_no_db()` with Dolt-based `_init_beads()`

**Files:**
- Modify: `src/superintendent/orchestrator/step_handler.py:333-396`
- Test: `tests/test_step_handler.py:705-844`

**Step 1: Write the failing tests**

Replace the three existing beads init tests (`test_runs_bd_init_no_db_for_sandbox`, `test_fallback_writes_config_when_bd_missing`, `test_beads_init_for_container`) with new tests:

```python
class TestInitializeStateHandler:
    # ... keep test_initializes_ralph_state, test_missing_worktree_path_fails,
    #     test_no_beads_init_for_local unchanged ...

    def test_starts_dolt_and_inits_beads_for_sandbox(self, tmp_path):
        """For sandbox targets, starts Dolt server and runs bd init --sandbox."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        # Should have exec'd: bd dolt start, health check, bd init
        assert len(docker.executed) >= 2
        exec_cmds = [cmd for _, cmd in docker.executed]
        assert any("bd dolt start" in cmd for cmd in exec_cmds)
        assert any("bd init" in cmd and "--sandbox" in cmd for cmd in exec_cmds)

    def test_beads_init_includes_skip_hooks_and_prefix(self, tmp_path):
        """bd init command includes --skip-hooks and -p flags."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        handler.execute(step)

        exec_cmds = [cmd for _, cmd in docker.executed]
        init_cmd = next(c for c in exec_cmds if "bd init" in c)
        assert "--skip-hooks" in init_cmd
        assert "-p" in init_cmd
        assert "my-repo" in init_cmd
        assert "-q" in init_cmd

    def test_dolt_health_check_retries_then_succeeds(self, tmp_path):
        """Health check retries on failure, then succeeds."""
        call_count = 0
        original_exec_results = {}

        class HealthCheckDockerBackend(MockDockerBackend):
            """Mock that fails health check twice then succeeds."""

            def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
                nonlocal call_count
                self.executed.append((name, cmd))
                if "select 1" in cmd:
                    call_count += 1
                    if call_count < 3:
                        return (1, "connection refused")
                    return (0, "1")
                return (0, "")

        docker = HealthCheckDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert call_count == 3  # failed twice, succeeded on third

    def test_dolt_health_check_timeout_fails(self, tmp_path):
        """If health check never succeeds, the step fails."""

        class AlwaysFailHealthCheck(MockDockerBackend):
            def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
                self.executed.append((name, cmd))
                if "select 1" in cmd:
                    return (1, "connection refused")
                return (0, "")

        docker = AlwaysFailHealthCheck()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is False
        assert "dolt" in result.message.lower() or "health" in result.message.lower()

    def test_beads_init_for_container(self, tmp_path):
        """Container targets also get Dolt startup and beads initialization."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_container"] = {"container_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        exec_cmds = [cmd for _, cmd in docker.executed]
        assert any("bd dolt start" in cmd for cmd in exec_cmds)
        assert any("bd init" in cmd for cmd in exec_cmds)
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_step_handler.py::TestInitializeStateHandler -v`
Expected: New tests FAIL (old method doesn't exec into sandbox)

**Step 3: Write the implementation**

Replace `_init_beads_no_db()` and update `_handle_initialize_state()` in `step_handler.py`:

```python
def _handle_initialize_state(self, step: WorkflowStep) -> StepResult:
    wt_output = self._context.step_outputs.get("create_worktree")
    if wt_output is None:
        return StepResult(
            success=False,
            step_id=step.id,
            message="Missing create_worktree output (worktree_path)",
        )

    worktree_path = Path(wt_output["worktree_path"])
    task = step.params.get("task", "")
    ralph_dir = worktree_path / ".ralph"

    ralph_state = RalphState(ralph_dir)
    ralph_state.init(task=task)

    # Initialize beads with Dolt for sandbox/container targets
    is_sandbox = "prepare_sandbox" in self._context.step_outputs
    is_container = "prepare_container" in self._context.step_outputs
    if is_sandbox or is_container:
        env_name = ""
        if is_sandbox:
            env_name = self._context.step_outputs["prepare_sandbox"]["sandbox_name"]
        else:
            env_name = self._context.step_outputs["prepare_container"]["container_name"]
        repo_name = Path(
            self._context.step_outputs.get("validate_repo", {}).get("repo_path", "")
        ).name

        init_result = self._init_beads(env_name, repo_name)
        if not init_result:
            return StepResult(
                success=False,
                step_id=step.id,
                message=f"Failed to initialize beads/Dolt in {env_name}",
            )

    return StepResult(
        success=True,
        step_id=step.id,
        data={"ralph_dir": str(ralph_dir)},
    )

def _init_beads(self, env_name: str, repo_name: str) -> bool:
    """Initialize beads with Dolt SQL server inside a sandbox/container.

    Starts the Dolt server, waits for it to be healthy, then runs bd init.
    Returns True on success, False on failure.
    """
    import time

    docker = self._context.backends.docker

    # 1. Start Dolt server
    docker.exec_in_sandbox(env_name, "bd dolt start")

    # 2. Health-check with retry
    max_retries = 10
    for attempt in range(max_retries):
        exit_code, _ = docker.exec_in_sandbox(
            env_name,
            "dolt --host 127.0.0.1 --port 3307 --no-tls sql -q 'select 1;'",
        )
        if exit_code == 0:
            break
        if attempt < max_retries - 1:
            time.sleep(1)
    else:
        return False

    # 3. Initialize beads
    exit_code, _ = docker.exec_in_sandbox(
        env_name,
        f"bd init --sandbox --skip-hooks -p {repo_name} -q",
    )
    return exit_code == 0
```

**Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_step_handler.py::TestInitializeStateHandler -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add src/superintendent/orchestrator/step_handler.py tests/test_step_handler.py
git commit -m "feat: replace no-db beads init with Dolt server startup in sandbox"
```

---

### Task 3: Update dry-run tests for new beads init flow

**Files:**
- Test: `tests/test_dry_run.py`

The dry-run flow exercises `DryRunDockerBackend.exec_in_sandbox()` which records commands. The existing tests don't assert on beads init commands, so they should still pass. But we should verify and add a test for the new exec commands.

**Step 1: Run existing dry-run tests to confirm they still pass**

Run: `uv run pytest tests/test_dry_run.py -v`
Expected: ALL PASS (dry-run uses DryRunDockerBackend which returns (0, "") for exec_in_sandbox)

**Step 2: Write a test for the new beads init dry-run commands**

Add to `TestDryRunSandboxCommands`:

```python
def test_sandbox_flow_records_beads_init_commands(self) -> None:
    """Dry-run records Dolt startup and beads init exec commands."""
    backends = _dryrun_backends()
    ctx = ExecutionContext(backends=backends)
    handler = RealStepHandler(ctx)
    executor = Executor(handler=handler)

    plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
    executor.run(plan)

    docker = backends.docker
    assert isinstance(docker, DryRunDockerBackend)
    exec_cmds = [c for c in docker.commands if "exec" in c]
    assert any("bd dolt start" in c for c in exec_cmds)
    assert any("bd init" in c and "--sandbox" in c for c in exec_cmds)
```

**Step 3: Run test to verify it passes**

Run: `uv run pytest tests/test_dry_run.py::TestDryRunSandboxCommands::test_sandbox_flow_records_beads_init_commands -v`
Expected: PASS

**Step 4: Commit**

```bash
git add tests/test_dry_run.py
git commit -m "test: add dry-run assertion for Dolt/beads init commands"
```

---

### Task 4: Run full test suite and fix any breakage

**Step 1: Run all tests**

Run: `uv run pytest -v`
Expected: ALL PASS

**Step 2: Run linting**

Run: `uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: Clean

**Step 3: Fix any failures**

Common issues to watch for:
- `test_full_plan_execution` tests use MockDockerBackend but now `_init_beads()` calls `exec_in_sandbox()` — MockDockerBackend already supports this (returns (0, ""))
- The `time.sleep(1)` in `_init_beads()` health check won't trigger in mock tests since MockDockerBackend returns (0, "") immediately
- Dry-run `exec_in_sandbox` returns (0, "") so health check passes on first try

**Step 4: Commit any fixes**

```bash
git add -u
git commit -m "fix: resolve test breakage from Dolt-in-sandbox changes"
```

---

### Task 5: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/BEADS_BEST_PRACTICES.md`

**Step 1: Update CLAUDE.md**

Remove references to `no-db: true` and `no-daemon: true`. Replace with guidance about Dolt server mode and `--sandbox --json` flags.

In the "Autonomous Agent Rules" section, change:
```
**Docker sandbox agents:** Use `no-db: true` and `no-daemon: true` in config.yaml.
```
To:
```
**Docker sandbox agents:** Beads runs with a Dolt SQL server inside each sandbox.
Agents should use `--sandbox --json` flags with bd commands.
```

**Step 2: Update docs/BEADS_BEST_PRACTICES.md**

Rewrite the Docker sandbox configuration section to describe the new Dolt-based setup:
- Remove the `no-db: true` / `no-daemon: true` config example
- Document that superintendent starts Dolt automatically during `initialize_state`
- Update the troubleshooting table to replace JSONL-related entries with Dolt-related entries

**Step 3: Commit**

```bash
git add CLAUDE.md docs/BEADS_BEST_PRACTICES.md
git commit -m "docs: update sandbox beads guidance for Dolt server mode"
```

---

### Task 6: Update memory files

**Files:**
- Modify: `/Users/brendan/.claude/projects/-Users-brendan-projects-superintendent/memory/MEMORY.md`

**Step 1: Update memory**

Remove outdated entries:
- "No Dolt/DB: beads must use JSONL mode" under Docker Sandbox Limitations
- References to `no-db: true`, `no-daemon: true`

Add new entries:
- Beads v0.57.0 requires Dolt SQL server (JSONL/SQLite removed in v0.50+)
- Sandboxes run Dolt inside container, initialized during `initialize_state` step
- Agent convention: `--sandbox --json` flags for all `bd` commands
- `bd init --sandbox --skip-hooks -p {prefix} -q` for sandbox initialization

**Step 2: Commit (memory files are not in the repo, no git needed)**

---

### Task 7: Final verification

**Step 1: Run full CI checklist**

```bash
uv run pytest -v
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

**Step 2: Review the diff**

```bash
git diff main --stat
git log --oneline main..HEAD
```

Expected commits:
1. `feat: add Dolt binary to sandbox template via multi-stage build`
2. `feat: replace no-db beads init with Dolt server startup in sandbox`
3. `test: add dry-run assertion for Dolt/beads init commands`
4. `fix: resolve test breakage from Dolt-in-sandbox changes` (if needed)
5. `docs: update sandbox beads guidance for Dolt server mode`
