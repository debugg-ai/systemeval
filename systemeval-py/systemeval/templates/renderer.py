"""Template renderer for test results."""

from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from jinja2 import Environment, BaseLoader, FileSystemLoader, select_autoescape

from systemeval.types import TestResult
from .defaults import DEFAULT_TEMPLATES, get_default_template


class TemplateRenderer:
    """Renders test results using Jinja2 templates.

    Supports:
    - Built-in default templates (summary, markdown, ci, github, junit, slack, table)
    - Custom templates from strings
    - Custom templates from files
    - Template directory for organization
    """

    def __init__(
        self,
        template_dir: Optional[Path] = None,
        custom_templates: Optional[Dict[str, str]] = None,
    ) -> None:
        """Initialize the template renderer.

        Args:
            template_dir: Optional directory containing .j2 template files
            custom_templates: Optional dict of template_name -> template_string
        """
        self._custom_templates = custom_templates or {}

        # Create environment with optional file loader
        if template_dir and template_dir.exists():
            loader = FileSystemLoader(str(template_dir))
            self._env = Environment(
                loader=loader,
                autoescape=select_autoescape(["xml", "html"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )
        else:
            self._env = Environment(
                loader=BaseLoader(),
                autoescape=select_autoescape(["xml", "html"]),
                trim_blocks=True,
                lstrip_blocks=True,
            )

        # Add custom filters
        self._env.filters["ljust"] = lambda s, w: str(s).ljust(w)
        self._env.filters["rjust"] = lambda s, w: str(s).rjust(w)

    def _get_template_string(self, template_name: str) -> str:
        """Get template string by name, checking custom then defaults.

        Args:
            template_name: Name of template or path to .j2 file

        Returns:
            Template string

        Raises:
            KeyError: If template not found
        """
        # Check custom templates first
        if template_name in self._custom_templates:
            return self._custom_templates[template_name]

        # Check default templates
        if template_name in DEFAULT_TEMPLATES:
            return DEFAULT_TEMPLATES[template_name]

        # Try as file path
        if template_name.endswith((".j2", ".jinja2", ".tpl")):
            path = Path(template_name)
            if path.exists():
                return path.read_text()

        raise KeyError(
            f"Template '{template_name}' not found. "
            f"Available defaults: {', '.join(DEFAULT_TEMPLATES.keys())}"
        )

    def render(
        self,
        template_name: str,
        context: Dict[str, Any],
    ) -> str:
        """Render a template with the given context.

        Args:
            template_name: Name of template (default or custom) or path to file
            context: Dictionary of variables for the template

        Returns:
            Rendered string
        """
        template_string = self._get_template_string(template_name)
        template = self._env.from_string(template_string)

        # Add computed context variables
        enriched_context = self._enrich_context(context)

        return template.render(**enriched_context)

    def render_string(
        self,
        template_string: str,
        context: Dict[str, Any],
    ) -> str:
        """Render a template string directly.

        Args:
            template_string: Jinja2 template string
            context: Dictionary of variables for the template

        Returns:
            Rendered string
        """
        template = self._env.from_string(template_string)
        enriched_context = self._enrich_context(context)
        return template.render(**enriched_context)

    def _enrich_context(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Add computed variables to the context.

        Args:
            context: Original context dict

        Returns:
            Enriched context with additional computed variables
        """
        enriched = dict(context)

        # Provide 'duration' alias for templates (canonical key is duration_seconds)
        if "duration_seconds" in enriched and "duration" not in enriched:
            enriched["duration"] = enriched["duration_seconds"]

        # Ensure failures have both duration and duration_seconds for compatibility
        if "failures" in enriched:
            new_failures = []
            for f in enriched["failures"]:
                enriched_f = dict(f)
                # Add duration_seconds if missing but duration exists
                if "duration_seconds" not in enriched_f and "duration" in enriched_f:
                    enriched_f["duration_seconds"] = enriched_f["duration"]
                # Add duration if missing but duration_seconds exists
                elif "duration" not in enriched_f and "duration_seconds" in enriched_f:
                    enriched_f["duration"] = enriched_f["duration_seconds"]
                new_failures.append(enriched_f)
            enriched["failures"] = new_failures

        # Add verdict emoji
        verdict = context.get("verdict", "ERROR")
        emoji_map = {
            "PASS": "\u2705",  # Green check
            "FAIL": "\u274C",  # Red X
            "ERROR": "\u26A0\uFE0F",  # Warning
        }
        enriched["verdict_emoji"] = emoji_map.get(verdict, "\u2753")

        # Add pass rate
        total = context.get("total", 0)
        passed = context.get("passed", 0)
        if total > 0:
            enriched["pass_rate"] = round((passed / total) * 100, 1)
        else:
            enriched["pass_rate"] = 0.0

        # Add failure rate
        failed = context.get("failed", 0)
        errors = context.get("errors", 0)
        if total > 0:
            enriched["failure_rate"] = round(((failed + errors) / total) * 100, 1)
        else:
            enriched["failure_rate"] = 0.0

        return enriched

    def list_templates(self) -> Dict[str, str]:
        """List all available templates.

        Returns:
            Dict of template_name -> description
        """
        templates = {
            "summary": "Concise one-line summary for CI logs",
            "markdown": "Full report in markdown format",
            "ci": "Structured format for CI/CD systems",
            "github": "GitHub Actions annotation format",
            "junit": "JUnit XML format for test tools",
            "slack": "Slack message format (mrkdwn)",
            "table": "ASCII table format",
            # Pipeline templates
            "pipeline_summary": "Pipeline eval one-line summary",
            "pipeline_table": "Pipeline eval detailed table",
            "pipeline_ci": "Pipeline eval CI format",
            "pipeline_github": "Pipeline eval GitHub annotations",
            "pipeline_markdown": "Pipeline eval markdown report",
            "pipeline_diagnostic": "Pipeline eval detailed diagnostics",
            # E2E generation templates
            "e2e_summary": "E2E generation one-line summary",
            "e2e_table": "E2E generation detailed table",
            "e2e_ci": "E2E generation CI format",
            "e2e_github": "E2E generation GitHub annotations",
            "e2e_markdown": "E2E generation markdown report",
            "e2e_slack": "E2E generation Slack format",
        }

        # Add custom templates
        for name in self._custom_templates:
            if name not in templates:
                templates[name] = "Custom template"

        return templates


def render_results(
    results: Union[TestResult, Dict[str, Any]],
    template_name: str = "summary",
    custom_templates: Optional[Dict[str, str]] = None,
) -> str:
    """Convenience function to render test results.

    Args:
        results: TestResult object or dict with result data
        template_name: Name of template to use
        custom_templates: Optional custom templates dict

    Returns:
        Rendered string
    """
    renderer = TemplateRenderer(custom_templates=custom_templates)

    # Convert TestResult to dict if needed
    if hasattr(results, "to_dict"):
        context = results.to_dict()
    elif isinstance(results, dict):
        context = results
    else:
        raise TypeError(f"Expected TestResult or dict, got {type(results)}")

    # Provide 'duration' alias for templates (canonical key is duration_seconds)
    if "duration_seconds" in context and "duration" not in context:
        context["duration"] = context["duration_seconds"]

    # Add failures list if available
    if hasattr(results, "failures"):
        context["failures"] = [
            {
                "test_id": f.test_id,
                "test_name": f.test_name,
                "message": f.message,
                "traceback": f.traceback,
                "duration_seconds": f.duration,
                "duration": f.duration,  # Alias for templates
                "metadata": getattr(f, "metadata", {}),
            }
            for f in results.failures
        ]
    elif "failures" not in context:
        context["failures"] = []

    return renderer.render(template_name, context)
