"""Tests for slash command .md files."""

from pathlib import Path

import pytest

# The commands/ directory at the project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
COMMANDS_DIR = PROJECT_ROOT / "commands"

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
    """Verify command files have proper descriptions and invoke the CLI."""

    def test_ralph_references_cli(self) -> None:
        content = (COMMANDS_DIR / "ralph.md").read_text()
        assert "superintendent" in content or "sup" in content
        assert "autonomous" in content
        assert "sandbox" in content
        assert "--repo" in content
        assert "--task" in content

    def test_spawn_references_cli(self) -> None:
        content = (COMMANDS_DIR / "spawn.md").read_text()
        assert "superintendent" in content or "sup" in content
        assert "interactive" in content
        assert "local" in content.lower()
        assert "--repo" in content
        assert "--task" in content

    def test_list_references_cli(self) -> None:
        content = (COMMANDS_DIR / "list.md").read_text()
        assert "superintendent" in content or "sup" in content
        assert "list" in content.lower()

    def test_resume_references_cli(self) -> None:
        content = (COMMANDS_DIR / "resume.md").read_text()
        assert "superintendent" in content or "sup" in content
        assert "resume" in content.lower()

    def test_cleanup_references_cli(self) -> None:
        content = (COMMANDS_DIR / "cleanup.md").read_text()
        assert "superintendent" in content or "sup" in content
        assert "cleanup" in content.lower()

    @pytest.mark.parametrize("cmd_name", EXPECTED_COMMANDS)
    def test_command_uses_arguments_placeholder(self, cmd_name: str) -> None:
        """Each command should reference $ARGUMENTS for user input."""
        content = (COMMANDS_DIR / f"{cmd_name}.md").read_text()
        assert "$ARGUMENTS" in content, (
            f"{cmd_name}.md should use $ARGUMENTS placeholder"
        )
