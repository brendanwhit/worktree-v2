"""Tests for the global worktree registry."""

import json
from pathlib import Path

from superintendent.state.registry import WorktreeEntry, WorktreeRegistry


class TestWorktreeEntry:
    """Test the WorktreeEntry dataclass."""

    def test_create_entry(self):
        entry = WorktreeEntry(
            name="my-worktree",
            repo="https://github.com/user/repo",
            branch="feature-branch",
            worktree_path="/home/user/worktrees/my-worktree",
            sandbox_name="sb-my-worktree",
        )
        assert entry.name == "my-worktree"
        assert entry.repo == "https://github.com/user/repo"
        assert entry.branch == "feature-branch"
        assert entry.worktree_path == "/home/user/worktrees/my-worktree"
        assert entry.sandbox_name == "sb-my-worktree"

    def test_timestamps_auto_populated(self):
        entry = WorktreeEntry(
            name="wt",
            repo="repo",
            branch="main",
            worktree_path="/tmp/wt",
        )
        assert entry.created_at is not None
        assert len(entry.created_at) > 0

    def test_to_dict(self):
        entry = WorktreeEntry(
            name="wt-1",
            repo="https://github.com/org/repo",
            branch="dev",
            worktree_path="/tmp/wt-1",
            sandbox_name="sb-1",
        )
        d = entry.to_dict()
        assert d["name"] == "wt-1"
        assert d["repo"] == "https://github.com/org/repo"
        assert d["branch"] == "dev"
        assert d["worktree_path"] == "/tmp/wt-1"
        assert d["sandbox_name"] == "sb-1"
        assert "created_at" in d

    def test_from_dict(self):
        d = {
            "name": "wt-2",
            "repo": "repo-url",
            "branch": "main",
            "worktree_path": "/tmp/wt-2",
            "sandbox_name": None,
            "created_at": "2026-01-01T00:00:00+00:00",
        }
        entry = WorktreeEntry.from_dict(d)
        assert entry.name == "wt-2"
        assert entry.sandbox_name is None
        assert entry.created_at == "2026-01-01T00:00:00+00:00"

    def test_roundtrip(self):
        entry = WorktreeEntry(
            name="round",
            repo="repo",
            branch="main",
            worktree_path="/tmp/round",
            sandbox_name="sb-round",
        )
        d = entry.to_dict()
        entry2 = WorktreeEntry.from_dict(d)
        assert entry2.name == entry.name
        assert entry2.repo == entry.repo
        assert entry2.worktree_path == entry.worktree_path

    def test_no_sandbox_name(self):
        entry = WorktreeEntry(
            name="local-wt",
            repo="repo",
            branch="main",
            worktree_path="/tmp/local-wt",
        )
        assert entry.sandbox_name is None
        d = entry.to_dict()
        assert d["sandbox_name"] is None


class TestWorktreeRegistry:
    """Test the WorktreeRegistry class."""

    def test_list_empty(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        assert reg.list_all() == []

    def test_add_entry(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        entry = WorktreeEntry(
            name="wt-1",
            repo="repo",
            branch="main",
            worktree_path="/tmp/wt-1",
        )
        reg.add(entry)
        entries = reg.list_all()
        assert len(entries) == 1
        assert entries[0].name == "wt-1"

    def test_add_multiple_entries(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        for i in range(3):
            reg.add(
                WorktreeEntry(
                    name=f"wt-{i}",
                    repo="repo",
                    branch="main",
                    worktree_path=f"/tmp/wt-{i}",
                )
            )
        assert len(reg.list_all()) == 3

    def test_add_duplicate_name_replaces(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="wt-dup",
                repo="repo-v1",
                branch="main",
                worktree_path="/tmp/wt-dup",
            )
        )
        reg.add(
            WorktreeEntry(
                name="wt-dup",
                repo="repo-v2",
                branch="dev",
                worktree_path="/tmp/wt-dup-new",
            )
        )
        entries = reg.list_all()
        assert len(entries) == 1
        assert entries[0].repo == "repo-v2"

    def test_remove_by_name(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="wt-rm",
                repo="repo",
                branch="main",
                worktree_path="/tmp/wt-rm",
            )
        )
        assert len(reg.list_all()) == 1
        removed = reg.remove("wt-rm")
        assert removed is True
        assert len(reg.list_all()) == 0

    def test_remove_nonexistent(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        removed = reg.remove("nope")
        assert removed is False

    def test_remove_preserves_others(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="keep",
                repo="repo",
                branch="main",
                worktree_path="/tmp/keep",
            )
        )
        reg.add(
            WorktreeEntry(
                name="remove-me",
                repo="repo",
                branch="main",
                worktree_path="/tmp/remove-me",
            )
        )
        reg.remove("remove-me")
        entries = reg.list_all()
        assert len(entries) == 1
        assert entries[0].name == "keep"

    def test_cleanup_removes_stale(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)

        # Add entry with a real path
        real_dir = tmp_path / "real-wt"
        real_dir.mkdir()
        reg.add(
            WorktreeEntry(
                name="real",
                repo="repo",
                branch="main",
                worktree_path=str(real_dir),
            )
        )
        # Add entry with a nonexistent path
        reg.add(
            WorktreeEntry(
                name="stale",
                repo="repo",
                branch="main",
                worktree_path="/tmp/nonexistent-path-12345",
            )
        )
        assert len(reg.list_all()) == 2

        removed = reg.cleanup()
        assert removed == ["stale"]
        assert len(reg.list_all()) == 1
        assert reg.list_all()[0].name == "real"

    def test_cleanup_empty_registry(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        removed = reg.cleanup()
        assert removed == []

    def test_cleanup_all_valid(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        real_dir = tmp_path / "valid-wt"
        real_dir.mkdir()
        reg.add(
            WorktreeEntry(
                name="valid",
                repo="repo",
                branch="main",
                worktree_path=str(real_dir),
            )
        )
        removed = reg.cleanup()
        assert removed == []
        assert len(reg.list_all()) == 1

    def test_persists_to_disk(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg1 = WorktreeRegistry(registry_path)
        reg1.add(
            WorktreeEntry(
                name="persist",
                repo="repo",
                branch="main",
                worktree_path="/tmp/persist",
            )
        )

        # Load from a new instance
        reg2 = WorktreeRegistry(registry_path)
        entries = reg2.list_all()
        assert len(entries) == 1
        assert entries[0].name == "persist"

    def test_creates_parent_dirs(self, tmp_path: Path):
        registry_path = tmp_path / "deep" / "nested" / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="deep",
                repo="repo",
                branch="main",
                worktree_path="/tmp/deep",
            )
        )
        assert registry_path.exists()

    def test_file_is_valid_json(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="json-check",
                repo="repo",
                branch="main",
                worktree_path="/tmp/json",
            )
        )
        data = json.loads(registry_path.read_text())
        assert "entries" in data
        assert len(data["entries"]) == 1

    def test_get_by_name(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        reg.add(
            WorktreeEntry(
                name="find-me",
                repo="repo",
                branch="main",
                worktree_path="/tmp/find-me",
            )
        )
        entry = reg.get("find-me")
        assert entry is not None
        assert entry.name == "find-me"

    def test_get_nonexistent(self, tmp_path: Path):
        registry_path = tmp_path / "worktree-registry.json"
        reg = WorktreeRegistry(registry_path)
        assert reg.get("nope") is None
