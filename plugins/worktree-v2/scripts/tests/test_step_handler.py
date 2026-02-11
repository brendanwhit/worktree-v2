"""Tests for step handler: dispatch, git, docker, auth, terminal handlers."""

from backends.auth import MockAuthBackend
from backends.docker import MockDockerBackend
from backends.factory import Backends
from backends.git import MockGitBackend
from backends.terminal import MockTerminalBackend
from orchestrator.executor import StepHandler
from orchestrator.models import WorkflowStep
from orchestrator.step_handler import ExecutionContext, RealStepHandler


def _mock_backends(**overrides) -> Backends:
    """Create a Backends container with all-mock implementations."""
    return Backends(
        docker=overrides.get("docker", MockDockerBackend()),
        git=overrides.get("git", MockGitBackend()),
        terminal=overrides.get("terminal", MockTerminalBackend()),
        auth=overrides.get("auth", MockAuthBackend()),
    )


# ---------------------------------------------------------------------------
# Task 17: ExecutionContext and dispatch
# ---------------------------------------------------------------------------


class TestExecutionContext:
    def test_creation_with_backends(self):
        backends = _mock_backends()
        ctx = ExecutionContext(backends=backends)
        assert ctx.backends is backends

    def test_step_outputs_default_empty(self):
        ctx = ExecutionContext(backends=_mock_backends())
        assert ctx.step_outputs == {}

    def test_step_outputs_accumulates(self):
        ctx = ExecutionContext(backends=_mock_backends())
        ctx.step_outputs["s1"] = {"path": "/tmp/repo"}
        ctx.step_outputs["s2"] = {"sandbox": "my-sandbox"}
        assert len(ctx.step_outputs) == 2
        assert ctx.step_outputs["s1"]["path"] == "/tmp/repo"


class TestRealStepHandlerDispatch:
    def test_satisfies_protocol(self):
        handler = RealStepHandler(ExecutionContext(backends=_mock_backends()))
        assert isinstance(handler, StepHandler)

    def test_unknown_action_returns_failure(self):
        handler = RealStepHandler(ExecutionContext(backends=_mock_backends()))
        step = WorkflowStep(id="test", action="nonexistent")
        result = handler.execute(step)
        assert result.success is False
        assert result.step_id == "test"
        assert "Unknown action" in result.message

    def test_all_planner_actions_registered(self):
        """Every action the planner emits has a handler in the dispatch table."""
        handler = RealStepHandler(ExecutionContext(backends=_mock_backends()))
        expected = {
            "validate_repo",
            "create_worktree",
            "prepare_sandbox",
            "authenticate",
            "initialize_state",
            "start_agent",
        }
        # Access the dispatch keys through a property
        assert expected == set(handler.registered_actions)


# ---------------------------------------------------------------------------
# Task 18: Git step handlers
# ---------------------------------------------------------------------------


class TestValidateRepoHandler:
    def test_local_path_found(self, tmp_path):
        """When repo is a local path and git finds it, succeed and return repo_path."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": str(repo_path), "is_url": False},
        )
        result = handler.execute(step)

        assert result.success is True
        assert result.data["repo_path"] == str(repo_path)

    def test_local_path_not_found(self):
        """When repo is a local path and git can't find it, fail."""
        git = MockGitBackend()  # no local_repos → ensure_local returns None
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": "/nonexistent/repo", "is_url": False},
        )
        result = handler.execute(step)

        assert result.success is False
        assert "not found" in result.message.lower()

    def test_url_clones_when_no_local(self):
        """When repo is a URL and no local clone exists, clone it."""
        git = MockGitBackend()  # no local_repos
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": "https://github.com/user/my-repo.git", "is_url": True},
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(git.cloned) == 1
        assert "my-repo" in str(git.cloned[0][1])

    def test_url_uses_existing_clone(self, tmp_path):
        """When repo is a URL and a local clone exists, use it without cloning."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(
            local_repos={"https://github.com/user/my-repo.git": repo_path}
        )
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": "https://github.com/user/my-repo.git", "is_url": True},
        )
        result = handler.execute(step)

        assert result.success is True
        assert result.data["repo_path"] == str(repo_path)
        assert len(git.cloned) == 0  # no clone needed

    def test_url_clone_fails(self):
        """When cloning fails, return failure."""
        git = MockGitBackend(fail_on="clone")
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": "https://github.com/user/repo.git", "is_url": True},
        )
        result = handler.execute(step)

        assert result.success is False
        assert "clone" in result.message.lower() or "failed" in result.message.lower()

    def test_outputs_saved_to_context(self, tmp_path):
        """Successful validate_repo saves repo_path to context step_outputs."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="validate_repo",
            action="validate_repo",
            params={"repo": str(repo_path), "is_url": False},
        )
        handler.execute(step)

        assert ctx.step_outputs["validate_repo"]["repo_path"] == str(repo_path)


class TestCreateWorktreeHandler:
    def test_creates_worktree(self, tmp_path):
        """Creates a worktree using the repo_path from validate_repo outputs."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend()
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(git.worktrees) == 1
        assert git.worktrees[0][0] == repo_path  # repo
        assert git.worktrees[0][1] == "agent/test"  # branch

    def test_worktree_failure(self, tmp_path):
        """When git.create_worktree fails, return failure."""
        git = MockGitBackend(fail_on="create_worktree")
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is False

    def test_outputs_worktree_path(self, tmp_path):
        """Successful create_worktree saves worktree_path to context."""
        git = MockGitBackend()
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        handler.execute(step)

        assert "worktree_path" in ctx.step_outputs["create_worktree"]

    def test_missing_repo_path_fails(self):
        """If validate_repo output is missing, fail gracefully."""
        ctx = ExecutionContext(backends=_mock_backends())
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
        )
        result = handler.execute(step)

        assert result.success is False


# ---------------------------------------------------------------------------
# Task 19: Docker step handlers
# ---------------------------------------------------------------------------


class TestPrepareSandboxHandler:
    def test_creates_sandbox(self, tmp_path):
        """Creates a docker sandbox with the worktree path as workspace."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.created) == 1
        assert docker.created[0][0] == "claude-test"

    def test_force_recreates_existing(self, tmp_path):
        """With force=True, stops existing sandbox before recreating."""
        docker = MockDockerBackend(sandboxes={"claude-test": True})
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": True},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.stopped) == 1
        assert len(docker.created) == 1

    def test_sandbox_creation_fails(self, tmp_path):
        """When docker.create_sandbox fails, return failure."""
        docker = MockDockerBackend(fail_on="create_sandbox")
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is False

    def test_outputs_sandbox_name(self, tmp_path):
        """Successful prepare_sandbox saves sandbox_name to context."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        handler.execute(step)

        assert ctx.step_outputs["prepare_sandbox"]["sandbox_name"] == "claude-test"

    def test_missing_worktree_path_fails(self):
        """If create_worktree output is missing, fail gracefully."""
        ctx = ExecutionContext(backends=_mock_backends())
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": False},
        )
        result = handler.execute(step)

        assert result.success is False


# ---------------------------------------------------------------------------
# Task 20: Auth and terminal step handlers
# ---------------------------------------------------------------------------


class TestAuthenticateHandler:
    def test_sets_up_git_auth(self):
        """Calls auth.setup_git_auth with the sandbox name."""
        auth = MockAuthBackend()
        ctx = ExecutionContext(backends=_mock_backends(auth=auth))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="authenticate",
            action="authenticate",
            params={"sandbox_name": "claude-test"},
            depends_on=["prepare_sandbox"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert auth.git_auths == ["claude-test"]

    def test_auth_failure(self):
        """When auth.setup_git_auth fails, return failure."""
        auth = MockAuthBackend(fail_on="setup_git_auth")
        ctx = ExecutionContext(backends=_mock_backends(auth=auth))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="authenticate",
            action="authenticate",
            params={"sandbox_name": "claude-test"},
            depends_on=["prepare_sandbox"],
        )
        result = handler.execute(step)

        assert result.success is False


class TestInitializeStateHandler:
    def test_initializes_ralph_state(self, tmp_path):
        """Creates .ralph/ directory in the worktree with task config."""
        ctx = ExecutionContext(backends=_mock_backends())
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        ralph_dir = tmp_path / ".ralph"
        assert ralph_dir.is_dir()
        assert (ralph_dir / "config.json").exists()

    def test_missing_worktree_path_fails(self):
        """If create_worktree output is missing, fail gracefully."""
        ctx = ExecutionContext(backends=_mock_backends())
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
        )
        result = handler.execute(step)

        assert result.success is False


class TestStartAgentHandler:
    def test_spawns_in_sandbox(self, tmp_path):
        """When sandbox_name is in params, uses docker.run_agent."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"sandbox_name": "claude-test", "task": "do stuff"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.agents_run) == 1
        assert docker.agents_run[0][0] == "claude-test"

    def test_spawns_locally(self, tmp_path):
        """When no sandbox_name, uses terminal.spawn."""
        terminal = MockTerminalBackend()
        ctx = ExecutionContext(backends=_mock_backends(terminal=terminal))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"task": "do stuff"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(terminal.spawned) == 1

    def test_sandbox_agent_failure(self, tmp_path):
        """When docker.run_agent fails, return failure."""
        docker = MockDockerBackend(fail_on="run_agent")
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"sandbox_name": "claude-test", "task": "do stuff"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is False

    def test_local_spawn_failure(self, tmp_path):
        """When terminal.spawn fails, return failure."""
        terminal = MockTerminalBackend(fail_on="spawn")
        ctx = ExecutionContext(backends=_mock_backends(terminal=terminal))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"task": "do stuff"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is False


# ---------------------------------------------------------------------------
# Integration: full plan with RealStepHandler + mock backends
# ---------------------------------------------------------------------------


class TestFullPlanExecution:
    def test_sandbox_plan_with_real_handler(self, tmp_path):
        """A complete sandbox plan succeeds with mock backends."""
        from orchestrator.executor import Executor
        from orchestrator.planner import Planner, PlannerInput

        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        ctx = ExecutionContext(
            backends=_mock_backends(git=git, docker=docker),
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="test task")
        )
        result = executor.run(plan)

        assert result.error is None, f"Unexpected error: {result.error}"
        assert len(result.completed_steps) == 6
        assert result.failed_step is None

    def test_local_plan_with_real_handler(self, tmp_path):
        """A complete local plan succeeds with mock backends."""
        from orchestrator.executor import Executor
        from orchestrator.planner import Planner, PlannerInput

        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        ctx = ExecutionContext(
            backends=_mock_backends(git=git),
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="test task", target="local")
        )
        result = executor.run(plan)

        assert result.error is None, f"Unexpected error: {result.error}"
        assert len(result.completed_steps) == 4
        assert result.failed_step is None
