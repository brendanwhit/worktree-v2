"""Tests for the Reporter protocol and implementations."""

from superintendent.orchestrator.reporter import (
    DryRunReporter,
    MockReporter,
    RealReporter,
    Reporter,
)


class TestReporterProtocol:
    """Verify that all implementations satisfy the Reporter protocol."""

    def test_real_reporter_satisfies_protocol(self):
        assert isinstance(RealReporter(), Reporter)

    def test_mock_reporter_satisfies_protocol(self):
        assert isinstance(MockReporter(), Reporter)

    def test_dry_run_reporter_satisfies_protocol(self):
        assert isinstance(DryRunReporter(), Reporter)


class TestRealReporter:
    """Test RealReporter output."""

    def test_on_agent_started_prints(self, capsys):
        reporter = RealReporter()
        reporter.on_agent_started(
            "agent-1", ["task-a", "task-b"], sandbox_name="sandbox-1"
        )
        captured = capsys.readouterr()
        assert "agent-1" in captured.out
        assert "sandbox-1" in captured.out
        assert "task-a" in captured.out

    def test_on_agent_started_without_sandbox(self, capsys):
        reporter = RealReporter()
        reporter.on_agent_started("agent-1", ["task-a"])
        captured = capsys.readouterr()
        assert "agent-1" in captured.out
        assert "sandbox" not in captured.out.lower().replace("[started]", "")

    def test_on_agent_completed_prints_minutes(self, capsys):
        reporter = RealReporter()
        reporter.on_agent_completed("agent-1", ["task-a"], duration_seconds=720.0)
        captured = capsys.readouterr()
        assert "12.0m" in captured.out
        assert "agent-1" in captured.out

    def test_on_agent_completed_prints_seconds(self, capsys):
        reporter = RealReporter()
        reporter.on_agent_completed("agent-1", ["task-a"], duration_seconds=45.0)
        captured = capsys.readouterr()
        assert "45s" in captured.out

    def test_on_agent_failed_prints(self, capsys):
        reporter = RealReporter()
        reporter.on_agent_failed("agent-1", ["task-a"], error="boom")
        captured = capsys.readouterr()
        assert "FAILED" in captured.out
        assert "boom" in captured.out

    def test_on_progress_prints(self, capsys):
        reporter = RealReporter()
        reporter.on_progress(running=2, completed=3, pending=5, failed=1)
        captured = capsys.readouterr()
        assert "3/11 completed" in captured.out
        assert "2 running" in captured.out
        assert "5 pending" in captured.out
        assert "1 failed" in captured.out

    def test_summarize_all_completed(self):
        reporter = RealReporter()
        result = reporter.summarize(
            completed_tasks=["task-a", "task-b"],
            failed_tasks=[],
            skipped_tasks=[],
            agents_spawned=2,
            total_time_seconds=120.0,
            errors=[],
        )
        assert "2.0m" in result
        assert "Agents spawned: 2" in result
        assert "Completed: 2 tasks" in result
        assert "task-a" in result
        assert "Failed" not in result
        assert "Skipped" not in result

    def test_summarize_with_failures(self):
        reporter = RealReporter()
        result = reporter.summarize(
            completed_tasks=["task-a"],
            failed_tasks=["task-b"],
            skipped_tasks=["task-c"],
            agents_spawned=3,
            total_time_seconds=30.0,
            errors=["connection timeout"],
        )
        assert "30s" in result
        assert "Failed: 1 tasks" in result
        assert "task-b" in result
        assert "Skipped: 1 tasks" in result
        assert "task-c" in result
        assert "connection timeout" in result

    def test_summarize_seconds_format(self):
        reporter = RealReporter()
        result = reporter.summarize(
            completed_tasks=[],
            failed_tasks=[],
            skipped_tasks=[],
            agents_spawned=0,
            total_time_seconds=45.0,
            errors=[],
        )
        assert "45s" in result


class TestMockReporter:
    """Test MockReporter event recording."""

    def test_on_agent_started_records_event(self):
        reporter = MockReporter()
        reporter.on_agent_started("agent-1", ["task-a"], sandbox_name="sb-1")
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event.event_type == "started"
        assert event.agent_id == "agent-1"
        assert event.data["task_names"] == ["task-a"]
        assert event.data["sandbox_name"] == "sb-1"

    def test_on_agent_completed_records_event(self):
        reporter = MockReporter()
        reporter.on_agent_completed("agent-1", ["task-a"], duration_seconds=60.0)
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event.event_type == "completed"
        assert event.data["duration_seconds"] == 60.0

    def test_on_agent_failed_records_event(self):
        reporter = MockReporter()
        reporter.on_agent_failed("agent-1", ["task-a"], error="timeout")
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event.event_type == "failed"
        assert event.data["error"] == "timeout"

    def test_on_progress_records_event(self):
        reporter = MockReporter()
        reporter.on_progress(running=1, completed=2, pending=3, failed=0)
        assert len(reporter.events) == 1
        event = reporter.events[0]
        assert event.event_type == "progress"
        assert event.data["running"] == 1
        assert event.data["completed"] == 2
        assert event.data["pending"] == 3
        assert event.data["failed"] == 0

    def test_summarize_records_and_returns(self):
        reporter = MockReporter()
        result = reporter.summarize(
            completed_tasks=["a", "b"],
            failed_tasks=["c"],
            skipped_tasks=[],
            agents_spawned=2,
            total_time_seconds=100.0,
            errors=[],
        )
        assert "completed=2" in result
        assert "failed=1" in result
        assert len(reporter.summaries) == 1

    def test_multiple_events_accumulate(self):
        reporter = MockReporter()
        reporter.on_agent_started("a1", ["t1"])
        reporter.on_agent_started("a2", ["t2"])
        reporter.on_agent_completed("a1", ["t1"], duration_seconds=10.0)
        reporter.on_agent_failed("a2", ["t2"], error="oops")
        assert len(reporter.events) == 4
        assert reporter.events[0].event_type == "started"
        assert reporter.events[1].event_type == "started"
        assert reporter.events[2].event_type == "completed"
        assert reporter.events[3].event_type == "failed"


class TestDryRunReporter:
    """Test DryRunReporter message collection."""

    def test_on_agent_started_collects_message(self):
        reporter = DryRunReporter()
        reporter.on_agent_started("agent-1", ["task-a"], sandbox_name="sb-1")
        assert len(reporter.messages) == 1
        assert "dry-run" in reporter.messages[0]
        assert "agent-1" in reporter.messages[0]
        assert "sb-1" in reporter.messages[0]

    def test_on_agent_completed_collects_message(self):
        reporter = DryRunReporter()
        reporter.on_agent_completed("agent-1", ["task-a"], duration_seconds=60.0)
        assert len(reporter.messages) == 1
        assert "dry-run" in reporter.messages[0]
        assert "completed" in reporter.messages[0]

    def test_on_agent_failed_collects_message(self):
        reporter = DryRunReporter()
        reporter.on_agent_failed("agent-1", ["task-a"], error="boom")
        assert len(reporter.messages) == 1
        assert "FAILED" in reporter.messages[0]
        assert "boom" in reporter.messages[0]

    def test_on_progress_collects_message(self):
        reporter = DryRunReporter()
        reporter.on_progress(running=1, completed=2, pending=3, failed=0)
        assert len(reporter.messages) == 1
        assert "2 completed" in reporter.messages[0]

    def test_summarize_collects_and_returns(self):
        reporter = DryRunReporter()
        result = reporter.summarize(
            completed_tasks=["a"],
            failed_tasks=[],
            skipped_tasks=[],
            agents_spawned=1,
            total_time_seconds=50.0,
            errors=[],
        )
        assert "dry-run" in result
        assert "1 completed" in result
        assert len(reporter.messages) == 1

    def test_multiple_messages_accumulate(self):
        reporter = DryRunReporter()
        reporter.on_agent_started("a1", ["t1"])
        reporter.on_progress(running=1, completed=0, pending=0, failed=0)
        reporter.on_agent_completed("a1", ["t1"], duration_seconds=30.0)
        assert len(reporter.messages) == 3
