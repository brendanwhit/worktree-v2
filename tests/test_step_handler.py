"""Tests for step handler: dispatch, git, docker, auth, terminal handlers."""

from superintendent.backends.auth import MockAuthBackend
from superintendent.backends.docker import MockDockerBackend
from superintendent.backends.factory import Backends
from superintendent.backends.git import MockGitBackend
from superintendent.backends.terminal import MockTerminalBackend
from superintendent.orchestrator.executor import StepHandler
from superintendent.orchestrator.models import WorkflowStep
from superintendent.orchestrator.step_handler import ExecutionContext, RealStepHandler
from superintendent.state.token_store import TokenStore


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
            "validate_auth",
            "create_worktree",
            "prepare_template",
            "prepare_sandbox",
            "prepare_container",
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

    def test_standalone_calls_clone_for_sandbox(self, tmp_path):
        """With standalone=True, calls git.clone_for_sandbox instead of create_worktree."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend()
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test", "standalone": True},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(git.sandbox_clones) == 1
        assert git.sandbox_clones[0][0] == repo_path
        assert git.sandbox_clones[0][2] == "agent/test"
        # Regular worktree should NOT be called
        assert len(git.worktrees) == 0

    def test_standalone_false_calls_create_worktree(self, tmp_path):
        """With standalone=False (default), calls git.create_worktree."""
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
        assert len(git.sandbox_clones) == 0

    def test_standalone_failure(self, tmp_path):
        """When clone_for_sandbox fails with standalone=True, return failure."""
        git = MockGitBackend(fail_on="clone_for_sandbox")
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test", "standalone": True},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is False
        assert "clone for sandbox" in result.message

    def test_reuse_existing_worktree_and_branch(self, tmp_path, monkeypatch):
        """Scenario 1: worktree path + branch both exist — reuse without creating."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend(known_branches={"agent/test"})
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        # Make the worktree path exist
        worktree_dir = tmp_path / "worktrees" / "test" / "agent-test"
        worktree_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "superintendent.orchestrator.step_handler.default_worktrees_dir",
            lambda: tmp_path / "worktrees",
        )

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert result.data["worktree_path"] == str(worktree_dir)
        # Should NOT have called create_worktree or create_worktree_from_existing
        assert len(git.worktrees) == 0

    def test_attach_existing_branch_no_worktree(self, tmp_path, monkeypatch):
        """Scenario 2: branch exists but no worktree — attach via create_worktree_from_existing."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend(known_branches={"agent/test"})
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        monkeypatch.setattr(
            "superintendent.orchestrator.step_handler.default_worktrees_dir",
            lambda: tmp_path / "worktrees",
        )

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        # Should have called create_worktree_from_existing (recorded in worktrees list)
        assert len(git.worktrees) == 1
        assert git.worktrees[0][1] == "agent/test"

    def test_attach_existing_branch_failure(self, tmp_path, monkeypatch):
        """Scenario 2 failure: branch exists, create_worktree_from_existing fails."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend(
            known_branches={"agent/test"},
            fail_on="create_worktree_from_existing",
        )
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        monkeypatch.setattr(
            "superintendent.orchestrator.step_handler.default_worktrees_dir",
            lambda: tmp_path / "worktrees",
        )

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test"},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is False

    def test_create_new_branch_and_worktree(self, tmp_path):
        """Scenario 3: neither branch nor worktree exist — create new."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend()  # no known_branches
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

    def test_force_removes_and_recreates(self, tmp_path, monkeypatch):
        """--force: removes existing worktree and recreates from scratch."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend(known_branches={"agent/test"})
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        # Make the worktree path exist
        worktree_dir = tmp_path / "worktrees" / "test" / "agent-test"
        worktree_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "superintendent.orchestrator.step_handler.default_worktrees_dir",
            lambda: tmp_path / "worktrees",
        )

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test", "force": True},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        # Should have called create_worktree (new branch), not reused
        assert len(git.worktrees) == 1

    def test_force_without_existing_worktree_creates_new(self, tmp_path):
        """--force with no existing worktree behaves like scenario 3."""
        repo_path = tmp_path / "repo"
        git = MockGitBackend()
        ctx = ExecutionContext(backends=_mock_backends(git=git))
        ctx.step_outputs["validate_repo"] = {"repo_path": str(repo_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="create_worktree",
            action="create_worktree",
            params={"branch": "agent/test", "repo_name": "test", "force": True},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(git.worktrees) == 1


# ---------------------------------------------------------------------------
# Validate auth handler
# ---------------------------------------------------------------------------


class TestValidateAuthHandler:
    def _empty_token_store(self, tmp_path):
        """Create an empty token store for isolated testing."""
        return TokenStore(path=tmp_path / "empty-tokens.json")

    def test_dry_run_succeeds(self, tmp_path):
        """In dry-run mode, validate_auth always succeeds."""
        ctx = ExecutionContext(
            backends=_mock_backends(),
            token_store=self._empty_token_store(tmp_path),
            dry_run=True,
        )
        handler = RealStepHandler(ctx)
        step = WorkflowStep(
            id="validate_auth",
            action="validate_auth",
            params={},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)
        assert result.success is True

    def test_succeeds_with_default_token(self, tmp_path):
        """When a default token exists, validate_auth succeeds via fallback."""
        store = TokenStore(path=tmp_path / "tokens.json")
        store.add("_default", "ghp_test123", github_user="testuser")
        ctx = ExecutionContext(
            backends=_mock_backends(),
            token_store=store,
        )
        handler = RealStepHandler(ctx)
        step = WorkflowStep(
            id="validate_auth",
            action="validate_auth",
            params={},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)
        assert result.success is True

    def test_fails_with_no_token(self, tmp_path, monkeypatch):
        """With no token available, validate_auth fails with helpful message."""
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)

        store = self._empty_token_store(tmp_path)
        ctx = ExecutionContext(
            backends=_mock_backends(),
            token_store=store,
        )
        handler = RealStepHandler(ctx)

        # Mock subprocess to make gh auth token fail
        import subprocess as sp

        original_run = sp.run

        def mock_run(cmd, **kwargs):
            if cmd[:3] == ["gh", "auth", "token"]:
                result = type(
                    "Result", (), {"returncode": 1, "stdout": "", "stderr": ""}
                )()
                return result
            return original_run(cmd, **kwargs)

        monkeypatch.setattr(sp, "run", mock_run)

        step = WorkflowStep(
            id="validate_auth",
            action="validate_auth",
            params={},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)
        assert result.success is False
        assert "No GitHub token" in result.message

    def test_succeeds_with_env_token(self, tmp_path, monkeypatch):
        """When GH_TOKEN env var is set, validate_auth succeeds."""
        monkeypatch.setenv("GH_TOKEN", "ghp_env_token")
        store = self._empty_token_store(tmp_path)
        ctx = ExecutionContext(
            backends=_mock_backends(),
            token_store=store,
        )
        handler = RealStepHandler(ctx)
        step = WorkflowStep(
            id="validate_auth",
            action="validate_auth",
            params={},
            depends_on=["validate_repo"],
        )
        result = handler.execute(step)
        assert result.success is True


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
        """With force=True, stops and removes existing sandbox before recreating."""
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
        assert len(docker.removed) == 1
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

    def test_passes_template_from_prepare_template_output(self, tmp_path):
        """When prepare_template output exists, template is passed to create_sandbox."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["prepare_template"] = {"template": "supt-sandbox:abc123"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_sandbox",
            action="prepare_sandbox",
            params={"sandbox_name": "claude-test", "force": False},
            depends_on=["prepare_template"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert docker.created[0][2] == "supt-sandbox:abc123"


# ---------------------------------------------------------------------------
# Template step handler
# ---------------------------------------------------------------------------


class TestPrepareTemplateHandler:
    def test_builds_template_on_cache_miss(self):
        """When template doesn't exist, builds it and returns tag."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_template",
            action="prepare_template",
            params={},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert "template" in result.data
        assert result.data["template"].startswith("supt-sandbox:")
        assert len(docker.templates_built) == 1
        assert docker.templates_built[0][1] == result.data["template"]

    def test_skips_build_on_cache_hit(self):
        """When template already exists, skip the build."""
        import hashlib

        from superintendent.orchestrator.step_handler import SANDBOX_BASE_IMAGE

        dockerfile = (
            "FROM dolthub/dolt:latest AS dolt-binary\n"
            f"FROM {SANDBOX_BASE_IMAGE}\n"
            "COPY --from=dolt-binary /usr/local/bin/dolt /usr/local/bin/dolt\n"
            "RUN npm install -g @beads/bd\n"
        )
        tag = "supt-sandbox:" + hashlib.sha256(dockerfile.encode()).hexdigest()[:12]

        docker = MockDockerBackend(existing_templates={tag})
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_template",
            action="prepare_template",
            params={},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert result.data["template"] == tag
        assert len(docker.templates_built) == 0  # no build needed

    def test_template_dockerfile_includes_dolt(self):
        """Template Dockerfile includes Dolt binary via multi-stage copy."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_template",
            action="prepare_template",
            params={},
            depends_on=["create_worktree"],
        )
        handler.execute(step)

        assert len(docker.templates_built) == 1
        dockerfile_content = docker.templates_built[0][0]
        assert "dolthub/dolt" in dockerfile_content
        assert "COPY --from=" in dockerfile_content
        assert "/usr/local/bin/dolt" in dockerfile_content

    def test_build_failure_returns_error(self):
        """When build_template fails, return failure result."""
        docker = MockDockerBackend(fail_on="build_template")
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_template",
            action="prepare_template",
            params={},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is False
        assert "Failed to build template" in result.message

    def test_template_tag_is_deterministic(self):
        """Same Dockerfile content produces the same tag."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_template",
            action="prepare_template",
            params={},
            depends_on=["create_worktree"],
        )
        result1 = handler.execute(step)

        docker2 = MockDockerBackend()
        ctx2 = ExecutionContext(backends=_mock_backends(docker=docker2))
        handler2 = RealStepHandler(ctx2)
        result2 = handler2.execute(step)

        assert result1.data["template"] == result2.data["template"]


class TestPrepareContainerHandler:
    def test_creates_container(self, tmp_path):
        """Creates a docker container with the worktree path as workspace."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_container",
            action="prepare_container",
            params={"container_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.containers_created) == 1
        assert docker.containers_created[0][0] == "claude-test"
        # Sandbox methods should NOT be called
        assert len(docker.created) == 0

    def test_force_recreates_existing(self, tmp_path):
        """With force=True, stops existing container before recreating."""
        docker = MockDockerBackend(containers={"claude-test": True})
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_container",
            action="prepare_container",
            params={"container_name": "claude-test", "force": True},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.containers_stopped) == 1
        assert len(docker.containers_created) == 1
        # Sandbox methods should NOT be called
        assert len(docker.stopped) == 0

    def test_container_creation_fails(self, tmp_path):
        """When docker.create_container fails, return failure."""
        docker = MockDockerBackend(fail_on="create_container")
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_container",
            action="prepare_container",
            params={"container_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is False

    def test_outputs_container_name(self, tmp_path):
        """Successful prepare_container saves container_name to context."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_container",
            action="prepare_container",
            params={"container_name": "claude-test", "force": False},
            depends_on=["create_worktree"],
        )
        handler.execute(step)

        assert ctx.step_outputs["prepare_container"]["container_name"] == "claude-test"

    def test_missing_worktree_path_fails(self):
        """If create_worktree output is missing, fail gracefully."""
        ctx = ExecutionContext(backends=_mock_backends())
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="prepare_container",
            action="prepare_container",
            params={"container_name": "claude-test", "force": False},
        )
        result = handler.execute(step)

        assert result.success is False


# ---------------------------------------------------------------------------
# Task 20: Auth and terminal step handlers
# ---------------------------------------------------------------------------


class TestAuthenticateHandler:
    def _empty_token_store(self, tmp_path):
        """Create an empty token store for isolated testing."""
        return TokenStore(path=tmp_path / "empty-tokens.json")

    def test_sets_up_auth_with_sandbox(self, tmp_path):
        """Auth succeeds for sandbox (via setup_git_auth or inject_token)."""
        auth = MockAuthBackend()
        ctx = ExecutionContext(
            backends=_mock_backends(auth=auth),
            token_store=self._empty_token_store(tmp_path),
        )
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="authenticate",
            action="authenticate",
            params={"sandbox_name": "claude-test"},
            depends_on=["prepare_sandbox"],
        )
        result = handler.execute(step)

        assert result.success is True
        # Either setup_git_auth or inject_token was called depending on host gh auth
        assert len(auth.git_auths) + len(auth.tokens_injected) >= 1

    def test_sets_up_auth_with_container(self, tmp_path):
        """Auth succeeds for container (via setup_git_auth or inject_token)."""
        auth = MockAuthBackend()
        ctx = ExecutionContext(
            backends=_mock_backends(auth=auth),
            token_store=self._empty_token_store(tmp_path),
        )
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="authenticate",
            action="authenticate",
            params={"container_name": "claude-test"},
            depends_on=["prepare_container"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(auth.git_auths) + len(auth.tokens_injected) >= 1

    def test_inject_token_when_token_available(self, tmp_path):
        """When a token is in the store, inject_token is called."""
        auth = MockAuthBackend()
        store = TokenStore(path=tmp_path / "tokens.json")
        store.add("_default", "ghp_test123", github_user="testuser")
        ctx = ExecutionContext(backends=_mock_backends(auth=auth), token_store=store)
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="authenticate",
            action="authenticate",
            params={"sandbox_name": "claude-test"},
            depends_on=["prepare_sandbox"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(auth.tokens_injected) == 1
        assert auth.tokens_injected[0] == ("claude-test", "ghp_test123")

    def test_auth_failure(self, tmp_path):
        """When inject_token fails, return failure."""
        auth = MockAuthBackend(fail_on="inject_token")
        store = TokenStore(path=tmp_path / "tokens.json")
        store.add("_default", "ghp_test123", github_user="testuser")
        ctx = ExecutionContext(backends=_mock_backends(auth=auth), token_store=store)
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

    def test_inits_beads_for_sandbox(self, tmp_path):
        """For sandbox targets, runs bd init --sandbox (auto-starts Dolt)."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert len(docker.executed) == 1
        exec_cmds = [cmd for _, cmd in docker.executed]
        assert any("bd init" in cmd and "--sandbox" in cmd for cmd in exec_cmds)

    def test_beads_init_includes_skip_hooks_and_prefix(self, tmp_path):
        """bd init command includes --skip-hooks and -p flags."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        handler.execute(step)

        exec_cmds = [cmd for _, cmd in docker.executed]
        init_cmd = next(c for c in exec_cmds if "bd init" in c)
        assert "--skip-hooks" in init_cmd
        assert "-p" in init_cmd
        assert "my_repo" in init_cmd
        assert "--database" in init_cmd
        assert "-q" in init_cmd

    def test_beads_init_sanitizes_repo_name(self, tmp_path):
        """Dots in repo name are replaced with underscores for Dolt database name."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/prview.nvim"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-prview"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        handler.execute(step)

        exec_cmds = [cmd for _, cmd in docker.executed]
        init_cmd = next(c for c in exec_cmds if "bd init" in c)
        assert "prview_nvim" in init_cmd
        assert "prview.nvim" not in init_cmd

    def test_beads_init_failure_returns_error(self, tmp_path):
        """If bd init fails, the step returns failure."""
        docker = MockDockerBackend(fail_on="exec_in_sandbox")
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_sandbox"] = {"sandbox_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is False
        assert "beads" in result.message.lower() or "dolt" in result.message.lower()

    def test_beads_init_for_container(self, tmp_path):
        """Container targets also get beads initialization."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        ctx.step_outputs["validate_repo"] = {"repo_path": "/home/user/my-repo"}
        ctx.step_outputs["prepare_container"] = {"container_name": "claude-my-repo"}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["authenticate"],
        )
        result = handler.execute(step)

        assert result.success is True
        exec_cmds = [cmd for _, cmd in docker.executed]
        assert any("bd init" in cmd for cmd in exec_cmds)

    def test_no_beads_init_for_local(self, tmp_path):
        """Local target (no sandbox/container output) does not init beads."""
        ctx = ExecutionContext(backends=_mock_backends())
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="initialize_state",
            action="initialize_state",
            params={"task": "test task", "context_file": None},
            depends_on=["create_worktree"],
        )
        result = handler.execute(step)

        assert result.success is True
        assert not (tmp_path / ".beads").exists()


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

    def test_spawns_in_container(self, tmp_path):
        """When container_name is in params, uses docker.run_agent."""
        docker = MockDockerBackend()
        ctx = ExecutionContext(backends=_mock_backends(docker=docker))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"container_name": "claude-test", "task": "do stuff"},
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
        cmd, _ = terminal.spawned[0]
        assert "claude '" in cmd

    def test_local_autonomous_includes_skip_permissions(self, tmp_path):
        """Autonomous local agents MUST include --dangerously-skip-permissions."""
        terminal = MockTerminalBackend()
        ctx = ExecutionContext(backends=_mock_backends(terminal=terminal))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"task": "do stuff", "mode": "autonomous"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is True
        cmd, _ = terminal.spawned[0]
        assert "--dangerously-skip-permissions" in cmd

    def test_local_interactive_excludes_skip_permissions(self, tmp_path):
        """Interactive local agents must NOT include --dangerously-skip-permissions."""
        terminal = MockTerminalBackend()
        ctx = ExecutionContext(backends=_mock_backends(terminal=terminal))
        ctx.step_outputs["create_worktree"] = {"worktree_path": str(tmp_path)}
        handler = RealStepHandler(ctx)

        step = WorkflowStep(
            id="start_agent",
            action="start_agent",
            params={"task": "do stuff", "mode": "interactive"},
            depends_on=["initialize_state"],
        )
        result = handler.execute(step)

        assert result.success is True
        cmd, _ = terminal.spawned[0]
        assert "--dangerously-skip-permissions" not in cmd

    def test_local_agent_writes_lifecycle_markers(self, tmp_path):
        """Local agents with .ralph/ dir get lifecycle marker wrapping."""
        ralph_dir = tmp_path / ".ralph"
        ralph_dir.mkdir()

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
        cmd, _ = terminal.spawned[0]
        assert "agent-started" in cmd
        assert "agent-done" in cmd
        assert "agent-exit-code" in cmd

    def test_local_agent_no_markers_without_ralph(self, tmp_path):
        """Local agents without .ralph/ dir skip lifecycle wrapping."""
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
        cmd, _ = terminal.spawned[0]
        assert "agent-started" not in cmd

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
        from superintendent.orchestrator.executor import Executor
        from superintendent.orchestrator.planner import Planner, PlannerInput

        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        store = TokenStore(path=tmp_path / "tokens.json")
        store.add("_default", "ghp_test", github_user="test")
        ctx = ExecutionContext(
            backends=_mock_backends(git=git, docker=docker),
            token_store=store,
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="test task")
        )
        result = executor.run(plan)

        assert result.error is None, f"Unexpected error: {result.error}"
        assert len(result.completed_steps) == 8
        assert result.failed_step is None

    def test_container_plan_with_real_handler(self, tmp_path):
        """A complete container plan succeeds with mock backends."""
        from superintendent.orchestrator.executor import Executor
        from superintendent.orchestrator.planner import Planner, PlannerInput

        repo_path = tmp_path / "my-repo"
        git = MockGitBackend(local_repos={str(repo_path): repo_path})
        docker = MockDockerBackend()
        store = TokenStore(path=tmp_path / "tokens.json")
        store.add("_default", "ghp_test", github_user="test")
        ctx = ExecutionContext(
            backends=_mock_backends(git=git, docker=docker),
            token_store=store,
        )
        handler = RealStepHandler(ctx)
        executor = Executor(handler=handler)

        plan = Planner().create_plan(
            PlannerInput(repo=str(repo_path), task="test task", target="container")
        )
        result = executor.run(plan)

        assert result.error is None, f"Unexpected error: {result.error}"
        assert len(result.completed_steps) == 8
        assert "prepare_container" in result.completed_steps
        assert "prepare_sandbox" not in result.completed_steps
        assert result.failed_step is None

    def test_local_plan_with_real_handler(self, tmp_path):
        """A complete local plan succeeds with mock backends."""
        from superintendent.orchestrator.executor import Executor
        from superintendent.orchestrator.planner import Planner, PlannerInput

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
