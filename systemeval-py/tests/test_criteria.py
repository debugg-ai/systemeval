"""Tests for the pass/fail criteria library in systemeval.core.criteria."""

import pytest
from systemeval.core.criteria import (
    MetricCriterion,
    # Test execution criteria
    TESTS_PASSED,
    NO_FAILURES,
    NO_ERRORS,
    ALL_TESTS_PASSED,
    # Pass rate criteria
    pass_rate_minimum,
    PASS_RATE_50,
    PASS_RATE_70,
    PASS_RATE_90,
    # Coverage criteria
    coverage_minimum,
    COVERAGE_50,
    COVERAGE_70,
    COVERAGE_80,
    COVERAGE_90,
    # Duration criteria
    duration_within,
    DURATION_WITHIN_1_MIN,
    DURATION_WITHIN_5_MIN,
    DURATION_WITHIN_10_MIN,
    # Error rate criteria
    ERROR_RATE_ZERO,
    error_rate_maximum,
    ERROR_RATE_5,
    ERROR_RATE_10,
    # Preset criteria sets
    UNIT_TEST_CRITERIA,
    INTEGRATION_TEST_CRITERIA,
    E2E_TEST_CRITERIA,
    STRICT_CRITERIA,
    SMOKE_TEST_CRITERIA,
)


class TestMetricCriterion:
    """Tests for the MetricCriterion dataclass."""

    def test_create_criterion(self):
        """Test creating a MetricCriterion instance."""
        criterion = MetricCriterion(
            name="test_criterion",
            evaluator=lambda v: v > 0,
            failure_message="Value {value} must be > 0",
        )

        assert criterion.name == "test_criterion"
        assert criterion.failure_message == "Value {value} must be > 0"
        assert callable(criterion.evaluator)

    def test_evaluate_passing(self):
        """Test evaluate returns (True, None) for passing criterion."""
        criterion = MetricCriterion(
            name="positive",
            evaluator=lambda v: v > 0,
            failure_message="Value {value} is not positive",
        )

        passed, message = criterion.evaluate(10)

        assert passed is True
        assert message is None

    def test_evaluate_failing(self):
        """Test evaluate returns (False, message) for failing criterion."""
        criterion = MetricCriterion(
            name="positive",
            evaluator=lambda v: v > 0,
            failure_message="Value {value} is not positive",
        )

        passed, message = criterion.evaluate(-5)

        assert passed is False
        assert message == "Value -5 is not positive"

    def test_evaluate_handles_type_error(self):
        """Test evaluate handles TypeError gracefully."""
        criterion = MetricCriterion(
            name="numeric",
            evaluator=lambda v: v > 0,
            failure_message="Value {value} comparison failed",
        )

        # Comparing string to int raises TypeError
        passed, message = criterion.evaluate("not a number")

        assert passed is False
        assert "not a number" in message

    def test_evaluate_handles_value_error(self):
        """Test evaluate handles ValueError gracefully."""
        criterion = MetricCriterion(
            name="conversion",
            evaluator=lambda v: int(v) > 0,
            failure_message="Value {value} is invalid",
        )

        # Converting invalid string to int raises ValueError
        passed, message = criterion.evaluate("abc")

        assert passed is False
        assert "abc" in message

    def test_evaluate_handles_attribute_error(self):
        """Test evaluate handles AttributeError gracefully."""
        criterion = MetricCriterion(
            name="attr_check",
            evaluator=lambda v: v.some_attribute > 0,
            failure_message="Value {value} has no attribute",
        )

        passed, message = criterion.evaluate(42)  # int has no some_attribute

        assert passed is False

    def test_failure_message_formatting(self):
        """Test that failure message correctly formats the value placeholder."""
        criterion = MetricCriterion(
            name="test",
            evaluator=lambda v: False,  # Always fail
            failure_message="Got: {value}%",
        )

        _, message = criterion.evaluate(42.5)
        assert message == "Got: 42.5%"

        _, message = criterion.evaluate(None)
        assert message == "Got: None%"

        _, message = criterion.evaluate([1, 2, 3])
        assert message == "Got: [1, 2, 3]%"


class TestTestExecutionCriteria:
    """Tests for test execution criteria constants."""

    class TestTestsPassed:
        """Tests for TESTS_PASSED criterion."""

        def test_passes_with_positive_count(self):
            """Test TESTS_PASSED passes with positive test count."""
            passed, _ = TESTS_PASSED.evaluate(1)
            assert passed is True

            passed, _ = TESTS_PASSED.evaluate(100)
            assert passed is True

        def test_fails_with_zero(self):
            """Test TESTS_PASSED fails with zero tests."""
            passed, message = TESTS_PASSED.evaluate(0)
            assert passed is False
            assert "0" in message
            assert "> 0" in message

        def test_fails_with_none(self):
            """Test TESTS_PASSED fails with None value."""
            passed, message = TESTS_PASSED.evaluate(None)
            assert passed is False
            assert "None" in message

        def test_fails_with_negative(self):
            """Test TESTS_PASSED fails with negative value."""
            passed, message = TESTS_PASSED.evaluate(-1)
            assert passed is False

        def test_criterion_name(self):
            """Test TESTS_PASSED has correct name."""
            assert TESTS_PASSED.name == "tests_passed"

    class TestNoFailures:
        """Tests for NO_FAILURES criterion."""

        def test_passes_with_zero_failures(self):
            """Test NO_FAILURES passes with zero failures."""
            passed, _ = NO_FAILURES.evaluate(0)
            assert passed is True

        def test_fails_with_any_failures(self):
            """Test NO_FAILURES fails with any failures."""
            passed, message = NO_FAILURES.evaluate(1)
            assert passed is False
            assert "1" in message
            assert "0" in message

            passed, _ = NO_FAILURES.evaluate(10)
            assert passed is False

        def test_criterion_name(self):
            """Test NO_FAILURES has correct name."""
            assert NO_FAILURES.name == "tests_failed"

    class TestNoErrors:
        """Tests for NO_ERRORS criterion."""

        def test_passes_with_zero_errors(self):
            """Test NO_ERRORS passes with zero errors."""
            passed, _ = NO_ERRORS.evaluate(0)
            assert passed is True

        def test_fails_with_any_errors(self):
            """Test NO_ERRORS fails with any errors."""
            passed, message = NO_ERRORS.evaluate(1)
            assert passed is False
            assert "errors are system bugs" in message

        def test_criterion_name(self):
            """Test NO_ERRORS has correct name."""
            assert NO_ERRORS.name == "tests_errored"

    class TestAllTestsPassed:
        """Tests for ALL_TESTS_PASSED criterion."""

        def test_passes_with_100_percent_float(self):
            """Test ALL_TESTS_PASSED passes with 100.0."""
            passed, _ = ALL_TESTS_PASSED.evaluate(100.0)
            assert passed is True

        def test_passes_with_100_percent_int(self):
            """Test ALL_TESTS_PASSED passes with 100."""
            passed, _ = ALL_TESTS_PASSED.evaluate(100)
            assert passed is True

        def test_fails_with_99_percent(self):
            """Test ALL_TESTS_PASSED fails with 99%."""
            passed, message = ALL_TESTS_PASSED.evaluate(99)
            assert passed is False
            assert "100%" in message

        def test_fails_with_zero_percent(self):
            """Test ALL_TESTS_PASSED fails with 0%."""
            passed, message = ALL_TESTS_PASSED.evaluate(0)
            assert passed is False

        def test_criterion_name(self):
            """Test ALL_TESTS_PASSED has correct name."""
            assert ALL_TESTS_PASSED.name == "pass_rate"


class TestPassRateCriteria:
    """Tests for pass rate criteria."""

    class TestPassRateMinimum:
        """Tests for pass_rate_minimum factory function."""

        def test_creates_criterion_with_threshold(self):
            """Test pass_rate_minimum creates criterion with correct threshold."""
            criterion = pass_rate_minimum(75.0)

            assert criterion.name == "pass_rate"
            assert ">= 75.0%" in criterion.failure_message

        def test_passes_at_threshold(self):
            """Test criterion passes when exactly at threshold."""
            criterion = pass_rate_minimum(80.0)

            passed, _ = criterion.evaluate(80.0)
            assert passed is True

        def test_passes_above_threshold(self):
            """Test criterion passes when above threshold."""
            criterion = pass_rate_minimum(80.0)

            passed, _ = criterion.evaluate(95.0)
            assert passed is True

        def test_fails_below_threshold(self):
            """Test criterion fails when below threshold."""
            criterion = pass_rate_minimum(80.0)

            passed, message = criterion.evaluate(79.9)
            assert passed is False
            assert "79.9%" in message
            assert ">= 80.0%" in message

        def test_fails_with_none(self):
            """Test criterion fails with None value."""
            criterion = pass_rate_minimum(50.0)

            passed, message = criterion.evaluate(None)
            assert passed is False

    class TestPresetPassRates:
        """Tests for preset pass rate criteria."""

        def test_pass_rate_50(self):
            """Test PASS_RATE_50 threshold."""
            passed, _ = PASS_RATE_50.evaluate(50.0)
            assert passed is True

            passed, _ = PASS_RATE_50.evaluate(49.9)
            assert passed is False

        def test_pass_rate_70(self):
            """Test PASS_RATE_70 threshold."""
            passed, _ = PASS_RATE_70.evaluate(70.0)
            assert passed is True

            passed, _ = PASS_RATE_70.evaluate(69.9)
            assert passed is False

        def test_pass_rate_90(self):
            """Test PASS_RATE_90 threshold."""
            passed, _ = PASS_RATE_90.evaluate(90.0)
            assert passed is True

            passed, _ = PASS_RATE_90.evaluate(89.9)
            assert passed is False


class TestCoverageCriteria:
    """Tests for coverage criteria."""

    class TestCoverageMinimum:
        """Tests for coverage_minimum factory function."""

        def test_creates_criterion_with_threshold(self):
            """Test coverage_minimum creates criterion with correct threshold."""
            criterion = coverage_minimum(85.0)

            assert criterion.name == "coverage"
            assert ">= 85.0%" in criterion.failure_message

        def test_passes_at_threshold(self):
            """Test criterion passes when exactly at threshold."""
            criterion = coverage_minimum(75.0)

            passed, _ = criterion.evaluate(75.0)
            assert passed is True

        def test_passes_above_threshold(self):
            """Test criterion passes when above threshold."""
            criterion = coverage_minimum(75.0)

            passed, _ = criterion.evaluate(100.0)
            assert passed is True

        def test_fails_below_threshold(self):
            """Test criterion fails when below threshold."""
            criterion = coverage_minimum(75.0)

            passed, message = criterion.evaluate(50.0)
            assert passed is False
            assert "50.0%" in message
            assert ">= 75.0%" in message

        def test_fails_with_none(self):
            """Test criterion fails with None value."""
            criterion = coverage_minimum(50.0)

            passed, _ = criterion.evaluate(None)
            assert passed is False

    class TestPresetCoverages:
        """Tests for preset coverage criteria."""

        def test_coverage_50(self):
            """Test COVERAGE_50 threshold."""
            passed, _ = COVERAGE_50.evaluate(50.0)
            assert passed is True

            passed, _ = COVERAGE_50.evaluate(49.9)
            assert passed is False

        def test_coverage_70(self):
            """Test COVERAGE_70 threshold."""
            passed, _ = COVERAGE_70.evaluate(70.0)
            assert passed is True

            passed, _ = COVERAGE_70.evaluate(69.9)
            assert passed is False

        def test_coverage_80(self):
            """Test COVERAGE_80 threshold."""
            passed, _ = COVERAGE_80.evaluate(80.0)
            assert passed is True

            passed, _ = COVERAGE_80.evaluate(79.9)
            assert passed is False

        def test_coverage_90(self):
            """Test COVERAGE_90 threshold."""
            passed, _ = COVERAGE_90.evaluate(90.0)
            assert passed is True

            passed, _ = COVERAGE_90.evaluate(89.9)
            assert passed is False


class TestDurationCriteria:
    """Tests for duration/timeout criteria."""

    class TestDurationWithin:
        """Tests for duration_within factory function."""

        def test_creates_criterion_with_timeout(self):
            """Test duration_within creates criterion with correct timeout."""
            criterion = duration_within(30)

            assert criterion.name == "duration_seconds"
            assert "<= 30s" in criterion.failure_message

        def test_passes_under_timeout(self):
            """Test criterion passes when under timeout."""
            criterion = duration_within(60)

            passed, _ = criterion.evaluate(30)
            assert passed is True

        def test_passes_at_timeout(self):
            """Test criterion passes when exactly at timeout."""
            criterion = duration_within(60)

            passed, _ = criterion.evaluate(60)
            assert passed is True

        def test_fails_over_timeout(self):
            """Test criterion fails when over timeout."""
            criterion = duration_within(60)

            passed, message = criterion.evaluate(61)
            assert passed is False
            assert "61s" in message
            assert "<= 60s" in message

        def test_passes_with_none(self):
            """Test criterion passes with None (no duration recorded)."""
            criterion = duration_within(60)

            passed, _ = criterion.evaluate(None)
            assert passed is True

        def test_handles_float_durations(self):
            """Test criterion handles float duration values."""
            criterion = duration_within(60.5)

            passed, _ = criterion.evaluate(60.5)
            assert passed is True

            passed, _ = criterion.evaluate(60.6)
            assert passed is False

    class TestPresetDurations:
        """Tests for preset duration criteria."""

        def test_duration_within_1_min(self):
            """Test DURATION_WITHIN_1_MIN (60 seconds)."""
            passed, _ = DURATION_WITHIN_1_MIN.evaluate(60)
            assert passed is True

            passed, _ = DURATION_WITHIN_1_MIN.evaluate(61)
            assert passed is False

        def test_duration_within_5_min(self):
            """Test DURATION_WITHIN_5_MIN (300 seconds)."""
            passed, _ = DURATION_WITHIN_5_MIN.evaluate(300)
            assert passed is True

            passed, _ = DURATION_WITHIN_5_MIN.evaluate(301)
            assert passed is False

        def test_duration_within_10_min(self):
            """Test DURATION_WITHIN_10_MIN (600 seconds)."""
            passed, _ = DURATION_WITHIN_10_MIN.evaluate(600)
            assert passed is True

            passed, _ = DURATION_WITHIN_10_MIN.evaluate(601)
            assert passed is False


class TestErrorRateCriteria:
    """Tests for error rate criteria."""

    class TestErrorRateZero:
        """Tests for ERROR_RATE_ZERO criterion."""

        def test_passes_with_zero_int(self):
            """Test ERROR_RATE_ZERO passes with 0."""
            passed, _ = ERROR_RATE_ZERO.evaluate(0)
            assert passed is True

        def test_passes_with_zero_float(self):
            """Test ERROR_RATE_ZERO passes with 0.0."""
            passed, _ = ERROR_RATE_ZERO.evaluate(0.0)
            assert passed is True

        def test_fails_with_any_errors(self):
            """Test ERROR_RATE_ZERO fails with any errors."""
            passed, message = ERROR_RATE_ZERO.evaluate(0.1)
            assert passed is False
            assert "errors are system bugs" in message

            passed, _ = ERROR_RATE_ZERO.evaluate(5)
            assert passed is False

        def test_criterion_name(self):
            """Test ERROR_RATE_ZERO has correct name."""
            assert ERROR_RATE_ZERO.name == "error_rate"

    class TestErrorRateMaximum:
        """Tests for error_rate_maximum factory function."""

        def test_creates_criterion_with_threshold(self):
            """Test error_rate_maximum creates criterion with correct threshold."""
            criterion = error_rate_maximum(10.0)

            assert criterion.name == "error_rate"
            assert "<= 10.0%" in criterion.failure_message

        def test_passes_under_threshold(self):
            """Test criterion passes when under threshold."""
            criterion = error_rate_maximum(5.0)

            passed, _ = criterion.evaluate(3.0)
            assert passed is True

        def test_passes_at_threshold(self):
            """Test criterion passes when at threshold."""
            criterion = error_rate_maximum(5.0)

            passed, _ = criterion.evaluate(5.0)
            assert passed is True

        def test_fails_over_threshold(self):
            """Test criterion fails when over threshold."""
            criterion = error_rate_maximum(5.0)

            passed, message = criterion.evaluate(5.1)
            assert passed is False
            assert "5.1%" in message
            assert "<= 5.0%" in message

        def test_passes_with_none(self):
            """Test criterion passes with None (no error rate recorded)."""
            criterion = error_rate_maximum(5.0)

            passed, _ = criterion.evaluate(None)
            assert passed is True

    class TestPresetErrorRates:
        """Tests for preset error rate criteria."""

        def test_error_rate_5(self):
            """Test ERROR_RATE_5 threshold."""
            passed, _ = ERROR_RATE_5.evaluate(5.0)
            assert passed is True

            passed, _ = ERROR_RATE_5.evaluate(5.1)
            assert passed is False

        def test_error_rate_10(self):
            """Test ERROR_RATE_10 threshold."""
            passed, _ = ERROR_RATE_10.evaluate(10.0)
            assert passed is True

            passed, _ = ERROR_RATE_10.evaluate(10.1)
            assert passed is False


class TestPresetCriteriaSets:
    """Tests for preset criteria sets."""

    def test_unit_test_criteria_contains_expected_criteria(self):
        """Test UNIT_TEST_CRITERIA contains correct criteria."""
        assert len(UNIT_TEST_CRITERIA) == 3
        names = [c.name for c in UNIT_TEST_CRITERIA]
        assert "tests_passed" in names
        assert "tests_errored" in names
        assert "duration_seconds" in names

    def test_unit_test_criteria_uses_1_min_timeout(self):
        """Test UNIT_TEST_CRITERIA uses 1 minute timeout."""
        duration_criterion = next(
            c for c in UNIT_TEST_CRITERIA if c.name == "duration_seconds"
        )
        passed, _ = duration_criterion.evaluate(60)
        assert passed is True

        passed, _ = duration_criterion.evaluate(61)
        assert passed is False

    def test_integration_test_criteria_contains_expected_criteria(self):
        """Test INTEGRATION_TEST_CRITERIA contains correct criteria."""
        assert len(INTEGRATION_TEST_CRITERIA) == 3
        names = [c.name for c in INTEGRATION_TEST_CRITERIA]
        assert "tests_passed" in names
        assert "tests_errored" in names
        assert "duration_seconds" in names

    def test_integration_test_criteria_uses_5_min_timeout(self):
        """Test INTEGRATION_TEST_CRITERIA uses 5 minute timeout."""
        duration_criterion = next(
            c for c in INTEGRATION_TEST_CRITERIA if c.name == "duration_seconds"
        )
        passed, _ = duration_criterion.evaluate(300)
        assert passed is True

        passed, _ = duration_criterion.evaluate(301)
        assert passed is False

    def test_e2e_test_criteria_contains_expected_criteria(self):
        """Test E2E_TEST_CRITERIA contains correct criteria."""
        assert len(E2E_TEST_CRITERIA) == 3
        names = [c.name for c in E2E_TEST_CRITERIA]
        assert "tests_passed" in names
        assert "error_rate" in names
        assert "duration_seconds" in names

    def test_e2e_test_criteria_uses_10_min_timeout(self):
        """Test E2E_TEST_CRITERIA uses 10 minute timeout."""
        duration_criterion = next(
            c for c in E2E_TEST_CRITERIA if c.name == "duration_seconds"
        )
        passed, _ = duration_criterion.evaluate(600)
        assert passed is True

        passed, _ = duration_criterion.evaluate(601)
        assert passed is False

    def test_strict_criteria_contains_expected_criteria(self):
        """Test STRICT_CRITERIA contains correct criteria."""
        assert len(STRICT_CRITERIA) == 3
        names = [c.name for c in STRICT_CRITERIA]
        assert "pass_rate" in names
        assert "tests_errored" in names
        assert "coverage" in names

    def test_strict_criteria_requires_100_percent_pass_rate(self):
        """Test STRICT_CRITERIA requires 100% pass rate."""
        pass_rate_criterion = next(
            c for c in STRICT_CRITERIA if c.name == "pass_rate"
        )
        passed, _ = pass_rate_criterion.evaluate(100)
        assert passed is True

        passed, _ = pass_rate_criterion.evaluate(99)
        assert passed is False

    def test_strict_criteria_requires_80_percent_coverage(self):
        """Test STRICT_CRITERIA requires 80% coverage."""
        coverage_criterion = next(
            c for c in STRICT_CRITERIA if c.name == "coverage"
        )
        passed, _ = coverage_criterion.evaluate(80)
        assert passed is True

        passed, _ = coverage_criterion.evaluate(79)
        assert passed is False

    def test_smoke_test_criteria_contains_expected_criteria(self):
        """Test SMOKE_TEST_CRITERIA contains correct criteria."""
        assert len(SMOKE_TEST_CRITERIA) == 2
        names = [c.name for c in SMOKE_TEST_CRITERIA]
        assert "tests_passed" in names
        assert "tests_errored" in names

    def test_smoke_test_criteria_is_minimal(self):
        """Test SMOKE_TEST_CRITERIA is minimal (no coverage, no duration)."""
        names = [c.name for c in SMOKE_TEST_CRITERIA]
        assert "coverage" not in names
        assert "duration_seconds" not in names


class TestEdgeCases:
    """Tests for edge cases and boundary conditions."""

    def test_zero_threshold_pass_rate(self):
        """Test pass rate with 0% threshold (always passes)."""
        criterion = pass_rate_minimum(0.0)

        passed, _ = criterion.evaluate(0.0)
        assert passed is True

        passed, _ = criterion.evaluate(-1)  # Should still pass >= 0
        assert passed is False  # -1 is not >= 0

    def test_100_threshold_pass_rate(self):
        """Test pass rate with 100% threshold."""
        criterion = pass_rate_minimum(100.0)

        passed, _ = criterion.evaluate(100.0)
        assert passed is True

        passed, _ = criterion.evaluate(99.99)
        assert passed is False

    def test_very_small_duration(self):
        """Test duration criterion with very small timeout."""
        criterion = duration_within(0.001)

        passed, _ = criterion.evaluate(0.001)
        assert passed is True

        passed, _ = criterion.evaluate(0.002)
        assert passed is False

    def test_very_large_duration(self):
        """Test duration criterion with very large timeout."""
        criterion = duration_within(86400)  # 24 hours

        passed, _ = criterion.evaluate(86400)
        assert passed is True

        passed, _ = criterion.evaluate(86401)
        assert passed is False

    def test_negative_value_handling(self):
        """Test criteria handle negative values appropriately."""
        # Pass rate should fail with negative value
        passed, _ = PASS_RATE_50.evaluate(-10)
        assert passed is False

        # Coverage should fail with negative value
        passed, _ = COVERAGE_50.evaluate(-10)
        assert passed is False

        # Duration criterion - negative duration is less than timeout
        passed, _ = DURATION_WITHIN_1_MIN.evaluate(-10)
        assert passed is True

    def test_float_precision_at_boundary(self):
        """Test float precision handling at exact boundaries."""
        criterion = pass_rate_minimum(70.0)

        # These should pass
        passed, _ = criterion.evaluate(70.0)
        assert passed is True

        passed, _ = criterion.evaluate(70.000001)
        assert passed is True

        # This should fail
        passed, _ = criterion.evaluate(69.999999)
        assert passed is False

    def test_boolean_values(self):
        """Test criteria with boolean values (booleans are ints in Python)."""
        # True is 1, False is 0
        passed, _ = TESTS_PASSED.evaluate(True)  # True == 1
        assert passed is True

        passed, _ = TESTS_PASSED.evaluate(False)  # False == 0
        assert passed is False

        passed, _ = NO_FAILURES.evaluate(False)  # False == 0
        assert passed is True

    def test_string_numeric_values(self):
        """Test criteria with string numeric values (should fail gracefully)."""
        # String comparison with number raises TypeError in Python 3
        # The criterion should handle this gracefully and return False
        passed, message = TESTS_PASSED.evaluate("10")
        assert passed is False  # TypeError is caught, returns False
        assert "10" in message

    def test_empty_results_scenario(self):
        """Test criteria behavior for empty test run scenario."""
        # No tests passed
        passed, _ = TESTS_PASSED.evaluate(0)
        assert passed is False

        # No failures (because no tests)
        passed, _ = NO_FAILURES.evaluate(0)
        assert passed is True

        # No errors
        passed, _ = NO_ERRORS.evaluate(0)
        assert passed is True

        # 0% pass rate
        passed, _ = ALL_TESTS_PASSED.evaluate(0)
        assert passed is False

    def test_all_tests_failed_scenario(self):
        """Test criteria behavior when all tests failed."""
        # 0% pass rate
        passed, _ = ALL_TESTS_PASSED.evaluate(0)
        assert passed is False

        passed, _ = PASS_RATE_50.evaluate(0)
        assert passed is False

        # Some failures
        passed, _ = NO_FAILURES.evaluate(10)
        assert passed is False

    def test_all_tests_passed_scenario(self):
        """Test criteria behavior when all tests passed."""
        # 100% pass rate
        passed, _ = ALL_TESTS_PASSED.evaluate(100)
        assert passed is True

        passed, _ = PASS_RATE_90.evaluate(100)
        assert passed is True

        # No failures
        passed, _ = NO_FAILURES.evaluate(0)
        assert passed is True

        # No errors
        passed, _ = NO_ERRORS.evaluate(0)
        assert passed is True


class TestCriterionSemantics:
    """Tests for criterion evaluation semantics and behavior."""

    def test_evaluator_is_lazy(self):
        """Test that evaluator is only called during evaluate()."""
        call_count = 0

        def counting_evaluator(v):
            nonlocal call_count
            call_count += 1
            return v > 0

        criterion = MetricCriterion(
            name="counting",
            evaluator=counting_evaluator,
            failure_message="Failed: {value}",
        )

        # Creating criterion shouldn't call evaluator
        assert call_count == 0

        # Each evaluate should call once
        criterion.evaluate(1)
        assert call_count == 1

        criterion.evaluate(2)
        assert call_count == 2

    def test_evaluator_receives_exact_value(self):
        """Test that evaluator receives the exact value passed."""
        received_values = []

        def capturing_evaluator(v):
            received_values.append(v)
            return True

        criterion = MetricCriterion(
            name="capturing",
            evaluator=capturing_evaluator,
            failure_message="Value: {value}",
        )

        criterion.evaluate(42)
        criterion.evaluate([1, 2, 3])
        criterion.evaluate({"key": "value"})
        criterion.evaluate(None)

        assert received_values == [42, [1, 2, 3], {"key": "value"}, None]

    def test_failure_message_not_evaluated_on_pass(self):
        """Test failure message is not included when criterion passes."""
        criterion = MetricCriterion(
            name="test",
            evaluator=lambda v: True,
            failure_message="This should never appear",
        )

        passed, message = criterion.evaluate("anything")

        assert passed is True
        assert message is None

    def test_criteria_are_immutable_instances(self):
        """Test that preset criteria are stable across evaluations."""
        # Evaluate multiple times
        result1 = TESTS_PASSED.evaluate(10)
        result2 = TESTS_PASSED.evaluate(0)
        result3 = TESTS_PASSED.evaluate(10)

        assert result1[0] is True
        assert result2[0] is False
        assert result3[0] is True

        # Name should be unchanged
        assert TESTS_PASSED.name == "tests_passed"

    def test_factory_functions_create_independent_instances(self):
        """Test that factory functions create independent criterion instances."""
        crit1 = pass_rate_minimum(50.0)
        crit2 = pass_rate_minimum(50.0)
        crit3 = pass_rate_minimum(75.0)

        # Different instances
        assert crit1 is not crit2
        assert crit1 is not crit3

        # But same behavior for same threshold
        assert crit1.evaluate(50)[0] == crit2.evaluate(50)[0]

        # Different threshold means different behavior
        assert crit1.evaluate(60)[0] is True
        assert crit3.evaluate(60)[0] is False
