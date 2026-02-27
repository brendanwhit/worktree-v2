"""Token store for managing scoped GitHub tokens per repository."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_KEY = "_default"


def _default_token_path() -> Path:
    """Return the default path for token storage."""
    return Path.home() / ".claude" / "ralph-tokens.json"


@dataclass
class TokenEntry:
    """A stored GitHub token, optionally associated with a GitHub user.

    The github_user field is used by the _default entry to enable
    owner-based resolution (personal repos fall back to the default
    token; org repos require an explicit per-repo token).
    """

    token: str
    created_at: str
    permissions: list[str]
    github_user: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "token": self.token,
            "created_at": self.created_at,
            "permissions": self.permissions,
        }
        if self.github_user:
            d["github_user"] = self.github_user
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TokenEntry":
        return cls(
            token=data["token"],
            created_at=data.get("created_at", ""),
            permissions=data.get("permissions", []),
            github_user=data.get("github_user", ""),
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
    """Manages GitHub tokens stored in ~/.claude/ralph-tokens.json.

    Tokens are keyed by "owner/repo". The special key "_default" holds
    a personal fallback token with a github_user for owner matching.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or _default_token_path()

    def _load(self) -> dict[str, TokenEntry]:
        if not self._path.exists():
            return {}
        data = json.loads(self._path.read_text())
        return {key: TokenEntry.from_dict(entry) for key, entry in data.items()}

    def _save(self, entries: dict[str, TokenEntry]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        data = {key: entry.to_dict() for key, entry in entries.items()}
        self._path.write_text(json.dumps(data, indent=2))

    def add(
        self,
        repo: str,
        token: str,
        permissions: list[str] | None = None,
        github_user: str = "",
    ) -> None:
        """Add a token for a repository (or _default). Overwrites if exists."""
        entries = self._load()
        entries[repo] = TokenEntry(
            token=token,
            created_at=datetime.now(UTC).isoformat(),
            permissions=permissions or [],
            github_user=github_user,
        )
        self._save(entries)

    def get(self, repo: str) -> TokenEntry | None:
        """Get a token entry by key (repo or _default)."""
        return self._load().get(repo)

    def remove(self, repo: str) -> bool:
        """Remove a token by key. Returns True if it existed."""
        entries = self._load()
        if repo not in entries:
            return False
        del entries[repo]
        self._save(entries)
        return True

    def list_all(self) -> dict[str, TokenEntry]:
        """Return all stored tokens, including _default."""
        return self._load()

    def resolve(self, repo: str) -> "ResolveResult":
        """Resolve a token for a repository.

        Resolution order:
        1. Exact per-repo match → source="repo"
        2. Owner matches _default entry's github_user → source="default"
        3. Owner differs from default user (org repo) → source="org_requires_explicit"
        4. No default configured → source="none"
        """
        entries = self._load()

        # 1. Exact per-repo match
        entry = entries.get(repo)
        if entry is not None:
            return ResolveResult(token=entry.token, source="repo")

        # Check default token
        default = entries.get(DEFAULT_KEY)
        if default is None:
            # 4. No default configured
            return ResolveResult(token=None, source="none")

        # Extract owner from "owner/repo" format
        owner = repo.split("/")[0] if "/" in repo else repo

        # 2. Owner matches default github_user (case-insensitive)
        if default.github_user and owner.lower() == default.github_user.lower():
            return ResolveResult(token=default.token, source="default")

        # 3. Owner differs — org repo requires explicit token
        return ResolveResult(token=None, source="org_requires_explicit")
