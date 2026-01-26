"""Tests for MockDebuggAIServer fixture."""

import json
import pytest
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from tests.fixtures.mock_debuggai_server import MockDebuggAIServer, create_mock_server


class TestMockServerBasics:
    """Basic functionality tests for MockDebuggAIServer."""

    def test_server_starts_and_stops(self):
        """Test server starts and stops cleanly."""
        server = MockDebuggAIServer()
        server.start()
        assert server.actual_port > 0
        assert server.base_url.startswith("http://")
        server.stop()

    def test_context_manager(self):
        """Test server works as context manager."""
        with MockDebuggAIServer() as server:
            assert server.actual_port > 0
            response = self._get(server, "/health")
            assert response["status"] == "healthy"

    def test_auto_assign_port(self):
        """Test server auto-assigns port when port=0."""
        server = MockDebuggAIServer(port=0)
        server.start()
        try:
            assert server.actual_port > 0
            assert server.actual_port != 0
        finally:
            server.stop()

    def test_health_endpoint(self):
        """Test /health endpoint."""
        with MockDebuggAIServer() as server:
            response = self._get(server, "/health")
            assert response["status"] == "healthy"

    def test_reset_clears_state(self):
        """Test reset() clears all server state."""
        with MockDebuggAIServer() as server:
            # Add some state
            server.create_suite("test-suite-1")
            server.inject_error("/test", 500, "Error")
            server.record_request("GET", "/test", None)

            assert len(server.suites) == 1
            assert len(server.injected_errors) == 1
            assert len(server.recorded_requests) == 1

            # Reset
            server.reset()

            assert len(server.suites) == 0
            assert len(server.injected_errors) == 0
            assert len(server.recorded_requests) == 0

    # Helper methods
    def _get(self, server: MockDebuggAIServer, path: str, api_key: str = "test-api-key-12345") -> dict:
        """Make a GET request to the server."""
        url = f"{server.base_url}{path}"
        request = Request(url)
        request.add_header("Authorization", f"Bearer {api_key}")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())

    def _post(self, server: MockDebuggAIServer, path: str, data: dict, api_key: str = "test-api-key-12345") -> dict:
        """Make a POST request to the server."""
        url = f"{server.base_url}{path}"
        body = json.dumps(data).encode()
        request = Request(url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {api_key}")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())


class TestAuthentication:
    """Tests for API key authentication."""

    def test_missing_auth_header_returns_401(self):
        """Test that missing auth header returns 401."""
        with MockDebuggAIServer() as server:
            url = f"{server.base_url}/users/me/"
            request = Request(url)
            with pytest.raises(HTTPError) as exc_info:
                urlopen(request, timeout=5)
            assert exc_info.value.code == 401

    def test_invalid_api_key_returns_401(self):
        """Test that invalid API key returns 401."""
        with MockDebuggAIServer() as server:
            url = f"{server.base_url}/users/me/"
            request = Request(url)
            request.add_header("Authorization", "Bearer invalid-key")
            with pytest.raises(HTTPError) as exc_info:
                urlopen(request, timeout=5)
            assert exc_info.value.code == 401

    def test_valid_api_key_succeeds(self):
        """Test that valid API key succeeds."""
        with MockDebuggAIServer(valid_api_key="my-test-key") as server:
            url = f"{server.base_url}/users/me/"
            request = Request(url)
            request.add_header("Authorization", "Bearer my-test-key")
            with urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
            assert "id" in data
            assert "email" in data

    def test_auth_disabled(self):
        """Test that auth can be disabled."""
        with MockDebuggAIServer(require_valid_api_key=False) as server:
            url = f"{server.base_url}/users/me/"
            request = Request(url)
            request.add_header("Authorization", "Bearer any-key")
            with urlopen(request, timeout=5) as response:
                data = json.loads(response.read().decode())
            assert "id" in data


class TestSuiteCreation:
    """Tests for test suite creation endpoints."""

    def test_create_suite_python_format(self):
        """Test POST /cli/e2e/suites (Python provider format)."""
        with MockDebuggAIServer() as server:
            response = self._post(server, "/cli/e2e/suites", {
                "repoName": "test-repo",
                "branchName": "main",
                "commitHash": "abc123",
                "workingChanges": [
                    {"status": "modified", "file": "src/app.py"},
                ],
                "testDescription": "Test changes",
            })

            assert response["success"] is True
            assert "testSuiteUuid" in response or "uuid" in response
            suite_uuid = response.get("testSuiteUuid") or response.get("uuid")
            assert suite_uuid.startswith("mock-")

    def test_create_suite_typescript_format(self):
        """Test POST /api/v1/e2e-commit-suites/ (TypeScript CLI format)."""
        with MockDebuggAIServer() as server:
            response = self._post(server, "/api/v1/e2e-commit-suites/", {
                "repoName": "test-repo",
                "branch": "feature-branch",
                "workingChanges": [
                    {"status": "added", "file": "new-file.ts"},
                ],
            })

            assert response["success"] is True
            assert "uuid" in response
            assert "tunnelKey" in response

    def test_create_suite_generates_tests(self):
        """Test that created suite has generated tests."""
        with MockDebuggAIServer() as server:
            response = self._post(server, "/cli/e2e/suites", {
                "repoName": "test-repo",
                "workingChanges": [
                    {"status": "modified", "file": "file1.py"},
                    {"status": "modified", "file": "file2.py"},
                    {"status": "added", "file": "file3.py"},
                ],
            })

            suite_uuid = response.get("testSuiteUuid") or response.get("uuid")
            suite = server.get_suite(suite_uuid)

            assert len(suite.tests) == 3
            for test in suite.tests:
                assert "uuid" in test
                assert "name" in test
                assert "curRun" in test

    def _post(self, server: MockDebuggAIServer, path: str, data: dict) -> dict:
        url = f"{server.base_url}{path}"
        body = json.dumps(data).encode()
        request = Request(url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {server.valid_api_key}")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())


class TestSuiteStatus:
    """Tests for suite status retrieval."""

    def test_get_suite_status_python_format(self):
        """Test GET /cli/e2e/suites/{uuid} (Python format)."""
        with MockDebuggAIServer() as server:
            suite = server.create_suite("test-uuid-123", status="running", num_tests=2)

            response = self._get(server, f"/cli/e2e/suites/{suite.uuid}")

            assert "suite" in response
            assert response["suite"]["uuid"] == suite.uuid
            assert response["suite"]["status"] == "running"

    def test_get_suite_status_typescript_format(self):
        """Test GET /api/v1/e2e-commit-suites/{uuid}/ (TypeScript format)."""
        with MockDebuggAIServer() as server:
            suite = server.create_suite("test-uuid-456", status="completed", num_tests=3)

            response = self._get(server, f"/api/v1/e2e-commit-suites/{suite.uuid}/")

            assert response["uuid"] == suite.uuid
            assert response["runStatus"] == "completed"
            assert len(response["tests"]) == 3

    def test_get_nonexistent_suite_returns_404(self):
        """Test that getting a nonexistent suite returns 404."""
        with MockDebuggAIServer() as server:
            url = f"{server.base_url}/cli/e2e/suites/nonexistent-uuid"
            request = Request(url)
            request.add_header("Authorization", f"Bearer {server.valid_api_key}")
            with pytest.raises(HTTPError) as exc_info:
                urlopen(request, timeout=5)
            assert exc_info.value.code == 404

    def test_set_suite_status(self):
        """Test setting suite status programmatically."""
        with MockDebuggAIServer() as server:
            suite = server.create_suite("status-test", status="pending")

            server.set_suite_status("status-test", "completed", ["completed", "completed", "failed"])

            updated_suite = server.get_suite("status-test")
            assert updated_suite.status == "completed"
            assert updated_suite.tests[0]["status"] == "completed"
            assert updated_suite.tests[2]["status"] == "failed"

    def _get(self, server: MockDebuggAIServer, path: str) -> dict:
        url = f"{server.base_url}{path}"
        request = Request(url)
        request.add_header("Authorization", f"Bearer {server.valid_api_key}")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())


class TestErrorInjection:
    """Tests for error injection functionality."""

    def test_inject_single_error(self):
        """Test injecting a single error."""
        with MockDebuggAIServer() as server:
            server.inject_error("/health", 503, "Service Unavailable", "GET", count=1)

            # First request should fail
            url = f"{server.base_url}/health"
            with pytest.raises(HTTPError) as exc_info:
                urlopen(url, timeout=5)
            assert exc_info.value.code == 503

            # Second request should succeed
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
            assert data["status"] == "healthy"

    def test_inject_permanent_error(self):
        """Test injecting a permanent error (count=0)."""
        with MockDebuggAIServer() as server:
            server.inject_error("/health", 500, "Internal Error", "GET", count=0)

            url = f"{server.base_url}/health"

            # Multiple requests should all fail
            for _ in range(3):
                with pytest.raises(HTTPError) as exc_info:
                    urlopen(url, timeout=5)
                assert exc_info.value.code == 500

    def test_clear_errors(self):
        """Test clearing injected errors."""
        with MockDebuggAIServer() as server:
            server.inject_error("/health", 500, "Error", "GET", count=0)

            # Should fail
            url = f"{server.base_url}/health"
            with pytest.raises(HTTPError):
                urlopen(url, timeout=5)

            # Clear errors
            server.clear_errors()

            # Should succeed
            with urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
            assert data["status"] == "healthy"


class TestResponseDelay:
    """Tests for response delay functionality."""

    def test_response_delay(self):
        """Test that response delay is applied."""
        with MockDebuggAIServer() as server:
            server.set_response_delay(0.5)

            start = time.time()
            url = f"{server.base_url}/health"
            with urlopen(url, timeout=5):
                pass
            elapsed = time.time() - start

            assert elapsed >= 0.4  # Allow some tolerance


class TestAutoCompletion:
    """Tests for auto-completion of test suites."""

    def test_auto_complete_suite(self):
        """Test that suites auto-complete after delay."""
        with MockDebuggAIServer() as server:
            server.set_auto_complete_delay(0.5)

            # Create suite via API
            response = self._post(server, "/cli/e2e/suites", {
                "repoName": "test",
                "workingChanges": [],
            })
            suite_uuid = response.get("testSuiteUuid") or response.get("uuid")

            # Initially pending
            suite = server.get_suite(suite_uuid)
            assert suite.status == "pending"

            # Wait for auto-completion
            time.sleep(0.7)

            # Should be completed
            suite = server.get_suite(suite_uuid)
            assert suite.status == "completed"

    def _post(self, server: MockDebuggAIServer, path: str, data: dict) -> dict:
        url = f"{server.base_url}{path}"
        body = json.dumps(data).encode()
        request = Request(url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {server.valid_api_key}")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())


class TestRequestRecording:
    """Tests for request recording functionality."""

    def test_records_suite_creation(self):
        """Test that suite creation requests are recorded."""
        with MockDebuggAIServer() as server:
            self._post(server, "/cli/e2e/suites", {
                "repoName": "recorded-repo",
                "workingChanges": [],
            })

            requests = server.get_recorded_requests(method="POST", path="/suite")
            assert len(requests) == 1
            assert requests[0]["body"]["repoName"] == "recorded-repo"

    def test_filter_recorded_requests(self):
        """Test filtering recorded requests."""
        with MockDebuggAIServer() as server:
            server.record_request("GET", "/path1", None)
            server.record_request("POST", "/path2", {"data": 1})
            server.record_request("GET", "/path2", None)

            assert len(server.get_recorded_requests()) == 3
            assert len(server.get_recorded_requests(method="GET")) == 2
            assert len(server.get_recorded_requests(path="/path2")) == 2
            assert len(server.get_recorded_requests(method="POST", path="/path2")) == 1

    def _post(self, server: MockDebuggAIServer, path: str, data: dict) -> dict:
        url = f"{server.base_url}{path}"
        body = json.dumps(data).encode()
        request = Request(url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {server.valid_api_key}")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())


class TestTunnelToken:
    """Tests for tunnel token endpoint."""

    def test_create_tunnel_token(self):
        """Test POST /api/v1/ngrok/token/."""
        with MockDebuggAIServer() as server:
            response = self._post(server, "/api/v1/ngrok/token/", {
                "commitSuiteUuid": "test-suite-123",
                "subdomain": "my-test-subdomain",
            })

            assert "token" in response
            assert response["token"].startswith("mock-ngrok-token-")
            assert response["subdomain"] == "my-test-subdomain"

    def _post(self, server: MockDebuggAIServer, path: str, data: dict) -> dict:
        url = f"{server.base_url}{path}"
        body = json.dumps(data).encode()
        request = Request(url, data=body, method="POST")
        request.add_header("Authorization", f"Bearer {server.valid_api_key}")
        request.add_header("Content-Type", "application/json")
        with urlopen(request, timeout=5) as response:
            return json.loads(response.read().decode())
