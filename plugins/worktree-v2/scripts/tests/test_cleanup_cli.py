"""Tests for cleanup.py CLI entry point."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from cli.cleanup import build_parser, cleanup_all, cleanup_by_name, main
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

    def test_all_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--all"])
        assert args.all is True

    def test_all_default_is_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--name", "foo"])
        assert args.all is False

    def test_dry_run_flag(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--all", "--dry-run"])
        assert args.dry_run is True

    def test_dry_run_default_is_false(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--all"])
        assert args.dry_run is False

    def test_name_default_is_none(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--all"])
        assert args.name is None


class TestCleanupByName:
    """Test removing a specific worktree entry by name."""

    def test_remove_existing_entry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/worktree",
            )
        )
        removed = cleanup_by_name("test", registry)
        assert removed is True
        assert registry.get("test") is None

    def test_remove_nonexistent_entry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        removed = cleanup_by_name("nonexistent", registry)
        assert removed is False

    def test_dry_run_does_not_remove(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/worktree",
            )
        )
        removed = cleanup_by_name("test", registry, dry_run=True)
        assert removed is True  # Would be removed
        assert registry.get("test") is not None  # But still exists


class TestCleanupAll:
    """Test cleaning up all stale entries."""

    def test_cleanup_removes_stale_entries(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        # Add an entry with a non-existent path
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        # Add an entry with a valid path
        valid_path = tmp_path / "valid-worktree"
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
        assert registry.get("stale") is None
        assert registry.get("valid") is not None

    def test_cleanup_empty_registry(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        removed = cleanup_all(registry)
        assert removed == []

    def test_cleanup_all_valid(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "registry.json")
        valid_path = tmp_path / "worktree"
        valid_path.mkdir()
        registry.add(
            WorktreeEntry(
                name="valid",
                repo="/tmp/repo",
                branch="main",
                worktree_path=str(valid_path),
            )
        )
        removed = cleanup_all(registry)
        assert removed == []

    def test_cleanup_dry_run_does_not_remove(self, tmp_path: Path) -> None:
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
        # Entry should still exist
        assert registry.get("stale") is not None


class TestMain:
    """Test the main() entry point."""

    def test_main_cleanup_all_returns_zero(self, tmp_path: Path) -> None:
        with patch("cli.cleanup.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name=None,
                all=True,
                dry_run=False,
            )
            with patch("cli.cleanup.get_default_registry") as mock_reg:
                mock_reg.return_value = WorktreeRegistry(tmp_path / "reg.json")
                exit_code = main()
                assert exit_code == 0

    def test_main_cleanup_by_name_returns_zero(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "reg.json")
        registry.add(
            WorktreeEntry(
                name="test",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/tmp/worktree",
            )
        )
        with patch("cli.cleanup.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name="test",
                all=False,
                dry_run=False,
            )
            with patch("cli.cleanup.get_default_registry") as mock_reg:
                mock_reg.return_value = registry
                exit_code = main()
                assert exit_code == 0

    def test_main_cleanup_not_found_returns_one(self, tmp_path: Path) -> None:
        with patch("cli.cleanup.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name="nonexistent",
                all=False,
                dry_run=False,
            )
            with patch("cli.cleanup.get_default_registry") as mock_reg:
                mock_reg.return_value = WorktreeRegistry(tmp_path / "reg.json")
                exit_code = main()
                assert exit_code == 1

    def test_main_no_args_returns_one(self) -> None:
        """With neither --name nor --all, main should return 1."""
        with patch("cli.cleanup.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name=None,
                all=False,
                dry_run=False,
            )
            exit_code = main()
            assert exit_code == 1

    def test_main_dry_run_returns_zero(self, tmp_path: Path) -> None:
        registry = WorktreeRegistry(tmp_path / "reg.json")
        registry.add(
            WorktreeEntry(
                name="stale",
                repo="/tmp/repo",
                branch="main",
                worktree_path="/nonexistent/path",
            )
        )
        with patch("cli.cleanup.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_parser.parse_args.return_value = argparse.Namespace(
                name=None,
                all=True,
                dry_run=True,
            )
            with patch("cli.cleanup.get_default_registry") as mock_reg:
                mock_reg.return_value = registry
                exit_code = main()
                assert exit_code == 0
