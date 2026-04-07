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
from superintendent.cli.main import _branch_to_slug, _extract_repo_name
from superintendent.orchestrator.executor import Executor
from superintendent.orchestrator.planner import Planner, PlannerInput
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry
from superintendent.state.token_store import TokenStore
from superintendent.state.workflow import WorkflowState


def _mock_backends(**overrides) -> Backends:
    """Create a Backends container with all-mock implementations."""
    return Backends(
        docker=overrides.get("docker", MockDockerBackend()),
        git=overrides.get("git", MockGitBackend()),
        terminal=overrides.get("terminal", MockTerminalBackend()),
        auth=overrides.get("auth", MockAuthBackend()),
    )


def _test_token_store(tmp_path: Path) -> TokenStore:
    """Create a token store with a default token for deterministic testing.

    Integration tests for sandbox/container flows need validate_auth to pass,
    which requires a resolvable token. This avoids depending on host-level
    gh auth or environment variables.
    """
    store = TokenStore(path=tmp_path / "test-tokens.json")
    store.add("_default", "ghp_test_default_token", github_user="testuser")
    return store


class TestSandboxFlowIntegration:
    """Full sandbox workflow: planner -> executor -> mock backends."""

    def test_sandbox_plan_completes_all_eight_steps(self, tmp_path: Path) -> None:
        """A sandbox plan creates 8 steps and all complete successfully."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, docker=docker, auth=auth)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.error is None
        assert len(result.completed_steps) == 8
        assert "validate_auth" in result.completed_steps
        assert "prepare_template" in result.completed_steps
        assert result.failed_step is None
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_sandbox_flow_calls_git_ensure_local(self, tmp_path: Path) -> None:
        """The validate_repo step calls git.ensure_local with the repo path."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert ctx.step_outputs["validate_repo"]["repo_path"] == str(repo_path)

    def test_sandbox_flow_creates_standalone_clone(self, tmp_path: Path) -> None:
        """The create_worktree step calls git.clone_for_sandbox for sandbox target."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(git.sandbox_clones) == 1
        source, _, branch = git.sandbox_clones[0]
        assert source == repo_path
        assert "agent/" in branch
        # Regular worktree should NOT be called
        assert len(git.worktrees) == 0

    def test_sandbox_flow_builds_template(self, tmp_path: Path) -> None:
        """The prepare_template step builds a Docker template image."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.templates_built) == 1
        assert docker.templates_built[0][1].startswith("supt-sandbox:")

    def test_sandbox_flow_passes_template_to_create_sandbox(
        self, tmp_path: Path
    ) -> None:
        """The template tag is passed to docker.create_sandbox."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.created) == 1
        sandbox_name, workspace, template = docker.created[0]
        assert sandbox_name.startswith("claude-")
        assert template is not None
        assert template.startswith("supt-sandbox:")

    def test_sandbox_flow_creates_docker_sandbox(self, tmp_path: Path) -> None:
        """The prepare_sandbox step calls docker.create_sandbox."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.created) == 1
        sandbox_name, workspace, _ = docker.created[0]
        assert sandbox_name.startswith("claude-")

    def test_sandbox_flow_authenticates(self, tmp_path: Path) -> None:
        """The authenticate step calls auth.inject_token or setup_git_auth."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, auth=auth)
        # Use token store with default token so validate_auth passes
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        # With a stored token, inject_token is called during authenticate
        assert len(auth.git_auths) + len(auth.tokens_injected) >= 1

    def test_sandbox_flow_initializes_ralph_state(self, tmp_path: Path) -> None:
        """The initialize_state step creates .ralph/ directory in worktree."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(docker.agents_run) == 1
        agent_sandbox, agent_prompt, _, _ = docker.agents_run[0]
        assert agent_sandbox.startswith("claude-")
        assert "fix bug" in agent_prompt
        assert "do NOT exit" in agent_prompt

    def test_context_file_injected_into_agent_prompt(self, tmp_path: Path) -> None:
        """The context file content is injected into the agent prompt."""
        repo_path = tmp_path / "my-repo"
        context_file = tmp_path / "plan.md"
        context_file.write_text("# Plan\n\nStep 1: Do the thing\n")

        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo=str(repo_path),
                task="do the thing",
                context_file=str(context_file),
            )
        )
        executor.run(plan)

        assert len(docker.agents_run) == 1
        _, agent_prompt, _, _ = docker.agents_run[0]
        assert "do the thing" in agent_prompt
        assert ".ralph/context.md" in agent_prompt
        # Content is NOT inlined — agent reads the file itself
        assert "Step 1: Do the thing" not in agent_prompt

        # Context file is persisted in .ralph/
        wt_path = Path(ctx.step_outputs["create_worktree"]["worktree_path"])
        ralph_context = wt_path / ".ralph" / "context.md"
        assert ralph_context.exists()
        assert "Step 1: Do the thing" in ralph_context.read_text()

    def test_sandbox_custom_sandbox_name(self, tmp_path: Path) -> None:
        """A custom sandbox_name is passed through to docker operations."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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

    def test_container_plan_completes_eight_steps(self, tmp_path: Path) -> None:
        """A container plan creates 8 steps and all complete successfully."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(result.completed_steps) == 8
        assert "validate_auth" in result.completed_steps
        assert "prepare_template" in result.completed_steps
        assert result.state == WorkflowState.AGENT_RUNNING

    def test_container_flow_creates_standalone_clone(self, tmp_path: Path) -> None:
        """Container target uses clone_for_sandbox, not regular worktree."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        executor.run(plan)

        assert len(git.sandbox_clones) == 1
        assert len(git.worktrees) == 0
        source, _, branch = git.sandbox_clones[0]
        assert source == repo_path
        assert "agent/" in branch

    def test_container_flow_uses_create_container_not_sandbox(
        self, tmp_path: Path
    ) -> None:
        """Container target calls docker.create_container, not create_sandbox."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        executor.run(plan)

        assert len(docker.containers_created) == 1
        assert len(docker.created) == 0  # no sandbox created
        assert docker.containers_created[0][0].startswith("claude-")

    def test_container_flow_authenticates_with_container_name(
        self, tmp_path: Path
    ) -> None:
        """Container flow passes container_name to auth, not sandbox_name."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        auth = MockAuthBackend()
        backends = _mock_backends(git=git, auth=auth)
        # Use token store with default token so validate_auth passes
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        executor.run(plan)

        # With a stored token, inject_token is called during authenticate
        assert len(auth.git_auths) + len(auth.tokens_injected) >= 1

    def test_container_flow_runs_agent_with_container_name(
        self, tmp_path: Path
    ) -> None:
        """Container flow uses container_name for docker.run_agent."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        executor.run(plan)

        assert len(docker.agents_run) == 1
        assert docker.agents_run[0][0].startswith("claude-")

    def test_container_custom_name(self, tmp_path: Path) -> None:
        """Custom sandbox_name is used as container_name for container target."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo=str(repo_path),
                task="fix bug",
                target="container",
                sandbox_name="my-container",
            )
        )
        result = executor.run(plan)

        assert result.error is None
        assert docker.containers_created[0][0] == "my-container"
        assert docker.agents_run[0][0] == "my-container"

    def test_container_force_stops_existing(self, tmp_path: Path) -> None:
        """With force=True, container target stops existing container."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(containers={"claude-my-repo": True})
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo=str(repo_path), task="fix bug", target="container", force=True
            )
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(docker.containers_stopped) == 1
        assert len(docker.containers_created) == 1
        # Sandbox operations should not be called
        assert len(docker.stopped) == 0
        assert len(docker.created) == 0

    def test_container_creation_failure(self, tmp_path: Path) -> None:
        """When docker.create_container fails, execution stops at prepare_container."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="create_container")
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="container")
        )
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "prepare_container"
        assert result.completed_steps == [
            "validate_repo",
            "validate_auth",
            "create_worktree",
            "prepare_template",
        ]


class TestBeadsInitIntegration:
    """Integration tests for beads initialization in sandboxes."""

    def test_beads_init_passes_database_flag(self, tmp_path: Path) -> None:
        """The _init_beads step passes --database with sanitized name."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        # Find the bd init command in docker exec calls
        init_cmds = [cmd for _, cmd in docker.executed if "bd init" in cmd]
        assert len(init_cmds) == 1
        assert "--database" in init_cmds[0]
        assert "--sandbox" in init_cmds[0]

    def test_beads_init_sanitizes_dots_in_repo_name(self, tmp_path: Path) -> None:
        """Dots in repo names are replaced with underscores for Dolt compatibility."""
        repo_path = tmp_path / "prview.nvim"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        init_cmds = [cmd for _, cmd in docker.executed if "bd init" in cmd]
        assert len(init_cmds) == 1
        # Dots should be replaced with underscores
        assert "prview_nvim" in init_cmds[0]
        assert ".nvim" not in init_cmds[0]

    def test_beads_init_retries_on_failure(self, tmp_path: Path) -> None:
        """If bd init fails, it retries once after cleanup."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})

        # First call to bd init fails, cleanup succeeds, second call succeeds
        call_count = {"n": 0}
        original_exec_results: dict[str, tuple[int, str]] = {}

        class CountingDockerBackend(MockDockerBackend):
            def exec_in_sandbox(self, name: str, cmd: str) -> tuple[int, str]:
                self.executed.append((name, cmd))
                if "bd init" in cmd:
                    call_count["n"] += 1
                    if call_count["n"] == 1:
                        return (1, "fsync error")  # First attempt fails
                    return (0, "")  # Second attempt succeeds
                return original_exec_results.get(cmd, (0, ""))

        docker = CountingDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.error is None
        assert call_count["n"] == 2  # bd init called twice


class TestURLRepoIntegration:
    """Integration tests for URL-based repos that need cloning."""

    def test_url_repo_triggers_clone(self, tmp_path: Path) -> None:
        """When repo is a URL and no local clone exists, git.clone is called."""
        git = MockGitBackend()  # no local_repos -> ensure_local returns None
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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

    def test_force_stops_and_removes_existing_sandbox(self, tmp_path: Path) -> None:
        """With force=True, an existing sandbox is stopped and removed before recreation."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(sandboxes={"claude-my-repo": True})
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", force=True)
        )
        result = executor.run(plan)

        assert result.error is None
        assert len(docker.stopped) == 1
        assert docker.stopped[0] == "claude-my-repo"
        assert len(docker.removed) == 1
        assert docker.removed[0] == "claude-my-repo"
        assert len(docker.created) == 1

    def test_force_false_does_not_stop_sandbox(self, tmp_path: Path) -> None:
        """With force=False, no sandbox is stopped even if it exists."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(sandboxes={"claude-my-repo": True})
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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
        """When create_worktree fails, validate_repo and validate_auth succeed but
        execution stops.

        For sandbox target (default), clone_for_sandbox is called, so we fail that.
        """
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            fail_on="clone_for_sandbox",
        )
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "create_worktree"
        assert result.completed_steps == ["validate_repo", "validate_auth"]

    def test_local_worktree_failure_stops_after_validate(self, tmp_path: Path) -> None:
        """When create_worktree fails in local mode, execution stops after validate."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            fail_on="create_worktree",
        )
        backends = _mock_backends(git=git)
        ctx = ExecutionContext(backends=backends)
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="fix bug", target="local")
        )
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "create_worktree"
        assert result.completed_steps == ["validate_repo"]

    def test_docker_failure_stops_after_worktree(self, tmp_path: Path) -> None:
        """When docker.create_sandbox fails, first four steps succeed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="create_sandbox")
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "prepare_sandbox"
        assert result.completed_steps == [
            "validate_repo",
            "validate_auth",
            "create_worktree",
            "prepare_template",
        ]

    def test_auth_failure_stops_after_sandbox(self, tmp_path: Path) -> None:
        """When auth fails, first five steps succeed (including validate_auth)."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        # Fail inject_token (used when token found during authenticate step)
        auth = MockAuthBackend(fail_on="inject_token")
        backends = _mock_backends(git=git, auth=auth)
        # Use token store with default token so validate_auth passes,
        # but inject_token fails during the authenticate step
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "authenticate"
        assert result.completed_steps == [
            "validate_repo",
            "validate_auth",
            "create_worktree",
            "prepare_template",
            "prepare_sandbox",
        ]

    def test_agent_failure_stops_at_last_step(self, tmp_path: Path) -> None:
        """When docker.run_agent fails, all steps except start_agent succeed."""
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend(fail_on="run_agent")
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        result = executor.run(plan)

        assert result.state == WorkflowState.FAILED
        assert result.failed_step == "start_agent"
        assert len(result.completed_steps) == 7

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
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
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
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(PlannerInput(repo=str(repo_path), task="fix bug"))
        executor.run(plan)

        assert len(executor.checkpoints) == 8
        for cp in executor.checkpoints:
            assert cp["success"] is True


class TestRegistrationIntegration:
    """Tests that run() registration logic produces correct WorktreeEntry fields.

    These tests exercise the same registration logic that lives in the CLI's
    run() command, but in isolation — building a plan, running it with mock
    backends, and then applying the registration logic to a tmp_path registry.
    """

    def _run_and_register(
        self, tmp_path: Path, target: str = "sandbox", sandbox_name: str | None = None
    ) -> tuple[WorktreeRegistry, "WorktreeEntry"]:
        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        backends = _mock_backends(git=git, docker=docker)
        ctx = ExecutionContext(
            backends=backends, token_store=_test_token_store(tmp_path)
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(
                repo=str(repo_path),
                task="fix bug",
                target=target,
                sandbox_name=sandbox_name,
            )
        )
        result = executor.run(plan)
        assert result.error is None

        # Apply the same registration logic as run()
        registry = WorktreeRegistry(tmp_path / "test-registry.json")
        worktree_path = ctx.step_outputs.get("create_worktree", {}).get(
            "worktree_path", ""
        )
        branch_name = plan.metadata.get("branch", "")
        repo_name = plan.metadata.get("repo_name", _extract_repo_name(str(repo_path)))
        name = _branch_to_slug(branch_name) if branch_name else repo_name

        target_val = plan.metadata.get("target")
        if target_val == "sandbox":
            env_name = plan.metadata.get("sandbox_name")
        elif target_val == "container":
            env_name = plan.metadata.get("container_name")
        else:
            env_name = None

        entry = WorktreeEntry(
            name=name,
            repo=str(repo_path),
            branch=branch_name,
            worktree_path=worktree_path,
            sandbox_name=env_name,
        )
        registry.add(entry)
        return registry, entry

    def test_sandbox_registration(self, tmp_path: Path):
        """Sandbox target registers with sandbox_name set."""
        registry, entry = self._run_and_register(tmp_path, target="sandbox")

        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].sandbox_name is not None
        assert entries[0].sandbox_name.startswith("claude-")
        assert entries[0].branch == "agent/my-repo"
        assert entries[0].worktree_path != ""
        # Registry file was created on disk
        assert (tmp_path / "test-registry.json").exists()

    def test_local_registration_no_sandbox_name(self, tmp_path: Path):
        """Local target registers with sandbox_name=None."""
        registry, entry = self._run_and_register(tmp_path, target="local")

        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].sandbox_name is None
        assert entries[0].branch == "agent/my-repo"

    def test_container_registration(self, tmp_path: Path):
        """Container target registers with container_name as sandbox_name."""
        registry, entry = self._run_and_register(tmp_path, target="container")

        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].sandbox_name is not None
        assert entries[0].sandbox_name.startswith("claude-")
        assert entries[0].branch == "agent/my-repo"

    def test_custom_sandbox_name_registration(self, tmp_path: Path):
        """Custom sandbox_name is preserved in registry entry."""
        registry, entry = self._run_and_register(
            tmp_path, target="sandbox", sandbox_name="my-custom"
        )

        entries = registry.list_all()
        assert len(entries) == 1
        assert entries[0].sandbox_name == "my-custom"
