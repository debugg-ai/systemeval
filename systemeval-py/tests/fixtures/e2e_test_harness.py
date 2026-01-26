"""
E2ETestHarness - Complete integration test environment for debugg-ai CLI testing.

Provides a unified test harness that manages:
- MockDebuggAIServer for API simulation
- GitRepoFixture for temporary git repositories
- Environment variable management
- CLI invocation helpers
- Cleanup on test failure

Usage:
    from tests.fixtures.e2e_test_harness import E2ETestHarness

    # Basic usage with context manager
    with E2ETestHarness() as harness:
        # Set up git repo with changes
        harness.repo.add_file("src/app.py", "print('hello')")
        harness.repo.commit("Add feature")

        # Run CLI command
        result = harness.run_cli("test")

        # Check results
        assert result.returncode == 0

    # Or with pytest fixture
    def test_cli_flow(e2e_harness):
        e2e_harness.repo.add_file("test.py", "pass")
        result = e2e_harness.run_cli("test")
        assert result.returncode == 0
"""

import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .mock_debuggai_server import MockDebuggAIServer, MockTestSuite
from .git_repo_fixture import GitRepoFixture, CommitInfo


@dataclass
class CLIResult:
    """Result of a CLI invocation."""

    returncode: int
    stdout: str
    stderr: str
    command: List[str]
    env: Dict[str, str] = field(default_factory=dict)

    @property
    def success(self) -> bool:
        """Check if the command succeeded (exit code 0)."""
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Get combined stdout and stderr."""
        return self.stdout + self.stderr

    def __repr__(self) -> str:
        return f"CLIResult(returncode={self.returncode}, stdout_len={len(self.stdout)}, stderr_len={len(self.stderr)})"


class E2ETestHarness:
    """
    Complete E2E testing environment for debugg-ai CLI.

    Features:
    - Manages MockDebuggAIServer lifecycle
    - Manages GitRepoFixture lifecycle
    - Sets up proper environment variables
    - Provides CLI invocation helpers
    - Automatic cleanup on exit/error

    Example:
        with E2ETestHarness() as harness:
            harness.repo.add_file("src/app.py", "code")
            harness.repo.commit("Add feature")

            result = harness.run_cli("test", "--wait-for-server")
            assert result.success
    """

    def __init__(
        self,
        # Server options
        server_port: int = 0,
        valid_api_key: str = "test-api-key-12345",
        require_auth: bool = True,
        auto_complete_delay: Optional[float] = None,
        response_delay: float = 0.0,

        # Git repo options
        initial_branch: str = "main",
        author_name: str = "Test User",
        author_email: str = "test@example.com",

        # CLI options
        cli_path: Optional[str] = None,
        cli_timeout: float = 60.0,

        # Debug options
        verbose: bool = False,
        keep_on_error: bool = False,
    ):
        """
        Initialize the E2E test harness.

        Args:
            server_port: Port for mock server (0 = auto-assign)
            valid_api_key: API key the mock server accepts
            require_auth: Whether to require API key authentication
            auto_complete_delay: Delay before suites auto-complete (None = no auto-complete)
            response_delay: Artificial delay on all responses

            initial_branch: Initial branch name for git repo
            author_name: Git author name for commits
            author_email: Git author email for commits

            cli_path: Path to the CLI executable (None = auto-detect)
            cli_timeout: Timeout for CLI commands in seconds

            verbose: Enable verbose logging
            keep_on_error: Don't clean up on error (for debugging)
        """
        # Server config
        self._server_port = server_port
        self._valid_api_key = valid_api_key
        self._require_auth = require_auth
        self._auto_complete_delay = auto_complete_delay
        self._response_delay = response_delay

        # Git config
        self._initial_branch = initial_branch
        self._author_name = author_name
        self._author_email = author_email

        # CLI config
        self._cli_path = cli_path
        self._cli_timeout = cli_timeout

        # Debug config
        self._verbose = verbose
        self._keep_on_error = keep_on_error

        # State
        self._server: Optional[MockDebuggAIServer] = None
        self._repo: Optional[GitRepoFixture] = None
        self._original_env: Dict[str, Optional[str]] = {}
        self._initialized: bool = False

    @property
    def server(self) -> MockDebuggAIServer:
        """Get the mock server instance."""
        if self._server is None:
            raise RuntimeError("Harness not initialized. Use start() or context manager.")
        return self._server

    @property
    def repo(self) -> GitRepoFixture:
        """Get the git repo fixture instance."""
        if self._repo is None:
            raise RuntimeError("Harness not initialized. Use start() or context manager.")
        return self._repo

    @property
    def api_key(self) -> str:
        """Get the valid API key for the mock server."""
        return self._valid_api_key

    @property
    def api_url(self) -> str:
        """Get the mock server's base URL."""
        return self.server.base_url

    def start(self) -> "E2ETestHarness":
        """Initialize the test environment."""
        if self._initialized:
            return self

        try:
            # Start mock server
            self._server = MockDebuggAIServer(
                port=self._server_port,
                verbose=self._verbose,
                valid_api_key=self._valid_api_key,
                require_valid_api_key=self._require_auth,
            )
            self._server.start()

            if self._auto_complete_delay is not None:
                self._server.set_auto_complete_delay(self._auto_complete_delay)

            if self._response_delay > 0:
                self._server.set_response_delay(self._response_delay)

            # Start git repo
            self._repo = GitRepoFixture(
                initial_branch=self._initial_branch,
                author_name=self._author_name,
                author_email=self._author_email,
                keep_on_error=self._keep_on_error,
            )
            self._repo.start()

            # Set up environment variables
            self._setup_environment()

            self._initialized = True
            return self

        except Exception:
            # Clean up on failure
            self._cleanup()
            raise

    def stop(self, error: bool = False) -> None:
        """Clean up the test environment."""
        # Restore environment first
        self._restore_environment()

        # Stop server
        if self._server is not None:
            self._server.stop()
            self._server = None

        # Stop repo
        if self._repo is not None:
            self._repo.stop(error=error)
            self._repo = None

        self._initialized = False

    def _cleanup(self) -> None:
        """Internal cleanup helper."""
        try:
            self._restore_environment()
        except Exception:
            pass

        if self._server is not None:
            try:
                self._server.stop()
            except Exception:
                pass
            self._server = None

        if self._repo is not None:
            try:
                self._repo.stop()
            except Exception:
                pass
            self._repo = None

    def _setup_environment(self) -> None:
        """Set up environment variables for CLI."""
        env_vars = {
            "DEBUGGAI_API_KEY": self._valid_api_key,
            "DEBUGGAI_API_URL": self.server.base_url,
            # Disable any real API calls
            "DEBUGGAI_MOCK_MODE": "1",
        }

        for key, value in env_vars.items():
            self._original_env[key] = os.environ.get(key)
            os.environ[key] = value

    def _restore_environment(self) -> None:
        """Restore original environment variables."""
        for key, value in self._original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self._original_env.clear()

    # ========================================================================
    # CLI Invocation
    # ========================================================================

    def run_cli(
        self,
        *args: str,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
        include_base_url: bool = True,
    ) -> CLIResult:
        """
        Run the debugg-ai CLI with the given arguments.

        Args:
            *args: CLI arguments (e.g., "test", "--wait-for-server")
            timeout: Command timeout in seconds (default: self._cli_timeout)
            env: Additional environment variables
            cwd: Working directory (default: git repo path)
            include_base_url: Whether to automatically add --base-url flag

        Returns:
            CLIResult with returncode, stdout, stderr
        """
        cli_cmd = self._get_cli_command()

        # Convert args to list for manipulation
        args_list = list(args)

        # Inject --base-url if running test command and not already provided
        if include_base_url and args_list and args_list[0] == "test":
            if "--base-url" not in args_list:
                args_list.extend(["--base-url", self.api_url])

        cmd = cli_cmd + args_list

        # Build environment
        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        # Default to repo path
        if cwd is None:
            cwd = str(self.repo.path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._cli_timeout,
                cwd=cwd,
                env=run_env,
            )

            return CLIResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=cmd,
                env=run_env,
            )

        except subprocess.TimeoutExpired as e:
            return CLIResult(
                returncode=-1,
                stdout=e.stdout or "" if hasattr(e, "stdout") else "",
                stderr=f"Command timed out after {timeout or self._cli_timeout}s",
                command=cmd,
                env=run_env,
            )

    def run_cli_with_node(
        self,
        *args: str,
        timeout: Optional[float] = None,
        env: Optional[Dict[str, str]] = None,
        cwd: Optional[str] = None,
    ) -> CLIResult:
        """
        Run the debugg-ai TypeScript CLI via node.

        This is useful when testing the TypeScript CLI directly.
        """
        cli_path = self._get_ts_cli_path()
        cmd = ["node", cli_path] + list(args)

        run_env = os.environ.copy()
        if env:
            run_env.update(env)

        if cwd is None:
            cwd = str(self.repo.path)

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout or self._cli_timeout,
                cwd=cwd,
                env=run_env,
            )

            return CLIResult(
                returncode=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                command=cmd,
                env=run_env,
            )

        except subprocess.TimeoutExpired as e:
            return CLIResult(
                returncode=-1,
                stdout=e.stdout or "" if hasattr(e, "stdout") else "",
                stderr=f"Command timed out after {timeout or self._cli_timeout}s",
                command=cmd,
                env=run_env,
            )

    def _get_cli_command(self) -> List[str]:
        """Get the command to run the CLI as a list of arguments."""
        if self._cli_path:
            # If user provided a path, use it (might be "node /path/to/cli.js" or just "/path/to/cli")
            return self._cli_path.split()

        # Try to find the CLI in common locations
        local_cli = Path(__file__).parent.parent.parent / "debugg-ai-cli" / "dist" / "cli.js"
        if local_cli.exists():
            return ["node", str(local_cli)]

        # Try npm global install
        try:
            subprocess.run(
                ["which", "debugg-ai"],
                capture_output=True,
                check=True,
            )
            return ["debugg-ai"]
        except subprocess.CalledProcessError:
            pass

        # Default to node with local path (may not exist)
        return ["node", str(local_cli)]

    def _get_ts_cli_path(self) -> str:
        """Get path to the TypeScript CLI dist file."""
        return str(Path(__file__).parent.parent.parent / "debugg-ai-cli" / "dist" / "cli.js")

    # ========================================================================
    # Test Helpers
    # ========================================================================

    def setup_working_changes(
        self,
        files: Dict[str, str],
        commit: bool = False,
        commit_message: str = "Add files",
    ) -> None:
        """
        Set up working directory with file changes.

        Args:
            files: Dict of path -> content
            commit: Whether to commit the files
            commit_message: Commit message if committing
        """
        for path, content in files.items():
            self.repo.add_file(path, content)

        if commit:
            self.repo.commit(commit_message)

    def setup_feature_branch(
        self,
        branch_name: str = "feature",
        files: Optional[Dict[str, str]] = None,
        num_commits: int = 1,
    ) -> CommitInfo:
        """
        Set up a feature branch with changes.

        Args:
            branch_name: Name for the feature branch
            files: Optional dict of path -> content
            num_commits: Number of commits to create

        Returns:
            CommitInfo for the last commit
        """
        self.repo.create_branch(branch_name)

        last_commit = None
        for i in range(1, num_commits + 1):
            if files and i == 1:
                for path, content in files.items():
                    self.repo.add_file(path, content)
            else:
                self.repo.add_file(f"feature_{i}.py", f"# Feature {i}\n")

            last_commit = self.repo.commit(f"Feature commit {i}")

        return last_commit

    def expect_suite_creation(
        self,
        suite_uuid: Optional[str] = None,
        status: str = "pending",
        num_tests: int = 3,
    ) -> MockTestSuite:
        """
        Pre-create a suite that the CLI will receive.

        This is useful when you want to control the suite state
        before the CLI makes its request.
        """
        return self.server.create_suite(
            suite_uuid=suite_uuid,
            status=status,
            num_tests=num_tests,
        )

    def set_suite_to_complete(
        self,
        suite_uuid: str,
        test_results: Optional[List[str]] = None,
    ) -> None:
        """
        Set a suite to completed state.

        Args:
            suite_uuid: UUID of the suite
            test_results: List of test statuses (e.g., ["passed", "passed", "failed"])
        """
        self.server.set_suite_status(
            suite_uuid=suite_uuid,
            status="completed",
            test_statuses=test_results,
        )

    def inject_api_error(
        self,
        path: str,
        status_code: int = 500,
        message: str = "Internal Server Error",
        method: str = "GET",
        count: int = 1,
    ) -> None:
        """
        Inject an error for a specific API endpoint.

        Args:
            path: URL path to inject error on
            status_code: HTTP status code
            message: Error message
            method: HTTP method
            count: Number of times to return error (0 = forever)
        """
        self.server.inject_error(path, status_code, message, method, count)

    def clear_api_errors(self) -> None:
        """Clear all injected API errors."""
        self.server.clear_errors()

    def get_api_requests(
        self,
        method: Optional[str] = None,
        path: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get recorded API requests.

        Args:
            method: Filter by HTTP method
            path: Filter by path substring

        Returns:
            List of recorded requests
        """
        return self.server.get_recorded_requests(method=method, path=path)

    def reset(self) -> None:
        """
        Reset the harness state for reuse.

        This clears server state and resets the repo to a clean state.
        """
        if self._server:
            self._server.reset()

        # For repo, we'd need to reset to initial state
        # For now, just note that repo changes persist

    # ========================================================================
    # Context Manager
    # ========================================================================

    def __enter__(self) -> "E2ETestHarness":
        """Context manager entry."""
        return self.start()

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        self.stop(error=exc_type is not None)


# ============================================================================
# Pytest Fixtures
# ============================================================================

def create_e2e_harness(**kwargs) -> E2ETestHarness:
    """Create and start an E2E test harness."""
    harness = E2ETestHarness(**kwargs)
    return harness.start()


def e2e_harness_fixture(**kwargs):
    """
    Factory for pytest fixture.

    Usage in conftest.py:
        @pytest.fixture
        def e2e_harness():
            with E2ETestHarness() as harness:
                yield harness
    """
    return E2ETestHarness(**kwargs)
