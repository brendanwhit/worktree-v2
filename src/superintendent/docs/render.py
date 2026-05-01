"""Render a CommandGroup tree as markdown or JSON."""

import json
from dataclasses import asdict

from superintendent.docs.model import CommandGroup


def render_json(tree: CommandGroup) -> str:
    """Render the tree as deterministic JSON.

    Sorted keys, two-space indent, no trailing whitespace, terminal newline.
    """
    return json.dumps(asdict(tree), indent=2, sort_keys=True) + "\n"


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
    rows = [
        "| Flag | Aliases | Type | Required | Default | Description |",
        "|---|---|---|---|---|---|",
    ]
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
