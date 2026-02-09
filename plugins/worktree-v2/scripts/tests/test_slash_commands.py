"""Tests for slash command .md files."""

from pathlib import Path

import pytest

# The commands/ directory relative to the plugin root
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent
COMMANDS_DIR = PLUGIN_ROOT / "commands"

EXPECTED_COMMANDS = ["ralph", "spawn", "list", "resume", "cleanup"]


class TestCommandFilesExist:
    """Verify all expected command .md files exist."""

    @pytest.mark.parametrize("cmd_name", EXPECTED_COMMANDS)
    def test_command_file_exists(self, cmd_name: str) -> None:
        cmd_file = COMMANDS_DIR / f"{cmd_name}.md"
        assert cmd_file.exists(), f"Missing command file: {cmd_file}"

    @pytest.mark.parametrize("cmd_name", EXPECTED_COMMANDS)
    def test_command_file_is_not_empty(self, cmd_name: str) -> None:
        cmd_file = COMMANDS_DIR / f"{cmd_name}.md"
        content = cmd_file.read_text()
        assert len(content.strip()) > 0, f"Command file is empty: {cmd_file}"


class TestCommandFileContent:
    """Verify command files have proper descriptions and invoke CLIs."""

    def test_ralph_references_cli(self) -> None:
        content = (COMMANDS_DIR / "ralph.md").read_text()
        assert "ralph" in content.lower()
        assert "--repo" in content
        assert "--task" in content

    def test_spawn_references_cli(self) -> None:
        content = (COMMANDS_DIR / "spawn.md").read_text()
        assert "spawn" in content.lower()
        assert "--repo" in content
        assert "--task" in content

    def test_spawn_mentions_local(self) -> None:
        """spawn is the local (no Docker) variant."""
        content = (COMMANDS_DIR / "spawn.md").read_text()
        assert "local" in content.lower() or "no docker" in content.lower()

    def test_list_references_registry(self) -> None:
        content = (COMMANDS_DIR / "list.md").read_text()
        assert "list" in content.lower() or "worktree" in content.lower()

    def test_resume_references_reattach(self) -> None:
        content = (COMMANDS_DIR / "resume.md").read_text()
        assert "resume" in content.lower() or "reattach" in content.lower()

    def test_cleanup_references_removal(self) -> None:
        content = (COMMANDS_DIR / "cleanup.md").read_text()
        assert (
            "cleanup" in content.lower()
            or "clean" in content.lower()
            or "remove" in content.lower()
        )

    @pytest.mark.parametrize("cmd_name", EXPECTED_COMMANDS)
    def test_command_uses_arguments_placeholder(self, cmd_name: str) -> None:
        """Each command should reference $ARGUMENTS for user input."""
        content = (COMMANDS_DIR / f"{cmd_name}.md").read_text()
        assert "$ARGUMENTS" in content, (
            f"{cmd_name}.md should use $ARGUMENTS placeholder"
        )
