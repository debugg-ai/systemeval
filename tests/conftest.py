"""Pytest configuration and fixtures for SystemEval tests."""

import pytest
from systemeval.adapters import TestResult, TestFailure, Verdict
from systemeval.core.evaluation import (
    EvaluationResult,
    EvaluationMetadata,
    SessionResult,
    MetricResult,
    create_evaluation,
    create_session,
    metric,
)


@pytest.fixture
def passing_test_result():
    """Create a passing TestResult."""
    return TestResult(
        passed=10,
        failed=0,
        errors=0,
        skipped=2,
        duration=5.5,
        category="unit",
    )


@pytest.fixture
def failing_test_result():
    """Create a failing TestResult with failures."""
    return TestResult(
        passed=8,
        failed=2,
        errors=0,
        skipped=1,
        duration=10.2,
        failures=[
            TestFailure(
                test_id="test_example::test_one",
                test_name="test_one",
                message="AssertionError: expected 1, got 2",
                duration=0.5,
            ),
            TestFailure(
                test_id="test_example::test_two",
                test_name="test_two",
                message="ValueError: invalid input",
                duration=0.3,
            ),
        ],
        category="integration",
    )


@pytest.fixture
def error_test_result():
    """Create an error TestResult."""
    return TestResult(
        passed=0,
        failed=0,
        errors=1,
        skipped=0,
        duration=0.1,
        exit_code=2,
    )


@pytest.fixture
def empty_test_result():
    """Create an empty TestResult (no tests collected)."""
    return TestResult(
        passed=0,
        failed=0,
        errors=0,
        skipped=0,
        duration=0.0,
        exit_code=2,
    )


@pytest.fixture
def sample_evaluation():
    """Create a sample EvaluationResult."""
    evaluation = create_evaluation(
        adapter_type="pytest",
        category="unit",
        project_name="test-project",
    )

    session = create_session("unit-tests")
    session.metrics.append(metric(
        name="tests_passed",
        value=10,
        expected=">0",
        condition=True,
        message="10 tests passed",
    ))
    session.metrics.append(metric(
        name="tests_failed",
        value=0,
        expected="0",
        condition=True,
    ))

    evaluation.add_session(session)
    evaluation.finalize()

    return evaluation


@pytest.fixture
def pipeline_metrics():
    """Sample pipeline metrics for testing."""
    return {
        "build_status": "succeeded",
        "build_duration": 45.2,
        "container_healthy": True,
        "health_checks_passed": 3,
        "kg_exists": True,
        "kg_pages": 15,
        "e2e_runs": 5,
        "e2e_passed": 4,
        "e2e_failed": 1,
        "e2e_error": 0,
        "e2e_error_rate": 0.0,
        "diagnostics": ["E2E test failure: login flow"],
    }
