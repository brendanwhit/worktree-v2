"""Tests for the token store module."""

import json
from pathlib import Path

from superintendent.state.token_store import (
    DEFAULT_KEY,
    ResolveResult,
    TokenEntry,
    TokenStore,
)


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
        assert "github_user" not in d  # omitted when empty

    def test_to_dict_with_github_user(self) -> None:
        entry = TokenEntry(
            token="ghp_abc123",
            created_at="2026-01-01T00:00:00+00:00",
            permissions=[],
            github_user="brendanwhit",
        )
        d = entry.to_dict()
        assert d["github_user"] == "brendanwhit"

    def test_from_dict(self) -> None:
        d = {
            "token": "ghp_xyz789",
            "created_at": "2026-02-01T00:00:00+00:00",
            "permissions": ["repo"],
        }
        entry = TokenEntry.from_dict(d)
        assert entry.token == "ghp_xyz789"
        assert entry.permissions == ["repo"]
        assert entry.github_user == ""

    def test_from_dict_with_github_user(self) -> None:
        d = {
            "token": "ghp_xyz789",
            "created_at": "2026-02-01T00:00:00+00:00",
            "permissions": [],
            "github_user": "someuser",
        }
        entry = TokenEntry.from_dict(d)
        assert entry.github_user == "someuser"

    def test_from_dict_defaults(self) -> None:
        d = {"token": "ghp_minimal"}
        entry = TokenEntry.from_dict(d)
        assert entry.created_at == ""
        assert entry.permissions == []
        assert entry.github_user == ""

    def test_roundtrip(self) -> None:
        entry = TokenEntry(
            token="ghp_round",
            created_at="2026-01-15T12:00:00+00:00",
            permissions=["repo", "read:org"],
            github_user="testuser",
        )
        d = entry.to_dict()
        entry2 = TokenEntry.from_dict(d)
        assert entry2.token == entry.token
        assert entry2.created_at == entry.created_at
        assert entry2.permissions == entry.permissions
        assert entry2.github_user == entry.github_user


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

    def test_add_with_github_user(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("owner/repo", "ghp_test", github_user="myuser")
        entry = store.get("owner/repo")
        assert entry is not None
        assert entry.github_user == "myuser"


class TestResolveResult:
    """Test the ResolveResult dataclass."""

    def test_fields(self) -> None:
        r = ResolveResult(token="ghp_abc", source="repo")
        assert r.token == "ghp_abc"
        assert r.source == "repo"

    def test_none_token(self) -> None:
        r = ResolveResult(token=None, source="none")
        assert r.token is None
        assert r.source == "none"


class TestTokenStoreDefault:
    """Test default token via standard add/get/remove with DEFAULT_KEY."""

    def test_set_and_get_default(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        default = store.get(DEFAULT_KEY)
        assert default is not None
        assert default.token == "ghp_def123"
        assert default.github_user == "brendanwhit"
        assert len(default.created_at) > 0

    def test_get_default_when_none(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        assert store.get(DEFAULT_KEY) is None

    def test_remove_default(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        assert store.remove(DEFAULT_KEY) is True
        assert store.get(DEFAULT_KEY) is None

    def test_remove_default_when_none(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        assert store.remove(DEFAULT_KEY) is False

    def test_default_preserved_across_repo_add(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        store.add("org/repo", "ghp_repo456", permissions=["repo"])
        default = store.get(DEFAULT_KEY)
        assert default is not None
        assert default.token == "ghp_def123"
        assert default.github_user == "brendanwhit"

    def test_default_preserved_across_repo_remove(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        store.add("org/repo", "ghp_repo456")
        store.remove("org/repo")
        default = store.get(DEFAULT_KEY)
        assert default is not None
        assert default.token == "ghp_def123"

    def test_repo_tokens_not_affected_by_default(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("org/repo", "ghp_repo456")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        entry = store.get("org/repo")
        assert entry is not None
        assert entry.token == "ghp_repo456"

    def test_default_in_list_all(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_def123", github_user="brendanwhit")
        store.add("org/repo", "ghp_repo456")
        tokens = store.list_all()
        assert DEFAULT_KEY in tokens
        assert len(tokens) == 2

    def test_set_default_with_permissions(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(
            DEFAULT_KEY, "ghp_def123", github_user="brendanwhit", permissions=["repo"]
        )
        default = store.get(DEFAULT_KEY)
        assert default is not None
        assert default.permissions == ["repo"]

    def test_set_default_overwrites(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_old", github_user="olduser")
        store.add(DEFAULT_KEY, "ghp_new", github_user="newuser")
        default = store.get(DEFAULT_KEY)
        assert default is not None
        assert default.token == "ghp_new"
        assert default.github_user == "newuser"


class TestTokenStoreResolve:
    """Test the resolve() method with all 4 resolution paths."""

    def test_exact_repo_match(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add("org/repo", "ghp_repo_token")
        result = store.resolve("org/repo")
        assert result.token == "ghp_repo_token"
        assert result.source == "repo"

    def test_repo_match_overrides_default(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default", github_user="brendanwhit")
        store.add("brendanwhit/repo", "ghp_explicit")
        result = store.resolve("brendanwhit/repo")
        assert result.token == "ghp_explicit"
        assert result.source == "repo"

    def test_default_fallback_for_own_repo(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default", github_user="brendanwhit")
        result = store.resolve("brendanwhit/some-repo")
        assert result.token == "ghp_default"
        assert result.source == "default"

    def test_default_fallback_case_insensitive(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default", github_user="BrendanWhit")
        result = store.resolve("brendanwhit/some-repo")
        assert result.token == "ghp_default"
        assert result.source == "default"

    def test_org_requires_explicit(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        store.add(DEFAULT_KEY, "ghp_default", github_user="brendanwhit")
        result = store.resolve("some-org/repo")
        assert result.token is None
        assert result.source == "org_requires_explicit"

    def test_no_default_configured(self, tmp_path: Path) -> None:
        store = TokenStore(tmp_path / "tokens.json")
        result = store.resolve("anyone/repo")
        assert result.token is None
        assert result.source == "none"

    def test_no_default_with_other_repos(self, tmp_path: Path) -> None:
        """Resolve returns 'none' when repo not found and no default."""
        store = TokenStore(tmp_path / "tokens.json")
        store.add("other/repo", "ghp_other")
        result = store.resolve("anyone/repo")
        assert result.token is None
        assert result.source == "none"


class TestTokenStoreBackwardCompatibility:
    """Test that legacy files without _default key work correctly."""

    def test_legacy_file_without_default(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens.json"
        legacy_data = {
            "org/repo1": {
                "token": "ghp_legacy1",
                "created_at": "2026-01-01T00:00:00+00:00",
                "permissions": ["repo"],
            },
            "org/repo2": {
                "token": "ghp_legacy2",
                "created_at": "2026-01-15T00:00:00+00:00",
                "permissions": [],
            },
        }
        path.write_text(json.dumps(legacy_data))
        store = TokenStore(path)

        # All repos should load fine
        tokens = store.list_all()
        assert len(tokens) == 2
        assert tokens["org/repo1"].token == "ghp_legacy1"

        # Default should be None
        assert store.get(DEFAULT_KEY) is None

        # Resolve should return "none" for unknown repos
        result = store.resolve("unknown/repo")
        assert result.source == "none"

    def test_adding_default_to_legacy_file(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens.json"
        legacy_data = {
            "org/repo": {
                "token": "ghp_legacy",
                "created_at": "2026-01-01T00:00:00+00:00",
                "permissions": [],
            },
        }
        path.write_text(json.dumps(legacy_data))
        store = TokenStore(path)

        # Set a default — should not disturb existing repo tokens
        store.add(DEFAULT_KEY, "ghp_default", github_user="myuser")
        assert store.get(DEFAULT_KEY) is not None
        assert store.get("org/repo") is not None
        assert store.get("org/repo").token == "ghp_legacy"

    def test_legacy_file_add_repo_preserves_format(self, tmp_path: Path) -> None:
        path = tmp_path / "tokens.json"
        legacy_data = {
            "org/repo1": {
                "token": "ghp_legacy1",
                "created_at": "2026-01-01",
                "permissions": [],
            },
        }
        path.write_text(json.dumps(legacy_data))
        store = TokenStore(path)

        store.add("org/repo2", "ghp_new")
        tokens = store.list_all()
        assert len(tokens) == 2
        assert tokens["org/repo1"].token == "ghp_legacy1"
        assert tokens["org/repo2"].token == "ghp_new"
