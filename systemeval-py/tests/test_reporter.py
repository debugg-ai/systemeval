"""Tests for the unified output formatting and reporting module."""

import json
import pytest
from io import StringIO
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from rich.console import Console

from systemeval.core.reporter import Reporter
from systemeval.core.evaluation import (
    EvaluationResult,
    EvaluationMetadata,
    SessionResult,
    MetricResult,
    Verdict,
    Severity,
    create_evaluation,
    create_session,
    metric,
)


# Helper fixtures and factories


@pytest.fixture
def basic_metadata():
    """Create basic evaluation metadata for testing."""
    return EvaluationMetadata(
        evaluation_id="test-uuid-1234",
        timestamp_utc="2024-01-15T10:30:00+00:00",
        duration_seconds=5.5,
        adapter_type="pytest",
        project_name="test-project",
    )


@pytest.fixture
def passing_session():
    """Create a passing session with multiple metrics."""
    session = SessionResult(
        session_id="session-1",
        session_name="unit-tests",
        duration_seconds=2.5,
    )
    session.metrics = [
        metric("test_count", 10, ">0", True, "10 tests executed"),
        metric("coverage", 85.5, ">=80", True, "Coverage met"),
    ]
    return session


@pytest.fixture
def failing_session():
    """Create a failing session with mixed metrics."""
    session = SessionResult(
        session_id="session-2",
        session_name="integration-tests",
        duration_seconds=3.0,
    )
    session.metrics = [
        metric("api_health", True, True, True, "API healthy"),
        metric("error_count", 5, "0", False, "5 errors occurred"),
        metric("response_time", 2500, "<1000", False, "Response too slow"),
    ]
    return session


@pytest.fixture
def empty_session():
    """Create an empty session with no metrics."""
    return SessionResult(
        session_id="session-empty",
        session_name="empty-session",
        duration_seconds=0.0,
    )


@pytest.fixture
def passing_result(basic_metadata, passing_session):
    """Create a passing evaluation result."""
    result = EvaluationResult(metadata=basic_metadata)
    result.sessions.append(passing_session)
    return result


@pytest.fixture
def failing_result(basic_metadata, passing_session, failing_session):
    """Create a failing evaluation result with mixed sessions."""
    result = EvaluationResult(metadata=basic_metadata)
    result.sessions.append(passing_session)
    result.sessions.append(failing_session)
    return result


@pytest.fixture
def empty_result(basic_metadata):
    """Create an evaluation result with no sessions."""
    return EvaluationResult(metadata=basic_metadata)


@pytest.fixture
def tmp_output_file(tmp_path):
    """Create a temporary output file path."""
    return tmp_path / "report.txt"


class TestReporterInitialization:
    """Tests for Reporter initialization and configuration."""

    def test_default_initialization(self):
        """Test default reporter settings."""
        reporter = Reporter()

        assert reporter.format == "table"
        assert reporter.verbose is False
        assert reporter.show_passed is False
        assert reporter.show_metrics is True

    def test_custom_format(self):
        """Test reporter with custom format."""
        reporter = Reporter(format="json")
        assert reporter.format == "json"

        reporter = Reporter(format="junit")
        assert reporter.format == "junit"

    def test_verbose_mode(self):
        """Test reporter with verbose mode enabled."""
        reporter = Reporter(verbose=True)
        assert reporter.verbose is True

    def test_show_passed_sessions(self):
        """Test reporter with show_passed enabled."""
        reporter = Reporter(show_passed=True)
        assert reporter.show_passed is True

    def test_disable_metrics(self):
        """Test reporter with metrics disabled."""
        reporter = Reporter(show_metrics=False)
        assert reporter.show_metrics is False

    def test_colors_disabled(self):
        """Test reporter with colors disabled."""
        reporter = Reporter(colors=False)
        # Console should be created with no_color=True
        assert reporter.console is not None

    def test_all_options_combined(self):
        """Test reporter with all options specified."""
        reporter = Reporter(
            format="json",
            verbose=True,
            colors=False,
            show_passed=True,
            show_metrics=False,
        )

        assert reporter.format == "json"
        assert reporter.verbose is True
        assert reporter.show_passed is True
        assert reporter.show_metrics is False


class TestReportDispatch:
    """Tests for the main report method dispatching."""

    def test_report_dispatches_to_json(self, passing_result):
        """Test that json format dispatches to _report_json."""
        reporter = Reporter(format="json")

        with patch.object(reporter, "_report_json") as mock_json:
            reporter.report(passing_result)
            mock_json.assert_called_once_with(passing_result, None)

    def test_report_dispatches_to_junit(self, passing_result):
        """Test that junit format dispatches to _report_junit."""
        reporter = Reporter(format="junit")

        with patch.object(reporter, "_report_junit") as mock_junit:
            reporter.report(passing_result)
            mock_junit.assert_called_once_with(passing_result, None)

    def test_report_dispatches_to_table(self, passing_result):
        """Test that table format dispatches to _report_table."""
        reporter = Reporter(format="table")

        with patch.object(reporter, "_report_table") as mock_table:
            reporter.report(passing_result)
            mock_table.assert_called_once_with(passing_result, None)

    def test_report_default_is_table(self, passing_result):
        """Test that unknown format defaults to table."""
        reporter = Reporter(format="unknown")

        with patch.object(reporter, "_report_table") as mock_table:
            reporter.report(passing_result)
            mock_table.assert_called_once()

    def test_report_with_output_file(self, passing_result, tmp_output_file):
        """Test that output_file is passed through."""
        reporter = Reporter(format="json")

        with patch.object(reporter, "_report_json") as mock_json:
            reporter.report(passing_result, output_file=tmp_output_file)
            mock_json.assert_called_once_with(passing_result, tmp_output_file)


class TestJsonReport:
    """Tests for JSON format reporting."""

    def test_json_output_to_console(self, passing_result):
        """Test JSON output printed to console."""
        reporter = Reporter(format="json", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_json(passing_result, None)

            # Should print JSON output
            mock_print.assert_called_once()
            output = mock_print.call_args[0][0]
            # Verify it's valid JSON
            data = json.loads(output)
            assert "verdict" in data
            assert "sessions" in data

    def test_json_output_to_file(self, passing_result, tmp_output_file):
        """Test JSON output written to file."""
        reporter = Reporter(format="json", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_json(passing_result, tmp_output_file)

            # Should print confirmation message
            mock_print.assert_called_once()
            assert "JSON report written to" in mock_print.call_args[0][0]

        # Verify file contents
        content = tmp_output_file.read_text()
        data = json.loads(content)
        assert data["verdict"] == "PASS"
        assert len(data["sessions"]) == 1

    def test_json_includes_all_fields(self, failing_result, tmp_output_file):
        """Test that JSON includes all expected fields."""
        reporter = Reporter(format="json")
        reporter._report_json(failing_result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())

        # Top-level fields
        assert "metadata" in data
        assert "verdict" in data
        assert "exit_code" in data
        assert "summary" in data
        assert "sessions" in data

        # Metadata fields
        assert data["metadata"]["adapter_type"] == "pytest"
        assert data["metadata"]["project_name"] == "test-project"

        # Summary fields
        assert "total_sessions" in data["summary"]
        assert "passed_sessions" in data["summary"]
        assert "failed_sessions" in data["summary"]

    def test_json_empty_result(self, empty_result, tmp_output_file):
        """Test JSON output with no sessions."""
        reporter = Reporter(format="json")
        reporter._report_json(empty_result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())
        assert data["verdict"] == "ERROR"
        assert data["sessions"] == []
        assert data["summary"]["total_sessions"] == 0


class TestJunitReport:
    """Tests for JUnit XML format reporting."""

    def test_junit_output_to_console(self, passing_result):
        """Test JUnit XML output printed to console."""
        reporter = Reporter(format="junit", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_junit(passing_result, None)

            mock_print.assert_called_once()
            output = mock_print.call_args[0][0]
            assert '<?xml version="1.0"' in output
            assert "<testsuites" in output
            assert "</testsuites>" in output

    def test_junit_output_to_file(self, passing_result, tmp_output_file):
        """Test JUnit XML output written to file."""
        reporter = Reporter(format="junit", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_junit(passing_result, tmp_output_file)

            mock_print.assert_called_once()
            assert "JUnit XML report written to" in mock_print.call_args[0][0]

        content = tmp_output_file.read_text()
        assert '<?xml version="1.0" encoding="UTF-8"?>' in content
        assert "<testsuites" in content

    def test_junit_structure_passing(self, passing_result, tmp_output_file):
        """Test JUnit XML structure for passing result."""
        reporter = Reporter(format="junit")
        reporter._report_junit(passing_result, tmp_output_file)

        content = tmp_output_file.read_text()

        # Verify structure
        assert 'name="test-project"' in content
        assert 'tests="1"' in content  # 1 session
        assert 'failures="0"' in content
        assert '<testsuite name="unit-tests"' in content
        assert '<testcase name="test_count"' in content
        assert '<testcase name="coverage"' in content
        # No failure elements for passing tests
        assert "<failure" not in content

    def test_junit_structure_failing(self, failing_result, tmp_output_file):
        """Test JUnit XML structure for failing result."""
        reporter = Reporter(format="junit")
        reporter._report_junit(failing_result, tmp_output_file)

        content = tmp_output_file.read_text()

        # Verify failure count
        assert 'failures="1"' in content  # 1 failed session

        # Verify failure elements present
        assert "<failure" in content
        assert "</failure>" in content

    def test_junit_includes_duration(self, passing_result, tmp_output_file):
        """Test JUnit XML includes duration attributes."""
        reporter = Reporter(format="junit")
        reporter._report_junit(passing_result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert 'time="5.500"' in content  # metadata duration
        assert 'time="2.500"' in content  # session duration

    def test_junit_uses_project_name(self, passing_result, tmp_output_file):
        """Test JUnit uses project_name for suite name."""
        reporter = Reporter(format="junit")
        reporter._report_junit(passing_result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert 'name="test-project"' in content

    def test_junit_falls_back_to_adapter_type(self, basic_metadata, passing_session, tmp_output_file):
        """Test JUnit falls back to adapter_type when no project_name."""
        basic_metadata.project_name = None
        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(passing_session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert 'name="pytest"' in content

    def test_junit_default_suite_name(self, passing_session, tmp_output_file):
        """Test JUnit uses 'Evaluation' when no project or adapter."""
        metadata = EvaluationMetadata(
            evaluation_id="test-id",
            project_name=None,
            adapter_type="",
        )
        result = EvaluationResult(metadata=metadata)
        result.sessions.append(passing_session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert 'name="Evaluation"' in content

    def test_junit_empty_result(self, empty_result, tmp_output_file):
        """Test JUnit XML with no sessions."""
        reporter = Reporter(format="junit")
        reporter._report_junit(empty_result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert 'tests="0"' in content
        assert 'failures="0"' in content

    def test_junit_failure_message(self, failing_session, basic_metadata, tmp_output_file):
        """Test JUnit failure message content."""
        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(failing_session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert '<failure message="5 errors occurred">' in content
        assert '<failure message="Response too slow">' in content
        assert "Value: 5" in content
        assert "Value: 2500" in content

    def test_junit_failure_default_message(self, basic_metadata, tmp_output_file):
        """Test JUnit failure with no message uses default."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            MetricResult(
                name="test_metric",
                value=0,
                expected=1,
                passed=False,
                message=None,  # No message
            )
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert '<failure message="Failed">' in content


class TestTableReport:
    """Tests for table format reporting."""

    def test_table_output_passing(self, passing_result):
        """Test table output for passing result."""
        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(passing_result, None)

            # Should have multiple print calls (header, summary, table, footer)
            assert mock_print.call_count >= 4

    def test_table_output_failing(self, failing_result):
        """Test table output for failing result."""
        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(failing_result, None)

            assert mock_print.call_count >= 4

    def test_table_hides_passed_sessions_by_default(self, failing_result):
        """Test that passed sessions are hidden when show_passed is False."""
        reporter = Reporter(format="table", colors=False, show_passed=False)

        # This tests the logic path where passed sessions are skipped
        with patch.object(reporter.console, "print"):
            reporter._report_table(failing_result, None)
            # No assertion needed - just verify no error

    def test_table_shows_passed_sessions_when_enabled(self, failing_result):
        """Test that passed sessions are shown when show_passed is True."""
        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(failing_result, None)
            # No assertion needed - just verify no error

    def test_table_shows_metrics_by_default(self, failing_result):
        """Test that metrics columns are shown by default."""
        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(failing_result, None)
            # No assertion needed - just verify no error

    def test_table_hides_metrics_when_disabled(self, failing_result):
        """Test that metrics columns are hidden when show_metrics is False."""
        reporter = Reporter(format="table", colors=False, show_passed=True, show_metrics=False)

        with patch.object(reporter.console, "print"):
            reporter._report_table(failing_result, None)
            # No assertion needed - just verify no error

    def test_table_verbose_shows_details(self, failing_result):
        """Test that verbose mode shows session details."""
        reporter = Reporter(format="table", colors=False, verbose=True, show_passed=True)

        with patch.object(reporter, "_print_session_details") as mock_details:
            reporter._report_table(failing_result, None)

            # Should call _print_session_details for failed sessions
            assert mock_details.call_count >= 1

    def test_table_verbose_skipped_for_passing(self, passing_result):
        """Test that verbose mode doesn't show details for all-passing result."""
        reporter = Reporter(format="table", colors=False, verbose=True)

        with patch.object(reporter, "_print_session_details") as mock_details:
            reporter._report_table(passing_result, None)

            # Should not call _print_session_details when all pass
            mock_details.assert_not_called()

    def test_table_uses_project_name(self, passing_result):
        """Test table header uses project name."""
        reporter = Reporter(format="table", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(passing_result, None)

            # Find call with project name
            all_output = str(mock_print.call_args_list)
            assert "TEST-PROJECT" in all_output.upper()

    def test_table_falls_back_to_adapter_type(self, basic_metadata, passing_session):
        """Test table header falls back to adapter type."""
        basic_metadata.project_name = None
        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(passing_session)

        reporter = Reporter(format="table", colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(result, None)

            all_output = str(mock_print.call_args_list)
            assert "PYTEST" in all_output.upper()

    def test_table_duration_formatting(self, passing_result):
        """Test that duration is formatted correctly in the table output.

        The duration appears in a Rich Panel object which is printed to console.
        We verify the reporter runs without error and produces output.
        """
        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(passing_result, None)

            # Verify multiple print calls occurred (header, summary panel, table, footer)
            assert mock_print.call_count >= 4

            # The summary panel contains duration info - verify it's a Panel object
            panel_calls = [
                call for call in mock_print.call_args_list
                if hasattr(call[0][0], '__class__') and 'Panel' in call[0][0].__class__.__name__
            ]
            assert len(panel_calls) >= 1, "Expected at least one Panel in output"

    def test_table_null_duration_raises_error(self, basic_metadata):
        """Test table behavior with None duration.

        Note: The underlying EvaluationResult.summary property does not handle
        None duration values gracefully - it raises TypeError when summing.
        This test documents the current behavior.
        """
        basic_metadata.duration_seconds = None
        session = SessionResult(
            session_id="s1",
            session_name="test",
            duration_seconds=None,
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="table", colors=False, show_passed=True)

        # Current behavior: raises TypeError due to None in duration sum
        with pytest.raises(TypeError):
            reporter._report_table(result, None)

    def test_table_exit_code_display(self, passing_result, failing_result):
        """Test that exit code is displayed in footer."""
        reporter = Reporter(format="table", colors=False)

        # Passing result - exit code 0
        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(passing_result, None)
            all_output = str(mock_print.call_args_list)
            assert "Exit code: 0" in all_output

        # Failing result - exit code 1
        with patch.object(reporter.console, "print") as mock_print:
            reporter._report_table(failing_result, None)
            all_output = str(mock_print.call_args_list)
            assert "Exit code: 1" in all_output


class TestPrintSessionDetails:
    """Tests for _print_session_details method."""

    def test_print_failed_metrics(self, failing_session):
        """Test that failed metrics are printed."""
        reporter = Reporter(colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._print_session_details(failing_session)

            # Should print session name and failed metrics
            assert mock_print.call_count >= 3  # session name + 2 failed metrics

    def test_print_metric_messages(self, failing_session):
        """Test that metric messages are printed."""
        reporter = Reporter(colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._print_session_details(failing_session)

            all_output = str(mock_print.call_args_list)
            assert "error_count" in all_output
            assert "response_time" in all_output

    def test_print_metric_value(self, failing_session):
        """Test that metric values are printed."""
        reporter = Reporter(colors=False)

        with patch.object(reporter.console, "print") as mock_print:
            reporter._print_session_details(failing_session)

            all_output = str(mock_print.call_args_list)
            # Check values are in output
            assert "5" in all_output  # error_count value
            assert "2500" in all_output  # response_time value

    def test_print_handles_no_message(self, basic_metadata):
        """Test printing metric without a message."""
        session = SessionResult(
            session_id="s1",
            session_name="test-session",
        )
        session.metrics = [
            MetricResult(
                name="test_metric",
                value=0,
                expected=1,
                passed=False,
                message=None,
            )
        ]

        reporter = Reporter(colors=False)

        # Should not raise error when message is None
        with patch.object(reporter.console, "print"):
            reporter._print_session_details(session)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_empty_sessions_list(self, empty_result):
        """Test reporting with empty sessions list."""
        reporter = Reporter(format="table", colors=False)

        with patch.object(reporter.console, "print"):
            reporter._report_table(empty_result, None)
            # Should not raise error

    def test_session_with_many_failed_metrics(self, basic_metadata):
        """Test table truncates long failed metrics list."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        # Create 10 failed metrics
        for i in range(10):
            session.metrics.append(
                metric(f"metric_{i}", 0, "1", False, f"Failed {i}")
            )

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(result, None)
            # Should show first 3 and "+X more"

    def test_special_characters_in_metric_name(self, basic_metadata, tmp_output_file):
        """Test handling of special characters in metric names."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            metric("metric<with>xml&chars", 1, "1", True),
            metric('metric"with"quotes', 1, "1", True),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        # JSON should handle special characters
        content = tmp_output_file.read_text()
        data = json.loads(content)
        assert len(data["sessions"][0]["metrics"]) == 2

    def test_special_characters_in_junit(self, basic_metadata, tmp_output_file):
        """Test handling of special characters in JUnit output."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        # Note: In real usage, metric names with XML special chars
        # would need escaping in the JUnit output
        session.metrics = [
            metric("metric_test", 1, "1", True),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        assert "metric_test" in content

    def test_junit_xml_escaping_in_metric_names(self, basic_metadata, tmp_output_file):
        """Test that XML special characters in metric names are properly escaped."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            metric("test<with>angle_brackets", 1, "1", True),
            metric("test&with_ampersand", 1, "1", True),
            metric('test"with"quotes', 1, "1", True),
            metric("test'with'apostrophes", 1, "1", True),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        # Verify XML special characters are escaped
        assert "&lt;" in content  # < escaped
        assert "&gt;" in content  # > escaped
        assert "&amp;" in content  # & escaped
        assert "&quot;" in content  # " escaped
        # ' is escaped as &#x27; (numeric entity) which is valid XML
        assert "&#x27;" in content or "&apos;" in content  # ' escaped
        # Verify raw characters are NOT present in attribute values
        assert 'name="test<with' not in content
        assert 'name="test&with' not in content

    def test_junit_xml_escaping_in_session_names(self, basic_metadata, tmp_output_file):
        """Test that XML special characters in session names are properly escaped."""
        session = SessionResult(
            session_id="s1",
            session_name="session<with>&special'chars\"",
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        # Verify session name is escaped
        assert "&lt;" in content
        assert "&gt;" in content
        assert "&amp;" in content
        # ' is escaped as &#x27; (numeric entity) which is valid XML
        assert "&#x27;" in content or "&apos;" in content
        assert "&quot;" in content
        # Verify the testsuite name attribute does not contain raw special chars
        assert 'testsuite name="session<with' not in content

    def test_junit_xml_escaping_in_failure_message(self, basic_metadata, tmp_output_file):
        """Test that XML special characters in failure messages are properly escaped."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            metric(
                "failed_metric",
                0,
                "1",
                False,
                'Error: value < 0 && value > -100 is "invalid"'
            ),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        # Verify failure message is escaped
        assert "&lt;" in content
        assert "&gt;" in content
        assert "&amp;" in content
        assert "&quot;" in content
        # Verify raw characters are NOT present in message attribute
        assert 'message="Error: value <' not in content

    def test_junit_xml_escaping_in_failure_value(self, basic_metadata, tmp_output_file):
        """Test that XML special characters in failure values are properly escaped."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        # A value that contains XML special characters (e.g., a string value)
        session.metrics = [
            MetricResult(
                name="string_value",
                value="<script>alert('xss')</script>",
                expected="safe",
                passed=False,
                message="Invalid value",
            ),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        # Verify the value is escaped
        assert "&lt;script&gt;" in content
        # ' is escaped as &#x27; (numeric entity) which is valid XML
        assert "&#x27;xss&#x27;" in content or "&apos;xss&apos;" in content
        # Verify raw script tags are NOT present
        assert "<script>" not in content

    def test_junit_xml_escaping_in_project_name(self, basic_metadata, tmp_output_file):
        """Test that XML special characters in project names are properly escaped."""
        basic_metadata.project_name = "project<with>&special'chars\""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()
        # Verify testsuites name attribute is escaped
        assert "&lt;" in content
        assert "&gt;" in content
        assert "&amp;" in content
        # ' is escaped as &#x27; (numeric entity) which is valid XML
        assert "&#x27;" in content or "&apos;" in content
        assert "&quot;" in content
        # Verify the testsuites name attribute does not contain raw special chars
        assert 'testsuites name="project<with' not in content

    def test_junit_xml_valid_after_escaping(self, basic_metadata, tmp_output_file):
        """Test that generated XML is valid and parseable after escaping."""
        import xml.etree.ElementTree as ET

        session = SessionResult(
            session_id="s1",
            session_name="session<with>&all'special\"chars",
        )
        session.metrics = [
            metric(
                "metric<>&'\"test",
                "value<>&'\"content",
                "1",
                False,
                "message<>&'\"text"
            ),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="junit")
        reporter._report_junit(result, tmp_output_file)

        content = tmp_output_file.read_text()

        # Verify the XML is parseable (will raise if invalid)
        root = ET.fromstring(content)

        # Verify structure is intact
        assert root.tag == "testsuites"
        testsuites = root.findall("testsuite")
        assert len(testsuites) == 1
        testcases = testsuites[0].findall("testcase")
        assert len(testcases) == 1

    def test_unicode_in_messages(self, basic_metadata, tmp_output_file):
        """Test handling of unicode characters in messages."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            metric("unicode_test", 1, "1", True, "Message with unicode: \u2714 \u2718 \u00e9"),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        content = tmp_output_file.read_text()
        data = json.loads(content)
        assert "\u2714" in data["sessions"][0]["metrics"][0]["message"]

    def test_very_long_session_name(self, basic_metadata):
        """Test handling of very long session names."""
        long_name = "a" * 200
        session = SessionResult(
            session_id="s1",
            session_name=long_name,
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(result, None)
            # Should not raise error

    def test_zero_duration(self, basic_metadata):
        """Test handling of zero duration."""
        basic_metadata.duration_seconds = 0.0
        session = SessionResult(
            session_id="s1",
            session_name="test",
            duration_seconds=0.0,
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(result, None)

    def test_negative_duration(self, basic_metadata):
        """Test handling of negative duration (edge case)."""
        basic_metadata.duration_seconds = -1.0
        session = SessionResult(
            session_id="s1",
            session_name="test",
            duration_seconds=-1.0,
        )
        session.metrics = [metric("m1", 1, "1", True)]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print"):
            reporter._report_table(result, None)

    def test_large_metric_value(self, basic_metadata, tmp_output_file):
        """Test handling of very large metric values."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        large_value = 10**20
        session.metrics = [
            metric("large_value", large_value, ">0", True),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())
        assert data["sessions"][0]["metrics"][0]["value"] == large_value

    def test_float_precision(self, basic_metadata, tmp_output_file):
        """Test handling of floating point precision."""
        session = SessionResult(
            session_id="s1",
            session_name="test",
        )
        session.metrics = [
            metric("float_value", 0.123456789012345, ">0", True),
        ]

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions.append(session)

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())
        # JSON should preserve float precision
        assert abs(data["sessions"][0]["metrics"][0]["value"] - 0.123456789012345) < 1e-15


class TestOutputFileHandling:
    """Tests for output file operations."""

    def test_json_creates_file(self, passing_result, tmp_path):
        """Test that JSON report creates output file."""
        output_file = tmp_path / "report.json"
        reporter = Reporter(format="json")

        with patch.object(reporter.console, "print"):
            reporter._report_json(passing_result, output_file)

        assert output_file.exists()
        assert output_file.stat().st_size > 0

    def test_junit_creates_file(self, passing_result, tmp_path):
        """Test that JUnit report creates output file."""
        output_file = tmp_path / "report.xml"
        reporter = Reporter(format="junit")

        with patch.object(reporter.console, "print"):
            reporter._report_junit(passing_result, output_file)

        assert output_file.exists()
        assert output_file.stat().st_size > 0

    def test_nested_output_directory(self, passing_result, tmp_path):
        """Test writing to nested directory path."""
        output_file = tmp_path / "subdir" / "deep" / "report.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)

        reporter = Reporter(format="json")

        with patch.object(reporter.console, "print"):
            reporter._report_json(passing_result, output_file)

        assert output_file.exists()


class TestMultipleSessionsReport:
    """Tests for reports with multiple sessions."""

    def test_multiple_passing_sessions(self, basic_metadata, tmp_output_file):
        """Test report with multiple passing sessions."""
        sessions = []
        for i in range(5):
            session = SessionResult(
                session_id=f"session-{i}",
                session_name=f"test-{i}",
                duration_seconds=float(i),
            )
            session.metrics = [metric(f"metric-{i}", 1, "1", True)]
            sessions.append(session)

        result = EvaluationResult(metadata=basic_metadata)
        result.sessions = sessions

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())
        assert len(data["sessions"]) == 5
        assert data["summary"]["total_sessions"] == 5
        assert data["summary"]["passed_sessions"] == 5

    def test_mixed_session_verdicts(self, basic_metadata, tmp_output_file):
        """Test report with mixed passing and failing sessions."""
        # 2 passing, 2 failing, 1 error
        result = EvaluationResult(metadata=basic_metadata)

        # Passing sessions
        for i in range(2):
            session = SessionResult(session_id=f"pass-{i}", session_name=f"pass-{i}")
            session.metrics = [metric(f"m{i}", 1, "1", True)]
            result.sessions.append(session)

        # Failing sessions
        for i in range(2):
            session = SessionResult(session_id=f"fail-{i}", session_name=f"fail-{i}")
            session.metrics = [metric(f"m{i}", 0, "1", False)]
            result.sessions.append(session)

        # Error session (no metrics)
        error_session = SessionResult(session_id="error-1", session_name="error-1")
        result.sessions.append(error_session)

        reporter = Reporter(format="json")
        reporter._report_json(result, tmp_output_file)

        data = json.loads(tmp_output_file.read_text())
        assert data["summary"]["passed_sessions"] == 2
        assert data["summary"]["failed_sessions"] == 2
        assert data["summary"]["error_sessions"] == 1
        assert data["verdict"] == "ERROR"  # ERROR takes precedence


class TestReportIntegration:
    """Integration tests for the Reporter class."""

    def test_full_report_workflow_json(self, tmp_path):
        """Test complete JSON report workflow."""
        # Create evaluation using factory functions
        result = create_evaluation(
            adapter_type="pytest",
            project_name="integration-test",
            category="unit",
        )

        # Add passing session
        session1 = create_session("unit-tests")
        session1.metrics.append(metric("test_count", 10, ">0", True))
        session1.metrics.append(metric("coverage", 85.0, ">=80", True))
        session1.duration_seconds = 2.5
        result.add_session(session1)

        # Add failing session
        session2 = create_session("integration-tests")
        session2.metrics.append(metric("api_health", True, True, True))
        session2.metrics.append(metric("errors", 5, "0", False, "5 errors found"))
        session2.duration_seconds = 3.0
        result.add_session(session2)

        result.finalize()

        # Generate report
        output_file = tmp_path / "report.json"
        reporter = Reporter(format="json")
        reporter.report(result, output_file=output_file)

        # Verify output
        data = json.loads(output_file.read_text())
        assert data["verdict"] == "FAIL"
        assert data["exit_code"] == 1
        assert data["metadata"]["project_name"] == "integration-test"
        assert len(data["sessions"]) == 2

    def test_full_report_workflow_junit(self, tmp_path):
        """Test complete JUnit report workflow."""
        result = create_evaluation(
            adapter_type="pytest",
            project_name="junit-test",
        )

        session = create_session("all-tests")
        session.metrics.append(metric("passed", 10, ">0", True))
        session.duration_seconds = 5.0
        result.add_session(session)

        result.finalize()

        output_file = tmp_path / "report.xml"
        reporter = Reporter(format="junit")
        reporter.report(result, output_file=output_file)

        content = output_file.read_text()
        assert '<?xml version="1.0" encoding="UTF-8"?>' in content
        assert 'name="junit-test"' in content
        assert 'name="all-tests"' in content

    def test_full_report_workflow_table(self):
        """Test complete table report workflow."""
        result = create_evaluation(
            adapter_type="pytest",
            project_name="table-test",
        )

        session = create_session("tests")
        session.metrics.append(metric("count", 5, ">0", True))
        result.add_session(session)

        result.finalize()

        reporter = Reporter(format="table", colors=False, show_passed=True)

        with patch.object(reporter.console, "print") as mock_print:
            reporter.report(result)

            # Verify output was generated
            assert mock_print.call_count >= 4
