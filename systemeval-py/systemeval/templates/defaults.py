"""Default output templates for systemeval."""

from pathlib import Path
from typing import Dict

# Template directory (jinja2 files extracted from this module)
_TEMPLATE_DIR = Path(__file__).parent / "jinja2"


def _load_template(name: str) -> str:
    """Load a template from the jinja2 directory.

    Args:
        name: Template name (without .jinja2 extension)

    Returns:
        Template content as string

    Raises:
        FileNotFoundError: If template file doesn't exist
    """
    template_path = _TEMPLATE_DIR / f"{name}.jinja2"
    if not template_path.exists():
        raise FileNotFoundError(f"Template file not found: {template_path}")
    return template_path.read_text()


# =============================================================================
# DEFAULT TEMPLATES
# =============================================================================
# These templates define consistent, repeatable output structures.
# Users can override or extend these in their systemeval.yaml config.
#
# Templates are loaded from separate .jinja2 files in the jinja2/ directory
# for better maintainability and editor support.

DEFAULT_TEMPLATES: Dict[str, str] = {
    # Core test result templates
    "summary": _load_template("summary"),
    "markdown": _load_template("markdown"),
    "ci": _load_template("ci"),
    "github": _load_template("github"),
    "junit": _load_template("junit"),
    "slack": _load_template("slack"),
    "table": _load_template("table"),

    # Pipeline evaluation templates
    "pipeline_summary": _load_template("pipeline_summary"),
    "pipeline_table": _load_template("pipeline_table"),
    "pipeline_ci": _load_template("pipeline_ci"),
    "pipeline_github": _load_template("pipeline_github"),
    "pipeline_markdown": _load_template("pipeline_markdown"),
    "pipeline_diagnostic": _load_template("pipeline_diagnostic"),

    # Multi-environment templates
    "env_summary": _load_template("env_summary"),
    "env_table": _load_template("env_table"),
    "env_ci": _load_template("env_ci"),

    # E2E test generation templates
    "e2e_summary": _load_template("e2e_summary"),
    "e2e_table": _load_template("e2e_table"),
    "e2e_ci": _load_template("e2e_ci"),
    "e2e_github": _load_template("e2e_github"),
    "e2e_markdown": _load_template("e2e_markdown"),
    "e2e_slack": _load_template("e2e_slack"),
}


def get_default_template(name: str) -> str:
    """Get a default template by name.

    Args:
        name: Template name (summary, markdown, ci, github, junit, slack, table)

    Returns:
        Template string

    Raises:
        KeyError: If template not found
    """
    if name not in DEFAULT_TEMPLATES:
        available = ", ".join(DEFAULT_TEMPLATES.keys())
        raise KeyError(f"Template '{name}' not found. Available: {available}")
    return DEFAULT_TEMPLATES[name]
