"""Template formatter that delegates to TemplateRenderer."""

from typing import TYPE_CHECKING, Optional

from systemeval.types import TestResult

if TYPE_CHECKING:
    from systemeval.config import MultiProjectResult


class TemplateFormatter:
    """Formats test results using Jinja2 templates.

    This formatter delegates to the TemplateRenderer to produce
    formatted output using built-in or custom templates.

    Attributes:
        template_name: Name of the template to use.
    """

    def __init__(self, template_name: str):
        """Initialize the template formatter.

        Args:
            template_name: Name of template to use (summary, markdown, ci, etc.).
        """
        self.template_name = template_name

    def format_single_result(self, result: TestResult) -> str:
        """Format a single test result using a template.

        Args:
            result: TestResult to format.

        Returns:
            Formatted string output from template.
        """
        from systemeval.templates import render_results

        return render_results(result, template_name=self.template_name)

    def format_multi_project_result(self, result: "MultiProjectResult") -> str:
        """Format multi-project results using a template.

        Note: Template output for multi-project mode is not yet fully implemented.
        For now, this returns a placeholder message.

        Args:
            result: MultiProjectResult to format.

        Returns:
            Formatted string output.
        """
        # TODO: Implement multi-project template rendering
        # For now, return a placeholder
        return (
            f"[yellow]Template output not yet implemented for multi-project mode[/yellow]\n"
            f"Template: {self.template_name}"
        )
