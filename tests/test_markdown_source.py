"""Tests for MarkdownSource adapter."""

from pathlib import Path
from textwrap import dedent

from superintendent.orchestrator.sources.markdown import MarkdownSource
from superintendent.orchestrator.sources.models import TaskStatus

SIMPLE_TASKS = dedent("""\
    # Tasks

    - [ ] Fix the login bug
    - [ ] Add dark mode support
    - [x] Update dependencies
""")

TASKS_WITH_IDS = dedent("""\
    # Tasks

    - [ ] [T001] Fix the login bug
    - [ ] [T002] Add dark mode support
    - [x] [T003] Update dependencies
""")

NESTED_TASKS = dedent("""\
    # Tasks

    - [ ] [T001] Set up auth system
      - [ ] [T002] Add OAuth provider
      - [ ] [T003] Add session management
    - [ ] [T004] Build UI
""")

EMPTY_FILE = dedent("""\
    # Tasks

    No tasks yet.
""")


class TestMarkdownSourceParsing:
    def test_parse_simple_tasks(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert len(tasks) == 3

    def test_task_descriptions(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks[0].title == "Fix the login bug"
        assert tasks[1].title == "Add dark mode support"
        assert tasks[2].title == "Update dependencies"

    def test_checked_tasks_are_completed(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks[0].status == TaskStatus.pending
        assert tasks[1].status == TaskStatus.pending
        assert tasks[2].status == TaskStatus.completed

    def test_generated_ids_when_no_explicit_ids(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        # All tasks should have unique IDs
        ids = [t.task_id for t in tasks]
        assert len(set(ids)) == 3
        # IDs should start with "md-"
        for task_id in ids:
            assert task_id.startswith("md-")

    def test_explicit_ids_parsed(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks[0].task_id == "T001"
        assert tasks[1].task_id == "T002"
        assert tasks[2].task_id == "T003"

    def test_explicit_id_stripped_from_title(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks[0].title == "Fix the login bug"

    def test_empty_file_returns_no_tasks(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(EMPTY_FILE)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks == []

    def test_source_ref_is_file_path(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        assert tasks[0].source_ref == str(md_file)

    def test_nested_tasks_infer_dependencies(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(NESTED_TASKS)
        source = MarkdownSource(md_file)
        tasks = source.get_tasks()
        # T002 and T003 are children of T001
        t002 = next(t for t in tasks if t.task_id == "T002")
        t003 = next(t for t in tasks if t.task_id == "T003")
        assert "T001" in t002.dependencies
        assert "T001" in t003.dependencies
        # T001 and T004 have no dependencies
        t001 = next(t for t in tasks if t.task_id == "T001")
        t004 = next(t for t in tasks if t.task_id == "T004")
        assert t001.dependencies == []
        assert t004.dependencies == []


class TestMarkdownSourceReadyTasks:
    def test_ready_excludes_completed(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(SIMPLE_TASKS)
        source = MarkdownSource(md_file)
        ready = source.get_ready_tasks()
        assert len(ready) == 2
        titles = [t.title for t in ready]
        assert "Update dependencies" not in titles

    def test_ready_excludes_blocked(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(NESTED_TASKS)
        source = MarkdownSource(md_file)
        ready = source.get_ready_tasks()
        # T001 and T004 are ready; T002/T003 depend on T001
        ids = [t.task_id for t in ready]
        assert "T001" in ids
        assert "T004" in ids
        assert "T002" not in ids
        assert "T003" not in ids


class TestMarkdownSourceStatusUpdate:
    def test_complete_toggles_checkbox(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        source = MarkdownSource(md_file)
        source.update_status("T001", TaskStatus.completed)
        content = md_file.read_text()
        assert "- [x] [T001] Fix the login bug" in content

    def test_pending_untoggles_checkbox(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        source = MarkdownSource(md_file)
        # T003 is already completed
        source.update_status("T003", TaskStatus.pending)
        content = md_file.read_text()
        assert "- [ ] [T003] Update dependencies" in content

    def test_update_unknown_task_is_noop(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        original = md_file.read_text()
        source = MarkdownSource(md_file)
        source.update_status("NONEXISTENT", TaskStatus.completed)
        assert md_file.read_text() == original


class TestMarkdownSourceClaim:
    def test_claim_returns_true(self, tmp_path: Path):
        md_file = tmp_path / "tasks.md"
        md_file.write_text(TASKS_WITH_IDS)
        source = MarkdownSource(md_file)
        assert source.claim_task("T001") is True
