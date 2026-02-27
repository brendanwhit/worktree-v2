"""Tests for smart cleanup logic."""

from pathlib import Path

from superintendent.backends.git import MockGitBackend
from superintendent.cli.main import (
    analyze_entry,
    smart_cleanup,
)
from superintendent.state.registry import WorktreeEntry, WorktreeRegistry


def _make_entry(
    name: str = "test",
    branch: str = "feature",
    worktree_path: str = "/tmp/wt",
    repo: str = "/tmp/repo",
) -> WorktreeEntry:
    return WorktreeEntry(
        name=name,
        repo=repo,
        branch=branch,
        worktree_path=worktree_path,
    )


class TestAnalyzeEntry:
    """Test analyze_entry for each cleanup qualification."""

    def test_missing_path_qualifies(self) -> None:
        entry = _make_entry(worktree_path="/nonexistent/path")
        git = MockGitBackend()
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert "path does not exist" in candidate.reasons

    def test_merged_pr_qualifies(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="merged-branch")
        git = MockGitBackend(merged_branches={"merged-branch"})
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert "branch has merged PR" in candidate.reasons

    def test_stale_branch_qualifies(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="stale-branch")
        git = MockGitBackend(stale_branches={"stale-branch"})
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert any("stale" in r for r in candidate.reasons)

    def test_missing_remote_qualifies(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="orphan-branch")
        git = MockGitBackend(remote_branches=set())  # no remotes
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert "remote branch no longer exists" in candidate.reasons

    def test_active_entry_not_candidate(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="active")
        git = MockGitBackend(remote_branches={"active"})
        candidate = analyze_entry(entry, git)
        assert candidate is None

    def test_uncommitted_changes_warning(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="merged")
        git = MockGitBackend(
            merged_branches={"merged"},
            dirty_worktrees={str(wt)},
        )
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert "has uncommitted changes" in candidate.warnings
        assert candidate.force_required is True

    def test_unpushed_commits_warning(self, tmp_path: Path) -> None:
        wt = tmp_path / "wt"
        wt.mkdir()
        entry = _make_entry(worktree_path=str(wt), branch="merged")
        git = MockGitBackend(
            merged_branches={"merged"},
            unpushed_branches={"merged"},
        )
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert "has unpushed commits" in candidate.warnings
        assert candidate.force_required is True

    def test_missing_path_no_safety_checks(self) -> None:
        """Missing path entries skip safety checks (nothing to inspect)."""
        entry = _make_entry(worktree_path="/nonexistent")
        git = MockGitBackend()
        candidate = analyze_entry(entry, git)
        assert candidate is not None
        assert candidate.warnings == []
        assert candidate.force_required is False


class TestSmartCleanup:
    """Test the smart_cleanup orchestration function."""

    def test_removes_candidates(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(_make_entry(name="stale", worktree_path="/nonexistent"))
        wt = tmp_path / "valid"
        wt.mkdir()
        registry.add(_make_entry(name="valid", worktree_path=str(wt), branch="active"))

        git = MockGitBackend(remote_branches={"active"})
        candidates = smart_cleanup(registry, git)
        assert len(candidates) == 1
        assert candidates[0].entry.name == "stale"
        assert registry.get("stale") is None
        assert registry.get("valid") is not None

    def test_dry_run_keeps_entries(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(_make_entry(name="stale", worktree_path="/nonexistent"))

        git = MockGitBackend()
        candidates = smart_cleanup(registry, git, dry_run=True)
        assert len(candidates) == 1
        assert registry.get("stale") is not None

    def test_force_required_skipped_without_force(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt = tmp_path / "dirty"
        wt.mkdir()
        registry.add(_make_entry(name="dirty", worktree_path=str(wt), branch="merged"))

        git = MockGitBackend(
            merged_branches={"merged"},
            dirty_worktrees={str(wt)},
        )
        candidates = smart_cleanup(registry, git, force=False)
        assert len(candidates) == 1
        assert candidates[0].force_required is True
        # Entry should NOT be removed without force
        assert registry.get("dirty") is not None

    def test_force_removes_force_required(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt = tmp_path / "dirty"
        wt.mkdir()
        registry.add(_make_entry(name="dirty", worktree_path=str(wt), branch="merged"))

        git = MockGitBackend(
            merged_branches={"merged"},
            dirty_worktrees={str(wt)},
        )
        candidates = smart_cleanup(registry, git, force=True)
        assert len(candidates) == 1
        assert registry.get("dirty") is None

    def test_no_candidates(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt = tmp_path / "active"
        wt.mkdir()
        registry.add(_make_entry(name="active", worktree_path=str(wt), branch="active"))

        git = MockGitBackend(remote_branches={"active"})
        candidates = smart_cleanup(registry, git)
        assert len(candidates) == 0
