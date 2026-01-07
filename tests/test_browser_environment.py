"""Tests for BrowserEnvironment."""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from systemeval.environments.browser import BrowserEnvironment
from systemeval.environments.base import EnvironmentType, SetupResult
from systemeval.adapters import TestResult


class TestBrowserEnvironmentInit:
    """Tests for BrowserEnvironment initialization."""

    def test_init_with_minimal_config(self, tmp_path):
        """Test initialization with minimal configuration."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
        }
        env = BrowserEnvironment("browser", config)

        assert env.test_runner == "playwright"
        assert env._server is None
        assert env._tunnel is None

    def test_init_with_server_config(self, tmp_path):
        """Test initialization creates server environment."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {
                "command": "npm run dev",
                "port": 3000,
                "ready_pattern": "ready",
            },
        }
        env = BrowserEnvironment("browser", config)

        assert env._server is not None
        assert env._server.port == 3000

    def test_init_with_tunnel_config(self, tmp_path):
        """Test initialization creates tunnel environment."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "tunnel": {
                "port": 3000,
                "region": "eu",
            },
        }
        env = BrowserEnvironment("browser", config)

        assert env._tunnel is not None
        assert env._tunnel.port == 3000
        assert env._tunnel.region == "eu"

    def test_init_with_tunnel_port_shorthand(self, tmp_path):
        """Test initialization with tunnel_port shorthand."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "tunnel_port": 8080,
        }
        env = BrowserEnvironment("browser", config)

        assert env._tunnel is not None
        assert env._tunnel.port == 8080

    def test_init_creates_playwright_adapter(self, tmp_path):
        """Test initialization creates PlaywrightAdapter for browser runner."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "playwright": {
                "config_file": "e2e.config.ts",
                "project": "chromium",
                "headed": True,
            },
        }
        env = BrowserEnvironment("browser", config)

        assert env._adapter is not None
        assert env._adapter.config_file == "e2e.config.ts"
        assert env._adapter.project == "chromium"
        assert env._adapter.headed

    def test_init_creates_surfer_adapter(self, tmp_path, monkeypatch):
        """Test initialization creates SurferAdapter for surfer runner."""
        monkeypatch.setenv("DEBUGGAI_API_KEY", "test-key")
        config = {
            "test_runner": "surfer",
            "working_dir": str(tmp_path),
            "surfer": {
                "project_slug": "my-project",
            },
        }
        env = BrowserEnvironment("browser", config)

        assert env._adapter is not None
        assert env._adapter.project_slug == "my-project"


class TestBrowserEnvironmentEnvType:
    """Tests for BrowserEnvironment env_type property."""

    def test_env_type_is_browser(self, tmp_path):
        """Test environment type is BROWSER."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})
        assert env.env_type == EnvironmentType.BROWSER


class TestBrowserEnvironmentSetup:
    """Tests for BrowserEnvironment setup."""

    def test_setup_starts_server_and_tunnel(self, tmp_path):
        """Test setup starts both server and tunnel."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        # Mock server and tunnel
        env._server = MagicMock()
        env._server.setup.return_value = SetupResult(success=True, message="Started")
        env._tunnel = MagicMock()
        env._tunnel.setup.return_value = SetupResult(success=True, message="Started")

        result = env.setup()

        assert result.success
        env._server.setup.assert_called_once()
        env._tunnel.setup.assert_called_once()

    def test_setup_cleans_up_on_tunnel_failure(self, tmp_path):
        """Test setup tears down server if tunnel fails."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._server.setup.return_value = SetupResult(success=True)
        env._tunnel = MagicMock()
        env._tunnel.setup.return_value = SetupResult(success=False, message="ngrok not found")

        result = env.setup()

        assert not result.success
        assert "Tunnel failed" in result.message
        env._server.teardown.assert_called_once()

    def test_setup_succeeds_without_server(self, tmp_path):
        """Test setup succeeds with tunnel only."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._tunnel = MagicMock()
        env._tunnel.setup.return_value = SetupResult(success=True)

        result = env.setup()

        assert result.success


class TestBrowserEnvironmentWaitReady:
    """Tests for BrowserEnvironment wait_ready."""

    def test_wait_ready_waits_for_both(self, tmp_path):
        """Test wait_ready waits for both server and tunnel."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._server.wait_ready.return_value = True
        env._tunnel = MagicMock()
        env._tunnel.wait_ready.return_value = True

        result = env.wait_ready(timeout=60)

        assert result
        env._server.wait_ready.assert_called_once()
        env._tunnel.wait_ready.assert_called_once()

    def test_wait_ready_fails_if_server_not_ready(self, tmp_path):
        """Test wait_ready returns False if server fails."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._server.wait_ready.return_value = False

        result = env.wait_ready(timeout=60)

        assert not result

    def test_wait_ready_succeeds_without_children(self, tmp_path):
        """Test wait_ready succeeds with no server or tunnel."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})

        result = env.wait_ready(timeout=60)

        assert result


class TestBrowserEnvironmentRunTests:
    """Tests for BrowserEnvironment run_tests."""

    def test_run_tests_uses_adapter(self, tmp_path):
        """Test run_tests executes via adapter."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
        }
        env = BrowserEnvironment("browser", config)

        mock_adapter = MagicMock()
        mock_adapter.validate_environment.return_value = True
        mock_adapter.discover.return_value = []
        mock_adapter.execute.return_value = TestResult(
            passed=5, failed=0, errors=0, skipped=1, duration=10.0
        )
        env._adapter = mock_adapter

        result = env.run_tests(category="e2e", verbose=True)

        assert result.passed == 5
        mock_adapter.discover.assert_called_once_with(category="e2e")
        mock_adapter.execute.assert_called_once()

    def test_run_tests_returns_error_without_adapter(self, tmp_path):
        """Test run_tests returns error if no adapter configured."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})
        env._adapter = None

        result = env.run_tests()

        assert result.errors == 1
        assert result.exit_code == 2

    def test_run_tests_returns_error_if_validation_fails(self, tmp_path):
        """Test run_tests returns error if adapter validation fails."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})
        env._adapter = MagicMock()
        env._adapter.validate_environment.return_value = False

        result = env.run_tests()

        assert result.errors == 1
        assert result.exit_code == 2


class TestBrowserEnvironmentTeardown:
    """Tests for BrowserEnvironment teardown."""

    def test_teardown_stops_both(self, tmp_path):
        """Test teardown stops both tunnel and server."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._tunnel = MagicMock()

        env.teardown()

        env._tunnel.teardown.assert_called_once_with(keep_running=False)
        env._server.teardown.assert_called_once_with(keep_running=False)

    def test_teardown_with_keep_running(self, tmp_path):
        """Test teardown respects keep_running flag."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._tunnel = MagicMock()

        env.teardown(keep_running=True)

        env._tunnel.teardown.assert_called_once_with(keep_running=True)


class TestBrowserEnvironmentProperties:
    """Tests for BrowserEnvironment properties."""

    def test_tunnel_url_returns_tunnel_url(self, tmp_path):
        """Test tunnel_url returns tunnel's URL."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._tunnel = MagicMock()
        env._tunnel.tunnel_url = "https://abc.ngrok.io"

        assert env.tunnel_url == "https://abc.ngrok.io"

    def test_tunnel_url_returns_none_without_tunnel(self, tmp_path):
        """Test tunnel_url returns None without tunnel."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})
        assert env.tunnel_url is None

    def test_server_url_returns_localhost_url(self, tmp_path):
        """Test server_url returns localhost URL."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev", "port": 8080},
        }
        env = BrowserEnvironment("browser", config)

        assert env.server_url == "http://localhost:8080"

    def test_server_url_returns_none_without_server(self, tmp_path):
        """Test server_url returns None without server."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})
        assert env.server_url is None


class TestBrowserEnvironmentIsReady:
    """Tests for BrowserEnvironment is_ready."""

    def test_is_ready_checks_both(self, tmp_path):
        """Test is_ready checks both server and tunnel."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
            "tunnel": {"port": 3000},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._server.is_ready.return_value = True
        env._tunnel = MagicMock()
        env._tunnel.is_ready.return_value = True

        assert env.is_ready()

    def test_is_ready_false_if_server_not_ready(self, tmp_path):
        """Test is_ready returns False if server not ready."""
        config = {
            "test_runner": "playwright",
            "working_dir": str(tmp_path),
            "server": {"command": "npm run dev"},
        }
        env = BrowserEnvironment("browser", config)

        env._server = MagicMock()
        env._server.is_ready.return_value = False

        assert not env.is_ready()

    def test_is_ready_true_without_children(self, tmp_path):
        """Test is_ready returns True with no server or tunnel."""
        env = BrowserEnvironment("browser", {"working_dir": str(tmp_path)})

        assert env.is_ready()
