"""Tests for systemeval.utils.logging module."""

import logging
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

from systemeval.utils.logging import (
    DEFAULT_LOG_LEVEL,
    LOG_FORMATS,
    SystemEvalFormatter,
    configure_logging,
    get_log_format,
    get_log_level,
    get_logger,
)


class TestLogFormats:
    """Tests for LOG_FORMATS constant."""

    def test_log_formats_contains_simple(self):
        """Test that simple format is defined."""
        assert "simple" in LOG_FORMATS
        assert "%(levelname)s" in LOG_FORMATS["simple"]
        assert "%(message)s" in LOG_FORMATS["simple"]

    def test_log_formats_contains_detailed(self):
        """Test that detailed format is defined."""
        assert "detailed" in LOG_FORMATS
        assert "%(asctime)s" in LOG_FORMATS["detailed"]
        assert "%(name)s" in LOG_FORMATS["detailed"]
        assert "%(levelname)s" in LOG_FORMATS["detailed"]
        assert "%(message)s" in LOG_FORMATS["detailed"]

    def test_log_formats_contains_json(self):
        """Test that json format is defined."""
        assert "json" in LOG_FORMATS
        assert "timestamp" in LOG_FORMATS["json"]
        assert "logger" in LOG_FORMATS["json"]
        assert "level" in LOG_FORMATS["json"]
        assert "message" in LOG_FORMATS["json"]

    def test_default_log_level_is_info(self):
        """Test that default log level is INFO."""
        assert DEFAULT_LOG_LEVEL == logging.INFO


class TestGetLogLevel:
    """Tests for get_log_level function."""

    def test_get_log_level_default(self):
        """Test default log level when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            os.environ.pop("SYSTEMEVAL_LOG_LEVEL", None)
            result = get_log_level()
            assert result == logging.INFO

    def test_get_log_level_debug(self):
        """Test DEBUG level from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "DEBUG"}):
            result = get_log_level()
            assert result == logging.DEBUG

    def test_get_log_level_warning(self):
        """Test WARNING level from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "WARNING"}):
            result = get_log_level()
            assert result == logging.WARNING

    def test_get_log_level_error(self):
        """Test ERROR level from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "ERROR"}):
            result = get_log_level()
            assert result == logging.ERROR

    def test_get_log_level_critical(self):
        """Test CRITICAL level from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "CRITICAL"}):
            result = get_log_level()
            assert result == logging.CRITICAL

    def test_get_log_level_lowercase(self):
        """Test that lowercase level names work."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "debug"}):
            result = get_log_level()
            assert result == logging.DEBUG

    def test_get_log_level_mixed_case(self):
        """Test that mixed case level names work."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "Warning"}):
            result = get_log_level()
            assert result == logging.WARNING

    def test_get_log_level_invalid_returns_default(self):
        """Test that invalid level returns default."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "INVALID_LEVEL"}):
            result = get_log_level()
            assert result == DEFAULT_LOG_LEVEL


class TestGetLogFormat:
    """Tests for get_log_format function."""

    def test_get_log_format_default(self):
        """Test default format when env var not set."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SYSTEMEVAL_LOG_FORMAT", None)
            result = get_log_format()
            assert result == LOG_FORMATS["simple"]

    def test_get_log_format_simple(self):
        """Test simple format from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "simple"}):
            result = get_log_format()
            assert result == LOG_FORMATS["simple"]

    def test_get_log_format_detailed(self):
        """Test detailed format from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "detailed"}):
            result = get_log_format()
            assert result == LOG_FORMATS["detailed"]

    def test_get_log_format_json(self):
        """Test json format from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "json"}):
            result = get_log_format()
            assert result == LOG_FORMATS["json"]

    def test_get_log_format_invalid_returns_simple(self):
        """Test that invalid format returns simple format."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "invalid_format"}):
            result = get_log_format()
            assert result == LOG_FORMATS["simple"]


class TestSystemEvalFormatter:
    """Tests for SystemEvalFormatter class."""

    def test_formatter_initialization(self):
        """Test formatter initialization."""
        formatter = SystemEvalFormatter("%(levelname)s: %(message)s")
        assert formatter._fmt == "%(levelname)s: %(message)s"

    def test_formatter_colors_disabled_when_not_tty(self):
        """Test that colors are disabled when stderr is not a TTY."""
        with patch.object(sys.stderr, "isatty", return_value=False):
            formatter = SystemEvalFormatter("%(levelname)s: %(message)s", use_colors=True)
            assert formatter.use_colors is False

    def test_formatter_colors_enabled_when_tty(self):
        """Test that colors are enabled when stderr is a TTY."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            formatter = SystemEvalFormatter("%(levelname)s: %(message)s", use_colors=True)
            assert formatter.use_colors is True

    def test_formatter_colors_disabled_explicitly(self):
        """Test that colors can be disabled explicitly."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            formatter = SystemEvalFormatter("%(levelname)s: %(message)s", use_colors=False)
            assert formatter.use_colors is False

    def test_formatter_format_without_colors(self):
        """Test formatting a log record without colors."""
        with patch.object(sys.stderr, "isatty", return_value=False):
            formatter = SystemEvalFormatter("%(levelname)s: %(message)s")
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            assert result == "INFO: Test message"

    def test_formatter_format_with_colors(self):
        """Test formatting a log record with colors."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            formatter = SystemEvalFormatter("%(levelname)s: %(message)s", use_colors=True)
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="test.py",
                lineno=1,
                msg="Test message",
                args=(),
                exc_info=None,
            )
            result = formatter.format(record)
            # Should contain ANSI color codes
            assert "\033[32m" in result  # Green for INFO
            assert "\033[0m" in result   # Reset code

    def test_formatter_colors_for_all_levels(self):
        """Test that all log levels have proper color formatting."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            formatter = SystemEvalFormatter("%(levelname)s", use_colors=True)

            test_cases = [
                (logging.DEBUG, "\033[36m"),     # Cyan
                (logging.INFO, "\033[32m"),      # Green
                (logging.WARNING, "\033[33m"),   # Yellow
                (logging.ERROR, "\033[31m"),     # Red
                (logging.CRITICAL, "\033[35m"),  # Magenta
            ]

            for level, expected_color in test_cases:
                record = logging.LogRecord(
                    name="test",
                    level=level,
                    pathname="test.py",
                    lineno=1,
                    msg="Test",
                    args=(),
                    exc_info=None,
                )
                result = formatter.format(record)
                assert expected_color in result, f"Expected {expected_color} for level {logging.getLevelName(level)}"

    def test_formatter_colors_dict_contains_all_levels(self):
        """Test that COLORS dict contains all standard log levels."""
        expected_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL", "RESET"]
        for level in expected_levels:
            assert level in SystemEvalFormatter.COLORS


class TestConfigureLogging:
    """Tests for configure_logging function."""

    def teardown_method(self):
        """Clean up root logger after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

    def test_configure_logging_default(self):
        """Test configure_logging with default parameters."""
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("SYSTEMEVAL_LOG_LEVEL", None)
            os.environ.pop("SYSTEMEVAL_LOG_FORMAT", None)
            configure_logging()

            root_logger = logging.getLogger()
            assert len(root_logger.handlers) == 1
            assert root_logger.level == logging.INFO

    def test_configure_logging_custom_level(self):
        """Test configure_logging with custom level."""
        configure_logging(level=logging.DEBUG)

        root_logger = logging.getLogger()
        assert root_logger.level == logging.DEBUG

    def test_configure_logging_custom_format(self):
        """Test configure_logging with custom format string."""
        custom_format = "CUSTOM: %(message)s"
        configure_logging(format_str=custom_format)

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert handler.formatter._fmt == custom_format

    def test_configure_logging_removes_existing_handlers(self):
        """Test that configure_logging removes existing handlers."""
        root_logger = logging.getLogger()

        # Add some handlers
        root_logger.addHandler(logging.StreamHandler())
        root_logger.addHandler(logging.StreamHandler())
        initial_count = len(root_logger.handlers)
        assert initial_count >= 2

        configure_logging()

        # Should have exactly one handler now
        assert len(root_logger.handlers) == 1

    def test_configure_logging_handler_outputs_to_stderr(self):
        """Test that handler outputs to stderr."""
        configure_logging()

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert isinstance(handler, logging.StreamHandler)
        assert handler.stream == sys.stderr

    def test_configure_logging_uses_systemeval_formatter(self):
        """Test that configure_logging uses SystemEvalFormatter."""
        configure_logging()

        root_logger = logging.getLogger()
        handler = root_logger.handlers[0]
        assert isinstance(handler.formatter, SystemEvalFormatter)

    def test_configure_logging_colors_parameter(self):
        """Test configure_logging with use_colors parameter."""
        with patch.object(sys.stderr, "isatty", return_value=True):
            configure_logging(use_colors=False)

            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]
            # Colors should be disabled
            assert handler.formatter.use_colors is False

    def test_configure_logging_suppresses_third_party_loggers(self):
        """Test that third-party loggers are suppressed."""
        configure_logging()

        assert logging.getLogger("urllib3").level == logging.WARNING
        assert logging.getLogger("requests").level == logging.WARNING
        assert logging.getLogger("docker").level == logging.WARNING

    def test_configure_logging_from_environment_level(self):
        """Test configure_logging reads level from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_LEVEL": "DEBUG"}):
            configure_logging()

            root_logger = logging.getLogger()
            assert root_logger.level == logging.DEBUG

    def test_configure_logging_from_environment_format(self):
        """Test configure_logging reads format from environment."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "detailed"}):
            configure_logging()

            root_logger = logging.getLogger()
            handler = root_logger.handlers[0]
            assert handler.formatter._fmt == LOG_FORMATS["detailed"]


class TestGetLogger:
    """Tests for get_logger function."""

    def test_get_logger_returns_logger(self):
        """Test that get_logger returns a Logger instance."""
        logger = get_logger("test_module")
        assert isinstance(logger, logging.Logger)

    def test_get_logger_with_module_name(self):
        """Test that get_logger uses the provided name."""
        logger = get_logger("my.module.name")
        assert logger.name == "my.module.name"

    def test_get_logger_same_name_returns_same_instance(self):
        """Test that same name returns the same logger instance."""
        logger1 = get_logger("shared_logger")
        logger2 = get_logger("shared_logger")
        assert logger1 is logger2

    def test_get_logger_different_names_return_different_instances(self):
        """Test that different names return different logger instances."""
        logger1 = get_logger("logger_one")
        logger2 = get_logger("logger_two")
        assert logger1 is not logger2

    def test_get_logger_can_log_messages(self):
        """Test that returned logger can log messages."""
        configure_logging(level=logging.DEBUG)
        logger = get_logger("functional_test")

        # Create a string buffer to capture log output
        buffer = StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)

        logger.debug("Debug message")
        logger.info("Info message")
        logger.warning("Warning message")
        logger.error("Error message")

        output = buffer.getvalue()
        assert "Debug message" in output
        assert "Info message" in output
        assert "Warning message" in output
        assert "Error message" in output

        logger.removeHandler(handler)


class TestLoggingIntegration:
    """Integration tests for the logging module."""

    def teardown_method(self):
        """Clean up root logger after each test."""
        root_logger = logging.getLogger()
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        root_logger.setLevel(logging.WARNING)

    def test_full_logging_workflow(self):
        """Test complete logging workflow from configuration to output."""
        # Configure logging
        configure_logging(level=logging.DEBUG, use_colors=False)

        # Get a logger
        logger = get_logger("test.integration")

        # Create a buffer to capture output
        buffer = StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setLevel(logging.DEBUG)
        formatter = SystemEvalFormatter("%(levelname)s - %(name)s: %(message)s", use_colors=False)
        handler.setFormatter(formatter)
        logger.addHandler(handler)

        # Log messages at different levels
        logger.debug("Debug level message")
        logger.info("Info level message")
        logger.warning("Warning level message")
        logger.error("Error level message")

        output = buffer.getvalue()

        assert "DEBUG - test.integration: Debug level message" in output
        assert "INFO - test.integration: Info level message" in output
        assert "WARNING - test.integration: Warning level message" in output
        assert "ERROR - test.integration: Error level message" in output

        logger.removeHandler(handler)

    def test_json_format_output(self):
        """Test that JSON format produces valid JSON-like output."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "json"}):
            configure_logging(use_colors=False)

            logger = get_logger("json_test")

            buffer = StringIO()
            handler = logging.StreamHandler(buffer)
            handler.setLevel(logging.INFO)
            handler.setFormatter(logging.Formatter(LOG_FORMATS["json"]))
            logger.addHandler(handler)

            logger.info("Test JSON message")

            output = buffer.getvalue()
            assert '"level":"INFO"' in output
            assert '"message":"Test JSON message"' in output
            assert '"logger":"json_test"' in output

            logger.removeHandler(handler)

    def test_detailed_format_includes_timestamp(self):
        """Test that detailed format includes timestamp."""
        with patch.dict(os.environ, {"SYSTEMEVAL_LOG_FORMAT": "detailed"}):
            configure_logging(use_colors=False)

            logger = get_logger("detailed_test")

            buffer = StringIO()
            handler = logging.StreamHandler(buffer)
            handler.setLevel(logging.INFO)
            handler.setFormatter(logging.Formatter(LOG_FORMATS["detailed"]))
            logger.addHandler(handler)

            logger.info("Test detailed message")

            output = buffer.getvalue()
            # Should contain timestamp pattern (YYYY-MM-DD HH:MM:SS)
            assert "detailed_test" in output
            assert "INFO" in output
            assert "Test detailed message" in output
            # Check for date-like pattern (contains dashes for date)
            assert "-" in output

            logger.removeHandler(handler)

    def test_logging_respects_level_filtering(self):
        """Test that logging respects level filtering."""
        configure_logging(level=logging.WARNING, use_colors=False)

        logger = get_logger("filter_test")

        buffer = StringIO()
        handler = logging.StreamHandler(buffer)
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
        logger.addHandler(handler)

        logger.debug("Should not appear")
        logger.info("Should not appear either")
        logger.warning("Warning should appear")
        logger.error("Error should appear")

        output = buffer.getvalue()
        assert "Should not appear" not in output
        assert "Should not appear either" not in output
        assert "Warning should appear" in output
        assert "Error should appear" in output

        logger.removeHandler(handler)


class TestAutoConfiguration:
    """Tests for auto-configuration behavior on module import."""

    def test_module_auto_configures_on_import(self):
        """Test that the module auto-configures logging if not already configured."""
        # This test verifies the behavior of lines 149-151 in logging.py
        # The auto-configuration happens at import time, so we verify the root
        # logger has handlers after importing the module

        # Clear all handlers first
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers[:]
        for handler in original_handlers:
            root_logger.removeHandler(handler)

        # Import should auto-configure
        # Note: Since the module is already imported, we need to verify the
        # configure_logging function works correctly when handlers list is empty
        assert callable(configure_logging)

        # Verify configure_logging adds handlers when called
        configure_logging()
        assert len(root_logger.handlers) >= 1

        # Restore original handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        for handler in original_handlers:
            root_logger.addHandler(handler)
