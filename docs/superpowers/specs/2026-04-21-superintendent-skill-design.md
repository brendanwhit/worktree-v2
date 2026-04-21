# Superintendent Self-Documenting Skill — Design Spec

## Problem

Agents using superintendent today have to chain `superintendent --help` calls into `superintendent run --help`, `superintendent token --help`, `superintendent token add --help`, etc. to understand the CLI surface. Each call costs a round-trip and potentially a permission prompt. The existing `README.md` covers the common path but doesn't carry every flag; `CLAUDE.md` is contributor-facing and not loaded outside the repo.

Hand-writing a reference doc that stays in sync with a growing typer CLI does not scale — the project already has 4 top-level commands plus 6 `token` subcommands, and is expected to grow (a `respond` command is already in another spec).

## Solution Overview

Ship a Claude Code skill that is half generated, half hand-written:

1. **Generated `CLI_REFERENCE.md`** — derived from the live typer app via introspection. Covers every command, subcommand, argument, and flag. Byte-identical across runs. Never hand-edited.

2. **Generated `cli-reference.json`** — the same data as structured JSON. Useful for tooling (shell completions, docs sites, version diffs) and easier to drift-check deterministically than markdown.

3. **Hand-written `SKILL.md`** — procedural guidance on *when* to reach for superintendent, *what to do before spawning* (`--explain`, `--dry-run`), how to recover from failures, and one-or-two critical gotchas. Roughly 60 lines, modeled after the obra/superpowers `brainstorming` skill's pattern of procedural-over-referential content.

Distribution:

- **In-repo** at `.claude/skills/superintendent/` (symlink to canonical location) — auto-picked-up by Claude Code when working inside the superintendent repo.
- **Installed globally** via a new `superintendent install-skill` subcommand that reads packaged resources and writes to `~/.claude/skills/superintendent/`.
- **Claude Code plugin** via a new `.claude-plugin/plugin.json` at repo root, so a user can install the plugin directly from this repo.

Freshness is enforced by a pytest test that regenerates the artifacts and byte-diffs them against the checked-in files. The error message points at `superintendent docs regenerate` as the one-liner fix.

## Architecture

### New subpackage: `superintendent.docs`

```
src/superintendent/docs/
├── __init__.py
├── model.py         # CommandSpec, FlagSpec, ArgumentSpec, CommandGroup dataclasses
├── introspect.py    # walk(app: typer.Typer) -> CommandGroup (pure, recursive)
├── render.py        # render_markdown(tree) + render_json(tree), two pure functions
└── assets/
    └── skills/
        └── superintendent/
            ├── SKILL.md             # hand-written
            ├── CLI_REFERENCE.md     # generated, checked in
            └── cli-reference.json   # generated, checked in
```

### Data flow

```
                ┌─────────────────────────────────┐
typer.Typer ────│ introspect.walk(app)            │── CommandGroup tree (pure)
                └─────────────────────────────────┘              │
                                                                 ▼
                              ┌──────────────────────────────────┴─────────┐
                              ▼                                            ▼
                   render.render_markdown(tree)              render.render_json(tree)
                              │                                            │
                              ▼                                            ▼
            assets/skills/superintendent/CLI_REFERENCE.md   .../cli-reference.json
```

### Two consumers of the pipeline

1. **`superintendent docs regenerate`** (new CLI subcommand) — writes the three artifacts to the canonical location. `--check` flag for dry-run.
2. **`tests/test_cli_reference.py`** — imports the same functions, regenerates in-memory, diffs against checked-in files. Fails with an actionable error message.

Both import directly from `superintendent.docs`. No shell-outs, no separate script.

**Why this shape:** `introspect.walk` is a pure function of a typer app — unit-testable with mock apps. Renderers are pure functions of the tree. Adding new CLI commands or subcommand groups triggers no changes to the docs subsystem — walker is recursive and picks them up automatically.

## File Layout

### Canonical location (single source of truth)

`src/superintendent/docs/assets/skills/superintendent/`

Contains `SKILL.md`, `CLI_REFERENCE.md`, `cli-reference.json`. Under `src/` so it's packaged into the wheel automatically via the existing `[tool.hatch.build.targets.wheel] packages = ["src/superintendent"]` configuration — no additional hatch include rules needed.

### In-repo Claude Code discovery

`.claude/skills/superintendent/` — a committed symlink pointing to `../../src/superintendent/docs/assets/skills/superintendent/`. Claude Code auto-loads skills from `.claude/skills/` when working inside the repo.

A symlink (rather than a copy) guarantees no drift between in-repo discovery and the canonical source. Git handles symlinks natively on Linux and macOS. Windows is not a supported dev platform for this project (CI runs on ubuntu only per `.github/workflows/ci.yml`), so symlink portability is not a concern.

### Plugin manifest

`.claude-plugin/plugin.json` at repo root:

```json
{
  "name": "superintendent",
  "description": "Spawn autonomous Claude agents in isolated Docker sandboxes, containers, or local worktrees.",
  "version": "0.3.0",
  "author": {
    "name": "Brendan Whitney",
    "email": "brendan.whitney@faraday.io"
  },
  "repository": "https://github.com/brendanwhit/superintendent",
  "license": "MIT",
  "keywords": ["agents", "claude", "docker", "worktree", "automation"],
  "skills": "./src/superintendent/docs/assets/skills/"
}
```

The `skills` field supplements the default `skills/` directory. Pointing it at the canonical location means the plugin, the symlink, and the wheel all reference the exact same files. Version tracks `pyproject.toml` — `install-skill` can hint at upgrades by comparing against the installed version.

Existing `commands/*.md` slash commands are auto-discovered from the default `commands/` path — no config needed for them.

### Installed location (target of `install-skill`)

`~/.claude/skills/superintendent/` — three files copied from the wheel's packaged resources.

### Summary of paths

| Purpose | Path | Created by |
|---|---|---|
| Canonical source | `src/superintendent/docs/assets/skills/superintendent/` | Hand-written + generator |
| In-repo discovery | `.claude/skills/superintendent/` (symlink) | Committed once |
| Plugin discovery | Referenced via `.claude-plugin/plugin.json` | Manifest only |
| Wheel package data | Same as canonical (under `src/`) | Hatch default |
| Global install | `~/.claude/skills/superintendent/` | `superintendent install-skill` |

## Components

### `src/superintendent/docs/model.py`

Three frozen dataclasses:

```python
@dataclass(frozen=True)
class ArgumentSpec:
    name: str
    type_repr: str           # "str", "int", "enum[a|b|c]", etc.
    help: str
    choices: tuple[str, ...] | None

@dataclass(frozen=True)
class FlagSpec:
    name: str                # "--foo" (primary long name)
    aliases: tuple[str, ...] # ("-f",)
    type_repr: str
    required: bool
    default: str             # string repr of default, "None" for None, "<prompt>" for prompt=True
    help: str
    is_bool: bool

@dataclass(frozen=True)
class CommandSpec:
    name: str
    help: str                # from docstring or typer help=
    arguments: tuple[ArgumentSpec, ...]
    flags: tuple[FlagSpec, ...]

@dataclass(frozen=True)
class CommandGroup:
    name: str                # "superintendent" or subgroup name
    help: str
    commands: tuple[CommandSpec, ...]
    subgroups: tuple["CommandGroup", ...]
```

Tuples (not lists) for hashability and for guaranteed iteration order in rendered output.

### `src/superintendent/docs/introspect.py`

Single public function:

```python
def walk(app: typer.Typer) -> CommandGroup:
    """Walk a typer app recursively, returning a CommandGroup tree.

    Uses typer internals:
    - app.registered_commands for direct commands
    - app.registered_groups for subgroups added via app.add_typer(...)
    - For each command, reads the underlying click.Command via
      typer.main.get_command_from_info() to extract Argument/Option params.

    Deterministic ordering: commands sorted by name within each group,
    flags sorted by primary name, arguments preserved in declaration order.
    """
```

Sorting rules are explicit so that re-registering commands in `main.py` in different order doesn't produce diff churn in `CLI_REFERENCE.md`.

Edge cases the walker must handle:
- Commands with no explicit `name=` (derived from function name)
- `list_cmd` → `list` remapping (already present in `main.py`)
- Callback-only options on the root app (e.g., `--version`)
- Enum types (`Mode`, `Target`, `Verbosity`) rendered as `enum[a|b|c]`
- `typer.Option(..., prompt=True, hide_input=True)` — render default as `<prompt>` rather than leaking the sentinel
- `typer.Option(None, ...)` optional with None default — render default as `None`
- `noqa: ARG001` unused params — skip or include? Include them; the user can still pass them and they are part of the public CLI surface.

### `src/superintendent/docs/render.py`

```python
def render_markdown(tree: CommandGroup) -> str: ...
def render_json(tree: CommandGroup) -> str: ...
```

Both pure. `render_json` uses `json.dumps(data, indent=2, sort_keys=True)` for deterministic output. `render_markdown` produces:

- A top-level `# Superintendent CLI Reference` header with a standing "Generated file — do not edit" note
- One H2 per command (`## superintendent run`)
- Help text as a paragraph
- Arguments table if any
- Flags table
- Nested subgroups rendered recursively with H3/H4 headers

No timestamps, no versions, no metadata that varies run-to-run.

### `src/superintendent/cli/main.py` additions

New `docs` subgroup added via `app.add_typer(docs_app)`:

```python
@docs_app.command()
def regenerate(
    check: bool = typer.Option(False, "--check", help="Show diff without writing."),
) -> None:
    """Regenerate CLI_REFERENCE.md and cli-reference.json from the live CLI."""
```

Reads the canonical path via `importlib.resources`, runs the pipeline, writes (or diffs on `--check`).

New top-level `install-skill` command:

```python
@app.command("install-skill")
def install_skill(
    target: Path = typer.Option(
        Path.home() / ".claude" / "skills" / "superintendent",
        help="Target directory for the installed skill.",
    ),
    force: bool = typer.Option(False, help="Overwrite existing files."),
) -> None:
    """Install the superintendent skill to a user-level Claude Code skills directory."""
```

Reads the three files from the packaged resources via `importlib.resources.files("superintendent.docs.assets.skills.superintendent")`, writes to `target`. Idempotent when `force=True`; errors if target exists and `force=False`.

### Hand-written `SKILL.md` (canonical content)

```markdown
---
name: superintendent
description: Use when you need to spawn an autonomous Claude agent on a specific task — fire-and-forget work, parallel subtasks, or work that needs isolation (Docker sandbox, container, or clean worktree) from your current session. Not for interactive collaboration in your current session.
---

# Superintendent

Spawns Claude agents in isolated workspaces. One sandbox per repo (auth persists). State lives in `.superintendent/`.

## When to use — and when NOT to

**Use when:**
- Task can run to completion without your ongoing direction
- N independent subtasks can run in parallel
- Work needs isolation (risky operations, dependency experiments)
- You need a clean worktree separate from current branch

**Don't use when:**
- You want to iterate conversationally (just keep working in this session)
- Task is small enough to finish here
- You need to watch and redirect mid-run (interactive mode exists, but a normal session is usually simpler)

## Before spawning anything

Run `--explain` to see the mode × target decision for your task:

    superintendent run <mode> <target> --explain --repo <repo> --task <task>

Then dry-run to preview the exact plan:

    superintendent run <mode> <target> ... --dry-run

**Never skip both.** Guessing at mode/target wastes a sandbox spin-up.

## Recovering from failures

Agent failed mid-run? Don't re-spawn blindly.

1. `superintendent list` — find the entry
2. `superintendent status <name>` — check exit state and what step failed
3. Fix the underlying issue
4. `superintendent run ... --force` — reuses the worktree, rebuilds state

## Critical rules

- **Never** pass `--dangerously-skip-isolation` without understanding what you're skipping. It's required for `autonomous + local` only because that combo has no sandbox.
- **Before `cleanup --all --smart`**, always dry-run first — it will remove merged/stale branches.
- **After spawning autonomous**, check back with `status` — the parent session doesn't know when the child finishes.

## Full command and flag reference

See [CLI_REFERENCE.md](./CLI_REFERENCE.md) — auto-generated from the CLI, always current.
```

## Freshness Enforcement

### `tests/test_cli_reference.py`

Three layered tests:

1. **JSON byte-diff** (primary drift signal — easiest to keep deterministic):

```python
def test_cli_reference_json_is_current():
    from superintendent.cli.main import app
    from superintendent.docs import introspect, render

    tree = introspect.walk(app)
    expected = render.render_json(tree)
    actual = (ASSET_DIR / "cli-reference.json").read_text()
    assert actual == expected, STALE_MESSAGE
```

2. **Markdown byte-diff** (secondary, catches renderer regressions):

```python
def test_cli_reference_md_is_current():
    ...  # same shape, on CLI_REFERENCE.md
```

3. **Structural assertions** (resilient to renderer changes; guards against a future typer upgrade silently breaking the walker):

```python
def test_introspection_covers_all_top_level_commands():
    tree = introspect.walk(app)
    command_names = {c.name for c in tree.commands}
    assert {"run", "list", "cleanup", "status", "install-skill"} <= command_names
    subgroup_names = {g.name for g in tree.subgroups}
    assert "token" in subgroup_names
    assert "docs" in subgroup_names

def test_run_command_has_required_repo_and_task_flags():
    tree = introspect.walk(app)
    run = next(c for c in tree.commands if c.name == "run")
    names = {f.name for f in run.flags}
    assert "--repo" in names
    assert "--task" in names
    repo_flag = next(f for f in run.flags if f.name == "--repo")
    assert repo_flag.required is True
```

Plus unit tests on the introspection itself using small mock typer apps, and a determinism test that regenerates twice and asserts byte-equality.

### Stale message

Constant at the top of the test file:

```python
STALE_MESSAGE = (
    "Generated CLI reference is out of date.\n"
    "Run: uv run superintendent docs regenerate\n"
    "Then commit the updated files under "
    "src/superintendent/docs/assets/skills/superintendent/."
)
```

### CI

No new workflow. The existing `test` job in `.github/workflows/ci.yml` runs `pytest` across Python 3.11/3.12/3.13; the drift test runs alongside everything else.

## Scope

### In scope

- `superintendent.docs` subpackage (`model.py`, `introspect.py`, `render.py`)
- Hand-written `SKILL.md`
- Generated `CLI_REFERENCE.md` and `cli-reference.json` (checked in)
- `superintendent docs regenerate` subcommand
- `superintendent install-skill` subcommand
- `.claude-plugin/plugin.json` at repo root
- `.claude/skills/superintendent/` symlink to canonical location
- `tests/test_cli_reference.py` with byte-diff + structural assertions
- Unit tests for `introspect.walk` and renderer determinism
- README section documenting `install-skill` and plugin install paths

### Out of scope (explicit non-goals)

- Shell completion generation (enabled by the JSON artifact but not built in this project)
- HTML / docs-site rendering
- Submitting the plugin to a public Claude Code marketplace
- Migrating existing `commands/*.md` slash commands to new patterns
- A `--self-update` command that re-runs `install-skill` after `uv tool upgrade`
- Auto-install-on-first-run behavior (explicitly rejected — user must run `install-skill`)

## Testing Strategy

| Test | What it catches |
|---|---|
| `test_cli_reference_json_is_current` | Any drift between the live CLI and the checked-in JSON |
| `test_cli_reference_md_is_current` | Any drift in the human-facing markdown; renderer regressions |
| Structural assertions | Future typer API changes that break the walker but still produce *some* output (byte-diffs would pass if the checked-in file was regenerated under the broken walker) |
| `test_walk_handles_enum_argument` | Enum arguments render correctly |
| `test_walk_handles_optional_flag` | `Optional[str]` defaults render as `None` |
| `test_walk_handles_prompt_flag` | Prompt-style options render default as `<prompt>` |
| `test_walk_handles_nested_subgroup` | `app.add_typer(sub)` is recursed into |
| `test_render_json_is_deterministic` | Two runs produce byte-identical output |
| `test_render_markdown_is_deterministic` | Same for markdown |
| `test_install_skill_writes_files` | `install-skill --target <tempdir>` writes three files with correct content |
| `test_install_skill_idempotent_with_force` | Re-running with `--force` overwrites cleanly |
| `test_install_skill_errors_without_force` | Errors if target exists and `--force` absent |

All of the above run in the existing `test` CI job. No new workflow, no new infrastructure.

## Implementation Order (for the plan document)

The writing-plans skill will produce the actual plan; this section is a hint for ordering:

1. Scaffold `superintendent.docs` package with `model.py`
2. Build `introspect.walk` with unit tests (mock typer apps)
3. Build `render_json` with determinism test
4. Build `render_markdown` with determinism test
5. Add `docs regenerate` subcommand
6. Generate initial `CLI_REFERENCE.md` and `cli-reference.json`
7. Write hand-written `SKILL.md`
8. Add drift + structural tests
9. Add `install-skill` subcommand + tests
10. Add `.claude-plugin/plugin.json`
11. Add `.claude/skills/superintendent/` symlink
12. Update `README.md` with install instructions

## Risks and Open Questions

- **Typer internals may change.** `app.registered_commands` and `app.registered_groups` are public-ish but not guaranteed stable across typer versions. Mitigation: the structural assertion tests catch silent breakage (e.g., `run` command missing from the tree). If typer API churn becomes painful, we could switch to `typer.main.get_command(app)` to get the underlying `click.Group` and walk click's more stable API.

- **Click Context vs. typer callback.** The root `@app.callback()` defines a `--version` option that lives on the group, not on any single command. The walker must surface this as a "root flag" section in the output, not silently drop it.

- **Symlinks in git.** The `.claude/skills/superintendent/` symlink must be committed as a symlink, not a directory copy. Needs a smoke test: `git ls-files -s .claude/skills/superintendent` should show mode `120000`. If someone accidentally commits it as a directory copy, drift is silently possible. Adding a CI check (`test -L .claude/skills/superintendent`) is cheap insurance — consider adding to the `lint` job.

- **Resource loading in the wheel.** `importlib.resources.files("superintendent.docs.assets.skills.superintendent")` needs the directory to exist as a proper package (with `__init__.py`) or we must use the namespace-package-friendly `files()` API with path-style access. The implementation will need to verify which form works cleanly with hatchling's wheel output.

- **Version bumping.** Per project convention, every PR bumps the version in both `pyproject.toml` and `src/superintendent/__init__.py`. This spec introduces a new CLI subcommand (`docs`, `install-skill`), which is a minor bump (0.3.0 → 0.4.0).

- **Plugin manifest version drift.** `plugin.json` includes a `version` field that duplicates `pyproject.toml`. A small test or CI check should assert they match, similar to the existing `version-check.yml` workflow.
