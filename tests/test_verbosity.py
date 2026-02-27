"""Tests for --verbose/--quiet flags and Verbosity enum."""

from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from superintendent.cli.main import app, resolve_verbosity
from superintendent.orchestrator.models import Verbosity

runner = CliRunner()


class TestVerbosityEnum:
    def test_values(self) -> None:
        assert Verbosity.quiet == "quiet"
        assert Verbosity.normal == "normal"
        assert Verbosity.verbose == "verbose"

    def test_all_values(self) -> None:
        assert set(Verbosity) == {Verbosity.quiet, Verbosity.normal, Verbosity.verbose}


class TestResolveVerbosity:
    def test_default_is_normal(self) -> None:
        assert resolve_verbosity(verbose=False, quiet=False) == Verbosity.normal

    def test_verbose_flag(self) -> None:
        assert resolve_verbosity(verbose=True, quiet=False) == Verbosity.verbose

    def test_quiet_flag(self) -> None:
        assert resolve_verbosity(verbose=False, quiet=True) == Verbosity.quiet

    def test_mutually_exclusive(self) -> None:
        with pytest.raises(typer.BadParameter, match="mutually exclusive"):
            resolve_verbosity(verbose=True, quiet=True)


class TestVerbosityFlags:
    def _mock_run_success(self):
        """Set up mocks for a successful run command."""
        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        return mock_planner, mock_executor

    def test_verbose_flag_accepted(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner, mock_executor = self._mock_run_success()
            mock_planner_cls.return_value = mock_planner
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--verbose",
                ],
            )
            assert result.exit_code == 0

    def test_verbose_short_flag_accepted(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner, mock_executor = self._mock_run_success()
            mock_planner_cls.return_value = mock_planner
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "-v",
                ],
            )
            assert result.exit_code == 0

    def test_quiet_flag_accepted(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner, mock_executor = self._mock_run_success()
            mock_planner_cls.return_value = mock_planner
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--quiet",
                ],
            )
            assert result.exit_code == 0

    def test_quiet_short_flag_accepted(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner, mock_executor = self._mock_run_success()
            mock_planner_cls.return_value = mock_planner
            mock_executor_cls.return_value = mock_executor

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "-q",
                ],
            )
            assert result.exit_code == 0

    def test_verbose_and_quiet_together_fails(self) -> None:
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/repo",
                "--task",
                "fix bug",
                "--verbose",
                "--quiet",
            ],
        )
        assert result.exit_code != 0

    def test_verbosity_passed_to_context(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
            patch("superintendent.cli.main.ExecutionContext") as mock_ctx_cls,
            patch("superintendent.cli.main.RealStepHandler"),
        ):
            mock_planner = MagicMock()
            mock_plan = MagicMock()
            mock_planner.create_plan.return_value = mock_plan
            mock_planner_cls.return_value = mock_planner

            mock_executor = MagicMock()
            mock_result = MagicMock()
            mock_result.state.name = "AGENT_RUNNING"
            mock_result.failed_step = None
            mock_executor.run.return_value = mock_result
            mock_executor_cls.return_value = mock_executor

            runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--verbose",
                ],
            )
            mock_ctx_cls.assert_called_once()
            call_kwargs = mock_ctx_cls.call_args
            assert call_kwargs.kwargs.get("verbosity") == Verbosity.verbose
