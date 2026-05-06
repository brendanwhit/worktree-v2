# Superintendent CLI Reference

_Generated file — do not edit. Regenerate with `superintendent docs regenerate`._

Agent orchestration CLI for spawning autonomous Claude agents.

## Root flags

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--install-completion` | — | `bool` | no | `None` | Install completion for the current shell. |
| `--show-completion` | — | `bool` | no | `None` | Show completion for the current shell, to copy it or customize the installation. |
| `--version` | -V | `bool` | no | `False` | Show version and exit. |

## `superintendent cleanup`

Remove stale entries from the registry.

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--all` | — | `bool` | no | `False` | Clean up all stale entries. |
| `--dry-run` | — | `bool` | no | `False` | Show what would be removed. |
| `--force` | — | `bool` | no | `False` | Force removal of entries with local-only work. |
| `--name` | — | `str` | no | `None` | Remove a specific entry by name. |
| `--smart` | — | `bool` | no | `False` | Use smart cleanup (check PRs, staleness, remotes). |
| `--stale-days` | — | `int` | no | `30` | Days without commits before a branch is stale. |

## `superintendent install-skill`

Install the superintendent skill to a Claude Code skills directory.

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--force` | — | `bool` | no | `False` | Overwrite existing files. |
| `--target` | — | `path` | no | `None` | Target directory (defaults to ~/.claude/skills/superintendent). |

## `superintendent list`

List all active entries.

## `superintendent run`

Create a workspace and spawn an agent.

**Arguments:**

| Argument | Type | Description |
|---|---|---|
| `mode` | `enum[interactive|autonomous]` | Interaction mode: interactive or autonomous |
| `target` | `enum[sandbox|container|local]` | Execution target: sandbox, container, or local |

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--branch` | — | `str` | no | `None` | Git branch name for the worktree. |
| `--context-file` | — | `str` | no | `None` | Path to a context file for the agent. |
| `--dangerously-skip-isolation` | — | `bool` | no | `False` | Required for autonomous + local (no sandbox isolation). |
| `--dry-run` | — | `bool` | no | `False` | Show the plan without executing. |
| `--explain` | — | `bool` | no | `False` | Show what would happen without executing. |
| `--force` | --no-force | `bool` | no | `False` | Force recreation of existing sandbox/worktree. |
| `--no-merge` | — | `bool` | no | `False` | Skip auto-merging main into stale branches when reusing worktrees. |
| `--quiet` | -q | `bool` | no | `False` | Suppress non-error output. |
| `--repo` | — | `str` | yes | `None` | Path or URL to the repository. |
| `--sandbox-name` | — | `str` | no | `None` | Custom name for the Docker sandbox. |
| `--task` | — | `str` | yes | `None` | Task description for the agent. |
| `--template-dockerfile` | — | `str` | no | `None` | Custom Dockerfile template. |
| `--verbose` | -v | `bool` | no | `False` | Show detailed progress and backend commands. |

## `superintendent status`

Show agent lifecycle status for registered entries.

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--name` | — | `str` | no | `None` | Filter by entry name. |

## `superintendent docs regenerate`

Regenerate CLI_REFERENCE.md and cli-reference.json from the live CLI.

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--check` | — | `bool` | no | `False` | Show diff without writing. |

## `superintendent token add`

Add a GitHub token for a repository.

**Arguments:**

| Argument | Type | Description |
|---|---|---|
| `repo` | `str` | Repository in owner/repo format. |

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--permission` | -p | `str` | no | `None` | Token permission scopes. |
| `--token` | — | `str` | yes | `<prompt>` | GitHub token. |

## `superintendent token remove`

Remove a GitHub token for a repository.

**Arguments:**

| Argument | Type | Description |
|---|---|---|
| `repo` | `str` | Repository in owner/repo format. |

## `superintendent token remove-default`

Remove the default personal GitHub token.

## `superintendent token set-default`

Set the default personal GitHub token.

Validates the token by calling `gh api user` and stores the
associated GitHub username for owner-based resolution.

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--token` | — | `str` | yes | `<prompt>` | GitHub token. |

## `superintendent token status`

Show all stored tokens with metadata.

## `superintendent token update`

Update an existing GitHub token for a repository.

**Arguments:**

| Argument | Type | Description |
|---|---|---|
| `repo` | `str` | Repository in owner/repo format. |

**Flags:**

| Flag | Aliases | Type | Required | Default | Description |
|---|---|---|---|---|---|
| `--permission` | -p | `str` | no | `None` | Token permission scopes. |
| `--token` | — | `str` | yes | `<prompt>` | New GitHub token. |
