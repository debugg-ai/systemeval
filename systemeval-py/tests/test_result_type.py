"""Tests for the generic Result type."""

import pytest

from systemeval.types import Result, Ok, Err


class TestResultOk:
    """Tests for Ok results."""

    def test_ok_is_ok(self):
        """Ok result returns True for is_ok."""
        result = Ok(42)
        assert result.is_ok is True
        assert result.is_err is False

    def test_ok_value(self):
        """Ok result returns value."""
        result = Ok("hello")
        assert result.value == "hello"

    def test_ok_unwrap(self):
        """Ok result unwrap returns value."""
        result = Ok([1, 2, 3])
        assert result.unwrap() == [1, 2, 3]

    def test_ok_error_raises(self):
        """Accessing error on Ok raises ValueError."""
        result = Ok(42)
        with pytest.raises(ValueError, match="Cannot get error from Ok result"):
            _ = result.error

    def test_ok_unwrap_or(self):
        """Ok unwrap_or returns value, not default."""
        result = Ok(42)
        assert result.unwrap_or(0) == 42

    def test_ok_repr(self):
        """Ok has readable repr."""
        result = Ok(42)
        assert repr(result) == "Ok(42)"


class TestResultErr:
    """Tests for Err results."""

    def test_err_is_err(self):
        """Err result returns True for is_err."""
        result = Err("oops")
        assert result.is_err is True
        assert result.is_ok is False

    def test_err_error(self):
        """Err result returns error."""
        result = Err("something went wrong")
        assert result.error == "something went wrong"

    def test_err_value_raises(self):
        """Accessing value on Err raises ValueError."""
        result = Err("error")
        with pytest.raises(ValueError, match="Cannot get value from Err result"):
            _ = result.value

    def test_err_unwrap_raises(self):
        """Err unwrap raises ValueError."""
        result = Err("error message")
        with pytest.raises(ValueError, match="Unwrap called on Err"):
            result.unwrap()

    def test_err_unwrap_or(self):
        """Err unwrap_or returns default."""
        result: Result[int, str] = Err("error")
        assert result.unwrap_or(99) == 99

    def test_err_repr(self):
        """Err has readable repr."""
        result = Err("oops")
        assert repr(result) == "Err('oops')"


class TestResultMap:
    """Tests for Result transformation methods."""

    def test_map_ok(self):
        """Map transforms Ok value."""
        result = Ok(5).map(lambda x: x * 2)
        assert result.is_ok
        assert result.value == 10

    def test_map_err_passes_through(self):
        """Map passes through Err unchanged."""
        result: Result[int, str] = Err("error")
        mapped = result.map(lambda x: x * 2)
        assert mapped.is_err
        assert mapped.error == "error"

    def test_map_err_transforms_error(self):
        """Map_err transforms Err value."""
        result: Result[int, str] = Err("error")
        mapped = result.map_err(lambda e: e.upper())
        assert mapped.is_err
        assert mapped.error == "ERROR"

    def test_map_err_ok_passes_through(self):
        """Map_err passes through Ok unchanged."""
        result = Ok(42).map_err(lambda e: e.upper())
        assert result.is_ok
        assert result.value == 42


class TestResultAndThen:
    """Tests for Result chaining."""

    def test_and_then_ok(self):
        """And_then chains successful operations."""
        def double(x: int) -> Result[int, str]:
            return Ok(x * 2)

        result = Ok(5).and_then(double)
        assert result.is_ok
        assert result.value == 10

    def test_and_then_err_short_circuits(self):
        """And_then short-circuits on Err."""
        def double(x: int) -> Result[int, str]:
            return Ok(x * 2)

        result: Result[int, str] = Err("early error")
        chained = result.and_then(double)
        assert chained.is_err
        assert chained.error == "early error"

    def test_and_then_returns_err(self):
        """And_then propagates Err from chained function."""
        def validate(x: int) -> Result[int, str]:
            if x < 0:
                return Err("negative not allowed")
            return Ok(x)

        result = Ok(-5).and_then(validate)
        assert result.is_err
        assert result.error == "negative not allowed"


class TestResultUnwrapOrElse:
    """Tests for unwrap_or_else."""

    def test_unwrap_or_else_ok(self):
        """Unwrap_or_else returns value for Ok."""
        result = Ok(42)
        value = result.unwrap_or_else(lambda e: 0)
        assert value == 42

    def test_unwrap_or_else_err(self):
        """Unwrap_or_else computes value from error."""
        result: Result[int, str] = Err("error")
        value = result.unwrap_or_else(lambda e: len(e))
        assert value == 5  # len("error")


class TestResultPracticalUsage:
    """Tests demonstrating practical Result usage patterns."""

    def test_parsing_example(self):
        """Example: parsing with Result."""
        def parse_int(s: str) -> Result[int, str]:
            try:
                return Ok(int(s))
            except ValueError:
                return Err(f"Cannot parse '{s}' as integer")

        assert parse_int("42").unwrap() == 42
        assert parse_int("abc").is_err
        assert "Cannot parse" in parse_int("abc").error

    def test_validation_chain(self):
        """Example: chaining validations."""
        def validate_positive(x: int) -> Result[int, str]:
            if x <= 0:
                return Err("must be positive")
            return Ok(x)

        def validate_even(x: int) -> Result[int, str]:
            if x % 2 != 0:
                return Err("must be even")
            return Ok(x)

        result = Ok(4).and_then(validate_positive).and_then(validate_even)
        assert result.is_ok
        assert result.value == 4

        result = Ok(-2).and_then(validate_positive).and_then(validate_even)
        assert result.is_err
        assert result.error == "must be positive"

        result = Ok(3).and_then(validate_positive).and_then(validate_even)
        assert result.is_err
        assert result.error == "must be even"

    def test_default_on_error(self):
        """Example: providing defaults for errors."""
        def get_config(key: str) -> Result[str, str]:
            config = {"host": "localhost", "port": "8080"}
            if key in config:
                return Ok(config[key])
            return Err(f"Key '{key}' not found")

        assert get_config("host").unwrap_or("127.0.0.1") == "localhost"
        assert get_config("missing").unwrap_or("default") == "default"
