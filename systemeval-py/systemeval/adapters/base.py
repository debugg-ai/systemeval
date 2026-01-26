"""Base adapter abstract class for test framework integration."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Union, overload

# Import shared types from central location
from systemeval.types import AdapterConfig, TestFailure, TestItem, TestResult, Verdict

# Re-export for backward compatibility
__all__ = ["BaseAdapter", "AdapterConfig", "TestItem", "TestResult", "TestFailure", "Verdict"]


class BaseAdapter(ABC):
    """Base class for test framework adapters.

    Adapters can be initialized with either:
    1. An AdapterConfig object (preferred)
    2. A project_root string (backward compatible)

    Example:
        # Using AdapterConfig (preferred)
        config = AdapterConfig(project_root="/path/to/project", parallel=True)
        adapter = PytestAdapter(config)

        # Using project_root string (backward compatible)
        adapter = PytestAdapter("/path/to/project")
    """

    def __init__(
        self,
        config_or_project_root: Union[AdapterConfig, str, Path],
    ) -> None:
        """Initialize adapter with configuration or project root.

        Args:
            config_or_project_root: Either an AdapterConfig object or
                                    an absolute path to the project root directory.
        """
        if isinstance(config_or_project_root, AdapterConfig):
            self._config = config_or_project_root
            # Ensure project_root is a string for compatibility
            self.project_root = str(config_or_project_root.project_root)
        else:
            # Backward compatible: create config from project_root string
            project_root = str(config_or_project_root)
            if not Path(project_root).is_absolute():
                raise ValueError(
                    f"project_root must be an absolute path, got: {project_root}"
                )
            self._config = AdapterConfig(project_root=project_root)
            self.project_root = project_root

    @property
    def config(self) -> AdapterConfig:
        """Get the adapter configuration."""
        return self._config

    @abstractmethod
    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover tests matching criteria."""
        pass

    @abstractmethod
    def execute(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> TestResult:
        """Execute tests and return structured results.

        Runs the specified tests (or all tests if none specified) using the
        framework-specific test runner and returns a unified TestResult.

        Args:
            tests: Optional list of specific TestItem objects to run.
                   If None, runs all discovered tests.
            parallel: Enable parallel test execution. Implementation depends
                      on framework support (pytest-xdist, Jest workers, etc.).
            coverage: Enable code coverage collection. Requires framework-specific
                      coverage plugins (pytest-cov, Jest --coverage, etc.).
            failfast: Stop execution on first test failure. Useful for rapid
                      feedback during development.
            verbose: Enable verbose output from the test runner.
            timeout: Maximum execution time in seconds. Implementation varies
                     by adapter (subprocess timeout, framework timeout, etc.).

        Returns:
            TestResult containing:
            - passed/failed/errors/skipped counts
            - duration in seconds
            - exit_code (0=pass, 1=fail, 2=error)
            - failures list with TestFailure details
            - verdict (PASS, FAIL, or ERROR)

        Note:
            Implementations should:
            - Handle subprocess timeouts gracefully
            - Parse framework-specific output to TestResult
            - Include failure details with test IDs and messages
            - Never raise exceptions for test failures (return them in result)
        """
        pass

    @abstractmethod
    def get_available_markers(self) -> List[str]:
        """Return available test markers/categories."""
        pass

    @abstractmethod
    def validate_environment(self) -> bool:
        """Validate that the test framework is properly configured."""
        pass

    def get_command(
        self,
        tests: Optional[List[TestItem]] = None,
        parallel: bool = False,
        coverage: bool = False,
        failfast: bool = False,
        verbose: bool = False,
        timeout: Optional[int] = None,
    ) -> List[str]:
        """Get the command that would be used to run tests.

        Useful for debugging and display purposes.

        Args:
            tests: Optional list of specific tests to run.
            parallel: Enable parallel execution.
            coverage: Enable coverage collection.
            failfast: Stop on first failure.
            verbose: Enable verbose output.
            timeout: Test timeout in seconds.

        Returns:
            List of command arguments that would be passed to subprocess.
        """
        return []
