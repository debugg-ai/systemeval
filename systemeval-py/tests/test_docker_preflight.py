"""Tests for Docker pre-flight checks.

Covers:
- Docker binary detection
- Docker daemon availability
- Compose version detection
- Compose file validation
- Running container detection
- Full preflight result aggregation
"""
from pathlib import Path
from unittest.mock import patch, MagicMock
import subprocess

import pytest

from systemeval.utils.docker.preflight import (
    PreflightResult,
    check_docker_binary,
    check_docker_running,
    check_docker_compose_version,
    check_compose_file,
    run_preflight,
)


class TestPreflightResult:
    """Tests for PreflightResult dataclass."""

    def test_starts_ok(self):
        result = PreflightResult(ok=True)
        assert result.ok is True
        assert result.errors == []
        assert result.warnings == []

    def test_add_pass(self):
        result = PreflightResult(ok=True)
        result.add_pass("test_check", "All good")
        assert len(result.checks) == 1
        assert result.checks[0]["status"] == "pass"
        assert result.ok is True

    def test_add_fail_sets_not_ok(self):
        result = PreflightResult(ok=True)
        result.add_fail("test_check", "Something wrong", "Fix it")
        assert result.ok is False
        assert len(result.errors) == 1
        assert "Fix it" in result.errors[0]

    def test_add_warn_keeps_ok(self):
        result = PreflightResult(ok=True)
        result.add_warn("test_check", "Minor issue")
        assert result.ok is True
        assert len(result.warnings) == 1


class TestCheckDockerBinary:
    """Tests for Docker binary detection."""

    @patch("shutil.which", return_value="/usr/local/bin/docker")
    def test_found(self, mock_which):
        assert check_docker_binary() == "/usr/local/bin/docker"

    @patch("shutil.which", return_value=None)
    def test_not_found(self, mock_which):
        assert check_docker_binary() is None


class TestCheckDockerRunning:
    """Tests for Docker daemon availability check."""

    @patch("subprocess.run")
    def test_running(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0)
        assert check_docker_running() is True

    @patch("subprocess.run")
    def test_not_running(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1)
        assert check_docker_running() is False

    @patch("subprocess.run", side_effect=FileNotFoundError)
    def test_docker_not_installed(self, mock_run):
        assert check_docker_running() is False

    @patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="docker", timeout=10))
    def test_timeout(self, mock_run):
        assert check_docker_running() is False


class TestCheckDockerComposeVersion:
    """Tests for Docker Compose version detection."""

    @patch("subprocess.run")
    def test_v2(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="2.24.5\n")
        assert check_docker_compose_version() == "2.24.5"

    @patch("subprocess.run")
    def test_not_available(self, mock_run):
        mock_run.side_effect = FileNotFoundError
        assert check_docker_compose_version() is None


class TestCheckComposeFile:
    """Tests for compose file existence check."""

    def test_explicit_file_exists(self, tmp_path):
        (tmp_path / "custom.yml").write_text("services: {}")
        result = check_compose_file(tmp_path, "custom.yml")
        assert result is not None
        assert result.name == "custom.yml"

    def test_explicit_file_not_found(self, tmp_path):
        result = check_compose_file(tmp_path, "nonexistent.yml")
        assert result is None

    def test_auto_discover(self, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("services: {}")
        result = check_compose_file(tmp_path)
        assert result is not None


class TestRunPreflight:
    """Tests for full preflight check execution."""

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value=None)
    def test_fails_without_docker(self, mock_binary, tmp_path):
        result = run_preflight(project_dir=tmp_path)
        assert result.ok is False
        assert any("not installed" in e.lower() for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=False)
    def test_fails_without_daemon(self, mock_running, mock_binary, tmp_path):
        result = run_preflight(project_dir=tmp_path)
        assert result.ok is False
        assert any("daemon" in e.lower() for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    def test_passes_with_compose_file(self, mock_version, mock_running, mock_binary, tmp_path):
        (tmp_path / "docker-compose.yml").write_text("services:\n  web:\n    image: nginx")
        result = run_preflight(
            project_dir=tmp_path,
            compose_file="docker-compose.yml",
        )
        assert result.ok is True

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value="2.24.5")
    def test_validates_services(self, mock_version, mock_running, mock_binary, tmp_path):
        (tmp_path / "docker-compose.yml").write_text(
            "services:\n  web:\n    image: nginx\n  db:\n    image: postgres"
        )
        result = run_preflight(
            project_dir=tmp_path,
            compose_file="docker-compose.yml",
            services=["web", "nonexistent"],
        )
        assert result.ok is False
        assert any("nonexistent" in e for e in result.errors)

    @patch("systemeval.utils.docker.preflight.check_docker_binary", return_value="/usr/bin/docker")
    @patch("systemeval.utils.docker.preflight.check_docker_running", return_value=True)
    @patch("systemeval.utils.docker.preflight.check_docker_compose_version", return_value=None)
    def test_fails_without_compose(self, mock_version, mock_running, mock_binary, tmp_path):
        result = run_preflight(project_dir=tmp_path)
        assert result.ok is False
        assert any("compose" in e.lower() for e in result.errors)
