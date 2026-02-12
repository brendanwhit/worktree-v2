"""Tests for RepoInfo analyzer."""

from pathlib import Path

import pytest

from superintendent.orchestrator.repo_info import RepoInfo


class TestRepoInfo:
    def test_create_minimal(self):
        info = RepoInfo(
            has_dockerfile=False,
            has_devcontainer=False,
            has_env_file=False,
            needs_auth=False,
            languages=["python"],
            estimated_complexity="simple",
        )
        assert info.has_dockerfile is False
        assert info.languages == ["python"]

    def test_all_fields(self):
        info = RepoInfo(
            has_dockerfile=True,
            has_devcontainer=True,
            has_env_file=True,
            needs_auth=True,
            languages=["python", "javascript"],
            estimated_complexity="complex",
        )
        assert info.has_dockerfile is True
        assert info.has_devcontainer is True
        assert info.has_env_file is True
        assert info.needs_auth is True
        assert len(info.languages) == 2
        assert info.estimated_complexity == "complex"


class TestRepoInfoFromPath:
    def test_detects_dockerfile(self, tmp_path: Path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_dockerfile is True

    def test_detects_docker_compose(self, tmp_path: Path):
        (tmp_path / "docker-compose.yml").write_text("version: '3'")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_dockerfile is True

    def test_detects_docker_compose_yaml(self, tmp_path: Path):
        (tmp_path / "docker-compose.yaml").write_text("version: '3'")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_dockerfile is True

    def test_detects_devcontainer_dir(self, tmp_path: Path):
        (tmp_path / ".devcontainer").mkdir()
        (tmp_path / ".devcontainer" / "devcontainer.json").write_text("{}")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_devcontainer is True

    def test_detects_env_file(self, tmp_path: Path):
        (tmp_path / ".env").write_text("SECRET=foo")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_env_file is True

    def test_detects_env_example(self, tmp_path: Path):
        (tmp_path / ".env.example").write_text("SECRET=")
        info = RepoInfo.from_path(tmp_path)
        assert info.has_env_file is True

    def test_detects_npmrc_auth(self, tmp_path: Path):
        (tmp_path / ".npmrc").write_text(
            "//registry.npmjs.org/:_authToken=${NPM_TOKEN}"
        )
        info = RepoInfo.from_path(tmp_path)
        assert info.needs_auth is True

    def test_detects_pip_conf(self, tmp_path: Path):
        (tmp_path / "pip.conf").write_text(
            "[global]\nindex-url = https://pypi.example.com"
        )
        info = RepoInfo.from_path(tmp_path)
        assert info.needs_auth is True

    def test_detects_python_language(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]\nname='test'")
        info = RepoInfo.from_path(tmp_path)
        assert "python" in info.languages

    def test_detects_python_from_setup_py(self, tmp_path: Path):
        (tmp_path / "setup.py").write_text("from setuptools import setup")
        info = RepoInfo.from_path(tmp_path)
        assert "python" in info.languages

    def test_detects_python_from_requirements(self, tmp_path: Path):
        (tmp_path / "requirements.txt").write_text("flask==2.0")
        info = RepoInfo.from_path(tmp_path)
        assert "python" in info.languages

    def test_detects_javascript_from_package_json(self, tmp_path: Path):
        (tmp_path / "package.json").write_text('{"name": "test"}')
        info = RepoInfo.from_path(tmp_path)
        assert "javascript" in info.languages

    def test_detects_typescript(self, tmp_path: Path):
        (tmp_path / "tsconfig.json").write_text("{}")
        info = RepoInfo.from_path(tmp_path)
        assert "typescript" in info.languages

    def test_detects_rust(self, tmp_path: Path):
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        info = RepoInfo.from_path(tmp_path)
        assert "rust" in info.languages

    def test_detects_go(self, tmp_path: Path):
        (tmp_path / "go.mod").write_text("module example.com/test")
        info = RepoInfo.from_path(tmp_path)
        assert "go" in info.languages

    def test_detects_multiple_languages(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        info = RepoInfo.from_path(tmp_path)
        assert "python" in info.languages
        assert "javascript" in info.languages

    def test_empty_repo(self, tmp_path: Path):
        info = RepoInfo.from_path(tmp_path)
        assert info.has_dockerfile is False
        assert info.has_devcontainer is False
        assert info.has_env_file is False
        assert info.needs_auth is False
        assert info.languages == []
        assert info.estimated_complexity == "simple"

    def test_complexity_from_multiple_languages(self, tmp_path: Path):
        (tmp_path / "pyproject.toml").write_text("[project]")
        (tmp_path / "package.json").write_text('{"name": "test"}')
        (tmp_path / "Cargo.toml").write_text('[package]\nname = "test"')
        info = RepoInfo.from_path(tmp_path)
        assert info.estimated_complexity in ("moderate", "complex")

    def test_complexity_from_docker_and_env(self, tmp_path: Path):
        (tmp_path / "Dockerfile").write_text("FROM python:3.11")
        (tmp_path / ".env").write_text("SECRET=foo")
        (tmp_path / ".devcontainer").mkdir()
        (tmp_path / ".devcontainer" / "devcontainer.json").write_text("{}")
        info = RepoInfo.from_path(tmp_path)
        assert info.estimated_complexity in ("moderate", "complex")

    def test_nonexistent_path_raises(self):
        with pytest.raises(ValueError, match="does not exist"):
            RepoInfo.from_path(Path("/nonexistent/path/that/does/not/exist"))

    def test_file_path_raises(self, tmp_path: Path):
        f = tmp_path / "afile.txt"
        f.write_text("hello")
        with pytest.raises(ValueError, match="not a directory"):
            RepoInfo.from_path(f)
