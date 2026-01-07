"""Tests for retry utilities with exponential backoff.

Covers:
- RetryConfig dataclass initialization and calculate_delay() method
- retry_with_backoff decorator (success, failure, max retries, exception filtering)
- retry_on_condition decorator (condition checking, retries, final return)
- execute_with_retry function (functional retry logic)
- Edge cases (max_delay=0, max_attempts=0, custom exceptions, etc.)
"""

import logging
import time
from unittest.mock import MagicMock, Mock, patch

import pytest

from systemeval.utils.retry import (
    RetryConfig,
    execute_with_retry,
    retry_on_condition,
    retry_with_backoff,
)


class TestRetryConfig:
    """Tests for RetryConfig dataclass."""

    def test_retry_config_default_values(self):
        """Test RetryConfig initializes with correct defaults."""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.initial_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
        assert config.exceptions == (Exception,)

    def test_retry_config_custom_values(self):
        """Test RetryConfig accepts custom values."""
        config = RetryConfig(
            max_attempts=5,
            initial_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
            exceptions=(ValueError, TypeError),
        )

        assert config.max_attempts == 5
        assert config.initial_delay == 0.5
        assert config.max_delay == 30.0
        assert config.exponential_base == 3.0
        assert config.exceptions == (ValueError, TypeError)

    def test_retry_config_single_exception(self):
        """Test RetryConfig with single exception type."""
        config = RetryConfig(exceptions=(ConnectionError,))

        assert config.exceptions == (ConnectionError,)

    def test_retry_config_multiple_exceptions(self):
        """Test RetryConfig with multiple exception types."""
        config = RetryConfig(
            exceptions=(ValueError, TypeError, RuntimeError, OSError)
        )

        assert len(config.exceptions) == 4
        assert ValueError in config.exceptions
        assert OSError in config.exceptions


class TestRetryConfigCalculateDelay:
    """Tests for RetryConfig.calculate_delay() method."""

    def test_calculate_delay_attempt_zero(self):
        """Test delay calculation for first attempt (attempt 0)."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0)

        delay = config.calculate_delay(0)

        # 1.0 * (2.0 ** 0) = 1.0
        assert delay == 1.0

    def test_calculate_delay_attempt_one(self):
        """Test delay calculation for second attempt (attempt 1)."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0)

        delay = config.calculate_delay(1)

        # 1.0 * (2.0 ** 1) = 2.0
        assert delay == 2.0

    def test_calculate_delay_attempt_two(self):
        """Test delay calculation for third attempt (attempt 2)."""
        config = RetryConfig(initial_delay=1.0, exponential_base=2.0)

        delay = config.calculate_delay(2)

        # 1.0 * (2.0 ** 2) = 4.0
        assert delay == 4.0

    def test_calculate_delay_exponential_growth(self):
        """Test delay grows exponentially with attempts."""
        config = RetryConfig(initial_delay=0.5, exponential_base=2.0, max_delay=1000.0)

        delays = [config.calculate_delay(i) for i in range(5)]

        # 0.5, 1.0, 2.0, 4.0, 8.0
        assert delays == [0.5, 1.0, 2.0, 4.0, 8.0]

    def test_calculate_delay_respects_max_delay(self):
        """Test delay is capped at max_delay."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=5.0,
        )

        # At attempt 3: 1.0 * 2^3 = 8.0, but capped at 5.0
        delay = config.calculate_delay(3)

        assert delay == 5.0

    def test_calculate_delay_max_delay_capping(self):
        """Test delay capping behavior across multiple attempts."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=4.0,
        )

        delays = [config.calculate_delay(i) for i in range(5)]

        # 1.0, 2.0, 4.0, 4.0, 4.0 (capped)
        assert delays == [1.0, 2.0, 4.0, 4.0, 4.0]

    def test_calculate_delay_custom_base(self):
        """Test delay calculation with custom exponential base."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=3.0,
            max_delay=100.0,
        )

        delays = [config.calculate_delay(i) for i in range(4)]

        # 1.0, 3.0, 9.0, 27.0
        assert delays == [1.0, 3.0, 9.0, 27.0]

    def test_calculate_delay_fractional_base(self):
        """Test delay calculation with fractional exponential base."""
        config = RetryConfig(
            initial_delay=2.0,
            exponential_base=1.5,
            max_delay=100.0,
        )

        delay_0 = config.calculate_delay(0)
        delay_1 = config.calculate_delay(1)
        delay_2 = config.calculate_delay(2)

        assert delay_0 == 2.0
        assert delay_1 == 3.0  # 2.0 * 1.5
        assert delay_2 == 4.5  # 2.0 * 2.25

    def test_calculate_delay_zero_initial(self):
        """Test delay calculation with zero initial delay."""
        config = RetryConfig(initial_delay=0.0, exponential_base=2.0)

        delay = config.calculate_delay(5)

        # 0.0 * anything = 0.0
        assert delay == 0.0

    def test_calculate_delay_zero_max(self):
        """Test delay is capped at zero when max_delay is zero."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=0.0,
        )

        delay = config.calculate_delay(0)

        assert delay == 0.0

    def test_calculate_delay_large_attempt_number(self):
        """Test delay calculation with large attempt number."""
        config = RetryConfig(
            initial_delay=1.0,
            exponential_base=2.0,
            max_delay=60.0,
        )

        # Very large attempt should be capped at max_delay
        delay = config.calculate_delay(100)

        assert delay == 60.0


class TestRetryWithBackoffDecorator:
    """Tests for retry_with_backoff decorator."""

    def test_retry_with_backoff_success_first_attempt(self):
        """Test function succeeds on first attempt without retry."""
        call_count = [0]

        @retry_with_backoff(max_attempts=3)
        def successful_func():
            call_count[0] += 1
            return "success"

        result = successful_func()

        assert result == "success"
        assert call_count[0] == 1

    def test_retry_with_backoff_success_after_retries(self):
        """Test function succeeds after some retries."""
        call_count = [0]

        @retry_with_backoff(max_attempts=5, initial_delay=0.01)
        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not ready yet")
            return "success"

        with patch("time.sleep"):
            result = flaky_func()

        assert result == "success"
        assert call_count[0] == 3

    def test_retry_with_backoff_max_retries_exceeded(self):
        """Test exception raised after max retries exceeded."""
        call_count = [0]

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def always_fails():
            call_count[0] += 1
            raise RuntimeError("Always fails")

        with patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                always_fails()

        assert "Always fails" in str(exc_info.value)
        assert call_count[0] == 3

    def test_retry_with_backoff_respects_exception_filter(self):
        """Test only specified exceptions trigger retries."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=5,
            exceptions=(ValueError,),
            initial_delay=0.01,
        )
        def raises_type_error():
            call_count[0] += 1
            raise TypeError("Not a ValueError")

        # TypeError should not be caught, so it propagates immediately
        with pytest.raises(TypeError):
            raises_type_error()

        assert call_count[0] == 1  # Only one call, no retries

    def test_retry_with_backoff_catches_specified_exception(self):
        """Test specified exceptions are caught and retried."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=3,
            exceptions=(ConnectionError, TimeoutError),
            initial_delay=0.01,
        )
        def network_operation():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ConnectionError("Connection failed")
            return "connected"

        with patch("time.sleep"):
            result = network_operation()

        assert result == "connected"
        assert call_count[0] == 3

    def test_retry_with_backoff_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        @retry_with_backoff()
        def documented_function():
            """This is a docstring."""
            return True

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a docstring."

    def test_retry_with_backoff_passes_args(self):
        """Test arguments are passed to decorated function."""
        received_args = []

        @retry_with_backoff(max_attempts=1)
        def func_with_args(a, b, c=None):
            received_args.append((a, b, c))
            return a + b

        result = func_with_args(1, 2, c=3)

        assert result == 3
        assert received_args == [(1, 2, 3)]

    def test_retry_with_backoff_passes_kwargs(self):
        """Test keyword arguments are passed to decorated function."""

        @retry_with_backoff(max_attempts=1)
        def func_with_kwargs(**kwargs):
            return kwargs

        result = func_with_kwargs(name="test", value=42)

        assert result == {"name": "test", "value": 42}

    def test_retry_with_backoff_calls_time_sleep(self):
        """Test decorator calls time.sleep with correct delays."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=4,
            initial_delay=1.0,
            exponential_base=2.0,
        )
        def always_fails():
            call_count[0] += 1
            raise ValueError("Failed")

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(ValueError):
                always_fails()

        # Should sleep 3 times (between attempts 1-2, 2-3, 3-4)
        assert mock_sleep.call_count == 3
        # Delays: 1.0, 2.0, 4.0
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)
        mock_sleep.assert_any_call(4.0)

    def test_retry_with_backoff_uses_custom_logger(self):
        """Test decorator uses custom logger when provided."""
        custom_logger = MagicMock(spec=logging.Logger)
        call_count = [0]

        @retry_with_backoff(
            max_attempts=2,
            initial_delay=0.01,
            logger_instance=custom_logger,
        )
        def fails_once():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("First failure")
            return "success"

        with patch("time.sleep"):
            result = fails_once()

        assert result == "success"
        assert custom_logger.warning.called

    def test_retry_with_backoff_logs_error_on_final_failure(self):
        """Test decorator logs error when all retries exhausted."""
        custom_logger = MagicMock(spec=logging.Logger)

        @retry_with_backoff(
            max_attempts=2,
            initial_delay=0.01,
            logger_instance=custom_logger,
        )
        def always_fails():
            raise ValueError("Permanent failure")

        with patch("time.sleep"):
            with pytest.raises(ValueError):
                always_fails()

        assert custom_logger.error.called
        error_message = str(custom_logger.error.call_args)
        assert "failed after 2 attempts" in error_message

    def test_retry_with_backoff_respects_max_delay(self):
        """Test decorator respects max_delay setting."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=5,
            initial_delay=10.0,
            max_delay=15.0,
            exponential_base=2.0,
        )
        def always_fails():
            call_count[0] += 1
            raise ValueError("Failed")

        sleep_values = []
        with patch("time.sleep", side_effect=lambda x: sleep_values.append(x)):
            with pytest.raises(ValueError):
                always_fails()

        # All delays should be capped at 15.0
        for delay in sleep_values:
            assert delay <= 15.0

    def test_retry_with_backoff_single_attempt(self):
        """Test decorator with max_attempts=1 (no retries)."""

        @retry_with_backoff(max_attempts=1)
        def fails():
            raise ValueError("No retries")

        with pytest.raises(ValueError) as exc_info:
            fails()

        assert "No retries" in str(exc_info.value)


class TestRetryOnConditionDecorator:
    """Tests for retry_on_condition decorator."""

    def test_retry_on_condition_success_first_attempt(self):
        """Test function returns immediately when condition not met."""
        call_count = [0]

        # Condition: retry when result is None
        @retry_on_condition(
            condition=lambda x: x is None,
            max_attempts=5,
        )
        def returns_value():
            call_count[0] += 1
            return "value"

        result = returns_value()

        assert result == "value"
        assert call_count[0] == 1

    def test_retry_on_condition_retries_when_condition_met(self):
        """Test function retries when condition is met."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: x < 3,
            max_attempts=5,
            initial_delay=0.01,
        )
        def incrementing_func():
            call_count[0] += 1
            return call_count[0]

        with patch("time.sleep"):
            result = incrementing_func()

        assert result == 3
        assert call_count[0] == 3

    def test_retry_on_condition_returns_last_value_on_exhaustion(self):
        """Test function returns last value when max attempts reached."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: True,  # Always retry
            max_attempts=3,
            initial_delay=0.01,
        )
        def always_triggers_retry():
            call_count[0] += 1
            return f"attempt_{call_count[0]}"

        with patch("time.sleep"):
            result = always_triggers_retry()

        assert result == "attempt_3"
        assert call_count[0] == 3

    def test_retry_on_condition_with_none_check(self):
        """Test retry on condition checking for None return."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: x is None,
            max_attempts=4,
            initial_delay=0.01,
        )
        def returns_none_then_value():
            call_count[0] += 1
            if call_count[0] < 3:
                return None
            return "found"

        with patch("time.sleep"):
            result = returns_none_then_value()

        assert result == "found"
        assert call_count[0] == 3

    def test_retry_on_condition_with_empty_list_check(self):
        """Test retry on condition checking for empty list."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: len(x) == 0,
            max_attempts=4,
            initial_delay=0.01,
        )
        def returns_list():
            call_count[0] += 1
            if call_count[0] < 2:
                return []
            return ["item1", "item2"]

        with patch("time.sleep"):
            result = returns_list()

        assert result == ["item1", "item2"]
        assert call_count[0] == 2

    def test_retry_on_condition_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        @retry_on_condition(condition=lambda x: False)
        def documented_function():
            """This is documentation."""
            return True

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is documentation."

    def test_retry_on_condition_passes_args(self):
        """Test arguments are passed to decorated function."""

        @retry_on_condition(condition=lambda x: False, max_attempts=1)
        def func_with_args(a, b):
            return a * b

        result = func_with_args(3, 4)

        assert result == 12

    def test_retry_on_condition_passes_kwargs(self):
        """Test keyword arguments are passed to decorated function."""

        @retry_on_condition(condition=lambda x: False, max_attempts=1)
        def func_with_kwargs(multiplier=1, value=0):
            return multiplier * value

        result = func_with_kwargs(multiplier=5, value=10)

        assert result == 50

    def test_retry_on_condition_calls_time_sleep(self):
        """Test decorator calls time.sleep with correct delays."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: True,  # Always retry
            max_attempts=4,
            initial_delay=1.0,
            exponential_base=2.0,
        )
        def always_retries():
            call_count[0] += 1
            return call_count[0]

        with patch("time.sleep") as mock_sleep:
            always_retries()

        # Should sleep 3 times (between attempts)
        assert mock_sleep.call_count == 3

    def test_retry_on_condition_uses_custom_logger(self):
        """Test decorator uses custom logger when provided."""
        custom_logger = MagicMock(spec=logging.Logger)

        @retry_on_condition(
            condition=lambda x: True,
            max_attempts=2,
            initial_delay=0.01,
            logger_instance=custom_logger,
        )
        def retries():
            return None

        with patch("time.sleep"):
            retries()

        # Logger should be used for debug and warning messages
        assert custom_logger.debug.called or custom_logger.warning.called

    def test_retry_on_condition_logs_warning_on_exhaustion(self):
        """Test decorator logs warning when max attempts reached."""
        custom_logger = MagicMock(spec=logging.Logger)

        @retry_on_condition(
            condition=lambda x: True,
            max_attempts=2,
            initial_delay=0.01,
            logger_instance=custom_logger,
        )
        def always_retries():
            return "value"

        with patch("time.sleep"):
            always_retries()

        assert custom_logger.warning.called
        warning_message = str(custom_logger.warning.call_args)
        assert "not met after 2 attempts" in warning_message

    def test_retry_on_condition_complex_condition(self):
        """Test decorator with complex condition logic."""
        call_count = [0]
        results = [
            {"status": "pending", "data": None},
            {"status": "pending", "data": None},
            {"status": "complete", "data": [1, 2, 3]},
        ]

        @retry_on_condition(
            condition=lambda x: x["status"] != "complete",
            max_attempts=5,
            initial_delay=0.01,
        )
        def check_status():
            call_count[0] += 1
            return results[call_count[0] - 1]

        with patch("time.sleep"):
            result = check_status()

        assert result["status"] == "complete"
        assert result["data"] == [1, 2, 3]


class TestExecuteWithRetry:
    """Tests for execute_with_retry function."""

    def test_execute_with_retry_success_first_attempt(self):
        """Test function succeeds on first attempt."""
        def successful_func():
            return "success"

        result = execute_with_retry(successful_func)

        assert result == "success"

    def test_execute_with_retry_success_after_retries(self):
        """Test function succeeds after some retries."""
        call_count = [0]

        def flaky_func():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not ready")
            return "ready"

        config = RetryConfig(max_attempts=3, initial_delay=0.01)

        with patch("time.sleep"):
            result = execute_with_retry(flaky_func, config)

        assert result == "ready"
        assert call_count[0] == 2

    def test_execute_with_retry_max_retries_exceeded(self):
        """Test exception raised after max retries exceeded."""
        call_count = [0]

        def always_fails():
            call_count[0] += 1
            raise RuntimeError("Permanent failure")

        config = RetryConfig(max_attempts=3, initial_delay=0.01)

        with patch("time.sleep"):
            with pytest.raises(RuntimeError) as exc_info:
                execute_with_retry(always_fails, config)

        assert "Permanent failure" in str(exc_info.value)
        assert call_count[0] == 3

    def test_execute_with_retry_uses_default_config(self):
        """Test function uses default RetryConfig when none provided."""
        call_count = [0]

        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not yet")
            return "done"

        with patch("time.sleep"):
            result = execute_with_retry(fails_twice)

        assert result == "done"
        assert call_count[0] == 3

    def test_execute_with_retry_respects_exception_filter(self):
        """Test only specified exceptions trigger retries."""
        call_count = [0]

        def raises_key_error():
            call_count[0] += 1
            raise KeyError("Not found")

        config = RetryConfig(
            max_attempts=5,
            exceptions=(ValueError,),
            initial_delay=0.01,
        )

        with pytest.raises(KeyError):
            execute_with_retry(raises_key_error, config)

        assert call_count[0] == 1  # Only one call, no retries

    def test_execute_with_retry_passes_args(self):
        """Test positional arguments are passed to function via *args."""
        # Note: The execute_with_retry signature is:
        # execute_with_retry(func, config, logger_instance, *args, **kwargs)
        # So args must come after logger_instance

        def add(a, b):
            return a + b

        result = execute_with_retry(add, None, None, 5, 3)

        assert result == 8

    def test_execute_with_retry_passes_kwargs(self):
        """Test keyword arguments are passed to function."""

        def multiply(x=1, y=1):
            return x * y

        result = execute_with_retry(multiply, None, x=4, y=5)

        assert result == 20

    def test_execute_with_retry_passes_args_and_kwargs(self):
        """Test both args and kwargs are passed to function."""

        def func(a, b, c=10):
            return a + b + c

        # Pass None for config and logger_instance, then positional args, then kwargs
        result = execute_with_retry(func, None, None, 1, 2, c=3)

        assert result == 6

    def test_execute_with_retry_uses_custom_logger(self):
        """Test function uses custom logger when provided."""
        custom_logger = MagicMock(spec=logging.Logger)
        call_count = [0]

        def fails_once():
            call_count[0] += 1
            if call_count[0] == 1:
                raise ValueError("First failure")
            return "success"

        config = RetryConfig(max_attempts=3, initial_delay=0.01)

        with patch("time.sleep"):
            result = execute_with_retry(fails_once, config, logger_instance=custom_logger)

        assert result == "success"
        assert custom_logger.warning.called

    def test_execute_with_retry_logs_error_on_final_failure(self):
        """Test function logs error when all retries exhausted."""
        custom_logger = MagicMock(spec=logging.Logger)

        def always_fails():
            raise ValueError("Always fails")

        config = RetryConfig(max_attempts=2, initial_delay=0.01)

        with patch("time.sleep"):
            with pytest.raises(ValueError):
                execute_with_retry(always_fails, config, logger_instance=custom_logger)

        assert custom_logger.error.called

    def test_execute_with_retry_calls_time_sleep(self):
        """Test function calls time.sleep with correct delays."""
        call_count = [0]

        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not ready")
            return "done"

        config = RetryConfig(
            max_attempts=5,
            initial_delay=1.0,
            exponential_base=2.0,
        )

        with patch("time.sleep") as mock_sleep:
            execute_with_retry(fails_twice, config)

        # Should sleep 2 times
        assert mock_sleep.call_count == 2
        mock_sleep.assert_any_call(1.0)
        mock_sleep.assert_any_call(2.0)


class TestRetryEdgeCases:
    """Edge case tests for retry utilities."""

    def test_retry_config_max_attempts_zero(self):
        """Test RetryConfig with max_attempts=0 results in no calls."""
        config = RetryConfig(max_attempts=0)
        call_count = [0]

        def func():
            call_count[0] += 1
            return "done"

        # With 0 max_attempts, the loop never executes
        result = execute_with_retry(func, config)

        # When max_attempts=0, loop doesn't execute, last_exception is None
        # and function returns None (no execution)
        assert call_count[0] == 0

    def test_retry_config_max_attempts_one(self):
        """Test RetryConfig with max_attempts=1 (single attempt, no retry)."""
        config = RetryConfig(max_attempts=1)
        call_count = [0]

        def fails():
            call_count[0] += 1
            raise ValueError("Single attempt failure")

        with pytest.raises(ValueError):
            execute_with_retry(fails, config)

        assert call_count[0] == 1

    def test_retry_with_lambda_function(self):
        """Test retry works with lambda functions."""
        call_count = [0]

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def wrapper():
            call_count[0] += 1
            func = lambda: "success" if call_count[0] >= 2 else None
            result = func()
            if result is None:
                raise ValueError("Not ready")
            return result

        with patch("time.sleep"):
            result = wrapper()

        assert result == "success"

    def test_retry_preserves_exception_chain(self):
        """Test retry preserves the original exception."""

        @retry_with_backoff(max_attempts=1)
        def raises_with_cause():
            try:
                raise KeyError("original")
            except KeyError as e:
                raise ValueError("wrapped") from e

        with pytest.raises(ValueError) as exc_info:
            raises_with_cause()

        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, KeyError)

    def test_retry_with_exception_subclass(self):
        """Test retry catches exception subclasses."""

        class CustomError(ValueError):
            pass

        call_count = [0]

        @retry_with_backoff(
            max_attempts=3,
            exceptions=(ValueError,),  # Should catch CustomError too
            initial_delay=0.01,
        )
        def raises_custom():
            call_count[0] += 1
            if call_count[0] < 2:
                raise CustomError("Custom error")
            return "success"

        with patch("time.sleep"):
            result = raises_custom()

        assert result == "success"
        assert call_count[0] == 2

    def test_retry_on_condition_with_exception_in_condition(self):
        """Test behavior when condition function raises exception."""

        def bad_condition(x):
            raise RuntimeError("Condition failed")

        @retry_on_condition(condition=bad_condition, max_attempts=3)
        def returns_value():
            return "value"

        # Exception in condition should propagate
        with pytest.raises(RuntimeError) as exc_info:
            returns_value()

        assert "Condition failed" in str(exc_info.value)

    def test_retry_with_very_small_delay(self):
        """Test retry with very small delay values."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=0.0001,
            max_delay=0.001,
        )
        def fails_then_succeeds():
            call_count[0] += 1
            if call_count[0] < 2:
                raise ValueError("Not yet")
            return "done"

        with patch("time.sleep") as mock_sleep:
            result = fails_then_succeeds()

        assert result == "done"
        # Verify sleep was called with small values
        for call in mock_sleep.call_args_list:
            assert call[0][0] <= 0.001

    def test_retry_with_large_max_attempts(self):
        """Test retry with large max_attempts value."""
        call_count = [0]
        target_attempts = 50

        @retry_with_backoff(
            max_attempts=100,
            initial_delay=0.001,
            max_delay=0.001,
        )
        def succeeds_at_50():
            call_count[0] += 1
            if call_count[0] < target_attempts:
                raise ValueError("Not yet")
            return "success"

        with patch("time.sleep"):
            result = succeeds_at_50()

        assert result == "success"
        assert call_count[0] == target_attempts

    def test_retry_function_with_side_effects(self):
        """Test retry with function that has side effects."""
        side_effects = []

        @retry_with_backoff(max_attempts=3, initial_delay=0.01)
        def function_with_side_effects():
            side_effects.append("called")
            if len(side_effects) < 3:
                raise ValueError("Not ready")
            return "done"

        with patch("time.sleep"):
            result = function_with_side_effects()

        assert result == "done"
        assert side_effects == ["called", "called", "called"]

    def test_execute_with_retry_none_function(self):
        """Test execute_with_retry behavior with function returning None."""

        def returns_none():
            return None

        result = execute_with_retry(returns_none)

        assert result is None

    def test_retry_with_generator_function(self):
        """Test retry with function that returns generator."""

        @retry_with_backoff(max_attempts=1)
        def returns_generator():
            return (x for x in range(3))

        result = returns_generator()

        # Should return the generator object
        assert list(result) == [0, 1, 2]

    def test_retry_on_condition_false_condition(self):
        """Test retry_on_condition with condition always False (never retry)."""
        call_count = [0]

        @retry_on_condition(
            condition=lambda x: False,  # Never retry
            max_attempts=5,
        )
        def func():
            call_count[0] += 1
            return "value"

        result = func()

        assert result == "value"
        assert call_count[0] == 1


class TestRetryIntegration:
    """Integration tests for retry utilities."""

    def test_nested_retry_decorators(self):
        """Test function with multiple retry decorators."""
        inner_count = [0]
        outer_count = [0]

        @retry_with_backoff(max_attempts=2, initial_delay=0.01)
        def outer():
            outer_count[0] += 1

            @retry_with_backoff(max_attempts=2, initial_delay=0.01)
            def inner():
                inner_count[0] += 1
                if inner_count[0] < 2:
                    raise ValueError("Inner not ready")
                return "inner_success"

            with patch("time.sleep"):
                return inner()

        result = outer()

        assert result == "inner_success"

    def test_retry_with_backoff_and_condition_combined(self):
        """Test using both retry decorators in sequence."""
        exception_count = [0]
        condition_count = [0]

        @retry_on_condition(
            condition=lambda x: x == "pending",
            max_attempts=3,
            initial_delay=0.01,
        )
        @retry_with_backoff(max_attempts=2, initial_delay=0.01)
        def complex_operation():
            exception_count[0] += 1
            if exception_count[0] == 1:
                raise ConnectionError("Connection failed")

            condition_count[0] += 1
            if condition_count[0] < 2:
                return "pending"
            return "complete"

        with patch("time.sleep"):
            result = complex_operation()

        assert result == "complete"

    def test_real_time_delays_small(self):
        """Test actual timing with small delays (no mocking)."""
        call_count = [0]

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01,
            exponential_base=2.0,
        )
        def fails_twice():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Not ready")
            return "done"

        start = time.time()
        result = fails_twice()
        elapsed = time.time() - start

        assert result == "done"
        # Should take at least initial_delay + initial_delay*2 = 0.03 seconds
        # (but give some tolerance for test execution)
        assert elapsed >= 0.02

    def test_execute_with_retry_vs_decorator_parity(self):
        """Test execute_with_retry produces same results as decorator."""
        call_count_decorator = [0]
        call_count_function = [0]

        @retry_with_backoff(
            max_attempts=3,
            initial_delay=0.01,
            exceptions=(ValueError,),
        )
        def decorated_func():
            call_count_decorator[0] += 1
            if call_count_decorator[0] < 2:
                raise ValueError("Not ready")
            return "decorator_result"

        def plain_func():
            call_count_function[0] += 1
            if call_count_function[0] < 2:
                raise ValueError("Not ready")
            return "function_result"

        config = RetryConfig(
            max_attempts=3,
            initial_delay=0.01,
            exceptions=(ValueError,),
        )

        with patch("time.sleep"):
            result1 = decorated_func()
            result2 = execute_with_retry(plain_func, config)

        assert result1 == "decorator_result"
        assert result2 == "function_result"
        assert call_count_decorator[0] == call_count_function[0] == 2
