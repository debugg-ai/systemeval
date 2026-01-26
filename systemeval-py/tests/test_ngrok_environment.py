"""Tests for NgrokEnvironment."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
import subprocess
import json

from systemeval.environments import NgrokEnvironment, EnvironmentType, SetupResult


class TestNgrokEnvironmentInit:
    """Tests for NgrokEnvironment initialization."""

    def test_init_with_defaults(self):
        """Test initialization with default values."""
        env = NgrokEnvironment("tunnel", {})
        assert env.port == 3000
        assert env.auth_token is None
        assert env.region == "us"
        assert env.tunnel_url is None

    def test_init_with_custom_config(self):
        """Test initialization with custom configuration."""
        config = {
            "port": 8080,
            "auth_token": "test-token",
            "region": "eu",
        }
        env = NgrokEnvironment("tunnel", config)
        assert env.port == 8080
        assert env.auth_token == "test-token"
        assert env.region == "eu"

    def test_env_type(self):
        """Test environment type is NGROK."""
        env = NgrokEnvironment("tunnel", {})
        assert env.env_type == EnvironmentType.NGROK


class TestNgrokEnvironmentSetup:
    """Tests for NgrokEnvironment setup."""

    def test_setup_fails_if_ngrok_not_found(self):
        """Test that setup fails if ngrok is not in PATH."""
        env = NgrokEnvironment("tunnel", {"port": 3000})

        with patch("shutil.which", return_value=None):
            result = env.setup()

        assert not result.success
        assert "ngrok not found" in result.message

    def test_setup_starts_ngrok_process(self):
        """Test that setup starts ngrok with correct arguments."""
        env = NgrokEnvironment("tunnel", {"port": 3000, "region": "eu"})
        mock_popen = MagicMock()
        mock_popen.pid = 12345

        with patch("shutil.which", return_value="/usr/bin/ngrok"):
            with patch("subprocess.Popen", return_value=mock_popen) as popen_mock:
                result = env.setup()

        assert result.success
        assert result.details["pid"] == 12345

        # Verify command arguments
        call_args = popen_mock.call_args
        cmd = call_args[0][0]
        assert cmd[0] == "/usr/bin/ngrok"
        assert "http" in cmd
        assert "3000" in cmd
        assert "--region" in cmd
        assert "eu" in cmd

    def test_setup_sets_auth_token_in_env(self):
        """Test that auth token is passed via environment."""
        env = NgrokEnvironment("tunnel", {"port": 3000, "auth_token": "secret-token"})
        mock_popen = MagicMock()
        mock_popen.pid = 12345

        with patch("shutil.which", return_value="/usr/bin/ngrok"):
            with patch("subprocess.Popen", return_value=mock_popen) as popen_mock:
                env.setup()

        call_args = popen_mock.call_args
        env_dict = call_args[1]["env"]
        assert env_dict["NGROK_AUTHTOKEN"] == "secret-token"


class TestNgrokEnvironmentWaitReady:
    """Tests for NgrokEnvironment wait_ready."""

    def test_wait_ready_returns_false_if_no_process(self):
        """Test wait_ready returns False if process not started."""
        env = NgrokEnvironment("tunnel", {})
        assert not env.wait_ready(timeout=1)

    def test_wait_ready_polls_api_for_tunnel_url(self):
        """Test that wait_ready polls ngrok API."""
        env = NgrokEnvironment("tunnel", {"port": 3000})
        env._process = MagicMock()
        env._process.poll.return_value = None  # Process running

        tunnel_response = {
            "tunnels": [
                {"proto": "https", "public_url": "https://abc123.ngrok.io"}
            ]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tunnel_response).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("systemeval.environments.ngrok.urlopen", return_value=mock_response):
            result = env.wait_ready(timeout=5)

        assert result
        assert env.tunnel_url == "https://abc123.ngrok.io"

    def test_wait_ready_prefers_https_tunnel(self):
        """Test that HTTPS tunnel is preferred over HTTP."""
        env = NgrokEnvironment("tunnel", {"port": 3000})
        env._process = MagicMock()
        env._process.poll.return_value = None

        tunnel_response = {
            "tunnels": [
                {"proto": "http", "public_url": "http://abc123.ngrok.io"},
                {"proto": "https", "public_url": "https://abc123.ngrok.io"},
            ]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(tunnel_response).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("systemeval.environments.ngrok.urlopen", return_value=mock_response):
            env.wait_ready(timeout=5)

        assert env.tunnel_url == "https://abc123.ngrok.io"

    def test_wait_ready_returns_false_if_process_exits(self):
        """Test wait_ready returns False if ngrok process exits."""
        env = NgrokEnvironment("tunnel", {"port": 3000})
        env._process = MagicMock()
        env._process.poll.return_value = 1  # Process exited

        result = env.wait_ready(timeout=1)
        assert not result


class TestNgrokEnvironmentTeardown:
    """Tests for NgrokEnvironment teardown."""

    def test_teardown_terminates_process(self):
        """Test that teardown terminates the ngrok process."""
        env = NgrokEnvironment("tunnel", {})
        mock_process = MagicMock()
        mock_process.wait.return_value = 0
        env._process = mock_process
        env._tunnel_url = "https://test.ngrok.io"

        env.teardown()

        mock_process.terminate.assert_called_once()
        assert env._process is None
        assert env._tunnel_url is None

    def test_teardown_kills_if_terminate_times_out(self):
        """Test that teardown kills process if terminate times out."""
        env = NgrokEnvironment("tunnel", {})
        mock_process = MagicMock()
        mock_process.wait.side_effect = [subprocess.TimeoutExpired("cmd", 5), None]
        env._process = mock_process

        env.teardown()

        mock_process.terminate.assert_called_once()
        mock_process.kill.assert_called_once()

    def test_teardown_keeps_running_if_flag_set(self):
        """Test that teardown keeps process running if keep_running=True."""
        env = NgrokEnvironment("tunnel", {})
        env._process = MagicMock()
        original_process = env._process

        env.teardown(keep_running=True)

        original_process.terminate.assert_not_called()
        assert env._process is original_process


class TestNgrokEnvironmentRunTests:
    """Tests for NgrokEnvironment run_tests."""

    def test_run_tests_returns_empty_result(self):
        """Test that run_tests returns empty result (NgrokEnvironment doesn't run tests)."""
        env = NgrokEnvironment("tunnel", {})
        result = env.run_tests()

        assert result.passed == 0
        assert result.failed == 0
        assert result.errors == 0
        assert result.skipped == 0
        assert result.exit_code == 0


class TestNgrokEnvironmentIsReady:
    """Tests for NgrokEnvironment is_ready."""

    def test_is_ready_false_if_no_process(self):
        """Test is_ready returns False if no process."""
        env = NgrokEnvironment("tunnel", {})
        assert not env.is_ready()

    def test_is_ready_false_if_process_exited(self):
        """Test is_ready returns False if process has exited."""
        env = NgrokEnvironment("tunnel", {})
        env._process = MagicMock()
        env._process.poll.return_value = 1
        assert not env.is_ready()

    def test_is_ready_false_if_no_tunnel_url(self):
        """Test is_ready returns False if no tunnel URL yet."""
        env = NgrokEnvironment("tunnel", {})
        env._process = MagicMock()
        env._process.poll.return_value = None
        assert not env.is_ready()

    def test_is_ready_true_when_tunnel_established(self):
        """Test is_ready returns True when tunnel is established."""
        env = NgrokEnvironment("tunnel", {})
        env._process = MagicMock()
        env._process.poll.return_value = None
        env._tunnel_url = "https://test.ngrok.io"
        assert env.is_ready()
