"""
Test result types.

This module contains types for representing test execution results,
including individual test items, failures, and aggregate results.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from .common import Verdict


@dataclass
class TestItem:
    """Represents a single test item discovered by an adapter."""

    id: str
    name: str
    path: str
    markers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Location info (optional, for parity with TypeScript)
    line: Optional[int] = None
    column: Optional[int] = None
    suite: Optional[str] = None


@dataclass
class TestFailure:
    """Represents a test failure with details."""

    test_id: str
    test_name: str
    message: str
    traceback: Optional[str] = None
    duration: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    # Assertion details (optional, for parity with TypeScript)
    expected: Optional[Any] = None
    actual: Optional[Any] = None


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

    # Pipeline adapter metadata (used by PipelineAdapter for detailed evaluation)
    pipeline_tests: Optional[List["TestItem"]] = field(default=None, repr=False)
    pipeline_metrics: Optional[Dict[str, Any]] = field(default=None, repr=False)
    pipeline_adapter: Optional[Any] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        """Calculate total if not provided."""
        if self.total is None:
            self.total = self.passed + self.failed + self.errors + self.skipped

    @property
    def verdict(self) -> Verdict:
        """Determine objective verdict based on results."""
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
            "duration_seconds": round(self.duration, 3),
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
    ) -> "EvaluationResult":  # type: ignore[name-defined]
        """Convert TestResult to unified EvaluationResult.

        Note: Import is deferred to avoid circular dependency.
        """
        from systemeval.core.evaluation import (
            EvaluationResult,
            create_evaluation,
            create_session,
            metric,
        )

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
                    "duration_seconds": f.duration,
                }
                for f in self.failures
            ]

        result.add_session(session)
        result.metadata.duration_seconds = self.duration
        result.finalize()

        return result


__all__ = ["TestItem", "TestFailure", "TestResult"]
