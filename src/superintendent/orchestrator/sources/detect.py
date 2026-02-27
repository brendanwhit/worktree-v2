"""Auto-detection logic for choosing the appropriate TaskSource."""

from pathlib import Path

from .beads import BeadsSource
from .markdown import MarkdownSource
from .protocol import TaskSource
from .single import SingleTaskSource
from .speckit import SpecKitSource

# Auto-detection priority order. Each source's can_handle() is checked
# in sequence; the first match wins. To add a new source, create a
# TaskSource subclass with can_handle()/create() and add it here.
_AUTO_DETECT_ORDER: list[type[TaskSource]] = [
    BeadsSource,
    SpecKitSource,
    MarkdownSource,
]

# Map source_name -> class for explicit --from flag
_SOURCE_BY_NAME: dict[str, type[TaskSource]] = {
    cls.source_name: cls
    for cls in [BeadsSource, SpecKitSource, MarkdownSource, SingleTaskSource]
}


def detect_source(
    repo_root: Path,
    source_type: str = "auto",
    task_description: str | None = None,
    markdown_path: Path | None = None,
) -> TaskSource | None:
    """Detect and return the appropriate TaskSource.

    Args:
        repo_root: Root directory of the repository.
        source_type: "auto" or an explicit source name (beads, markdown, single).
        task_description: Ad-hoc task string (used for single source).
        markdown_path: Explicit path to a markdown task file.

    Returns:
        A TaskSource instance, or None if no source could be determined.
    """
    if source_type == "single":
        if task_description:
            return SingleTaskSource(task_description)
        return None

    if source_type == "markdown" and markdown_path is not None:
        return MarkdownSource(markdown_path)

    if source_type != "auto":
        source_cls = _SOURCE_BY_NAME.get(source_type)
        if source_cls is not None:
            return source_cls.create(repo_root)
        return None

    # Auto-detection: check each source in priority order
    for source_cls in _AUTO_DETECT_ORDER:
        if source_cls.can_handle(repo_root):
            return source_cls.create(repo_root)

    # Fallback to single task if a description was provided
    if task_description:
        return SingleTaskSource(task_description)

    return None
