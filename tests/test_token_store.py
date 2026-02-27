"""Tests for the token store module."""

import json
from pathlib import Path

from superintendent.state.token_store import TokenEntry, TokenStore


class TestTokenEntry:
    """Test the TokenEntry dataclass."""

    def test_to_dict(self) -> None:
        entry = TokenEntry(
            token="ghp_abc123",
            created_at="2026-01-01T00:00:00+00:00",
            permissions=["repo", "workflow"],
        )
        d = entry.to_dict()
        assert d["token"] == "ghp_abc123"
        assert d["created_at"] == "2026-01-01T00:00:00+00:00"
        assert d["permissions"] == ["repo", "workflow"]

    def test_from_dict(self) -> None:
        d = {
            "token": "ghp_xyz789",
            "created_at": "2026-02-01T00:00:00+00:00",
            "permissions": ["repo"],
        }
        entry = TokenEntry.from_dict(d)
        assert entry.token == "ghp_xyz789"
        assert entry.permissions == ["repo"]

    def test_from_dict_defaults(self) -> None:
        d = {"token": "ghp_minimal"}
        entry = TokenEntry.from_dict(d)
        assert entry.created_at == ""
        assert entry.permissions == []

    def test_roundtrip(self) -> None:
        entry = TokenEntry(
            token="ghp_round",
            created_at="2026-01-15T12:00:00+00:00",
            permissions=["repo", "read:org"],
        )
        d = entry.to_dict()
        entry2 = TokenEntry.from_dict(d)
        assert entry2.token == entry.token
        assert entry2.created_at == entry.created_at
        assert entry2.permissions == entry.permissions


class TestTokenStore:
    """Test the TokenStore class."""

    def test_empty_store(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        assert store.list_all() == {}

    def test_add_token(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_test123", permissions=["repo"])
        entry = store.get("owner/repo")
        assert entry is not None
        assert entry.token == "ghp_test123"
        assert entry.permissions == ["repo"]

    def test_add_overwrites(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_old")
        store.add("owner/repo", "ghp_new")
        entry = store.get("owner/repo")
        assert entry is not None
        assert entry.token == "ghp_new"

    def test_get_nonexistent(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        assert store.get("owner/repo") is None

    def test_remove_existing(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_remove")
        assert store.remove("owner/repo") is True
        assert store.get("owner/repo") is None

    def test_remove_nonexistent(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        assert store.remove("owner/repo") is False

    def test_list_all(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("org/repo1", "ghp_aaa")
        store.add("org/repo2", "ghp_bbb")
        tokens = store.list_all()
        assert len(tokens) == 2
        assert "org/repo1" in tokens
        assert "org/repo2" in tokens

    def test_persists_to_disk(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens.json"
        store1 = TokenStore(path)
        store1.add("owner/repo", "ghp_persist", permissions=["repo"])

        store2 = TokenStore(path)
        entry = store2.get("owner/repo")
        assert entry is not None
        assert entry.token == "ghp_persist"

    def test_creates_parent_dirs(self, tmp_path: Path) -> None:
        path = tmp_path / "deep" / "nested" / "tokens.json"
        store = TokenStore(path)
        store.add("owner/repo", "ghp_deep")
        assert path.exists()

    def test_file_is_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens.json"
        store = TokenStore(path)
        store.add("owner/repo", "ghp_json")
        data = json.loads(path.read_text())
        assert "owner/repo" in data
        assert data["owner/repo"]["token"] == "ghp_json"

    def test_add_default_permissions(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_noperms")
        entry = store.get("owner/repo")
        assert entry is not None
        assert entry.permissions == []

    def test_created_at_auto_populated(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_time")
        entry = store.get("owner/repo")
        assert entry is not None
        assert len(entry.created_at) > 0
