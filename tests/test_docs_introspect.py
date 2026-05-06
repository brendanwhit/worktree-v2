"""Tests for typer-app introspection."""

import enum

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


# --- Task 3: arguments, enums, optional and prompt flags ---


class _Mode(enum.StrEnum):
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
        def run(
            branch: str | None = typer.Option(None, help="Branch."),
        ) -> None:
            pass

        tree = walk(app)
        flag = next(f for f in tree.commands[0].flags if f.name == "--branch")
        assert flag.default == "None"
        assert flag.required is False

    def test_prompt_flag_default_is_sentinel(self):
        app = typer.Typer()

        @app.command()
        def login(
            token: str = typer.Option(..., prompt=True, hide_input=True),
        ) -> None:
            pass

        tree = walk(app)
        flag = next(f for f in tree.commands[0].flags if f.name == "--token")
        assert flag.default == "<prompt>"


# --- Task 4: nested subgroups ---


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


# --- Task 5: root callback flags ---


class TestWalkRootCallback:
    def test_root_callback_version_flag_surfaces_on_group(self):
        app = typer.Typer()

        @app.callback()
        def main(
            version: bool = typer.Option(
                False,
                "--version",
                "-V",
                help="Show version and exit.",
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
