"""Output formatters for SystemEval CLI.

This module provides formatters for different output modes:
- ConsoleFormatter: Rich console output with tables and colors
- JsonFormatter: Machine-readable JSON output
- TemplateFormatter: Jinja2 template-based output

All formatters implement the OutputFormatter protocol for consistency.
"""

from typing import Optional

from rich.console import Console

from .base import CLIProgressCallback, OutputFormatter
from .console_formatter import ConsoleFormatter
from .json_formatter import JsonFormatter
from .template_formatter import TemplateFormatter

__all__ = [
    "OutputFormatter",
    "CLIProgressCallback",
    "ConsoleFormatter",
    "JsonFormatter",
    "TemplateFormatter",
    "create_formatter",
]


def create_formatter(
    console: Console,
    json_output: bool = False,
    template: Optional[str] = None,
    adapter_type: str = "unknown",
    project_name: Optional[str] = None,
) -> OutputFormatter:
    """Factory function to create the appropriate formatter.

    Args:
        console: Rich Console instance.
        json_output: Whether to use JSON output.
        template: Template name if using template output.
        adapter_type: Test adapter type for JSON evaluation context.
        project_name: Project name for JSON evaluation context.

    Returns:
        OutputFormatter instance based on the output mode.

    Raises:
        ValueError: If both json_output and template are specified.
    """
    if json_output and template:
        raise ValueError("Cannot specify both --json and --template")

    if json_output:
        return JsonFormatter(
            adapter_type=adapter_type,
            project_name=project_name,
        )
    elif template:
        return TemplateFormatter(template_name=template)
    else:
        return ConsoleFormatter(console=console)
