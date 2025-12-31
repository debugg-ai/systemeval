"""Retry utilities with exponential backoff for transient failures."""

import functools
import logging
import time
from typing import Any, Callable, Optional, Tuple, Type, Union

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        exceptions: Tuple[Type[Exception], ...] = (Exception,),
    ):
        """Initialize retry configuration with backoff parameters."""
        self.max_attempts = max_attempts
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.exceptions = exceptions

    def calculate_delay(self, attempt: int) -> float:
        """Calculate delay for a given attempt using exponential backoff."""
        delay = self.initial_delay * (self.exponential_base ** attempt)
        return min(delay, self.max_delay)


def retry_with_backoff(
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    logger_instance: Optional[logging.Logger] = None,
) -> Callable:
    """Decorator that retries a function with exponential backoff on specified exceptions."""
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
        exceptions=exceptions,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = logger_instance or logger
            last_exception = None

            for attempt in range(config.max_attempts):
                try:
                    return func(*args, **kwargs)
                except config.exceptions as e:
                    last_exception = e

                    if attempt + 1 >= config.max_attempts:
                        # Last attempt failed, raise the exception
                        log.error(
                            f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                        )
                        raise

                    # Calculate delay and retry
                    delay = config.calculate_delay(attempt)
                    log.warning(
                        f"{func.__name__} attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)

            # This shouldn't be reached, but just in case
            if last_exception:
                raise last_exception

        return wrapper

    return decorator


def retry_on_condition(
    condition: Callable[[Any], bool],
    max_attempts: int = 3,
    initial_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    logger_instance: Optional[logging.Logger] = None,
) -> Callable:
    """Decorator that retries a function when a condition is met on the return value."""
    config = RetryConfig(
        max_attempts=max_attempts,
        initial_delay=initial_delay,
        max_delay=max_delay,
        exponential_base=exponential_base,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            log = logger_instance or logger

            for attempt in range(config.max_attempts):
                result = func(*args, **kwargs)

                # Check if retry condition is met
                if not condition(result):
                    return result

                if attempt + 1 >= config.max_attempts:
                    # Last attempt, return whatever we got
                    log.warning(
                        f"{func.__name__} condition not met after {config.max_attempts} attempts"
                    )
                    return result

                # Calculate delay and retry
                delay = config.calculate_delay(attempt)
                log.debug(
                    f"{func.__name__} attempt {attempt + 1}/{config.max_attempts}: "
                    f"condition not met, retrying in {delay:.1f}s..."
                )
                time.sleep(delay)

            return result

        return wrapper

    return decorator


def execute_with_retry(
    func: Callable,
    config: Optional[RetryConfig] = None,
    logger_instance: Optional[logging.Logger] = None,
    *args: Any,
    **kwargs: Any,
) -> Any:
    """Execute a function with retry logic (functional alternative to decorator)."""
    if config is None:
        config = RetryConfig()

    log = logger_instance or logger
    last_exception = None

    for attempt in range(config.max_attempts):
        try:
            return func(*args, **kwargs)
        except config.exceptions as e:
            last_exception = e

            if attempt + 1 >= config.max_attempts:
                log.error(
                    f"{func.__name__} failed after {config.max_attempts} attempts: {e}"
                )
                raise

            delay = config.calculate_delay(attempt)
            log.warning(
                f"{func.__name__} attempt {attempt + 1}/{config.max_attempts} failed: {e}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)

    if last_exception:
        raise last_exception
