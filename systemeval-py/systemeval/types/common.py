"""
Common types used across SystemEval.

This module contains fundamental types like Verdict enum and the generic
Result[T, E] type for error handling.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generic, Optional, TypeVar


class Verdict(str, Enum):
    """Binary verdict - deterministic, no subjective interpretation."""
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


# ============================================================================
# Generic Result Type for Error Handling
# ============================================================================
# A lightweight Result type for standardized error handling.
#
# Design Philosophy:
# - The codebase uses domain-specific Result types (TestResult, ExecutionResult,
#   GenerationResult, etc.) for complex operations with rich metadata.
# - This generic Result type is for simpler success/failure cases where you need
#   to return either a value or an error without raising exceptions.
# - Use domain-specific Result types for operations with complex state.
# - Use this generic Result for simple operations like parsing, validation, etc.
#
# Example usage:
#     from systemeval.types import Result, Ok, Err
#
#     def parse_config(raw: str) -> Result[Config, str]:
#         try:
#             return Ok(Config.parse(raw))
#         except ValueError as e:
#             return Err(f"Invalid config: {e}")
#
#     # Pattern matching
#     result = parse_config(data)
#     if result.is_ok:
#         config = result.value
#     else:
#         print(f"Error: {result.error}")
#
#     # Using unwrap (raises if error)
#     config = parse_config(data).unwrap()
#
#     # Using unwrap_or (default on error)
#     config = parse_config(data).unwrap_or(default_config)
# ============================================================================

T = TypeVar("T")  # Success type
E = TypeVar("E")  # Error type
U = TypeVar("U")  # Mapped type


@dataclass
class Result(Generic[T, E]):
    """
    Generic Result type for explicit error handling.

    Represents either a successful value (Ok) or an error (Err).
    Provides methods for safe value access and transformation.

    Attributes:
        _value: The success value (set when is_ok is True)
        _error: The error value (set when is_ok is False)
        _is_ok: Whether this is a success result

    Note: Use the Ok() and Err() factory functions to create instances.
    """

    _value: Optional[T] = field(default=None, repr=False)
    _error: Optional[E] = field(default=None, repr=False)
    _is_ok: bool = field(default=True, repr=False)

    @property
    def is_ok(self) -> bool:
        """Return True if result is Ok."""
        return self._is_ok

    @property
    def is_err(self) -> bool:
        """Return True if result is Err."""
        return not self._is_ok

    @property
    def value(self) -> T:
        """
        Get the success value.

        Raises:
            ValueError: If result is an error
        """
        if not self._is_ok:
            raise ValueError(f"Cannot get value from Err result: {self._error}")
        return self._value  # type: ignore[return-value]

    @property
    def error(self) -> E:
        """
        Get the error value.

        Raises:
            ValueError: If result is Ok
        """
        if self._is_ok:
            raise ValueError("Cannot get error from Ok result")
        return self._error  # type: ignore[return-value]

    def unwrap(self) -> T:
        """
        Get value or raise exception.

        Raises:
            ValueError: If result is an error, with the error message
        """
        if not self._is_ok:
            raise ValueError(f"Unwrap called on Err: {self._error}")
        return self._value  # type: ignore[return-value]

    def unwrap_or(self, default: T) -> T:
        """Return value if Ok, otherwise return default."""
        return self._value if self._is_ok else default  # type: ignore[return-value]

    def unwrap_or_else(self, f: Callable[[E], T]) -> T:
        """Return value if Ok, otherwise compute from error."""
        if self._is_ok:
            return self._value  # type: ignore[return-value]
        return f(self._error)  # type: ignore[arg-type]

    def map(self, f: Callable[[T], U]) -> "Result[U, E]":
        """Apply function to Ok value, pass through Err."""
        if self._is_ok:
            return Ok(f(self._value))  # type: ignore[arg-type]
        return Err(self._error)  # type: ignore[arg-type]

    def map_err(self, f: Callable[[E], U]) -> "Result[T, U]":
        """Apply function to Err value, pass through Ok."""
        if self._is_ok:
            return Ok(self._value)  # type: ignore[arg-type]
        return Err(f(self._error))  # type: ignore[arg-type]

    def and_then(self, f: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        """Chain operations that return Results (flatMap/bind)."""
        if self._is_ok:
            return f(self._value)  # type: ignore[arg-type]
        return Err(self._error)  # type: ignore[arg-type]

    def __repr__(self) -> str:
        if self._is_ok:
            return f"Ok({self._value!r})"
        return f"Err({self._error!r})"


def Ok(value: T) -> Result[T, Any]:
    """Create a successful Result."""
    return Result(_value=value, _is_ok=True)


def Err(error: E) -> Result[Any, E]:
    """Create an error Result."""
    return Result(_error=error, _is_ok=False)


__all__ = ["Verdict", "Result", "Ok", "Err"]
