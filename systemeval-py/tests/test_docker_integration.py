"""Integration tests for Docker testing expansion.

End-to-end tests that validate the full pipeline:
- DockerComposeEnvironment construction with auto-discovery
- Config resolution from minimal → fully resolved
- Preflight check chains
- Attach mode behavior
- Remote Docker host config
- CLI docker subcommands via CliRunner
- Edge cases and error paths
"""
from pathlib import Path
from textwrap import dedent
from unittest.mock import patch, MagicMock

import pytest
from click.testing import CliRunner

from systemeval.config.environments import (
    DockerComposeEnvConfig,
    DockerHostConfig,
    parse_environment_config,
)
from systemeval.environments.implementations.docker_compose import DockerComposeEnvironment
from systemeval.utils.docker.compose_parser import parse_compose_file
from systemeval.utils.docker.discovery import resolve_docker_config, validate_docker_config
from systemeval.utils.docker.preflight import run_preflight, PreflightResult


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def project(tmp_path):
    """Create a realistic project directory with a compose file."""
    compose = tmp_path / "docker-compose.yml"
    compose.write_text(dedent("""\
        services:
          django:
            build: ./
            image: myapp_django
            ports:
              - "8002:8002"
            volumes:
              - ./backend:/app
            depends_on:
              - redis
            environment:
              DJANGO_SETTINGS_MODULE: config.settings.local
              DATABASE_URL: postgres://postgres:postgres@postgres:5432/myapp
            healthcheck:
              test: ["CMD", "curl", "-f", "http://localhost:8002/api/v1/health/"]
              interval: 10s
              timeout: 5s
          postgres:
            image: postgres:15
            ports:
              - "5434:5432"
          redis:
            image: redis:6
    """))
    (tmp_path / "pytest.ini").write_text("")
    (tmp_path / "backend").mkdir()
    return tmp_path


@pytest.fixture
def minimal_project(tmp_path):
    """Create a project with only a compose file — no other hints."""
    compose = tmp_path / "compose.yml"
    compose.write_text(dedent("""\
        services:
          app:
            build: .
            ports:
              - "3000:3000"
          db:
            image: postgres
    """))
    return tmp_path


@pytest.fixture
def local_yml_project(tmp_path):
    """Project using local.yml (like sentinal)."""
    compose = tmp_path / "local.yml"
    compose.write_text(dedent("""\
        services:
          django:
            build: ./
            image: sentinal_django
            ports:
              - "8002:8002"
            volumes:
              - ./backend:/app
            depends_on:
              - redis
          postgres:
            image: sentinal_postgres
            build: ./
            ports:
              - "5434:5434"
          redis:
            image: redis:6
          celeryworker:
            image: sentinal_django
            build: ./
            volumes:
              - ./backend:/app
            depends_on:
              - redis
          nginx:
            image: sentinal_nginx
            build: ./compose/local/nginx
            ports:
              - "80:80"
            depends_on:
              - django
    """))
    (tmp_path / "manage.py").write_text("")
    (tmp_path / "backend").mkdir()
    return tmp_path


# ---------------------------------------------------------------------------
# Auto-Discovery Pipeline Tests
# ---------------------------------------------------------------------------

class TestAutoDiscoveryPipeline:
    """Test the full auto-discovery flow from minimal config to resolved."""

    def test_minimal_config_resolves_everything(self, project):
        """From just {type: docker-compose} we get all fields populated."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project)

        assert resolved["compose_file"] == "docker-compose.yml"
        assert "django" in resolved["services"]
        assert "postgres" in resolved["services"]
        assert "redis" in resolved["services"]
        assert resolved["test_service"] == "django"
        assert resolved["test_command"] == "pytest"
        assert resolved["health_check"]["port"] == 8002
        assert resolved["health_check"]["service"] == "django"
        assert resolved["health_check"]["endpoint"] == "/api/v1/health/"

    def test_discovers_compose_yml(self, minimal_project):
        """Discovers compose.yml (not just docker-compose.yml)."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, minimal_project)

        assert resolved["compose_file"] == "compose.yml"
        assert resolved["test_service"] == "app"

    def test_discovers_local_yml(self, local_yml_project):
        """Discovers local.yml and picks django as test service."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, local_yml_project)

        assert resolved["compose_file"] == "local.yml"
        assert resolved["test_service"] == "django"
        assert len(resolved["services"]) == 5

    def test_explicit_values_not_overridden(self, project):
        """User-provided values take precedence over auto-detection."""
        config = {
            "type": "docker-compose",
            "compose_file": "docker-compose.yml",
            "test_service": "postgres",
            "test_command": "make test",
            "services": ["django", "postgres"],
        }
        resolved = resolve_docker_config(config, project)

        assert resolved["test_service"] == "postgres"
        assert resolved["test_command"] == "make test"
        assert resolved["services"] == ["django", "postgres"]

    def test_no_compose_file_returns_input(self, tmp_path):
        """Empty directory with no compose file returns config unchanged."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, tmp_path)
        assert resolved == config

    def test_health_endpoint_from_healthcheck(self, project):
        """Health endpoint extracted from Docker healthcheck directive."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project)
        assert resolved["health_check"]["endpoint"] == "/api/v1/health/"

    def test_environment_variables_extracted(self, project):
        """Test-relevant env vars extracted from compose service."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project)
        env = resolved.get("env", {})
        assert "DJANGO_SETTINGS_MODULE" in env


class TestValidationPipeline:
    """Test config validation catches real problems."""

    def test_valid_config_passes(self, project):
        """Fully resolved config validates cleanly."""
        config = {"type": "docker-compose"}
        resolved = resolve_docker_config(config, project)
        errors = validate_docker_config(resolved, project)
        assert errors == []

    def test_missing_compose_file_detected(self, tmp_path):
        """Missing compose file is caught by validation."""
        config = {"compose_file": "nonexistent.yml", "services": ["web"]}
        errors = validate_docker_config(config, tmp_path)
        assert len(errors) >= 1
        assert "not found" in errors[0].lower()

    def test_invalid_service_detected(self, project):
        """Service not in compose file is caught."""
        config = {
            "compose_file": "docker-compose.yml",
            "services": ["django", "nonexistent_service"],
            "test_service": "django",
        }
        errors = validate_docker_config(config, project)
        assert any("nonexistent_service" in e for e in errors)

    def test_test_service_not_in_services_detected(self, project):
        """test_service must be in services list."""
        config = {
            "compose_file": "docker-compose.yml",
            "services": ["django", "postgres"],
            "test_service": "celery",
        }
        errors = validate_docker_config(config, project)
        assert any("test_service" in e for e in errors)

    def test_no_config_at_all(self, tmp_path):
        """Empty config on empty directory returns errors."""
        errors = validate_docker_config({}, tmp_path)
        assert len(errors) >= 1


# ---------------------------------------------------------------------------
# Preflight Check Pipeline Tests
# ---------------------------------------------------------------------------

class TestPreflightPipeline:
    """Test preflight checks run in correct order and report properly."""

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value=None)
    def test_stops_early_without_docker(self, mock_bin, project):
        """No docker binary → immediate fail, no further checks."""
        result = run_preflight(project_dir=project)
        assert result.ok is False
        assert any("not installed" in e.lower() for e in result.errors)
        # Should only have 1 check (docker_binary)
        assert len(result.checks) == 1

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=False)
    def test_stops_early_without_daemon(self, mock_run, mock_bin, project):
        """Docker installed but daemon not running → fail after 2 checks."""
        result = run_preflight(project_dir=project)
        assert result.ok is False
        assert any("daemon" in e.lower() for e in result.errors)
        assert len(result.checks) == 2

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value=None)
    def test_stops_early_without_compose(self, mock_ver, mock_run, mock_bin, project):
        """No compose → fail after 3 checks."""
        result = run_preflight(project_dir=project)
        assert result.ok is False
        assert any("compose" in e.lower() for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    def test_full_pass_with_compose_file(self, mock_ver, mock_run, mock_bin, project):
        """All preflight checks pass with valid project."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
        )
        assert result.ok is True
        assert len(result.errors) == 0

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    def test_validates_services_in_compose(self, mock_ver, mock_run, mock_bin, project):
        """Preflight validates that requested services exist in compose file."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
            services=["django", "ghost_service"],
        )
        assert result.ok is False
        assert any("ghost_service" in e for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    @patch("systemeval.utils.docker.preflight.check_containers_running", return_value=[])
    def test_attach_fails_when_no_containers_running(self, mock_containers, mock_ver, mock_run, mock_bin, project):
        """Attach mode fails if no containers are running."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
            attach=True,
        )
        assert result.ok is False
        assert any("no containers" in e.lower() for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    @patch("systemeval.utils.docker.preflight.check_containers_running", return_value=["postgres", "redis"])
    def test_attach_fails_when_test_service_not_running(self, mock_containers, mock_ver, mock_run, mock_bin, project):
        """Attach mode fails if test service is not in running containers."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
            attach=True,
            test_service="django",
        )
        assert result.ok is False
        assert any("django" in e.lower() for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    @patch("systemeval.utils.docker.preflight.check_containers_running", return_value=["django", "postgres", "redis"])
    def test_attach_passes_when_test_service_running(self, mock_containers, mock_ver, mock_run, mock_bin, project):
        """Attach mode passes when test service is among running containers."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
            attach=True,
            test_service="django",
        )
        assert result.ok is True

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="v1:1.29.2")
    def test_warns_on_compose_v1(self, mock_ver, mock_run, mock_bin, project):
        """Compose v1 generates a warning but still passes."""
        result = run_preflight(
            project_dir=project,
            compose_file="docker-compose.yml",
        )
        assert result.ok is True
        assert any("v1" in w for w in result.warnings)


# ---------------------------------------------------------------------------
# DockerComposeEnvironment Construction Tests
# ---------------------------------------------------------------------------

class TestDockerComposeEnvironmentConstruction:
    """Test DockerComposeEnvironment is built correctly from configs."""

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_auto_discovery_populates_fields(self, mock_preflight, project):
        """Auto-discovery fills in compose_file, services, test_service, etc."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
        })
        assert env.compose_file == "docker-compose.yml"
        assert env.test_service == "django"
        assert "django" in env.services
        assert "postgres" in env.services
        assert env.test_command == "pytest"
        assert env.health_config.port == 8002

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_attach_mode_flag(self, mock_preflight, project):
        """Attach mode is correctly stored."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "attach": True,
            "working_dir": str(project),
        })
        assert env.attach is True

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_auto_discover_disabled(self, mock_preflight, project):
        """auto_discover=False uses raw config values."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "auto_discover": False,
            "compose_file": "custom.yml",
            "test_service": "myapp",
            "working_dir": str(project),
        })
        assert env.compose_file == "custom.yml"
        assert env.test_service == "myapp"

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_remote_docker_config(self, mock_preflight, project):
        """Remote Docker host config is passed to DockerResourceManager."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "docker": {
                "host": "ssh://deploy@192.168.1.100",
                "context": "production",
            },
        })
        assert env._docker_host == "ssh://deploy@192.168.1.100"
        assert env._docker_context == "production"
        assert env.docker.docker_host == "ssh://deploy@192.168.1.100"
        assert env.docker.docker_context == "production"

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_health_config_from_compose(self, mock_preflight, project):
        """Health check config is auto-populated from compose healthcheck."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
        })
        assert env.health_config.service == "django"
        assert env.health_config.port == 8002
        assert env.health_config.endpoint == "/api/v1/health/"

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_explicit_health_config_used(self, mock_preflight, project):
        """Explicit health config overrides auto-detection."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "health_check": {
                "service": "django",
                "endpoint": "/ready/",
                "port": 9999,
                "timeout": 30,
            },
        })
        assert env.health_config.endpoint == "/ready/"
        assert env.health_config.port == 9999


# ---------------------------------------------------------------------------
# DockerComposeEnvironment Setup/Teardown Behavior Tests
# ---------------------------------------------------------------------------

class TestDockerComposeEnvironmentBehavior:
    """Test setup/teardown behavior in different modes."""

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_attach_setup_skips_build_and_up(self, mock_preflight, project):
        """Attach mode setup does not call build or up."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "attach": True,
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        # Mock docker manager so we can verify it's NOT called
        env.docker = MagicMock()
        result = env.setup()

        assert result.success is True
        assert "attach" in result.message.lower()
        assert result.details.get("mode") == "attach"
        env.docker.build.assert_not_called()
        env.docker.up.assert_not_called()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_attach_teardown_skips_down(self, mock_preflight, project):
        """Attach mode teardown does not call docker down."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "attach": True,
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        env.docker = MagicMock()
        env.setup()  # sets _is_up = True
        env.teardown()

        env.docker.down.assert_not_called()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_managed_setup_calls_build_and_up(self, mock_preflight, project):
        """Managed mode setup calls build then up."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        env.docker = MagicMock()
        env.docker.build.return_value = MagicMock(success=True, duration=5.0)
        env.docker.up.return_value = MagicMock(success=True, duration=3.0, stderr="")
        result = env.setup()

        assert result.success is True
        env.docker.build.assert_called_once()
        env.docker.up.assert_called_once()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_managed_teardown_calls_down(self, mock_preflight, project):
        """Managed mode teardown calls docker down."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        env.docker = MagicMock()
        env.docker.build.return_value = MagicMock(success=True, duration=1.0)
        env.docker.up.return_value = MagicMock(success=True, duration=1.0, stderr="")
        env.setup()
        env.teardown()

        env.docker.down.assert_called_once()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_skip_build_skips_build(self, mock_preflight, project):
        """skip_build=True skips build phase."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
            "skip_build": True,
        })
        env.docker = MagicMock()
        env.docker.up.return_value = MagicMock(success=True, duration=1.0, stderr="")
        result = env.setup()

        assert result.success is True
        env.docker.build.assert_not_called()
        env.docker.up.assert_called_once()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_build_failure_stops_setup(self, mock_preflight, project):
        """If build fails, setup stops and does not call up."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        env.docker = MagicMock()
        env.docker.build.return_value = MagicMock(success=False, error="Build failed", duration=2.0)
        result = env.setup()

        assert result.success is False
        assert "build" in result.message.lower()
        env.docker.up.assert_not_called()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_up_failure_reported(self, mock_preflight, project):
        """If docker up fails, setup reports failure."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        env.docker = MagicMock()
        env.docker.build.return_value = MagicMock(success=True, duration=1.0)
        env.docker.up.return_value = MagicMock(success=False, duration=1.0, stderr="port already in use")
        result = env.setup()

        assert result.success is False
        assert "port already in use" in result.message

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_run_tests_requires_up(self, mock_preflight, project):
        """run_tests returns error if environment is not up."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })
        result = env.run_tests()
        assert result.errors == 1
        assert result.exit_code == 2


# ---------------------------------------------------------------------------
# DockerResourceManager Configuration Tests
# ---------------------------------------------------------------------------

class TestDockerResourceManagerConfig:
    """Test DockerResourceManager is configured correctly."""

    def test_default_config(self):
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        mgr = DockerResourceManager()
        assert mgr.compose_file == "docker-compose.yml"
        assert mgr.docker_host is None
        assert mgr.docker_context is None

    def test_remote_docker_host(self):
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        mgr = DockerResourceManager(
            docker_host="ssh://deploy@192.168.1.100",
            docker_context="staging",
        )
        assert mgr.docker_host == "ssh://deploy@192.168.1.100"
        assert mgr.docker_context == "staging"

    def test_get_env_with_remote(self):
        """_get_env() returns DOCKER_HOST/DOCKER_CONTEXT when set."""
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        import os
        mgr = DockerResourceManager(docker_host="tcp://remote:2376")
        env = mgr._get_env()
        assert env is not None
        assert env["DOCKER_HOST"] == "tcp://remote:2376"

    def test_get_env_without_remote(self):
        """_get_env() returns None when no remote config."""
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        mgr = DockerResourceManager()
        assert mgr._get_env() is None

    def test_compose_cmd_includes_file(self):
        """_compose_cmd builds correct command with compose file."""
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        mgr = DockerResourceManager(compose_file="local.yml")
        cmd = mgr._compose_cmd("up", "-d")
        assert cmd == ["docker", "compose", "-f", "local.yml", "up", "-d"]

    def test_compose_cmd_includes_project_name(self):
        """_compose_cmd includes -p flag when project_name is set."""
        from systemeval.utils.docker.docker_manager import DockerResourceManager
        mgr = DockerResourceManager(compose_file="local.yml", project_name="myproj")
        cmd = mgr._compose_cmd("up")
        assert "-p" in cmd
        assert "myproj" in cmd


# ---------------------------------------------------------------------------
# Pydantic Config Model Tests
# ---------------------------------------------------------------------------

class TestConfigModels:
    """Test Pydantic config models for new Docker features."""

    def test_docker_compose_env_config_defaults(self):
        """DockerComposeEnvConfig has sensible defaults."""
        cfg = DockerComposeEnvConfig()
        assert cfg.compose_file is None
        assert cfg.test_service is None
        assert cfg.services == []
        assert cfg.attach is False
        assert cfg.auto_discover is True
        assert cfg.docker is None

    def test_docker_compose_env_config_with_attach(self):
        cfg = DockerComposeEnvConfig(attach=True)
        assert cfg.attach is True

    def test_docker_compose_env_config_with_remote(self):
        cfg = DockerComposeEnvConfig(
            docker=DockerHostConfig(host="ssh://user@host", context="prod"),
        )
        assert cfg.docker.host == "ssh://user@host"
        assert cfg.docker.context == "prod"

    def test_docker_host_config_all_fields(self):
        cfg = DockerHostConfig(
            host="tcp://192.168.1.100:2376",
            context="remote-prod",
            tls_cert="/certs/cert.pem",
            tls_key="/certs/key.pem",
            tls_ca="/certs/ca.pem",
        )
        assert cfg.host == "tcp://192.168.1.100:2376"
        assert cfg.tls_cert == "/certs/cert.pem"

    def test_parse_docker_compose_config(self):
        """parse_environment_config handles docker-compose type."""
        config = parse_environment_config("backend", {
            "type": "docker-compose",
            "attach": True,
            "compose_file": "local.yml",
            "auto_discover": False,
        })
        assert isinstance(config, DockerComposeEnvConfig)
        assert config.attach is True
        assert config.compose_file == "local.yml"

    def test_docker_compose_config_serialization(self):
        """Config round-trips through model_dump."""
        cfg = DockerComposeEnvConfig(
            compose_file="local.yml",
            services=["web", "db"],
            test_service="web",
            attach=True,
            docker=DockerHostConfig(host="tcp://remote:2376"),
        )
        dumped = cfg.model_dump()
        assert dumped["attach"] is True
        assert dumped["docker"]["host"] == "tcp://remote:2376"
        assert dumped["services"] == ["web", "db"]


# ---------------------------------------------------------------------------
# CLI Docker Subcommands Tests
# ---------------------------------------------------------------------------

class TestCLIDockerCommands:
    """Test CLI docker subcommands compile and run."""

    @pytest.fixture
    def runner(self):
        return CliRunner()

    @pytest.fixture
    def cli(self):
        from systemeval.cli_main import main
        return main

    def test_docker_group_exists(self, runner, cli):
        result = runner.invoke(cli, ["docker", "--help"])
        assert result.exit_code == 0
        assert "status" in result.output
        assert "exec" in result.output
        assert "logs" in result.output
        assert "ready" in result.output

    def test_docker_status_help(self, runner, cli):
        result = runner.invoke(cli, ["docker", "status", "--help"])
        assert result.exit_code == 0
        assert "--env" in result.output
        assert "--config" in result.output

    def test_docker_exec_help(self, runner, cli):
        result = runner.invoke(cli, ["docker", "exec", "--help"])
        assert result.exit_code == 0
        assert "--service" in result.output
        assert "COMMAND" in result.output

    def test_docker_logs_help(self, runner, cli):
        result = runner.invoke(cli, ["docker", "logs", "--help"])
        assert result.exit_code == 0
        assert "--follow" in result.output
        assert "--tail" in result.output

    def test_docker_ready_help(self, runner, cli):
        result = runner.invoke(cli, ["docker", "ready", "--help"])
        assert result.exit_code == 0
        assert "--env" in result.output

    def test_test_command_has_attach_flag(self, runner, cli):
        result = runner.invoke(cli, ["test", "--help"])
        assert result.exit_code == 0
        assert "--attach" in result.output


# ---------------------------------------------------------------------------
# Compose Parser Integration Tests
# ---------------------------------------------------------------------------

class TestComposeParserIntegration:
    """Test compose parser handles real-world compose files."""

    def test_multi_service_compose(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert len(info.service_names) == 3
        assert info.get_test_service() == "django"
        assert info.get_health_port("django") == 8002
        assert info.get_health_endpoint("django") == "/api/v1/health/"

    def test_service_dependencies_parsed(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert "redis" in info.services["django"].depends_on

    def test_build_context_parsed(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert info.services["django"].build_context == "./"

    def test_source_mount_detected(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert info.services["django"].has_source_mount is True
        assert info.services["postgres"].has_source_mount is False

    def test_environment_parsed(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        env = info.services["django"].environment
        assert env["DJANGO_SETTINGS_MODULE"] == "config.settings.local"

    def test_image_parsed(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert info.services["postgres"].image == "postgres:15"
        assert info.services["redis"].image == "redis:6"

    def test_health_port_no_ports(self, project):
        info = parse_compose_file(project / "docker-compose.yml")
        assert info.get_health_port("redis") is None

    def test_empty_compose_file(self, tmp_path):
        f = tmp_path / "docker-compose.yml"
        f.write_text("")
        info = parse_compose_file(f)
        assert info.service_names == []

    def test_nonexistent_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            parse_compose_file(tmp_path / "nope.yml")

    def test_complex_port_formats(self, tmp_path):
        """Handles various port specification formats."""
        f = tmp_path / "docker-compose.yml"
        f.write_text(dedent("""\
            services:
              a:
                image: nginx
                ports:
                  - 8080
              b:
                image: nginx
                ports:
                  - "9090:80"
              c:
                image: nginx
                ports:
                  - "0.0.0.0:3000:3000"
              d:
                image: nginx
                ports:
                  - target: 5432
                    published: 5434
        """))
        info = parse_compose_file(f)
        assert info.services["a"].ports == [(8080, 8080)]
        assert info.services["b"].ports == [(9090, 80)]
        assert info.services["c"].ports == [(3000, 3000)]
        assert info.services["d"].ports == [(5434, 5432)]


# ---------------------------------------------------------------------------
# Full Pipeline Tests (discovery → validation → environment → setup)
# ---------------------------------------------------------------------------

class TestFullPipeline:
    """Test the entire flow from raw config dict to environment setup."""

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_minimal_config_to_working_environment(self, mock_preflight, project):
        """The minimal 1-field config results in a usable environment."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
        })

        # Everything was auto-detected
        assert env.compose_file == "docker-compose.yml"
        assert env.test_service == "django"
        assert env.test_command == "pytest"
        assert env.health_config.port == 8002

        # Setup in attach mode
        env.attach = True
        env.docker = MagicMock()
        result = env.setup()
        assert result.success is True
        env.docker.build.assert_not_called()
        env.docker.up.assert_not_called()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_local_yml_project_full_flow(self, mock_preflight, local_yml_project):
        """local.yml project (like sentinal) works through full flow."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(local_yml_project),
        })
        assert env.compose_file == "local.yml"
        assert env.test_service == "django"
        assert len(env.services) == 5

        # Verify it would call build + up in managed mode
        env.docker = MagicMock()
        env.docker.build.return_value = MagicMock(success=True, duration=10.0)
        env.docker.up.return_value = MagicMock(success=True, duration=5.0, stderr="")
        result = env.setup()
        assert result.success is True
        env.docker.build.assert_called_once()
        env.docker.up.assert_called_once()

    def test_preflight_failure_blocks_setup(self, project):
        """Preflight failure prevents setup from proceeding."""
        env = DockerComposeEnvironment("backend", {
            "type": "docker-compose",
            "working_dir": str(project),
            "auto_discover": False,
            "compose_file": "docker-compose.yml",
            "test_service": "django",
        })

        # Simulate preflight failure
        from systemeval.environments.base import SetupResult
        with patch.object(env, '_run_preflight', return_value=SetupResult(
            success=False,
            message="Pre-flight checks failed:\ndocker_binary: not installed",
            duration=0.0,
        )):
            env.docker = MagicMock()
            result = env.setup()
            assert result.success is False
            assert "pre-flight" in result.message.lower()
            env.docker.build.assert_not_called()

    @patch.object(DockerComposeEnvironment, '_run_preflight', return_value=None)
    def test_remote_docker_flows_through(self, mock_preflight, project):
        """Remote Docker config propagates from config → environment → manager."""
        config = {
            "type": "docker-compose",
            "working_dir": str(project),
            "docker": {
                "host": "ssh://deploy@prod-server",
            },
        }
        env = DockerComposeEnvironment("prod", config)

        # Verify it flows through to DockerResourceManager
        assert env.docker.docker_host == "ssh://deploy@prod-server"

        # Verify _get_env includes DOCKER_HOST
        env_vars = env.docker._get_env()
        assert env_vars["DOCKER_HOST"] == "ssh://deploy@prod-server"
