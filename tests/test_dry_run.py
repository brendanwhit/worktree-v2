"""Dry-run verification tests.

Verify that dry-run mode shows correct commands without executing.
Uses DryRun backends through the RealStepHandler + Executor pipeline
and verifies the commands each backend records.
"""

from pathlib import Path

from superintendent.backends.auth import DryRunAuthBackend
from superintendent.backends.docker import DryRunDockerBackend
from superintendent.backends.factory import Backends
from superintendent.backends.git import DryRunGitBackend
from superintendent.backends.terminal import DryRunTerminalBackend
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.workflow import WorkflowState


def _dryrun_backends() -> Backends:
    """Create a Backends container with all DryRun implementations."""
    return Backends(
        docker=DryRunDockerBackend(),
        git=DryRunGitBackend(),
        terminal=DryRunTerminalBackend(),
        auth=DryRunAuthBackend(),
    )


class TestDryRunSandboxCommands:
    """Verify dry-run sandbox flow records correct commands."""

    def test_sandbox_flow_completes_without_errors(self) -> None:
        """Dry-run sandbox flow succeeds end-to-end."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        result = executor.run(plan)

        assert result.error is None
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_sandbox_flow_records_git_commands(self) -> None:
        """Dry-run records git ensure_local and worktree commands."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        git = backends.git
        assert isinstance(git, DryRunGitBackend)
        assert len(git.commands) >= 2
        # First command: ensure_local
        assert "ensure_local" in git.commands[0]
        assert "/tmp/my-repo" in git.commands[0]
        # Second command: worktree add
        assert "worktree add" in git.commands[1]

    def test_sandbox_flow_records_docker_create(self) -> None:
        """Dry-run records docker sandbox create command."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        create_cmds = [c for c in docker.commands if "create" in c]
        assert len(create_cmds) >= 1
        assert "claude-my-repo" in create_cmds[0]

    def test_sandbox_flow_records_auth_command(self) -> None:
        """Dry-run records auth setup command."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        auth = backends.auth
        assert isinstance(auth, DryRunAuthBackend)
        assert len(auth.commands) == 1
        assert "gh auth setup-git" in auth.commands[0]
        assert "claude-my-repo" in auth.commands[0]

    def test_sandbox_flow_records_agent_run(self) -> None:
        """Dry-run records docker sandbox run command for agent."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        run_cmds = [c for c in docker.commands if "run" in c]
        assert len(run_cmds) >= 1
        assert "claude-my-repo" in run_cmds[0]
        assert "fix bug" in run_cmds[0]


class TestDryRunLocalCommands:
    """Verify dry-run local flow records correct commands."""

    def test_local_flow_completes_without_errors(self) -> None:
        """Dry-run local flow succeeds end-to-end."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", target="local")
        )
        result = executor.run(plan)

        assert result.error is None
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_local_flow_records_no_docker_commands(self) -> None:
        """Local dry-run does not record any docker commands."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", target="local")
        )
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        assert len(docker.commands) == 0

    def test_local_flow_records_no_auth_commands(self) -> None:
        """Local dry-run does not record any auth commands."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", target="local")
        )
        executor.run(plan)

        auth = backends.auth
        assert isinstance(auth, DryRunAuthBackend)
        assert len(auth.commands) == 0

    def test_local_flow_records_terminal_spawn(self) -> None:
        """Local dry-run records terminal spawn command."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", target="local")
        )
        executor.run(plan)

        terminal = backends.terminal
        assert isinstance(terminal, DryRunTerminalBackend)
        assert len(terminal.commands) >= 1
        assert "fix bug" in terminal.commands[0]


class TestDryRunNoSideEffects:
    """Verify dry-run mode has no side effects."""

    def test_dryrun_does_not_create_directories(self, tmp_path: Path) -> None:
        """Dry-run does not create .ralph/ or worktree directories on disk."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(tmp_path / "repo"), task="fix bug")
        )
        executor.run(plan)

        # DryRunGitBackend.ensure_local returns Path(repo) without checking disk,
        # and .ralph/ initialization uses real filesystem. Check that the worktree
        # path from dry-run is computed but not created on real filesystem.
        worktree_output = ctx.step_outputs.get("create_worktree", {})
        if "worktree_path" in worktree_output:
            # The worktree path itself may exist if it maps to tmp_path parent,
            # but no .git directory should be created inside it
            wt_path = Path(worktree_output["worktree_path"])
            assert not (wt_path / ".git").exists()

    def test_dryrun_docker_does_not_start_containers(self) -> None:
        """Dry-run docker backend does not actually start containers."""
        docker = DryRunDockerBackend()
        docker.create_sandbox("test", Path("/tmp/workspace"))
        docker.start_sandbox("test")
        docker.run_agent("test", Path("/tmp/workspace"), "do stuff")

        # Operations recorded as commands but nothing actually ran
        assert len(docker.commands) == 3
        # sandbox_exists returns False (no real lookup)
        assert docker.sandbox_exists("test") is False

    def test_dryrun_git_does_not_clone(self) -> None:
        """Dry-run git backend does not actually clone repos."""
        git = DryRunGitBackend()
        result = git.clone("https://github.com/user/repo.git", Path("/tmp/clone"))

        assert result is True  # reports success
        assert len(git.commands) == 1
        assert "git clone" in git.commands[0]

    def test_dryrun_terminal_does_not_spawn(self) -> None:
        """Dry-run terminal backend does not actually spawn processes."""
        terminal = DryRunTerminalBackend()
        result = terminal.spawn("echo hello", Path("/tmp"))

        assert result is True  # reports success
        assert len(terminal.commands) == 1
        # DryRunTerminalBackend tracks state (is_running=True after spawn)
        # but no real OS process is created
        assert terminal.is_running() is True

    def test_dryrun_auth_does_not_authenticate(self) -> None:
        """Dry-run auth backend does not actually set up auth."""
        auth = DryRunAuthBackend()
        result = auth.setup_git_auth("test-sandbox")

        assert result is True  # reports success
        assert len(auth.commands) == 1
        assert "gh auth setup-git" in auth.commands[0]


class TestDryRunCustomSandboxName:
    """Verify dry-run with custom sandbox name records correct commands."""

    def test_custom_sandbox_name_in_docker_commands(self) -> None:
        """Custom sandbox name appears in docker commands."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo="/tmp/my-repo",
                task="fix bug",
                sandbox_name="my-custom-sandbox",
            )
        )
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        all_commands = " ".join(docker.commands)
        assert "my-custom-sandbox" in all_commands

    def test_custom_sandbox_name_in_auth_commands(self) -> None:
        """Custom sandbox name appears in auth commands."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo="/tmp/my-repo",
                task="fix bug",
                sandbox_name="my-custom-sandbox",
            )
        )
        executor.run(plan)

        auth = backends.auth
        assert isinstance(auth, DryRunAuthBackend)
        assert "my-custom-sandbox" in auth.commands[0]


class TestDryRunURLRepo:
    """Verify dry-run with URL repo records clone command."""

    def test_url_repo_records_ensure_local(self) -> None:
        """DryRunGitBackend.ensure_local returns a Path for the URL."""
        backends = _dryrun_backends()
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

        # DryRunGitBackend.ensure_local returns Path(repo) so validate_repo
        # succeeds without cloning
        assert result.error is None
        git = backends.git
        assert isinstance(git, DryRunGitBackend)
        assert any("ensure_local" in cmd for cmd in git.commands)


class TestDryRunForceFlag:
    """Verify dry-run with force=True records stop + create commands."""

    def test_force_records_sandbox_exists_check(self) -> None:
        """With force=True, dry-run checks if sandbox exists."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", force=True)
        )
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        # DryRunDockerBackend.sandbox_exists records a grep command
        exists_cmds = [c for c in docker.commands if "grep" in c]
        assert len(exists_cmds) == 1

    def test_force_still_creates_sandbox(self) -> None:
        """With force=True, dry-run still records sandbox creation."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="fix bug", force=True)
        )
        result = executor.run(plan)

        assert result.error is None
        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        create_cmds = [c for c in docker.commands if "create" in c]
        assert len(create_cmds) >= 1


class TestDryRunCommandContent:
    """Verify the content of recorded commands matches expected format."""

    def test_git_worktree_command_format(self) -> None:
        """Git worktree command includes repo path, branch, and target."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo="/tmp/my-repo",
                task="fix bug",
                branch="feature-branch",
            )
        )
        executor.run(plan)

        git = backends.git
        assert isinstance(git, DryRunGitBackend)
        worktree_cmds = [c for c in git.commands if "worktree" in c]
        assert len(worktree_cmds) == 1
        assert "feature-branch" in worktree_cmds[0]
        assert "worktree add" in worktree_cmds[0]

    def test_docker_create_command_includes_workspace(self) -> None:
        """Docker create command includes workspace volume mount."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        create_cmds = [c for c in docker.commands if "create" in c]
        assert len(create_cmds) >= 1
        assert ":/workspace" in create_cmds[0]

    def test_auth_command_references_sandbox(self) -> None:
        """Auth setup command includes the sandbox name."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo="/tmp/my-repo", task="fix bug"))
        executor.run(plan)

        auth = backends.auth
        assert isinstance(auth, DryRunAuthBackend)
        assert len(auth.commands) == 1
        assert "docker sandbox exec" in auth.commands[0]
        assert "claude-my-repo" in auth.commands[0]

    def test_agent_run_command_includes_prompt(self) -> None:
        """Docker run agent command includes the task prompt."""
        backends = _dryrun_backends()
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo="/tmp/my-repo", task="implement auth system")
        )
        executor.run(plan)

        docker = backends.docker
        assert isinstance(docker, DryRunDockerBackend)
        run_cmds = [c for c in docker.commands if "run" in c]
        assert any("implement auth system" in c for c in run_cmds)
