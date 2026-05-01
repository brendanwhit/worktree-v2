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
        assert {"run", "list", "cleanup", "status", "install-skill"} <= names

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
        assert {
            "add",
            "update",
            "remove",
            "set-default",
            "remove-default",
            "status",
        } <= names
