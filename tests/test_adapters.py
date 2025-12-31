"""Tests for adapter TestResult to EvaluationResult conversion."""

import json
import pytest
from systemeval.adapters import TestResult, TestFailure, Verdict
from systemeval.core.evaluation import SCHEMA_VERSION


class TestTestResultVerdict:
    """Tests for TestResult verdict computation."""

    def test_verdict_pass_all_tests_pass(self, passing_test_result):
        """Test PASS verdict when all tests pass."""
        assert passing_test_result.verdict == Verdict.PASS

    def test_verdict_fail_with_failures(self, failing_test_result):
        """Test FAIL verdict when tests fail."""
        assert failing_test_result.verdict == Verdict.FAIL

    def test_verdict_fail_with_errors(self):
        """Test FAIL verdict when tests have errors."""
        result = TestResult(
            passed=5,
            failed=0,
            errors=1,
            skipped=0,
            duration=1.0,
        )
        assert result.verdict == Verdict.FAIL

    def test_verdict_error_exit_code_2(self):
        """Test ERROR verdict with exit code 2."""
        result = TestResult(
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            duration=0.0,
            exit_code=2,
        )
        assert result.verdict == Verdict.ERROR

    def test_verdict_error_no_tests(self, empty_test_result):
        """Test ERROR verdict when no tests collected."""
        assert empty_test_result.verdict == Verdict.ERROR


class TestTestResultToDict:
    """Tests for TestResult.to_dict() method."""

    def test_to_dict_includes_verdict(self, passing_test_result):
        """Test that to_dict includes verdict."""
        d = passing_test_result.to_dict()
        assert d["verdict"] == "PASS"

    def test_to_dict_includes_all_counts(self, failing_test_result):
        """Test that to_dict includes all counts."""
        d = failing_test_result.to_dict()
        assert d["passed"] == 8
        assert d["failed"] == 2
        assert d["errors"] == 0
        assert d["skipped"] == 1
        assert d["total"] == 11

    def test_to_dict_includes_timestamp(self, passing_test_result):
        """Test that to_dict includes timestamp."""
        d = passing_test_result.to_dict()
        assert "timestamp" in d
        assert d["timestamp"].endswith("Z")

    def test_to_dict_uses_duration_seconds(self, passing_test_result):
        """Test that to_dict uses duration_seconds (not duration) for consistency."""
        d = passing_test_result.to_dict()
        assert "duration_seconds" in d
        assert d["duration_seconds"] == 5.5
        # The internal attribute is still .duration, but serialized key is duration_seconds
        assert passing_test_result.duration == 5.5


class TestTestResultToEvaluation:
    """Tests for TestResult.to_evaluation() conversion."""

    def test_to_evaluation_basic_conversion(self, passing_test_result):
        """Test basic conversion to EvaluationResult."""
        eval_result = passing_test_result.to_evaluation(
            adapter_type="pytest",
            project_name="test-project",
        )
        eval_result.finalize()

        assert eval_result.metadata.adapter_type == "pytest"
        assert eval_result.metadata.project_name == "test-project"
        assert eval_result.verdict == Verdict.PASS

    def test_to_evaluation_failing_result(self, failing_test_result):
        """Test conversion of failing TestResult."""
        eval_result = failing_test_result.to_evaluation(
            adapter_type="pytest",
        )
        eval_result.finalize()

        assert eval_result.verdict == Verdict.FAIL
        assert eval_result.exit_code == 1

    def test_to_evaluation_creates_session(self, passing_test_result):
        """Test that conversion creates a session."""
        eval_result = passing_test_result.to_evaluation()
        eval_result.finalize()

        assert len(eval_result.sessions) == 1
        session = eval_result.sessions[0]
        assert len(session.metrics) >= 2  # At least passed and failed metrics

    def test_to_evaluation_captures_test_counts(self, passing_test_result):
        """Test that metrics capture test counts."""
        eval_result = passing_test_result.to_evaluation()
        eval_result.finalize()

        session = eval_result.sessions[0]
        metric_names = [m.name for m in session.metrics]

        assert "tests_passed" in metric_names
        assert "tests_failed" in metric_names
        assert "tests_errors" in metric_names

    def test_to_evaluation_metrics_pass_correctly(self, passing_test_result):
        """Test that metrics have correct pass status."""
        eval_result = passing_test_result.to_evaluation()
        eval_result.finalize()

        session = eval_result.sessions[0]

        # Find specific metrics
        passed_metric = next(m for m in session.metrics if m.name == "tests_passed")
        failed_metric = next(m for m in session.metrics if m.name == "tests_failed")

        assert passed_metric.value == 10
        assert passed_metric.passed is True
        assert failed_metric.value == 0
        assert failed_metric.passed is True

    def test_to_evaluation_failing_metrics(self, failing_test_result):
        """Test that failing tests create failing metrics."""
        eval_result = failing_test_result.to_evaluation()
        eval_result.finalize()

        session = eval_result.sessions[0]
        failed_metric = next(m for m in session.metrics if m.name == "tests_failed")

        assert failed_metric.value == 2
        assert failed_metric.passed is False  # 2 > 0 means condition fails

    def test_to_evaluation_captures_failures_metadata(self, failing_test_result):
        """Test that failures are captured in session metadata."""
        eval_result = failing_test_result.to_evaluation()
        eval_result.finalize()

        session = eval_result.sessions[0]
        assert "failures" in session.metadata
        assert len(session.metadata["failures"]) == 2

    def test_to_evaluation_captures_duration(self, passing_test_result):
        """Test that duration is captured in session."""
        eval_result = passing_test_result.to_evaluation()
        eval_result.finalize()

        # Duration is captured in the session
        session = eval_result.sessions[0]
        assert session.duration_seconds == 5.5

        # Metadata duration_seconds is set by finalize() based on elapsed time
        # but the TestResult duration is preserved in the session
        assert eval_result.summary["total_duration_seconds"] == 5.5

    def test_to_evaluation_json_serializable(self, passing_test_result):
        """Test that converted result is JSON serializable."""
        eval_result = passing_test_result.to_evaluation(
            adapter_type="pytest",
            project_name="test-project",
        )
        eval_result.finalize()

        # Should not raise
        json_str = eval_result.to_json()
        data = json.loads(json_str)

        assert data["verdict"] == "PASS"
        assert data["metadata"]["adapter_type"] == "pytest"
        assert data["metadata"]["schema_version"] == SCHEMA_VERSION

    def test_to_evaluation_with_coverage(self):
        """Test conversion with coverage data."""
        result = TestResult(
            passed=10,
            failed=0,
            errors=0,
            skipped=0,
            duration=5.0,
            coverage_percent=85.5,
        )

        eval_result = result.to_evaluation()
        eval_result.finalize()

        session = eval_result.sessions[0]
        coverage_metric = next(
            (m for m in session.metrics if m.name == "coverage_percent"),
            None
        )

        assert coverage_metric is not None
        assert coverage_metric.value == 85.5
        assert coverage_metric.severity == "info"

    def test_to_evaluation_error_result(self, error_test_result):
        """Test conversion of error TestResult."""
        eval_result = error_test_result.to_evaluation()
        eval_result.finalize()

        # The session should have a failing metric for errors
        session = eval_result.sessions[0]
        errors_metric = next(m for m in session.metrics if m.name == "tests_errors")

        assert errors_metric.value == 1
        assert errors_metric.passed is False


class TestTestResultTotal:
    """Tests for TestResult total calculation."""

    def test_total_auto_calculated(self):
        """Test that total is auto-calculated if not provided."""
        result = TestResult(
            passed=5,
            failed=2,
            errors=1,
            skipped=3,
            duration=1.0,
        )
        assert result.total == 11

    def test_total_preserved_if_provided(self):
        """Test that total is preserved if explicitly provided."""
        result = TestResult(
            passed=5,
            failed=2,
            errors=1,
            skipped=3,
            duration=1.0,
            total=100,  # explicit override
        )
        assert result.total == 100

    def test_total_zero_preserved_if_explicit(self):
        """Test that total=0 is preserved when explicitly provided.

        This is important for 'no tests collected' scenarios where
        total=0 is a valid, meaningful value that should not be
        overwritten by the sum of counts.
        """
        result = TestResult(
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            duration=0.0,
            total=0,  # explicit zero - should NOT be overwritten
        )
        assert result.total == 0
