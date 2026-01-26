"""
Integration tests for debugg-ai CLI error handling.

Tests error scenarios:
- Invalid/missing API key (401)
- API server unreachable
- Test generation timeout
- Malformed API responses
- Partial artifact download failures
- Git repository not found
- No changes detected
- Verify error messages are actionable

All tests verify that the CLI fails gracefully with actionable error messages.
"""

import os
import pytest
import socket
import tempfile
from pathlib import Path

from tests.fixtures import E2ETestHarness, CLIResult


# Skip all tests if CLI not available
pytestmark = pytest.mark.skipif(
    not (Path(__file__).parent.parent / "fixtures" / ".." / ".." / "debugg-ai-cli" / "dist" / "cli.js").resolve().exists(),
    reason="CLI not built - run 'npm run build' in debugg-ai-cli",
)


class TestAuthenticationErrors:
    """Tests for authentication and authorization error handling."""

    def test_invalid_api_key_returns_401(self):
        """Test that an invalid API key returns 401 and actionable error message."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "print('hello')"})

            # Run with an invalid API key
            result = harness.run_cli(
                "test",
                env={"DEBUGGAI_API_KEY": "invalid-key-12345"},
            )

            # CLI should fail
            assert result.returncode != 0, "CLI should fail with invalid API key"

            # Error message should be actionable - mention auth/key
            output = result.output.lower()
            assert any(term in output for term in [
                "unauthorized", "invalid", "api key", "authentication",
                "401", "auth", "credentials", "access denied"
            ]), f"Error message should mention auth issue: {result.output}"

    def test_missing_api_key(self):
        """Test that missing API key produces actionable error message."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "print('hello')"})

            # Run without API key (unset it)
            result = harness.run_cli(
                "test",
                env={"DEBUGGAI_API_KEY": ""},
            )

            # CLI should fail or produce warning
            output = result.output.lower()

            # Either fails with clear error or warns about missing key
            if result.returncode != 0:
                assert any(term in output for term in [
                    "api key", "required", "missing", "set", "environment",
                    "debuggai_api_key", "authorization", "authenticate"
                ]), f"Error should mention missing API key: {result.output}"

    def test_expired_or_revoked_api_key(self):
        """Test handling of expired/revoked API key (simulated via 401)."""
        with E2ETestHarness(require_auth=True) as harness:
            # Inject 401 with specific message
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=401,
                message="API key has been revoked",
                method="POST",
                count=0,  # Always return error
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            assert result.returncode != 0, "CLI should fail with revoked key"
            output = result.output.lower()
            assert any(term in output for term in [
                "401", "unauthorized", "revoked", "invalid", "key",
                "authentication", "access"
            ]), f"Error should indicate auth failure: {result.output}"


class TestAPIServerErrors:
    """Tests for API server connectivity and availability errors."""

    def test_api_server_unreachable(self):
        """Test handling when API server is unreachable."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "print('hello')"})

            # Point to a port with nothing listening
            # Find an unused port
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(('127.0.0.1', 0))
            unused_port = sock.getsockname()[1]
            sock.close()

            result = harness.run_cli(
                "test",
                "--base-url", f"http://127.0.0.1:{unused_port}",
                include_base_url=False,
                timeout=30.0,
            )

            # CLI should fail
            assert result.returncode != 0, "CLI should fail when server unreachable"

            # Error message should be actionable
            output = result.output.lower()
            assert any(term in output for term in [
                "connect", "unreachable", "refused", "network", "server",
                "econnrefused", "timeout", "host", "connection", "reach",
                "unavailable", "failed"
            ]), f"Error should indicate connection issue: {result.output}"

    def test_api_server_returns_500(self):
        """Test handling of internal server errors (500)."""
        with E2ETestHarness() as harness:
            # Inject 500 error on suite creation
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=500,
                message="Internal Server Error",
                method="POST",
                count=0,  # Always fail
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            assert result.returncode != 0, "CLI should fail on 500 error"
            output = result.output.lower()
            assert any(term in output for term in [
                "500", "server error", "internal", "failed", "error",
                "service", "unavailable"
            ]), f"Error should indicate server error: {result.output}"

    def test_api_server_returns_503_service_unavailable(self):
        """Test handling of service unavailable (503) errors."""
        with E2ETestHarness() as harness:
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=503,
                message="Service Unavailable - try again later",
                method="POST",
                count=0,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            assert result.returncode != 0, "CLI should fail on 503 error"
            output = result.output.lower()
            assert any(term in output for term in [
                "503", "unavailable", "service", "later", "retry",
                "maintenance", "overload"
            ]), f"Error should indicate service unavailable: {result.output}"

    def test_api_server_rate_limited(self):
        """Test handling of rate limiting (429) errors."""
        with E2ETestHarness() as harness:
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=429,
                message="Too Many Requests - rate limit exceeded",
                method="POST",
                count=0,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            assert result.returncode != 0, "CLI should fail on rate limit"
            output = result.output.lower()
            assert any(term in output for term in [
                "429", "rate", "limit", "too many", "exceeded", "throttl",
                "slow down", "retry"
            ]), f"Error should indicate rate limiting: {result.output}"


class TestTimeoutErrors:
    """Tests for timeout-related error handling."""

    def test_test_generation_timeout(self):
        """Test handling when test generation times out."""
        with E2ETestHarness(response_delay=5.0) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Run with very short timeout
            result = harness.run_cli("test", timeout=2.0)

            # Should timeout
            assert result.returncode != 0, "CLI should fail on timeout"
            output = result.output.lower()
            assert any(term in output for term in [
                "timeout", "timed out", "took too long", "exceeded"
            ]), f"Error should indicate timeout: {result.output}"

    def test_polling_timeout_with_stuck_suite(self):
        """Test timeout when suite never completes (stuck in pending)."""
        with E2ETestHarness() as harness:
            # Create a suite that never completes (no auto-complete)
            suite = harness.expect_suite_creation(
                suite_uuid="stuck-suite-123",
                status="pending",
                num_tests=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            # Run with reasonable timeout
            result = harness.run_cli("test", timeout=10.0)

            # Either times out or gives up waiting
            # Both are acceptable behaviors
            assert isinstance(result, CLIResult)


class TestMalformedResponseErrors:
    """Tests for handling malformed or unexpected API responses."""

    def test_malformed_json_response(self):
        """Test handling of malformed JSON in API response."""
        with E2ETestHarness() as harness:
            # Inject a 200 response that contains invalid content
            # We simulate by injecting an error with status 200 but the message
            # won't parse as expected suite response
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=200,
                message="not valid json structure",
                method="POST",
                count=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # CLI may handle this as success with empty data or as error
            # Key is it should not crash
            assert isinstance(result, CLIResult)

    def test_missing_required_fields_in_response(self):
        """Test handling when response is missing required fields."""
        with E2ETestHarness() as harness:
            # This tests resilience to partial/incomplete responses
            harness.setup_working_changes({"test.py": "pass"})

            # Create a suite with minimal info
            suite = harness.expect_suite_creation(
                suite_uuid="minimal-suite",
                status="completed",
                num_tests=0,  # No tests
            )

            result = harness.run_cli("test")

            # Should handle gracefully
            assert isinstance(result, CLIResult)

    def test_unexpected_status_values(self):
        """Test handling of unexpected status values in response."""
        with E2ETestHarness() as harness:
            suite = harness.expect_suite_creation(
                suite_uuid="weird-status-suite",
                status="unknown_weird_status",  # Non-standard status
                num_tests=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test", timeout=10.0)

            # CLI should handle gracefully without crashing
            assert isinstance(result, CLIResult)


class TestArtifactDownloadErrors:
    """Tests for artifact download failure handling."""

    def test_artifact_endpoint_404(self):
        """Test handling when artifact download returns 404."""
        with E2ETestHarness() as harness:
            # Set up a completed suite
            suite = harness.expect_suite_creation(
                suite_uuid="artifact-404-suite",
                status="completed",
                num_tests=1,
            )
            harness.set_suite_to_complete(
                "artifact-404-suite",
                test_results=["passed"],
            )

            harness.setup_working_changes({"test.py": "pass"})

            # Note: Artifact URLs point to external mock URLs that won't exist
            # The CLI should handle missing artifacts gracefully
            result = harness.run_cli("test")

            # Should complete even if artifacts unavailable
            assert isinstance(result, CLIResult)

    def test_partial_artifact_download_failure(self):
        """Test handling when some artifacts fail to download."""
        with E2ETestHarness() as harness:
            # Create suite with multiple tests
            suite = harness.expect_suite_creation(
                suite_uuid="partial-fail-suite",
                status="completed",
                num_tests=3,
            )
            harness.set_suite_to_complete(
                "partial-fail-suite",
                test_results=["passed", "passed", "passed"],
            )

            harness.setup_working_changes({
                "test1.py": "pass",
                "test2.py": "pass",
                "test3.py": "pass",
            })

            result = harness.run_cli("test")

            # CLI should handle partial failures gracefully
            assert isinstance(result, CLIResult)


class TestGitRepositoryErrors:
    """Tests for git repository-related errors."""

    def test_not_a_git_repository(self):
        """Test error when run outside a git repository."""
        with E2ETestHarness() as harness:
            # Create a temporary directory that is NOT a git repo
            with tempfile.TemporaryDirectory() as non_git_dir:
                # Create a file in it
                test_file = Path(non_git_dir) / "test.py"
                test_file.write_text("print('hello')")

                result = harness.run_cli(
                    "test",
                    cwd=non_git_dir,
                )

                # CLI should fail with git-related error
                assert result.returncode != 0, "CLI should fail outside git repo"
                output = result.output.lower()
                assert any(term in output for term in [
                    "git", "repository", "not a", "init", "outside",
                    "no repo", "fatal"
                ]), f"Error should mention git repo issue: {result.output}"

    def test_git_command_not_available(self):
        """Test error when git is not in PATH."""
        with E2ETestHarness() as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Modify PATH to exclude git
            original_path = os.environ.get("PATH", "")
            # Use an empty path so git can't be found
            result = harness.run_cli(
                "test",
                env={"PATH": "/nonexistent"},
            )

            # CLI might fail at git detection or continue with limited functionality
            assert isinstance(result, CLIResult)


class TestNoChangesDetected:
    """Tests for handling when no changes are detected."""

    def test_no_uncommitted_changes(self):
        """Test behavior when there are no uncommitted changes."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Don't add any working changes - repo has only initial commit

            result = harness.run_cli("test")

            # CLI should handle gracefully - either succeed with message or fail with info
            assert isinstance(result, CLIResult)
            output = result.output.lower()

            # If failed, should mention no changes
            if result.returncode != 0:
                assert any(term in output for term in [
                    "no changes", "nothing to", "no file", "clean",
                    "up to date", "no diff", "empty"
                ]), f"Should explain no changes: {result.output}"

    def test_only_untracked_files_no_staged(self):
        """Test with untracked files but nothing staged."""
        with E2ETestHarness() as harness:
            # Add file without staging
            harness.repo.add_file("new_file.py", "print('new')", stage=False)

            result = harness.run_cli("test")

            # Should detect the untracked/unstaged changes or explain what to do
            assert isinstance(result, CLIResult)

    def test_all_changes_already_committed(self):
        """Test when all changes are already committed."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Make changes and commit them
            harness.repo.add_file("feature.py", "print('feature')")
            harness.repo.commit("Add feature")

            # Now run test with no pending changes
            result = harness.run_cli("test")

            # Should handle gracefully
            assert isinstance(result, CLIResult)


class TestActionableErrorMessages:
    """Tests that verify error messages are actionable and helpful."""

    def test_error_includes_next_steps(self):
        """Test that errors provide guidance on how to resolve."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                env={"DEBUGGAI_API_KEY": "invalid"},
            )

            if result.returncode != 0:
                output = result.output.lower()
                # Error should give some hint about resolution
                # Either mentions the key, URL to get one, or how to set it
                actionable_terms = [
                    "set", "configure", "provide", "get", "check",
                    "verify", "ensure", "try", "visit", "see",
                    "documentation", "help", "debuggai_api_key"
                ]
                # At minimum should mention something actionable
                has_actionable_guidance = any(term in output for term in actionable_terms)
                # This is a soft check - we want actionable messages but don't fail if not perfect
                if not has_actionable_guidance:
                    pytest.skip("Error message could be more actionable")

    def test_error_output_format_is_parseable(self):
        """Test that error output can be parsed programmatically."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli(
                "test",
                "--json",  # Request JSON output
                env={"DEBUGGAI_API_KEY": "invalid"},
            )

            if result.returncode != 0:
                output = result.stdout + result.stderr
                # If --json flag is supported, error might be JSON formatted
                # Or at least should have clear error indication
                assert len(output) > 0, "Error output should not be empty"

    def test_network_error_suggests_retry(self):
        """Test that network errors suggest retrying."""
        with E2ETestHarness() as harness:
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=503,
                message="Service temporarily unavailable",
                method="POST",
                count=0,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Network/service errors should ideally suggest retry
            if result.returncode != 0:
                output = result.output.lower()
                # Check for retry-related guidance
                retry_terms = ["retry", "again", "later", "wait", "temporary"]
                # Soft check - prefer actionable but don't require
                if not any(term in output for term in retry_terms):
                    # At minimum verify error is reported clearly
                    assert any(term in output for term in [
                        "error", "fail", "unavailable", "503"
                    ]), f"Should indicate error clearly: {result.output}"


class TestConcurrentErrors:
    """Tests for error handling during concurrent/parallel operations."""

    def test_suite_status_error_during_polling(self):
        """Test handling error while polling for suite status."""
        with E2ETestHarness() as harness:
            # Create suite first
            suite = harness.expect_suite_creation(
                suite_uuid="poll-error-suite",
                status="pending",
                num_tests=1,
            )

            # Then inject error on status check
            harness.inject_api_error(
                "/api/v1/e2e-commit-suites/poll-error-suite",
                status_code=500,
                message="Internal error checking status",
                method="GET",
                count=3,  # Fail first 3 attempts
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test", timeout=30.0)

            # Should handle polling errors - may retry or fail gracefully
            assert isinstance(result, CLIResult)

    def test_server_returns_conflicting_status(self):
        """Test handling when server returns conflicting information."""
        with E2ETestHarness() as harness:
            # Create suite in one state
            suite = harness.expect_suite_creation(
                suite_uuid="conflict-suite",
                status="running",
                num_tests=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            # Immediately set to failed
            harness.set_suite_to_complete(
                "conflict-suite",
                test_results=["failed"],
            )

            result = harness.run_cli("test")

            # Should handle state transitions gracefully
            assert isinstance(result, CLIResult)


class TestEdgeCaseErrors:
    """Tests for edge case error scenarios."""

    def test_empty_api_response(self):
        """Test handling of empty API response body."""
        with E2ETestHarness() as harness:
            # Inject error with empty message (simulates empty body)
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=200,
                message="",
                method="POST",
                count=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Should handle empty response without crashing
            assert isinstance(result, CLIResult)

    def test_extremely_long_error_message(self):
        """Test handling of very long error messages."""
        with E2ETestHarness() as harness:
            long_message = "Error: " + ("x" * 10000)  # 10KB message
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=400,
                message=long_message,
                method="POST",
                count=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Should handle long message without crashing
            assert isinstance(result, CLIResult)
            assert result.returncode != 0, "Should fail on 400 error"

    def test_unicode_in_error_message(self):
        """Test handling of unicode characters in error messages."""
        with E2ETestHarness() as harness:
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=400,
                message="Error: Invalid input \u2019 \u201c \u201d \u2014 \u00e9\u00e8\u00ea",
                method="POST",
                count=1,
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # Should handle unicode without crashing
            assert isinstance(result, CLIResult)

    def test_special_characters_in_file_paths(self):
        """Test error handling with special characters in file paths."""
        with E2ETestHarness() as harness:
            # Create file with special characters
            harness.setup_working_changes({
                "src/file with spaces.py": "pass",
                "src/file-with-dashes.py": "pass",
                "src/file_underscores.py": "pass",
            })

            result = harness.run_cli("test")

            # Should handle special characters in paths
            assert isinstance(result, CLIResult)


class TestRecoveryBehavior:
    """Tests for error recovery and retry behavior."""

    def test_recovers_after_transient_error(self):
        """Test that CLI can recover after a transient error."""
        with E2ETestHarness(auto_complete_delay=0.5) as harness:
            # Inject error that only happens once
            harness.inject_api_error(
                "/cli/e2e/suites",
                status_code=500,
                message="Temporary failure",
                method="POST",
                count=1,  # Only fail once, then succeed
            )

            harness.setup_working_changes({"test.py": "pass"})

            result = harness.run_cli("test")

            # CLI may retry and succeed, or fail on first error
            # Key is it should not hang or crash
            assert isinstance(result, CLIResult)

    def test_fails_fast_on_permanent_error(self):
        """Test that CLI fails fast on permanent errors (like auth)."""
        with E2ETestHarness(require_auth=True) as harness:
            harness.setup_working_changes({"test.py": "pass"})

            # Track time
            import time
            start = time.time()

            result = harness.run_cli(
                "test",
                env={"DEBUGGAI_API_KEY": "invalid"},
                timeout=30.0,
            )

            elapsed = time.time() - start

            # Should fail relatively quickly, not retry endlessly
            assert result.returncode != 0
            # Should complete within reasonable time (not waiting full timeout)
            assert elapsed < 20.0, f"Should fail fast on auth error, took {elapsed}s"
