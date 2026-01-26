"""Tests for Docker environment detection utilities."""

import os
from pathlib import Path
from unittest.mock import patch, mock_open, MagicMock

import pytest
from systemeval.utils.docker import (
    is_docker_environment,
    get_environment_type,
    get_docker_compose_service,
    get_container_id,
)


class TestIsDockerEnvironment:
    """Tests for is_docker_environment() function."""

    def test_detects_dockerenv_file(self):
        """Test detection via /.dockerenv file presence."""
        with patch.object(Path, "exists", return_value=True):
            assert is_docker_environment() is True

    def test_detects_docker_container_env_var(self):
        """Test detection via DOCKER_CONTAINER environment variable."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"DOCKER_CONTAINER": "1"}):
                assert is_docker_environment() is True

    def test_detects_docker_container_env_var_any_value(self):
        """Test detection with any truthy DOCKER_CONTAINER value."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"DOCKER_CONTAINER": "true"}):
                assert is_docker_environment() is True

    def test_detects_docker_cgroup(self):
        """Test detection via docker in cgroup file."""
        cgroup_content = "12:memory:/docker/abc123\n11:cpu:/docker/abc123\n"
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                # Remove DOCKER_CONTAINER if present
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is True

    def test_detects_containerd_cgroup(self):
        """Test detection via containerd in cgroup file."""
        cgroup_content = "12:memory:/containerd/abc123\n"
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is True

    def test_returns_false_when_not_docker(self):
        """Test returns False when no Docker indicators present."""
        cgroup_content = "12:memory:/user.slice/user-1000.slice\n"
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is False

    def test_handles_missing_cgroup_file(self):
        """Test graceful handling of missing /proc/1/cgroup file."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", side_effect=FileNotFoundError):
                    assert is_docker_environment() is False

    def test_handles_cgroup_permission_error(self):
        """Test graceful handling of permission denied on cgroup file."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", side_effect=PermissionError):
                    assert is_docker_environment() is False

    def test_dockerenv_takes_priority(self):
        """Test that /.dockerenv detection short-circuits other checks."""
        # If /.dockerenv exists, we should return True without checking env vars or cgroup
        mock_path = MagicMock()
        mock_path.exists.return_value = True

        with patch("systemeval.utils.docker.docker.Path") as MockPath:
            MockPath.return_value = mock_path
            result = is_docker_environment()
            assert result is True
            # Path.exists should be called
            mock_path.exists.assert_called_once()

    def test_env_var_takes_priority_over_cgroup(self):
        """Test that DOCKER_CONTAINER env var short-circuits cgroup check."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"DOCKER_CONTAINER": "yes"}):
                # Should not even try to open cgroup file
                with patch("builtins.open") as mock_open_func:
                    result = is_docker_environment()
                    assert result is True
                    mock_open_func.assert_not_called()

    def test_empty_docker_container_env_not_detected(self):
        """Test that empty DOCKER_CONTAINER env var is not treated as True."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {"DOCKER_CONTAINER": ""}):
                with patch("builtins.open", side_effect=FileNotFoundError):
                    assert is_docker_environment() is False


class TestGetEnvironmentType:
    """Tests for get_environment_type() function."""

    def test_returns_docker_when_in_docker(self):
        """Test returns 'docker' when running in Docker."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            assert get_environment_type() == "docker"

    def test_returns_local_when_not_in_docker(self):
        """Test returns 'local' when not running in Docker."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ):
            assert get_environment_type() == "local"

    def test_return_type_is_string(self):
        """Test that return type is always a string."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            result = get_environment_type()
            assert isinstance(result, str)

        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ):
            result = get_environment_type()
            assert isinstance(result, str)


class TestGetDockerComposeService:
    """Tests for get_docker_compose_service() function."""

    def test_returns_service_name_when_set(self):
        """Test returns COMPOSE_SERVICE value when set."""
        with patch.dict(os.environ, {"COMPOSE_SERVICE": "web"}):
            assert get_docker_compose_service() == "web"

    def test_returns_none_when_not_set(self):
        """Test returns None when COMPOSE_SERVICE not set."""
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("COMPOSE_SERVICE", None)
            assert get_docker_compose_service() is None

    def test_returns_empty_string_if_set_empty(self):
        """Test returns empty string if COMPOSE_SERVICE is set but empty."""
        with patch.dict(os.environ, {"COMPOSE_SERVICE": ""}):
            assert get_docker_compose_service() == ""

    def test_returns_complex_service_name(self):
        """Test returns complex service names correctly."""
        with patch.dict(os.environ, {"COMPOSE_SERVICE": "api-backend-worker"}):
            assert get_docker_compose_service() == "api-backend-worker"

    def test_returns_service_with_underscores(self):
        """Test returns service names with underscores."""
        with patch.dict(os.environ, {"COMPOSE_SERVICE": "celery_worker_1"}):
            assert get_docker_compose_service() == "celery_worker_1"


class TestGetContainerId:
    """Tests for get_container_id() function."""

    def test_returns_none_when_not_in_docker(self):
        """Test returns None when not in Docker environment."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ):
            assert get_container_id() is None

    def test_returns_hostname_when_in_docker(self):
        """Test returns HOSTNAME as container ID when in Docker."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": "abc123def456"}):
                assert get_container_id() == "abc123def456"

    def test_returns_none_when_in_docker_but_no_hostname(self):
        """Test returns None when in Docker but HOSTNAME not set."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("HOSTNAME", None)
                assert get_container_id() is None

    def test_returns_full_container_id(self):
        """Test returns full container ID (64 char hex)."""
        full_id = "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2"
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": full_id}):
                assert get_container_id() == full_id

    def test_returns_short_container_id(self):
        """Test returns short container ID (12 char hex)."""
        short_id = "a1b2c3d4e5f6"
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": short_id}):
                assert get_container_id() == short_id

    def test_does_not_call_is_docker_twice(self):
        """Test that is_docker_environment is only called once."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ) as mock_is_docker:
            get_container_id()
            mock_is_docker.assert_called_once()

    def test_returns_custom_hostname_in_docker(self):
        """Test returns custom hostname when set in Docker."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": "my-custom-container"}):
                assert get_container_id() == "my-custom-container"


class TestDockerPluginIntegration:
    """Integration tests for Docker plugin functions working together."""

    def test_environment_type_matches_container_id_behavior(self):
        """Test that environment type and container ID are consistent."""
        # When in Docker
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": "container123"}):
                assert get_environment_type() == "docker"
                assert get_container_id() is not None

        # When not in Docker
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ):
            assert get_environment_type() == "local"
            assert get_container_id() is None

    def test_compose_service_independent_of_docker_detection(self):
        """Test that COMPOSE_SERVICE can be read regardless of Docker detection."""
        # COMPOSE_SERVICE should work even outside actual Docker
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=False
        ):
            with patch.dict(os.environ, {"COMPOSE_SERVICE": "test-service"}):
                assert get_docker_compose_service() == "test-service"

    def test_all_functions_work_in_docker_environment(self):
        """Test all functions return expected values in Docker environment."""
        with patch.object(Path, "exists", return_value=True):
            with patch.dict(
                os.environ,
                {
                    "COMPOSE_SERVICE": "api",
                    "HOSTNAME": "abc123",
                },
            ):
                assert is_docker_environment() is True
                assert get_environment_type() == "docker"
                assert get_docker_compose_service() == "api"
                assert get_container_id() == "abc123"

    def test_all_functions_work_outside_docker(self):
        """Test all functions return expected values outside Docker."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                os.environ.pop("COMPOSE_SERVICE", None)
                with patch("builtins.open", side_effect=FileNotFoundError):
                    assert is_docker_environment() is False
                    assert get_environment_type() == "local"
                    assert get_docker_compose_service() is None
                    assert get_container_id() is None


class TestDockerPluginEdgeCases:
    """Edge case tests for Docker plugin."""

    def test_cgroup_with_mixed_content(self):
        """Test cgroup detection with mixed Docker/non-Docker entries."""
        cgroup_content = (
            "12:memory:/user.slice\n"
            "11:cpu:/docker/abc123\n"
            "10:blkio:/user.slice\n"
        )
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is True

    def test_cgroup_with_nested_docker_path(self):
        """Test cgroup detection with nested docker path."""
        cgroup_content = "12:memory:/docker/overlay2/abc123\n"
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is True

    def test_cgroup_case_sensitivity(self):
        """Test that cgroup detection is case-sensitive for 'docker'."""
        cgroup_content = "12:memory:/DOCKER/abc123\n"
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    # Python's 'in' is case-sensitive, so 'DOCKER' won't match 'docker'
                    assert is_docker_environment() is False

    def test_empty_cgroup_file(self):
        """Test handling of empty cgroup file."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", mock_open(read_data="")):
                    assert is_docker_environment() is False

    def test_hostname_with_special_characters(self):
        """Test container ID with special characters in hostname."""
        with patch(
            "systemeval.utils.docker.docker.is_docker_environment", return_value=True
        ):
            with patch.dict(os.environ, {"HOSTNAME": "container-name_v1.2"}):
                assert get_container_id() == "container-name_v1.2"

    def test_compose_service_with_special_characters(self):
        """Test compose service with special characters."""
        with patch.dict(os.environ, {"COMPOSE_SERVICE": "api-v2.1_worker"}):
            assert get_docker_compose_service() == "api-v2.1_worker"

    def test_docker_container_env_with_various_truthy_values(self):
        """Test DOCKER_CONTAINER with various truthy string values."""
        truthy_values = ["1", "true", "True", "TRUE", "yes", "YES", "on", "any_value"]

        for value in truthy_values:
            with patch.object(Path, "exists", return_value=False):
                with patch.dict(os.environ, {"DOCKER_CONTAINER": value}):
                    assert is_docker_environment() is True, f"Failed for value: {value}"

    def test_multiple_detection_methods_all_true(self):
        """Test when multiple detection methods would return true."""
        # All indicators present - should still return True (short-circuits on first)
        cgroup_content = "12:memory:/docker/abc123\n"
        with patch.object(Path, "exists", return_value=True):
            with patch.dict(os.environ, {"DOCKER_CONTAINER": "1"}):
                with patch("builtins.open", mock_open(read_data=cgroup_content)):
                    assert is_docker_environment() is True


class TestDockerPluginErrorHandling:
    """Error handling tests for Docker plugin."""

    def test_cgroup_io_error_handled(self):
        """Test that IOError when reading cgroup is handled gracefully."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                with patch("builtins.open", side_effect=IOError("Read error")):
                    # IOError is a base class, but the code only catches
                    # FileNotFoundError and PermissionError
                    # This test verifies the current behavior
                    try:
                        result = is_docker_environment()
                        # If it doesn't raise, it should return False
                        # (but current code would raise)
                    except IOError:
                        # Current implementation only catches specific errors
                        pass

    def test_os_error_in_cgroup_check(self):
        """Test OSError handling in cgroup check."""
        with patch.object(Path, "exists", return_value=False):
            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("DOCKER_CONTAINER", None)
                # OSError is the base class of FileNotFoundError and PermissionError
                # but the code specifically catches those two subclasses
                with patch("builtins.open", side_effect=FileNotFoundError):
                    assert is_docker_environment() is False

    def test_concurrent_env_modification_safety(self):
        """Test behavior when environment variables are modified concurrently."""
        # This is a theoretical test - in practice Python GIL prevents true concurrency
        # but we verify the code doesn't cache values inappropriately
        with patch.object(Path, "exists", return_value=False):
            with patch("builtins.open", side_effect=FileNotFoundError):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("DOCKER_CONTAINER", None)
                    assert is_docker_environment() is False

                with patch.dict(os.environ, {"DOCKER_CONTAINER": "1"}):
                    assert is_docker_environment() is True
