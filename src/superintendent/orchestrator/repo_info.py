"""RepoInfo: analyzes a repository to inform execution strategy decisions."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RepoInfo:
    """Gathered context about a repository for strategy decisions."""

    has_dockerfile: bool
    has_devcontainer: bool
    has_env_file: bool
    needs_auth: bool
    languages: list[str] = field(default_factory=list)
    estimated_complexity: str = "simple"  # simple, moderate, complex

    @classmethod
    def from_path(cls, repo: Path) -> "RepoInfo":
        """Analyze a repository path and return a RepoInfo."""
        if not repo.exists():
            raise ValueError(f"Repository path does not exist: {repo}")
        if not repo.is_dir():
            raise ValueError(f"Repository path is not a directory: {repo}")

        has_dockerfile = _detect_dockerfile(repo)
        has_devcontainer = _detect_devcontainer(repo)
        has_env_file = _detect_env_file(repo)
        needs_auth = _detect_auth_needs(repo)
        languages = _detect_languages(repo)
        estimated_complexity = _estimate_complexity(
            has_dockerfile=has_dockerfile,
            has_devcontainer=has_devcontainer,
            has_env_file=has_env_file,
            needs_auth=needs_auth,
            languages=languages,
        )

        return cls(
            has_dockerfile=has_dockerfile,
            has_devcontainer=has_devcontainer,
            has_env_file=has_env_file,
            needs_auth=needs_auth,
            languages=languages,
            estimated_complexity=estimated_complexity,
        )


def _detect_dockerfile(repo: Path) -> bool:
    """Check for Dockerfile or docker-compose files."""
    indicators = [
        "Dockerfile",
        "docker-compose.yml",
        "docker-compose.yaml",
        "compose.yml",
        "compose.yaml",
    ]
    return any((repo / name).exists() for name in indicators)


def _detect_devcontainer(repo: Path) -> bool:
    """Check for .devcontainer directory."""
    devcontainer_dir = repo / ".devcontainer"
    return devcontainer_dir.is_dir()


def _detect_env_file(repo: Path) -> bool:
    """Check for .env or .env.example files."""
    indicators = [".env", ".env.example", ".env.local", ".env.sample"]
    return any((repo / name).exists() for name in indicators)


def _detect_auth_needs(repo: Path) -> bool:
    """Check for files that suggest authentication requirements."""
    auth_indicators = [
        ".npmrc",
        "pip.conf",
        ".pypirc",
    ]
    return any((repo / name).exists() for name in auth_indicators)


def _detect_languages(repo: Path) -> list[str]:
    """Detect programming languages used in the repo."""
    languages: list[str] = []

    # Python indicators
    python_indicators = [
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
        "Pipfile",
    ]
    if any((repo / name).exists() for name in python_indicators):
        languages.append("python")

    # JavaScript indicators
    if (repo / "package.json").exists():
        languages.append("javascript")

    # TypeScript indicators
    if (repo / "tsconfig.json").exists():
        languages.append("typescript")

    # Rust indicators
    if (repo / "Cargo.toml").exists():
        languages.append("rust")

    # Go indicators
    if (repo / "go.mod").exists():
        languages.append("go")

    # Java indicators
    java_indicators = ["pom.xml", "build.gradle", "build.gradle.kts"]
    if any((repo / name).exists() for name in java_indicators):
        languages.append("java")

    return languages


def _estimate_complexity(
    *,
    has_dockerfile: bool,
    has_devcontainer: bool,
    has_env_file: bool,
    needs_auth: bool,
    languages: list[str],
) -> str:
    """Estimate repo complexity based on detected characteristics."""
    score = 0
    if has_dockerfile:
        score += 1
    if has_devcontainer:
        score += 1
    if has_env_file:
        score += 1
    if needs_auth:
        score += 1
    score += max(0, len(languages) - 1)  # multiple languages add complexity

    if score >= 3:
        return "complex"
    elif score >= 1:
        return "moderate"
    return "simple"
