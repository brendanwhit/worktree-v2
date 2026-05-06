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
