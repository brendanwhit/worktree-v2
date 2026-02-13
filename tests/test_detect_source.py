"""Tests for TaskSource auto-detection logic."""

from pathlib import Path

from superintendent.orchestrator.sources.beads import BeadsSource
from superintendent.orchestrator.sources.detect import detect_source
from superintendent.orchestrator.sources.markdown import MarkdownSource
from superintendent.orchestrator.sources.single import SingleTaskSource


def _make_beads_dir(tmp_path: Path) -> None:
    """Create a .beads/ dir with an issues.jsonl file."""
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    (beads_dir / "issues.jsonl").write_text("")


class TestDetectSourceExplicit:
    def test_explicit_single_returns_single(self, tmp_path: Path):
        source = detect_source(
            repo_root=tmp_path,
            source_type="single",
            task_description="fix bug",
        )
        assert isinstance(source, SingleTaskSource)

    def test_explicit_single_no_description_returns_none(self, tmp_path: Path):
        source = detect_source(repo_root=tmp_path, source_type="single")
        assert source is None

    def test_explicit_markdown_returns_markdown(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text("- [ ] Task one\n")
        source = detect_source(
            repo_root=tmp_path,
            source_type="markdown",
        )
        assert isinstance(source, MarkdownSource)

    def test_explicit_markdown_with_custom_path(self, tmp_path: Path):
        custom = tmp_path / "work" / "my-tasks.md"
        custom.parent.mkdir(parents=True)
        custom.write_text("- [ ] Custom task\n")
        source = detect_source(
            repo_root=tmp_path,
            source_type="markdown",
            markdown_path=custom,
        )
        assert isinstance(source, MarkdownSource)

    def test_explicit_beads_returns_beads(self, tmp_path: Path):
        _make_beads_dir(tmp_path)
        source = detect_source(
            repo_root=tmp_path,
            source_type="beads",
        )
        assert isinstance(source, BeadsSource)

    def test_unknown_source_type_returns_none(self, tmp_path: Path):
        source = detect_source(repo_root=tmp_path, source_type="nosuchsource")
        assert source is None


class TestDetectSourceAuto:
    def test_auto_detects_beads(self, tmp_path: Path):
        _make_beads_dir(tmp_path)
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert isinstance(source, BeadsSource)

    def test_auto_ignores_empty_beads_dir(self, tmp_path: Path):
        (tmp_path / ".beads").mkdir()  # no issues.jsonl
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert source is None

    def test_auto_detects_markdown_tasks_md(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text("- [ ] Task one\n")
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert isinstance(source, MarkdownSource)

    def test_auto_detects_markdown_todo_md(self, tmp_path: Path):
        md_file = tmp_path / "TODO.md"
        md_file.write_text("- [ ] Task one\n")
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert isinstance(source, MarkdownSource)

    def test_auto_prefers_beads_over_markdown(self, tmp_path: Path):
        _make_beads_dir(tmp_path)
        (tmp_path / "tasks.md").write_text("- [ ] Task one\n")
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert isinstance(source, BeadsSource)

    def test_auto_falls_back_to_single_with_description(self, tmp_path: Path):
        source = detect_source(
            repo_root=tmp_path,
            source_type="auto",
            task_description="fix the bug",
        )
        assert isinstance(source, SingleTaskSource)

    def test_auto_returns_none_when_nothing_found(self, tmp_path: Path):
        source = detect_source(repo_root=tmp_path, source_type="auto")
        assert source is None
