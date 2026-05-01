# Superintendent Self-Documenting Skill — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a Claude Code skill from the typer CLI so that agents have a complete, always-current reference without making nested `--help` calls.

**Architecture:** A new `superintendent.docs` subpackage introspects the typer app via click, builds a `CommandGroup` tree, and renders both `CLI_REFERENCE.md` and `cli-reference.json`. A pytest test diffs the generated output against checked-in files to catch drift; a `superintendent docs regenerate` subcommand fixes it. The skill ships in three places: in-repo at `.claude/skills/superintendent/` (symlink to canonical), via `superintendent install-skill` for global Claude Code use, and via a `.claude-plugin/plugin.json` for plugin-style install.

**Tech Stack:** Python 3.11+, typer, click (via `typer.main.get_command`), pytest, hatchling, ruff, ty.

**Spec:** `docs/superpowers/specs/2026-04-21-superintendent-skill-design.md`

---

## File Inventory

**Created (new files):**

- `src/superintendent/docs/__init__.py` — package marker
- `src/superintendent/docs/model.py` — `ArgumentSpec`, `FlagSpec`, `CommandSpec`, `CommandGroup` dataclasses
- `src/superintendent/docs/introspect.py` — `walk(app: typer.Typer) -> CommandGroup`
- `src/superintendent/docs/render.py` — `render_markdown()`, `render_json()`
- `src/superintendent/docs/assets/skills/superintendent/SKILL.md` — hand-written
- `src/superintendent/docs/assets/skills/superintendent/CLI_REFERENCE.md` — generated, checked in
- `src/superintendent/docs/assets/skills/superintendent/cli-reference.json` — generated, checked in
- `.claude-plugin/plugin.json` — Claude Code plugin manifest
- `.claude/skills/superintendent` — symlink to canonical asset directory
- `tests/test_docs_model.py`
- `tests/test_docs_introspect.py`
- `tests/test_docs_render.py`
- `tests/test_docs_command.py` — for `docs regenerate`
- `tests/test_install_skill.py`
- `tests/test_cli_reference.py` — drift + structural assertions
- `tests/test_plugin_manifest.py` — version-match check

**Modified:**

- `src/superintendent/cli/main.py` — add `docs` subgroup with `regenerate`, add `install-skill` command
- `src/superintendent/__init__.py` — bump `__version__` to `0.4.0`
- `pyproject.toml` — bump `version` to `0.4.0`
- `README.md` — add install-skill and plugin install sections

---

## Task 1: Scaffold `superintendent.docs` package + data model

**Files:**
- Create: `src/superintendent/docs/__init__.py`
- Create: `src/superintendent/docs/model.py`
- Create: `tests/test_docs_model.py`

- [ ] **Step 1: Create the package marker**

```bash
mkdir -p src/superintendent/docs
```

Create `src/superintendent/docs/__init__.py` with content:

```python
"""CLI documentation generation for superintendent."""
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_docs_model.py`:

```python
"""Tests for the docs data model."""

from superintendent.docs.model import (
    ArgumentSpec,
    CommandGroup,
    CommandSpec,
    FlagSpec,
)


class TestArgumentSpec:
    def test_create_argument(self):
        arg = ArgumentSpec(
            name="mode",
            type_repr="enum[interactive|autonomous]",
            help="Interaction mode",
            choices=("interactive", "autonomous"),
        )
        assert arg.name == "mode"
        assert arg.choices == ("interactive", "autonomous")

    def test_argument_is_hashable(self):
        arg = ArgumentSpec(name="x", type_repr="str", help="", choices=None)
        assert hash(arg) is not None  # frozen dataclass


class TestFlagSpec:
    def test_create_flag(self):
        flag = FlagSpec(
            name="--repo",
            aliases=(),
            type_repr="str",
            required=True,
            default="None",
            help="Path or URL to the repository.",
            is_bool=False,
        )
        assert flag.required is True
        assert flag.is_bool is False

    def test_bool_flag(self):
        flag = FlagSpec(
            name="--dry-run",
            aliases=(),
            type_repr="bool",
            required=False,
            default="False",
            help="Show the plan without executing.",
            is_bool=True,
        )
        assert flag.is_bool is True


class TestCommandSpec:
    def test_create_command(self):
        flag = FlagSpec(
            name="--repo", aliases=(), type_repr="str", required=True,
            default="None", help="", is_bool=False,
        )
        cmd = CommandSpec(name="run", help="Spawn an agent.", arguments=(), flags=(flag,))
        assert cmd.name == "run"
        assert len(cmd.flags) == 1


class TestCommandGroup:
    def test_create_empty_group(self):
        group = CommandGroup(
            name="superintendent", help="Agent orchestration CLI.",
            flags=(), commands=(), subgroups=(),
        )
        assert group.commands == ()

    def test_group_with_root_flag(self):
        version = FlagSpec(
            name="--version", aliases=("-V",), type_repr="bool", required=False,
            default="False", help="Show version and exit.", is_bool=True,
        )
        group = CommandGroup(
            name="superintendent", help="", flags=(version,),
            commands=(), subgroups=(),
        )
        assert group.flags[0].name == "--version"

    def test_group_is_hashable(self):
        group = CommandGroup(name="x", help="", flags=(), commands=(), subgroups=())
        assert hash(group) is not None
```

- [ ] **Step 3: Run test to verify it fails**

```bash
uv run pytest tests/test_docs_model.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'superintendent.docs.model'`.

- [ ] **Step 4: Implement the data model**

Create `src/superintendent/docs/model.py`:

```python
"""Data model for the CLI introspection tree."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ArgumentSpec:
    """A positional argument on a CLI command."""

    name: str
    type_repr: str
    help: str
    choices: tuple[str, ...] | None


@dataclass(frozen=True)
class FlagSpec:
    """A flag (option) on a CLI command or group."""

    name: str
    aliases: tuple[str, ...]
    type_repr: str
    required: bool
    default: str
    help: str
    is_bool: bool


@dataclass(frozen=True)
class CommandSpec:
    """A leaf command (e.g. `superintendent run`)."""

    name: str
    help: str
    arguments: tuple[ArgumentSpec, ...]
    flags: tuple[FlagSpec, ...]


@dataclass(frozen=True)
class CommandGroup:
    """A typer group — root app or sub-app added via add_typer."""

    name: str
    help: str
    flags: tuple[FlagSpec, ...]
    commands: tuple[CommandSpec, ...]
    subgroups: tuple["CommandGroup", ...]
```

- [ ] **Step 5: Run test to verify it passes**

```bash
uv run pytest tests/test_docs_model.py -v
```

Expected: PASS — 7 tests passed.

- [ ] **Step 6: Lint and format**

```bash
uv run ruff check src/superintendent/docs/ tests/test_docs_model.py
uv run ruff format src/superintendent/docs/ tests/test_docs_model.py
```

- [ ] **Step 7: Commit**

```bash
git add src/superintendent/docs/__init__.py src/superintendent/docs/model.py tests/test_docs_model.py
git commit -m "feat: add docs subpackage data model"
```

---

## Task 2: `introspect.walk` — root commands and basic flags

**Files:**
- Create: `src/superintendent/docs/introspect.py`
- Create: `tests/test_docs_introspect.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_introspect.py`:

```python
"""Tests for typer-app introspection."""

import typer

from superintendent.docs.introspect import walk


class TestWalkBasic:
    def test_walk_empty_app(self):
        app = typer.Typer(name="empty")

        @app.command()
        def hello() -> None:
            """Say hello."""
            pass

        tree = walk(app)
        assert tree.name == "empty"
        assert len(tree.commands) == 1
        assert tree.commands[0].name == "hello"
        assert tree.commands[0].help == "Say hello."

    def test_walk_command_with_str_flag(self):
        app = typer.Typer()

        @app.command()
        def greet(name: str = typer.Option(..., help="Person's name.")) -> None:
            """Greet someone."""
            pass

        tree = walk(app)
        cmd = tree.commands[0]
        names = {f.name for f in cmd.flags}
        assert "--name" in names
        name_flag = next(f for f in cmd.flags if f.name == "--name")
        assert name_flag.required is True
        assert name_flag.help == "Person's name."

    def test_walk_command_with_bool_flag(self):
        app = typer.Typer()

        @app.command()
        def go(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
            pass

        tree = walk(app)
        flag = next(f for f in tree.commands[0].flags if f.name == "--verbose")
        assert flag.is_bool is True
        assert flag.aliases == ("-v",)
        assert flag.default == "False"

    def test_commands_sorted_by_name(self):
        app = typer.Typer()

        @app.command()
        def zebra() -> None:
            pass

        @app.command()
        def alpha() -> None:
            pass

        tree = walk(app)
        names = [c.name for c in tree.commands]
        assert names == sorted(names)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_docs_introspect.py -v
```

Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement `walk` (basic)**

Create `src/superintendent/docs/introspect.py`:

```python
"""Walk a typer app and produce a CommandGroup tree."""

import click
import typer

from superintendent.docs.model import (
    ArgumentSpec,
    CommandGroup,
    CommandSpec,
    FlagSpec,
)


def walk(app: typer.Typer) -> CommandGroup:
    """Walk a typer app recursively, returning a CommandGroup tree.

    Goes through click (more stable than typer internals): typer.main.get_command
    returns a click.Group whose .commands and .params are walked.
    """
    click_obj = typer.main.get_command(app)
    if not isinstance(click_obj, click.Group):
        raise TypeError(f"Expected click.Group, got {type(click_obj).__name__}")
    return _walk_group(click_obj, name=app.info.name or click_obj.name or "")


def _walk_group(group: click.Group, name: str) -> CommandGroup:
    flags = tuple(_param_to_flag(p) for p in group.params if _is_option(p))
    commands: list[CommandSpec] = []
    subgroups: list[CommandGroup] = []
    for child_name, child in group.commands.items():
        if isinstance(child, click.Group):
            subgroups.append(_walk_group(child, name=child_name))
        else:
            commands.append(_walk_command(child, name=child_name))
    commands.sort(key=lambda c: c.name)
    subgroups.sort(key=lambda g: g.name)
    return CommandGroup(
        name=name,
        help=(group.help or "").strip(),
        flags=tuple(sorted(flags, key=lambda f: f.name)),
        commands=tuple(commands),
        subgroups=tuple(subgroups),
    )


def _walk_command(cmd: click.Command, name: str) -> CommandSpec:
    arguments: list[ArgumentSpec] = []
    flags: list[FlagSpec] = []
    for p in cmd.params:
        if _is_option(p):
            flags.append(_param_to_flag(p))
        else:
            arguments.append(_param_to_argument(p))
    return CommandSpec(
        name=name,
        help=(cmd.help or cmd.short_help or "").strip(),
        arguments=tuple(arguments),
        flags=tuple(sorted(flags, key=lambda f: f.name)),
    )


def _is_option(param: click.Parameter) -> bool:
    return isinstance(param, click.Option)


def _param_to_flag(param: click.Parameter) -> FlagSpec:
    opts = list(param.opts) + list(param.secondary_opts)
    long_opts = [o for o in opts if o.startswith("--")]
    short_opts = [o for o in opts if o.startswith("-") and not o.startswith("--")]
    primary = long_opts[0] if long_opts else (short_opts[0] if short_opts else "")
    aliases = tuple(o for o in opts if o != primary)
    is_bool = isinstance(param.type, click.types.BoolParamType)
    return FlagSpec(
        name=primary,
        aliases=aliases,
        type_repr=_type_repr(param.type),
        required=bool(getattr(param, "required", False)),
        default=_default_repr(param),
        help=(getattr(param, "help", "") or "").strip(),
        is_bool=is_bool,
    )


def _param_to_argument(param: click.Parameter) -> ArgumentSpec:
    choices = None
    if isinstance(param.type, click.Choice):
        choices = tuple(param.type.choices)
    return ArgumentSpec(
        name=param.name or "",
        type_repr=_type_repr(param.type),
        help=(getattr(param, "help", "") or "").strip(),
        choices=choices,
    )


def _type_repr(param_type: click.ParamType) -> str:
    if isinstance(param_type, click.Choice):
        return f"enum[{'|'.join(param_type.choices)}]"
    if isinstance(param_type, click.types.BoolParamType):
        return "bool"
    if isinstance(param_type, click.types.IntParamType):
        return "int"
    if isinstance(param_type, click.types.StringParamType):
        return "str"
    return param_type.name or "str"


def _default_repr(param: click.Parameter) -> str:
    if getattr(param, "prompt", None):
        return "<prompt>"
    default = getattr(param, "default", None)
    if default is None:
        return "None"
    if callable(default):
        return "<dynamic>"
    return repr(default)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_docs_introspect.py -v
```

Expected: PASS — 4 tests passed.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check src/superintendent/docs/ tests/test_docs_introspect.py
uv run ruff format src/superintendent/docs/ tests/test_docs_introspect.py
```

- [ ] **Step 6: Commit**

```bash
git add src/superintendent/docs/introspect.py tests/test_docs_introspect.py
git commit -m "feat: add introspect.walk for typer commands and basic flags"
```

---

## Task 3: `introspect.walk` — arguments, enums, optional and prompt flags

**Files:**
- Modify: `src/superintendent/docs/introspect.py` (no changes expected — verify behavior)
- Modify: `tests/test_docs_introspect.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_docs_introspect.py`:

```python
import enum

from superintendent.docs.model import ArgumentSpec


class _Mode(str, enum.Enum):
    interactive = "interactive"
    autonomous = "autonomous"


class TestWalkArguments:
    def test_walk_command_with_argument(self):
        app = typer.Typer()

        @app.command()
        def run(name: str = typer.Argument(..., help="Workspace name.")) -> None:
            pass

        tree = walk(app)
        cmd = tree.commands[0]
        assert len(cmd.arguments) == 1
        assert cmd.arguments[0].name == "name"
        assert cmd.arguments[0].help == "Workspace name."

    def test_walk_enum_argument(self):
        app = typer.Typer()

        @app.command()
        def run(mode: _Mode = typer.Argument(..., help="Mode.")) -> None:
            pass

        tree = walk(app)
        arg = tree.commands[0].arguments[0]
        assert arg.choices == ("interactive", "autonomous")
        assert arg.type_repr == "enum[interactive|autonomous]"


class TestWalkOptionalAndPromptFlags:
    def test_optional_flag_has_none_default(self):
        app = typer.Typer()

        @app.command()
        def run(branch: str | None = typer.Option(None, help="Branch.")) -> None:
            pass

        tree = walk(app)
        flag = next(f for f in tree.commands[0].flags if f.name == "--branch")
        assert flag.default == "None"
        assert flag.required is False

    def test_prompt_flag_default_is_sentinel(self):
        app = typer.Typer()

        @app.command()
        def login(token: str = typer.Option(..., prompt=True, hide_input=True)) -> None:
            pass

        tree = walk(app)
        flag = next(f for f in tree.commands[0].flags if f.name == "--token")
        assert flag.default == "<prompt>"
```

- [ ] **Step 2: Run new tests; expect them to pass against the existing implementation**

```bash
uv run pytest tests/test_docs_introspect.py -v
```

Expected: All tests pass. The implementation from Task 2 already handles these cases — this task is verification.

- [ ] **Step 3: If any tests fail, fix `introspect.py` minimally**

If a test fails, read the error, identify the gap (likely in `_default_repr`, `_type_repr`, or enum choice extraction), patch, re-run.

- [ ] **Step 4: Commit**

```bash
git add tests/test_docs_introspect.py src/superintendent/docs/introspect.py
git commit -m "test: cover arguments, enums, optional and prompt flags in introspect"
```

---

## Task 4: `introspect.walk` — nested subgroups

**Files:**
- Modify: `tests/test_docs_introspect.py`
- Modify: `src/superintendent/docs/introspect.py` (likely no change — verify recursion works)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_docs_introspect.py`:

```python
class TestWalkSubgroups:
    def test_walk_nested_subgroup(self):
        app = typer.Typer(name="parent")
        sub = typer.Typer(name="token", help="Manage tokens.")
        app.add_typer(sub)

        @sub.command()
        def add(repo: str = typer.Argument(...)) -> None:
            """Add a token."""
            pass

        @sub.command()
        def remove(repo: str = typer.Argument(...)) -> None:
            """Remove a token."""
            pass

        tree = walk(app)
        assert len(tree.subgroups) == 1
        token_group = tree.subgroups[0]
        assert token_group.name == "token"
        assert {c.name for c in token_group.commands} == {"add", "remove"}

    def test_subgroups_sorted(self):
        app = typer.Typer()
        z = typer.Typer(name="zebra")
        a = typer.Typer(name="alpha")

        @z.command()
        def cmd_z() -> None:
            pass

        @a.command()
        def cmd_a() -> None:
            pass

        app.add_typer(z)
        app.add_typer(a)

        tree = walk(app)
        names = [g.name for g in tree.subgroups]
        assert names == ["alpha", "zebra"]
```

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_docs_introspect.py -v
```

Expected: PASS. The Task 2 implementation already recurses via `_walk_group`. If a test fails, the most likely gap is `app.info.name` not being passed to `_walk_group`; fix and re-run.

- [ ] **Step 3: Commit**

```bash
git add tests/test_docs_introspect.py src/superintendent/docs/introspect.py
git commit -m "test: cover nested typer subgroups in introspect"
```

---

## Task 5: `introspect.walk` — root callback flags

**Files:**
- Modify: `tests/test_docs_introspect.py`
- Modify: `src/superintendent/docs/introspect.py` (likely already works — root flags come through `click.Group.params`)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_docs_introspect.py`:

```python
class TestWalkRootCallback:
    def test_root_callback_version_flag_surfaces_on_group(self):
        app = typer.Typer()

        @app.callback()
        def main(
            version: bool = typer.Option(
                False, "--version", "-V", help="Show version and exit.",
            ),
        ) -> None:
            """Root help."""
            pass

        @app.command()
        def hello() -> None:
            pass

        tree = walk(app)
        names = {f.name for f in tree.flags}
        assert "--version" in names
        version_flag = next(f for f in tree.flags if f.name == "--version")
        assert version_flag.help == "Show version and exit."
        assert version_flag.is_bool is True
        assert "-V" in version_flag.aliases
```

- [ ] **Step 2: Run test**

```bash
uv run pytest tests/test_docs_introspect.py::TestWalkRootCallback -v
```

Expected: PASS. Click's `Group.params` surfaces callback options here; if it fails, likely `_walk_group` is not reading `group.params` (Task 2's implementation does — verify).

- [ ] **Step 3: Verify on the real superintendent app**

Sanity check (informational, no commit yet):

```bash
uv run python -c "
from superintendent.cli.main import app
from superintendent.docs.introspect import walk
tree = walk(app)
print('root flags:', [f.name for f in tree.flags])
print('top-level commands:', [c.name for c in tree.commands])
print('subgroups:', [g.name for g in tree.subgroups])
"
```

Expected output: `--version` appears in root flags; commands include `cleanup`, `list`, `run`, `status`; subgroups include `token`.

- [ ] **Step 4: Commit**

```bash
git add tests/test_docs_introspect.py src/superintendent/docs/introspect.py
git commit -m "test: cover root callback flags in introspect"
```

---

## Task 6: `render_json` with determinism

**Files:**
- Create: `src/superintendent/docs/render.py`
- Create: `tests/test_docs_render.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_render.py`:

```python
"""Tests for markdown and JSON renderers."""

import json

import typer

from superintendent.docs.introspect import walk
from superintendent.docs.model import (
    ArgumentSpec,
    CommandGroup,
    CommandSpec,
    FlagSpec,
)
from superintendent.docs.render import render_json


def _sample_tree() -> CommandGroup:
    flag = FlagSpec(
        name="--repo", aliases=(), type_repr="str", required=True,
        default="None", help="Repo path.", is_bool=False,
    )
    cmd = CommandSpec(name="run", help="Run.", arguments=(), flags=(flag,))
    return CommandGroup(
        name="superintendent", help="Top-level help.",
        flags=(), commands=(cmd,), subgroups=(),
    )


class TestRenderJSON:
    def test_render_returns_valid_json(self):
        out = render_json(_sample_tree())
        data = json.loads(out)
        assert data["name"] == "superintendent"
        assert data["commands"][0]["name"] == "run"
        assert data["commands"][0]["flags"][0]["name"] == "--repo"

    def test_render_json_is_deterministic(self):
        tree = _sample_tree()
        assert render_json(tree) == render_json(tree)

    def test_render_json_keys_are_sorted(self):
        out = render_json(_sample_tree())
        # sort_keys=True means alphabetical key order in each object
        first_obj = json.loads(out)
        keys = list(first_obj.keys())
        assert keys == sorted(keys)

    def test_render_json_against_real_app(self):
        from superintendent.cli.main import app
        out = render_json(walk(app))
        data = json.loads(out)
        assert data["name"]
        names = {c["name"] for c in data["commands"]}
        assert {"run", "list", "cleanup", "status"} <= names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_docs_render.py -v
```

Expected: FAIL — `ModuleNotFoundError` for `render`.

- [ ] **Step 3: Implement `render_json`**

Create `src/superintendent/docs/render.py`:

```python
"""Render a CommandGroup tree as markdown or JSON."""

import json
from dataclasses import asdict

from superintendent.docs.model import CommandGroup


def render_json(tree: CommandGroup) -> str:
    """Render the tree as deterministic JSON.

    Sorted keys, two-space indent, no trailing whitespace, terminal newline.
    """
    return json.dumps(asdict(tree), indent=2, sort_keys=True) + "\n"
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_docs_render.py -v
```

Expected: PASS — 4 tests pass.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check src/superintendent/docs/render.py tests/test_docs_render.py
uv run ruff format src/superintendent/docs/render.py tests/test_docs_render.py
```

- [ ] **Step 6: Commit**

```bash
git add src/superintendent/docs/render.py tests/test_docs_render.py
git commit -m "feat: add render_json with determinism guarantees"
```

---

## Task 7: `render_markdown` with determinism

**Files:**
- Modify: `src/superintendent/docs/render.py`
- Modify: `tests/test_docs_render.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_docs_render.py`:

```python
from superintendent.docs.render import render_markdown


class TestRenderMarkdown:
    def test_render_includes_top_header(self):
        out = render_markdown(_sample_tree())
        assert "# Superintendent CLI Reference" in out
        assert "Generated file" in out  # do-not-edit notice

    def test_render_includes_command(self):
        out = render_markdown(_sample_tree())
        assert "## `superintendent run`" in out
        assert "--repo" in out
        assert "Repo path." in out

    def test_render_markdown_is_deterministic(self):
        tree = _sample_tree()
        assert render_markdown(tree) == render_markdown(tree)

    def test_render_markdown_no_timestamps(self):
        # 2026 is the current year; many timestamp formats include it.
        # If a generator introduces "Generated at 2026-...", this fires.
        out = render_markdown(_sample_tree())
        # The string "Generated file" is allowed (do-not-edit notice).
        # "Generated at" or "Generated on" with a year is not.
        assert "Generated at" not in out
        assert "Generated on" not in out

    def test_render_markdown_against_real_app(self):
        from superintendent.cli.main import app
        out = render_markdown(walk(app))
        assert "## `superintendent run`" in out
        assert "## `superintendent token add`" in out  # nested subgroup
        assert "--repo" in out
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_docs_render.py::TestRenderMarkdown -v
```

Expected: FAIL — `render_markdown` not defined.

- [ ] **Step 3: Implement `render_markdown`**

Append to `src/superintendent/docs/render.py`:

```python
def render_markdown(tree: CommandGroup) -> str:
    """Render the tree as a deterministic markdown reference.

    Stable column widths, no timestamps, no metadata that varies run-to-run.
    """
    lines: list[str] = []
    lines.append("# Superintendent CLI Reference")
    lines.append("")
    lines.append(
        "_Generated file — do not edit. Regenerate with "
        "`superintendent docs regenerate`._"
    )
    lines.append("")
    if tree.help:
        lines.append(tree.help)
        lines.append("")
    if tree.flags:
        lines.append("## Root flags")
        lines.append("")
        lines.extend(_flag_table(tree.flags))
        lines.append("")
    _render_group(tree, prefix=tree.name, lines=lines)
    return "\n".join(lines).rstrip() + "\n"


def _render_group(group: "CommandGroup", prefix: str, lines: list[str]) -> None:
    for cmd in group.commands:
        lines.append(f"## `{prefix} {cmd.name}`")
        lines.append("")
        if cmd.help:
            lines.append(cmd.help)
            lines.append("")
        if cmd.arguments:
            lines.append("**Arguments:**")
            lines.append("")
            lines.extend(_argument_table(cmd.arguments))
            lines.append("")
        if cmd.flags:
            lines.append("**Flags:**")
            lines.append("")
            lines.extend(_flag_table(cmd.flags))
            lines.append("")
    for sub in group.subgroups:
        _render_group(sub, prefix=f"{prefix} {sub.name}", lines=lines)


def _flag_table(flags: tuple) -> list[str]:
    rows = ["| Flag | Aliases | Type | Required | Default | Description |",
            "|---|---|---|---|---|---|"]
    for f in flags:
        aliases = ", ".join(f.aliases) if f.aliases else "—"
        required = "yes" if f.required else "no"
        rows.append(
            f"| `{f.name}` | {aliases} | `{f.type_repr}` | {required} "
            f"| `{f.default}` | {f.help or '—'} |"
        )
    return rows


def _argument_table(arguments: tuple) -> list[str]:
    rows = ["| Argument | Type | Description |", "|---|---|---|"]
    for a in arguments:
        rows.append(f"| `{a.name}` | `{a.type_repr}` | {a.help or '—'} |")
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_docs_render.py -v
```

Expected: PASS — all render tests pass.

- [ ] **Step 5: Lint and format**

```bash
uv run ruff check src/superintendent/docs/render.py tests/test_docs_render.py
uv run ruff format src/superintendent/docs/render.py tests/test_docs_render.py
```

- [ ] **Step 6: Commit**

```bash
git add src/superintendent/docs/render.py tests/test_docs_render.py
git commit -m "feat: add render_markdown with determinism guarantees"
```

---

## Task 8: `superintendent docs regenerate` subcommand

**Files:**
- Modify: `src/superintendent/cli/main.py`
- Create: `tests/test_docs_command.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_docs_command.py`:

```python
"""Tests for the `superintendent docs regenerate` subcommand."""

import json
from pathlib import Path

from typer.testing import CliRunner

from superintendent.cli.main import app

runner = CliRunner()


class TestDocsRegenerate:
    def test_regenerate_writes_three_files(self, tmp_path, monkeypatch):
        # Point the canonical asset dir at a tempdir for the test.
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        result = runner.invoke(app, ["docs", "regenerate"])
        assert result.exit_code == 0, result.output
        assert (target / "CLI_REFERENCE.md").exists()
        assert (target / "cli-reference.json").exists()

    def test_regenerate_check_does_not_write(self, tmp_path, monkeypatch):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        result = runner.invoke(app, ["docs", "regenerate", "--check"])
        # First run: --check should report drift (the dir is empty)
        assert result.exit_code != 0 or "would" in result.output.lower()
        # No files should have been written
        assert not (target / "CLI_REFERENCE.md").exists()

    def test_regenerated_json_is_valid(self, tmp_path, monkeypatch):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        runner.invoke(app, ["docs", "regenerate"])
        data = json.loads((target / "cli-reference.json").read_text())
        assert "commands" in data
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_docs_command.py -v
```

Expected: FAIL — `docs` subcommand does not exist.

- [ ] **Step 3: Implement the `docs` subgroup**

In `src/superintendent/cli/main.py`, add near the other `typer.Typer` declarations (after the `token_app` block):

```python
docs_app = typer.Typer(name="docs", help="Generate and inspect CLI reference docs.")
app.add_typer(docs_app)
```

Add a helper to resolve the target directory (testable via env var):

```python
def _docs_target_dir() -> Path:
    """Where docs regenerate writes. Override via env for tests."""
    override = os.environ.get("SUPERINTENDENT_DOCS_TARGET")
    if override:
        return Path(override)
    # Canonical location relative to this source file.
    return (
        Path(__file__).parent.parent / "docs" / "assets" / "skills" / "superintendent"
    )
```

Add the regenerate command:

```python
@docs_app.command()
def regenerate(
    check: bool = typer.Option(
        False, "--check", help="Show diff without writing."
    ),
) -> None:
    """Regenerate CLI_REFERENCE.md and cli-reference.json from the live CLI."""
    from superintendent.docs import introspect, render

    target = _docs_target_dir()
    target.mkdir(parents=True, exist_ok=True)

    tree = introspect.walk(app)
    new_md = render.render_markdown(tree)
    new_json = render.render_json(tree)

    md_path = target / "CLI_REFERENCE.md"
    json_path = target / "cli-reference.json"

    if check:
        drift = []
        if not md_path.exists() or md_path.read_text() != new_md:
            drift.append(str(md_path))
        if not json_path.exists() or json_path.read_text() != new_json:
            drift.append(str(json_path))
        if drift:
            typer.echo(f"Drift detected; would update: {', '.join(drift)}")
            raise typer.Exit(code=1)
        typer.echo("Up to date.")
        return

    md_path.write_text(new_md)
    json_path.write_text(new_json)
    typer.echo(f"Wrote {md_path}")
    typer.echo(f"Wrote {json_path}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_docs_command.py -v
```

Expected: PASS — 3 tests pass.

- [ ] **Step 5: Lint, format, typecheck**

```bash
uv run ruff check src/superintendent/cli/main.py tests/test_docs_command.py
uv run ruff format src/superintendent/cli/main.py tests/test_docs_command.py
uv run ty check src/superintendent/cli/main.py
```

- [ ] **Step 6: Commit**

```bash
git add src/superintendent/cli/main.py tests/test_docs_command.py
git commit -m "feat: add 'superintendent docs regenerate' subcommand"
```

---

## Task 9: Hand-write SKILL.md and generate initial reference artifacts

**Files:**
- Create: `src/superintendent/docs/assets/skills/superintendent/SKILL.md`
- Create: `src/superintendent/docs/assets/skills/superintendent/CLI_REFERENCE.md` (generated)
- Create: `src/superintendent/docs/assets/skills/superintendent/cli-reference.json` (generated)

- [ ] **Step 1: Create asset directory**

```bash
mkdir -p src/superintendent/docs/assets/skills/superintendent
```

- [ ] **Step 2: Write SKILL.md**

Create `src/superintendent/docs/assets/skills/superintendent/SKILL.md` with this content:

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

- [ ] **Step 3: Generate the reference artifacts**

```bash
uv run superintendent docs regenerate
```

Expected output:
```
Wrote .../CLI_REFERENCE.md
Wrote .../cli-reference.json
```

- [ ] **Step 4: Sanity-check the generated files**

```bash
head -50 src/superintendent/docs/assets/skills/superintendent/CLI_REFERENCE.md
```

Expected: Header, root flags table (with `--version`), command sections for `cleanup`, `list`, `run`, `status`, plus token subgroup.

```bash
uv run python -c "import json; data = json.load(open('src/superintendent/docs/assets/skills/superintendent/cli-reference.json')); print('commands:', [c['name'] for c in data['commands']]); print('subgroups:', [g['name'] for g in data['subgroups']])"
```

Expected: commands include `cleanup`, `docs`... wait — `docs` is now a subgroup since we added `docs_app`. Verify subgroups include `docs` and `token`.

- [ ] **Step 5: Commit**

```bash
git add src/superintendent/docs/assets/skills/superintendent/
git commit -m "feat: add hand-written SKILL.md and generated CLI reference"
```

---

## Task 10: Drift tests + structural assertions

**Files:**
- Create: `tests/test_cli_reference.py`

- [ ] **Step 1: Write the test file**

Create `tests/test_cli_reference.py`:

```python
"""Drift tests: keep the checked-in CLI reference in sync with the live CLI."""

from pathlib import Path

from superintendent.cli.main import app
from superintendent.docs import introspect, render

ASSET_DIR = (
    Path(__file__).parent.parent
    / "src"
    / "superintendent"
    / "docs"
    / "assets"
    / "skills"
    / "superintendent"
)

STALE_MESSAGE = (
    "Generated CLI reference is out of date.\n"
    "Run: uv run superintendent docs regenerate\n"
    "Then commit the updated files under "
    "src/superintendent/docs/assets/skills/superintendent/."
)


class TestDriftJSON:
    def test_cli_reference_json_is_current(self):
        tree = introspect.walk(app)
        expected = render.render_json(tree)
        actual = (ASSET_DIR / "cli-reference.json").read_text()
        assert actual == expected, STALE_MESSAGE


class TestDriftMarkdown:
    def test_cli_reference_md_is_current(self):
        tree = introspect.walk(app)
        expected = render.render_markdown(tree)
        actual = (ASSET_DIR / "CLI_REFERENCE.md").read_text()
        assert actual == expected, STALE_MESSAGE


class TestStructuralAssertions:
    def test_introspection_covers_all_top_level_commands(self):
        tree = introspect.walk(app)
        names = {c.name for c in tree.commands}
        # install-skill is added in Task 11; that task tightens this assertion.
        assert {"run", "list", "cleanup", "status"} <= names

    def test_introspection_covers_subgroups(self):
        tree = introspect.walk(app)
        names = {g.name for g in tree.subgroups}
        assert "token" in names
        assert "docs" in names

    def test_run_command_has_required_repo_and_task_flags(self):
        tree = introspect.walk(app)
        run = next(c for c in tree.commands if c.name == "run")
        names = {f.name for f in run.flags}
        assert "--repo" in names
        assert "--task" in names
        repo_flag = next(f for f in run.flags if f.name == "--repo")
        assert repo_flag.required is True

    def test_walk_captures_root_callback_flags(self):
        tree = introspect.walk(app)
        names = {f.name for f in tree.flags}
        assert "--version" in names

    def test_token_subgroup_has_expected_commands(self):
        tree = introspect.walk(app)
        token = next(g for g in tree.subgroups if g.name == "token")
        names = {c.name for c in token.commands}
        # Commands defined in main.py: add, update, remove, set-default, remove-default, status
        assert {"add", "update", "remove", "set-default", "remove-default", "status"} <= names
```

The assertion in `test_introspection_covers_all_top_level_commands` deliberately omits `install-skill` here — that command is added in Task 11, which then tightens this assertion to include it.

- [ ] **Step 2: Run tests**

```bash
uv run pytest tests/test_cli_reference.py -v
```

Expected: PASS — drift tests pass against the freshly-generated files; structural assertions pass.

- [ ] **Step 3: Confirm drift detection works**

Manually corrupt the JSON to verify the test fails as expected:

```bash
echo "{}" > src/superintendent/docs/assets/skills/superintendent/cli-reference.json
uv run pytest tests/test_cli_reference.py::TestDriftJSON -v
```

Expected: FAIL with the stale message. Then restore:

```bash
uv run superintendent docs regenerate
uv run pytest tests/test_cli_reference.py -v
```

Expected: PASS again.

- [ ] **Step 4: Commit**

```bash
git add tests/test_cli_reference.py
git commit -m "test: add CLI reference drift and structural assertions"
```

---

## Task 11: `superintendent install-skill` subcommand

**Files:**
- Modify: `src/superintendent/cli/main.py`
- Create: `tests/test_install_skill.py`
- Modify: `tests/test_cli_reference.py` (tighten assertion to include `install-skill`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_install_skill.py`:

```python
"""Tests for the `superintendent install-skill` subcommand."""

from typer.testing import CliRunner

from superintendent.cli.main import app

runner = CliRunner()


class TestInstallSkill:
    def test_install_writes_three_files(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        result = runner.invoke(app, ["install-skill", "--target", str(target)])
        assert result.exit_code == 0, result.output
        assert (target / "SKILL.md").exists()
        assert (target / "CLI_REFERENCE.md").exists()
        assert (target / "cli-reference.json").exists()

    def test_install_skill_md_contains_frontmatter(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        runner.invoke(app, ["install-skill", "--target", str(target)])
        text = (target / "SKILL.md").read_text()
        assert "---" in text
        assert "name: superintendent" in text

    def test_install_errors_when_target_exists_without_force(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("preexisting")
        result = runner.invoke(app, ["install-skill", "--target", str(target)])
        assert result.exit_code != 0
        assert "preexisting" == (target / "SKILL.md").read_text()  # untouched

    def test_install_overwrites_with_force(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("preexisting")
        result = runner.invoke(app, ["install-skill", "--target", str(target), "--force"])
        assert result.exit_code == 0
        assert "preexisting" != (target / "SKILL.md").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/test_install_skill.py -v
```

Expected: FAIL — `install-skill` does not exist.

- [ ] **Step 3: Implement the command**

In `src/superintendent/cli/main.py`, add after the `docs_app` registration:

```python
@app.command("install-skill")
def install_skill(
    target: Path = typer.Option(
        None,
        help="Target directory (defaults to ~/.claude/skills/superintendent).",
    ),
    force: bool = typer.Option(
        False, "--force", help="Overwrite existing files."
    ),
) -> None:
    """Install the superintendent skill to a Claude Code skills directory."""
    from importlib.resources import files

    if target is None:
        target = Path.home() / ".claude" / "skills" / "superintendent"

    skill_dir = files("superintendent.docs") / "assets" / "skills" / "superintendent"
    file_names = ("SKILL.md", "CLI_REFERENCE.md", "cli-reference.json")

    if target.exists() and any((target / n).exists() for n in file_names) and not force:
        typer.echo(
            f"Error: target already contains skill files: {target}\n"
            "Use --force to overwrite.",
            err=True,
        )
        raise typer.Exit(code=1)

    target.mkdir(parents=True, exist_ok=True)
    for name in file_names:
        (target / name).write_text((skill_dir / name).read_text())
        typer.echo(f"Wrote {target / name}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
uv run pytest tests/test_install_skill.py -v
```

Expected: PASS — 4 tests pass.

- [ ] **Step 5: Tighten the structural assertion**

In `tests/test_cli_reference.py`, update `test_introspection_covers_all_top_level_commands`:

```python
    def test_introspection_covers_all_top_level_commands(self):
        tree = introspect.walk(app)
        names = {c.name for c in tree.commands}
        assert {"run", "list", "cleanup", "status", "install-skill"} <= names
```

- [ ] **Step 6: Regenerate reference artifacts (now includes `install-skill`)**

```bash
uv run superintendent docs regenerate
uv run pytest tests/test_cli_reference.py tests/test_install_skill.py -v
```

Expected: PASS.

- [ ] **Step 7: Lint, format, typecheck**

```bash
uv run ruff check src/superintendent/cli/main.py tests/test_install_skill.py
uv run ruff format src/superintendent/cli/main.py tests/test_install_skill.py
uv run ty check src/superintendent/cli/main.py
```

- [ ] **Step 8: Commit**

```bash
git add src/superintendent/cli/main.py tests/test_install_skill.py tests/test_cli_reference.py src/superintendent/docs/assets/skills/superintendent/
git commit -m "feat: add 'superintendent install-skill' subcommand"
```

---

## Task 12: Plugin manifest + `.claude/skills` symlink + version-match test

**Files:**
- Create: `.claude-plugin/plugin.json`
- Create: `.claude/skills/superintendent` (symlink)
- Create: `tests/test_plugin_manifest.py`

- [ ] **Step 1: Create the plugin manifest**

```bash
mkdir -p .claude-plugin
```

Create `.claude-plugin/plugin.json`:

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
  "keywords": [
    "agents",
    "claude",
    "docker",
    "worktree",
    "automation"
  ],
  "skills": "./src/superintendent/docs/assets/skills/"
}
```

Set `version` to `0.3.0` to match the current `pyproject.toml`; Task 13 bumps both together.

- [ ] **Step 2: Create the in-repo skill symlink**

```bash
mkdir -p .claude/skills
cd .claude/skills
ln -s ../../src/superintendent/docs/assets/skills/superintendent superintendent
cd ../..
```

Verify:

```bash
ls -la .claude/skills/superintendent
```

Expected: `lrwxr-xr-x ... superintendent -> ../../src/superintendent/docs/assets/skills/superintendent`

```bash
ls .claude/skills/superintendent/
```

Expected: shows `SKILL.md`, `CLI_REFERENCE.md`, `cli-reference.json` (resolved through symlink).

```bash
git ls-files -s .claude/skills/superintendent
```

(After `git add`) Expected: mode `120000` indicating a symlink, not `100644`.

- [ ] **Step 3: Write the version-match test**

Create `tests/test_plugin_manifest.py`:

```python
"""Verify .claude-plugin/plugin.json stays in sync with the package version."""

import json
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent


class TestPluginManifestVersion:
    def test_plugin_version_matches_pyproject(self):
        plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
        with (REPO_ROOT / "pyproject.toml").open("rb") as f:
            pyproject = tomllib.load(f)
        assert plugin["version"] == pyproject["project"]["version"], (
            f"Plugin version {plugin['version']} does not match "
            f"pyproject.toml version {pyproject['project']['version']}. "
            "Bump both together."
        )

    def test_plugin_skills_path_exists(self):
        plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
        skills_path = REPO_ROOT / plugin["skills"].lstrip("./") / "superintendent"
        assert (skills_path / "SKILL.md").exists()
```

- [ ] **Step 4: Run the version-match test**

```bash
uv run pytest tests/test_plugin_manifest.py -v
```

Expected: PASS — both `plugin.json` and `pyproject.toml` say `0.3.0`, so the test confirms they match. (Task 13 bumps both to `0.4.0` together; the test stays green.)

If you want to verify the test actually catches drift, temporarily change `plugin.json` to `0.99.0`, re-run, see it fail, then restore to `0.3.0`. Optional sanity-check.

- [ ] **Step 5: Add a smoke test for the in-repo symlink**

Append to `tests/test_plugin_manifest.py`:

```python
class TestInRepoSkillSymlink:
    def test_claude_skills_symlink_points_at_canonical_dir(self):
        link = REPO_ROOT / ".claude" / "skills" / "superintendent"
        assert link.is_symlink(), (
            "Expected .claude/skills/superintendent to be a symlink. "
            "Re-run: ln -s ../../src/superintendent/docs/assets/skills/superintendent "
            ".claude/skills/superintendent"
        )
        assert link.resolve() == (
            REPO_ROOT
            / "src"
            / "superintendent"
            / "docs"
            / "assets"
            / "skills"
            / "superintendent"
        ).resolve()
```

- [ ] **Step 6: Run all tests**

```bash
uv run pytest tests/test_plugin_manifest.py -v
```

Expected: 3 tests pass.

- [ ] **Step 7: Lint and format**

```bash
uv run ruff check tests/test_plugin_manifest.py
uv run ruff format tests/test_plugin_manifest.py
```

- [ ] **Step 8: Commit**

```bash
git add .claude-plugin/plugin.json .claude/skills/superintendent tests/test_plugin_manifest.py
git commit -m "feat: add Claude Code plugin manifest and in-repo skill symlink"
```

---

## Task 13: Version bump, README updates, and final verification

**Files:**
- Modify: `pyproject.toml`
- Modify: `src/superintendent/__init__.py`
- Modify: `.claude-plugin/plugin.json`
- Modify: `README.md`

- [ ] **Step 1: Bump versions to 0.4.0**

Edit `pyproject.toml`: change `version = "0.3.0"` → `version = "0.4.0"`.

Edit `src/superintendent/__init__.py`: change `__version__ = "0.3.0"` → `__version__ = "0.4.0"`.

Edit `.claude-plugin/plugin.json`: change `"version": "0.3.0"` → `"version": "0.4.0"`.

- [ ] **Step 2: Verify version sync test passes**

```bash
uv run pytest tests/test_plugin_manifest.py -v
```

Expected: PASS.

- [ ] **Step 3: Add README sections**

Edit `README.md`. After the existing `## Installation` section, add a new section:

```markdown
## Claude Code Skill

Superintendent ships with a Claude Code skill that gives agents an always-current
reference for the CLI. Three install paths:

### In-repo (automatic)

When working inside the superintendent repo, Claude Code auto-loads the skill from
`.claude/skills/superintendent/`. No setup needed.

### Global install (after `uv tool install`)

```bash
superintendent install-skill
```

Writes `SKILL.md`, `CLI_REFERENCE.md`, and `cli-reference.json` to
`~/.claude/skills/superintendent/`. Re-run after `uv tool upgrade superintendent` to
refresh the reference. Use `--target PATH` to install elsewhere; use `--force` to
overwrite an existing install.

### As a Claude Code plugin

This repo ships a `.claude-plugin/plugin.json` so it can be installed directly as a
plugin via `/plugin install` or by adding the repo as a marketplace source.

### Regenerating the reference (contributors)

The CLI reference is auto-generated from the typer app. After changing any CLI
command or flag:

```bash
uv run superintendent docs regenerate
```

Then commit the updated files under
`src/superintendent/docs/assets/skills/superintendent/`. CI catches drift via
`tests/test_cli_reference.py`.
```

- [ ] **Step 4: Run the full CI checklist**

```bash
uv run pytest                               # All tests pass
uv run ruff check src/ tests/               # Lint clean
uv run ruff format --check src/ tests/      # Format clean
uv run ty check src/ --exclude 'tests/'     # Type-check clean
```

If any fails, fix and re-run before committing.

- [ ] **Step 5: Verify the install-skill command end-to-end (manual)**

```bash
# Use a tempdir to avoid clobbering anything in your real ~/.claude
TMPDIR=$(mktemp -d)
uv run superintendent install-skill --target "$TMPDIR/skills/superintendent"
ls "$TMPDIR/skills/superintendent/"
head -5 "$TMPDIR/skills/superintendent/SKILL.md"
rm -rf "$TMPDIR"
```

Expected: Three files present; SKILL.md starts with `---` frontmatter and `name: superintendent`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml src/superintendent/__init__.py .claude-plugin/plugin.json README.md
git commit -m "feat: bump version to 0.4.0 and document skill install paths"
```

- [ ] **Step 7: Final sanity check**

```bash
git log --oneline | head -15
uv run pytest -v --tb=short 2>&1 | tail -20
```

Expected: ~13 new commits since branch base; all tests green.

---

## Done

The skill is now:
- Auto-loaded for agents working in the superintendent repo (via `.claude/skills/` symlink)
- Installable globally via `superintendent install-skill`
- Installable as a Claude Code plugin via `.claude-plugin/plugin.json`
- Kept current by `tests/test_cli_reference.py` failing on drift
- Refreshable via `uv run superintendent docs regenerate`

When adding a new command (e.g., a future `superintendent respond`):
1. Implement it in `cli/main.py` with TDD as usual
2. `uv run superintendent docs regenerate`
3. Commit code + regenerated reference together

Nothing else.
