"""Integration tests: full orchestration flow with mock backends.

Tests the Planner -> Executor -> RealStepHandler -> MockBackends pipeline
end-to-end, verifying that backends receive the correct calls and that
state transitions happen correctly.
"""

from pathlib import Path

from superintendent.backends.auth import MockAuthBackend
from superintendent.backends.docker import MockDockerBackend
from superintendent.backends.factory import Backends
from superintendent.backends.git import MockGitBackend
from superintendent.backends.terminal import MockTerminalBackend
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.workflow import WorkflowState


def _mock_backends(**overrides) -> Backends:
    """Create a Backends container with all-mock implementations."""
    return Backends(
        docker=overrides.get("docker", MockDockerBackend()),
        git=overrides.get("git", MockGitBackend()),
        terminal=overrides.get("terminal", MockTerminalBackend()),
        auth=overrides.get("auth", MockAuthBackend()),
    )


class TestSandboxFlowIntegration:
    """Full sandbox workflow: planner -> executor -> mock backends."""

    def test_sandbox_plan_completes_all_six_steps(self, tmp_path: Path) -> None:
        """A sandbox plan creates 6 steps and all complete successfully."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, docker=docker, auth=auth)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.error is None
        assert len(result.completed_steps) == 6
        assert result.failed_step is None
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_sandbox_flow_calls_git_ensure_local(self, tmp_path: Path) -> None:
        """The validate_repo step calls git.ensure_local with the repo path."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert ctx.step_outputs["validate_repo"]["repo_path"] == str(repo_path)

    def test_sandbox_flow_creates_worktree(self, tmp_path: Path) -> None:
        """The create_worktree step calls git.create_worktree with correct args."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(git.worktrees) == 1
        worktree_repo, worktree_branch, _ = git.worktrees[0]
        assert worktree_repo == repo_path
        assert "agent/" in worktree_branch

    def test_sandbox_flow_creates_docker_sandbox(self, tmp_path: Path) -> None:
        """The prepare_sandbox step calls docker.create_sandbox."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.created) == 1
        sandbox_name, workspace, _ = docker.created[0]
        assert sandbox_name.startswith("claude-")

    def test_sandbox_flow_authenticates(self, tmp_path: Path) -> None:
        """The authenticate step calls auth.setup_git_auth with sandbox name."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, auth=auth)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(auth.git_auths) == 1
        assert auth.git_auths[0].startswith("claude-")

    def test_sandbox_flow_initializes_ralph_state(self, tmp_path: Path) -> None:
        """The initialize_state step creates .ralph/ directory in worktree."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        ralph_dir = ctx.step_outputs["initialize_state"]["ralph_dir"]
        assert Path(ralph_dir).name == ".ralph"

    def test_sandbox_flow_runs_agent_in_docker(self, tmp_path: Path) -> None:
        """The start_agent step calls docker.run_agent for sandbox target."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.agents_run) == 1
        agent_sandbox, _, agent_prompt = docker.agents_run[0]
        assert agent_sandbox.startswith("claude-")
        assert agent_prompt == "fix bug"

    def test_sandbox_custom_sandbox_name(self, tmp_path: Path) -> None:
        """A custom sandbox_name is passed through to docker operations."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo=str(repo_path),
                task="fix bug",
                sandbox_name="my-custom-sandbox",
            )
        )
        result = executor.run(plan)

        assert result.error is None
        assert docker.created[0][0] == "my-custom-sandbox"
        assert docker.agents_run[0][0] == "my-custom-sandbox"


class TestLocalFlowIntegration:
    """Full local workflow: planner -> executor -> mock backends."""

    def test_local_plan_completes_four_steps(self, tmp_path: Path) -> None:
        """A local plan creates 4 steps and all complete successfully."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        terminal = MockTerminalBackend()
        backends = _mock_backends(git=git, terminal=terminal)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(result.completed_steps) == 4
        assert result.failed_step is None
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_local_plan_skips_sandbox_and_auth(self, tmp_path: Path) -> None:
        """A local plan does not call docker or auth backends."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, docker=docker, auth=auth)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        executor.run(plan)

        assert len(docker.created) == 0
        assert len(auth.git_auths) == 0

    def test_local_plan_spawns_terminal_agent(self, tmp_path: Path) -> None:
        """A local plan spawns the agent via terminal.spawn."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        terminal = MockTerminalBackend()
        backends = _mock_backends(git=git, terminal=terminal)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        executor.run(plan)

        assert len(terminal.spawned) == 1
        cmd, _ = terminal.spawned[0]
        assert "fix bug" in cmd


class TestContainerFlowIntegration:
    """Full container workflow: planner -> executor -> mock backends."""

    def test_container_plan_completes_six_steps(self, tmp_path: Path) -> None:
        """A container plan creates 6 steps like sandbox mode."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(result.completed_steps) == 6
        assert result.state == WorkflowState.AGENT_RUNNING


class TestURLRepoIntegration:
    """Integration tests for URL-based repos that need cloning."""

    def test_url_repo_triggers_clone(self) -> None:
        """When repo is a URL and no local clone exists, git.clone is called."""
        git = MockGitBackend()  # no local_repos -> ensure_local returns None
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo="https://github.com/user/my-repo.git",
                task="fix bug",
            )
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(git.cloned) == 1
        assert "my-repo" in str(git.cloned[0][1])

    def test_url_repo_uses_existing_clone(self, tmp_path: Path) -> None:
        """When a local clone already exists for a URL, skip cloning."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(
            local_repos={"https://github.com/user/my-repo.git": repo_path}
        )
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo="https://github.com/user/my-repo.git",
                task="fix bug",
            )
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(git.cloned) == 0
        assert ctx.step_outputs["validate_repo"]["repo_path"] == str(repo_path)


class TestForceRecreationIntegration:
    """Integration tests for force=True with existing sandbox."""

    def test_force_stops_existing_sandbox_before_creating(self, tmp_path: Path) -> None:
        """With force=True, an existing sandbox is stopped before recreation."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(sandboxes={"claude-my-repo": True})
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", force=True)
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(docker.stopped) == 1
        assert docker.stopped[0] == "claude-my-repo"
        assert len(docker.created) == 1

    def test_force_false_does_not_stop_sandbox(self, tmp_path: Path) -> None:
        """With force=False, no sandbox is stopped even if it exists."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(sandboxes={"claude-my-repo": True})
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", force=False)
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(docker.stopped) == 0


class TestFailurePropagationIntegration:
    """Integration tests for error propagation through the full pipeline."""

    def test_git_failure_stops_execution_early(self) -> None:
        """When git.ensure_local fails, execution stops at validate_repo."""
        git = MockGitBackend()  # no local repos, non-URL path -> failure
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/nonexistent/repo", task="fix bug")
        )
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "validate_repo"
        assert len(result.completed_steps) == 0

    def test_worktree_failure_stops_after_validate(self, tmp_path: Path) -> None:
        """When create_worktree fails, validate_repo succeeds but execution stops."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            fail_on="create_worktree",
        )
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "create_worktree"
        assert result.completed_steps == ["validate_repo"]

    def test_docker_failure_stops_after_worktree(self, tmp_path: Path) -> None:
        """When docker.create_sandbox fails, first two steps succeed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="create_sandbox")
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "prepare_sandbox"
        assert result.completed_steps == ["validate_repo", "create_worktree"]

    def test_auth_failure_stops_after_sandbox(self, tmp_path: Path) -> None:
        """When auth.setup_git_auth fails, first three steps succeed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        auth = MockAuthBackend(fail_on="setup_git_auth")
        backends = _mock_backends(git=git, auth=auth)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "authenticate"
        assert result.completed_steps == [
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
        ]

    def test_agent_failure_stops_at_last_step(self, tmp_path: Path) -> None:
        """When docker.run_agent fails, all steps except start_agent succeed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="run_agent")
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "start_agent"
        assert len(result.completed_steps) == 5

    def test_local_terminal_failure(self, tmp_path: Path) -> None:
        """When terminal.spawn fails in local mode, execution stops at start_agent."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        terminal = MockTerminalBackend(fail_on="spawn")
        backends = _mock_backends(git=git, terminal=terminal)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "start_agent"
        assert len(result.completed_steps) == 3

    def test_failure_result_contains_error_message(self) -> None:
        """When a step fails, the error field contains a descriptive message."""
        git = MockGitBackend()
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/nonexistent/repo", task="fix bug")
        )
        result = executor.run(plan)

        assert result.error is not None
        assert len(result.error) > 0

    def test_failure_records_step_result(self) -> None:
        """Failed step result is recorded in step_results dict."""
        git = MockGitBackend()
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/nonexistent/repo", task="fix bug")
        )
        result = executor.run(plan)

        assert "validate_repo" in result.step_results
        assert result.step_results["validate_repo"].success is False


class TestStateTransitionsIntegration:
    """Integration tests verifying executor state transitions through full flow."""

    def test_sandbox_flow_reaches_agent_running(self, tmp_path: Path) -> None:
        """After successful sandbox flow, executor state is AGENT_RUNNING."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert executor.state == WorkflowState.AGENT_RUNNING
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_local_flow_reaches_agent_running(self, tmp_path: Path) -> None:
        """After successful local flow, executor state is AGENT_RUNNING."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        result = executor.run(plan)

        assert executor.state == WorkflowState.AGENT_RUNNING
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_failed_flow_reaches_failed_state(self) -> None:
        """After a failure, executor state is FAILED."""
        git = MockGitBackend()
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/nonexistent/repo", task="fix bug")
        )
        executor.run(plan)

        assert executor.state == WorkflowState.FAILED

    def test_checkpoints_saved_for_each_step(self, tmp_path: Path) -> None:
        """Executor saves a checkpoint for every executed step."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(executor.checkpoints) == 6
        for cp in executor.checkpoints:
            assert cp["success"] is True
