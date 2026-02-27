"""Tests for the --explain flag on the run command."""

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from superintendent.cli.main import app, explain_plan
from superintendent.orchestrator.models import Mode, Target

runner = CliRunner()


class TestExplainFlag:
    def test_explain_shows_output_without_executing(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "pyproject.toml").touch()

        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    str(repo),
                    "--task",
                    "fix bug",
                    "--explain",
                ],
            )
            assert result.exit_code == 0
            # Should not have created planner or executor
            mock_planner_cls.assert_not_called()
            mock_executor_cls.assert_not_called()

    def test_explain_includes_task_and_repo(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()

        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                str(repo),
                "--task",
                "implement feature",
                "--explain",
            ],
        )
        assert result.exit_code == 0
        assert "implement feature" in result.output
        assert str(repo) in result.output

    def test_explain_shows_strategy_decision(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()

        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                str(repo),
                "--task",
                "fix bug",
                "--explain",
            ],
        )
        assert result.exit_code == 0
        assert "Decision:" in result.output
        assert "autonomous" in result.output
        assert "sandbox" in result.output

    def test_explain_shows_repo_analysis(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / "Dockerfile").touch()
        (repo / "pyproject.toml").touch()

        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                str(repo),
                "--task",
                "fix bug",
                "--explain",
            ],
        )
        assert result.exit_code == 0
        assert "has_dockerfile: yes" in result.output
        assert "languages: python" in result.output

    def test_explain_with_non_dir_repo(self) -> None:
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "https://github.com/org/repo",
                "--task",
                "fix bug",
                "--explain",
            ],
        )
        assert result.exit_code == 0
        assert "Decision:" in result.output


class TestExplainPlanFunction:
    def test_returns_string(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        output = explain_plan(str(repo), "fix bug", Mode.autonomous, Target.sandbox)
        assert isinstance(output, str)
        assert len(output) > 0

    def test_includes_mode_and_target(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        output = explain_plan(str(repo), "fix bug", Mode.interactive, Target.local)
        assert "interactive" in output
        assert "local" in output

    def test_includes_reasoning(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        repo.mkdir()
        output = explain_plan(str(repo), "fix bug", Mode.autonomous, Target.sandbox)
        assert "Reasoning:" in output or "Mode:" in output
