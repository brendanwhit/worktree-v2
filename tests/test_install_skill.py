"""Tests for the `superintendent install-skill` subcommand."""

from typer.testing import CliRunner

from superintendent.cli.main import app

runner = CliRunner()


class TestInstallSkill:
    def test_install_writes_three_files(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        result = runner.invoke(app, ["install-skill", "--target", str(target)])
        assert result.exit_code == 0, result.output
        assert (target / "SKILL.md").exists()
        assert (target / "CLI_REFERENCE.md").exists()
        assert (target / "cli-reference.json").exists()

    def test_install_skill_md_contains_frontmatter(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        runner.invoke(app, ["install-skill", "--target", str(target)])
        text = (target / "SKILL.md").read_text()
        assert "---" in text
        assert "name: superintendent" in text

    def test_install_errors_when_target_exists_without_force(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("preexisting")
        result = runner.invoke(app, ["install-skill", "--target", str(target)])
        assert result.exit_code != 0
        assert (target / "SKILL.md").read_text() == "preexisting"  # untouched

    def test_install_overwrites_with_force(self, tmp_path):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        (target / "SKILL.md").write_text("preexisting")
        result = runner.invoke(
            app, ["install-skill", "--target", str(target), "--force"]
        )
        assert result.exit_code == 0
        assert (target / "SKILL.md").read_text() != "preexisting"
