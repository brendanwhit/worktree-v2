# CR Handoff: `superintendent respond` — Design Spec

## Problem

When an autonomous agent creates a PR, the context behind its decisions (why it chose an approach, what tradeoffs it made, what reviewers should watch for) lives only in the agent's conversation history — which is lost when the session ends. When review comments arrive, a new agent must be spawned to address them, but it starts from zero with no understanding of the original work.

Additionally, worktrees with open PRs awaiting review can be cleaned up by `superintendent cleanup --smart`, destroying the workspace needed to respond.

## Solution Overview

Four changes:

1. **Rename `.ralph/` to `.superintendent/`** — the agent state directory gets a generic name since it now stores more than ralph-specific state
2. **Context file protocol** — agents write `.superintendent/pr-context.md` after creating a PR, briefing the next agent on what was done and why
3. **`superintendent respond` command** — spawns an agent in an existing worktree to address review comments, injecting the saved context and PR number into the prompt
4. **Cleanup guard** — entries with open PRs are protected from smart cleanup

## Change 1: Rename `.ralph/` to `.superintendent/`

Rename the agent state directory and its manager class throughout the codebase.

### Source files

| Before | After |
|---|---|
| `src/superintendent/state/ralph.py` | `src/superintendent/state/agent_state.py` |
| `class RalphState` | `class AgentState` |
| `ralph_dir` parameter in `wrap_with_lifecycle()` (terminal.py) | `state_dir` |
| `ralph_dir` local variables in docker.py, step_handler.py, cli/main.py | `state_dir` |
| `.ralph/` string literals everywhere | `.superintendent/` |

### Documentation and config

| File | Change |
|---|---|
| `.gitignore` | `.ralph/` entry → `.superintendent/` |
| `docs/ARCHITECTURE.md` | Update directory tree and `.ralph/` references |
| `README.md` | Update `.ralph/` reference |
| `CLAUDE.md` | Update directory tree mentioning `ralph.py` |
| `src/superintendent/state/__init__.py` | Update module docstring |

### Test files

| File | Change |
|---|---|
| `tests/test_ralph_state.py` → `test_agent_state.py` | Rename file, update all imports and references |
| `tests/test_terminal_backend.py` | Update `.ralph` references |
| `tests/test_step_handler.py` | Update `.ralph` references |
| `tests/test_status.py` | Update `.ralph` references (12 occurrences) |
| `tests/test_integration.py` | Update `.ralph` references |
| `tests/test_dry_run.py` | Update `.ralph` references |
| `tests/test_checkpoint.py` | Update `.ralph` reference |

Files inside the directory stay the same: `config.json`, `progress.md`, `guardrails.md`, `worktree-task.md`, `agent-started`, `agent-done`, `agent-exit-code`.

This is a mechanical find-and-replace. No behavior changes.

## Change 2: Context file and write protocol

### The file

`.superintendent/pr-context.md` — a freeform markdown file written by the agent after creating a PR. Contents:

- What changed and why
- Key design decisions and alternatives considered
- Known risks or tradeoffs
- What reviewers are likely to question

### How agents write it

The `_enrich_prompt()` method in `step_handler.py` already appends instructions to the agent's task for autonomous agents. Add instructions telling the agent to write this file after creating its PR:

> "After creating your PR, write a context file to `.superintendent/pr-context.md` summarizing your changes, key decisions, and anything a reviewer should know. This file will be used to brief a future agent if review comments need to be addressed."

### No enforcement

If the agent doesn't write the file, `superintendent respond` still works — it spawns without the extra context. The command checks for the file and includes it if present, skips gracefully if not.

## Change 3: `superintendent respond` command

### Signature

```
superintendent respond <identifier> [--autonomous] [--dry-run] [--dangerously-skip-isolation]
```

- `identifier` is a positional Typer Argument — registry name, branch name, or PR URL
- `--autonomous` flag (default False) — runs without permission prompts. Requires `--dangerously-skip-isolation` (same guard as `run`)
- `--dry-run` — shows the constructed prompt and spawn command without executing

### Why `respond` bypasses the Executor/StepHandler pipeline

The `run` command goes through Planner → Executor → StepHandler because it orchestrates multiple steps (validate repo, create worktree, prepare sandbox, authenticate, initialize state, start agent). `respond` only does one thing: spawn an agent in an existing worktree. The full workflow machinery is unnecessary — there's no worktree to create, no sandbox to provision, no auth to configure. The worktree and state directory already exist from the original `run`.

This is the same pattern as the `resume` command, which also operates directly on an existing entry without going through the executor pipeline.

### Identifier resolution

`<identifier>` resolves in order:

1. **Registry name** — `registry.get(identifier)`
2. **Branch name** — `registry.get_by_branch(identifier)`
3. **PR URL** — parse `https://github.com/{owner}/{repo}/pull/{number}`, call `gh pr list --head {branch} --json number` to get the head branch, then look up by branch in the registry. If `gh` fails (not authenticated, network error), error with a message suggesting the user check `gh auth status`.

PR URL parsing extracts owner, repo, and PR number via regex on the pattern `https://github.com/{owner}/{repo}/pull/{number}`.

If no entry is found after all three attempts, error with a helpful message listing available entries (same pattern as `resume`).

### What it does

1. Resolve identifier to a `WorktreeEntry`
2. Verify worktree path exists — if not, error with: "Worktree not found at {path}. It may have been cleaned up. Re-run with `superintendent run` to recreate."
3. Determine PR number:
   - If identifier was a URL: already parsed
   - Otherwise: `gh pr list --head {branch} --json number --limit 1`
4. Read `.superintendent/pr-context.md` from the worktree (if it exists)
5. Build prompt:
   ```
   You are responding to code review comments on PR #{number} in this repository.

   {contents of pr-context.md, if present, preceded by "## Context from the original author\n"}

   Read the review comments using `gh pr view {number} --comments` or `gh api`, then for each comment:
   - If the feedback is valid: implement the change and commit
   - If you disagree: reply on the PR with a clear technical explanation

   After addressing all comments, push your changes.
   ```
6. For autonomous mode, apply `enrich_prompt()` to add the standard safeguards (run tests, CI checklist, etc.) that autonomous agents normally get via the `run` path. Extract from `RealStepHandler._enrich_prompt()` into a standalone function in step_handler.py:
   ```python
   def enrich_prompt(task: str, autonomous: bool, *, notify_installed: bool = False, include_pr_context_instruction: bool = True) -> str:
   ```
   - `notify_installed`: the current method calls `self._notify_plugin_installed()` which checks if the notify plugin exists at `~/.claude/plugins/...`. The extracted function accepts this as a bool so callers can compute it themselves or pass False.
   - `include_pr_context_instruction`: when True (default), appends the "write pr-context.md" instruction. The `respond` command passes `include_pr_context_instruction=False` since the agent is updating an existing PR, not creating a new one.
7. Build agent command via `build_agent_command()` (shared helper in terminal.py)
8. Wrap with lifecycle markers via `wrap_with_lifecycle()` if `.superintendent/` exists
9. Spawn agent:
   - If `entry.sandbox_name` is set: use `docker.run_agent(entry.sandbox_name, prompt, autonomous=autonomous, cwd=worktree_path)` — the sandbox still exists and the agent should run inside it
   - Otherwise: use `terminal.spawn(cmd, worktree_path)` for local entries
   - For sandbox spawning, instantiate `RealDockerBackend()` directly (same pattern as `cleanup` using `RealGitBackend()`)

### Dependency injection for testing

The `respond` command function accepts optional backend parameters with defaults:

```python
def respond(
    identifier: str,
    ...,
    _terminal: TerminalBackend | None = None,
    _docker: DockerBackend | None = None,
    _registry: WorktreeRegistry | None = None,
) -> None:
    terminal = _terminal or detect_terminal()
    docker = _docker or RealDockerBackend()
    registry = _registry or get_default_registry()
```

Underscore-prefixed parameters are not exposed as CLI options (typer ignores them). Tests pass in mocks via these parameters. This matches the pattern used elsewhere in the codebase for testability.

### No worktree creation

The worktree already exists from the original `run`. This command only spawns a new agent session in it.

## Change 4: Cleanup guard for open PRs

### analyze_entry() change

Add an early return at the top of `analyze_entry()` in `cli/main.py`, after the existing `worktree_path` construction:

```python
worktree_path = Path(entry.worktree_path)

# Entries with open PRs are never cleanup candidates
if worktree_path.exists() and git.has_open_pr(worktree_path, entry.branch):
    return None
```

Note: `worktree_path` is used as the git repo path (the existing code at line 278 does `repo_path = worktree_path`). This guard must come before the existing checks (merged PR, stale branch, missing remote) so that an open PR always protects the entry.

### New GitBackend method

```python
def has_open_pr(self, repo_path: Path, branch: str) -> bool:
    """Check if the branch has an open (unmerged) PR."""
```

Implementation in `RealGitBackend`: calls `gh pr list --head {branch} --state open --json number --limit 1` from `repo_path` and returns True if any results. Mirrors the existing `has_merged_pr()` pattern.

Mock/DryRun implementations:
- `MockGitBackend`: gets an `open_prs: set[str]` field, returns `branch in self.open_prs`
- `DryRunGitBackend`: returns False

## Testing Strategy

### Testing philosophy

Mock external boundaries (git CLI, GitHub API, terminal spawn) but use real instances of our own code (registry, file I/O, analyze_entry, command orchestration). This ensures the wiring between components is tested, not just individual units.

### Test 1: `respond` command — full flow (test_respond.py)

```python
def test_respond_by_name(tmp_path):
    # Real registry at tmp_path with a real entry
    # Real .superintendent/pr-context.md file on disk
    # MockTerminalBackend injected via _terminal parameter
    # Monkeypatch gh CLI calls to return PR number
    # Call respond() with _terminal=mock, _registry=real_registry
    # Assert: terminal.spawned[0] command contains PR number
    # Assert: terminal.spawned[0] command contains pr-context.md contents
    # Assert: terminal.spawned[0] workspace is the entry's worktree_path

def test_respond_by_branch(tmp_path):
    # Same as above but look up by branch name
    # Assert: resolves to correct entry

def test_respond_by_pr_url(tmp_path):
    # Same but pass a GitHub PR URL
    # Monkeypatch gh CLI calls to return branch name from PR
    # Assert: resolves to correct entry and extracts PR number from URL

def test_respond_without_context_file(tmp_path):
    # Entry exists but no pr-context.md
    # Assert: still spawns agent successfully
    # Assert: prompt does NOT contain "Context from the original author"

def test_respond_entry_not_found(tmp_path):
    # Empty registry
    # Assert: exits with error code 1 and helpful message

def test_respond_worktree_missing(tmp_path):
    # Entry in registry but worktree_path doesn't exist
    # Assert: exits with error code 1 and message about cleanup

def test_respond_sandbox_entry(tmp_path):
    # Entry with sandbox_name set
    # MockDockerBackend injected via _docker parameter
    # Assert: docker.run_agent() called, NOT terminal.spawn()

def test_respond_dry_run(tmp_path):
    # Entry exists with context file
    # --dry-run flag set
    # Assert: prompt and command printed, agent NOT spawned
```

### Test 2: PR URL parsing (test_respond.py)

```python
def test_parse_pr_url_valid():
    # "https://github.com/owner/repo/pull/42" -> ("owner", "repo", 42)

def test_parse_pr_url_invalid():
    # "not-a-url" -> None

def test_parse_pr_url_wrong_format():
    # "https://github.com/owner/repo/issues/42" -> None
```

### Test 3: Cleanup guard (test_smart_cleanup.py)

```python
def test_open_pr_prevents_cleanup(tmp_path):
    # Real registry with entry
    # MockGitBackend with open_prs={"the-branch"}
    # Run full smart_cleanup() flow
    # Assert: entry is NOT in returned candidates

def test_merged_pr_still_qualifies(tmp_path):
    # Same but open_prs is empty, merged_prs has the branch
    # Assert: entry IS in candidates (existing behavior preserved)

def test_no_pr_still_qualifies_on_other_criteria(tmp_path):
    # No open or merged PRs, but branch is stale
    # Assert: entry IS in candidates
```

### Test 4: Prompt enrichment (test_step_handler.py)

```python
def test_enrich_prompt_includes_pr_context_instruction():
    # Call _enrich_prompt() with autonomous=True
    # Assert: output contains "pr-context.md" instruction

def test_enrich_prompt_interactive_excludes_pr_context_instruction():
    # Call _enrich_prompt() with autonomous=False
    # Assert: output does NOT contain "pr-context.md" instruction
```

### Test 5: Rename verification (across existing test files)

- Update all existing tests from `RalphState` to `AgentState`, `.ralph/` to `.superintendent/`
- No new behavioral tests — just naming

## Files Changed

| File | Change |
|---|---|
| `src/superintendent/state/ralph.py` → `agent_state.py` | Rename file, class `RalphState` → `AgentState` |
| `src/superintendent/state/__init__.py` | Update module docstring |
| `src/superintendent/orchestrator/step_handler.py` | Update imports, rename `ralph_dir` → `state_dir`, add pr-context.md instruction to `_enrich_prompt()`, extract `_enrich_prompt()` as importable utility |
| `src/superintendent/backends/docker.py` | Rename `ralph_dir` → `state_dir`, update `.ralph/` → `.superintendent/` |
| `src/superintendent/backends/terminal.py` | Rename `ralph_dir` parameter → `state_dir` in `wrap_with_lifecycle()` |
| `src/superintendent/backends/git.py` | Add `has_open_pr()` to protocol + all implementations |
| `src/superintendent/cli/main.py` | New `respond` command with DI seam, PR URL parser, update `analyze_entry()` with open PR guard, rename `ralph_dir` → `state_dir`, update `.ralph/` → `.superintendent/` |
| `.gitignore` | `.ralph/` → `.superintendent/` |
| `docs/ARCHITECTURE.md` | Update directory tree and references |
| `README.md` | Update `.ralph/` reference |
| `CLAUDE.md` | Update directory tree |
| `tests/test_respond.py` (new) | Respond command tests, URL parsing tests |
| `tests/test_smart_cleanup.py` | Cleanup guard tests |
| `tests/test_step_handler.py` | Prompt enrichment tests, rename references |
| `tests/test_ralph_state.py` → `test_agent_state.py` | Rename file, update references |
| All other test files referencing `.ralph/` or `RalphState` | Mechanical rename |

## Known Limitations

- **Cleanup race:** If a PR is merged and `cleanup --smart` runs before the user runs `respond` for post-merge comments, the entry is removed. This is a narrow window and acceptable for v1.
- **Registry not updated after respond:** The registry entry is unchanged after a respond session. If future features need "last activity" tracking, this would need revisiting.

## Out of Scope

- Structured context format (JSON/YAML) — freeform markdown for now, can add later
- Context stored on GitHub (PR comments) — local file is simpler
- Automatic detection of new review comments — user triggers `respond` manually
- Multi-round review support — each `respond` invocation is independent
- Adding `--limit 1` to existing `has_merged_pr` for consistency (follow-up cleanup)
