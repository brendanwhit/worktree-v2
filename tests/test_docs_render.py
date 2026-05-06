"""Tests for markdown and JSON renderers."""

import json

from superintendent.docs.introspect import walk
from superintendent.docs.model import (
    CommandGroup,
    CommandSpec,
    FlagSpec,
)
from superintendent.docs.render import render_json, render_markdown


def _sample_tree() -> CommandGroup:
    flag = FlagSpec(
        name="--repo",
        aliases=(),
        type_repr="str",
        required=True,
        default="None",
        help="Repo path.",
        is_bool=False,
    )
    cmd = CommandSpec(name="run", help="Run.", arguments=(), flags=(flag,))
    return CommandGroup(
        name="superintendent",
        help="Top-level help.",
        flags=(),
        commands=(cmd,),
        subgroups=(),
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
        out = render_markdown(_sample_tree())
        assert "Generated at" not in out
        assert "Generated on" not in out

    def test_render_markdown_against_real_app(self):
        from superintendent.cli.main import app

        out = render_markdown(walk(app))
        assert "## `superintendent run`" in out
        assert "## `superintendent token add`" in out  # nested subgroup
        assert "--repo" in out
