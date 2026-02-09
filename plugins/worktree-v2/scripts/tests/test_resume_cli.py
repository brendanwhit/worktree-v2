"""Tests for resume.py CLI entry point."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.resume import build_parser, list_worktrees, main, resume_worktree
from state.registry import WorktreeEntry, WorktreeRegistry


class TestBuildParser:
    """Test argument parser construction."""

    def test_parser_exists(self) -> None:
        parser = build_parser()
        assert parser is not None

    def test_name_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--name", "my-worktree"])
        assert args.name == "my-worktree"

    def test_list_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--list"])
        assert args.list_entries is True

    def test_list_default_is_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--name", "foo"])
        assert args.list_entries is False

    def test_name_default_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--list"])
        assert args.name is None

    def test_requires_name_or_list(self) -> None:
        """Parser should accept --name or --list (at minimum one)."""
        parser = build_parser()
        # With neither, parse succeeds but main should error
        args = parser.parse_args([])
        assert args.name is None
        assert args.list_entries is False


class TestListWorktrees:
    """Test listing worktree entries."""

    def test_list_empty_registry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        entries = list_worktrees(registry)
        assert entries == []

    def test_list_populated_registry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        entry = WorktreeEntry(
            name="test",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/tmp/worktree",
            sandbox_name="claude-test",
        )
        registry.add(entry)
        entries = list_worktrees(registry)
        assert len(entries) == 1
        assert entries[0].name == "test"

    def test_list_multiple_entries(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        for i in range(3):
            registry.add(
                WorktreeEntry(
                    name=f"wt-{i}",
                    repo=f"/tmp/repo-{i}",
                    branch=f"branch-{i}",
                    worktree_path=f"/tmp/worktree-{i}",
                )
            )
        entries = list_worktrees(registry)
        assert len(entries) == 3


class TestResumeWorktree:
    """Test resuming a worktree entry."""

    def test_resume_existing_entry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        entry = WorktreeEntry(
            name="test",
            repo="/tmp/repo",
            branch="main",
            worktree_path=str(wt_path),
            sandbox_name="claude-test",
        )
        registry.add(entry)
        result = resume_worktree("test", registry)
        assert result is not None
        assert result.name == "test"

    def test_resume_nonexistent_entry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        result = resume_worktree("nonexistent", registry)
        assert result is None

    def test_resume_missing_worktree_path(self, tmp_path: Path) -> None:
        """If the worktree path no longer exists, resume should return None."""
        registry = WorktreeRegistry(tmp_path / "registry.json")
        entry = WorktreeEntry(
            name="stale",
            repo="/tmp/repo",
            branch="main",
            worktree_path="/nonexistent/path",
            sandbox_name="claude-stale",
        )
        registry.add(entry)
        result = resume_worktree("stale", registry)
        assert result is None


class TestMain:
    """Test the main() entry point."""

    def test_main_list_returns_zero(self, tmp_path: Path) -> None:
        with patch("cli.resume.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name=None,
                list_entries=True,
            )
            with patch("cli.resume.get_default_registry") as mock_reg:
                mock_reg.return_value = WorktreeRegistry(tmp_path / "reg.json")
                exit_code = main()
                assert exit_code == 0

    def test_main_resume_success_returns_zero(self, tmp_path: Path) -> None:
        wt_path = tmp_path / "worktree"
        wt_path.mkdir()
        registry = WorktreeRegistry(tmp_path / "reg.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path=str(wt_path),
            )
        )
        with patch("cli.resume.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name="test",
                list_entries=False,
            )
            with patch("cli.resume.get_default_registry") as mock_reg:
                mock_reg.return_value = registry
                exit_code = main()
                assert exit_code == 0

    def test_main_resume_not_found_returns_one(self, tmp_path: Path) -> None:
        with patch("cli.resume.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name="nonexistent",
                list_entries=False,
            )
            with patch("cli.resume.get_default_registry") as mock_reg:
                mock_reg.return_value = WorktreeRegistry(tmp_path / "reg.json")
                exit_code = main()
                assert exit_code == 1

    def test_main_no_args_returns_one(self) -> None:
        """With neither --name nor --list, main should return 1."""
        with patch("cli.resume.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name=None,
                list_entries=False,
            )
            exit_code = main()
            assert exit_code == 1
