"""Token store for managing scoped GitHub tokens per repository."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _default_token_path() -> Path:
    """Return the default path for token storage."""
    return Path.home() / ".claude" / "ralph-tokens.json"


@dataclass
class TokenEntry:
    """A stored GitHub token for a specific repository."""

    token: str
    created_at: str
    permissions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "created_at": self.created_at,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenEntry":
        return cls(
            token=data["token"],
            created_at=data.get("created_at", ""),
            permissions=data.get("permissions", []),
        )


class TokenStore:
    """Manages GitHub tokens stored in ~/.claude/ralph-tokens.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_token_path()

    def _load(self) -> dict[str, TokenEntry]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text())
        return {repo: TokenEntry.from_dict(entry) for repo, entry in data.items()}

    def _save(self, entries: dict[str, TokenEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {repo: entry.to_dict() for repo, entry in entries.items()}
        self._path.write_text(json.dumps(data, indent=2))

    def add(self, repo: str, token: str, permissions: list[str] | None = None) -> None:
        """Add a token for a repository. Overwrites if exists."""
        entries = self._load()
        entries[repo] = TokenEntry(
            token=token,
            created_at=datetime.now(UTC).isoformat(),
            permissions=permissions or [],
        )
        self._save(entries)

    def get(self, repo: str) -> TokenEntry | None:
        """Get a token entry for a repository."""
        return self._load().get(repo)

    def remove(self, repo: str) -> bool:
        """Remove a token for a repository. Returns True if it existed."""
        entries = self._load()
        if repo not in entries:
            return False
        del entries[repo]
        self._save(entries)
        return True

    def list_all(self) -> dict[str, TokenEntry]:
        """Return all stored tokens."""
        return self._load()
