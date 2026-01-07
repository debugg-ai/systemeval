"""
Core modules for systemeval.

Provides framework-agnostic test result structures, configuration loading,
pass/fail criteria, and unified reporting.

SCHEMA HIERARCHY (Read this first!):
=====================================================================

1. Shared Types (types.py)
   - Verdict enum: PASS, FAIL, ERROR
   - TestResult, TestItem, TestFailure dataclasses
   - Central location to avoid circular dependencies

2. TestResult (adapters/base.py re-exports from types.py)
   - Intermediate format returned by adapter.execute()
   - Contains: passed, failed, errors, skipped, duration, exit_code
   - Has .to_evaluation() method to convert to EvaluationResult

3. EvaluationResult (core/evaluation.py)
   - PRIMARY output schema for ALL evaluations
   - This is the SINGULAR contract for output
   - Contains: metadata, sessions, verdict, summary
   - Methods: to_json(), to_dict()

CORRECT FLOW:
Adapter.execute() → TestResult → .to_evaluation() → EvaluationResult → JSON

Always use evaluation.py classes for new code.
=====================================================================
"""

from .criteria import (
    COVERAGE_50,
    COVERAGE_70,
    COVERAGE_80,
    COVERAGE_90,
    DURATION_WITHIN_1_MIN,
    DURATION_WITHIN_5_MIN,
    DURATION_WITHIN_10_MIN,
    E2E_TEST_CRITERIA,
    ERROR_RATE_5,
    ERROR_RATE_10,
    ERROR_RATE_ZERO,
    INTEGRATION_TEST_CRITERIA,
    MetricCriterion,
    NO_ERRORS,
    NO_FAILURES,
    PASS_RATE_50,
    PASS_RATE_70,
    PASS_RATE_90,
    SMOKE_TEST_CRITERIA,
    STRICT_CRITERIA,
    TESTS_PASSED,
    UNIT_TEST_CRITERIA,
    coverage_minimum,
    duration_within,
    error_rate_maximum,
    pass_rate_minimum,
)
from .reporter import Reporter
from .evaluation import (
    EvaluationResult,
    EvaluationMetadata,
    SessionResult,
    MetricResult,
    Verdict,
    create_evaluation,
    create_session,
    metric,
    SCHEMA_VERSION,
)

__all__ = [
    # Criteria
    "MetricCriterion",
    "TESTS_PASSED",
    "NO_FAILURES",
    "NO_ERRORS",
    "ERROR_RATE_ZERO",
    "ERROR_RATE_5",
    "ERROR_RATE_10",
    "PASS_RATE_50",
    "PASS_RATE_70",
    "PASS_RATE_90",
    "COVERAGE_50",
    "COVERAGE_70",
    "COVERAGE_80",
    "COVERAGE_90",
    "DURATION_WITHIN_1_MIN",
    "DURATION_WITHIN_5_MIN",
    "DURATION_WITHIN_10_MIN",
    "UNIT_TEST_CRITERIA",
    "INTEGRATION_TEST_CRITERIA",
    "E2E_TEST_CRITERIA",
    "STRICT_CRITERIA",
    "SMOKE_TEST_CRITERIA",
    "pass_rate_minimum",
    "coverage_minimum",
    "error_rate_maximum",
    "duration_within",
    # Reporter
    "Reporter",
    # Evaluation (PRIMARY schema - use this!)
    "Verdict",
    "MetricResult",
    "SessionResult",
    "EvaluationResult",
    "EvaluationMetadata",
    "create_evaluation",
    "create_session",
    "metric",
    "SCHEMA_VERSION",
]
