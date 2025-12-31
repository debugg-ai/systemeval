"""
Base adapter abstract class for test framework integration.

SCHEMA ARCHITECTURE:
====================

TestResult (this file):
- INTERMEDIATE format returned by adapter.execute()
- Simple data class with test counts (passed, failed, errors, skipped)
- Has .to_evaluation() method for conversion to final schema
- Think of it as: "raw test execution data"

EvaluationResult (evaluation.py):
- FINAL output schema with full metadata, sessions, verdicts
- This is what gets serialized to JSON
- Think of it as: "complete evaluation report with context"

FLOW:
1. Adapter discovers tests → List[TestItem]
2. Adapter executes tests → TestResult (this class)
3. TestResult.to_evaluation() → EvaluationResult (final output)
4. EvaluationResult.to_json() → JSON output

Never skip step 3. Always convert TestResult to EvaluationResult before output.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

# Import unified evaluation schema
from systemeval.core.evaluation import (
    EvaluationResult,
    Verdict,
    create_evaluation,
    create_session,
    metric,
)


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
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TestResult:
    """Test execution results with objective verdict."""

    passed: int
    failed: int
    errors: int
    skipped: int
    duration: float
    failures: List[TestFailure] = field(default_factory=list)
    total: Optional[int] = None
    exit_code: int = 0
    coverage_percent: Optional[float] = None
    category: Optional[str] = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"))
    parsing_warning: Optional[str] = None  # Warning when output format is unrecognized
    parsed_from: Optional[str] = None  # Source of parsed data: "pytest", "jest", "playwright", "json", "fallback"

    def __post_init__(self) -> None:
        """Calculate total if not provided."""
        if self.total is None:
            self.total = self.passed + self.failed + self.errors + self.skipped

    @property
    def verdict(self) -> Verdict:
        """Determine objective verdict based on results.

        Verdict Logic (cascade, non-negotiable):
        - exit_code == 2 → ERROR (collection/config error)
        - total == 0 → ERROR (no tests collected)
        - parsed_from == "fallback" AND exit_code != 0 → ERROR (unrecognized output with failure)
        - failed > 0 or errors > 0 → FAIL
        - All tests pass → PASS
        """
        if self.exit_code == 2:
            return Verdict.ERROR
        if self.total == 0:
            return Verdict.ERROR
        # When output format is unrecognized and command failed, report ERROR not FAIL
        # This prevents false positives from guessed test counts
        if self.parsed_from == "fallback" and self.exit_code != 0:
            return Verdict.ERROR
        if self.failed > 0 or self.errors > 0:
            return Verdict.FAIL
        return Verdict.PASS

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration": round(self.duration, 3),
            "timestamp": self.timestamp,
            "category": self.category,
            "coverage_percent": self.coverage_percent,
        }
        if self.parsing_warning:
            result["parsing_warning"] = self.parsing_warning
        if self.parsed_from:
            result["parsed_from"] = self.parsed_from
        return result

    def to_evaluation(
        self,
        adapter_type: str = "unknown",
        project_name: Optional[str] = None,
    ) -> EvaluationResult:
        """
        Convert TestResult to unified EvaluationResult.

        This provides backward compatibility while migrating to the
        unified schema.
        """
        result = create_evaluation(
            adapter_type=adapter_type,
            category=self.category,
            project_name=project_name,
        )

        # Create session from test results
        session = create_session(self.category or "tests")

        # Add core metrics
        session.metrics.append(metric(
            name="tests_passed",
            value=self.passed,
            expected=">0",
            condition=self.passed > 0 or self.total == 0,
            message=f"{self.passed} tests passed",
        ))

        session.metrics.append(metric(
            name="tests_failed",
            value=self.failed,
            expected="0",
            condition=self.failed == 0,
            message=f"{self.failed} tests failed" if self.failed else None,
        ))

        session.metrics.append(metric(
            name="tests_errors",
            value=self.errors,
            expected="0",
            condition=self.errors == 0,
            message=f"{self.errors} test errors" if self.errors else None,
        ))

        if self.coverage_percent is not None:
            session.metrics.append(metric(
                name="coverage_percent",
                value=self.coverage_percent,
                expected=">=0",
                condition=True,  # Coverage is informational
                message=f"{self.coverage_percent:.1f}% coverage",
                severity="info",
            ))

        session.duration_seconds = self.duration

        # Add failure details to session metadata
        if self.failures:
            session.metadata["failures"] = [
                {
                    "test_id": f.test_id,
                    "test_name": f.test_name,
                    "message": f.message,
                    "duration": f.duration,
                }
                for f in self.failures
            ]

        result.add_session(session)
        result.metadata.duration_seconds = self.duration
        result.finalize()

        return result


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
