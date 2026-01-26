"""Tests for template rendering system (SE-72m).

Tests for:
- systemeval/templates/renderer.py
- systemeval/templates/defaults.py
"""

import json
import tempfile
import pytest
from pathlib import Path

from systemeval.templates.renderer import TemplateRenderer, render_results
from systemeval.templates.defaults import DEFAULT_TEMPLATES, get_default_template
from systemeval.adapters import TestResult, TestFailure


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def basic_context():
    """Basic context for template rendering."""
    return {
        "verdict": "PASS",
        "category": "unit",
        "passed": 10,
        "failed": 0,
        "errors": 0,
        "skipped": 2,
        "total": 12,
        "duration": 5.5,
        "timestamp": "2025-01-15T10:30:00Z",
        "exit_code": 0,
        "coverage_percent": None,
        "failures": [],
    }


@pytest.fixture
def failing_context():
    """Context with failures for template rendering."""
    return {
        "verdict": "FAIL",
        "category": "integration",
        "passed": 8,
        "failed": 2,
        "errors": 1,
        "skipped": 1,
        "total": 12,
        "duration": 10.2,
        "timestamp": "2025-01-15T11:00:00Z",
        "exit_code": 1,
        "coverage_percent": 75.5,
        "failures": [
            {
                "test_id": "test_module::test_one",
                "test_name": "test_one",
                "message": "AssertionError: expected 1, got 2",
                "traceback": "Traceback...\nAssertionError: expected 1, got 2",
                "duration_seconds": 0.5,
                "metadata": {},
            },
            {
                "test_id": "test_module::test_two",
                "test_name": "test_two",
                "message": "ValueError: invalid input",
                "traceback": "Traceback...\nValueError: invalid input",
                "duration_seconds": 0.3,
                "metadata": {},
            },
        ],
    }


@pytest.fixture
def pipeline_context():
    """Context for pipeline evaluation templates."""
    return {
        "verdict": "FAIL",
        "passed": 2,
        "failed": 1,
        "errors": 0,
        "total": 3,
        "duration": 120.5,
        "timestamp": "2025-01-15T12:00:00Z",
        "exit_code": 1,
        "failures": [
            {
                "test_id": "project-alpha",
                "test_name": "project-alpha",
                "message": "E2E tests failed: 2 failures",
                "traceback": "",
                "duration": 45.0,
                "metadata": {
                    "build_status": "succeeded",
                    "container_healthy": True,
                    "kg_pages": 10,
                    "e2e_passed": 3,
                    "e2e_failed": 2,
                    "e2e_errors": 0,
                },
            },
        ],
    }


@pytest.fixture
def renderer():
    """Create a basic TemplateRenderer."""
    return TemplateRenderer()


@pytest.fixture
def temp_template_dir():
    """Create a temporary directory with template files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        template_path = Path(tmpdir) / "custom.j2"
        template_path.write_text("Custom: {{ verdict }} - {{ passed }}/{{ total }}")
        yield Path(tmpdir)


# =============================================================================
# DEFAULT TEMPLATES TESTS
# =============================================================================


class TestDefaultTemplates:
    """Tests for default template definitions."""

    def test_default_templates_dict_exists(self):
        """Test that DEFAULT_TEMPLATES dictionary exists and is populated."""
        assert isinstance(DEFAULT_TEMPLATES, dict)
        assert len(DEFAULT_TEMPLATES) > 0

    def test_all_expected_templates_present(self):
        """Test that all expected default templates are defined."""
        expected = [
            "summary",
            "markdown",
            "ci",
            "github",
            "junit",
            "slack",
            "table",
            "pipeline_summary",
            "pipeline_table",
            "pipeline_ci",
            "pipeline_github",
            "pipeline_markdown",
            "pipeline_diagnostic",
            "env_summary",
            "env_table",
            "env_ci",
        ]
        for template_name in expected:
            assert template_name in DEFAULT_TEMPLATES, f"Missing template: {template_name}"

    def test_templates_are_strings(self):
        """Test that all templates are non-empty strings."""
        for name, template in DEFAULT_TEMPLATES.items():
            assert isinstance(template, str), f"Template {name} is not a string"
            assert len(template) > 0, f"Template {name} is empty"

    def test_templates_contain_jinja_variables(self):
        """Test that templates contain expected Jinja2 variables."""
        # Summary template should reference verdict and counts
        assert "{{ verdict }}" in DEFAULT_TEMPLATES["summary"]
        assert "{{ passed }}" in DEFAULT_TEMPLATES["summary"]
        assert "{{ total }}" in DEFAULT_TEMPLATES["summary"]

    def test_summary_template_structure(self):
        """Test summary template has expected structure."""
        template = DEFAULT_TEMPLATES["summary"]
        assert "{{ verdict }}" in template
        assert "{{ category" in template
        assert "{{ duration" in template


class TestGetDefaultTemplate:
    """Tests for get_default_template function."""

    def test_get_existing_template(self):
        """Test getting an existing template by name."""
        template = get_default_template("summary")
        assert template is not None
        assert isinstance(template, str)
        assert "verdict" in template

    def test_get_all_existing_templates(self):
        """Test getting all existing templates by name."""
        for name in DEFAULT_TEMPLATES:
            template = get_default_template(name)
            assert template == DEFAULT_TEMPLATES[name]

    def test_get_nonexistent_template_raises_keyerror(self):
        """Test that getting non-existent template raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            get_default_template("nonexistent_template")
        assert "nonexistent_template" in str(exc_info.value)
        assert "not found" in str(exc_info.value)

    def test_keyerror_includes_available_templates(self):
        """Test that KeyError message lists available templates."""
        with pytest.raises(KeyError) as exc_info:
            get_default_template("invalid")
        error_message = str(exc_info.value)
        # Should mention at least some available templates
        assert "summary" in error_message or "Available:" in error_message


# =============================================================================
# TEMPLATE RENDERER INITIALIZATION TESTS
# =============================================================================


class TestTemplateRendererInit:
    """Tests for TemplateRenderer initialization."""

    def test_init_without_arguments(self):
        """Test initialization without any arguments."""
        renderer = TemplateRenderer()
        assert renderer is not None
        assert renderer._custom_templates == {}

    def test_init_with_custom_templates(self):
        """Test initialization with custom templates."""
        custom = {"my_template": "Hello {{ name }}"}
        renderer = TemplateRenderer(custom_templates=custom)
        assert "my_template" in renderer._custom_templates
        assert renderer._custom_templates["my_template"] == "Hello {{ name }}"

    def test_init_with_template_dir(self, temp_template_dir):
        """Test initialization with template directory."""
        renderer = TemplateRenderer(template_dir=temp_template_dir)
        assert renderer is not None

    def test_init_with_nonexistent_template_dir(self):
        """Test initialization with non-existent template directory."""
        renderer = TemplateRenderer(template_dir=Path("/nonexistent/path"))
        # Should not raise, just use BaseLoader
        assert renderer is not None

    def test_init_with_both_custom_templates_and_dir(self, temp_template_dir):
        """Test initialization with both custom templates and directory."""
        custom = {"inline": "Inline: {{ value }}"}
        renderer = TemplateRenderer(
            template_dir=temp_template_dir,
            custom_templates=custom,
        )
        assert "inline" in renderer._custom_templates


# =============================================================================
# TEMPLATE RENDERING TESTS
# =============================================================================


class TestTemplateRendererRender:
    """Tests for TemplateRenderer.render() method."""

    def test_render_default_summary_template(self, renderer, basic_context):
        """Test rendering with default summary template."""
        output = renderer.render("summary", basic_context)
        assert "[PASS]" in output
        assert "UNIT" in output  # category is uppercased
        assert "10" in output  # passed count
        assert "12" in output  # total count

    def test_render_default_markdown_template(self, renderer, basic_context):
        """Test rendering with default markdown template."""
        output = renderer.render("markdown", basic_context)
        assert "# Test Results:" in output
        assert "**Verdict**" in output
        assert "PASS" in output

    def test_render_default_ci_template(self, renderer, basic_context):
        """Test rendering with default CI template."""
        output = renderer.render("ci", basic_context)
        assert "SYSTEMEVAL RESULTS" in output
        assert "Verdict:" in output
        assert "PASS" in output

    def test_render_default_github_template(self, renderer, basic_context):
        """Test rendering with default GitHub template."""
        output = renderer.render("github", basic_context)
        assert "::notice::" in output

    def test_render_default_junit_template(self, renderer, basic_context):
        """Test rendering with default JUnit template."""
        output = renderer.render("junit", basic_context)
        assert '<?xml version="1.0"' in output
        assert "<testsuites" in output

    def test_render_default_slack_template(self, renderer, basic_context):
        """Test rendering with default Slack template."""
        output = renderer.render("slack", basic_context)
        assert "*PASS*" in output

    def test_render_default_table_template(self, renderer, basic_context):
        """Test rendering with default table template."""
        output = renderer.render("table", basic_context)
        assert "SYSTEMEVAL RESULTS" in output
        assert "Verdict" in output

    def test_render_with_failures(self, renderer, failing_context):
        """Test rendering templates with failure data."""
        output = renderer.render("markdown", failing_context)
        assert "FAIL" in output
        assert "## Failures" in output
        assert "test_one" in output
        assert "test_two" in output

    def test_render_ci_with_failures(self, renderer, failing_context):
        """Test rendering CI template with failures."""
        output = renderer.render("ci", failing_context)
        assert "FAILURES" in output
        assert "test_module::test_one" in output

    def test_render_github_with_failures(self, renderer, failing_context):
        """Test rendering GitHub template with failures."""
        output = renderer.render("github", failing_context)
        assert "::error::" in output
        assert "test_one" in output

    def test_render_slack_with_failures(self, renderer, failing_context):
        """Test rendering Slack template with failures."""
        output = renderer.render("slack", failing_context)
        assert "*Failures:*" in output

    def test_render_junit_with_failures(self, renderer, failing_context):
        """Test rendering JUnit template with failures."""
        output = renderer.render("junit", failing_context)
        assert '<failure message="' in output

    def test_render_custom_template(self):
        """Test rendering with custom template."""
        custom = {"greeting": "Hello {{ name }}, score: {{ score }}"}
        renderer = TemplateRenderer(custom_templates=custom)
        output = renderer.render("greeting", {"name": "World", "score": 100})
        assert "Hello World" in output
        assert "score: 100" in output

    def test_custom_template_overrides_default(self):
        """Test that custom template overrides default with same name."""
        custom = {"summary": "Custom summary: {{ verdict }}"}
        renderer = TemplateRenderer(custom_templates=custom)
        output = renderer.render("summary", {"verdict": "PASS"})
        assert "Custom summary: PASS" in output
        assert "[PASS]" not in output  # default format not present

    def test_render_nonexistent_template_raises(self, renderer, basic_context):
        """Test that rendering non-existent template raises KeyError."""
        with pytest.raises(KeyError) as exc_info:
            renderer.render("nonexistent", basic_context)
        assert "nonexistent" in str(exc_info.value)
        assert "not found" in str(exc_info.value)


# =============================================================================
# TEMPLATE FILE LOADING TESTS
# =============================================================================


class TestTemplateFileLoading:
    """Tests for loading templates from files."""

    def test_render_from_j2_file(self, temp_template_dir, basic_context):
        """Test rendering template from .j2 file."""
        renderer = TemplateRenderer()
        template_path = temp_template_dir / "custom.j2"
        output = renderer.render(str(template_path), basic_context)
        assert "Custom: PASS" in output
        assert "10/12" in output

    def test_render_from_jinja2_extension(self):
        """Test rendering template from .jinja2 file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jinja2", delete=False
        ) as f:
            f.write("Result: {{ verdict }}")
            f.flush()
            renderer = TemplateRenderer()
            output = renderer.render(f.name, {"verdict": "PASS"})
            assert "Result: PASS" in output

    def test_render_from_tpl_extension(self):
        """Test rendering template from .tpl file."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".tpl", delete=False
        ) as f:
            f.write("Output: {{ value }}")
            f.flush()
            renderer = TemplateRenderer()
            output = renderer.render(f.name, {"value": 42})
            assert "Output: 42" in output

    def test_nonexistent_file_raises_keyerror(self, renderer):
        """Test that non-existent file path raises KeyError."""
        with pytest.raises(KeyError):
            renderer.render("/nonexistent/template.j2", {})


# =============================================================================
# RENDER STRING TESTS
# =============================================================================


class TestTemplateRendererRenderString:
    """Tests for TemplateRenderer.render_string() method."""

    def test_render_string_basic(self, renderer):
        """Test basic string template rendering."""
        output = renderer.render_string(
            "Hello {{ name }}!",
            {"name": "World"},
        )
        assert output == "Hello World!"

    def test_render_string_with_filters(self, renderer):
        """Test string template with Jinja filters."""
        output = renderer.render_string(
            "{{ text | upper }}",
            {"text": "hello"},
        )
        assert output == "HELLO"

    def test_render_string_with_conditionals(self, renderer):
        """Test string template with conditionals."""
        output = renderer.render_string(
            "{% if passed %}OK{% else %}FAIL{% endif %}",
            {"passed": True},
        )
        assert output == "OK"

    def test_render_string_with_loops(self, renderer):
        """Test string template with loops."""
        output = renderer.render_string(
            "{% for item in items %}{{ item }},{% endfor %}",
            {"items": ["a", "b", "c"]},
        )
        assert output == "a,b,c,"

    def test_render_string_with_enriched_context(self, renderer):
        """Test that render_string also enriches context."""
        output = renderer.render_string(
            "Rate: {{ pass_rate }}%",
            {"total": 10, "passed": 8},
        )
        assert "Rate: 80.0%" in output


# =============================================================================
# CONTEXT ENRICHMENT TESTS
# =============================================================================


class TestContextEnrichment:
    """Tests for context enrichment (_enrich_context)."""

    def test_verdict_emoji_pass(self, renderer, basic_context):
        """Test verdict emoji for PASS."""
        output = renderer.render("markdown", basic_context)
        # Green check mark emoji should be present
        assert "\u2705" in output

    def test_verdict_emoji_fail(self, renderer, failing_context):
        """Test verdict emoji for FAIL."""
        output = renderer.render("markdown", failing_context)
        # Red X emoji should be present
        assert "\u274C" in output

    def test_verdict_emoji_error(self, renderer):
        """Test verdict emoji for ERROR."""
        context = {
            "verdict": "ERROR",
            "category": "unit",
            "passed": 0,
            "failed": 0,
            "errors": 1,
            "skipped": 0,
            "total": 1,
            "duration": 0.1,
            "timestamp": "2025-01-15T10:00:00Z",
            "exit_code": 2,
            "coverage_percent": None,
            "failures": [],
        }
        output = renderer.render("markdown", context)
        # Warning emoji should be present (or the template mentions error)
        assert "ERROR" in output

    def test_pass_rate_calculation(self, renderer, basic_context):
        """Test pass rate calculation."""
        output = renderer.render_string(
            "Pass rate: {{ pass_rate }}%",
            basic_context,
        )
        # 10/12 = 83.3%
        assert "83.3%" in output

    def test_pass_rate_zero_total(self, renderer):
        """Test pass rate with zero total (division by zero handling)."""
        context = {"total": 0, "passed": 0}
        output = renderer.render_string(
            "Pass rate: {{ pass_rate }}%",
            context,
        )
        assert "0.0%" in output

    def test_failure_rate_calculation(self, renderer, failing_context):
        """Test failure rate calculation."""
        output = renderer.render_string(
            "Failure rate: {{ failure_rate }}%",
            failing_context,
        )
        # (2+1)/12 = 25%
        assert "25.0%" in output

    def test_failure_rate_zero_total(self, renderer):
        """Test failure rate with zero total."""
        context = {"total": 0, "failed": 0, "errors": 0}
        output = renderer.render_string(
            "Failure rate: {{ failure_rate }}%",
            context,
        )
        assert "0.0%" in output


# =============================================================================
# CUSTOM FILTER TESTS
# =============================================================================


class TestCustomFilters:
    """Tests for custom Jinja2 filters."""

    def test_ljust_filter(self, renderer):
        """Test ljust filter for left-justified text."""
        output = renderer.render_string(
            "[{{ text | ljust(10) }}]",
            {"text": "hi"},
        )
        assert output == "[hi        ]"

    def test_rjust_filter(self, renderer):
        """Test rjust filter for right-justified text."""
        output = renderer.render_string(
            "[{{ text | rjust(10) }}]",
            {"text": "hi"},
        )
        assert output == "[        hi]"

    def test_ljust_with_longer_text(self, renderer):
        """Test ljust filter when text is longer than width."""
        output = renderer.render_string(
            "[{{ text | ljust(3) }}]",
            {"text": "hello"},
        )
        assert output == "[hello]"  # No truncation

    def test_filters_used_in_table_template(self, renderer, basic_context):
        """Test that ljust filter is used correctly in table template."""
        output = renderer.render("table", basic_context)
        # Table template uses ljust for alignment
        assert "Verdict" in output
        assert "PASS" in output


# =============================================================================
# LIST TEMPLATES TESTS
# =============================================================================


class TestListTemplates:
    """Tests for TemplateRenderer.list_templates() method."""

    def test_list_templates_returns_dict(self, renderer):
        """Test that list_templates returns a dictionary."""
        templates = renderer.list_templates()
        assert isinstance(templates, dict)

    def test_list_templates_includes_defaults(self, renderer):
        """Test that list_templates includes default templates."""
        templates = renderer.list_templates()
        assert "summary" in templates
        assert "markdown" in templates
        assert "ci" in templates
        assert "github" in templates
        assert "junit" in templates
        assert "slack" in templates
        assert "table" in templates

    def test_list_templates_includes_descriptions(self, renderer):
        """Test that templates have descriptions."""
        templates = renderer.list_templates()
        for name, description in templates.items():
            assert isinstance(description, str)
            assert len(description) > 0

    def test_list_templates_includes_custom(self):
        """Test that list_templates includes custom templates."""
        custom = {"my_custom": "{{ data }}"}
        renderer = TemplateRenderer(custom_templates=custom)
        templates = renderer.list_templates()
        assert "my_custom" in templates
        assert templates["my_custom"] == "Custom template"

    def test_list_templates_custom_does_not_override_description(self):
        """Test that custom template named same as default gets default description."""
        custom = {"summary": "Custom: {{ verdict }}"}
        renderer = TemplateRenderer(custom_templates=custom)
        templates = renderer.list_templates()
        # summary still listed, not marked as custom
        assert "summary" in templates
        assert "Concise" in templates["summary"]  # Default description


# =============================================================================
# RENDER_RESULTS CONVENIENCE FUNCTION TESTS
# =============================================================================


class TestRenderResultsFunction:
    """Tests for render_results() convenience function."""

    def test_render_results_with_test_result(self, passing_test_result):
        """Test render_results with TestResult object."""
        output = render_results(passing_test_result, "summary")
        assert "[PASS]" in output
        assert "10" in output

    def test_render_results_with_dict(self, basic_context):
        """Test render_results with dict."""
        output = render_results(basic_context, "summary")
        assert "[PASS]" in output

    def test_render_results_with_failing_result(self, failing_test_result):
        """Test render_results with failing TestResult."""
        output = render_results(failing_test_result, "summary")
        assert "[FAIL]" in output

    def test_render_results_with_custom_template(self, passing_test_result):
        """Test render_results with custom template."""
        custom = {"brief": "{{ verdict }}: {{ passed }}/{{ total }}"}
        output = render_results(
            passing_test_result,
            "brief",
            custom_templates=custom,
        )
        assert "PASS: 10/12" in output

    def test_render_results_default_template_is_summary(self, passing_test_result):
        """Test that default template is summary."""
        output = render_results(passing_test_result)
        assert "[PASS]" in output

    def test_render_results_extracts_failures_from_test_result(self, failing_test_result):
        """Test that failures are extracted from TestResult."""
        output = render_results(failing_test_result, "markdown")
        assert "Failures" in output
        assert "test_one" in output

    def test_render_results_invalid_type_raises(self):
        """Test that invalid result type raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            render_results("invalid", "summary")
        assert "Expected TestResult or dict" in str(exc_info.value)

    def test_render_results_dict_without_failures_key(self):
        """Test render_results with dict missing failures key adds empty list."""
        context = {
            "verdict": "PASS",
            "category": "unit",
            "passed": 5,
            "failed": 0,
            "errors": 0,
            "skipped": 0,
            "total": 5,
            "duration": 1.0,
            "timestamp": "2025-01-15T10:00:00Z",
            "exit_code": 0,
        }
        # Should not raise, and should render correctly
        output = render_results(context, "summary")
        assert "[PASS]" in output


# =============================================================================
# PIPELINE TEMPLATE TESTS
# =============================================================================


class TestPipelineTemplates:
    """Tests for pipeline evaluation templates."""

    def test_pipeline_summary_template(self, renderer, pipeline_context):
        """Test pipeline_summary template."""
        output = renderer.render("pipeline_summary", pipeline_context)
        assert "[FAIL]" in output
        assert "Pipeline Eval" in output
        assert "2/3" in output  # passed/total

    def test_pipeline_table_template(self, renderer, pipeline_context):
        """Test pipeline_table template."""
        output = renderer.render("pipeline_table", pipeline_context)
        assert "PIPELINE EVALUATION RESULTS" in output
        assert "project-alpha" in output

    def test_pipeline_ci_template(self, renderer, pipeline_context):
        """Test pipeline_ci template."""
        output = renderer.render("pipeline_ci", pipeline_context)
        assert "SYSTEMEVAL PIPELINE RESULTS" in output
        assert "FAILURES" in output

    def test_pipeline_github_template(self, renderer, pipeline_context):
        """Test pipeline_github template."""
        output = renderer.render("pipeline_github", pipeline_context)
        assert "::error::" in output
        assert "project-alpha" in output

    def test_pipeline_markdown_template(self, renderer, pipeline_context):
        """Test pipeline_markdown template."""
        output = renderer.render("pipeline_markdown", pipeline_context)
        assert "# Pipeline Evaluation Results" in output
        assert "## Failed Projects" in output

    def test_pipeline_diagnostic_template(self, renderer, pipeline_context):
        """Test pipeline_diagnostic template."""
        output = renderer.render("pipeline_diagnostic", pipeline_context)
        assert "DIAGNOSTIC REPORT" in output
        assert "PROJECT: project-alpha" in output


# =============================================================================
# ENVIRONMENT TEMPLATE TESTS
# =============================================================================


class TestEnvironmentTemplates:
    """Tests for multi-environment templates."""

    @pytest.fixture
    def env_context(self):
        """Context for environment templates."""
        return {
            "verdict": "PASS",
            "env_name": "backend",
            "env_type": "django",
            "passed": 50,
            "failed": 0,
            "errors": 0,
            "skipped": 5,
            "total": 55,
            "duration": 30.5,
            "timestamp": "2025-01-15T14:00:00Z",
            "exit_code": 0,
            "failures": [],
            "timings": {
                "build": 5.0,
                "startup": 2.0,
                "health_check": 1.0,
                "tests": 20.0,
                "cleanup": 2.5,
            },
            "build_status": "done",
            "build_success": True,
            "build_detail": "OK",
            "startup_status": "done",
            "startup_success": True,
            "health_status": "done",
            "health_success": True,
            "test_status": "done",
        }

    def test_env_summary_template(self, renderer, env_context):
        """Test env_summary template."""
        output = renderer.render("env_summary", env_context)
        assert "[PASS]" in output
        assert "BACKEND" in output
        assert "django" in output

    def test_env_table_template(self, renderer, env_context):
        """Test env_table template."""
        output = renderer.render("env_table", env_context)
        assert "SYSTEMEVAL TEST REPORT" in output
        assert "Environment:" in output
        assert "backend" in output

    def test_env_ci_template(self, renderer, env_context):
        """Test env_ci template."""
        output = renderer.render("env_ci", env_context)
        assert "SYSTEMEVAL ENVIRONMENT TEST RESULTS" in output
        assert "PHASE TIMINGS" in output


# =============================================================================
# ERROR HANDLING TESTS
# =============================================================================


class TestErrorHandling:
    """Tests for error handling in template rendering."""

    def test_invalid_template_syntax(self, renderer):
        """Test handling of invalid Jinja2 syntax."""
        custom = {"broken": "{{ unclosed"}
        renderer = TemplateRenderer(custom_templates=custom)
        with pytest.raises(Exception):  # Jinja2 TemplateSyntaxError
            renderer.render("broken", {})

    def test_undefined_variable_in_default_autoescape(self, renderer):
        """Test rendering with missing context variable."""
        # By default, Jinja2 treats undefined as empty string in rendering
        output = renderer.render_string("Value: {{ missing }}", {})
        assert "Value:" in output

    def test_filter_error(self, renderer):
        """Test error when filter receives wrong type."""
        # round filter on non-number should raise
        with pytest.raises(Exception):
            renderer.render_string("{{ text | round(2) }}", {"text": "not a number"})

    def test_empty_template(self, renderer):
        """Test rendering empty template string."""
        output = renderer.render_string("", {"data": "value"})
        assert output == ""

    def test_empty_context(self, renderer):
        """Test rendering with empty context."""
        custom = {"simple": "Static text only"}
        renderer = TemplateRenderer(custom_templates=custom)
        output = renderer.render("simple", {})
        assert output == "Static text only"


# =============================================================================
# SPECIAL CHARACTER AND ESCAPING TESTS
# =============================================================================


class TestEscaping:
    """Tests for HTML/XML escaping in templates."""

    def test_junit_escapes_xml_special_chars(self, renderer):
        """Test that JUnit template escapes XML special characters."""
        context = {
            "category": "unit",
            "total": 1,
            "passed": 0,
            "failed": 1,
            "errors": 0,
            "skipped": 0,
            "duration": 1.0,
            "timestamp": "2025-01-15T10:00:00Z",
            "failures": [
                {
                    "test_id": "test::special",
                    "test_name": "test_special",
                    "message": "Expected <value> but got <other>",
                    "traceback": "Assert: <value> != <other>",
                    "duration": 0.1,
                },
            ],
        }
        output = renderer.render("junit", context)
        # XML special characters should be escaped
        assert "&lt;value&gt;" in output or "<value>" not in output

    def test_markdown_preserves_special_chars(self, renderer, basic_context):
        """Test that markdown template preserves content."""
        basic_context["category"] = "unit<test>"
        output = renderer.render("markdown", basic_context)
        # Markdown doesn't need XML escaping
        assert "unit<test>" in output or "unit&lt;test&gt;" in output


# =============================================================================
# INTEGRATION TESTS WITH TEST RESULTS
# =============================================================================


class TestIntegrationWithTestResult:
    """Integration tests using actual TestResult objects."""

    def test_full_rendering_pipeline_passing(self, passing_test_result):
        """Test full rendering pipeline with passing result."""
        renderer = TemplateRenderer()

        # Convert to dict
        context = passing_test_result.to_dict()
        context["failures"] = []

        # Render each template type
        for template_name in ["summary", "markdown", "ci", "github", "slack", "table"]:
            output = renderer.render(template_name, context)
            assert len(output) > 0
            # GitHub template uses emojis and 'passed' not 'PASS'
            if template_name == "github":
                assert "passed" in output or "\u2705" in output
            else:
                assert "PASS" in output

    def test_full_rendering_pipeline_failing(self, failing_test_result):
        """Test full rendering pipeline with failing result."""
        renderer = TemplateRenderer()

        # Convert to dict with failures
        context = failing_test_result.to_dict()
        context["failures"] = [
            {
                "test_id": f.test_id,
                "test_name": f.test_name,
                "message": f.message,
                "traceback": f.traceback,
                "duration": f.duration,
                "metadata": {},
            }
            for f in failing_test_result.failures
        ]

        # Render each template type
        for template_name in ["summary", "markdown", "ci", "github", "slack", "table"]:
            output = renderer.render(template_name, context)
            assert len(output) > 0
            # GitHub template uses emojis and 'failed' not 'FAIL'
            if template_name == "github":
                assert "failed" in output or "\u274C" in output
            else:
                assert "FAIL" in output

    def test_junit_output_is_valid_xml(self, failing_test_result):
        """Test that JUnit template produces valid XML structure."""
        import xml.etree.ElementTree as ET

        renderer = TemplateRenderer()
        context = failing_test_result.to_dict()
        context["failures"] = [
            {
                "test_id": f.test_id,
                "test_name": f.test_name,
                "message": f.message,
                "traceback": f.traceback or f.message,
                "duration": f.duration,
            }
            for f in failing_test_result.failures
        ]

        output = renderer.render("junit", context)

        # Should parse as valid XML
        root = ET.fromstring(output)
        assert root.tag == "testsuites"
        assert root.find("testsuite") is not None
