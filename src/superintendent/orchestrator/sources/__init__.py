"""Task source abstractions for the superintendent orchestrator."""

from superintendent.orchestrator.sources.beads import BeadsSource
from superintendent.orchestrator.sources.detect import detect_source
from superintendent.orchestrator.sources.markdown import MarkdownSource
from superintendent.orchestrator.sources.models import Task, TaskStatus
from superintendent.orchestrator.sources.protocol import TaskSource
from superintendent.orchestrator.sources.single import SingleTaskSource

__all__ = [
    "BeadsSource",
    "MarkdownSource",
    "SingleTaskSource",
    "Task",
    "TaskSource",
    "TaskStatus",
    "detect_source",
]
