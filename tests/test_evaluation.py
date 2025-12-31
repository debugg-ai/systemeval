"""Tests for the unified EvaluationResult schema."""

import json
import pytest
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
    SCHEMA_VERSION,
)


class TestMetricResult:
    """Tests for MetricResult dataclass."""

    def test_create_passing_metric(self):
        """Test creating a passing metric."""
        m = metric(
            name="test_count",
            value=10,
            expected=">0",
            condition=True,
            message="10 tests executed",
        )

        assert m.name == "test_count"
        assert m.value == 10
        assert m.expected == ">0"
        assert m.passed is True
        assert m.message == "10 tests executed"
        assert m.severity == Severity.ERROR  # default

    def test_create_failing_metric(self):
        """Test creating a failing metric."""
        m = metric(
            name="error_count",
            value=5,
            expected="0",
            condition=False,
            message="5 errors occurred",
            severity="error",
        )

        assert m.passed is False
        assert m.severity == Severity.ERROR

    def test_metric_to_dict(self):
        """Test metric serialization."""
        m = metric(
            name="coverage",
            value=85.5,
            expected=">=80",
            condition=True,
        )

        d = m.to_dict()
        assert d["name"] == "coverage"
        assert d["value"] == 85.5
        assert d["passed"] is True

    def test_severity_valid_string_values(self):
        """Test that valid severity string values are accepted."""
        for severity_value in ["error", "warning", "info"]:
            m = metric(
                name="test",
                value=1,
                expected="1",
                condition=True,
                severity=severity_value,
            )
            assert m.severity == Severity(severity_value)
            assert m.severity.value == severity_value

    def test_severity_enum_values(self):
        """Test that Severity enum values are accepted."""
        m_error = metric(
            name="test",
            value=1,
            expected="1",
            condition=True,
            severity=Severity.ERROR,
        )
        assert m_error.severity == Severity.ERROR
        assert m_error.severity.value == "error"

        m_warning = metric(
            name="test",
            value=1,
            expected="1",
            condition=True,
            severity=Severity.WARNING,
        )
        assert m_warning.severity == Severity.WARNING
        assert m_warning.severity.value == "warning"

        m_info = metric(
            name="test",
            value=1,
            expected="1",
            condition=True,
            severity=Severity.INFO,
        )
        assert m_info.severity == Severity.INFO
        assert m_info.severity.value == "info"

    def test_severity_default_value(self):
        """Test that default severity is ERROR."""
        m = metric(
            name="test",
            value=1,
            expected="1",
            condition=True,
        )
        assert m.severity == Severity.ERROR
        assert m.severity.value == "error"

    def test_severity_invalid_string_raises_error(self):
        """Test that invalid severity string raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            metric(
                name="test",
                value=1,
                expected="1",
                condition=True,
                severity="critical",  # Invalid
            )
        assert "Invalid severity value" in str(exc_info.value)
        assert "critical" in str(exc_info.value)
        assert "error, warning, info" in str(exc_info.value)

    def test_severity_invalid_type_raises_error(self):
        """Test that invalid severity type raises TypeError."""
        with pytest.raises(TypeError) as exc_info:
            MetricResult(
                name="test",
                value=1,
                expected="1",
                passed=True,
                severity=123,  # Invalid type
            )
        assert "severity must be a string or Severity enum" in str(exc_info.value)

    def test_severity_serialization_to_dict(self):
        """Test that severity is serialized correctly in to_dict()."""
        m = metric(
            name="test",
            value=1,
            expected="1",
            condition=True,
            severity=Severity.WARNING,
        )
        d = m.to_dict()
        assert d["severity"] == "warning"  # Should be string value, not enum

    def test_severity_in_json_serialization(self):
        """Test that severity is serialized correctly to JSON."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric(
            name="test_metric",
            value=1,
            expected="1",
            condition=True,
            severity=Severity.INFO,
        ))
        result.add_session(session)
        result.finalize()

        json_str = result.to_json()
        data = json.loads(json_str)
        metric_data = data["sessions"][0]["metrics"][0]
        assert metric_data["severity"] == "info"


class TestSessionResult:
    """Tests for SessionResult dataclass."""

    def test_session_verdict_pass(self):
        """Test session verdict when all metrics pass."""
        session = create_session("unit-tests")
        session.metrics.append(metric("a", 1, "1", True))
        session.metrics.append(metric("b", 2, "2", True))

        assert session.verdict == Verdict.PASS

    def test_session_verdict_fail(self):
        """Test session verdict when any metric fails."""
        session = create_session("integration-tests")
        session.metrics.append(metric("a", 1, "1", True))
        session.metrics.append(metric("b", 0, "1", False))  # failing

        assert session.verdict == Verdict.FAIL

    def test_session_verdict_error_no_metrics(self):
        """Test session verdict when no metrics exist."""
        session = create_session("empty-session")

        assert session.verdict == Verdict.ERROR

    def test_session_failed_metrics(self):
        """Test failed_metrics property."""
        session = create_session("test")
        session.metrics.append(metric("pass1", 1, "1", True))
        session.metrics.append(metric("fail1", 0, "1", False))
        session.metrics.append(metric("fail2", 0, "1", False))

        assert len(session.failed_metrics) == 2
        assert session.failed_metrics[0].name == "fail1"

    def test_session_to_dict(self):
        """Test session serialization."""
        session = create_session("my-session")
        session.metrics.append(metric("test", 1, "1", True))
        session.duration_seconds = 5.5

        d = session.to_dict()
        assert d["session_name"] == "my-session"
        assert d["verdict"] == "PASS"
        assert d["duration_seconds"] == 5.5
        assert len(d["metrics"]) == 1


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_create_evaluation(self):
        """Test creating an evaluation result."""
        result = create_evaluation(
            adapter_type="pytest",
            category="unit",
            project_name="myproject",
        )

        assert result.metadata.adapter_type == "pytest"
        assert result.metadata.category == "unit"
        assert result.metadata.project_name == "myproject"
        assert result.metadata.schema_version == SCHEMA_VERSION
        assert result.metadata.evaluation_id  # should have UUID

    def test_evaluation_verdict_pass(self):
        """Test evaluation verdict when all sessions pass."""
        result = create_evaluation("test")

        session1 = create_session("s1")
        session1.metrics.append(metric("m1", 1, "1", True))

        session2 = create_session("s2")
        session2.metrics.append(metric("m2", 2, "2", True))

        result.add_session(session1)
        result.add_session(session2)

        assert result.verdict == Verdict.PASS
        assert result.exit_code == 0

    def test_evaluation_verdict_fail(self):
        """Test evaluation verdict when any session fails."""
        result = create_evaluation("test")

        session1 = create_session("s1")
        session1.metrics.append(metric("m1", 1, "1", True))

        session2 = create_session("s2")
        session2.metrics.append(metric("m2", 0, "1", False))  # failing

        result.add_session(session1)
        result.add_session(session2)

        assert result.verdict == Verdict.FAIL
        assert result.exit_code == 1

    def test_evaluation_verdict_error_no_sessions(self):
        """Test evaluation verdict when no sessions exist."""
        result = create_evaluation("test")

        assert result.verdict == Verdict.ERROR
        assert result.exit_code == 2

    def test_evaluation_finalize_completes(self):
        """Test that finalize completes successfully."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric("m1", 1, "1", True))
        result.add_session(session)

        result.finalize()
        assert result._finalized is True

    def test_evaluation_finalize_idempotent(self):
        """Test that finalize is idempotent."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric("m1", 1, "1", True))
        result.add_session(session)

        result.finalize()
        duration1 = result.metadata.duration_seconds

        result.finalize()  # second call
        duration2 = result.metadata.duration_seconds

        assert duration1 == duration2

    def test_evaluation_cannot_add_after_finalize(self):
        """Test that adding session after finalize raises error."""
        result = create_evaluation("test")
        result.finalize()

        with pytest.raises(RuntimeError):
            result.add_session(create_session("new"))

    def test_evaluation_summary(self):
        """Test evaluation summary statistics."""
        result = create_evaluation("test")

        session = create_session("s1")
        session.metrics.append(metric("pass1", 1, "1", True))
        session.metrics.append(metric("pass2", 2, "2", True))
        session.metrics.append(metric("fail1", 0, "1", False))
        session.duration_seconds = 10.0

        result.add_session(session)

        summary = result.summary
        assert summary["total_sessions"] == 1
        assert summary["total_metrics"] == 3
        assert summary["passed_metrics"] == 2
        assert summary["failed_metrics"] == 1
        assert summary["total_duration_seconds"] == 10.0

    def test_evaluation_to_json(self):
        """Test JSON serialization."""
        result = create_evaluation("pytest", category="unit")
        session = create_session("tests")
        session.metrics.append(metric("count", 5, ">0", True))
        result.add_session(session)
        result.finalize()

        json_str = result.to_json()
        data = json.loads(json_str)

        assert data["verdict"] == "PASS"
        assert data["exit_code"] == 0
        assert data["metadata"]["adapter_type"] == "pytest"
        assert data["metadata"]["schema_version"] == SCHEMA_VERSION
        assert len(data["sessions"]) == 1

    def test_evaluation_compatibility_properties(self):
        """Test backward compatibility properties."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric("p1", 1, "1", True))
        session.metrics.append(metric("p2", 2, "2", True))
        session.metrics.append(metric("f1", 0, "1", False))
        result.add_session(session)

        # These properties provide backward compatibility with TestResult
        assert result.passed == 2
        assert result.failed == 1
        assert result.total == 3


class TestEnvironmentCapture:
    """Tests for environment context capture."""

    def test_captures_python_version(self):
        """Test that Python version is captured."""
        result = create_evaluation("test")
        assert "python_version" in result.metadata.environment

    def test_captures_hostname(self):
        """Test that hostname is captured."""
        result = create_evaluation("test")
        assert "hostname" in result.metadata.environment

    def test_captures_platform(self):
        """Test that platform is captured."""
        result = create_evaluation("test")
        assert "platform" in result.metadata.environment
