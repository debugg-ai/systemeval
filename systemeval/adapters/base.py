"""Base adapter abstract class for test framework integration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class TestItem:
    """Represents a single test item discovered by the adapter."""

    id: str
    name: str
    path: str
    markers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestFailure:
    """Represents a test failure with details."""

    test_id: str
    test_name: str
    message: str
    traceback: Optional[str] = None
    duration: float = 0.0


@dataclass
class TestResult:
    """Test execution results."""

    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    failures: List[TestFailure] = field(default_factory=list)
    total: int = 0
    exit_code: int = 0
    coverage_percent: Optional[float] = None

    def __post_init__(self) -> None:
        """Calculate total if not provided."""
        if self.total == 0:
            self.total = self.passed + self.failed + self.errors + self.skipped


class BaseAdapter(ABC):
    """Base class for test framework adapters."""

    def __init__(self, project_root: str) -> None:
        """Initialize adapter with project root directory.

        Args:
            project_root: Absolute path to the project root directory
        """
        self.project_root = project_root

    @abstractmethod
    def discover(
        self,
        category: Optional[str] = None,
        app: Optional[str] = None,
        file: Optional[str] = None,
    ) -> List[TestItem]:
        """Discover tests matching criteria.

        Args:
            category: Test category/marker to filter by (e.g., 'unit', 'integration')
            app: Application/module name to filter by
            file: Specific test file path to filter by

        Returns:
            List of discovered test items
        """
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
        """Execute tests and return results.

        Args:
            tests: Specific test items to run (None = run all)
            parallel: Enable parallel test execution
            coverage: Enable coverage reporting
            failfast: Stop on first failure
            verbose: Verbose output
            timeout: Timeout in seconds for entire test run

        Returns:
            Test execution results
        """
        pass

    @abstractmethod
    def get_available_markers(self) -> List[str]:
        """Return available test markers/categories.

        Returns:
            List of marker names (e.g., ['unit', 'integration', 'api'])
        """
        pass

    @abstractmethod
    def validate_environment(self) -> bool:
        """Validate that the test framework is properly configured.

        Returns:
            True if environment is valid, False otherwise
        """
        pass
