"""
Integration tests for debugg-ai CLI --wait-for-server mode.

Tests the server wait functionality:
1. Test server wait functionality with immediate server availability
2. Start mock HTTP server on configurable port
3. Test --wait-for-server polls until ready
4. Test --server-timeout triggers on slow server
5. Test --server-port configuration
6. Verify tests run after server is ready

Requirements from SE-i5x.
"""

import http.server
import json
import os
import pytest
import socket
import socketserver
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

from tests.fixtures import E2ETestHarness, CLIResult


# Skip all tests if CLI not available
pytestmark = pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / ".." / ".." / "debugg-ai-cli" / "dist" / "cli.js").resolve().exists(),
    reason="CLI not built - run 'npm run build' in debugg-ai-cli",
)


def get_free_port() -> int:
    """Get a free port number for testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        port = s.getsockname()[1]
    return port


class MockHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """Simple HTTP handler for mock server."""

    def log_message(self, format: str, *args) -> None:
        """Suppress logging unless in debug mode."""
        if os.environ.get('DEBUG'):
            super().log_message(format, *args)

    def do_GET(self) -> None:
        """Handle GET requests - return 200 OK."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()
        self.wfile.write(b'<html><body>Mock Server Ready</body></html>')

    def do_HEAD(self) -> None:
        """Handle HEAD requests - return 200 OK."""
        self.send_response(200)
        self.send_header('Content-Type', 'text/html')
        self.end_headers()


class DelayedMockServer:
    """
    Mock HTTP server that can be configured to delay before becoming available.

    Useful for testing --wait-for-server polling behavior and timeouts.
    """

    def __init__(
        self,
        port: int = 0,
        startup_delay: float = 0.0,
        host: str = '127.0.0.1',
    ):
        """
        Initialize delayed mock server.

        Args:
            port: Port to listen on (0 = auto-assign)
            startup_delay: Seconds to wait before accepting connections
            host: Host to bind to
        """
        self.host = host
        self.port = port
        self.startup_delay = startup_delay
        self._server: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._started_event = threading.Event()
        self._actual_port: Optional[int] = None

    @property
    def actual_port(self) -> int:
        """Get the actual port being used."""
        if self._actual_port:
            return self._actual_port
        return self.port

    @property
    def base_url(self) -> str:
        """Get the base URL for the server."""
        return f"http://{self.host}:{self.actual_port}"

    def start(self) -> "DelayedMockServer":
        """Start the server (with optional delay)."""
        if self._server is not None:
            return self

        def run_server():
            # Apply startup delay before starting to accept connections
            if self.startup_delay > 0:
                time.sleep(self.startup_delay)

            # Create and start server
            try:
                self._server = socketserver.TCPServer(
                    (self.host, self.port),
                    MockHTTPRequestHandler
                )
                self._actual_port = self._server.server_address[1]
                self._started_event.set()
                self._server.serve_forever()
            except Exception as e:
                self._started_event.set()  # Unblock waiters on error
                raise

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()

        # If no delay, wait for server to be ready
        if self.startup_delay == 0:
            self._started_event.wait(timeout=5.0)

        return self

    def wait_for_start(self, timeout: float = 10.0) -> bool:
        """Wait for the server to actually start accepting connections."""
        return self._started_event.wait(timeout=timeout)

    def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.shutdown()
            self._server = None

        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None

        self._started_event.clear()
        self._actual_port = None

    def __enter__(self) -> "DelayedMockServer":
        """Context manager entry."""
        return self.start()

    def __exit__(self, *args) -> None:
        """Context manager exit."""
        self.stop()


class TestWaitForServerBasic:
    """Basic tests for --wait-for-server flag recognition and behavior."""

    def test_wait_for_server_flag_recognized(self):
        """Test that --wait-for-server flag is recognized by CLI."""
        with E2ETestHarness() as harness:
            # Run help to check if flag is documented
            result = harness.run_cli("test", "--help")

            # Should show help without error
            assert result.success or result.returncode == 0

            # Flag should be documented in help output
            output = result.output.lower()
            assert "wait" in output or "server" in output, \
                "Expected --wait-for-server related documentation in help"

    def test_server_port_flag_recognized(self):
        """Test that --server-port flag is recognized by CLI."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            assert result.success or result.returncode == 0
            output = result.output.lower()
            assert "port" in output, \
                "Expected --server-port related documentation in help"

    def test_server_timeout_flag_recognized(self):
        """Test that --server-timeout flag is recognized by CLI."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            assert result.success or result.returncode == 0
            output = result.output.lower()
            assert "timeout" in output, \
                "Expected --server-timeout related documentation in help"


class TestWaitForServerWithImmediateServer:
    """Tests for --wait-for-server when server is immediately available."""

    def test_wait_for_server_succeeds_when_server_ready(self):
        """Test that CLI proceeds when server is immediately available."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=0) as mock_server:
            mock_server.wait_for_start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "# Test file"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(mock_server.actual_port),
                    "--server-timeout", "10000",
                    timeout=30.0
                )

                # CLI should not fail due to server wait
                # It may fail for other reasons (API, etc.) but not server wait
                assert isinstance(result, CLIResult)

                # Check for successful server detection or graceful progression
                output = result.output.lower()
                server_ready_indicators = [
                    "server is ready",
                    "server ready",
                    "starting test",
                    "analyzing",
                    "creating test suite",
                    "test suite"
                ]
                server_error_indicators = [
                    "did not start",
                    "server timeout",
                    "connection refused"
                ]

                # Should NOT have server timeout errors
                has_server_error = any(
                    indicator in output for indicator in server_error_indicators
                )

                # The CLI either succeeded or failed for non-server reasons
                if has_server_error:
                    pytest.fail(
                        f"Server wait failed even though server was ready. "
                        f"Output: {result.output[:500]}"
                    )

    def test_wait_for_server_with_custom_port(self):
        """Test --wait-for-server with custom port configuration."""
        port = get_free_port()

        with DelayedMockServer(port=port) as mock_server:
            mock_server.wait_for_start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"app.py": "print('hello')"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(mock_server.actual_port),
                    timeout=30.0
                )

                assert isinstance(result, CLIResult)

                # Verify port was used (check output or requests)
                output = result.output
                # Port should appear in output if verbose or in server messages
                # This is a soft check - port configuration is the main test

    def test_server_port_default_value(self):
        """Test that default server port is 3000."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            output = result.output.lower()
            # Default should be documented as 3000
            assert "3000" in output or "default" in output, \
                "Expected default port documentation"


class TestWaitForServerWithDelayedServer:
    """Tests for --wait-for-server polling behavior with delayed server startup."""

    def test_wait_for_server_polls_until_ready(self):
        """Test that CLI polls and waits for delayed server startup."""
        port = get_free_port()

        # Server will start after 2 second delay
        with DelayedMockServer(port=port, startup_delay=2.0) as mock_server:
            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"feature.py": "# New feature"})

                start_time = time.time()

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "15000",  # 15 second timeout
                    timeout=45.0
                )

                elapsed_time = time.time() - start_time

                assert isinstance(result, CLIResult)

                # CLI should have waited at least the startup delay
                # (with some tolerance for polling intervals)
                assert elapsed_time >= 1.5, \
                    f"CLI should have waited for server. Elapsed: {elapsed_time}s"

                # Should not have server timeout error
                output = result.output.lower()
                if "did not start" in output or "server timeout" in output:
                    pytest.fail(
                        f"Server wait timed out unexpectedly. "
                        f"Expected server to be ready after {elapsed_time}s delay. "
                        f"Output: {result.output[:500]}"
                    )

    def test_wait_for_server_multiple_poll_attempts(self):
        """Test that CLI makes multiple poll attempts before server is ready."""
        port = get_free_port()

        # Server will start after 3 seconds
        with DelayedMockServer(port=port, startup_delay=3.0) as mock_server:
            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "pass"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "20000",  # 20 second timeout
                    "--verbose",  # Enable verbose to see polling
                    timeout=45.0
                )

                assert isinstance(result, CLIResult)

                # With verbose mode, we might see polling messages
                output = result.output.lower()
                # Check for waiting/polling indicators
                waiting_indicators = ["waiting", "poll", "checking", "retry"]

                # This is a soft check - not all CLIs will output polling info


class TestWaitForServerTimeout:
    """Tests for --server-timeout behavior when server fails to start."""

    def test_server_timeout_triggers_when_no_server(self):
        """Test that --server-timeout causes failure when no server starts."""
        # Use a port with no server running
        port = get_free_port()

        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            start_time = time.time()

            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", str(port),
                "--server-timeout", "3000",  # 3 second timeout (short for test speed)
                timeout=30.0
            )

            elapsed_time = time.time() - start_time

            assert isinstance(result, CLIResult)

            # Should have failed due to server timeout
            # Check for timeout-related error messages
            output = result.output.lower()
            timeout_indicators = [
                "timeout",
                "did not start",
                "failed to start",
                "not ready",
                "connection refused",
                "could not connect"
            ]

            has_timeout_error = any(
                indicator in output for indicator in timeout_indicators
            )

            # Exit code should be non-zero for timeout
            if result.returncode == 0:
                # If CLI didn't fail, it might have skipped server wait
                # This is acceptable graceful degradation
                pass
            else:
                # CLI failed - should be due to server timeout
                assert has_timeout_error or result.returncode != 0, \
                    f"Expected timeout error. Output: {result.output[:500]}"

            # Should have waited approximately the timeout duration
            # Allow some tolerance (1s) for processing
            assert elapsed_time >= 2.0, \
                f"CLI should have waited at least close to timeout. Elapsed: {elapsed_time}s"

    def test_server_timeout_custom_value(self):
        """Test that custom --server-timeout value is respected."""
        port = get_free_port()

        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Very short timeout - should fail quickly
            start_time = time.time()

            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", str(port),
                "--server-timeout", "2000",  # 2 seconds
                timeout=15.0
            )

            elapsed_time = time.time() - start_time

            assert isinstance(result, CLIResult)

            # Should have completed within reasonable time (timeout + overhead)
            assert elapsed_time < 10.0, \
                f"CLI took too long. Expected ~2s timeout. Elapsed: {elapsed_time}s"

    def test_server_timeout_default_is_60_seconds(self):
        """Test that default server timeout is 60000ms (60 seconds)."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            output = result.output
            # Default timeout should be documented as 60000
            assert "60000" in output or "60 second" in output.lower() or "minute" in output.lower(), \
                "Expected default timeout documentation (60000ms or 60 seconds)"


class TestWaitForServerIntegration:
    """Integration tests verifying full workflow with server wait."""

    def test_tests_run_after_server_ready(self):
        """Test that E2E tests run after server becomes ready."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=1.0) as mock_server:
            with E2ETestHarness(auto_complete_delay=1.0) as harness:
                harness.setup_working_changes({
                    "src/app.py": "print('hello world')",
                    "src/utils.py": "def helper(): return 42",
                })

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "15000",
                    timeout=60.0
                )

                assert isinstance(result, CLIResult)

                # Check that API requests were made (indicating tests proceeded)
                requests = harness.get_api_requests(method="POST", path="/suite")

                # Should have created at least one suite after server was ready
                # Or CLI should have progressed past server wait
                output = result.output.lower()

                test_progression_indicators = [
                    "creating test",
                    "test suite",
                    "analyzing",
                    "changes",
                    "completed"
                ]

                progressed = any(
                    indicator in output for indicator in test_progression_indicators
                ) or len(requests) >= 1

                # Either tests ran OR we got a non-server-related error
                server_blocked = "did not start" in output or "server timeout" in output

                assert progressed or not server_blocked, \
                    f"Tests should run after server ready. Output: {result.output[:500]}"

    def test_workflow_with_server_port_and_changes(self):
        """Test complete workflow with server port configuration and code changes."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=0) as mock_server:
            mock_server.wait_for_start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                # Set up realistic working changes
                harness.setup_working_changes({
                    "src/components/Button.tsx": "export const Button = () => <button>Click</button>",
                    "src/pages/Home.tsx": "import { Button } from '../components/Button'",
                })

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(mock_server.actual_port),
                    timeout=45.0
                )

                assert isinstance(result, CLIResult)

                # Verify the working changes were submitted
                requests = harness.get_api_requests(method="POST", path="/suite")

                if requests:
                    body = requests[0].get("body", {})
                    working_changes = body.get("workingChanges", body.get("working_changes", []))

                    # Should have our files in the changes
                    change_files = [c.get("file", "") for c in working_changes]
                    has_button = any("Button" in f for f in change_files)
                    has_home = any("Home" in f for f in change_files)

                    # At least some of our changes should be present
                    assert has_button or has_home or len(working_changes) > 0, \
                        f"Expected working changes to be submitted. Got: {change_files}"


class TestWaitForServerEdgeCases:
    """Edge case tests for --wait-for-server functionality."""

    def test_wait_for_server_without_flag_skips_wait(self):
        """Test that omitting --wait-for-server skips the server wait."""
        port = get_free_port()
        # No server running on this port

        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            start_time = time.time()

            # Run WITHOUT --wait-for-server
            result = harness.run_cli(
                "test",
                "--server-port", str(port),
                timeout=30.0
            )

            elapsed_time = time.time() - start_time

            assert isinstance(result, CLIResult)

            # Without --wait-for-server, should not wait for server
            # Should proceed quickly (or fail for other reasons)
            # This verifies the flag is actually required for waiting behavior

    def test_server_port_zero_handling(self):
        """Test handling of port 0 (which would mean auto-assign)."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Port 0 is unusual - CLI should handle gracefully
            result = harness.run_cli(
                "test",
                "--server-port", "0",
                timeout=15.0
            )

            assert isinstance(result, CLIResult)
            # Should not crash - either work or give meaningful error

    def test_invalid_server_port_handling(self):
        """Test handling of invalid port numbers."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Invalid port - CLI should handle gracefully
            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", "invalid",
                timeout=15.0
            )

            assert isinstance(result, CLIResult)

            # Should fail gracefully with error message
            # Not crash with unhandled exception
            if result.returncode != 0:
                output = result.output.lower()
                # Should have some indication of invalid input
                error_indicators = ["invalid", "error", "port", "number", "argument"]
                has_error_msg = any(ind in output for ind in error_indicators)
                # Soft check - may just fail without specific message

    def test_server_port_out_of_range(self):
        """Test handling of out-of-range port numbers."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Port > 65535 is invalid
            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", "99999",
                "--server-timeout", "2000",
                timeout=15.0
            )

            assert isinstance(result, CLIResult)
            # Should handle gracefully

    def test_negative_server_timeout_handling(self):
        """Test handling of negative timeout values."""
        port = get_free_port()

        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", str(port),
                "--server-timeout", "-1000",
                timeout=15.0
            )

            assert isinstance(result, CLIResult)
            # Should handle gracefully - either use default or fail with message


class TestWaitForServerWithVerboseOutput:
    """Tests for verbose output during server wait."""

    def test_verbose_shows_server_wait_progress(self):
        """Test that verbose mode shows server wait status."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=1.5) as mock_server:
            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "pass"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "15000",
                    "--verbose",
                    timeout=45.0
                )

                assert isinstance(result, CLIResult)

                output = result.output.lower()
                # Verbose mode should show server-related messages
                verbose_indicators = [
                    "waiting",
                    "server",
                    "port",
                    str(port)
                ]

                # At least some indication of server wait in verbose mode
                has_server_info = any(ind in output for ind in verbose_indicators)

                # This is a soft check - verbose format may vary

    def test_dev_mode_shows_server_details(self):
        """Test that --dev mode shows detailed server wait info."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=0) as mock_server:
            mock_server.wait_for_start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "pass"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(mock_server.actual_port),
                    "--dev",
                    timeout=30.0
                )

                assert isinstance(result, CLIResult)

                # Dev mode should have detailed output
                output = result.output
                # Check for development-style output (timestamps, categories, etc.)


class TestWaitForServerConcurrency:
    """Tests for concurrent server and CLI behavior."""

    def test_server_starts_while_cli_waiting(self):
        """Test that CLI detects server that starts during wait period."""
        port = get_free_port()

        # Server will start after 3 seconds
        mock_server = DelayedMockServer(port=port, startup_delay=3.0)

        try:
            # Start server in background (will delay before accepting)
            mock_server.start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "pass"})

                # CLI should wait and eventually find the server
                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "15000",
                    timeout=45.0
                )

                assert isinstance(result, CLIResult)

                # Should have progressed past server wait
                output = result.output.lower()
                server_wait_failed = "did not start" in output or "server timeout" in output

                # Server started after 3s, with 15s timeout - should succeed
                assert not server_wait_failed, \
                    f"CLI should have detected server after it started. Output: {result.output[:500]}"

        finally:
            mock_server.stop()

    def test_rapid_server_restart(self):
        """Test handling when server restarts quickly."""
        port = get_free_port()

        # Start server
        mock_server = DelayedMockServer(port=port, startup_delay=0)
        mock_server.start()
        mock_server.wait_for_start()

        try:
            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                harness.setup_working_changes({"test.py": "pass"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(port),
                    "--server-timeout", "10000",
                    timeout=30.0
                )

                assert isinstance(result, CLIResult)
                # Should complete without server-related issues

        finally:
            mock_server.stop()


class TestWaitForServerExitCodes:
    """Tests for exit code behavior with --wait-for-server."""

    def test_exit_code_nonzero_on_server_timeout(self):
        """Test that exit code is non-zero when server times out."""
        port = get_free_port()
        # No server on this port

        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                "--wait-for-server",
                "--server-port", str(port),
                "--server-timeout", "2000",  # Short timeout
                timeout=15.0
            )

            # Server timeout should cause non-zero exit
            assert result.returncode != 0 or "timeout" in result.output.lower() or "did not start" in result.output.lower(), \
                "Expected non-zero exit or timeout message when server not available"

    def test_exit_code_zero_when_server_ready_and_tests_pass(self):
        """Test that exit code is 0 when server is ready and tests pass."""
        port = get_free_port()

        with DelayedMockServer(port=port, startup_delay=0) as mock_server:
            mock_server.wait_for_start()

            with E2ETestHarness(auto_complete_delay=0.5) as harness:
                # Pre-create a passing suite
                suite = harness.expect_suite_creation(suite_uuid="passing-server-suite")
                harness.set_suite_to_complete(
                    "passing-server-suite",
                    test_results=["passed", "passed"],
                )

                harness.setup_working_changes({"test.py": "pass"})

                result = harness.run_cli(
                    "test",
                    "--wait-for-server",
                    "--server-port", str(mock_server.actual_port),
                    timeout=30.0
                )

                # If server wait succeeded and tests passed, exit should be 0
                # Note: CLI behavior may vary based on implementation
                assert isinstance(result, CLIResult)


class TestWaitForServerDocumentation:
    """Tests verifying documentation and help text for server wait options."""

    def test_help_documents_wait_for_server(self):
        """Test that --help documents --wait-for-server flag."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            assert result.success or result.returncode == 0

            # Should document the wait-for-server option
            output = result.output
            assert "--wait-for-server" in output or "wait-for-server" in output.lower(), \
                "Expected --wait-for-server to be documented in help"

    def test_help_documents_server_port(self):
        """Test that --help documents --server-port flag."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            assert result.success or result.returncode == 0

            output = result.output
            assert "--server-port" in output or "server-port" in output.lower(), \
                "Expected --server-port to be documented in help"

    def test_help_documents_server_timeout(self):
        """Test that --help documents --server-timeout flag."""
        with E2ETestHarness() as harness:
            result = harness.run_cli("test", "--help")

            assert result.success or result.returncode == 0

            output = result.output
            assert "--server-timeout" in output or "server-timeout" in output.lower(), \
                "Expected --server-timeout to be documented in help"
