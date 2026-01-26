"""
MockDebuggAIServer - Local HTTP server simulating the DebuggAI API.

Provides a test double for integration testing without real API calls.
Supports configurable responses, delays, and error injection.

Usage:
    from tests.fixtures.mock_debuggai_server import MockDebuggAIServer

    server = MockDebuggAIServer(port=8999)
    server.start()

    # Configure expected behavior
    server.set_suite_status("test-uuid", "completed")
    server.set_response_delay(2.0)  # Simulate slow API
    server.inject_error("/health", 503, "Service Unavailable")

    # Run tests against http://localhost:8999
    ...

    server.stop()

    # Or as context manager
    with MockDebuggAIServer() as server:
        # server.base_url is available
        ...
"""

import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse


@dataclass
class MockTestSuite:
    """Represents a test suite in the mock server."""

    uuid: str
    status: str = "pending"  # pending, running, in_progress, completed, failed
    run_status: str = "pending"  # For commit suites
    tests: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    tunnel_key: Optional[str] = None
    public_url: Optional[str] = None
    repo_name: str = ""
    branch_name: str = ""
    commit_hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MockTest:
    """Represents a test within a suite."""

    uuid: str
    name: str
    status: str = "pending"  # pending, running, completed, failed
    run_script: Optional[str] = None
    run_gif: Optional[str] = None
    run_json: Optional[str] = None
    cur_run: Optional[Dict[str, Any]] = None


@dataclass
class InjectedError:
    """Represents an injected error for testing error handling."""

    status_code: int
    message: str
    count: int = 1  # Number of times to return this error (0 = forever)
    _remaining: int = field(default=0, init=False)

    def __post_init__(self):
        self._remaining = self.count

    def should_trigger(self) -> bool:
        """Check if error should trigger and decrement counter."""
        if self.count == 0:  # Forever
            return True
        if self._remaining > 0:
            self._remaining -= 1
            return True
        return False


class MockDebuggAIRequestHandler(BaseHTTPRequestHandler):
    """HTTP request handler for MockDebuggAIServer."""

    def log_message(self, format: str, *args) -> None:
        """Suppress default logging unless verbose mode enabled."""
        if self._mock_server.verbose:
            super().log_message(format, *args)

    @property
    def _mock_server(self) -> "MockDebuggAIServer":
        """Get the MockDebuggAIServer instance."""
        return self.server.mock_server

    def _send_json_response(
        self, data: Any, status_code: int = 200
    ) -> None:
        """Send a JSON response."""
        response_body = json.dumps(data).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def _send_error_response(self, status_code: int, message: str) -> None:
        """Send an error response."""
        self._send_json_response(
            {"error": message, "status": "error"}, status_code
        )

    def _parse_path(self) -> Tuple[str, Dict[str, List[str]]]:
        """Parse URL path and query parameters."""
        parsed = urlparse(self.path)
        query_params = parse_qs(parsed.query)
        return parsed.path, query_params

    def _read_body(self) -> Dict[str, Any]:
        """Read and parse JSON request body."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode("utf-8"))

    def _check_auth(self) -> bool:
        """Check authorization header."""
        auth_header = self.headers.get("Authorization", "")
        if not auth_header:
            self._send_error_response(401, "Authorization header required")
            return False

        # Accept both "Bearer <token>" and "Token <token>" formats
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]
        elif auth_header.startswith("Token "):
            token = auth_header[6:]
        else:
            self._send_error_response(401, "Invalid authorization format")
            return False

        if self._mock_server.require_valid_api_key and token != self._mock_server.valid_api_key:
            self._send_error_response(401, "Invalid API key")
            return False

        return True

    def _check_injected_error(self, path: str, method: str) -> bool:
        """Check if there's an injected error for this endpoint."""
        key = f"{method}:{path}"
        if key in self._mock_server.injected_errors:
            error = self._mock_server.injected_errors[key]
            if error.should_trigger():
                self._send_error_response(error.status_code, error.message)
                if error.count > 0 and error._remaining == 0:
                    del self._mock_server.injected_errors[key]
                return True
        return False

    def _apply_delay(self) -> None:
        """Apply configured response delay."""
        if self._mock_server.response_delay > 0:
            time.sleep(self._mock_server.response_delay)

    def do_GET(self) -> None:
        """Handle GET requests."""
        path, params = self._parse_path()
        self._apply_delay()

        if self._check_injected_error(path, "GET"):
            return

        # Health check endpoint
        if path == "/health":
            self._send_json_response({"status": "healthy", "version": "mock-1.0"})
            return

        # Get current user
        if path in ("/users/me/", "/api/v1/users/me/"):
            if not self._check_auth():
                return
            self._send_json_response({
                "id": "mock-user-123",
                "email": "test@example.com",
                "name": "Test User",
            })
            return

        # Get test suite status (Python provider format)
        if path.startswith("/cli/e2e/suites/"):
            if not self._check_auth():
                return
            suite_uuid = path.split("/")[-1] or path.split("/")[-2]
            suite = self._mock_server.suites.get(suite_uuid)
            if not suite:
                self._send_error_response(404, f"Suite {suite_uuid} not found")
                return
            self._send_json_response({
                "suite": {
                    "uuid": suite.uuid,
                    "status": suite.status,
                    "tests": suite.tests,
                    "repoName": suite.repo_name,
                    "branchName": suite.branch_name,
                }
            })
            return

        # Get commit suite status (TypeScript CLI format)
        if path.startswith("/api/v1/e2e-commit-suites/") or path.startswith("/api/v1/commit-suites/"):
            if not self._check_auth():
                return
            parts = path.rstrip("/").split("/")
            suite_uuid = parts[-1]
            suite = self._mock_server.suites.get(suite_uuid)
            if not suite:
                self._send_error_response(404, f"Suite {suite_uuid} not found")
                return
            self._send_json_response({
                "uuid": suite.uuid,
                "runStatus": suite.run_status,
                "status": suite.status,
                "tests": suite.tests,
                "tunnelKey": suite.tunnel_key,
                "publicUrl": suite.public_url,
                "repoName": suite.repo_name,
                "branchName": suite.branch_name,
                "commitHash": suite.commit_hash,
            })
            return

        self._send_error_response(404, f"Unknown endpoint: {path}")

    def do_POST(self) -> None:
        """Handle POST requests."""
        path, params = self._parse_path()
        self._apply_delay()

        if self._check_injected_error(path, "POST"):
            return

        if not self._check_auth():
            return

        body = self._read_body()

        # Create test suite (Python provider format)
        if path == "/cli/e2e/suites":
            suite = self._create_suite(body)
            self._send_json_response({
                "success": True,
                "testSuiteUuid": suite.uuid,
                "uuid": suite.uuid,
            })
            return

        # Create commit suite (TypeScript CLI format)
        if path in ("/api/v1/e2e-commit-suites/", "/api/v1/commit-suites/"):
            suite = self._create_suite(body)
            self._send_json_response({
                "success": True,
                "uuid": suite.uuid,
                "testSuiteUuid": suite.uuid,
                "tunnelKey": suite.tunnel_key,
            })
            return

        # Create tunnel token
        if path == "/api/v1/ngrok/token/":
            suite_uuid = body.get("commitSuiteUuid")
            subdomain = body.get("subdomain", f"test-{uuid.uuid4().hex[:8]}")
            self._send_json_response({
                "token": f"mock-ngrok-token-{uuid.uuid4().hex[:16]}",
                "subdomain": subdomain,
            })
            return

        self._send_error_response(404, f"Unknown endpoint: {path}")

    def do_PATCH(self) -> None:
        """Handle PATCH requests."""
        path, params = self._parse_path()
        self._apply_delay()

        if self._check_injected_error(path, "PATCH"):
            return

        if not self._check_auth():
            return

        body = self._read_body()

        # Update commit suite
        if path.startswith("/api/v1/commit-suites/"):
            parts = path.rstrip("/").split("/")
            suite_uuid = parts[-1]
            suite = self._mock_server.suites.get(suite_uuid)
            if not suite:
                self._send_error_response(404, f"Suite {suite_uuid} not found")
                return

            # Update fields
            if "publicUrl" in body:
                suite.public_url = body["publicUrl"]
            if "testEnvironment" in body:
                suite.metadata["testEnvironment"] = body["testEnvironment"]

            self._send_json_response({"success": True, "uuid": suite.uuid})
            return

        self._send_error_response(404, f"Unknown endpoint: {path}")

    def _create_suite(self, body: Dict[str, Any]) -> MockTestSuite:
        """Create a new test suite from request body."""
        suite_uuid = f"mock-{uuid.uuid4().hex[:12]}"
        tunnel_key = f"tunnel-{uuid.uuid4().hex[:8]}"

        suite = MockTestSuite(
            uuid=suite_uuid,
            status="pending",
            run_status="pending",
            tunnel_key=tunnel_key,
            repo_name=body.get("repoName", "unknown"),
            branch_name=body.get("branchName", body.get("branch", "main")),
            commit_hash=body.get("commitHash", ""),
            metadata=body,
        )

        # Generate mock tests based on working changes
        working_changes = body.get("workingChanges", [])
        for i, change in enumerate(working_changes[:5]):  # Max 5 tests
            test = {
                "uuid": f"test-{uuid.uuid4().hex[:8]}",
                "name": f"Test for {change.get('file', f'file-{i}')}",
                "status": "pending",
                "curRun": {
                    "status": "pending",
                    "runScript": f"https://mock.debugg.ai/scripts/{suite_uuid}/test-{i}.spec.js",
                    "runGif": f"https://mock.debugg.ai/recordings/{suite_uuid}/test-{i}.gif",
                    "runJson": f"https://mock.debugg.ai/results/{suite_uuid}/test-{i}.json",
                },
            }
            suite.tests.append(test)

        # If no changes provided, create a default test
        if not suite.tests:
            suite.tests.append({
                "uuid": f"test-{uuid.uuid4().hex[:8]}",
                "name": "Default E2E Test",
                "status": "pending",
                "curRun": {
                    "status": "pending",
                    "runScript": f"https://mock.debugg.ai/scripts/{suite_uuid}/default.spec.js",
                },
            })

        self._mock_server.suites[suite_uuid] = suite
        self._mock_server.record_request("POST", "/suite", body)

        # Auto-progress if configured
        if self._mock_server.auto_complete_delay > 0:
            self._mock_server._schedule_suite_completion(suite_uuid)

        return suite


class MockDebuggAIServer:
    """
    Mock HTTP server simulating the DebuggAI API.

    Features:
    - Simulates all DebuggAI API endpoints
    - Configurable response delays
    - Error injection for testing error handling
    - Request recording for verification
    - Auto-completion of test suites
    """

    def __init__(
        self,
        port: int = 0,  # 0 = auto-assign
        host: str = "127.0.0.1",
        verbose: bool = False,
        valid_api_key: str = "test-api-key-12345",
        require_valid_api_key: bool = True,
    ):
        """
        Initialize the mock server.

        Args:
            port: Port to listen on (0 for auto-assign)
            host: Host to bind to
            verbose: Enable verbose logging
            valid_api_key: API key to accept as valid
            require_valid_api_key: Whether to validate API keys
        """
        self.host = host
        self.port = port
        self.verbose = verbose
        self.valid_api_key = valid_api_key
        self.require_valid_api_key = require_valid_api_key

        # State
        self.suites: Dict[str, MockTestSuite] = {}
        self.recorded_requests: List[Dict[str, Any]] = []
        self.injected_errors: Dict[str, InjectedError] = {}
        self.response_delay: float = 0.0
        self.auto_complete_delay: float = 0.0  # 0 = disabled

        # Server instance
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._completion_timers: List[threading.Timer] = []

    @property
    def base_url(self) -> str:
        """Get the base URL for the server."""
        if self._server:
            return f"http://{self.host}:{self._server.server_address[1]}"
        return f"http://{self.host}:{self.port}"

    @property
    def actual_port(self) -> int:
        """Get the actual port (useful when port=0 for auto-assign)."""
        if self._server:
            return self._server.server_address[1]
        return self.port

    def start(self) -> "MockDebuggAIServer":
        """Start the mock server in a background thread."""
        if self._server:
            return self

        # Create handler class with reference to this server
        handler = MockDebuggAIRequestHandler

        self._server = HTTPServer((self.host, self.port), handler)
        self._server.mock_server = self  # For handler access via _mock_server property

        self._thread = threading.Thread(target=self._server.serve_forever)
        self._thread.daemon = True
        self._thread.start()

        # Wait for server to be ready
        time.sleep(0.1)

        if self.verbose:
            print(f"MockDebuggAIServer started at {self.base_url}")

        return self

    def stop(self) -> None:
        """Stop the mock server."""
        # Cancel any pending completion timers
        for timer in self._completion_timers:
            timer.cancel()
        self._completion_timers.clear()

        if self._server:
            self._server.shutdown()
            self._server = None

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        if self.verbose:
            print("MockDebuggAIServer stopped")

    def reset(self) -> None:
        """Reset server state (suites, requests, errors)."""
        self.suites.clear()
        self.recorded_requests.clear()
        self.injected_errors.clear()
        self.response_delay = 0.0

    # ========================================================================
    # Configuration Methods
    # ========================================================================

    def set_response_delay(self, seconds: float) -> None:
        """Set delay for all responses (simulates slow API)."""
        self.response_delay = seconds

    def set_auto_complete_delay(self, seconds: float) -> None:
        """Set delay before auto-completing test suites (0 to disable)."""
        self.auto_complete_delay = seconds

    def inject_error(
        self,
        path: str,
        status_code: int,
        message: str,
        method: str = "GET",
        count: int = 1,
    ) -> None:
        """
        Inject an error for a specific endpoint.

        Args:
            path: URL path to inject error for
            status_code: HTTP status code to return
            message: Error message
            method: HTTP method (GET, POST, etc.)
            count: Number of times to return error (0 = forever)
        """
        key = f"{method}:{path}"
        self.injected_errors[key] = InjectedError(
            status_code=status_code, message=message, count=count
        )

    def clear_errors(self) -> None:
        """Clear all injected errors."""
        self.injected_errors.clear()

    # ========================================================================
    # Suite Management Methods
    # ========================================================================

    def create_suite(
        self,
        suite_uuid: Optional[str] = None,
        status: str = "pending",
        num_tests: int = 3,
    ) -> MockTestSuite:
        """
        Pre-create a test suite for testing.

        Args:
            suite_uuid: UUID for the suite (auto-generated if not provided)
            status: Initial status
            num_tests: Number of mock tests to create
        """
        if suite_uuid is None:
            suite_uuid = f"mock-{uuid.uuid4().hex[:12]}"

        suite = MockTestSuite(
            uuid=suite_uuid,
            status=status,
            run_status=status,
            tunnel_key=f"tunnel-{uuid.uuid4().hex[:8]}",
        )

        for i in range(num_tests):
            suite.tests.append({
                "uuid": f"test-{uuid.uuid4().hex[:8]}",
                "name": f"Mock Test {i + 1}",
                "status": "pending",
                "curRun": {
                    "status": "pending",
                    "runScript": f"https://mock.debugg.ai/scripts/{suite_uuid}/test-{i}.spec.js",
                },
            })

        self.suites[suite_uuid] = suite
        return suite

    def set_suite_status(
        self,
        suite_uuid: str,
        status: str,
        test_statuses: Optional[List[str]] = None,
    ) -> None:
        """
        Set the status of a test suite.

        Args:
            suite_uuid: UUID of the suite
            status: New status (pending, running, completed, failed)
            test_statuses: Optional list of statuses for individual tests
        """
        if suite_uuid not in self.suites:
            raise KeyError(f"Suite {suite_uuid} not found")

        suite = self.suites[suite_uuid]
        suite.status = status
        suite.run_status = status

        if test_statuses:
            for i, test_status in enumerate(test_statuses):
                if i < len(suite.tests):
                    suite.tests[i]["status"] = test_status
                    if suite.tests[i].get("curRun"):
                        suite.tests[i]["curRun"]["status"] = test_status

    def get_suite(self, suite_uuid: str) -> Optional[MockTestSuite]:
        """Get a suite by UUID."""
        return self.suites.get(suite_uuid)

    def _schedule_suite_completion(self, suite_uuid: str) -> None:
        """Schedule a suite to auto-complete after the configured delay."""
        if self.auto_complete_delay <= 0:
            return

        def complete_suite():
            if suite_uuid in self.suites:
                suite = self.suites[suite_uuid]
                suite.status = "completed"
                suite.run_status = "completed"
                for test in suite.tests:
                    test["status"] = "completed"
                    if test.get("curRun"):
                        test["curRun"]["status"] = "completed"

        timer = threading.Timer(self.auto_complete_delay, complete_suite)
        timer.daemon = True
        timer.start()
        self._completion_timers.append(timer)

    # ========================================================================
    # Request Recording Methods
    # ========================================================================

    def record_request(
        self, method: str, path: str, body: Optional[Dict[str, Any]] = None
    ) -> None:
        """Record a request for later verification."""
        self.recorded_requests.append({
            "method": method,
            "path": path,
            "body": body,
            "timestamp": time.time(),
        })

    def get_recorded_requests(
        self, method: Optional[str] = None, path: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get recorded requests, optionally filtered by method/path."""
        requests = self.recorded_requests
        if method:
            requests = [r for r in requests if r["method"] == method]
        if path:
            requests = [r for r in requests if path in r["path"]]
        return requests

    def clear_recorded_requests(self) -> None:
        """Clear all recorded requests."""
        self.recorded_requests.clear()

    # ========================================================================
    # Context Manager Support
    # ========================================================================

    def __enter__(self) -> "MockDebuggAIServer":
        """Context manager entry."""
        return self.start()

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.stop()


# ============================================================================
# Pytest Fixtures
# ============================================================================


def mock_debuggai_server():
    """
    Pytest fixture for MockDebuggAIServer.

    Usage:
        def test_something(mock_debuggai_server):
            with mock_debuggai_server() as server:
                # Use server.base_url
                ...
    """
    return MockDebuggAIServer


# Convenience fixture factory
def create_mock_server(**kwargs) -> MockDebuggAIServer:
    """Create and start a mock server with the given options."""
    server = MockDebuggAIServer(**kwargs)
    return server.start()
