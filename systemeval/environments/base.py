"""
Base environment abstraction for test orchestration.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional

from systemeval.adapters import TestResult


class EnvironmentType(str, Enum):
    """Supported environment types."""
    STANDALONE = "standalone"
    DOCKER_COMPOSE = "docker-compose"
    COMPOSITE = "composite"


@dataclass
class SetupResult:
    """Result of environment setup."""
    success: bool
    message: str = ""
    duration: float = 0.0
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class PhaseTimings:
    """Timing breakdown for test phases."""
    build: float = 0.0
    startup: float = 0.0
    health_check: float = 0.0
    tests: float = 0.0
    cleanup: float = 0.0

    @property
    def total(self) -> float:
        return self.build + self.startup + self.health_check + self.tests + self.cleanup


class Environment(ABC):
    """
    Base class for test environments.

    Environments manage the lifecycle of a test context:
    setup -> wait_ready -> run_tests -> teardown
    """

    def __init__(self, name: str, config: Dict[str, Any]) -> None:
        """
        Initialize environment.

        Args:
            name: Environment name (e.g., 'backend', 'frontend')
            config: Environment configuration dict
        """
        self.name = name
        self.config = config
        self.timings = PhaseTimings()
        self._is_setup = False

    @property
    @abstractmethod
    def env_type(self) -> EnvironmentType:
        """Return the environment type."""
        pass

    @abstractmethod
    def setup(self) -> SetupResult:
        """
        Set up the environment (build, start services, etc.)

        Returns:
            SetupResult with success status and details
        """
        pass

    @abstractmethod
    def is_ready(self) -> bool:
        """
        Check if the environment is ready for tests.

        Returns:
            True if ready, False otherwise
        """
        pass

    @abstractmethod
    def wait_ready(self, timeout: int = 120) -> bool:
        """
        Wait for the environment to be ready.

        Args:
            timeout: Maximum seconds to wait

        Returns:
            True if ready within timeout, False otherwise
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

        Args:
            suite: Test suite to run (e.g., 'e2e', 'integration')
            category: Test category filter
            verbose: Verbose output

        Returns:
            TestResult with test outcomes
        """
        pass

    @abstractmethod
    def teardown(self, keep_running: bool = False) -> None:
        """
        Tear down the environment.

        Args:
            keep_running: If True, keep services running after tests
        """
        pass

    def __enter__(self) -> "Environment":
        """Context manager entry."""
        result = self.setup()
        if not result.success:
            raise RuntimeError(f"Environment setup failed: {result.message}")
        if not self.wait_ready():
            self.teardown()
            raise RuntimeError(f"Environment {self.name} did not become ready")
        self._is_setup = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit."""
        if self._is_setup:
            self.teardown()
        return False
