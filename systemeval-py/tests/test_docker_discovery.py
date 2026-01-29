"""Tests for Docker auto-discovery and config resolution.

Covers:
- Compose file discovery (searching for common filenames)
- Config resolution (filling in missing values from compose file)
- Test command inference
- Config validation (services, compose file, test service)
"""
from pathlib import Path
from textwrap import dedent

import pytest

from systemeval.utils.docker.discovery import (
    find_compose_file,
    discover_compose_file,
    infer_test_command,
    resolve_docker_config,
    validate_docker_config,
    COMPOSE_FILE_CANDIDATES,
)


@pytest.fixture
def project_dir(tmp_path):
    """Create a temp project directory."""
    return tmp_path


def _write_file(directory, filename, content=""):
    """Write a file and return its path."""
    path = directory / filename
    path.write_text(dedent(content))
    return path


class TestFindComposeFile:
    """Tests for compose file discovery."""

    def test_finds_docker_compose_yml(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", "services: {}")
        result = find_compose_file(project_dir)
        assert result is not None
        assert result.name == "docker-compose.yml"

    def test_finds_compose_yml(self, project_dir):
        _write_file(project_dir, "compose.yml", "services: {}")
        result = find_compose_file(project_dir)
        assert result is not None
        assert result.name == "compose.yml"

    def test_finds_local_yml(self, project_dir):
        _write_file(project_dir, "local.yml", "services: {}")
        result = find_compose_file(project_dir)
        assert result is not None
        assert result.name == "local.yml"

    def test_priority_order(self, project_dir):
        """docker-compose.yml has higher priority than local.yml."""
        _write_file(project_dir, "docker-compose.yml", "services: {}")
        _write_file(project_dir, "local.yml", "services: {}")
        result = find_compose_file(project_dir)
        assert result.name == "docker-compose.yml"

    def test_returns_none_when_not_found(self, project_dir):
        result = find_compose_file(project_dir)
        assert result is None


class TestInferTestCommand:
    """Tests for test command inference."""

    def test_detects_pytest_from_pytest_ini(self, project_dir):
        _write_file(project_dir, "pytest.ini")
        assert infer_test_command(project_dir) == "pytest"

    def test_detects_pytest_from_pyproject_toml(self, project_dir):
        _write_file(project_dir, "pyproject.toml")
        assert infer_test_command(project_dir) == "pytest"

    def test_detects_pytest_from_manage_py(self, project_dir):
        _write_file(project_dir, "manage.py")
        assert infer_test_command(project_dir) == "pytest"

    def test_detects_npm_test_from_package_json(self, project_dir):
        _write_file(project_dir, "package.json")
        assert infer_test_command(project_dir) == "npm test"

    def test_defaults_to_pytest(self, project_dir):
        assert infer_test_command(project_dir) == "pytest"


class TestResolveDockerConfig:
    """Tests for auto-discovery config resolution."""

    def test_minimal_config_discovers_everything(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", """\
            services:
              web:
                build: .
                ports:
                  - "8000:8000"
                volumes:
                  - ./src:/app
              db:
                image: postgres
        """)
        _write_file(project_dir, "pytest.ini")

        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project_dir)

        assert resolved["compose_file"] == "docker-compose.yml"
        assert "web" in resolved["services"]
        assert "db" in resolved["services"]
        assert resolved["test_service"] == "web"
        assert resolved["test_command"] == "pytest"
        assert resolved["health_check"]["port"] == 8000

    def test_explicit_values_not_overridden(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", """\
            services:
              web:
                build: .
                volumes:
                  - ./src:/app
              db:
                image: postgres
        """)

        config = {
            "type": "docker-compose",
            "compose_file": "docker-compose.yml",
            "test_service": "db",
            "test_command": "make test",
        }
        resolved = resolve_docker_config(config, project_dir)

        assert resolved["test_service"] == "db"
        assert resolved["test_command"] == "make test"

    def test_no_compose_file_returns_as_is(self, project_dir):
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project_dir)
        assert resolved == config

    def test_discovers_local_yml(self, project_dir):
        _write_file(project_dir, "local.yml", """\
            services:
              django:
                build: .
                ports:
                  - "8002:8002"
                volumes:
                  - ./backend:/app
        """)

        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project_dir)

        assert resolved["compose_file"] == "local.yml"
        assert resolved["test_service"] == "django"

    def test_preserves_explicit_services(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", """\
            services:
              web:
                image: nginx
              db:
                image: postgres
              redis:
                image: redis
        """)

        config = {
            "type": "docker-compose",
            "services": ["web", "db"],
        }
        resolved = resolve_docker_config(config, project_dir)
        assert resolved["services"] == ["web", "db"]


class TestValidateDockerConfig:
    """Tests for config validation."""

    def test_valid_config_returns_no_errors(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", """\
            services:
              web:
                image: nginx
              db:
                image: postgres
        """)

        config = {
            "compose_file": "docker-compose.yml",
            "services": ["web", "db"],
            "test_service": "web",
        }
        errors = validate_docker_config(config, project_dir)
        assert errors == []

    def test_missing_compose_file_error(self, project_dir):
        config = {
            "compose_file": "nonexistent.yml",
            "services": ["web"],
        }
        errors = validate_docker_config(config, project_dir)
        assert len(errors) >= 1
        assert "not found" in errors[0].lower()

    def test_invalid_service_error(self, project_dir):
        _write_file(project_dir, "docker-compose.yml", """\
            services:
              web:
                image: nginx
        """)

        config = {
            "compose_file": "docker-compose.yml",
            "services": ["web", "nonexistent"],
            "test_service": "web",
        }
        errors = validate_docker_config(config, project_dir)
        assert len(errors) >= 1
        assert "nonexistent" in errors[0]

    def test_test_service_not_in_services_error(self, project_dir):
        config = {
            "compose_file": "docker-compose.yml",
            "services": ["web", "db"],
            "test_service": "worker",
        }
        errors = validate_docker_config(config, project_dir)
        assert any("test_service" in e for e in errors)

    def test_no_compose_file_at_all(self, project_dir):
        config = {}
        errors = validate_docker_config(config, project_dir)
        assert len(errors) >= 1
        assert any("compose file" in e.lower() for e in errors)
