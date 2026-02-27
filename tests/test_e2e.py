"""End-to-end tests: invoke the CLI entry point and verify output.

These tests exercise the full CLI -> Planner -> output path using
dry-run mode so no real backends are called. Unlike test_cli.py
(which mocks Planner/Executor), these let the real Planner create
plans and verify the actual JSON output structure.
"""

import json

from typer.testing import CliRunner

from superintendent.cli.main import app

runner = CliRunner()


class TestE2EDryRunSandbox:
    """E2E: CLI dry-run for sandbox target produces correct plan output."""

    def test_dry_run_outputs_valid_json_plan(self) -> None:
        """Dry-run mode outputs a JSON plan that can be parsed."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "implement feature",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
        assert "Dry Run" in result.output

        # Extract JSON from output (after the header line)
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        assert "steps" in plan_data
        assert "metadata" in plan_data

    def test_dry_run_sandbox_plan_has_six_steps(self) -> None:
        """Dry-run sandbox plan includes all 6 steps."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        assert len(plan_data["steps"]) == 6
        actions = [s["action"] for s in plan_data["steps"]]
        assert actions == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        ]

    def test_dry_run_sandbox_metadata_correct(self) -> None:
        """Dry-run plan metadata reflects the CLI arguments."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        metadata = plan_data["metadata"]
        assert metadata["repo"] == "/tmp/test-repo"
        assert metadata["task"] == "fix bug"
        assert metadata["mode"] == "autonomous"
        assert metadata["target"] == "sandbox"

    def test_dry_run_sandbox_step_dependencies(self) -> None:
        """Each step depends on its predecessor in the linear chain."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        steps = plan_data["steps"]
        # First step has no deps
        assert steps[0]["depends_on"] == []
        # Each subsequent step depends on the previous
        for i in range(1, len(steps)):
            assert steps[i - 1]["id"] in steps[i]["depends_on"]

    def test_dry_run_sandbox_custom_flags(self) -> None:
        """Custom branch, sandbox name, and context file appear in plan."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--branch",
                "my-branch",
                "--sandbox-name",
                "my-sandbox",
                "--context-file",
                "context.md",
                "--force",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        metadata = plan_data["metadata"]
        assert metadata["branch"] == "my-branch"
        assert metadata["sandbox_name"] == "my-sandbox"
        assert metadata["context_file"] == "context.md"

        # force flag should be in prepare_sandbox step params
        sandbox_step = next(
            s for s in plan_data["steps"] if s["action"] == "prepare_sandbox"
        )
        assert sandbox_step["params"]["force"] is True


class TestE2EDryRunLocal:
    """E2E: CLI dry-run for local target produces correct plan output."""

    def test_dry_run_local_plan_has_four_steps(self) -> None:
        """Dry-run local plan includes only 4 steps (no sandbox/auth)."""
        result = runner.invoke(
            app,
            [
                "run",
                "interactive",
                "local",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        assert len(plan_data["steps"]) == 4
        actions = [s["action"] for s in plan_data["steps"]]
        assert actions == [
            "validate_repo",
            "create_worktree",
            "initialize_state",
            "start_agent",
        ]

    def test_dry_run_local_has_no_sandbox_steps(self) -> None:
        """Local mode plan does not include prepare_sandbox or authenticate."""
        result = runner.invoke(
            app,
            [
                "run",
                "interactive",
                "local",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        actions = [s["action"] for s in plan_data["steps"]]
        assert "prepare_sandbox" not in actions
        assert "authenticate" not in actions

    def test_dry_run_local_start_agent_has_no_sandbox_name(self) -> None:
        """In local mode, start_agent step has no sandbox_name param."""
        result = runner.invoke(
            app,
            [
                "run",
                "interactive",
                "local",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        agent_step = next(s for s in plan_data["steps"] if s["action"] == "start_agent")
        assert "sandbox_name" not in agent_step["params"]


class TestE2EDryRunContainer:
    """E2E: CLI dry-run for container target produces correct plan."""

    def test_dry_run_container_plan_has_six_steps(self) -> None:
        """Container mode produces same 6-step structure as sandbox."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "container",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        assert len(plan_data["steps"]) == 6


class TestE2EURLRepo:
    """E2E: CLI dry-run with URL repos produces correct plan."""

    def test_dry_run_url_repo_sets_is_url_true(self) -> None:
        """When repo is a URL, validate_repo step has is_url=True."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "https://github.com/user/my-repo.git",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        validate_step = plan_data["steps"][0]
        assert validate_step["params"]["is_url"] is True

    def test_dry_run_url_repo_extracts_repo_name(self) -> None:
        """Repo name is extracted from URL for metadata and naming."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "https://github.com/user/my-repo.git",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        assert plan_data["metadata"]["repo_name"] == "my-repo"
        assert plan_data["metadata"]["sandbox_name"] == "claude-my-repo"
        assert plan_data["metadata"]["branch"] == "agent/my-repo"

    def test_dry_run_local_path_sets_is_url_false(self) -> None:
        """When repo is a local path, validate_repo step has is_url=False."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/my-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        lines = result.output.strip().split("\n")
        json_text = "\n".join(lines[1:])
        plan_data = json.loads(json_text)

        validate_step = plan_data["steps"][0]
        assert validate_step["params"]["is_url"] is False


class TestE2EExitCodes:
    """E2E: verify correct exit codes for different scenarios."""

    def test_dry_run_returns_zero_exit_code(self) -> None:
        """Successful dry-run exits with code 0."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "sandbox",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0

    def test_missing_required_args_returns_nonzero(self) -> None:
        """Missing required arguments exit with nonzero code."""
        result = runner.invoke(app, ["run", "autonomous", "sandbox"])
        assert result.exit_code != 0

    def test_autonomous_local_without_skip_isolation_fails(self) -> None:
        """Autonomous + local without --dangerously-skip-isolation exits 1."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "local",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dry-run",
            ],
        )
        assert result.exit_code != 0
        assert "dangerously-skip-isolation" in result.output

    def test_autonomous_local_with_skip_isolation_dry_run_succeeds(self) -> None:
        """Autonomous + local + --dangerously-skip-isolation + dry-run exits 0."""
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "local",
                "--repo",
                "/tmp/test-repo",
                "--task",
                "fix bug",
                "--dangerously-skip-isolation",
                "--dry-run",
            ],
        )
        assert result.exit_code == 0
