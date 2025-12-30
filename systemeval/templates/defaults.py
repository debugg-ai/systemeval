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

    # =========================================================================
    # PIPELINE TEMPLATES
    # =========================================================================
    # These templates are designed for pipeline evaluation results with
    # project-level metrics (build, container, knowledge graph, E2E tests).

    # -------------------------------------------------------------------------
    # PIPELINE_SUMMARY: One-line summary for pipeline evaluation
    # -------------------------------------------------------------------------
    "pipeline_summary": """\
[{{ verdict }}] Pipeline Eval | {{ passed }}/{{ total }} projects passed | {{ duration | round(1) }}s
{% for failure in failures %}  - {{ failure.test_name }}: {{ failure.message | truncate(60) }}
{% endfor %}
""",

    # -------------------------------------------------------------------------
    # PIPELINE_TABLE: Detailed table matching run_system_eval output
    # -------------------------------------------------------------------------
    "pipeline_table": """\
================================================================================
PIPELINE EVALUATION RESULTS
================================================================================
Duration: {{ duration | round(1) }}s
Projects: {{ passed }}/{{ total }} passed

Project                  Build        Container  KG Pages   E2E P/F/E    Result
--------------------------------------------------------------------------------
{% for failure in failures %}{{ failure.test_name | ljust(24) | truncate(24) }} {{ failure.metadata.build_status | default('none') | ljust(12) }} {{ ('healthy' if failure.metadata.container_healthy else 'unhealthy') | ljust(10) }} {{ failure.metadata.kg_pages | default(0) | string | ljust(10) }} {{ failure.metadata.e2e_passed | default(0) }}/{{ failure.metadata.e2e_failed | default(0) }}/{{ failure.metadata.e2e_errors | default(0) | ljust(8) }} FAIL
{% endfor %}
--------------------------------------------------------------------------------
{% if failures %}
FAILED CRITERIA:
{% for failure in failures %}
  - {{ failure.test_name }}: {{ failure.message }}
{% endfor %}
{% endif %}
================================================================================
RESULT: {{ verdict }}
================================================================================
""",

    # -------------------------------------------------------------------------
    # PIPELINE_CI: Structured CI format for pipeline evaluation
    # -------------------------------------------------------------------------
    "pipeline_ci": """\
================================================================================
SYSTEMEVAL PIPELINE RESULTS
================================================================================
Verdict:    {{ verdict }}
Duration:   {{ duration | round(1) }}s
Exit Code:  {{ exit_code }}
Timestamp:  {{ timestamp }}
--------------------------------------------------------------------------------
PROJECTS
--------------------------------------------------------------------------------
Total:      {{ total }}
Passed:     {{ passed }}
Failed:     {{ failed }}
Errors:     {{ errors }}
--------------------------------------------------------------------------------
{% if failures %}
FAILURES ({{ failures | length }})
--------------------------------------------------------------------------------
{% for failure in failures %}
[{{ loop.index }}] {{ failure.test_name }}
    Build:      {{ failure.metadata.build_status | default('unknown') }}
    Health:     {{ 'healthy' if failure.metadata.container_healthy else 'unhealthy' }}
    KG Pages:   {{ failure.metadata.kg_pages | default(0) }}
    E2E:        {{ failure.metadata.e2e_passed | default(0) }} pass / {{ failure.metadata.e2e_failed | default(0) }} fail / {{ failure.metadata.e2e_error | default(0) }} error
    Reason:     {{ failure.message }}
{% endfor %}
--------------------------------------------------------------------------------
{% endif %}
RESULT: {{ verdict }}
================================================================================
""",

    # -------------------------------------------------------------------------
    # PIPELINE_GITHUB: GitHub Actions annotations for pipeline
    # -------------------------------------------------------------------------
    "pipeline_github": """\
{% if verdict == "PASS" %}::notice::{{ verdict_emoji }} Pipeline evaluation passed: {{ passed }}/{{ total }} projects
{% else %}::error::{{ verdict_emoji }} Pipeline evaluation failed: {{ failed }} projects failed
{% endif %}
{% for failure in failures %}::error title={{ failure.test_name }}::{{ failure.message | truncate(100) | replace('\n', ' ') }}
{% endfor %}
""",

    # -------------------------------------------------------------------------
    # PIPELINE_MARKDOWN: Full markdown report for pipeline
    # -------------------------------------------------------------------------
    "pipeline_markdown": """\
# Pipeline Evaluation Results

| Metric | Value |
|--------|-------|
| **Verdict** | {{ verdict_emoji }} **{{ verdict }}** |
| **Projects Evaluated** | {{ total }} |
| **Passed** | {{ passed }} |
| **Failed** | {{ failed }} |
| **Duration** | {{ duration | round(1) }}s |
| **Timestamp** | {{ timestamp }} |

## Exit Code: {{ exit_code }}

{% if verdict == "PASS" %}
All projects passed pipeline evaluation.
{% else %}
**{{ failed }} project(s) failed evaluation.**
{% endif %}

{% if failures %}
## Failed Projects

{% for failure in failures %}
### {{ failure.test_name }}

| Stage | Status |
|-------|--------|
| Build | {{ failure.metadata.build_status | default('unknown') }} |
| Container | {{ 'healthy' if failure.metadata.container_healthy else 'unhealthy' }} |
| Knowledge Graph | {{ failure.metadata.kg_pages | default(0) }} pages |
| E2E Tests | {{ failure.metadata.e2e_passed | default(0) }}P / {{ failure.metadata.e2e_failed | default(0) }}F / {{ failure.metadata.e2e_error | default(0) }}E |

**Failure Reason:** {{ failure.message }}

{% endfor %}
{% endif %}
""",

    # -------------------------------------------------------------------------
    # PIPELINE_DIAGNOSTIC: Detailed diagnostic output for debugging
    # -------------------------------------------------------------------------
    "pipeline_diagnostic": """\
================================================================================
SYSTEMEVAL PIPELINE DIAGNOSTIC REPORT
================================================================================
Timestamp:  {{ timestamp }}
Duration:   {{ duration | round(1) }}s
Verdict:    {{ verdict_emoji }} {{ verdict }}
Exit Code:  {{ exit_code }}

================================================================================
SUMMARY
================================================================================
Projects Evaluated: {{ total }}
  Passed:  {{ passed }}
  Failed:  {{ failed }}
  Errors:  {{ errors }}

{% for failure in failures %}
================================================================================
PROJECT: {{ failure.test_name }}
================================================================================
Status: FAILED

--- BUILD ---
  Status:    {{ failure.metadata.build_status | default('unknown') }}
  ID:        {{ failure.metadata.build_id | default('N/A') }}
  Duration:  {{ failure.metadata.build_duration | default('N/A') }}s

--- CONTAINER ---
  Healthy:   {{ 'Yes' if failure.metadata.container_healthy else 'No' }}
  Health Checks: {{ failure.metadata.health_checks_passed | default(0) }}
  ID:        {{ failure.metadata.container_id | default('N/A') }}
  Startup:   {{ failure.metadata.container_startup_time | default('N/A') }}s

--- PIPELINE ---
  Status:    {{ failure.metadata.pipeline_status | default('N/A') }}
  Name:      {{ failure.metadata.pipeline_name | default('N/A') }}
  ID:        {{ failure.metadata.pipeline_id | default('N/A') }}
{% set stages = failure.metadata.get('pipeline_stages', []) if failure.metadata else [] %}
{% if stages %}
  Stages:
{% for stage in stages %}    {{ stage.order }}. {{ stage.name }}: {{ stage.status }}{% if stage.duration %} ({{ stage.duration | round(1) }}s){% endif %}{% if stage.error %} - ERROR: {{ stage.error }}{% endif %}

{% endfor %}{% endif %}

--- KNOWLEDGE GRAPH ---
  Exists:    {{ 'Yes' if failure.metadata.kg_exists else 'No' }}
  Pages:     {{ failure.metadata.kg_pages | default(0) }}
  ID:        {{ failure.metadata.kg_id | default('N/A') }}

--- SURFERS/CRAWLERS ---
{% set surfers = failure.metadata.get('surfers', {}) if failure.metadata else {} %}
  Total:     {{ surfers.get('total', 0) }}
  Completed: {{ surfers.get('completed', 0) }}
  Failed:    {{ surfers.get('failed', 0) }}
  Running:   {{ surfers.get('running', 0) }}
{% if surfers.get('errors') %}  Errors:
{% for err in surfers.get('errors', []) %}    - {{ err | truncate(70) }}
{% endfor %}{% endif %}

--- E2E TESTS ---
  Total Runs:   {{ failure.metadata.e2e_runs | default(0) }}
  Passed:       {{ failure.metadata.e2e_passed | default(0) }}
  Failed:       {{ failure.metadata.e2e_failed | default(0) }}
  Errors:       {{ failure.metadata.e2e_error | default(0) }}
  Pending:      {{ failure.metadata.e2e_pending | default(0) }}
  Pass Rate:    {{ failure.metadata.e2e_pass_rate | default(0) }}%
  Error Rate:   {{ failure.metadata.e2e_error_rate | default(0) }}%
  Avg Steps:    {{ failure.metadata.e2e_avg_steps | default(0) }}

--- DIAGNOSTICS ---
{% set diagnostics = failure.metadata.get('diagnostics', []) if failure.metadata else [] %}
{% if diagnostics %}{% for diag in diagnostics %}  ⚠ {{ diag }}
{% endfor %}{% else %}  No diagnostic issues found.
{% endif %}

--- FAILURE REASON ---
  {{ failure.message }}

{% endfor %}
================================================================================
END DIAGNOSTIC REPORT
================================================================================
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
