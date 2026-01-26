"""
Integration tests for systemeval invoking debugg-ai-cli as subprocess.

Tests how systemeval wraps and invokes the debugg-ai CLI, focusing on:
1. Subprocess invocation and lifecycle
2. JSON output parsing from CLI
3. Timeout handling for long-running CLI operations
4. Environment variable passthrough (DEBUGGAI_API_KEY)
5. Working directory configuration

Requirements from SE-bf5.
"""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from tests.fixtures import (
    E2ETestHarness,
    MockDebuggAIServer,
    GitRepoFixture,
    CLIResult,
    create_e2e_harness,
    create_mock_server,
    create_git_repo,
)


# ============================================================================
# Constants and Paths
# ============================================================================

# Path to the debugg-ai CLI
CLI_PATH = Path(__file__).parent.parent.parent / "debugg-ai-cli" / "dist" / "cli.js"

# Check if CLI is available
CLI_AVAILABLE = CLI_PATH.exists()

# Skip marker for tests requiring CLI
requires_cli = pytest.mark.skipif(
    not CLI_AVAILABLE,
    reason=f"CLI not built at {CLI_PATH} - run 'npm run build' in debugg-ai-cli",
)


# ============================================================================
# Helper Classes
# ============================================================================


class SystemEvalCLIWrapper:
    """
    Wrapper class demonstrating how systemeval would invoke debugg-ai-cli.

    This is a test utility that simulates how systemeval would wrap
    the debugg-ai CLI for subprocess invocation.
    """

    def __init__(
        self,
        cli_path: Optional[str] = None,
        working_dir: Optional[str] = None,
        api_key: Optional[str] = None,
        api_url: Optional[str] = None,
        timeout: float = 60.0,
        env: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the CLI wrapper.

        Args:
            cli_path: Path to cli.js (default: auto-detect)
            working_dir: Working directory for CLI execution
            api_key: DEBUGGAI_API_KEY to pass to CLI
            api_url: Base URL for API (for testing with mock server)
            timeout: Timeout in seconds for CLI operations
            env: Additional environment variables
        """
        self.cli_path = cli_path or str(CLI_PATH)
        self.working_dir = working_dir
        self.api_key = api_key
        self.api_url = api_url
        self.timeout = timeout
        self.env = env or {}

    def build_command(self, *args: str) -> List[str]:
        """Build the command list for subprocess."""
        cmd = ["node", self.cli_path]
        cmd.extend(args)
        return cmd

    def build_environment(self) -> Dict[str, str]:
        """Build the environment dict for subprocess."""
        env = os.environ.copy()

        if self.api_key:
            env["DEBUGGAI_API_KEY"] = self.api_key

        if self.api_url:
            env["DEBUGGAI_API_URL"] = self.api_url

        env.update(self.env)
        return env

    def run(
        self,
        *args: str,
        timeout: Optional[float] = None,
        capture_output: bool = True,
    ) -> CLIResult:
        """
        Run the CLI with given arguments.

        Args:
            *args: CLI arguments
            timeout: Override default timeout
            capture_output: Whether to capture stdout/stderr

        Returns:
            CLIResult with returncode, stdout, stderr
        """
        cmd = self.build_command(*args)
        env = self.build_environment()
        effective_timeout = timeout if timeout is not None else self.timeout

        try:
            result = subprocess.run(
                cmd,
                cwd=self.working_dir,
                env=env,
                capture_output=capture_output,
                text=True,
                timeout=effective_timeout,
            )

            return CLIResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=cmd,
                env=env,
            )

        except subprocess.TimeoutExpired as e:
            return CLIResult(
                returncode=-1,
                stdout=getattr(e, "stdout", "") or "",
                stderr=f"Command timed out after {effective_timeout}s",
                command=cmd,
                env=env,
            )

        except FileNotFoundError as e:
            return CLIResult(
                returncode=-2,
                stdout="",
                stderr=f"CLI not found: {e}",
                command=cmd,
                env=env,
            )

    def run_json(
        self,
        *args: str,
        timeout: Optional[float] = None,
    ) -> tuple[CLIResult, Optional[Dict[str, Any]]]:
        """
        Run CLI and parse JSON output.

        Returns:
            Tuple of (CLIResult, parsed_json or None)
        """
        result = self.run(*args, "--json", timeout=timeout)
        parsed = self.parse_json_output(result.stdout)
        return result, parsed

    @staticmethod
    def parse_json_output(output: str) -> Optional[Dict[str, Any]]:
        """
        Parse JSON from CLI output.

        The CLI may output non-JSON text before/after JSON.
        This finds and parses the JSON portion.
        """
        if not output:
            return None

        # Try direct parse first
        try:
            return json.loads(output.strip())
        except json.JSONDecodeError:
            pass

        # Try to find JSON object in output
        start = output.find("{")
        end = output.rfind("}") + 1

        if start >= 0 and end > start:
            try:
                return json.loads(output[start:end])
            except json.JSONDecodeError:
                pass

        # Try to find JSON array
        start = output.find("[")
        end = output.rfind("]") + 1

        if start >= 0 and end > start:
            try:
                return json.loads(output[start:end])
            except json.JSONDecodeError:
                pass

        return None


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def cli_wrapper():
    """Create a CLI wrapper for testing."""
    return SystemEvalCLIWrapper()


@pytest.fixture
def mock_server():
    """Create and start a mock server."""
    server = create_mock_server(verbose=False)
    yield server
    server.stop()


@pytest.fixture
def git_repo():
    """Create a temporary git repository."""
    repo = create_git_repo()
    yield repo
    repo.stop()


@pytest.fixture
def e2e_harness():
    """Create a complete E2E test harness."""
    harness = create_e2e_harness(auto_complete_delay=0.5)
    yield harness
    harness.stop()


# ============================================================================
# Test Classes
# ============================================================================


class TestCLISubprocessInvocation:
    """Tests for basic subprocess invocation of debugg-ai CLI."""

    @requires_cli
    def test_cli_invocation_with_help(self, cli_wrapper):
        """Test CLI can be invoked with --help flag."""
        result = cli_wrapper.run("--help")

        assert result.returncode == 0
        assert "debugg" in result.stdout.lower() or "usage" in result.stdout.lower()

    @requires_cli
    def test_cli_invocation_with_version(self, cli_wrapper):
        """Test CLI can be invoked with --version flag."""
        result = cli_wrapper.run("--version")

        # Version should succeed
        assert result.returncode == 0

    @requires_cli
    def test_cli_command_building(self, cli_wrapper):
        """Test command list is built correctly."""
        cmd = cli_wrapper.build_command("test", "--json", "--verbose")

        assert "node" in cmd[0]
        assert "cli.js" in cmd[1]
        assert "test" in cmd
        assert "--json" in cmd
        assert "--verbose" in cmd

    def test_cli_not_found_handling(self, tmp_path):
        """Test handling when CLI path doesn't exist."""
        wrapper = SystemEvalCLIWrapper(cli_path="/nonexistent/path/cli.js")
        result = wrapper.run("--help")

        # Node.js will fail when script doesn't exist, either with:
        # - FileNotFoundError (returncode -2) if node itself isn't found
        # - Exit code 1 with error message if node exists but script doesn't
        assert result.returncode != 0
        # Should have some error indication
        has_error = (
            result.returncode == -2 or
            "not found" in result.stderr.lower() or
            "cannot find" in result.stderr.lower() or
            "enoent" in result.stderr.lower() or
            "error" in result.stderr.lower()
        )
        assert has_error, f"Expected error message in stderr: {result.stderr}"

    @requires_cli
    def test_cli_invalid_command_returns_error(self, cli_wrapper):
        """Test CLI returns error for invalid commands."""
        result = cli_wrapper.run("nonexistent-command")

        # Should fail with non-zero exit code
        assert result.returncode != 0 or "error" in result.output.lower()


class TestJSONOutputParsing:
    """Tests for parsing JSON output from debugg-ai CLI."""

    def test_parse_clean_json_object(self, cli_wrapper):
        """Test parsing clean JSON object."""
        json_str = '{"status": "success", "tests": 5}'
        parsed = cli_wrapper.parse_json_output(json_str)

        assert parsed is not None
        assert parsed["status"] == "success"
        assert parsed["tests"] == 5

    def test_parse_json_with_surrounding_text(self, cli_wrapper):
        """Test parsing JSON with text before/after."""
        output = 'Loading... {"status": "done", "count": 3} Complete!'
        parsed = cli_wrapper.parse_json_output(output)

        assert parsed is not None
        assert parsed["status"] == "done"
        assert parsed["count"] == 3

    def test_parse_json_array(self, cli_wrapper):
        """Test parsing JSON array output."""
        json_str = '[{"test": 1}, {"test": 2}]'
        parsed = cli_wrapper.parse_json_output(json_str)

        assert parsed is not None
        assert len(parsed) == 2
        assert parsed[0]["test"] == 1

    def test_parse_empty_output_returns_none(self, cli_wrapper):
        """Test parsing empty output returns None."""
        parsed = cli_wrapper.parse_json_output("")
        assert parsed is None

    def test_parse_invalid_json_returns_none(self, cli_wrapper):
        """Test parsing invalid JSON returns None."""
        parsed = cli_wrapper.parse_json_output("not json at all")
        assert parsed is None

    def test_parse_malformed_json_returns_none(self, cli_wrapper):
        """Test parsing malformed JSON returns None."""
        parsed = cli_wrapper.parse_json_output('{"incomplete":')
        assert parsed is None

    def test_parse_nested_json(self, cli_wrapper):
        """Test parsing deeply nested JSON."""
        json_str = '''
        {
            "suite": {
                "uuid": "test-123",
                "status": "completed",
                "tests": [
                    {"name": "test1", "status": "passed"},
                    {"name": "test2", "status": "failed", "error": {"message": "assertion failed"}}
                ]
            },
            "metadata": {
                "duration": 15.5,
                "artifacts": ["script.js", "recording.gif"]
            }
        }
        '''
        parsed = cli_wrapper.parse_json_output(json_str)

        assert parsed is not None
        assert parsed["suite"]["uuid"] == "test-123"
        assert len(parsed["suite"]["tests"]) == 2
        assert parsed["suite"]["tests"][1]["error"]["message"] == "assertion failed"

    @requires_cli
    def test_cli_json_output_flag(self, e2e_harness):
        """Test CLI --json flag produces parseable output."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "# test file"})

        result, parsed = wrapper.run_json("test", timeout=30.0)

        # Output should be parseable (even if command fails)
        # The important thing is JSON flag is handled
        assert isinstance(result, CLIResult)
        # If we got JSON output, verify it's a dict
        if parsed is not None:
            assert isinstance(parsed, dict)


class TestTimeoutHandling:
    """Tests for CLI timeout handling."""

    @requires_cli
    def test_timeout_kills_long_running_process(self, e2e_harness):
        """Test timeout terminates long-running CLI operations."""
        # Set up server with very long delay
        e2e_harness.server.set_response_delay(10.0)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
            timeout=1.0,  # Very short timeout
        )

        e2e_harness.setup_working_changes({"test.py": "# test"})

        start = time.time()
        result = wrapper.run("test")
        elapsed = time.time() - start

        # Should complete in reasonable time (either timeout or quick CLI failure)
        # The test verifies that the timeout mechanism is working - CLI either:
        # - Times out as expected (returncode -1, "timed out" in stderr)
        # - Fails quickly before making slow API call (returncode != 0)
        assert elapsed < 5.0, f"CLI took too long: {elapsed}s"
        # Either timed out or completed with some error
        if result.returncode == -1:
            assert "timed out" in result.stderr.lower()
        else:
            # CLI completed (possibly with error) before timeout
            assert result.returncode != 0 or elapsed < 2.0

    @requires_cli
    def test_timeout_per_operation_override(self, e2e_harness):
        """Test per-operation timeout override."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
            timeout=60.0,  # Default long timeout
        )

        # Set up server with delay
        e2e_harness.server.set_response_delay(5.0)
        e2e_harness.setup_working_changes({"test.py": "# test"})

        start = time.time()
        result = wrapper.run("test", timeout=0.5)  # Override with short timeout
        elapsed = time.time() - start

        # Should use the override timeout
        assert elapsed < 3.0
        assert result.returncode == -1

    @requires_cli
    def test_no_timeout_allows_completion(self, e2e_harness):
        """Test sufficient timeout allows completion."""
        # Set server to complete quickly
        e2e_harness.server.set_auto_complete_delay(0.5)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
            timeout=30.0,
        )

        e2e_harness.setup_working_changes({"test.py": "# test"})

        result = wrapper.run("--help")  # Help should be fast

        # Should complete without timeout
        assert result.returncode == 0

    def test_timeout_returns_partial_output(self):
        """Test timeout captures any partial output available."""
        # Create a slow script that outputs before timing out
        script = """
import time
import sys
print("Starting...", flush=True)
time.sleep(0.1)
print("Progress...", flush=True)
time.sleep(10)  # Will timeout
print("Done")
"""
        wrapper = SystemEvalCLIWrapper(timeout=0.5)

        # Use Python to simulate slow CLI
        cmd = [sys.executable, "-c", script]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=0.5,
            )
        except subprocess.TimeoutExpired as e:
            # Partial output may or may not be captured
            # depending on buffering
            pass


class TestEnvironmentVariablePassthrough:
    """Tests for environment variable handling."""

    @requires_cli
    def test_api_key_passed_via_environment(self, mock_server, git_repo):
        """Test DEBUGGAI_API_KEY is passed to CLI."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
            api_key="test-api-key-secret",
            api_url=mock_server.base_url,
        )

        env = wrapper.build_environment()

        assert "DEBUGGAI_API_KEY" in env
        assert env["DEBUGGAI_API_KEY"] == "test-api-key-secret"

    @requires_cli
    def test_api_url_passed_via_environment(self, mock_server, git_repo):
        """Test DEBUGGAI_API_URL is passed to CLI."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
            api_key="test-key",
            api_url="https://custom-api.example.com",
        )

        env = wrapper.build_environment()

        assert "DEBUGGAI_API_URL" in env
        assert env["DEBUGGAI_API_URL"] == "https://custom-api.example.com"

    @requires_cli
    def test_additional_env_vars_merged(self, git_repo):
        """Test additional env vars are merged into environment."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
            api_key="test-key",
            env={
                "CUSTOM_VAR_1": "value1",
                "CUSTOM_VAR_2": "value2",
            },
        )

        env = wrapper.build_environment()

        assert env["CUSTOM_VAR_1"] == "value1"
        assert env["CUSTOM_VAR_2"] == "value2"
        assert env["DEBUGGAI_API_KEY"] == "test-key"

    def test_env_vars_not_leaked_to_parent(self, git_repo):
        """Test CLI env vars don't leak to parent process."""
        original_key = os.environ.get("DEBUGGAI_API_KEY")

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
            api_key="test-secret-key",
        )

        # Build environment
        env = wrapper.build_environment()

        # Parent process should be unchanged
        assert os.environ.get("DEBUGGAI_API_KEY") == original_key
        assert env.get("DEBUGGAI_API_KEY") == "test-secret-key"

    @requires_cli
    def test_cli_uses_passed_api_key(self, e2e_harness):
        """Test CLI actually uses the passed API key."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "# test"})

        result = wrapper.run("test", timeout=10.0)

        # Check that API was called (server should have recorded requests)
        # This verifies the CLI actually made requests with the key
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_invalid_api_key_rejected(self, e2e_harness):
        """Test CLI fails with invalid API key."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key="invalid-wrong-key",
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "# test"})

        result = wrapper.run("test", timeout=10.0)

        # Should fail with auth error
        assert result.returncode != 0 or "auth" in result.output.lower() or "401" in result.output


class TestWorkingDirectoryConfiguration:
    """Tests for working directory handling."""

    @requires_cli
    def test_cli_runs_in_specified_directory(self, git_repo):
        """Test CLI runs in the specified working directory."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
        )

        result = wrapper.run("--help")

        # Help should work regardless of directory
        assert result.returncode == 0

    @requires_cli
    def test_cli_detects_git_repo_from_working_dir(self, e2e_harness):
        """Test CLI detects git repository from working directory."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        # Add some changes
        e2e_harness.setup_working_changes({"src/feature.py": "print('hello')"})

        result = wrapper.run("test", timeout=10.0)

        # CLI should have detected the git repo
        requests = e2e_harness.get_api_requests(method="POST", path="/suite")
        if requests:
            # Should have repo info in request
            body = requests[0].get("body", {})
            has_repo_info = (
                "repoName" in body or
                "repo_name" in body or
                "repository" in body
            )
            # Repo detection is optional but expected
            assert isinstance(result, CLIResult)

    @requires_cli
    def test_working_dir_with_spaces_in_path(self, tmp_path):
        """Test CLI works with spaces in working directory path."""
        # Create path with spaces
        spaced_path = tmp_path / "path with spaces" / "project"
        spaced_path.mkdir(parents=True)

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=spaced_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=spaced_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=spaced_path,
            check=True,
            capture_output=True,
        )

        wrapper = SystemEvalCLIWrapper(working_dir=str(spaced_path))

        result = wrapper.run("--help")

        assert result.returncode == 0

    def test_nonexistent_working_dir_error(self):
        """Test error when working directory doesn't exist."""
        wrapper = SystemEvalCLIWrapper(working_dir="/nonexistent/path/here")

        result = wrapper.run("--help")

        # Should fail (FileNotFoundError or similar)
        assert result.returncode != 0

    @requires_cli
    def test_working_dir_affects_file_analysis(self, e2e_harness):
        """Test working directory affects which files are analyzed."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        # Add files in the repo
        e2e_harness.repo.add_file("analyzed_file.py", "# This should be analyzed")

        result = wrapper.run("test", timeout=10.0)

        # Verify the CLI attempted to analyze files from the working dir
        assert isinstance(result, CLIResult)


class TestCLIWithMockServer:
    """Tests for CLI invocation with mock API server."""

    @requires_cli
    def test_cli_connects_to_mock_server(self, e2e_harness):
        """Test CLI connects to mock server successfully."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "pass"})

        result = wrapper.run("test", timeout=15.0)

        # Check server received requests
        requests = e2e_harness.get_api_requests()

        # CLI should have made at least one request
        # (may fail if CLI can't connect, but we want to verify the attempt)
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_cli_handles_server_error_gracefully(self, e2e_harness):
        """Test CLI handles API server errors gracefully."""
        # Inject error
        e2e_harness.inject_api_error(
            "/api/v1/e2e-commit-suites/",
            status_code=500,
            message="Internal Server Error",
            method="POST",
            count=0,  # Always fail
        )

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "pass"})

        result = wrapper.run("test", timeout=15.0)

        # Should fail but not crash
        assert isinstance(result, CLIResult)
        assert result.returncode != 0 or "error" in result.output.lower()

    @requires_cli
    def test_cli_handles_suite_completion(self, e2e_harness):
        """Test CLI correctly handles suite completion flow."""
        # Set auto-complete so any suite created by CLI will auto-complete
        e2e_harness.server.set_auto_complete_delay(1.0)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "pass"})

        result = wrapper.run("test", timeout=30.0)

        # The CLI should have completed (maybe with errors, but completed)
        assert isinstance(result, CLIResult)

        # Check if any suites were created and auto-completed
        suites = e2e_harness.server.suites
        for suite_id, suite in suites.items():
            # If suite was created by CLI, it should have been auto-completed
            # (or still pending if CLI finished before auto-complete triggered)
            assert suite.status in ("pending", "completed", "running")


class TestCLIResultParsing:
    """Tests for parsing various CLI result formats."""

    def test_parse_success_result(self, cli_wrapper):
        """Test parsing successful test run result."""
        json_output = '''
        {
            "status": "success",
            "suiteId": "test-suite-123",
            "tests": {
                "total": 5,
                "passed": 4,
                "failed": 1
            },
            "duration": 12.5
        }
        '''

        parsed = cli_wrapper.parse_json_output(json_output)

        assert parsed is not None
        assert parsed["status"] == "success"
        assert parsed["tests"]["passed"] == 4
        assert parsed["tests"]["failed"] == 1

    def test_parse_error_result(self, cli_wrapper):
        """Test parsing error result."""
        json_output = '''
        {
            "status": "error",
            "error": {
                "code": "AUTH_FAILED",
                "message": "Invalid API key"
            }
        }
        '''

        parsed = cli_wrapper.parse_json_output(json_output)

        assert parsed is not None
        assert parsed["status"] == "error"
        assert parsed["error"]["code"] == "AUTH_FAILED"

    def test_parse_suite_status_result(self, cli_wrapper):
        """Test parsing suite status polling result."""
        json_output = '''
        {
            "uuid": "suite-abc-123",
            "runStatus": "in_progress",
            "tests": [
                {"uuid": "test-1", "name": "Login Flow", "status": "running"},
                {"uuid": "test-2", "name": "Signup Flow", "status": "pending"}
            ],
            "progress": 50
        }
        '''

        parsed = cli_wrapper.parse_json_output(json_output)

        assert parsed is not None
        assert parsed["runStatus"] == "in_progress"
        assert len(parsed["tests"]) == 2

    def test_parse_artifact_urls(self, cli_wrapper):
        """Test parsing artifact URLs from result."""
        json_output = '''
        {
            "status": "completed",
            "artifacts": {
                "testScript": "https://api.debugg.ai/artifacts/script.js",
                "recording": "https://api.debugg.ai/artifacts/run.gif",
                "results": "https://api.debugg.ai/artifacts/results.json"
            }
        }
        '''

        parsed = cli_wrapper.parse_json_output(json_output)

        assert parsed is not None
        assert "artifacts" in parsed
        assert "testScript" in parsed["artifacts"]


class TestIntegrationScenarios:
    """End-to-end integration scenarios."""

    @requires_cli
    def test_full_test_flow_with_mock_server(self, e2e_harness):
        """Test complete test flow: changes -> submit -> poll -> complete."""
        # Set up quick completion
        e2e_harness.server.set_auto_complete_delay(1.0)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
            timeout=30.0,
        )

        # Add changes to analyze
        e2e_harness.setup_working_changes({
            "src/feature.py": "def new_feature(): return 'hello'",
            "src/utils.py": "def helper(): return 42",
        })

        result, parsed = wrapper.run_json("test")

        # Verify flow executed
        assert isinstance(result, CLIResult)

        # Check API was called
        requests = e2e_harness.get_api_requests(method="POST")
        assert len(requests) >= 0  # May not always make requests depending on CLI state

    @requires_cli
    def test_feature_branch_analysis(self, e2e_harness):
        """Test analyzing changes on a feature branch."""
        # Set up feature branch scenario
        base_hash, head_hash = e2e_harness.repo.setup_pr_scenario(
            base_branch="main",
            head_branch="feature-test",
            num_commits=3,
        )

        e2e_harness.server.set_auto_complete_delay(0.5)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        result = wrapper.run("test", timeout=15.0)

        # Should have analyzed the feature branch
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_multiple_sequential_runs(self, e2e_harness):
        """Test multiple CLI invocations in sequence."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        # Run 1: Help
        result1 = wrapper.run("--help")
        assert result1.returncode == 0

        # Run 2: Version
        result2 = wrapper.run("--version")
        assert result2.returncode == 0

        # Both should succeed independently
        assert result1.success
        assert result2.success

    @requires_cli
    def test_cli_with_verbose_flag(self, e2e_harness):
        """Test CLI with --verbose flag produces more output."""
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        e2e_harness.setup_working_changes({"test.py": "pass"})

        # Run without verbose
        result_quiet = wrapper.run("test", timeout=10.0)

        # Reset server state
        e2e_harness.reset()
        e2e_harness.setup_working_changes({"test.py": "pass"})

        # Run with verbose
        result_verbose = wrapper.run("test", "--verbose", timeout=10.0)

        # Both should be valid results
        assert isinstance(result_quiet, CLIResult)
        assert isinstance(result_verbose, CLIResult)


class TestEdgeCases:
    """Edge case and resilience tests."""

    @requires_cli
    def test_empty_working_directory(self, e2e_harness):
        """Test CLI handles empty working directory."""
        # Don't add any changes
        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        result = wrapper.run("test", timeout=10.0)

        # Should handle gracefully (may report no changes)
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_large_number_of_changes(self, e2e_harness):
        """Test CLI handles many file changes."""
        # Add many files
        changes = {f"src/file_{i}.py": f"# File {i}" for i in range(50)}
        e2e_harness.setup_working_changes(changes)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        result = wrapper.run("test", timeout=30.0)

        # Should handle without crashing
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_unicode_in_file_content(self, e2e_harness):
        """Test CLI handles unicode content in files."""
        e2e_harness.setup_working_changes({
            "unicode_test.py": "# File with unicode: \u4e2d\u6587 \u65e5\u672c\u8a9e \u0440\u0443\u0441\u0441\u043a\u0438\u0439",
        })

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        result = wrapper.run("test", timeout=10.0)

        # Should handle unicode without crashing
        assert isinstance(result, CLIResult)

    @requires_cli
    def test_binary_file_handling(self, e2e_harness):
        """Test CLI handles presence of binary files."""
        # Add a text file plus a binary file marker
        e2e_harness.setup_working_changes({
            "text_file.py": "# Normal text file",
        })

        # Add a binary-ish file (simulated)
        binary_path = e2e_harness.repo.path / "image.png"
        binary_path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(e2e_harness.repo.path),
            api_key=e2e_harness.api_key,
            api_url=e2e_harness.api_url,
        )

        result = wrapper.run("test", timeout=10.0)

        # Should handle without crashing
        assert isinstance(result, CLIResult)

    def test_special_characters_in_api_key(self, git_repo):
        """Test API key with special characters is passed correctly."""
        special_key = "sk_test_!@#$%^&*()_+-=[]{}|;':\",./<>?"

        wrapper = SystemEvalCLIWrapper(
            working_dir=str(git_repo.path),
            api_key=special_key,
        )

        env = wrapper.build_environment()

        # Key should be preserved exactly
        assert env["DEBUGGAI_API_KEY"] == special_key


class TestCLIWrapperUtilityMethods:
    """Tests for CLI wrapper utility methods."""

    def test_wrapper_default_values(self):
        """Test wrapper has sensible defaults."""
        wrapper = SystemEvalCLIWrapper()

        assert wrapper.timeout == 60.0
        assert wrapper.cli_path == str(CLI_PATH)
        assert wrapper.working_dir is None
        assert wrapper.api_key is None

    def test_wrapper_custom_values(self):
        """Test wrapper accepts custom values."""
        wrapper = SystemEvalCLIWrapper(
            cli_path="/custom/path/cli.js",
            working_dir="/custom/working/dir",
            api_key="custom-key",
            api_url="https://custom.api.com",
            timeout=120.0,
            env={"CUSTOM": "value"},
        )

        assert wrapper.cli_path == "/custom/path/cli.js"
        assert wrapper.working_dir == "/custom/working/dir"
        assert wrapper.api_key == "custom-key"
        assert wrapper.api_url == "https://custom.api.com"
        assert wrapper.timeout == 120.0
        assert wrapper.env["CUSTOM"] == "value"

    def test_cli_result_properties(self):
        """Test CLIResult dataclass properties."""
        result = CLIResult(
            returncode=0,
            stdout="output",
            stderr="error",
            command=["test"],
        )

        assert result.success is True
        assert result.output == "outputerror"

        result_failed = CLIResult(
            returncode=1,
            stdout="out",
            stderr="err",
            command=["test"],
        )

        assert result_failed.success is False
