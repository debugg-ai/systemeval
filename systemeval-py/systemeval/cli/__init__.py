"""SystemEval CLI modules.

This package contains the CLI implementation split into focused modules:
- formatters: Output formatting for different modes (console, JSON, templates)

Note: The main CLI entry point is in ../cli_main.py (parent directory).
This package provides supporting modules for the CLI.
"""

from .formatters import (
    CLIProgressCallback,
    ConsoleFormatter,
    JsonFormatter,
    OutputFormatter,
    TemplateFormatter,
    create_formatter,
)

__all__ = [
    "CLIProgressCallback",
    "ConsoleFormatter",
    "JsonFormatter",
    "OutputFormatter",
    "TemplateFormatter",
    "create_formatter",
]
