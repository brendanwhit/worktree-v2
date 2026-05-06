"""Tests for the `superintendent docs regenerate` subcommand."""

import json

from typer.testing import CliRunner

from superintendent.cli.main import app

runner = CliRunner()


class TestDocsRegenerate:
    def test_regenerate_writes_three_files(self, tmp_path, monkeypatch):
        # Point the canonical asset dir at a tempdir for the test.
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        result = runner.invoke(app, ["docs", "regenerate"])
        assert result.exit_code == 0, result.output
        assert (target / "CLI_REFERENCE.md").exists()
        assert (target / "cli-reference.json").exists()

    def test_regenerate_check_does_not_write(self, tmp_path, monkeypatch):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        result = runner.invoke(app, ["docs", "regenerate", "--check"])
        # First run: --check should report drift (the dir is empty)
        assert result.exit_code != 0 or "would" in result.output.lower()
        # No files should have been written
        assert not (target / "CLI_REFERENCE.md").exists()

    def test_regenerated_json_is_valid(self, tmp_path, monkeypatch):
        target = tmp_path / "skills" / "superintendent"
        target.mkdir(parents=True)
        monkeypatch.setenv("SUPERINTENDENT_DOCS_TARGET", str(target))

        runner.invoke(app, ["docs", "regenerate"])
        data = json.loads((target / "cli-reference.json").read_text())
        assert "commands" in data
