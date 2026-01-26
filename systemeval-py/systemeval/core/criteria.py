"""
Standard Pass/Fail Criteria Library

HARDCODED criteria for common test metrics.
These are NOT configurable - they define what "passing" means.

Framework-agnostic criteria that can be reused across pytest, jest, etc.
"""
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricCriterion:
    """
    A single metric with hardcoded pass/fail criteria.

    The evaluator is a callable that returns True (pass) or False (fail).
    This is NOT interpretable - the criteria is baked into the code.
    """

    name: str
    evaluator: Callable[[Any], bool]
    failure_message: str  # Use {value} placeholder for the actual value

    def evaluate(self, value: Any) -> tuple[bool, Optional[str]]:
        """
        Evaluate the criterion.

        Returns:
            (passed, failure_message_or_none) tuple
        """
        try:
            passed = self.evaluator(value)
        except (TypeError, ValueError, AttributeError) as e:
            # Evaluator failed due to incompatible value type
            logger.debug(f"Criterion '{self.name}' evaluation failed: {e}")
            passed = False
        return (passed, None if passed else self.failure_message.format(value=value))


# =============================================================================
# TEST EXECUTION CRITERIA
# =============================================================================

TESTS_PASSED = MetricCriterion(
    name="tests_passed",
    evaluator=lambda v: v is not None and v > 0,
    failure_message="Tests passed: {value} (required: > 0)",
)

NO_FAILURES = MetricCriterion(
    name="tests_failed",
    evaluator=lambda v: v == 0,
    failure_message="Tests failed: {value} (required: 0)",
)

NO_ERRORS = MetricCriterion(
    name="tests_errored",
    evaluator=lambda v: v == 0,
    failure_message="Tests with errors: {value} (required: 0 - errors are system bugs)",
)

ALL_TESTS_PASSED = MetricCriterion(
    name="pass_rate",
    evaluator=lambda v: v == 100.0 or v == 100,
    failure_message="Pass rate: {value}% (required: 100%)",
)


# =============================================================================
# PASS RATE CRITERIA
# =============================================================================

def pass_rate_minimum(threshold: float) -> MetricCriterion:
    """Create a pass rate criterion with custom threshold."""
    return MetricCriterion(
        name="pass_rate",
        evaluator=lambda v: v is not None and v >= threshold,
        failure_message=f"Pass rate: {{value}}% (required: >= {threshold}%)",
    )


PASS_RATE_50 = pass_rate_minimum(50.0)
PASS_RATE_70 = pass_rate_minimum(70.0)
PASS_RATE_90 = pass_rate_minimum(90.0)


# =============================================================================
# COVERAGE CRITERIA
# =============================================================================

def coverage_minimum(threshold: float) -> MetricCriterion:
    """Create a coverage criterion with custom threshold."""
    return MetricCriterion(
        name="coverage",
        evaluator=lambda v: v is not None and v >= threshold,
        failure_message=f"Coverage: {{value}}% (required: >= {threshold}%)",
    )


COVERAGE_50 = coverage_minimum(50.0)
COVERAGE_70 = coverage_minimum(70.0)
COVERAGE_80 = coverage_minimum(80.0)
COVERAGE_90 = coverage_minimum(90.0)


# =============================================================================
# DURATION / TIMEOUT CRITERIA
# =============================================================================

def duration_within(timeout_sec: float) -> MetricCriterion:
    """Create a duration criterion with custom timeout."""
    return MetricCriterion(
        name="duration_seconds",
        evaluator=lambda v: v is None or v <= timeout_sec,
        failure_message=f"Duration: {{value}}s (required: <= {timeout_sec}s)",
    )


DURATION_WITHIN_1_MIN = duration_within(60)
DURATION_WITHIN_5_MIN = duration_within(300)
DURATION_WITHIN_10_MIN = duration_within(600)


# =============================================================================
# ERROR RATE CRITERIA
# =============================================================================

ERROR_RATE_ZERO = MetricCriterion(
    name="error_rate",
    evaluator=lambda v: v == 0 or v == 0.0,
    failure_message="Error rate: {value}% (required: 0% - errors are system bugs)",
)


def error_rate_maximum(threshold: float) -> MetricCriterion:
    """Create an error rate criterion with custom threshold."""
    return MetricCriterion(
        name="error_rate",
        evaluator=lambda v: v is None or v <= threshold,
        failure_message=f"Error rate: {{value}}% (required: <= {threshold}%)",
    )


ERROR_RATE_5 = error_rate_maximum(5.0)
ERROR_RATE_10 = error_rate_maximum(10.0)


# =============================================================================
# PRESET CRITERIA SETS
# These are standard sets for common test categories.
# =============================================================================

# For unit tests (fast, no external dependencies)
UNIT_TEST_CRITERIA = [
    TESTS_PASSED,
    NO_ERRORS,
    DURATION_WITHIN_1_MIN,
]

# For integration tests (may have external dependencies)
INTEGRATION_TEST_CRITERIA = [
    TESTS_PASSED,
    NO_ERRORS,
    DURATION_WITHIN_5_MIN,
]

# For E2E tests (browser automation, slow)
E2E_TEST_CRITERIA = [
    TESTS_PASSED,
    ERROR_RATE_ZERO,  # System bugs, not test failures
    DURATION_WITHIN_10_MIN,
]

# For strict quality gates (CI/CD)
STRICT_CRITERIA = [
    ALL_TESTS_PASSED,
    NO_ERRORS,
    COVERAGE_80,
]

# For minimal smoke tests
SMOKE_TEST_CRITERIA = [
    TESTS_PASSED,
    NO_ERRORS,
]
