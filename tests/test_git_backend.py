"""Tests for GitBackend (Protocol, Mock, DryRun, Real)."""

from pathlib import Path

import pytest

from superintendent.backends.git import (
    DryRunGitBackend,
    GitBackend,
    MockGitBackend,
    RealGitBackend,
    WorktreeInfo,
    _extract_repo_name,
    _find_local_clone,
    _is_git_repo,
)


class TestGitBackendProtocol:
    """Verify all implementations satisfy the GitBackend protocol."""

    def test_real_satisfies_protocol(self):
        assert isinstance(RealGitBackend(), GitBackend)

    def test_mock_satisfies_protocol(self):
        assert isinstance(MockGitBackend(), GitBackend)

    def test_dryrun_satisfies_protocol(self):
        assert isinstance(DryRunGitBackend(), GitBackend)


class TestMockGitBackend:
    """Test MockGitBackend recording and failure injection."""

    def test_clone_records_call(self):
        backend = MockGitBackend()
        result = backend.clone("https://github.com/test/repo", Path("/tmp/repo"))
        assert result is True
        assert len(backend.cloned) == 1
        assert backend.cloned[0] == ("https://github.com/test/repo", Path("/tmp/repo"))

    def test_clone_failure(self):
        backend = MockGitBackend(fail_on="clone")
        result = backend.clone("https://github.com/test/repo", Path("/tmp/repo"))
        assert result is False
        assert len(backend.cloned) == 0

    def test_create_worktree_records_call(self):
        backend = MockGitBackend()
        result = backend.create_worktree(
            Path("/repo"), "feature-branch", Path("/worktree")
        )
        assert result is True
        assert len(backend.worktrees) == 1
        assert backend.worktrees[0] == (
            Path("/repo"),
            "feature-branch",
            Path("/worktree"),
        )

    def test_create_worktree_failure(self):
        backend = MockGitBackend(fail_on="create_worktree")
        result = backend.create_worktree(
            Path("/repo"), "feature-branch", Path("/worktree")
        )
        assert result is False

    def test_fetch_records_call(self):
        backend = MockGitBackend()
        result = backend.fetch(Path("/repo"))
        assert result is True
        assert backend.fetched == [Path("/repo")]

    def test_fetch_failure(self):
        backend = MockGitBackend(fail_on="fetch")
        result = backend.fetch(Path("/repo"))
        assert result is False

    def test_checkout_records_call(self):
        backend = MockGitBackend()
        result = backend.checkout(Path("/repo"), "main")
        assert result is True
        assert backend.checkouts == [(Path("/repo"), "main")]

    def test_checkout_failure(self):
        backend = MockGitBackend(fail_on="checkout")
        result = backend.checkout(Path("/repo"), "main")
        assert result is False

    def test_ensure_local_with_known_repo(self):
        backend = MockGitBackend(local_repos={"/path/to/repo": Path("/path/to/repo")})
        result = backend.ensure_local("/path/to/repo")
        assert result == Path("/path/to/repo")

    def test_ensure_local_unknown_repo(self):
        backend = MockGitBackend()
        result = backend.ensure_local("/unknown")
        assert result is None

    def test_ensure_local_none(self):
        backend = MockGitBackend()
        result = backend.ensure_local(None)
        assert result is None

    def test_ensure_local_failure(self):
        backend = MockGitBackend(
            fail_on="ensure_local",
            local_repos={"/repo": Path("/repo")},
        )
        result = backend.ensure_local("/repo")
        assert result is None

    def test_multiple_operations_recorded(self):
        backend = MockGitBackend()
        backend.clone("url1", Path("/p1"))
        backend.clone("url2", Path("/p2"))
        backend.fetch(Path("/p1"))
        assert len(backend.cloned) == 2
        assert len(backend.fetched) == 1

    def test_list_worktrees(self):
        wt = WorktreeInfo(path=Path("/wt"), branch="main")
        backend = MockGitBackend(known_worktrees=[wt])
        result = backend.list_worktrees(Path("/repo"))
        assert len(result) == 1
        assert result[0].branch == "main"

    def test_list_worktrees_failure(self):
        backend = MockGitBackend(fail_on="list_worktrees")
        assert backend.list_worktrees(Path("/repo")) == []

    def test_branch_exists_true(self):
        backend = MockGitBackend(known_branches={"feature/x"})
        assert backend.branch_exists(Path("/repo"), "feature/x") is True

    def test_branch_exists_false(self):
        backend = MockGitBackend()
        assert backend.branch_exists(Path("/repo"), "no-branch") is False

    def test_branch_exists_failure(self):
        backend = MockGitBackend(fail_on="branch_exists", known_branches={"feature/x"})
        assert backend.branch_exists(Path("/repo"), "feature/x") is False

    def test_create_worktree_from_existing(self):
        backend = MockGitBackend()
        result = backend.create_worktree_from_existing(
            Path("/repo"), "feature/x", Path("/wt")
        )
        assert result is True
        assert len(backend.worktrees) == 1

    def test_create_worktree_from_existing_failure(self):
        backend = MockGitBackend(fail_on="create_worktree_from_existing")
        result = backend.create_worktree_from_existing(
            Path("/repo"), "feature/x", Path("/wt")
        )
        assert result is False

    def test_get_branch_age_days(self):
        backend = MockGitBackend(branch_ages={"main": 10.5})
        result = backend.get_branch_age_days(Path("/repo"), "main")
        assert result == 10.5

    def test_get_branch_age_days_unknown(self):
        backend = MockGitBackend()
        result = backend.get_branch_age_days(Path("/repo"), "main")
        assert result is None

    def test_get_branch_age_days_failure(self):
        backend = MockGitBackend(
            fail_on="get_branch_age_days", branch_ages={"main": 5.0}
        )
        assert backend.get_branch_age_days(Path("/repo"), "main") is None

    def test_merge_branch(self):
        backend = MockGitBackend()
        result = backend.merge_branch(Path("/repo"), "main")
        assert result is True
        assert backend.merges == [(Path("/repo"), "main")]

    def test_merge_branch_failure(self):
        backend = MockGitBackend(fail_on="merge_branch")
        assert backend.merge_branch(Path("/repo"), "main") is False
        assert backend.merges == []

    def test_get_default_branch(self):
        backend = MockGitBackend(default_branch="master")
        assert backend.get_default_branch(Path("/repo")) == "master"

    def test_get_default_branch_default(self):
        backend = MockGitBackend()
        assert backend.get_default_branch(Path("/repo")) == "main"


class TestDryRunGitBackend:
    """Test DryRunGitBackend command recording."""

    def test_clone_records_command(self):
        backend = DryRunGitBackend()
        result = backend.clone("https://github.com/test/repo", Path("/tmp/repo"))
        assert result is True
        assert len(backend.commands) == 1
        assert "git clone" in backend.commands[0]
        assert "https://github.com/test/repo" in backend.commands[0]

    def test_create_worktree_records_command(self):
        backend = DryRunGitBackend()
        result = backend.create_worktree(
            Path("/repo"), "feature-branch", Path("/worktree")
        )
        assert result is True
        assert "worktree add" in backend.commands[0]
        assert "feature-branch" in backend.commands[0]

    def test_fetch_records_command(self):
        backend = DryRunGitBackend()
        result = backend.fetch(Path("/repo"))
        assert result is True
        assert "fetch --all" in backend.commands[0]

    def test_checkout_records_command(self):
        backend = DryRunGitBackend()
        result = backend.checkout(Path("/repo"), "main")
        assert result is True
        assert "checkout main" in backend.commands[0]

    def test_ensure_local_records_command(self):
        backend = DryRunGitBackend()
        result = backend.ensure_local("/some/repo")
        assert result == Path("/some/repo")
        assert len(backend.commands) == 1

    def test_ensure_local_none(self):
        backend = DryRunGitBackend()
        result = backend.ensure_local(None)
        assert result is None
        assert len(backend.commands) == 0

    def test_all_operations_always_succeed(self):
        backend = DryRunGitBackend()
        assert backend.clone("url", Path("/p")) is True
        assert backend.create_worktree(Path("/r"), "b", Path("/w")) is True
        assert backend.fetch(Path("/r")) is True
        assert backend.checkout(Path("/r"), "b") is True
        assert len(backend.commands) == 4

    def test_commands_accumulate(self):
        backend = DryRunGitBackend()
        backend.clone("url", Path("/p"))
        backend.fetch(Path("/r"))
        backend.checkout(Path("/r"), "main")
        assert len(backend.commands) == 3

    def test_list_worktrees_records_command(self):
        backend = DryRunGitBackend()
        result = backend.list_worktrees(Path("/repo"))
        assert result == []
        assert "worktree list" in backend.commands[0]

    def test_branch_exists_records_command(self):
        backend = DryRunGitBackend()
        result = backend.branch_exists(Path("/repo"), "feature/x")
        assert result is True
        assert "rev-parse" in backend.commands[0]
        assert "feature/x" in backend.commands[0]

    def test_create_worktree_from_existing_records_command(self):
        backend = DryRunGitBackend()
        result = backend.create_worktree_from_existing(
            Path("/repo"), "feature/x", Path("/wt")
        )
        assert result is True
        assert "worktree add" in backend.commands[0]
        assert "feature/x" in backend.commands[0]

    def test_get_branch_age_days_records_command(self):
        backend = DryRunGitBackend()
        result = backend.get_branch_age_days(Path("/repo"), "main")
        assert result == 0.0
        assert "log -1" in backend.commands[0]
        assert "main" in backend.commands[0]

    def test_merge_branch_records_command(self):
        backend = DryRunGitBackend()
        result = backend.merge_branch(Path("/repo"), "origin/main")
        assert result is True
        assert "merge origin/main" in backend.commands[0]

    def test_get_default_branch_records_command(self):
        backend = DryRunGitBackend()
        result = backend.get_default_branch(Path("/repo"))
        assert result == "main"
        assert "symbolic-ref" in backend.commands[0]


class TestRealGitBackend:
    """Test RealGitBackend with actual git operations."""

    def test_ensure_local_with_valid_repo(self, tmp_path):
        # Create a fake git repo
        git_dir = tmp_path / "repo"
        git_dir.mkdir()
        (git_dir / ".git").mkdir()
        backend = RealGitBackend()
        result = backend.ensure_local(str(git_dir))
        assert result == git_dir

    def test_ensure_local_with_nonexistent_path(self):
        backend = RealGitBackend()
        result = backend.ensure_local("/nonexistent/path")
        assert result is None

    def test_ensure_local_with_url_no_local_clone(self):
        backend = RealGitBackend()
        result = backend.ensure_local("https://github.com/test/repo")
        assert result is None

    def test_ensure_local_with_ssh_url_no_local_clone(self):
        backend = RealGitBackend()
        result = backend.ensure_local("git@github.com:test/repo.git")
        assert result is None

    def test_ensure_local_finds_clone_from_url(self, tmp_path, monkeypatch):
        """When a URL is given, ensure_local parses the repo name and checks CWD."""
        # Create a fake local clone matching the repo name
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        monkeypatch.chdir(tmp_path)
        backend = RealGitBackend()
        result = backend.ensure_local("https://github.com/user/my-repo.git")
        assert result == repo_dir

    def test_ensure_local_url_no_match_in_cwd(self, tmp_path, monkeypatch):
        """URL parsing works but no matching directory exists in CWD."""
        monkeypatch.chdir(tmp_path)
        backend = RealGitBackend()
        result = backend.ensure_local("https://github.com/user/nonexistent")
        assert result is None

    def test_ensure_local_none(self):
        backend = RealGitBackend()
        result = backend.ensure_local(None)
        assert result is None

    def test_ensure_local_non_git_dir(self, tmp_path):
        # Directory exists but no .git
        backend = RealGitBackend()
        result = backend.ensure_local(str(tmp_path))
        assert result is None

    @pytest.mark.integration
    def test_clone_and_worktree(self, tmp_path):
        """Integration test: clone a repo and create a worktree."""
        repo_path = tmp_path / "repo"
        # Initialize a bare-ish local repo for testing
        import subprocess

        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )

        backend = RealGitBackend()

        # Create worktree
        worktree_path = tmp_path / "worktree"
        result = backend.create_worktree(repo_path, "test-branch", worktree_path)
        assert result is True
        assert worktree_path.exists()

    def test_ensure_local_finds_clone_one_level_deep(self, tmp_path):
        """When a URL is given, find a clone nested one level under a search path."""
        # Create search_path/projects/my-repo/.git
        projects = tmp_path / "projects"
        projects.mkdir()
        repo_dir = projects / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        backend = RealGitBackend(search_paths=[tmp_path])
        result = backend.ensure_local("https://github.com/user/my-repo.git")
        assert result == repo_dir

    def test_ensure_local_custom_search_paths(self, tmp_path):
        """Custom search_paths are used instead of defaults."""
        search1 = tmp_path / "search1"
        search2 = tmp_path / "search2"
        search1.mkdir()
        search2.mkdir()
        repo_dir = search2 / "target-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        backend = RealGitBackend(search_paths=[search1, search2])
        result = backend.ensure_local("https://github.com/org/target-repo")
        assert result == repo_dir

    def test_ensure_local_prefers_direct_child_over_nested(self, tmp_path):
        """Direct child match is found before one-level-deep match."""
        # Direct: tmp_path/my-repo/.git
        direct = tmp_path / "my-repo"
        direct.mkdir()
        (direct / ".git").mkdir()

        # Nested: tmp_path/subdir/my-repo/.git
        subdir = tmp_path / "subdir"
        subdir.mkdir()
        nested = subdir / "my-repo"
        nested.mkdir()
        (nested / ".git").mkdir()

        backend = RealGitBackend(search_paths=[tmp_path])
        result = backend.ensure_local("https://github.com/user/my-repo")
        assert result == direct

    def test_ensure_local_skips_dotdirs_in_search(self, tmp_path):
        """Hidden directories (starting with .) are skipped during search."""
        hidden = tmp_path / ".hidden"
        hidden.mkdir()
        repo_dir = hidden / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        backend = RealGitBackend(search_paths=[tmp_path])
        result = backend.ensure_local("https://github.com/user/my-repo")
        assert result is None

    def test_ensure_local_strips_trailing_slash_from_url(self, tmp_path):
        """URL with trailing slash is handled correctly."""
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        backend = RealGitBackend(search_paths=[tmp_path])
        result = backend.ensure_local("https://github.com/user/my-repo/")
        assert result == repo_dir

    def test_ensure_local_strips_dot_git_from_url(self, tmp_path):
        """URL ending in .git is handled correctly."""
        repo_dir = tmp_path / "my-repo"
        repo_dir.mkdir()
        (repo_dir / ".git").mkdir()

        backend = RealGitBackend(search_paths=[tmp_path])
        result = backend.ensure_local("git@github.com:user/my-repo.git")
        assert result == repo_dir

    @pytest.mark.integration
    def test_fetch_on_local_repo(self, tmp_path):
        """Integration test: fetch on a local repo."""
        import subprocess

        repo_path = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)

        backend = RealGitBackend()
        # fetch --all on a repo with no remotes still returns 0
        result = backend.fetch(repo_path)
        assert result is True

    @pytest.mark.integration
    def test_list_worktrees(self, tmp_path):
        """Integration test: list worktrees of a repo."""
        import subprocess

        repo_path = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )

        backend = RealGitBackend()
        worktrees = backend.list_worktrees(repo_path)
        # At least the main worktree should be listed
        assert len(worktrees) >= 1
        assert worktrees[0].path == repo_path

    @pytest.mark.integration
    def test_list_worktrees_with_additional(self, tmp_path):
        """Integration test: list worktrees including an added worktree."""
        import subprocess

        repo_path = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )
        wt_path = tmp_path / "wt"
        subprocess.run(
            [
                "git",
                "-C",
                str(repo_path),
                "worktree",
                "add",
                str(wt_path),
                "-b",
                "test-branch",
            ],
            check=True,
            capture_output=True,
        )

        backend = RealGitBackend()
        worktrees = backend.list_worktrees(repo_path)
        branches = [wt.branch for wt in worktrees]
        assert "test-branch" in branches

    @pytest.mark.integration
    def test_branch_exists_local(self, tmp_path):
        """Integration test: check local branch exists."""
        import subprocess

        repo_path = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )

        backend = RealGitBackend()
        # Default branch should exist (either main or master)
        result = subprocess.run(
            ["git", "-C", str(repo_path), "branch", "--show-current"],
            capture_output=True,
            text=True,
        )
        default_branch = result.stdout.strip()
        assert backend.branch_exists(repo_path, default_branch) is True
        assert backend.branch_exists(repo_path, "nonexistent-branch") is False

    @pytest.mark.integration
    def test_create_worktree_from_existing(self, tmp_path):
        """Integration test: create worktree from an existing branch."""
        import subprocess

        repo_path = tmp_path / "repo"
        subprocess.run(["git", "init", str(repo_path)], check=True, capture_output=True)
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "-C", str(repo_path), "commit", "--allow-empty", "-m", "init"],
            check=True,
            capture_output=True,
        )
        # Create a branch
        subprocess.run(
            ["git", "-C", str(repo_path), "branch", "existing-branch"],
            check=True,
            capture_output=True,
        )

        backend = RealGitBackend()
        wt_path = tmp_path / "wt"
        result = backend.create_worktree_from_existing(
            repo_path, "existing-branch", wt_path
        )
        assert result is True
        assert wt_path.exists()


class TestHelperFunctions:
    """Test helper functions used by RealGitBackend."""

    def test_extract_repo_name_https(self):
        assert _extract_repo_name("https://github.com/user/my-repo") == "my-repo"

    def test_extract_repo_name_https_dot_git(self):
        assert _extract_repo_name("https://github.com/user/my-repo.git") == "my-repo"

    def test_extract_repo_name_ssh(self):
        assert _extract_repo_name("git@github.com:user/my-repo.git") == "my-repo"

    def test_extract_repo_name_trailing_slash(self):
        assert _extract_repo_name("https://github.com/user/my-repo/") == "my-repo"

    def test_extract_repo_name_plain_name(self):
        assert _extract_repo_name("my-repo") == "my-repo"

    def test_is_git_repo_true(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert _is_git_repo(repo) is True

    def test_is_git_repo_no_git_dir(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        assert _is_git_repo(repo) is False

    def test_is_git_repo_nonexistent(self, tmp_path):
        assert _is_git_repo(tmp_path / "nonexistent") is False

    def test_find_local_clone_direct_child(self, tmp_path):
        repo = tmp_path / "my-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert _find_local_clone("my-repo", [tmp_path]) == repo

    def test_find_local_clone_one_level_deep(self, tmp_path):
        subdir = tmp_path / "projects"
        subdir.mkdir()
        repo = subdir / "my-repo"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert _find_local_clone("my-repo", [tmp_path]) == repo

    def test_find_local_clone_not_found(self, tmp_path):
        assert _find_local_clone("no-such-repo", [tmp_path]) is None

    def test_find_local_clone_skips_nonexistent_search_path(self, tmp_path):
        result = _find_local_clone("repo", [tmp_path / "nonexistent"])
        assert result is None

    def test_find_local_clone_multiple_search_paths(self, tmp_path):
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        repo = second / "target"
        repo.mkdir()
        (repo / ".git").mkdir()
        assert _find_local_clone("target", [first, second]) == repo

    def test_find_local_clone_prefers_earlier_search_path(self, tmp_path):
        first = tmp_path / "first"
        second = tmp_path / "second"
        first.mkdir()
        second.mkdir()
        repo1 = first / "target"
        repo1.mkdir()
        (repo1 / ".git").mkdir()
        repo2 = second / "target"
        repo2.mkdir()
        (repo2 / ".git").mkdir()
        assert _find_local_clone("target", [first, second]) == repo1
