"""Tests for the superintendent CLI (typer-based)."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from superintendent.backends.git import MockGitBackend
from superintendent.cli.main import (
    _branch_to_slug,
    app,
    auto_create_worktree,
    check_and_merge_stale,
    cleanup_all,
    cleanup_by_name,
    list_entries,
    resume_entry,
)
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry
from superintendent.state.token_store import DEFAULT_KEY, TokenStore

runner = CliRunner()


class TestRunCommand:
    """Test the 'run' subcommand."""

    def test_requires_mode_and_target(self) -> None:
        result = runner.invoke(app, ["run"])
        assert result.exit_code != 0

    def test_requires_task_flag(self) -> None:
        result = runner.invoke(
            app, ["run", "autonomous", "sandbox", "--repo", "/tmp/repo"]
        )
        assert result.exit_code != 0

    def test_requires_repo_flag(self) -> None:
        result = runner.invoke(
            app, ["run", "autonomous", "sandbox", "--task", "fix bug"]
        )
        assert result.exit_code != 0

    def test_mode_and_target_as_positional_args(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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
                ],
            )
            assert result.exit_code == 0
            planner_input = mock_planner.create_plan.call_args[0][0]
            assert planner_input.mode == "autonomous"
            assert planner_input.target == "sandbox"

    def test_interactive_local(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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

            result = runner.invoke(
                app,
                [
                    "run",
                    "interactive",
                    "local",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                ],
            )
            assert result.exit_code == 0
            planner_input = mock_planner.create_plan.call_args[0][0]
            assert planner_input.mode == "interactive"
            assert planner_input.target == "local"

    def test_all_flags(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "sandbox",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "implement feature",
                    "--branch",
                    "feature-branch",
                    "--context-file",
                    "ctx.md",
                    "--template-dockerfile",
                    "Dockerfile.custom",
                    "--force",
                    "--sandbox-name",
                    "my-sandbox",
                ],
            )
            assert result.exit_code == 0
            planner_input = mock_planner.create_plan.call_args[0][0]
            assert planner_input.repo == "/tmp/repo"
            assert planner_input.task == "implement feature"
            assert planner_input.branch == "feature-branch"
            assert planner_input.context_file == "ctx.md"
            assert planner_input.force is True
            assert planner_input.sandbox_name == "my-sandbox"

    def test_dry_run_skips_execution(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner = MagicMock()
            mock_plan = MagicMock()
            mock_plan.to_json.return_value = '{"steps": []}'
            mock_planner.create_plan.return_value = mock_plan
            mock_planner_cls.return_value = mock_planner

            mock_executor = MagicMock()
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
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0
            mock_executor.run.assert_not_called()
            assert "Dry Run" in result.output

    def test_failure_returns_nonzero_exit(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
        ):
            mock_planner = MagicMock()
            mock_plan = MagicMock()
            mock_planner.create_plan.return_value = mock_plan
            mock_planner_cls.return_value = mock_planner

            mock_executor = MagicMock()
            mock_result = MagicMock()
            mock_result.state.name = "FAILED"
            mock_result.failed_step = "validate_repo"
            mock_result.error = "Repo not found"
            mock_executor.run.return_value = mock_result
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
                ],
            )
            assert result.exit_code == 1

    def test_invalid_mode_rejected(self) -> None:
        result = runner.invoke(
            app,
            [
                "run",
                "invalid-mode",
                "sandbox",
                "--repo",
                "/tmp/repo",
                "--task",
                "fix",
            ],
        )
        assert result.exit_code != 0

    def test_invalid_target_rejected(self) -> None:
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "invalid-target",
                "--repo",
                "/tmp/repo",
                "--task",
                "fix",
            ],
        )
        assert result.exit_code != 0


class TestDangerouslySkipIsolation:
    """Test the --dangerously-skip-isolation safety gate."""

    def test_autonomous_local_fails_without_flag(self) -> None:
        result = runner.invoke(
            app,
            [
                "run",
                "autonomous",
                "local",
                "--repo",
                "/tmp/repo",
                "--task",
                "fix bug",
            ],
        )
        assert result.exit_code != 0
        assert "dangerously-skip-isolation" in result.output

    def test_autonomous_local_succeeds_with_flag(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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

            result = runner.invoke(
                app,
                [
                    "run",
                    "autonomous",
                    "local",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                    "--dangerously-skip-isolation",
                ],
            )
            assert result.exit_code == 0

    def test_interactive_local_does_not_need_flag(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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

            result = runner.invoke(
                app,
                [
                    "run",
                    "interactive",
                    "local",
                    "--repo",
                    "/tmp/repo",
                    "--task",
                    "fix bug",
                ],
            )
            assert result.exit_code == 0

    def test_autonomous_sandbox_does_not_need_flag(self) -> None:
        with (
            patch("superintendent.cli.main.Planner") as mock_planner_cls,
            patch("superintendent.cli.main.Executor") as mock_executor_cls,
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
                ],
            )
            assert result.exit_code == 0


class TestListCommand:
    """Test the 'list' subcommand."""

    def test_empty_registry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "No entries" in result.output

    def test_populated_registry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/worktree",
                sandbox_name="claude-test",
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["list"])
            assert result.exit_code == 0
            assert "test" in result.output
            assert "/tmp/repo" in result.output


class TestResumeCommand:
    """Test the 'resume' subcommand."""

    def test_requires_name(self) -> None:
        result = runner.invoke(app, ["resume"])
        assert result.exit_code != 0

    def test_resume_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path=str(wt_path),
                sandbox_name="claude-test",
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["resume", "--name", "test"])
            assert result.exit_code == 0
            assert "Resuming" in result.output

    def test_resume_not_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["resume", "--name", "nonexistent"])
            assert result.exit_code == 1

    def test_resume_by_branch(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="my-worktree",
                repo="/tmp/repo",
                branch="feature/cool-feature",
                worktree_path=str(wt_path),
                sandbox_name="claude-test",
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["resume", "--name", "feature/cool-feature"])
            assert result.exit_code == 0
            assert "Resuming" in result.output

    def test_resume_not_found_shows_available(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="existing",
                repo="/tmp/repo",
                branch="main",
                worktree_path=str(wt_path),
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["resume", "--name", "nonexistent"])
            assert result.exit_code == 1
            assert "searched by name and branch" in result.output
            assert "existing" in result.output


class TestCleanupCommand:
    """Test the 'cleanup' subcommand."""

    def test_requires_name_or_all(self) -> None:
        with patch(
            "superintendent.cli.main.get_default_registry",
            return_value=MagicMock(),
        ):
            result = runner.invoke(app, ["cleanup"])
            assert result.exit_code == 1

    def test_cleanup_by_name(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/worktree",
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["cleanup", "--name", "test"])
            assert result.exit_code == 0
            assert "Removed" in result.output

    def test_cleanup_all_dry_run(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        with patch(
            "superintendent.cli.main.get_default_registry", return_value=registry
        ):
            result = runner.invoke(app, ["cleanup", "--all", "--dry-run"])
            assert result.exit_code == 0
            assert "Would remove" in result.output
            # Entry should still exist
            assert registry.get("stale") is not None


class TestBusinessLogicFunctions:
    """Test business logic functions independently."""

    def test_list_entries_empty(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        assert list_entries(registry) == []

    def test_list_entries_populated(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/wt",
            )
        )
        entries = list_entries(registry)
        assert len(entries) == 1
        assert entries[0].name == "test"

    def test_resume_entry_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path=str(wt_path),
            )
        )
        entry = resume_entry("test", registry)
        assert entry is not None
        assert entry.name == "test"

    def test_resume_entry_not_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        assert resume_entry("nonexistent", registry) is None

    def test_resume_entry_missing_path(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        assert resume_entry("stale", registry) is None

    def test_resume_entry_by_branch(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="my-worktree",
                repo="/tmp/repo",
                branch="feature/cool",
                worktree_path=str(wt_path),
            )
        )
        # Look up by branch name, not entry name
        entry = resume_entry("feature/cool", registry)
        assert entry is not None
        assert entry.name == "my-worktree"

    def test_resume_entry_name_takes_precedence(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path1 = tmp_path / "wt1"
        wt_path1.mkdir()
        wt_path2 = tmp_path / "wt2"
        wt_path2.mkdir()
        registry.add(
            WorktreeEntry(
                name="name-match",
                repo="/tmp/repo1",
                branch="some-branch",
                worktree_path=str(wt_path1),
            )
        )
        registry.add(
            WorktreeEntry(
                name="other",
                repo="/tmp/repo2",
                branch="name-match",
                worktree_path=str(wt_path2),
            )
        )
        # "name-match" matches both a name and a branch; name should win
        entry = resume_entry("name-match", registry)
        assert entry is not None
        assert entry.repo == "/tmp/repo1"

    def test_cleanup_by_name_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/wt",
            )
        )
        assert cleanup_by_name("test", registry) is True
        assert registry.get("test") is None

    def test_cleanup_by_name_not_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        assert cleanup_by_name("nonexistent", registry) is False

    def test_cleanup_by_name_dry_run(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/wt",
            )
        )
        assert cleanup_by_name("test", registry, dry_run=True) is True
        assert registry.get("test") is not None

    def test_cleanup_all_stale(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        valid_path = tmp_path / "valid"
        valid_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="valid",
                repo="/tmp/repo2",
                branch="main",
                worktree_path=str(valid_path),
            )
        )
        removed = cleanup_all(registry)
        assert "stale" in removed
        assert "valid" not in removed

    def test_cleanup_all_dry_run(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        removed = cleanup_all(registry, dry_run=True)
        assert "stale" in removed
        assert registry.get("stale") is not None


class TestBranchToSlug:
    """Test the _branch_to_slug helper."""

    def test_simple_branch(self) -> None:
        assert _branch_to_slug("main") == "main"

    def test_slash_branch(self) -> None:
        assert _branch_to_slug("feature/my-feature") == "feature-my-feature"

    def test_multiple_slashes(self) -> None:
        assert _branch_to_slug("user/feature/thing") == "user-feature-thing"

    def test_special_chars(self) -> None:
        assert _branch_to_slug("fix@bug#123") == "fix-bug-123"

    def test_consecutive_dashes(self) -> None:
        assert _branch_to_slug("a//b") == "a-b"


class TestAutoCreateWorktree:
    """Test the auto_create_worktree function."""

    def test_creates_worktree_for_existing_branch(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        # Mock the worktrees dir so we don't touch real home
        worktrees_base = tmp_path / "worktrees"
        monkeypatch.setattr(
            "superintendent.cli.main._default_worktrees_dir",
            lambda: worktrees_base,
        )

        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            known_branches={"feature/cool"},
        )
        # Mock create_worktree_from_existing to also create the directory
        original = git.create_worktree_from_existing

        def mock_create(repo: Path, branch: str, target: Path) -> bool:
            target.mkdir(parents=True, exist_ok=True)
            return original(repo, branch, target)

        git.create_worktree_from_existing = mock_create

        entry = auto_create_worktree("feature/cool", str(repo_path), registry, git)
        assert entry is not None
        assert entry.branch == "feature/cool"
        assert entry.name == "feature-cool"
        assert "repo" in entry.worktree_path
        # Should be registered
        assert registry.get("feature-cool") is not None

    def test_returns_none_when_branch_missing(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()
        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            known_branches=set(),
        )
        entry = auto_create_worktree(
            "nonexistent-branch", str(repo_path), registry, git
        )
        assert entry is None

    def test_returns_none_when_repo_not_found(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        git = MockGitBackend()
        entry = auto_create_worktree("feature/x", "/no/such/repo", registry, git)
        assert entry is None

    def test_returns_none_when_worktree_creation_fails(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        worktrees_base = tmp_path / "worktrees"
        monkeypatch.setattr(
            "superintendent.cli.main._default_worktrees_dir",
            lambda: worktrees_base,
        )

        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            known_branches={"feature/x"},
            fail_on="create_worktree_from_existing",
        )
        entry = auto_create_worktree("feature/x", str(repo_path), registry, git)
        assert entry is None

    def test_registers_existing_worktree_dir(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """If the worktree directory already exists, just register it."""
        registry = WorktreeRegistry(tmp_path / "registry.json")
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        (repo_path / ".git").mkdir()

        worktrees_base = tmp_path / "worktrees"
        wt_dir = worktrees_base / "repo" / "feature-x"
        wt_dir.mkdir(parents=True)
        monkeypatch.setattr(
            "superintendent.cli.main._default_worktrees_dir",
            lambda: worktrees_base,
        )

        git = MockGitBackend(
            local_repos={str(repo_path): repo_path},
            known_branches={"feature/x"},
        )
        entry = auto_create_worktree("feature/x", str(repo_path), registry, git)
        assert entry is not None
        assert entry.worktree_path == str(wt_dir)
        # create_worktree_from_existing should NOT have been called
        assert len(git.worktrees) == 0


class TestCheckAndMergeStale:
    """Test the check_and_merge_stale function."""

    def test_not_stale_returns_none(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(branch_ages={"feature/x": 3.0})
        result = check_and_merge_stale(entry, git)
        assert result is None

    def test_stale_merges_successfully(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/old",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(branch_ages={"feature/old": 10.0})
        result = check_and_merge_stale(entry, git)
        assert result is not None
        assert "merged main successfully" in result
        assert "10 days stale" in result
        assert len(git.fetched) == 1
        assert len(git.merges) == 1

    def test_stale_merge_conflict(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/conflict",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(
            branch_ages={"feature/conflict": 14.0},
            fail_on="merge_branch",
        )
        result = check_and_merge_stale(entry, git)
        assert result is not None
        assert "conflicts" in result
        assert "auto-aborted" in result

    def test_stale_fetch_fails(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(
            branch_ages={"feature/x": 10.0},
            fail_on="fetch",
        )
        result = check_and_merge_stale(entry, git)
        assert result is not None
        assert "fetch failed" in result

    def test_unknown_branch_age_returns_none(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend()  # no branch_ages
        result = check_and_merge_stale(entry, git)
        assert result is None

    def test_missing_worktree_path_returns_none(self) -> None:
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path="/nonexistent",
        )
        git = MockGitBackend(branch_ages={"feature/x": 10.0})
        result = check_and_merge_stale(entry, git)
        assert result is None

    def test_custom_stale_threshold(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(branch_ages={"feature/x": 3.0})
        # With default threshold (7 days), 3 days should NOT be stale
        assert check_and_merge_stale(entry, git) is None
        # With threshold of 2 days, 3 days IS stale
        result = check_and_merge_stale(entry, git, stale_days=2.0)
        assert result is not None
        assert "merged main successfully" in result

    def test_uses_detected_default_branch(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="wt",
            repo="/repo",
            branch="feature/x",
            worktree_path=str(wt_path),
        )
        git = MockGitBackend(
            branch_ages={"feature/x": 10.0},
            default_branch="develop",
        )
        result = check_and_merge_stale(entry, git)
        assert result is not None
        assert "merged develop successfully" in result
        # Should merge origin/develop, not origin/main
        assert git.merges[0][1] == "origin/develop"


class TestTokenSetDefault:
    """Test the 'token set-default' subcommand."""

    def test_success(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "brendanwhit\n"
        mock_result.stderr = ""

        with (
            patch(
                "superintendent.cli.main.get_default_token_store", return_value=store
            ),
            patch("superintendent.cli.main.subprocess.run", return_value=mock_result),
        ):
            result = runner.invoke(
                app, ["token", "set-default", "--token", "ghp_test123"]
            )
            assert result.exit_code == 0
            assert "brendanwhit" in result.output
            default = store.get(DEFAULT_KEY)
            assert default is not None
            assert default.token == "ghp_test123"
            assert default.github_user == "brendanwhit"

    def test_invalid_token(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "401 Unauthorized"

        with (
            patch(
                "superintendent.cli.main.get_default_token_store", return_value=store
            ),
            patch("superintendent.cli.main.subprocess.run", return_value=mock_result),
        ):
            result = runner.invoke(app, ["token", "set-default", "--token", "ghp_bad"])
            assert result.exit_code == 1
            assert "validation failed" in result.output
            assert store.get(DEFAULT_KEY) is None

    def test_gh_not_found(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")

        with (
            patch(
                "superintendent.cli.main.get_default_token_store", return_value=store
            ),
            patch(
                "superintendent.cli.main.subprocess.run",
                side_effect=FileNotFoundError("gh not found"),
            ),
        ):
            result = runner.invoke(app, ["token", "set-default", "--token", "ghp_test"])
            assert result.exit_code == 1
            assert "could not validate" in result.output


class TestTokenRemoveDefault:
    """Test the 'token remove-default' subcommand."""

    def test_success(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_test123", github_user="brendanwhit")

        with patch(
            "superintendent.cli.main.get_default_token_store", return_value=store
        ):
            result = runner.invoke(app, ["token", "remove-default"])
            assert result.exit_code == 0
            assert "Default token removed" in result.output
            assert store.get(DEFAULT_KEY) is None

    def test_none_configured(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")

        with patch(
            "superintendent.cli.main.get_default_token_store", return_value=store
        ):
            result = runner.invoke(app, ["token", "remove-default"])
            assert result.exit_code == 1
            assert "No default token configured" in result.output


class TestTokenStatusWithDefault:
    """Test that 'token status' shows default token info."""

    def test_shows_default_and_repos(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default_long_token", github_user="brendanwhit")
        store.add("org/repo", "ghp_repo_long_token", permissions=["repo"])

        with patch(
            "superintendent.cli.main.get_default_token_store", return_value=store
        ):
            result = runner.invoke(app, ["token", "status"])
            assert result.exit_code == 0
            assert "Default:" in result.output
            assert "brendanwhit" in result.output
            assert "org/repo" in result.output

    def test_shows_only_default(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default_long_token", github_user="brendanwhit")

        with patch(
            "superintendent.cli.main.get_default_token_store", return_value=store
        ):
            result = runner.invoke(app, ["token", "status"])
            assert result.exit_code == 0
            assert "Default:" in result.output
            assert "No tokens stored" not in result.output
