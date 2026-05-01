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

    When a Typer app has a single command and no subgroups, click returns a
    plain Command instead of a Group. We wrap it in a synthetic CommandGroup.
    """
    click_obj = typer.main.get_command(app)
    name = app.info.name or click_obj.name or ""
    if isinstance(click_obj, click.Group):
        return _walk_group(click_obj, name=name)
    # Single-command app: wrap the Command in a group
    cmd = _walk_command(click_obj, name=click_obj.name or name)
    return CommandGroup(
        name=name,
        help=(click_obj.help or "").strip(),
        flags=(),
        commands=(cmd,),
        subgroups=(),
    )


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
    choices: tuple[str, ...] | None = None
    if isinstance(param.type, click.Choice):
        choices = tuple(str(c) for c in param.type.choices)
    return ArgumentSpec(
        name=param.name or "",
        type_repr=_type_repr(param.type),
        help=(getattr(param, "help", "") or "").strip(),
        choices=choices,
    )


def _type_repr(param_type: click.ParamType) -> str:
    if isinstance(param_type, click.Choice):
        return f"enum[{'|'.join(str(c) for c in param_type.choices)}]"
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
