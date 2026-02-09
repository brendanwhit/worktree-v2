"""Tests for spawn.py CLI entry point (simpler, no Docker)."""

from unittest.mock import MagicMock, patch

import pytest

from cli.spawn import build_parser, main, run


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_exists(self) -> None:
        parser = build_parser()
        assert parser is not None

    def test_required_repo_flag(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_required_task_flag(self) -> None:
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--repo", "/tmp/repo"])

    def test_minimal_args(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])
        assert args.repo == "/tmp/repo"
        assert args.task == "fix bug"

    def test_branch_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--repo", "/tmp/repo", "--task", "fix bug", "--branch", "my-branch"]
        )
        assert args.branch == "my-branch"

    def test_branch_default_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])
        assert args.branch is None

    def test_context_file_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "/tmp/repo",
                "--task",
                "fix bug",
                "--context-file",
                "context.md",
            ]
        )
        assert args.context_file == "context.md"

    def test_context_file_default_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])
        assert args.context_file is None

    def test_dry_run_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--repo", "/tmp/repo", "--task", "fix bug", "--dry-run"]
        )
        assert args.dry_run is True

    def test_dry_run_default_is_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])
        assert args.dry_run is False

    def test_no_sandbox_name_flag(self) -> None:
        """spawn.py should NOT have a --sandbox-name flag (no Docker)."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--sandbox-name",
                    "foo",
                ]
            )

    def test_no_template_dockerfile_flag(self) -> None:
        """spawn.py should NOT have a --template-dockerfile flag (no Docker)."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(
                [
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--template-dockerfile",
                    "Dockerfile",
                ]
            )

    def test_no_force_flag(self) -> None:
        """spawn.py should NOT have a --force flag (no sandbox to recreate)."""
        parser = build_parser()
        with pytest.raises(SystemExit):
            parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug", "--force"])

    def test_all_flags_together(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            [
                "--repo",
                "https://github.com/user/repo",
                "--task",
                "implement feature",
                "--branch",
                "feature-branch",
                "--context-file",
                "ctx.md",
                "--dry-run",
            ]
        )
        assert args.repo == "https://github.com/user/repo"
        assert args.task == "implement feature"
        assert args.branch == "feature-branch"
        assert args.context_file == "ctx.md"
        assert args.dry_run is True


class TestRun:
    """Test the run() function."""

    def test_run_uses_local_mode(self) -> None:
        """spawn.py should always use local mode (no Docker)."""
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        run(args, planner=mock_planner, executor=mock_executor)

        planner_input = mock_planner.create_plan.call_args[0][0]
        assert planner_input.mode == "local"

    def test_run_passes_repo_and_task(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        run(args, planner=mock_planner, executor=mock_executor)

        planner_input = mock_planner.create_plan.call_args[0][0]
        assert planner_input.repo == "/tmp/repo"
        assert planner_input.task == "fix bug"

    def test_run_passes_branch_to_planner(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--repo", "/tmp/repo", "--task", "fix bug", "--branch", "my-branch"]
        )

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        run(args, planner=mock_planner, executor=mock_executor)

        planner_input = mock_planner.create_plan.call_args[0][0]
        assert planner_input.branch == "my-branch"

    def test_run_passes_context_file_to_planner(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--repo", "/tmp/repo", "--task", "fix", "--context-file", "ctx.md"]
        )

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        run(args, planner=mock_planner, executor=mock_executor)

        planner_input = mock_planner.create_plan.call_args[0][0]
        assert planner_input.context_file == "ctx.md"

    def test_run_executes_plan(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        run(args, planner=mock_planner, executor=mock_executor)
        mock_executor.run.assert_called_once_with(mock_plan)

    def test_run_dry_run_skips_execution(self) -> None:
        parser = build_parser()
        args = parser.parse_args(
            ["--repo", "/tmp/repo", "--task", "fix bug", "--dry-run"]
        )

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()

        result = run(args, planner=mock_planner, executor=mock_executor)
        mock_executor.run.assert_not_called()
        assert result is mock_plan

    def test_run_returns_execution_result(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo", "/tmp/repo", "--task", "fix bug"])

        mock_planner = MagicMock()
        mock_plan = MagicMock()
        mock_planner.create_plan.return_value = mock_plan

        mock_executor = MagicMock()
        mock_result = MagicMock()
        mock_result.state.name = "AGENT_RUNNING"
        mock_result.failed_step = None
        mock_executor.run.return_value = mock_result

        result = run(args, planner=mock_planner, executor=mock_executor)
        assert result is mock_result


class TestMain:
    """Test the main() entry point function."""

    def test_main_returns_zero_on_success(self) -> None:
        with patch("cli.spawn.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = MagicMock(
                repo="/tmp/repo",
                task="fix bug",
                branch=None,
                context_file=None,
                dry_run=False,
            )
            with patch("cli.spawn.run") as mock_run:
                mock_result = MagicMock()
                mock_result.state.name = "AGENT_RUNNING"
                mock_result.failed_step = None
                mock_run.return_value = mock_result
                exit_code = main()
                assert exit_code == 0

    def test_main_returns_one_on_failure(self) -> None:
        with patch("cli.spawn.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = MagicMock(
                repo="/tmp/repo",
                task="fix bug",
                branch=None,
                context_file=None,
                dry_run=False,
            )
            with patch("cli.spawn.run") as mock_run:
                mock_result = MagicMock()
                mock_result.state.name = "FAILED"
                mock_result.failed_step = "validate_repo"
                mock_result.error = "Repo not found"
                mock_run.return_value = mock_result
                exit_code = main()
                assert exit_code == 1

    def test_main_returns_zero_on_dry_run(self) -> None:
        with patch("cli.spawn.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = MagicMock(
                repo="/tmp/repo",
                task="fix bug",
                branch=None,
                context_file=None,
                dry_run=True,
            )
            with patch("cli.spawn.run") as mock_run:
                mock_plan = MagicMock()
                mock_run.return_value = mock_plan
                exit_code = main()
                assert exit_code == 0
