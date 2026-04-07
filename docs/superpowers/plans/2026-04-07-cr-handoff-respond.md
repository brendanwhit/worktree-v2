# CR Handoff: `superintendent respond` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable agents to hand off PR context and let new agents respond to code review comments via `superintendent respond`.

**Architecture:** Four changes — rename `.ralph/` to `.superintendent/` throughout, add pr-context.md write instruction to autonomous agent prompts, add `superintendent respond` command that spawns agents in existing worktrees with PR context, and guard open-PR entries from cleanup. The respond command bypasses the Executor/StepHandler pipeline (like `resume`) since it only spawns an agent in an existing worktree.

**Tech Stack:** Python, Typer CLI, `gh` CLI for GitHub API

**Spec:** `docs/superpowers/specs/2026-04-07-cr-handoff-respond-design.md`

---

### Task 1: Rename `.ralph/` to `.superintendent/` — state module

**Files:**
- Rename: `src/superintendent/state/ralph.py` → `src/superintendent/state/agent_state.py`
- Modify: `src/superintendent/state/__init__.py:1-2`
- Rename: `tests/test_ralph_state.py` → `tests/test_agent_state.py`

- [ ] **Step 1: Rename the source file and update class/variable names**

Rename `src/superintendent/state/ralph.py` to `src/superintendent/state/agent_state.py`. Inside the file:
- Module docstring: `"""Agent state (.superintendent/ directory) management."""`
- Class: `RalphState` → `AgentState`
- Constructor parameter: `ralph_dir` → `state_dir`
- All `self.ralph_dir` → `self.state_dir`
- Docstrings: `.ralph/` → `.superintendent/`

```python
"""Agent state (.superintendent/ directory) management."""

import json
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


class AgentState:
    """Manages the .superintendent/ directory for an agent."""

    def __init__(self, state_dir: Path) -> None:
        self.state_dir = state_dir

    @property
    def is_initialized(self) -> bool:
        return self.state_dir.is_dir()

    @property
    def config(self) -> dict[str, Any] | None:
        """Load config from config.json. Returns None if not initialized."""
        config_path = self.state_dir / "config.json"
        if not config_path.exists():
            return None
        result: dict[str, Any] = json.loads(config_path.read_text())
        return result

    def init(
        self,
        task: str,
        execution_mode: str = "unknown",
        bead_id: str | None = None,
    ) -> None:
        """Initialize the .superintendent/ directory with default files.

        Idempotent: does not overwrite existing files.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)

        config_path = self.state_dir / "config.json"
        if not config_path.exists():
            config = {
                "execution_mode": execution_mode,
                "task": task,
                "bead_id": bead_id,
                "created_at": _now_iso(),
            }
            config_path.write_text(json.dumps(config, indent=2))

        progress_path = self.state_dir / "progress.md"
        if not progress_path.exists():
            progress_path.write_text("# Progress\n\n")

        guardrails_path = self.state_dir / "guardrails.md"
        if not guardrails_path.exists():
            guardrails_path.write_text(
                "# Guardrails\n\nLearned failure patterns and things to avoid.\n"
            )

        task_path = self.state_dir / "worktree-task.md"
        if not task_path.exists():
            task_path.write_text(f"# Task\n\n{task}\n")

    def reset(self) -> None:
        """Remove the .superintendent/ directory entirely for sandbox reuse."""
        if self.state_dir.exists():
            shutil.rmtree(self.state_dir)

    def save_config(self, config: dict[str, Any]) -> None:
        """Save a config dict to config.json."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        (self.state_dir / "config.json").write_text(json.dumps(config, indent=2))

    def update_progress(self, entry: str) -> None:
        """Append a timestamped entry to progress.md."""
        progress_path = self.state_dir / "progress.md"
        timestamp = _now_iso()
        with open(progress_path, "a") as f:
            f.write(f"- [{timestamp}] {entry}\n")
```

- [ ] **Step 2: Update `src/superintendent/state/__init__.py`**

```python
"""State management: workflow state machine, registry, checkpoints, and .superintendent/ directory."""
```

- [ ] **Step 3: Rename test file and update references**

Rename `tests/test_ralph_state.py` to `tests/test_agent_state.py`. Find-and-replace:
- `from superintendent.state.ralph import RalphState` → `from superintendent.state.agent_state import AgentState`
- `RalphState` → `AgentState`
- `.ralph` → `.superintendent`
- `ralph_dir` → `state_dir`
- Class names: `TestRalphState*` → `TestAgentState*`
- Module docstring: update to reference `.superintendent/`

- [ ] **Step 4: Run tests to verify rename**

Run: `uv run pytest tests/test_agent_state.py -v`
Expected: All tests pass (same behavior, new names)

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: rename .ralph/ to .superintendent/ — state module

Rename RalphState → AgentState, ralph_dir → state_dir, .ralph/ → .superintendent/.
No behavior changes — mechanical rename."
```

---

### Task 2: Rename `.ralph/` references — backends and orchestrator

**Files:**
- Modify: `src/superintendent/backends/terminal.py:42` (parameter `ralph_dir` → `state_dir`)
- Modify: `src/superintendent/backends/docker.py:147-163,398-414` (local var + string refs)
- Modify: `src/superintendent/orchestrator/step_handler.py` (import, all `.ralph` refs)

- [ ] **Step 1: Update `terminal.py` — `wrap_with_lifecycle` parameter**

Change `ralph_dir: Path` parameter to `state_dir: Path` at line 42. Update docstring.

```python
def wrap_with_lifecycle(cmd: str, state_dir: Path) -> str:
    """Wrap an agent command with lifecycle marker writes.

    Writes agent-started before the command, then captures the exit code
    and writes agent-exit-code and agent-done after it completes.
    """
    return (
        f"date -u +%Y-%m-%dT%H:%M:%SZ > {state_dir}/agent-started; "
        f"{cmd}; "
        f"_exit=$?; echo $_exit > {state_dir}/agent-exit-code; "
        f"date -u +%Y-%m-%dT%H:%M:%SZ > {state_dir}/agent-done; "
        f"exit $_exit"
    )
```

- [ ] **Step 2: Update `docker.py` — both `run_agent` methods**

In `RealDockerBackend.run_agent` (line ~156): `ralph_dir` → `state_dir`, `".ralph"` → `".superintendent"`.

In `DryRunDockerBackend.run_agent` (line ~409): same changes.

- [ ] **Step 3: Update `step_handler.py` — imports and all references**

- Import: `from superintendent.state.ralph import RalphState` → `from superintendent.state.agent_state import AgentState`
- In `_handle_initialize_state` (~line 385): `RalphState` → `AgentState`, all `ralph_dir` → `state_dir`, `".ralph"` → `".superintendent"`
- In `_handle_initialize_state` (~line 441): step output key `"ralph_dir"` → `"state_dir"`
- In `_handle_start_agent` (~line 632): `ralph_dir` → `state_dir`, `".ralph"` → `".superintendent"`
- In `_handle_start_agent` (~line 605): user-facing string `".ralph/context.md"` → `".superintendent/context.md"`

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -x -q`
Expected: All tests pass (some tests may fail if they reference old imports — that's Task 3)

- [ ] **Step 5: Commit**

```bash
git add src/superintendent/backends/terminal.py src/superintendent/backends/docker.py src/superintendent/orchestrator/step_handler.py
git commit -m "refactor: rename ralph references in backends and orchestrator"
```

---

### Task 3: Rename `.ralph/` references — CLI, tests, docs, config

**Files:**
- Modify: `src/superintendent/cli/main.py` (`.ralph` → `.superintendent`, `ralph_dir` → `state_dir`)
- Modify: `tests/test_status.py` (~12 `.ralph` references)
- Modify: `tests/test_step_handler.py` (~5 `.ralph` references)
- Modify: `tests/test_integration.py` (~5 `.ralph` references)
- Modify: `tests/test_terminal_backend.py` (~3 `.ralph` references)
- Modify: `tests/test_dry_run.py` (~2 `.ralph` references)
- Modify: `tests/test_checkpoint.py` (~1 `.ralph` reference)
- Modify: `.gitignore` (line 1: `.ralph/` → `.superintendent/`)
- Modify: `docs/ARCHITECTURE.md` (4 references)
- Modify: `README.md` (1 reference)
- Modify: `CLAUDE.md` (directory tree if `ralph.py` mentioned)

- [ ] **Step 1: Update `cli/main.py`**

Find-and-replace all `.ralph` → `.superintendent` and `ralph_dir` → `state_dir` in:
- `check_agent_status()` (~line 857): local var and string references
- `_read_marker()` caller and `".ralph"` string

- [ ] **Step 2: Update all test files**

Find-and-replace `.ralph` → `.superintendent` in each test file listed above. Also update any `ralph_dir` variable names to `state_dir`.

- [ ] **Step 3: Update `.gitignore` and docs**

- `.gitignore`: `.ralph/` → `.superintendent/`
- `docs/ARCHITECTURE.md`: update directory tree and text references
- `README.md`: update reference
- `CLAUDE.md`: update directory tree if `ralph.py` is mentioned

- [ ] **Step 4: Run full test suite and lint**

Run: `uv run pytest -x -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: All pass, no lint errors

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "refactor: complete .ralph/ → .superintendent/ rename across CLI, tests, docs"
```

---

### Task 4: Extract `enrich_prompt()` as standalone function

**Note:** This task adds new behavior to the `run` command path — autonomous agents will now be instructed to write `.superintendent/pr-context.md` after creating PRs. This is intentional per the spec's Change 2.

**Files:**
- Modify: `src/superintendent/orchestrator/step_handler.py:484-591`
- Modify: `tests/test_step_handler.py` (add tests for extracted function)

- [ ] **Step 1: Write tests for the extracted function**

Add to `tests/test_step_handler.py`:

```python
from superintendent.orchestrator.step_handler import enrich_prompt


class TestEnrichPrompt:
    def test_autonomous_adds_test_suite_reminder(self):
        result = enrich_prompt("do task", autonomous=True)
        assert "Run the project's test suite" in result

    def test_interactive_no_test_reminder(self):
        result = enrich_prompt("do task", autonomous=False)
        assert "Run the project's test suite" not in result

    def test_notify_plugin_adds_preamble(self):
        result = enrich_prompt("do task", autonomous=False, notify_installed=True)
        assert "/notify:notify" in result

    def test_no_notify_no_preamble(self):
        result = enrich_prompt("do task", autonomous=False, notify_installed=False)
        assert "/notify:notify" not in result

    def test_pr_context_instruction_included_by_default(self):
        result = enrich_prompt("do task", autonomous=True)
        assert "pr-context.md" in result

    def test_pr_context_instruction_excluded_when_flagged(self):
        result = enrich_prompt(
            "do task", autonomous=True, include_pr_context_instruction=False
        )
        assert "pr-context.md" not in result

    def test_pr_context_instruction_not_in_interactive(self):
        result = enrich_prompt("do task", autonomous=False)
        assert "pr-context.md" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_step_handler.py::TestEnrichPrompt -v`
Expected: ImportError or test failures (function doesn't exist yet)

- [ ] **Step 3: Extract the function**

In `step_handler.py`, add a module-level function before the `RealStepHandler` class:

```python
def enrich_prompt(
    task: str,
    autonomous: bool,
    *,
    notify_installed: bool = False,
    include_pr_context_instruction: bool = True,
) -> str:
    """Add session-setup instructions to an agent prompt.

    Args:
        task: The base task prompt.
        autonomous: Whether the agent runs autonomously.
        notify_installed: Whether the notify plugin is available.
        include_pr_context_instruction: Whether to tell the agent to write
            pr-context.md after creating a PR. Set False for respond agents.
    """
    preamble_parts: list[str] = []
    if not autonomous and notify_installed:
        preamble_parts.append(
            "First, run /notify:notify to enable audio notifications."
        )

    suffix_parts: list[str] = []
    if autonomous:
        suffix_parts.append(
            "IMPORTANT: Run the project's test suite after completing each "
            "task. Do NOT proceed to the next task if tests fail — fix the "
            "failure first."
        )
        suffix_parts.append(
            "IMPORTANT: When you have finished all tasks, do NOT exit the "
            "conversation. Instead, summarize what you accomplished and wait "
            "for the user to review your work. The user may have follow-up "
            "questions or corrections."
        )
        if include_pr_context_instruction:
            suffix_parts.append(
                "IMPORTANT: After creating your PR, write a context file to "
                "`.superintendent/pr-context.md` summarizing your changes, key "
                "decisions, and anything a reviewer should know. This file will "
                "be used to brief a future agent if review comments need to be "
                "addressed."
            )

    parts = []
    if preamble_parts:
        parts.append(" ".join(preamble_parts))
    parts.append(task)
    if suffix_parts:
        parts.append("\n".join(suffix_parts))
    return "\n\n".join(parts)
```

Update `RealStepHandler._enrich_prompt` to delegate:

```python
def _enrich_prompt(self, task: str, autonomous: bool) -> str:
    """Add session-setup instructions to the agent prompt."""
    return enrich_prompt(
        task,
        autonomous,
        notify_installed=self._notify_plugin_installed(),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_step_handler.py -v`
Expected: All pass including new TestEnrichPrompt tests

- [ ] **Step 5: Commit**

```bash
git add src/superintendent/orchestrator/step_handler.py tests/test_step_handler.py
git commit -m "refactor: extract enrich_prompt() as standalone function

Enables reuse by the respond command. Adds pr-context.md write
instruction for autonomous agents, with flag to skip for respond."
```

---

### Task 5: Add `has_open_pr` to GitBackend + cleanup guard

**Files:**
- Modify: `src/superintendent/backends/git.py:139-141,370-395,637-638,710-712`
- Modify: `src/superintendent/cli/main.py:262-301`
- Modify: `tests/test_smart_cleanup.py`

- [ ] **Step 1: Write cleanup guard tests**

Add to `tests/test_smart_cleanup.py`:

```python
class TestOpenPrGuard:
    """Entries with open PRs are protected from cleanup."""

    def test_open_pr_prevents_cleanup(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(branch="feature", worktree_path=str(wt))
        git = MockGitBackend(open_prs={"feature"})
        result = analyze_entry(entry, git)
        assert result is None  # not a cleanup candidate

    def test_merged_pr_still_qualifies(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(branch="feature", worktree_path=str(wt))
        git = MockGitBackend(merged_branches={"feature"})
        result = analyze_entry(entry, git)
        assert result is not None
        assert "merged PR" in result.reasons[0]

    def test_open_pr_overrides_stale(self, tmp_path: Path) -> None:
        """Even if the branch is stale, an open PR protects it."""
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(branch="feature", worktree_path=str(wt))
        git = MockGitBackend(open_prs={"feature"}, branch_ages={"feature": 999.0})
        result = analyze_entry(entry, git)
        assert result is None

    def test_smart_cleanup_skips_open_pr(self, tmp_path: Path) -> None:
        """Full smart_cleanup flow respects the guard."""
        wt = tmp_path / "wt"
        wt.mkdir()
        reg_path = tmp_path / "registry.json"
        registry = WorktreeRegistry(reg_path)
        entry = _make_entry(branch="feature", worktree_path=str(wt))
        registry.add(entry)
        git = MockGitBackend(open_prs={"feature"})
        candidates = smart_cleanup(registry, git, dry_run=True)
        assert len(candidates) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_smart_cleanup.py::TestOpenPrGuard -v`
Expected: FAIL — `MockGitBackend` doesn't have `open_prs` field, `has_open_pr` doesn't exist

- [ ] **Step 3: Add `has_open_pr` to GitBackend protocol**

In `src/superintendent/backends/git.py`, add after `has_merged_pr` (line ~141):

```python
def has_open_pr(self, repo: Path, branch: str) -> bool:
    """Check if the branch has an open (unmerged) PR."""
    ...
```

- [ ] **Step 4: Implement in RealGitBackend**

Add after `has_merged_pr` (line ~395):

```python
def has_open_pr(self, repo: Path, branch: str) -> bool:
    result = subprocess.run(
        [
            "gh", "pr", "list",
            "--head", branch,
            "--state", "open",
            "--json", "number",
            "--limit", "1",
        ],
        capture_output=True,
        text=True,
        cwd=str(repo),
    )
    if result.returncode != 0:
        return False
    try:
        import json
        prs = json.loads(result.stdout)
        return len(prs) > 0
    except (json.JSONDecodeError, TypeError):
        return False
```

- [ ] **Step 5: Implement in MockGitBackend and DryRunGitBackend**

MockGitBackend — add field and method after `unpushed_branches` (~line 572):

```python
open_prs: set[str] = field(default_factory=set)
```

Add method after `has_merged_pr` (~line 638):

```python
def has_open_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
    return branch in self.open_prs
```

DryRunGitBackend — add after `has_merged_pr` (~line 712):

```python
def has_open_pr(self, repo: Path, branch: str) -> bool:  # noqa: ARG002
    self.commands.append(f"gh pr list --head {branch} --state open --json number --limit 1")
    return False
```

- [ ] **Step 6: Add cleanup guard to `analyze_entry()`**

In `src/superintendent/cli/main.py`, inside `analyze_entry()` at line ~272, after `worktree_path = Path(entry.worktree_path)`, add:

```python
# Entries with open PRs are never cleanup candidates
if worktree_path.exists() and git.has_open_pr(worktree_path, entry.branch):
    return None
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `uv run pytest tests/test_smart_cleanup.py -v`
Expected: All pass

- [ ] **Step 8: Commit**

```bash
git add src/superintendent/backends/git.py src/superintendent/cli/main.py tests/test_smart_cleanup.py
git commit -m "feat: guard open-PR entries from smart cleanup

Add has_open_pr() to GitBackend. Entries with open PRs are never
flagged as cleanup candidates, even if the branch is stale."
```

---

### Task 6: Add `superintendent respond` command — core

**Files:**
- Modify: `src/superintendent/cli/main.py`
- Create: `tests/test_respond.py`

- [ ] **Step 1: Write PR URL parsing tests**

Create `tests/test_respond.py`:

```python
"""Tests for superintendent respond command."""

from superintendent.cli.main import parse_pr_url


class TestParsePrUrl:
    def test_valid_url(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42")
        assert result == ("owner", "repo", 42)

    def test_valid_url_trailing_slash(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42/")
        assert result == ("owner", "repo", 42)

    def test_invalid_url(self):
        assert parse_pr_url("not-a-url") is None

    def test_issues_url(self):
        assert parse_pr_url("https://github.com/owner/repo/issues/42") is None

    def test_no_number(self):
        assert parse_pr_url("https://github.com/owner/repo/pull/") is None

    def test_files_suffix(self):
        result = parse_pr_url("https://github.com/owner/repo/pull/42/files")
        assert result == ("owner", "repo", 42)
```

- [ ] **Step 2: Implement `parse_pr_url`**

Add to `cli/main.py`:

```python
def parse_pr_url(url: str) -> tuple[str, str, int] | None:
    """Parse a GitHub PR URL into (owner, repo, number).

    Returns None if the URL doesn't match the expected format.
    """
    match = re.match(
        r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)",
        url,
    )
    if not match:
        return None
    return (match.group(1), match.group(2), int(match.group(3)))
```

- [ ] **Step 3: Run URL parsing tests**

Run: `uv run pytest tests/test_respond.py::TestParsePrUrl -v`
Expected: All pass

- [ ] **Step 4: Write respond command tests**

Add to `tests/test_respond.py`:

```python
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from superintendent.backends.docker import MockDockerBackend
from superintendent.backends.terminal import MockTerminalBackend
from superintendent.cli.main import app, get_default_registry, parse_pr_url
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry

runner = CliRunner()


def _setup_entry(tmp_path: Path, *, sandbox_name: str | None = None) -> tuple[WorktreeRegistry, WorktreeEntry]:
    """Create a real registry with one entry and a real .superintendent/ dir."""
    reg_path = tmp_path / "registry.json"
    registry = WorktreeRegistry(reg_path)
    wt = tmp_path / "worktree"
    wt.mkdir()
    state_dir = wt / ".superintendent"
    state_dir.mkdir()
    entry = WorktreeEntry(
        name="test-entry",
        repo="/tmp/repo",
        branch="feature/test",
        worktree_path=str(wt),
        sandbox_name=sandbox_name,
    )
    registry.add(entry)
    return registry, entry


class TestRespondCommand:
    def test_respond_by_name(self, tmp_path: Path):
        registry, entry = _setup_entry(tmp_path)
        wt = Path(entry.worktree_path)
        (wt / ".superintendent" / "pr-context.md").write_text("Key decision: chose X over Y")
        terminal = MockTerminalBackend()

        with patch("superintendent.cli.main.get_default_registry", return_value=registry), \
             patch("superintendent.cli.main._resolve_pr_number", return_value=42), \
             patch("superintendent.cli.main.detect_terminal", return_value=terminal):
            result = runner.invoke(app, ["respond", "test-entry"])

        assert result.exit_code == 0
        assert len(terminal.spawned) == 1
        cmd, workspace = terminal.spawned[0]
        assert "42" in cmd
        assert "Key decision: chose X over Y" in cmd
        assert workspace == wt

    def test_respond_without_context_file(self, tmp_path: Path):
        registry, entry = _setup_entry(tmp_path)
        terminal = MockTerminalBackend()

        with patch("superintendent.cli.main.get_default_registry", return_value=registry), \
             patch("superintendent.cli.main._resolve_pr_number", return_value=42), \
             patch("superintendent.cli.main.detect_terminal", return_value=terminal):
            result = runner.invoke(app, ["respond", "test-entry"])

        assert result.exit_code == 0
        cmd, _ = terminal.spawned[0]
        assert "Context from the original author" not in cmd

    def test_respond_entry_not_found(self, tmp_path: Path):
        registry = WorktreeRegistry(tmp_path / "registry.json")

        with patch("superintendent.cli.main.get_default_registry", return_value=registry):
            result = runner.invoke(app, ["respond", "nonexistent"])

        assert result.exit_code == 1

    def test_respond_worktree_missing(self, tmp_path: Path):
        reg_path = tmp_path / "registry.json"
        registry = WorktreeRegistry(reg_path)
        entry = WorktreeEntry(
            name="test-entry",
            repo="/tmp/repo",
            branch="feature/test",
            worktree_path="/nonexistent/path",
        )
        registry.add(entry)

        with patch("superintendent.cli.main.get_default_registry", return_value=registry):
            result = runner.invoke(app, ["respond", "test-entry"])

        assert result.exit_code == 1
        assert "not found" in result.output.lower() or "cleaned up" in result.output.lower()

    def test_respond_sandbox_entry(self, tmp_path: Path):
        registry, entry = _setup_entry(tmp_path, sandbox_name="my-sandbox")
        docker = MockDockerBackend()

        with patch("superintendent.cli.main.get_default_registry", return_value=registry), \
             patch("superintendent.cli.main._resolve_pr_number", return_value=42), \
             patch("superintendent.cli.main._get_docker_backend", return_value=docker):
            result = runner.invoke(app, ["respond", "test-entry"])

        assert result.exit_code == 0
        assert len(docker.agents_run) == 1
        assert docker.agents_run[0][0] == "my-sandbox"

    def test_respond_dry_run(self, tmp_path: Path):
        registry, entry = _setup_entry(tmp_path)
        (Path(entry.worktree_path) / ".superintendent" / "pr-context.md").write_text("context here")

        with patch("superintendent.cli.main.get_default_registry", return_value=registry), \
             patch("superintendent.cli.main._resolve_pr_number", return_value=42):
            result = runner.invoke(app, ["respond", "test-entry", "--dry-run"])

        assert result.exit_code == 0
        assert "42" in result.output  # PR number shown
```

The DI pattern is `unittest.mock.patch` on `detect_terminal` and `_get_docker_backend` — the same functions called inside the `respond` command. This avoids Typer's `ctx.obj` which doesn't work for injecting backends.

- [ ] **Step 5: Run tests to verify they fail**

Run: `uv run pytest tests/test_respond.py -v`
Expected: ImportError or failures (respond command doesn't exist yet)

- [ ] **Step 6: Commit test file**

```bash
git add tests/test_respond.py
git commit -m "test: add tests for superintendent respond command"
```

---

### Task 7: Implement `superintendent respond` command

**Files:**
- Modify: `src/superintendent/cli/main.py`

- [ ] **Step 1: Add helper functions**

Add these helpers to `cli/main.py` (near the other helper functions):

```python
def _resolve_pr_number(branch: str, worktree_path: Path) -> int | None:
    """Resolve a branch to its PR number via gh CLI."""
    result = subprocess.run(
        ["gh", "pr", "list", "--head", branch, "--json", "number", "--limit", "1"],
        capture_output=True,
        text=True,
        cwd=str(worktree_path),
    )
    if result.returncode != 0:
        return None
    try:
        import json
        prs = json.loads(result.stdout)
        if prs:
            pr_number: int = prs[0]["number"]
            return pr_number
    except (json.JSONDecodeError, TypeError, KeyError, IndexError):
        pass
    return None


def _resolve_branch_from_pr_url(
    owner: str, repo: str, number: int
) -> str | None:
    """Resolve a PR URL to its head branch name via gh CLI."""
    result = subprocess.run(
        ["gh", "api", f"repos/{owner}/{repo}/pulls/{number}", "--jq", ".head.ref"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    branch = result.stdout.strip()
    return branch if branch else None


def _get_docker_backend() -> "DockerBackend":
    """Return a RealDockerBackend for respond command."""
    from superintendent.backends.docker import RealDockerBackend
    return RealDockerBackend()
```

- [ ] **Step 2: Add the respond command**

```python
@app.command()
def respond(
    identifier: str = typer.Argument(
        ..., help="Registry name, branch name, or GitHub PR URL."
    ),
    autonomous: bool = typer.Option(
        False, "--autonomous", help="Run agent without permission prompts."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Show prompt and command without spawning."
    ),
    dangerously_skip_isolation: bool = typer.Option(
        False,
        "--dangerously-skip-isolation",
        help="Required for autonomous mode.",
    ),
) -> None:
    """Spawn an agent to respond to code review comments on a PR."""
    if autonomous and not dangerously_skip_isolation:
        typer.echo("Error: --autonomous requires --dangerously-skip-isolation")
        raise typer.Exit(code=1)

    registry = get_default_registry()

    # Resolve identifier to entry
    pr_number_from_url: int | None = None
    entry = registry.get(identifier)
    if entry is None:
        entry = registry.get_by_branch(identifier)
    if entry is None:
        # Try as PR URL
        parsed = parse_pr_url(identifier)
        if parsed:
            owner, repo, pr_number_from_url = parsed
            branch = _resolve_branch_from_pr_url(owner, repo, pr_number_from_url)
            if branch is None:
                typer.echo(
                    "Error: could not resolve PR URL to a branch. "
                    "Check `gh auth status`.",
                    err=True,
                )
                raise typer.Exit(code=1)
            entry = registry.get_by_branch(branch)

    if entry is None:
        typer.echo(f"Error: no entry found for '{identifier}'", err=True)
        all_entries = registry.list_all()
        if all_entries:
            typer.echo("Available entries:", err=True)
            for e in all_entries:
                typer.echo(f"  {e.name} [{e.branch}]", err=True)
        raise typer.Exit(code=1)

    worktree_path = Path(entry.worktree_path)
    if not worktree_path.exists():
        typer.echo(
            f"Error: worktree not found at {entry.worktree_path}. "
            "It may have been cleaned up. Re-run with `superintendent run` to recreate.",
            err=True,
        )
        raise typer.Exit(code=1)

    # Determine PR number
    pr_number = pr_number_from_url
    if pr_number is None:
        pr_number = _resolve_pr_number(entry.branch, worktree_path)
    if pr_number is None:
        typer.echo(
            f"Warning: could not determine PR number for branch '{entry.branch}'. "
            "The agent will need to find it.",
            err=True,
        )

    # Read context file
    context_file = worktree_path / ".superintendent" / "pr-context.md"
    context = ""
    if context_file.exists():
        context = (
            "\n\n## Context from the original author\n"
            + context_file.read_text().strip()
        )

    # Build prompt
    pr_ref = f"PR #{pr_number}" if pr_number else "the open PR on this branch"
    prompt = (
        f"You are responding to code review comments on {pr_ref} in this repository."
        f"{context}\n\n"
        "Read the review comments using `gh pr view` or `gh api`, then for each comment:\n"
        "- If the feedback is valid: implement the change and commit\n"
        "- If you disagree: reply on the PR with a clear technical explanation\n\n"
        "After addressing all comments, push your changes."
    )

    # Enrich for autonomous mode
    if autonomous:
        from superintendent.orchestrator.step_handler import enrich_prompt
        prompt = enrich_prompt(
            prompt,
            autonomous=True,
            include_pr_context_instruction=False,
        )

    if dry_run:
        typer.echo("=== Dry Run: Respond ===")
        typer.echo(f"Entry: {entry.name} [{entry.branch}]")
        typer.echo(f"Worktree: {entry.worktree_path}")
        typer.echo(f"PR: #{pr_number}" if pr_number else "PR: unknown")
        typer.echo(f"Autonomous: {autonomous}")
        typer.echo(f"\n--- Prompt ---\n{prompt}")
        return

    # Spawn agent
    from superintendent.backends.terminal import build_agent_command, detect_terminal, wrap_with_lifecycle

    if entry.sandbox_name:
        docker = _get_docker_backend()
        if not docker.run_agent(
            entry.sandbox_name, prompt, autonomous=autonomous, cwd=worktree_path
        ):
            typer.echo(f"Error: failed to start agent in {entry.sandbox_name}", err=True)
            raise typer.Exit(code=1)
    else:
        cmd = build_agent_command(prompt, autonomous=autonomous)
        state_dir = worktree_path / ".superintendent"
        if state_dir.is_dir():
            cmd = wrap_with_lifecycle(cmd, state_dir)
        terminal = detect_terminal()
        if not terminal.spawn(cmd, worktree_path):
            typer.echo("Error: failed to spawn local agent", err=True)
            raise typer.Exit(code=1)

    typer.echo(f"Agent spawned to respond to {pr_ref}.")
    typer.echo(f"  Worktree: {entry.worktree_path}")
    if entry.sandbox_name:
        typer.echo(f"  Sandbox: {entry.sandbox_name}")
```

- [ ] **Step 3: Run respond tests**

Run: `uv run pytest tests/test_respond.py -v`
Expected: Most pass. Some may need adjustment based on how mocks are injected — adjust the test to match the actual DI pattern (patching `detect_terminal`, `_get_docker_backend`, etc.)

- [ ] **Step 4: Run full test suite and lint**

Run: `uv run pytest -x -q && uv run ruff check src/ tests/ && uv run ruff format --check src/ tests/`
Expected: All pass

- [ ] **Step 5: Commit**

```bash
git add src/superintendent/cli/main.py tests/test_respond.py
git commit -m "feat: add superintendent respond command

Spawns an agent in an existing worktree to address code review
comments. Reads .superintendent/pr-context.md for context handoff.
Resolves by name, branch, or PR URL."
```

---

### Task 8: Version bump, final verification, PR

**Files:**
- Modify: `pyproject.toml:3`
- Modify: `src/superintendent/__init__.py:3`

- [ ] **Step 1: Check current version and bump**

Read current version from `pyproject.toml` and `src/superintendent/__init__.py`. Bump to next minor version (this adds a new CLI command): if current is `0.2.x`, bump to `0.3.0`.

Update both files. Run `uv lock` to sync.

- [ ] **Step 2: Run full CI checklist**

```bash
uv run pytest -x -q
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

All must pass.

- [ ] **Step 3: Commit version bump**

```bash
git add pyproject.toml src/superintendent/__init__.py uv.lock
git commit -m "bump: version 0.3.0 — adds superintendent respond command"
```

- [ ] **Step 4: Push and create PR**

```bash
git push -u origin bmw/cr-handoff-respond
gh pr create --title "feat: add superintendent respond command for CR handoff" --body "$(cat <<'EOF'
## Summary
- Rename `.ralph/` to `.superintendent/` throughout codebase (mechanical rename, no behavior change)
- Autonomous agents now write `.superintendent/pr-context.md` after creating PRs (context handoff for future agents)
- New `superintendent respond <identifier>` command spawns agents to address code review comments
  - Resolves by registry name, branch name, or GitHub PR URL
  - Injects saved context and PR number into agent prompt
  - Supports `--autonomous`, `--dry-run`, sandbox entries
- Entries with open PRs are protected from `cleanup --smart`

## Test plan
- [ ] PR URL parsing (valid, invalid, wrong format)
- [ ] Respond by name, branch, and PR URL
- [ ] Respond without context file (graceful skip)
- [ ] Respond with missing worktree (error)
- [ ] Respond with sandbox entry (routes through docker)
- [ ] Dry run (shows prompt, no spawn)
- [ ] Cleanup guard: open PR prevents cleanup
- [ ] Cleanup guard: merged PR still qualifies
- [ ] enrich_prompt includes/excludes pr-context instruction

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```
