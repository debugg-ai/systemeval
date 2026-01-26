"""
Base environment abstraction for test orchestration.

This module defines the core abstractions for test environments:

- Environment: Abstract base class for all test environments
- EnvironmentType: Enum of supported environment types
- SetupResult: Result of environment setup operations
- PhaseTimings: Timing breakdown for test execution phases

Environment Lifecycle:
    1. __init__: Configure the environment
    2. setup(): Initialize resources (build, start services)
    3. wait_ready(): Wait for environment to be ready
    4. run_tests(): Execute tests
    5. teardown(): Clean up resources

Usage with context manager:
    with DockerComposeEnvironment("backend", config) as env:
        result = env.run_tests()

Usage without context manager:
    env = DockerComposeEnvironment("backend", config)
    try:
        setup_result = env.setup()
        if setup_result.success and env.wait_ready():
            result = env.run_tests()
    finally:
        env.teardown()
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from systemeval.types import TestResult


class EnvironmentType(str, Enum):
    """
    Supported environment types for test execution.

    Each type represents a different execution context with specific
    lifecycle management requirements.

    Attributes:
        STANDALONE: Direct execution on local host (no containers)
        DOCKER_COMPOSE: Multi-container Docker Compose environment
        COMPOSITE: Combination of multiple environments
        NGROK: Environment with ngrok tunnel for public URL exposure
        BROWSER: Browser testing environment (Playwright, Surfer)
    """

    STANDALONE = "standalone"
    DOCKER_COMPOSE = "docker-compose"
    COMPOSITE = "composite"
    NGROK = "ngrok"
    BROWSER = "browser"


@dataclass
class SetupResult:
    """
    Result of environment setup operation.

    Captures the outcome of setup(), including success status,
    human-readable message, timing, and any additional details.

    Attributes:
        success: Whether setup completed successfully
        message: Human-readable status message
        duration: Time taken for setup in seconds
        details: Additional details (e.g., container IDs, ports)

    Example:
        result = SetupResult(
            success=True,
            message="Started 3 containers",
            duration=15.2,
            details={"containers": ["web", "db", "redis"]}
        )
    """

    success: bool
    message: str = ""
    duration: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseTimings:
    """
    Timing breakdown for test execution phases.

    Tracks time spent in each phase of the environment lifecycle
    for performance analysis and debugging.

    Attributes:
        build: Time for build phase (Docker build, npm install, etc.)
        startup: Time to start services
        health_check: Time waiting for services to become healthy
        tests: Time running tests
        cleanup: Time for teardown/cleanup

    Properties:
        total: Sum of all phase timings

    Example:
        timings = PhaseTimings(
            build=30.0,
            startup=5.0,
            health_check=10.0,
            tests=120.0,
            cleanup=2.0,
        )
        print(f"Total time: {timings.total}s")  # 167.0s
    """

    build: float = 0.0
    startup: float = 0.0
    health_check: float = 0.0
    tests: float = 0.0
    cleanup: float = 0.0

    @property
    def total(self) -> float:
        """Return total time across all phases."""
        return self.build + self.startup + self.health_check + self.tests + self.cleanup


class Environment(ABC):
    """
    Abstract base class for test environments.

    Environments manage the complete lifecycle of a test execution context:
    setup, readiness checks, test execution, and teardown. Subclasses
    implement the specifics for different execution environments.

    Lifecycle Methods:
        setup() -> SetupResult: Initialize the environment
        is_ready() -> bool: Check if ready (non-blocking)
        wait_ready(timeout) -> bool: Wait until ready (blocking)
        run_tests(...) -> TestResult: Execute tests
        teardown(keep_running): Clean up resources

    Context Manager Support:
        Environments can be used as context managers for automatic
        setup and teardown:

        with MyEnvironment("name", config) as env:
            result = env.run_tests()

    Attributes:
        name: Environment name (e.g., 'backend', 'frontend')
        config: Configuration dictionary
        timings: PhaseTimings tracking execution times
        env_type: EnvironmentType indicating the environment kind

    Example Implementation:
        class LocalEnvironment(Environment):
            @property
            def env_type(self) -> EnvironmentType:
                return EnvironmentType.STANDALONE

            def setup(self) -> SetupResult:
                return SetupResult(success=True)

            def is_ready(self) -> bool:
                return True

            def wait_ready(self, timeout: int = 120) -> bool:
                return True

            def run_tests(self, suite=None, category=None, verbose=False):
                # Execute tests...
                return TestResult(passed=10, failed=0, ...)

            def teardown(self, keep_running: bool = False) -> None:
                pass
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        """
        Initialize the environment.

        Args:
            name: Human-readable name for this environment instance.
                  Used in logging and error messages.
                  Examples: 'backend', 'frontend', 'full-stack'
            config: Configuration dictionary with environment-specific
                   settings. The structure depends on the environment type.

        Attributes Set:
            self.name: The provided name
            self.config: The provided configuration
            self.timings: Fresh PhaseTimings instance
            self._is_setup: Internal flag tracking setup state
        """
        self.name = name
        self.config = config
        self.timings = PhaseTimings()
        self._is_setup = False

    @property
    @abstractmethod
    def env_type(self) -> EnvironmentType:
        """
        Return the environment type.

        Each environment implementation must return the appropriate
        EnvironmentType enum value.

        Returns:
            EnvironmentType indicating what kind of environment this is.

        Example:
            @property
            def env_type(self) -> EnvironmentType:
                return EnvironmentType.DOCKER_COMPOSE
        """
        pass

    @abstractmethod
    def setup(self) -> SetupResult:
        """
        Set up the environment for test execution.

        This method performs all initialization required before tests
        can run, such as:
        - Building Docker images
        - Starting containers or services
        - Installing dependencies
        - Creating test databases

        Implementations should:
        - Record timing in self.timings.build and self.timings.startup
        - Return success=False with descriptive message on failure
        - Include relevant details in the result (container IDs, ports, etc.)

        Returns:
            SetupResult with:
            - success: True if setup completed without errors
            - message: Human-readable status (shown to user)
            - duration: Time taken in seconds
            - details: Additional data (container IDs, URLs, etc.)

        Raises:
            Should not raise exceptions - capture errors in SetupResult.

        Example:
            def setup(self) -> SetupResult:
                start = time.time()
                try:
                    self._start_containers()
                    return SetupResult(
                        success=True,
                        message="Started 3 containers",
                        duration=time.time() - start,
                    )
                except Exception as e:
                    return SetupResult(
                        success=False,
                        message=f"Failed to start: {e}",
                        duration=time.time() - start,
                    )
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if the environment is ready for tests (non-blocking).

        Performs a quick check to determine if the environment is
        ready to execute tests. This should NOT wait or retry.

        Ready typically means:
        - All services are running
        - Health checks pass
        - Required ports are accessible
        - Databases are accepting connections

        Returns:
            True if the environment is ready for tests,
            False if not yet ready or in error state.

        Note:
            Use wait_ready() for blocking/polling behavior.
            This method should be fast and non-blocking.

        Example:
            def is_ready(self) -> bool:
                return self._container_running and self._health_check_passes()
        """
        pass

    @abstractmethod
    def wait_ready(self, timeout: int = 120) -> bool:
        """
        Wait for the environment to become ready (blocking).

        Polls is_ready() until it returns True or timeout expires.
        This is typically called after setup() succeeds.

        Args:
            timeout: Maximum seconds to wait for readiness.
                    Default is 120 seconds (2 minutes).

        Returns:
            True if environment became ready within timeout,
            False if timeout expired before environment was ready.

        Side Effects:
            Should update self.timings.health_check with wait duration.

        Note:
            Implementations should:
            - Log progress during waiting
            - Use reasonable polling intervals (e.g., 1-5 seconds)
            - Handle interrupts gracefully

        Example:
            def wait_ready(self, timeout: int = 120) -> bool:
                start = time.time()
                while time.time() - start < timeout:
                    if self.is_ready():
                        self.timings.health_check = time.time() - start
                        return True
                    time.sleep(2)
                return False
        """
        pass

    @abstractmethod
    def run_tests(
        self,
        suite: Optional[str] = None,
        category: Optional[str] = None,
        verbose: bool = False,
    ) -> TestResult:
        """
        Run tests in this environment.

        Executes the test suite and returns structured results.
        The environment must be ready (setup() and wait_ready()
        must have succeeded).

        Args:
            suite: Optional test suite name to run (e.g., 'e2e', 'unit').
                  If None, runs default/all tests.
            category: Optional test category filter (e.g., 'integration').
                     Filters tests by marker or tag.
            verbose: If True, output detailed test progress.

        Returns:
            TestResult containing:
            - passed/failed/errors/skipped counts
            - duration in seconds
            - failure details
            - exit code

        Side Effects:
            Updates self.timings.tests with execution duration.

        Note:
            Implementations should handle:
            - Test discovery
            - Test execution (via adapter or direct command)
            - Output parsing
            - Timeout handling

        Example:
            def run_tests(self, suite=None, category=None, verbose=False):
                start = time.time()
                result = self._executor.execute("pytest -v")
                parsed = self._executor.parse_test_results(
                    result.stdout, result.exit_code
                )
                self.timings.tests = time.time() - start
                return parsed
        """
        pass

    @abstractmethod
    def teardown(self, keep_running: bool = False) -> None:
        """
        Tear down the environment and release resources.

        Cleans up all resources created during setup(), such as:
        - Stopping and removing containers
        - Closing network connections
        - Deleting temporary files
        - Killing background processes

        Args:
            keep_running: If True, leave services running instead of
                         stopping them. Useful for debugging failed tests.

        Side Effects:
            Updates self.timings.cleanup with teardown duration.

        Note:
            - Should be idempotent (safe to call multiple times)
            - Should not raise exceptions (log errors instead)
            - Called automatically by context manager __exit__

        Example:
            def teardown(self, keep_running: bool = False) -> None:
                start = time.time()
                if not keep_running:
                    self._stop_containers()
                self.timings.cleanup = time.time() - start
        """
        pass

    def __enter__(self) -> "Environment":
        """
        Context manager entry - setup and wait for ready.

        Performs setup() and wait_ready() automatically.
        Raises RuntimeError if either fails.

        Returns:
            self: The environment instance ready for use.

        Raises:
            RuntimeError: If setup() fails or environment doesn't
                         become ready within the default timeout.

        Example:
            with DockerComposeEnvironment("backend", config) as env:
                result = env.run_tests()
                # teardown called automatically on exit
        """
        result = self.setup()
        if not result.success:
            raise RuntimeError(f"Environment setup failed: {result.message}")
        if not self.wait_ready():
            self.teardown()
            raise RuntimeError(f"Environment {self.name} did not become ready")
        self._is_setup = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """
        Context manager exit - teardown the environment.

        Calls teardown() if setup was successful. Called automatically
        when exiting a 'with' block, even if an exception occurred.

        Args:
            exc_type: Exception type if an exception was raised, else None
            exc_val: Exception instance if raised, else None
            exc_tb: Traceback if exception raised, else None

        Returns:
            False: Never suppresses exceptions (they propagate normally)
        """
        if self._is_setup:
            self.teardown()
        return False
