"""Tests for Docker Compose file parser.

Covers:
- YAML parsing of docker-compose files
- Service information extraction (ports, volumes, health checks)
- Source code mount detection
- Test service inference heuristics
- Port parsing (short, long, host-only formats)
- Environment variable parsing (list and dict formats)
"""
from pathlib import Path
from textwrap import dedent

import pytest
import yaml

from systemeval.utils.docker.compose_parser import (
    ComposeFileInfo,
    ServiceInfo,
    parse_compose_file,
    _is_source_mount,
    _parse_port,
    _parse_environment,
)


@pytest.fixture
def compose_dir(tmp_path):
    """Create a temp directory for compose files."""
    return tmp_path


def _write_compose(compose_dir, content, filename="docker-compose.yml"):
    """Write a compose file and return its path."""
    path = compose_dir / filename
    path.write_text(dedent(content))
    return path


class TestParsePort:
    """Tests for port parsing utility."""

    def test_integer_port(self):
        assert _parse_port(8000) == (8000, 8000)

    def test_string_single_port(self):
        assert _parse_port("8000") == (8000, 8000)

    def test_string_host_container_port(self):
        assert _parse_port("8002:8000") == (8002, 8000)

    def test_string_with_host_bind(self):
        assert _parse_port("0.0.0.0:8002:8000") == (8002, 8000)

    def test_string_with_protocol(self):
        assert _parse_port("8002:8000/tcp") == (8002, 8000)

    def test_dict_long_syntax(self):
        assert _parse_port({"target": 8000, "published": 8002}) == (8002, 8000)

    def test_dict_target_only(self):
        assert _parse_port({"target": 8000}) == (8000, 8000)

    def test_invalid_returns_none(self):
        assert _parse_port("invalid") is None


class TestParseEnvironment:
    """Tests for environment variable parsing."""

    def test_dict_format(self):
        result = _parse_environment({"FOO": "bar", "NUM": 42})
        assert result == {"FOO": "bar", "NUM": "42"}

    def test_list_format(self):
        result = _parse_environment(["FOO=bar", "BAZ=qux"])
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_list_without_value(self):
        result = _parse_environment(["FOO"])
        assert result == {"FOO": ""}

    def test_none_value_in_dict(self):
        result = _parse_environment({"FOO": None})
        assert result == {"FOO": ""}

    def test_empty_returns_empty(self):
        assert _parse_environment({}) == {}
        assert _parse_environment([]) == {}
        assert _parse_environment(None) == {}


class TestIsSourceMount:
    """Tests for source code mount detection."""

    def test_detects_app_mount(self):
        assert _is_source_mount("./backend:/app") is True

    def test_detects_workspace_mount(self):
        assert _is_source_mount("./src:/workspace") is True

    def test_detects_dot_app_mount(self):
        assert _is_source_mount(".:/app") is True

    def test_rejects_named_volume(self):
        assert _is_source_mount("pgdata:/var/lib/postgresql/data") is False

    def test_rejects_absolute_path(self):
        assert _is_source_mount("/data:/app") is False


class TestParseComposeFile:
    """Tests for full compose file parsing."""

    def test_parses_basic_compose(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                ports:
                  - "8080:80"
              db:
                image: postgres
        """)
        info = parse_compose_file(path)
        assert info.service_names == ["web", "db"]
        assert info.services["web"].ports == [(8080, 80)]
        assert info.services["web"].image == "nginx"

    def test_detects_source_mount(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              django:
                build: .
                volumes:
                  - ./backend:/app
                  - static_files:/app/static
              postgres:
                image: postgres:15
        """)
        info = parse_compose_file(path)
        assert info.services["django"].has_source_mount is True
        assert info.services["postgres"].has_source_mount is False

    def test_parses_working_dir(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              app:
                image: node
                working_dir: /workspace
        """)
        info = parse_compose_file(path)
        assert info.services["app"].working_dir == "/workspace"

    def test_parses_healthcheck(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                healthcheck:
                  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health/"]
                  interval: 10s
                  timeout: 5s
        """)
        info = parse_compose_file(path)
        assert info.services["web"].healthcheck is not None
        assert "curl" in str(info.services["web"].healthcheck["test"])

    def test_parses_depends_on_list(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                depends_on:
                  - db
                  - redis
              db:
                image: postgres
              redis:
                image: redis
        """)
        info = parse_compose_file(path)
        assert info.services["web"].depends_on == ["db", "redis"]

    def test_parses_depends_on_dict(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                depends_on:
                  db:
                    condition: service_healthy
              db:
                image: postgres
        """)
        info = parse_compose_file(path)
        assert info.services["web"].depends_on == ["db"]

    def test_parses_volumes_section(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              db:
                image: postgres
            volumes:
              pgdata:
              backups:
        """)
        info = parse_compose_file(path)
        assert "pgdata" in info.volumes
        assert "backups" in info.volumes

    def test_parses_build_context_string(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              app:
                build: ./backend
        """)
        info = parse_compose_file(path)
        assert info.services["app"].build_context == "./backend"

    def test_parses_build_context_dict(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              app:
                build:
                  context: ./src
                  dockerfile: Dockerfile.dev
        """)
        info = parse_compose_file(path)
        assert info.services["app"].build_context == "./src"

    def test_file_not_found_raises(self, compose_dir):
        with pytest.raises(FileNotFoundError):
            parse_compose_file(compose_dir / "nonexistent.yml")

    def test_empty_file_returns_empty_info(self, compose_dir):
        path = _write_compose(compose_dir, "")
        info = parse_compose_file(path)
        assert info.service_names == []


class TestComposeFileInfoInference:
    """Tests for ComposeFileInfo inference methods."""

    def test_get_test_service_by_source_mount(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              db:
                image: postgres
              django:
                build: .
                volumes:
                  - ./backend:/app
        """)
        info = parse_compose_file(path)
        assert info.get_test_service() == "django"

    def test_get_test_service_by_working_dir(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              db:
                image: postgres
              app:
                image: myapp
                working_dir: /workspace
        """)
        info = parse_compose_file(path)
        assert info.get_test_service() == "app"

    def test_get_test_service_by_common_name(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              postgres:
                image: postgres
              redis:
                image: redis
              django:
                image: myapp
        """)
        info = parse_compose_file(path)
        assert info.get_test_service() == "django"

    def test_get_test_service_by_build_context(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              db:
                image: postgres
              custom_name:
                build: .
        """)
        info = parse_compose_file(path)
        assert info.get_test_service() == "custom_name"

    def test_get_health_port(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                ports:
                  - "8002:8000"
        """)
        info = parse_compose_file(path)
        assert info.get_health_port("web") == 8002

    def test_get_health_port_missing_service(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
        """)
        info = parse_compose_file(path)
        assert info.get_health_port("nonexistent") is None

    def test_get_health_endpoint_from_healthcheck(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                healthcheck:
                  test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health/"]
        """)
        info = parse_compose_file(path)
        assert info.get_health_endpoint("web") == "/api/v1/health/"

    def test_get_health_endpoint_from_env(self, compose_dir):
        path = _write_compose(compose_dir, """\
            services:
              web:
                image: nginx
                environment:
                  HEALTH_CHECK_PATH: /healthz
        """)
        info = parse_compose_file(path)
        assert info.get_health_endpoint("web") == "/healthz"
