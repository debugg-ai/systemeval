"""
Core modules for systemeval.

Provides framework-agnostic test result structures, configuration loading,
pass/fail criteria, and unified reporting.
"""

from .config import (
    CategoryConfig,
    EnvironmentConfig,
    JestConfig,
    PytestConfig,
    ReportingConfig,
    SystemEvalConfig,
    find_config_file,
    load_config,
)
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
from .reporter import Reporter, create_reporter
from .result import MetricResult, SequenceResult, SessionResult, Verdict
from .evaluation import (
    EvaluationResult,
    EvaluationMetadata,
    SessionResult as EvalSessionResult,
    MetricResult as EvalMetricResult,
    Verdict as EvalVerdict,
    create_evaluation,
    create_session,
    metric,
    SCHEMA_VERSION,
)

__all__ = [
    # Config
    "CategoryConfig",
    "EnvironmentConfig",
    "JestConfig",
    "PytestConfig",
    "ReportingConfig",
    "SystemEvalConfig",
    "find_config_file",
    "load_config",
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
    "create_reporter",
    # Result (legacy)
    "Verdict",
    "MetricResult",
    "SessionResult",
    "SequenceResult",
    # Evaluation (unified schema)
    "EvaluationResult",
    "EvaluationMetadata",
    "create_evaluation",
    "create_session",
    "metric",
    "SCHEMA_VERSION",
]
