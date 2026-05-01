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
            name="--repo",
            aliases=(),
            type_repr="str",
            required=True,
            default="None",
            help="",
            is_bool=False,
        )
        cmd = CommandSpec(
            name="run", help="Spawn an agent.", arguments=(), flags=(flag,)
        )
        assert cmd.name == "run"
        assert len(cmd.flags) == 1


class TestCommandGroup:
    def test_create_empty_group(self):
        group = CommandGroup(
            name="superintendent",
            help="Agent orchestration CLI.",
            flags=(),
            commands=(),
            subgroups=(),
        )
        assert group.commands == ()

    def test_group_with_root_flag(self):
        version = FlagSpec(
            name="--version",
            aliases=("-V",),
            type_repr="bool",
            required=False,
            default="False",
            help="Show version and exit.",
            is_bool=True,
        )
        group = CommandGroup(
            name="superintendent",
            help="",
            flags=(version,),
            commands=(),
            subgroups=(),
        )
        assert group.flags[0].name == "--version"

    def test_group_is_hashable(self):
        group = CommandGroup(name="x", help="", flags=(), commands=(), subgroups=())
        assert hash(group) is not None
