"""Tests for GitBackend (Protocol, Mock, DryRun, Real)."""

from pathlib import Path

import pytest

from superintendent.backends.git import (
    DryRunGitBackend,
    GitBackend,
    MockGitBackend,
    RealGitBackend,
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
