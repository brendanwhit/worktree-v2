"""Auto-detection logic for choosing the appropriate TaskSource."""

from pathlib import Path

from superintendent.orchestrator.sources.beads import BeadsSource
from superintendent.orchestrator.sources.markdown import MarkdownSource
from superintendent.orchestrator.sources.protocol import TaskSource
from superintendent.orchestrator.sources.single import SingleTaskSource

# Markdown filenames to check during auto-detection, in priority order
_MARKDOWN_CANDIDATES = ["tasks.md", "TODO.md"]


def detect_source(
    repo_root: Path,
    source_type: str = "auto",
    task_description: str | None = None,
    markdown_path: Path | None = None,
) -> TaskSource | None:
    """Detect and return the appropriate TaskSource.

    Args:
        repo_root: Root directory of the repository.
        source_type: One of "auto", "beads", "markdown", "single".
        task_description: Ad-hoc task string (used for single source).
        markdown_path: Explicit path to a markdown task file.

    Returns:
        A TaskSource instance, or None if no source could be determined.
    """
    if source_type == "single":
        if task_description:
            return SingleTaskSource(task_description)
        return None

    if source_type == "beads":
        return BeadsSource(repo_root=repo_root)

    if source_type == "markdown":
        path = _find_markdown(repo_root, markdown_path)
        if path is not None:
            return MarkdownSource(path)
        return None

    # Auto-detection: beads → markdown → single
    if _has_beads(repo_root):
        return BeadsSource(repo_root=repo_root)

    md_path = _find_markdown(repo_root, markdown_path)
    if md_path is not None:
        return MarkdownSource(md_path)

    if task_description:
        return SingleTaskSource(task_description)

    return None


def _has_beads(repo_root: Path) -> bool:
    """Check if the repo has a .beads/ directory."""
    return (repo_root / ".beads").is_dir()


def _find_markdown(repo_root: Path, explicit_path: Path | None = None) -> Path | None:
    """Find a markdown task file."""
    if explicit_path is not None and explicit_path.exists():
        return explicit_path

    for candidate in _MARKDOWN_CANDIDATES:
        path = repo_root / candidate
        if path.exists():
            return path

    return None
