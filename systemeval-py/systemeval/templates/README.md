# SystemEval Templates

This module provides a Jinja2-based template system for rendering test results in various formats.

## Overview

- **renderer.py**: `TemplateRenderer` class for rendering test results
- **defaults.py**: Built-in template definitions

## Built-in Templates

| Template | Description | Use Case |
|----------|-------------|----------|
| `summary` | Concise one-line summary | Terminal output |
| `markdown` | Markdown-formatted report | Documentation, PRs |
| `ci` | CI-friendly plain text | GitHub Actions, CircleCI |
| `github` | GitHub Actions annotations | GitHub workflow output |
| `junit` | JUnit XML format | CI systems expecting JUnit |
| `slack` | Slack message format | Slack notifications |
| `table` | ASCII table format | Terminal display |
| `pipeline_*` | Pipeline adapter templates | Pipeline evaluations |
| `e2e_*` | E2E test templates | E2E test results |

## Usage

### Basic Usage

```python
from systemeval.templates import render_results
from systemeval.types import TestResult

result = TestResult(passed=10, failed=2, errors=0, skipped=1, duration=5.5)

# Render with default summary template
output = render_results(result, template="summary")

# Render as markdown
output = render_results(result, template="markdown")
```

### Using TemplateRenderer

```python
from systemeval.templates import TemplateRenderer
from pathlib import Path

# With custom template directory
renderer = TemplateRenderer(template_dir=Path("./my_templates"))
output = renderer.render(result, "my_custom_template")

# With inline custom templates
renderer = TemplateRenderer(custom_templates={
    "my_format": "Tests: {{ result.passed }} passed, {{ result.failed }} failed"
})
output = renderer.render(result, "my_format")
```

### Template Context

Templates receive a context with:

```python
{
    "result": TestResult,        # The test result object
    "verdict": str,              # "PASS", "FAIL", or "ERROR"
    "duration": str,             # Formatted duration (e.g., "5.23s")
    "timestamp": str,            # ISO timestamp
    "category": str | None,      # Test category if specified
}
```

## Adding New Templates

1. Add template string to `defaults.py`:

```python
DEFAULT_TEMPLATES["my_template"] = """
Your Jinja2 template here
Passed: {{ result.passed }}
Failed: {{ result.failed }}
"""
```

2. Use it via CLI or API:

```bash
systemeval test --template my_template
```

## Template Filters

Custom Jinja2 filters available:

- `ljust(width)`: Left-justify string
- `rjust(width)`: Right-justify string

Example:
```jinja2
{{ "Status"|ljust(10) }}: {{ verdict }}
```
