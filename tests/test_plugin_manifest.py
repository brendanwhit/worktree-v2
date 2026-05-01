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


class TestInRepoSkillSymlink:
    def test_claude_skills_symlink_points_at_canonical_dir(self):
        link = REPO_ROOT / ".claude" / "skills" / "superintendent"
        assert link.is_symlink(), (
            "Expected .claude/skills/superintendent to be a symlink. "
            "Re-run: ln -s ../../src/superintendent/docs/assets/skills/superintendent "
            ".claude/skills/superintendent"
        )
        assert (
            link.resolve()
            == (
                REPO_ROOT
                / "src"
                / "superintendent"
                / "docs"
                / "assets"
                / "skills"
                / "superintendent"
            ).resolve()
        )
