"""Template system for formatted test output."""

from .renderer import TemplateRenderer, render_results
from .defaults import DEFAULT_TEMPLATES, get_default_template

__all__ = [
    "TemplateRenderer",
    "render_results",
    "DEFAULT_TEMPLATES",
    "get_default_template",
]
