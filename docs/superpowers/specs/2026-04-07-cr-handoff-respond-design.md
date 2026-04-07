# CR Handoff: `superintendent respond` — Design Spec

## Problem

When an autonomous agent creates a PR, the context behind its decisions (why it chose an approach, what tradeoffs it made, what reviewers should watch for) lives only in the agent's conversation history — which is lost when the session ends. When review comments arrive, a new agent must be spawned to address them, but it starts from zero with no understanding of the original work.

Additionally, worktrees with open PRs awaiting review can be cleaned up by `superintendent cleanup --smart`, destroying the workspace needed to respond.

## Solution Overview

Three changes:

1. **Rename `.ralph/` to `.superintendent/`** — the agent state directory gets a generic name since it now stores more than ralph-specific state
2. **Context file protocol** — agents write `.superintendent/pr-context.md` after creating a PR, briefing the next agent on what was done and why
3. **`superintendent respond` command** — spawns an agent in an existing worktree to address review comments, injecting the saved context and PR number into the prompt
4. **Cleanup guard** — entries with open PRs are protected from smart cleanup

## Change 1: Rename `.ralph/` to `.superintendent/`

Rename the agent state directory and its manager class throughout the codebase.

| Before | After |
|---|---|
| `.ralph/` | `.superintendent/` |
| `src/superintendent/state/ralph.py` | `src/superintendent/state/agent_state.py` |
| `class RalphState` | `class AgentState` |
| All references in step_handler.py, docker.py, terminal.py, cli/main.py | Updated |
| All references in tests | Updated |

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
superintendent respond <identifier> [--mode interactive|autonomous] [--dangerously-skip-isolation]
```

Default mode is `interactive`. `--dangerously-skip-isolation` required for `autonomous` (same pattern as `run`).

### Identifier resolution

`<identifier>` resolves in order:

1. **Registry name** — `registry.get(identifier)`
2. **Branch name** — `registry.get_by_branch(identifier)`
3. **PR URL** — parse `https://github.com/{owner}/{repo}/pull/{number}`, call `gh api repos/{owner}/{repo}/pulls/{number}` to get the head branch, then look up by branch in the registry

PR URL parsing extracts owner, repo, and PR number via regex. The `gh api` call returns the branch name from the PR's `head.ref` field.

If no entry is found after all three attempts, error with a helpful message listing available entries (same pattern as `resume`).

### What it does

1. Resolve identifier to a `WorktreeEntry`
2. Determine PR number:
   - If identifier was a URL: already parsed
   - Otherwise: `gh pr list --head {branch} --json number --limit 1`
3. Read `.superintendent/pr-context.md` from the worktree (if it exists)
4. Build prompt:
   ```
   You are responding to code review comments on PR #{number} in this repository.

   {contents of pr-context.md, if present, preceded by "## Context from the original author\n"}

   Read the review comments using `gh pr view {number} --comments` or `gh api`, then for each comment:
   - If the feedback is valid: implement the change and commit
   - If you disagree: reply on the PR with a clear technical explanation

   After addressing all comments, push your changes.
   ```
5. Build agent command via `build_agent_command()` (shared helper in terminal.py)
6. Wrap with lifecycle markers via `wrap_with_lifecycle()` if `.superintendent/` exists
7. Spawn agent in the existing worktree via terminal backend

### No worktree creation

The worktree already exists from the original `run`. This command only spawns a new agent session in it. If the worktree path doesn't exist, error with a message suggesting the user re-run or check if it was cleaned up.

## Change 4: Cleanup guard for open PRs

### analyze_entry() change

Add an early return at the top of `analyze_entry()` in `cli/main.py`:

```python
if worktree_path.exists() and git.has_open_pr(repo_path, entry.branch):
    return None  # not a cleanup candidate — PR is awaiting review
```

This must come before the existing checks (merged PR, stale branch, missing remote) so that an open PR always protects the entry.

### New GitBackend method

```python
def has_open_pr(self, repo_path: Path, branch: str) -> bool:
    """Check if the branch has an open (unmerged) PR."""
```

Implementation in `RealGitBackend`: calls `gh pr list --head {branch} --state open --json number --limit 1` from `repo_path` and returns True if any results.

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
    # Mock terminal backend (records spawned commands)
    # Monkeypatch gh CLI calls to return PR number
    # Call the respond orchestration logic
    # Assert: terminal.spawned[0] command contains PR number
    # Assert: terminal.spawned[0] command contains pr-context.md contents
    # Assert: terminal.spawned[0] workspace is the entry's worktree_path

def test_respond_by_branch(tmp_path):
    # Same as above but look up by branch name
    # Assert: resolves to correct entry

def test_respond_by_pr_url(tmp_path):
    # Same but pass a GitHub PR URL
    # Monkeypatch gh api call to return branch name
    # Assert: resolves to correct entry and extracts PR number from URL

def test_respond_without_context_file(tmp_path):
    # Entry exists but no pr-context.md
    # Assert: still spawns agent successfully
    # Assert: prompt does NOT contain "Context from the original author"

def test_respond_entry_not_found(tmp_path):
    # Empty registry
    # Assert: exits with error code 1 and helpful message
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

### Test 4: Rename verification (across existing test files)

- Update all existing tests from `RalphState` to `AgentState`, `.ralph/` to `.superintendent/`
- No new behavioral tests — just naming

## Files Changed

| File | Change |
|---|---|
| `src/superintendent/state/ralph.py` → `agent_state.py` | Rename file, class `RalphState` → `AgentState` |
| `src/superintendent/orchestrator/step_handler.py` | Update imports, add pr-context.md instruction to `_enrich_prompt()`, update `.ralph/` → `.superintendent/` |
| `src/superintendent/backends/docker.py` | Update `.ralph/` → `.superintendent/` |
| `src/superintendent/backends/terminal.py` | Update `.ralph/` → `.superintendent/` references in `wrap_with_lifecycle` docstring |
| `src/superintendent/backends/git.py` | Add `has_open_pr()` to protocol + all implementations |
| `src/superintendent/cli/main.py` | New `respond` command, PR URL parser, update `analyze_entry()` with open PR guard, update `.ralph/` → `.superintendent/` |
| `tests/test_respond.py` (new) | Respond command tests, URL parsing tests |
| `tests/test_smart_cleanup.py` | Cleanup guard tests |
| `tests/test_ralph_state.py` → `test_agent_state.py` | Rename, update references |
| All other test files referencing `.ralph/` or `RalphState` | Mechanical rename |

## Out of Scope

- Structured context format (JSON/YAML) — freeform markdown for now, can add later
- Context stored on GitHub (PR comments) — local file is simpler
- Automatic detection of new review comments — user triggers `respond` manually
- Multi-round review support — each `respond` invocation is independent
