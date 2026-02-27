"""Token store for managing scoped GitHub tokens per repository."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_DEFAULT_KEY = "_default"


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


@dataclass
class DefaultToken:
    """A default personal GitHub token with associated username."""

    token: str
    github_user: str
    created_at: str
    permissions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "token": self.token,
            "github_user": self.github_user,
            "created_at": self.created_at,
            "permissions": self.permissions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DefaultToken":
        return cls(
            token=data["token"],
            github_user=data.get("github_user", ""),
            created_at=data.get("created_at", ""),
            permissions=data.get("permissions", []),
        )


@dataclass
class ResolveResult:
    """Result of resolving a token for a repository.

    source is one of:
        "repo" — exact per-repo match
        "default" — owner matches default token's github_user
        "org_requires_explicit" — org repo with no explicit token
        "none" — no default configured
    """

    token: str | None
    source: str


class TokenStore:
    """Manages GitHub tokens stored in ~/.claude/ralph-tokens.json."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_token_path()

    def _load_raw(self) -> dict[str, Any]:
        """Load the raw JSON data from disk."""
        if not self._path.exists():
            return {}
        return json.loads(self._path.read_text())

    def _save_raw(self, data: dict[str, Any]) -> None:
        """Write raw JSON data to disk."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2))

    def _load(self) -> dict[str, TokenEntry]:
        """Load repo token entries, filtering out the _default key."""
        raw = self._load_raw()
        return {
            repo: TokenEntry.from_dict(entry)
            for repo, entry in raw.items()
            if repo != _DEFAULT_KEY
        }

    def _save(self, entries: dict[str, TokenEntry]) -> None:
        """Save repo token entries, preserving the _default key."""
        raw = self._load_raw()
        # Preserve the default entry if it exists
        default_data = raw.get(_DEFAULT_KEY)
        data: dict[str, Any] = {}
        if default_data is not None:
            data[_DEFAULT_KEY] = default_data
        data.update({repo: entry.to_dict() for repo, entry in entries.items()})
        self._save_raw(data)

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
        """Return all stored tokens (excluding default)."""
        return self._load()

    def set_default(
        self,
        token: str,
        github_user: str,
        permissions: list[str] | None = None,
    ) -> None:
        """Set the default personal token."""
        raw = self._load_raw()
        raw[_DEFAULT_KEY] = DefaultToken(
            token=token,
            github_user=github_user,
            created_at=datetime.now(UTC).isoformat(),
            permissions=permissions or [],
        ).to_dict()
        self._save_raw(raw)

    def get_default(self) -> DefaultToken | None:
        """Get the default personal token, or None if not set."""
        raw = self._load_raw()
        default_data = raw.get(_DEFAULT_KEY)
        if default_data is None:
            return None
        return DefaultToken.from_dict(default_data)

    def remove_default(self) -> bool:
        """Remove the default personal token. Returns True if it existed."""
        raw = self._load_raw()
        if _DEFAULT_KEY not in raw:
            return False
        del raw[_DEFAULT_KEY]
        self._save_raw(raw)
        return True

    def resolve(self, repo: str) -> "ResolveResult":
        """Resolve a token for a repository.

        Resolution order:
        1. Exact per-repo match → source="repo"
        2. Owner matches default token's github_user → source="default"
        3. Owner differs from default user (org repo) → source="org_requires_explicit"
        4. No default configured → source="none"
        """
        # 1. Exact per-repo match
        entry = self.get(repo)
        if entry is not None:
            return ResolveResult(token=entry.token, source="repo")

        # Check default token
        default = self.get_default()
        if default is None:
            # 4. No default configured
            return ResolveResult(token=None, source="none")

        # Extract owner from "owner/repo" format
        owner = repo.split("/")[0] if "/" in repo else repo

        # 2. Owner matches default github_user (case-insensitive)
        if owner.lower() == default.github_user.lower():
            return ResolveResult(token=default.token, source="default")

        # 3. Owner differs — org repo requires explicit token
        return ResolveResult(token=None, source="org_requires_explicit")
