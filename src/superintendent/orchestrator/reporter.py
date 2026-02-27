"""Reporter: progress reporting for multi-agent orchestration.

Follows the Real/Mock/DryRun pattern used by all backends.
The Orchestrator calls reporter methods as agents start, complete, or fail.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable


@dataclass
class AgentEvent:
    """Record of a reporter event for testing."""

    event_type: str
    agent_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime | None = None


@runtime_checkable
class Reporter(Protocol):
    """Protocol for orchestration progress reporting.

    The Orchestrator calls these methods as agents progress through
    their lifecycle. Implementations control how progress is displayed.
    """

    def on_agent_started(
        self, agent_id: str, task_names: list[str], sandbox_name: str | None = None
    ) -> None:
        """Called when an agent begins execution."""
        ...

    def on_agent_completed(
        self, agent_id: str, task_names: list[str], duration_seconds: float
    ) -> None:
        """Called when an agent finishes successfully."""
        ...

    def on_agent_failed(self, agent_id: str, task_names: list[str], error: str) -> None:
        """Called when an agent fails."""
        ...

    def on_progress(
        self,
        running: int,
        completed: int,
        pending: int,
        failed: int,
    ) -> None:
        """Called periodically with overall progress counts."""
        ...

    def summarize(
        self,
        completed_tasks: list[str],
        failed_tasks: list[str],
        skipped_tasks: list[str],
        agents_spawned: int,
        total_time_seconds: float,
        errors: list[str],
    ) -> str:
        """Generate a final summary string."""
        ...


class RealReporter:
    """Reports progress to the terminal."""

    def on_agent_started(
        self, agent_id: str, task_names: list[str], sandbox_name: str | None = None
    ) -> None:
        tasks_str = ", ".join(task_names)
        location = f" in {sandbox_name}" if sandbox_name else ""
        print(f"[started] Agent {agent_id}{location} (tasks: {tasks_str})")

    def on_agent_completed(
        self, agent_id: str, task_names: list[str], duration_seconds: float
    ) -> None:
        tasks_str = ", ".join(task_names)
        minutes = duration_seconds / 60
        time_str = f"{minutes:.1f}m" if minutes >= 1 else f"{duration_seconds:.0f}s"
        print(
            f"[completed] Agent {agent_id} completed in {time_str} (tasks: {tasks_str})"
        )

    def on_agent_failed(self, agent_id: str, task_names: list[str], error: str) -> None:
        tasks_str = ", ".join(task_names)
        print(f"[FAILED] Agent {agent_id} FAILED (tasks: {tasks_str}): {error}")

    def on_progress(
        self,
        running: int,
        completed: int,
        pending: int,
        failed: int,
    ) -> None:
        total = running + completed + pending + failed
        print(
            f"[progress] {completed}/{total} completed, "
            f"{running} running, {pending} pending, {failed} failed"
        )

    def summarize(
        self,
        completed_tasks: list[str],
        failed_tasks: list[str],
        skipped_tasks: list[str],
        agents_spawned: int,
        total_time_seconds: float,
        errors: list[str],
    ) -> str:
        lines = ["--- Orchestration Summary ---"]
        minutes = total_time_seconds / 60
        if minutes >= 1:
            lines.append(f"Total time: {minutes:.1f}m")
        else:
            lines.append(f"Total time: {total_time_seconds:.0f}s")
        lines.append(f"Agents spawned: {agents_spawned}")
        lines.append(f"Completed: {len(completed_tasks)} tasks")
        if completed_tasks:
            for t in completed_tasks:
                lines.append(f"  - {t}")
        if failed_tasks:
            lines.append(f"Failed: {len(failed_tasks)} tasks")
            for t in failed_tasks:
                lines.append(f"  - {t}")
        if skipped_tasks:
            lines.append(f"Skipped: {len(skipped_tasks)} tasks")
            for t in skipped_tasks:
                lines.append(f"  - {t}")
        if errors:
            lines.append(f"Errors ({len(errors)}):")
            for e in errors:
                lines.append(f"  - {e}")
        return "\n".join(lines)


@dataclass
class MockReporter:
    """Records reporter events for testing."""

    events: list[AgentEvent] = field(default_factory=list)
    summaries: list[str] = field(default_factory=list)

    def on_agent_started(
        self, agent_id: str, task_names: list[str], sandbox_name: str | None = None
    ) -> None:
        self.events.append(
            AgentEvent(
                event_type="started",
                agent_id=agent_id,
                data={"task_names": task_names, "sandbox_name": sandbox_name},
            )
        )

    def on_agent_completed(
        self, agent_id: str, task_names: list[str], duration_seconds: float
    ) -> None:
        self.events.append(
            AgentEvent(
                event_type="completed",
                agent_id=agent_id,
                data={"task_names": task_names, "duration_seconds": duration_seconds},
            )
        )

    def on_agent_failed(self, agent_id: str, task_names: list[str], error: str) -> None:
        self.events.append(
            AgentEvent(
                event_type="failed",
                agent_id=agent_id,
                data={"task_names": task_names, "error": error},
            )
        )

    def on_progress(
        self,
        running: int,
        completed: int,
        pending: int,
        failed: int,
    ) -> None:
        self.events.append(
            AgentEvent(
                event_type="progress",
                agent_id="",
                data={
                    "running": running,
                    "completed": completed,
                    "pending": pending,
                    "failed": failed,
                },
            )
        )

    def summarize(
        self,
        completed_tasks: list[str],
        failed_tasks: list[str],
        skipped_tasks: list[str],
        agents_spawned: int,
        total_time_seconds: float,
        errors: list[str],
    ) -> str:
        summary = (
            f"completed={len(completed_tasks)} "
            f"failed={len(failed_tasks)} "
            f"skipped={len(skipped_tasks)} "
            f"agents={agents_spawned} "
            f"time={total_time_seconds:.0f}s "
            f"errors={len(errors)}"
        )
        self.summaries.append(summary)
        return summary


class DryRunReporter:
    """Shows what would be reported without executing."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def on_agent_started(
        self, agent_id: str, task_names: list[str], sandbox_name: str | None = None
    ) -> None:
        tasks_str = ", ".join(task_names)
        location = f" in {sandbox_name}" if sandbox_name else ""
        self.messages.append(
            f"[dry-run] Would report: Agent {agent_id} started{location} (tasks: {tasks_str})"
        )

    def on_agent_completed(
        self, agent_id: str, task_names: list[str], duration_seconds: float
    ) -> None:
        tasks_str = ", ".join(task_names)
        self.messages.append(
            f"[dry-run] Would report: Agent {agent_id} completed "
            f"in {duration_seconds:.0f}s (tasks: {tasks_str})"
        )

    def on_agent_failed(self, agent_id: str, task_names: list[str], error: str) -> None:
        tasks_str = ", ".join(task_names)
        self.messages.append(
            f"[dry-run] Would report: Agent {agent_id} FAILED (tasks: {tasks_str}): {error}"
        )

    def on_progress(
        self,
        running: int,
        completed: int,
        pending: int,
        failed: int,
    ) -> None:
        self.messages.append(
            f"[dry-run] Would report progress: "
            f"{completed} completed, {running} running, {pending} pending, {failed} failed"
        )

    def summarize(
        self,
        completed_tasks: list[str],
        failed_tasks: list[str],
        skipped_tasks: list[str],
        agents_spawned: int,
        total_time_seconds: float,
        errors: list[str],
    ) -> str:
        msg = (
            f"[dry-run] Would summarize: {len(completed_tasks)} completed, "
            f"{len(failed_tasks)} failed, {len(skipped_tasks)} skipped, "
            f"{agents_spawned} agents, {total_time_seconds:.0f}s total, "
            f"{len(errors)} errors"
        )
        self.messages.append(msg)
        return msg
