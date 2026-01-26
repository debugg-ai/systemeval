"""
Centralized logging configuration for SystemEval.

Provides:
- Consistent logging format across all modules
- Configurable log levels via environment variables
- Separate handling for internal debug logging vs user-facing CLI output

Usage:
    from systemeval.utils.logging import get_logger

    logger = get_logger(__name__)
    logger.debug("Internal debug information")
    logger.info("General information")
    logger.warning("Warning message")
    logger.error("Error message")

Environment Variables:
    SYSTEMEVAL_LOG_LEVEL: Set global log level (DEBUG, INFO, WARNING, ERROR)
    SYSTEMEVAL_LOG_FORMAT: Override log format (simple, detailed, json)
"""
import logging
import os
import sys
from typing import Optional

# Default log levels by component
DEFAULT_LOG_LEVEL = logging.INFO

# Log format options
LOG_FORMATS = {
    "simple": "%(levelname)s: %(message)s",
    "detailed": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    "json": '{"timestamp":"%(asctime)s","logger":"%(name)s","level":"%(levelname)s","message":"%(message)s"}',
}


class SystemEvalFormatter(logging.Formatter):
    """
    Custom formatter with color support for terminal output.

    Uses ANSI color codes when outputting to a TTY.
    """

    # ANSI color codes
    COLORS = {
        "DEBUG": "\033[36m",  # Cyan
        "INFO": "\033[32m",   # Green
        "WARNING": "\033[33m", # Yellow
        "ERROR": "\033[31m",   # Red
        "CRITICAL": "\033[35m", # Magenta
        "RESET": "\033[0m",
    }

    def __init__(self, fmt: str, use_colors: bool = True):
        super().__init__(fmt)
        self.use_colors = use_colors and sys.stderr.isatty()

    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            # Add color to level name
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"

        return super().format(record)


def get_log_level() -> int:
    """
    Get log level from environment or use default.

    Returns:
        Logging level constant (DEBUG, INFO, WARNING, ERROR)
    """
    level_name = os.getenv("SYSTEMEVAL_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, DEFAULT_LOG_LEVEL)


def get_log_format() -> str:
    """
    Get log format from environment or use default.

    Returns:
        Log format string
    """
    format_name = os.getenv("SYSTEMEVAL_LOG_FORMAT", "simple")
    return LOG_FORMATS.get(format_name, LOG_FORMATS["simple"])


def configure_logging(
    level: Optional[int] = None,
    format_str: Optional[str] = None,
    use_colors: bool = True,
) -> None:
    """
    Configure root logger with SystemEval defaults.

    This should be called once at application startup.

    Args:
        level: Log level (defaults to environment or INFO)
        format_str: Log format string (defaults to environment or simple)
        use_colors: Enable colored output for terminal
    """
    level = level or get_log_level()
    format_str = format_str or get_log_format()

    # Remove existing handlers to avoid duplicates
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)

    # Set formatter
    formatter = SystemEvalFormatter(format_str, use_colors=use_colors)
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger.addHandler(handler)
    root_logger.setLevel(level)

    # Suppress overly verbose third-party loggers
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("docker").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger for the specified module.

    Args:
        name: Module name (typically __name__)

    Returns:
        Configured logger instance

    Example:
        logger = get_logger(__name__)
        logger.info("Processing started")
    """
    return logging.getLogger(name)


# Auto-configure on import if not already configured
if not logging.getLogger().handlers:
    configure_logging()
