"""Tests for SurferAdapter."""

import pytest
import json
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError, URLError

from systemeval.adapters import SurferAdapter
from systemeval.adapters import TestResult


class TestSurferAdapterInit:
    """Tests for SurferAdapter initialization."""

    def test_init_with_config(self, tmp_path):
        """Test initialization with configuration."""
        adapter = SurferAdapter(
            str(tmp_path),
            project_slug="my-project",
            api_key="test-api-key",
            api_base_url="https://api.example.com",
            poll_interval=10,
            timeout=300,
        )
        assert adapter.project_slug == "my-project"
        assert adapter.api_key == "test-api-key"
        assert adapter.api_base_url == "https://api.example.com"
        assert adapter.poll_interval == 10
        assert adapter.surfer_timeout == 300

    def test_init_reads_api_key_from_env(self, tmp_path, monkeypatch):
        """Test initialization reads API key from environment."""
        monkeypatch.setenv("DEBUGGAI_API_KEY", "env-api-key")

        adapter = SurferAdapter(str(tmp_path), project_slug="test")
        assert adapter.api_key == "env-api-key"

    def test_init_strips_trailing_slash(self, tmp_path):
        """Test initialization strips trailing slash from API URL."""
        adapter = SurferAdapter(
            str(tmp_path),
            project_slug="test",
            api_base_url="https://api.example.com/",
        )
        assert adapter.api_base_url == "https://api.example.com"


class TestSurferAdapterValidateEnvironment:
    """Tests for SurferAdapter validate_environment."""

    def test_validate_fails_without_api_key(self, tmp_path):
        """Test validation fails without API key."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key=None)
        adapter.api_key = None  # Explicitly clear

        result = adapter.validate_environment()
        assert not result

    def test_validate_fails_without_project_slug(self, tmp_path):
        """Test validation fails without project slug."""
        adapter = SurferAdapter(str(tmp_path), project_slug="", api_key="test-key")

        result = adapter.validate_environment()
        assert not result

    def test_validate_checks_api_connectivity(self, tmp_path):
        """Test validation makes API call to verify credentials."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="test-key")

        mock_response = MagicMock()
        mock_response.read.return_value = b'{"id": 1}'
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("systemeval.adapters.surfer_adapter.urlopen", return_value=mock_response):
            result = adapter.validate_environment()

        assert result

    def test_validate_handles_401_error(self, tmp_path):
        """Test validation handles authentication failure."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="bad-key")

        error = HTTPError("url", 401, "Unauthorized", {}, None)
        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=error):
            result = adapter.validate_environment()

        assert not result

    def test_validate_handles_404_error(self, tmp_path):
        """Test validation handles project not found."""
        adapter = SurferAdapter(str(tmp_path), project_slug="nonexistent", api_key="key")

        error = HTTPError("url", 404, "Not Found", {}, None)
        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=error):
            result = adapter.validate_environment()

        assert not result


class TestSurferAdapterDiscover:
    """Tests for SurferAdapter discover."""

    def test_discover_returns_empty_without_api_key(self, tmp_path):
        """Test discover returns empty list without API key."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key=None)
        adapter.api_key = None

        tests = adapter.discover()
        assert tests == []

    def test_discover_parses_api_response(self, tmp_path):
        """Test discover parses API test list response."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        api_response = {
            "results": [
                {
                    "id": "e2e-1",
                    "name": "Login flow test",
                    "url": "/login",
                    "status": "active",
                    "description": "Tests login functionality",
                },
                {
                    "id": "e2e-2",
                    "name": "Checkout flow test",
                    "url": "/checkout",
                    "status": "active",
                    "description": "Tests checkout",
                },
            ]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(api_response).encode()
        mock_response.__enter__ = lambda s: mock_response
        mock_response.__exit__ = MagicMock(return_value=False)

        with patch("systemeval.adapters.surfer_adapter.urlopen", return_value=mock_response):
            tests = adapter.discover()

        assert len(tests) == 2
        assert tests[0].name == "Login flow test"
        assert tests[0].id == "e2e-1"
        assert "surfer" in tests[0].markers
        assert "browser" in tests[0].markers

    def test_discover_handles_api_error(self, tmp_path):
        """Test discover handles API errors gracefully."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        error = HTTPError("url", 500, "Server Error", {}, None)
        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=error):
            tests = adapter.discover()

        assert tests == []


class TestSurferAdapterExecute:
    """Tests for SurferAdapter execute."""

    def test_execute_fails_without_api_key(self, tmp_path):
        """Test execute returns error result without API key."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key=None)
        adapter.api_key = None

        result = adapter.execute()

        assert result.errors == 1
        assert result.exit_code == 2
        assert "DEBUGGAI_API_KEY" in result.failures[0].message

    def test_execute_triggers_test_run(self, tmp_path):
        """Test execute triggers a test run via API."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        # Mock trigger response
        trigger_response = {"id": "run-123"}

        # Mock poll response (completed)
        poll_response = {
            "status": "completed",
            "stats": {"passed": 3, "failed": 0, "skipped": 1},
            "duration_seconds": 45.5,
        }

        responses = [trigger_response, poll_response]
        response_idx = [0]

        def mock_urlopen(request, timeout=None):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(responses[response_idx[0]]).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            response_idx[0] = min(response_idx[0] + 1, len(responses) - 1)
            return mock_resp

        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=mock_urlopen):
            result = adapter.execute()

        assert result.passed == 3
        assert result.failed == 0
        assert result.skipped == 1
        assert result.parsed_from == "surfer"

    def test_execute_passes_target_url(self, tmp_path):
        """Test execute passes target URL in request."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        trigger_response = {"id": "run-123"}
        poll_response = {"status": "completed", "stats": {"passed": 1}}

        captured_requests = []

        def mock_urlopen(request, timeout=None):
            captured_requests.append(request)
            mock_resp = MagicMock()
            if len(captured_requests) == 1:
                mock_resp.read.return_value = json.dumps(trigger_response).encode()
            else:
                mock_resp.read.return_value = json.dumps(poll_response).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=mock_urlopen):
            adapter.execute(target_url="https://abc.ngrok.io")

        # Check first request (trigger) has target_url
        trigger_request = captured_requests[0]
        body = json.loads(trigger_request.data.decode())
        assert body["target_url"] == "https://abc.ngrok.io"

    def test_execute_handles_failed_trigger(self, tmp_path):
        """Test execute handles failed test run trigger."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        error = HTTPError("url", 400, "Bad Request", {}, None)
        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=error):
            result = adapter.execute()

        assert result.errors == 1
        assert "trigger" in result.failures[0].test_id.lower()

    def test_execute_handles_timeout(self, tmp_path):
        """Test execute handles polling timeout."""
        adapter = SurferAdapter(
            str(tmp_path),
            project_slug="test",
            api_key="key",
            timeout=1,  # Very short timeout
            poll_interval=0.1,
        )

        trigger_response = {"id": "run-123"}
        poll_response = {"status": "running"}  # Never completes

        responses = [trigger_response] + [poll_response] * 100

        def mock_urlopen(request, timeout=None):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(responses.pop(0) if responses else poll_response).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=mock_urlopen):
            with patch("time.sleep"):  # Don't actually sleep
                result = adapter.execute(timeout=1)

        assert result.errors == 1
        assert "timed out" in result.failures[0].message.lower()

    def test_execute_parses_failure_details(self, tmp_path):
        """Test execute parses test failure details from response."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")

        trigger_response = {"id": "run-123"}
        poll_response = {
            "status": "failed",
            "stats": {"passed": 2, "failed": 1},
            "failures": [
                {
                    "id": "test-1",
                    "name": "Login test",
                    "message": "Button not found",
                    "status": "failed",
                }
            ],
        }

        responses = [trigger_response, poll_response]

        def mock_urlopen(request, timeout=None):
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(responses.pop(0)).encode()
            mock_resp.__enter__ = lambda s: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            return mock_resp

        with patch("systemeval.adapters.surfer_adapter.urlopen", side_effect=mock_urlopen):
            result = adapter.execute()

        assert result.passed == 2
        assert result.failed == 1
        assert len(result.failures) == 1
        assert result.failures[0].message == "Button not found"


class TestSurferAdapterGetMarkers:
    """Tests for SurferAdapter get_available_markers."""

    def test_get_available_markers(self, tmp_path):
        """Test get_available_markers returns expected list."""
        adapter = SurferAdapter(str(tmp_path), project_slug="test", api_key="key")
        markers = adapter.get_available_markers()

        assert "browser" in markers
        assert "e2e" in markers
        assert "surfer" in markers
        assert "cloud" in markers
