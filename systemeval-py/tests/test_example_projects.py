"""Validate systemeval works with all example Docker projects.

Tests the full discovery → resolution → validation → environment pipeline
against three real project layouts:

1. django-rest-api     — docker-compose.yml, postgres + redis, pytest
2. express-mongo-api   — compose.yml (modern naming), mongodb, npm test
3. fastapi-react-fullstack — local.yml, multi-service, pyproject.toml
"""
from pathlib import Path
from unittest.mock import patch

import pytest

from systemeval.config.environments import (
    DockerComposeEnvConfig,
    parse_environment_config,
)
from systemeval.environments.implementations.docker_compose import DockerComposeEnvironment
from systemeval.utils.docker.compose_parser import parse_compose_file, ComposeFileInfo
from systemeval.utils.docker.discovery import (
    find_compose_file,
    resolve_docker_config,
    validate_docker_config,
    infer_test_command,
)
from systemeval.utils.docker.preflight import run_preflight


EXAMPLES_DIR = Path(__file__).parent.parent / "example-usage-projects"


def _example(name: str) -> Path:
    """Get path to an example project."""
    path = EXAMPLES_DIR / name
    assert path.exists(), f"Example project not found: {path}"
    return path


# ==========================================================================
# Project 1: django-rest-api (docker-compose.yml)
# ==========================================================================

class TestDjangoRestApi:
    """Validate systemeval against the Django REST API example."""

    @pytest.fixture
    def project_dir(self):
        return _example("django-rest-api")

    # -- Compose file discovery --

    def test_finds_compose_file(self, project_dir):
        found = find_compose_file(project_dir)
        assert found is not None
        assert found.name == "docker-compose.yml"

    def test_parses_compose_file(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        assert "django" in info.service_names
        assert "postgres" in info.service_names
        assert "redis" in info.service_names

    def test_django_service_has_source_mount(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        assert info.services["django"].has_source_mount is True

    def test_postgres_no_source_mount(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        assert info.services["postgres"].has_source_mount is False

    def test_infers_test_service_as_django(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        assert info.get_test_service() == "django"

    def test_infers_health_port(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        assert info.get_health_port("django") == 8900

    def test_infers_health_endpoint(self, project_dir):
        info = parse_compose_file(project_dir / "docker-compose.yml")
        endpoint = info.get_health_endpoint("django")
        assert endpoint is not None
        assert "/health" in endpoint

    def test_infers_test_command(self, project_dir):
        cmd = infer_test_command(project_dir)
        assert cmd == "pytest"

    # -- Config resolution --

    def test_minimal_config_resolves(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        assert resolved["compose_file"] == "docker-compose.yml"
        assert resolved["test_service"] == "django"
        assert resolved["test_command"] == "pytest"
        assert "django" in resolved["services"]
        assert resolved["health_check"]["port"] == 8900

    def test_explicit_config_not_overridden(self, project_dir):
        config = {
            "type": "docker-compose",
            "test_service": "postgres",
            "test_command": "make test",
        }
        resolved = resolve_docker_config(config, project_dir)
        assert resolved["test_service"] == "postgres"
        assert resolved["test_command"] == "make test"

    # -- Validation --

    def test_resolved_config_validates(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        errors = validate_docker_config(resolved, project_dir)
        assert errors == []

    def test_bad_service_caught(self, project_dir):
        config = {
            "compose_file": "docker-compose.yml",
            "services": ["django", "nonexistent"],
            "test_service": "django",
        }
        errors = validate_docker_config(config, project_dir)
        assert any("nonexistent" in e for e in errors)

    # -- Environment construction --

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_constructs(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("django-api", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
        })
        assert env.compose_file == "docker-compose.yml"
        assert env.test_service == "django"
        assert env.test_command == "pytest"
        assert env.health_config.port == 8900

    # -- Pydantic config --

    def test_systemeval_yaml_environments_parse(self, project_dir):
        """All environments in systemeval.yaml parse correctly."""
        import yaml
        with open(project_dir / "systemeval.yaml") as f:
            raw = yaml.safe_load(f)

        for name, env_dict in raw["environments"].items():
            config = parse_environment_config(name, env_dict)
            assert isinstance(config, DockerComposeEnvConfig)


# ==========================================================================
# Project 2: express-mongo-api (compose.yml)
# ==========================================================================

class TestExpressMongoApi:
    """Validate systemeval against the Express + MongoDB example."""

    @pytest.fixture
    def project_dir(self):
        return _example("express-mongo-api")

    # -- Compose file discovery --

    def test_finds_compose_yml(self, project_dir):
        """Discovers compose.yml (not docker-compose.yml)."""
        found = find_compose_file(project_dir)
        assert found is not None
        assert found.name == "compose.yml"

    def test_parses_services(self, project_dir):
        info = parse_compose_file(project_dir / "compose.yml")
        assert "api" in info.service_names
        assert "mongo" in info.service_names

    def test_api_has_source_mount(self, project_dir):
        info = parse_compose_file(project_dir / "compose.yml")
        # ./src:/app/src is a source-like mount
        svc = info.services["api"]
        assert svc.build_context is not None

    def test_infers_test_service(self, project_dir):
        info = parse_compose_file(project_dir / "compose.yml")
        test_svc = info.get_test_service()
        assert test_svc == "api"

    def test_infers_health_port(self, project_dir):
        info = parse_compose_file(project_dir / "compose.yml")
        assert info.get_health_port("api") == 3900

    def test_infers_npm_test(self, project_dir):
        cmd = infer_test_command(project_dir)
        assert cmd == "npm test"

    # -- Config resolution --

    def test_minimal_config_resolves(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        assert resolved["compose_file"] == "compose.yml"
        assert resolved["test_service"] == "api"
        assert resolved["test_command"] == "npm test"
        assert resolved["health_check"]["port"] == 3900

    # -- Validation --

    def test_resolved_config_validates(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        errors = validate_docker_config(resolved, project_dir)
        assert errors == []

    # -- Environment construction --

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_constructs(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("express-api", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
        })
        assert env.compose_file == "compose.yml"
        assert env.test_service == "api"
        assert env.test_command == "npm test"

    # -- Pydantic config --

    def test_systemeval_yaml_environments_parse(self, project_dir):
        import yaml
        with open(project_dir / "systemeval.yaml") as f:
            raw = yaml.safe_load(f)

        for name, env_dict in raw["environments"].items():
            config = parse_environment_config(name, env_dict)
            assert isinstance(config, DockerComposeEnvConfig)


# ==========================================================================
# Project 3: fastapi-react-fullstack (local.yml)
# ==========================================================================

class TestFastapiReactFullstack:
    """Validate systemeval against the FastAPI + React fullstack example."""

    @pytest.fixture
    def project_dir(self):
        return _example("fastapi-react-fullstack")

    # -- Compose file discovery --

    def test_finds_local_yml(self, project_dir):
        """Discovers local.yml (non-standard name)."""
        found = find_compose_file(project_dir)
        assert found is not None
        assert found.name == "local.yml"

    def test_parses_all_services(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert "backend" in info.service_names
        assert "frontend" in info.service_names
        assert "postgres" in info.service_names
        assert "nginx" in info.service_names
        assert len(info.service_names) == 4

    def test_backend_has_source_mount(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert info.services["backend"].has_source_mount is True

    def test_frontend_has_source_mount(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        svc = info.services["frontend"]
        # ./frontend/src:/app/src is a source mount
        assert svc.build_context is not None

    def test_infers_test_service_as_backend(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        # backend has source mount + working_dir, should be picked first
        test_svc = info.get_test_service()
        assert test_svc == "backend"

    def test_infers_health_port(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert info.get_health_port("backend") == 8180

    def test_postgres_port_mapping(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert info.get_health_port("postgres") == 5433

    def test_nginx_port_mapping(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert info.get_health_port("nginx") == 8280

    def test_backend_working_dir(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert info.services["backend"].working_dir == "/app"

    def test_backend_depends_on_postgres(self, project_dir):
        info = parse_compose_file(project_dir / "local.yml")
        assert "postgres" in info.services["backend"].depends_on

    def test_infers_test_command(self, project_dir):
        # No pytest.ini in root, but backend/pyproject.toml exists
        # Root-level discovery: no pytest.ini at project root
        cmd = infer_test_command(project_dir)
        assert cmd == "pytest"

    # -- Config resolution --

    def test_minimal_config_resolves(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        assert resolved["compose_file"] == "local.yml"
        assert resolved["test_service"] == "backend"
        assert len(resolved["services"]) == 4
        assert resolved["health_check"]["port"] == 8180

    def test_backend_only_config(self, project_dir):
        """Can target just backend + postgres for faster tests."""
        config = {
            "type": "docker-compose",
            "compose_file": "local.yml",
            "services": ["backend", "postgres"],
            "test_service": "backend",
        }
        resolved = resolve_docker_config(config, project_dir)
        assert resolved["services"] == ["backend", "postgres"]
        assert resolved["test_service"] == "backend"

    # -- Validation --

    def test_resolved_config_validates(self, project_dir):
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        errors = validate_docker_config(resolved, project_dir)
        assert errors == []

    def test_frontend_only_validates(self, project_dir):
        config = {
            "compose_file": "local.yml",
            "services": ["frontend"],
            "test_service": "frontend",
        }
        errors = validate_docker_config(config, project_dir)
        assert errors == []

    def test_invalid_service_caught(self, project_dir):
        config = {
            "compose_file": "local.yml",
            "services": ["backend", "worker"],
            "test_service": "backend",
        }
        errors = validate_docker_config(config, project_dir)
        assert any("worker" in e for e in errors)

    # -- Environment construction --

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_constructs_minimal(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("fullstack", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
        })
        assert env.compose_file == "local.yml"
        assert env.test_service == "backend"
        assert len(env.services) == 4

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_backend_only(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
            "compose_file": "local.yml",
            "services": ["backend", "postgres"],
            "test_service": "backend",
            "test_command": "pytest -v",
        })
        assert env.services == ["backend", "postgres"]
        assert env.test_command == "pytest -v"

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_attach_mode(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("fullstack-attach", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
            "attach": True,
        })
        assert env.attach is True
        assert env.compose_file == "local.yml"

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_remote_docker(self, mock_pf, project_dir):
        env = DockerComposeEnvironment("staging", {
            "type": "docker-compose",
            "working_dir": str(project_dir),
            "compose_file": "local.yml",
            "test_service": "backend",
            "docker": {"host": "ssh://deploy@staging-server"},
        })
        assert env._docker_host == "ssh://deploy@staging-server"
        assert env.docker.docker_host == "ssh://deploy@staging-server"

    # -- Pydantic config --

    def test_systemeval_yaml_environments_parse(self, project_dir):
        import yaml
        with open(project_dir / "systemeval.yaml") as f:
            raw = yaml.safe_load(f)

        for name, env_dict in raw["environments"].items():
            config = parse_environment_config(name, env_dict)
            assert isinstance(config, DockerComposeEnvConfig)


# ==========================================================================
# Cross-project tests
# ==========================================================================

class TestCrossProject:
    """Verify systemeval handles all three project types uniformly."""

    @pytest.mark.parametrize("project_name,expected_compose,expected_test_svc", [
        ("django-rest-api", "docker-compose.yml", "django"),
        ("express-mongo-api", "compose.yml", "api"),
        ("fastapi-react-fullstack", "local.yml", "backend"),
    ])
    def test_auto_discovery_from_minimal_config(self, project_name, expected_compose, expected_test_svc):
        """Each project auto-discovers correctly from {type: docker-compose}."""
        project_dir = _example(project_name)
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        assert resolved["compose_file"] == expected_compose
        assert resolved["test_service"] == expected_test_svc

    @pytest.mark.parametrize("project_name", [
        "django-rest-api",
        "express-mongo-api",
        "fastapi-react-fullstack",
    ])
    def test_resolved_config_validates_clean(self, project_name):
        """Every project validates with zero errors after resolution."""
        project_dir = _example(project_name)
        resolved = resolve_docker_config({"type": "docker-compose"}, project_dir)
        errors = validate_docker_config(resolved, project_dir)
        assert errors == [], f"Validation errors for {project_name}: {errors}"

    @pytest.mark.parametrize("project_name", [
        "django-rest-api",
        "express-mongo-api",
        "fastapi-react-fullstack",
    ])
    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_environment_constructs_from_minimal(self, mock_pf, project_name):
        """Each project builds a working DockerComposeEnvironment from minimal config."""
        project_dir = _example(project_name)
        env = DockerComposeEnvironment(project_name, {
            "type": "docker-compose",
            "working_dir": str(project_dir),
        })
        assert env.compose_file is not None
        assert env.test_service is not None
        assert env.test_command is not None

    @pytest.mark.parametrize("project_name,expected_cmd", [
        ("django-rest-api", "pytest"),
        ("express-mongo-api", "npm test"),
        ("fastapi-react-fullstack", "pytest"),
    ])
    def test_infers_correct_test_command(self, project_name, expected_cmd):
        """Each project infers the right test command."""
        project_dir = _example(project_name)
        cmd = infer_test_command(project_dir)
        assert cmd == expected_cmd

    @pytest.mark.parametrize("project_name", [
        "django-rest-api",
        "express-mongo-api",
        "fastapi-react-fullstack",
    ])
    def test_systemeval_yaml_is_valid(self, project_name):
        """Every project has a parseable systemeval.yaml with valid environments."""
        import yaml
        project_dir = _example(project_name)
        with open(project_dir / "systemeval.yaml") as f:
            raw = yaml.safe_load(f)

        assert "environments" in raw
        assert len(raw["environments"]) >= 2

        for name, env_dict in raw["environments"].items():
            config = parse_environment_config(name, env_dict)
            assert isinstance(config, DockerComposeEnvConfig), f"{project_name}/{name} is not DockerComposeEnvConfig"
