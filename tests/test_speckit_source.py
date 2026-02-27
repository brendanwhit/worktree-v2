"""Tests for SpecKitSource adapter."""

from pathlib import Path
from textwrap import dedent

from superintendent.orchestrator.sources.models import TaskStatus
from superintendent.orchestrator.sources.speckit import SpecKitSource

BASIC_SPECKIT = dedent("""\
    ## Phase 1: Setup

    - [ ] [T001] [P] [US1] Create project structure
    - [ ] [T002] [P] [US1] Set up CI pipeline
    - [ ] [T003] [US1] Configure linting
    - [x] [T004] [P] [US2] Write initial tests
""")

MULTI_PHASE = dedent("""\
    ## Setup

    - [ ] [T001] [P] [US1] Initialize repo

    ## Foundation

    - [ ] [T002] [US1] Add core module
    - [ ] [T003] [US1] Add database layer

    ## Stories

    - [ ] [T004] [P] [US2] Implement login
    - [ ] [T005] [P] [US2] Implement signup

    ## Polish

    - [ ] [T006] [P] [US3] Add logging
""")

NO_SPECKIT = dedent("""\
    # Tasks

    - [ ] Fix the login bug
    - [ ] Add dark mode support
""")

MIXED_STORIES = dedent("""\
    - [ ] [T001] [P] [US1] Task A
    - [ ] [T002] [US1] Task B (depends on T001 chain)
    - [ ] [T003] [US1] Task C (depends on T002)
    - [ ] [T004] [P] [US2] Task D (different story, independent)
    - [ ] [T005] [US2] Task E (depends on T004 chain)
""")


class TestSpecKitSourceDetection:
    def test_detects_speckit_format(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        assert SpecKitSource.can_handle(tmp_path) is True

    def test_rejects_plain_markdown(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(NO_SPECKIT)
        assert SpecKitSource.can_handle(tmp_path) is False

    def test_rejects_missing_file(self, tmp_path: Path) -> None:
        assert SpecKitSource.can_handle(tmp_path) is False

    def test_create_returns_instance(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource.create(tmp_path)
        assert isinstance(source, SpecKitSource)
        assert source.source_name == "speckit"


class TestSpecKitSourceParsing:
    def test_parse_all_tasks(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert len(tasks) == 4

    def test_task_ids(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        ids = [t.task_id for t in tasks]
        assert ids == ["T001", "T002", "T003", "T004"]

    def test_task_titles(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert tasks[0].title == "Create project structure"
        assert tasks[2].title == "Configure linting"

    def test_completed_status(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert tasks[0].status == TaskStatus.pending
        assert tasks[3].status == TaskStatus.completed

    def test_source_ref(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert tasks[0].source_ref == str(md)


class TestSpecKitParallelMarkers:
    def test_parallel_tasks_have_label(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert tasks[0].labels.get("parallel") == "true"
        assert tasks[1].labels.get("parallel") == "true"
        assert "parallel" not in tasks[2].labels

    def test_parallel_tasks_no_sibling_dependency(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        # T001 and T002 are both parallel in US1 — no deps
        assert tasks[0].dependencies == []
        assert tasks[1].dependencies == []

    def test_sequential_task_depends_on_previous(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(MIXED_STORIES)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        by_id = {t.task_id: t for t in tasks}
        # T002 is sequential in US1, should depend on T001 (last sequential before it)
        # But T001 is parallel, so it doesn't set the last_sequential.
        # T002 is the first sequential in US1, so no dependency.
        assert by_id["T002"].dependencies == []
        # T003 is sequential in US1, depends on T002
        assert by_id["T003"].dependencies == ["T002"]


class TestSpecKitStoryGrouping:
    def test_story_labels(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        assert tasks[0].labels["story"] == "US1"
        assert tasks[3].labels["story"] == "US2"

    def test_cross_story_independence(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(MIXED_STORIES)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        by_id = {t.task_id: t for t in tasks}
        # T004 is in US2, independent of US1 tasks
        assert by_id["T004"].dependencies == []
        # T005 is sequential in US2, no dependency (T004 is parallel)
        assert by_id["T005"].dependencies == []


class TestSpecKitPhaseStructure:
    def test_phase_labels(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(MULTI_PHASE)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        by_id = {t.task_id: t for t in tasks}
        assert by_id["T001"].labels["phase"] == "Setup"
        assert by_id["T002"].labels["phase"] == "Foundation"
        assert by_id["T003"].labels["phase"] == "Foundation"
        assert by_id["T004"].labels["phase"] == "Stories"
        assert by_id["T006"].labels["phase"] == "Polish"

    def test_all_phases_present(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(MULTI_PHASE)
        source = SpecKitSource(md)
        tasks = source.get_tasks()
        phases = {t.labels.get("phase") for t in tasks}
        assert phases == {"Setup", "Foundation", "Stories", "Polish"}


class TestSpecKitReadyTasks:
    def test_excludes_completed(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        ready = source.get_ready_tasks()
        ids = [t.task_id for t in ready]
        assert "T004" not in ids

    def test_excludes_blocked(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(MIXED_STORIES)
        source = SpecKitSource(md)
        ready = source.get_ready_tasks()
        ids = [t.task_id for t in ready]
        # T003 depends on T002
        assert "T003" not in ids
        # T001, T002, T004, T005 are all ready (parallel or first-sequential)
        assert "T001" in ids
        assert "T002" in ids
        assert "T004" in ids


class TestSpecKitStatusUpdate:
    def test_complete_toggles_checkbox(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        source.update_status("T001", TaskStatus.completed)
        content = md.read_text()
        assert "- [x] [T001] [P] [US1] Create project structure" in content

    def test_pending_untoggles_checkbox(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        source.update_status("T004", TaskStatus.pending)
        content = md.read_text()
        assert "- [ ] [T004] [P] [US2] Write initial tests" in content

    def test_update_unknown_task_is_noop(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        original = md.read_text()
        source = SpecKitSource(md)
        source.update_status("NONEXISTENT", TaskStatus.completed)
        assert md.read_text() == original


class TestSpecKitClaim:
    def test_claim_returns_true(self, tmp_path: Path) -> None:
        md = tmp_path / "tasks.md"
        md.write_text(BASIC_SPECKIT)
        source = SpecKitSource(md)
        assert source.claim_task("T001") is True
