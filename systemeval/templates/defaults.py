"""Default output templates for systemeval."""

from typing import Dict

# =============================================================================
# DEFAULT TEMPLATES
# =============================================================================
# These templates define consistent, repeatable output structures.
# Users can override or extend these in their systemeval.yaml config.

DEFAULT_TEMPLATES: Dict[str, str] = {
    # -------------------------------------------------------------------------
    # SUMMARY: Concise one-line summary for CI logs
    # -------------------------------------------------------------------------
    "summary": """\
[{{ verdict }}] {{ category | upper }} | {{ passed }}/{{ total }} passed | {{ failed }} failed | {{ errors }} errors | {{ duration | round(2) }}s
""",

    # -------------------------------------------------------------------------
    # MARKDOWN: Full report in markdown format
    # -------------------------------------------------------------------------
    "markdown": """\
# Test Results: {{ category | upper }}

| Metric | Value |
|--------|-------|
| **Verdict** | {{ verdict_emoji }} **{{ verdict }}** |
| **Category** | {{ category }} |
| **Total Tests** | {{ total }} |
| **Passed** | {{ passed }} |
| **Failed** | {{ failed }} |
| **Errors** | {{ errors }} |
| **Skipped** | {{ skipped }} |
| **Duration** | {{ duration | round(2) }}s |
| **Timestamp** | {{ timestamp }} |
{% if coverage_percent is not none %}| **Coverage** | {{ coverage_percent | round(1) }}% |
{% endif %}

## Exit Code: {{ exit_code }}

{% if verdict == "PASS" %}
All tests passed successfully.
{% elif verdict == "FAIL" %}
**{{ failed + errors }} test(s) did not pass.**
{% else %}
**Execution error occurred.** Check configuration and test collection.
{% endif %}
{% if failures %}

## Failures

{% for failure in failures %}
### {{ failure.test_name }}

- **Test ID**: `{{ failure.test_id }}`
- **Duration**: {{ failure.duration | round(3) }}s

```
{{ failure.message | truncate(500) }}
```

{% endfor %}
{% endif %}
""",

    # -------------------------------------------------------------------------
    # CI: Structured format optimized for CI/CD systems
    # -------------------------------------------------------------------------
    "ci": """\
================================================================================
SYSTEMEVAL RESULTS
================================================================================
Verdict:    {{ verdict }}
Category:   {{ category }}
Timestamp:  {{ timestamp }}
Duration:   {{ duration | round(2) }}s
Exit Code:  {{ exit_code }}
--------------------------------------------------------------------------------
COUNTS
--------------------------------------------------------------------------------
Total:      {{ total }}
Passed:     {{ passed }}
Failed:     {{ failed }}
Errors:     {{ errors }}
Skipped:    {{ skipped }}
{% if coverage_percent is not none %}Coverage:   {{ coverage_percent | round(1) }}%
{% endif %}
--------------------------------------------------------------------------------
{% if failures %}
FAILURES ({{ failures | length }})
--------------------------------------------------------------------------------
{% for failure in failures %}
[{{ loop.index }}] {{ failure.test_id }}
    Duration: {{ failure.duration | round(3) }}s
    Message:  {{ failure.message | truncate(200) | replace('\n', ' ') }}
{% endfor %}
--------------------------------------------------------------------------------
{% endif %}
RESULT: {{ verdict }}
================================================================================
""",

    # -------------------------------------------------------------------------
    # GITHUB: GitHub Actions annotation format
    # -------------------------------------------------------------------------
    "github": """\
{% if verdict == "PASS" %}::notice::{{ verdict_emoji }} Tests passed: {{ passed }}/{{ total }} ({{ category }})
{% elif verdict == "FAIL" %}::error::{{ verdict_emoji }} Tests failed: {{ failed }} failures, {{ errors }} errors ({{ category }})
{% else %}::error::{{ verdict_emoji }} Test execution error ({{ category }})
{% endif %}
{% for failure in failures %}::error file={{ failure.test_id | replace('::', '/') }},title={{ failure.test_name }}::{{ failure.message | truncate(100) | replace('\n', ' ') }}
{% endfor %}
""",

    # -------------------------------------------------------------------------
    # JUNIT: JUnit XML format for test reporting tools
    # -------------------------------------------------------------------------
    "junit": """\
<?xml version="1.0" encoding="UTF-8"?>
<testsuites name="{{ category }}" tests="{{ total }}" failures="{{ failed }}" errors="{{ errors }}" skipped="{{ skipped }}" time="{{ duration | round(3) }}" timestamp="{{ timestamp }}">
  <testsuite name="{{ category }}" tests="{{ total }}" failures="{{ failed }}" errors="{{ errors }}" skipped="{{ skipped }}" time="{{ duration | round(3) }}">
{% for failure in failures %}
    <testcase name="{{ failure.test_name }}" classname="{{ failure.test_id | replace('::', '.') }}" time="{{ failure.duration | round(3) }}">
      <failure message="{{ failure.message | e | truncate(200) }}">{{ failure.traceback | e if failure.traceback else failure.message | e }}</failure>
    </testcase>
{% endfor %}
  </testsuite>
</testsuites>
""",

    # -------------------------------------------------------------------------
    # SLACK: Slack message format (mrkdwn)
    # -------------------------------------------------------------------------
    "slack": """\
{{ verdict_emoji }} *{{ verdict }}* | `{{ category }}`
>*Passed:* {{ passed }}/{{ total }} | *Failed:* {{ failed }} | *Errors:* {{ errors }} | *Duration:* {{ duration | round(1) }}s
{% if failures %}
*Failures:*
{% for failure in failures[:5] %}`{{ failure.test_name }}`: {{ failure.message | truncate(50) | replace('\n', ' ') }}
{% endfor %}{% if failures | length > 5 %}_...and {{ failures | length - 5 }} more_{% endif %}
{% endif %}
""",

    # -------------------------------------------------------------------------
    # TABLE: ASCII table format
    # -------------------------------------------------------------------------
    "table": """\
+{{ '-' * 78 }}+
| SYSTEMEVAL RESULTS{{ ' ' * 59 }}|
+{{ '-' * 78 }}+
| Verdict     | {{ verdict | ljust(63) }}|
| Category    | {{ category | ljust(63) }}|
| Exit Code   | {{ exit_code | string | ljust(63) }}|
+{{ '-' * 78 }}+
| Total       | {{ total | string | ljust(63) }}|
| Passed      | {{ passed | string | ljust(63) }}|
| Failed      | {{ failed | string | ljust(63) }}|
| Errors      | {{ errors | string | ljust(63) }}|
| Skipped     | {{ skipped | string | ljust(63) }}|
| Duration    | {{ (duration | round(2) | string + 's') | ljust(63) }}|
+{{ '-' * 78 }}+
""",
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
