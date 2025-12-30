"""Tests for the unified EvaluationResult schema."""

import json
import pytest
from systemeval.core.evaluation import (
    EvaluationResult,
    EvaluationMetadata,
    SessionResult,
    MetricResult,
    Verdict,
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
        assert m.severity == "error"  # default

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
        assert m.severity == "error"

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

    def test_evaluation_finalize_computes_hash(self):
        """Test that finalize computes run_hash."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric("m1", 1, "1", True))
        result.add_session(session)

        assert result.metadata.run_hash == ""
        result.finalize()
        assert result.metadata.run_hash != ""
        assert len(result.metadata.run_hash) == 16  # SHA256 truncated

    def test_evaluation_finalize_idempotent(self):
        """Test that finalize is idempotent."""
        result = create_evaluation("test")
        session = create_session("s1")
        session.metrics.append(metric("m1", 1, "1", True))
        result.add_session(session)

        result.finalize()
        hash1 = result.metadata.run_hash

        result.finalize()  # second call
        hash2 = result.metadata.run_hash

        assert hash1 == hash2

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


class TestHashReproducibility:
    """Tests for content hash reproducibility."""

    def test_same_content_same_hash(self):
        """Test that same content produces same hash."""
        def make_result():
            r = create_evaluation("pytest", category="unit", project_name="test")
            s = create_session("tests")
            s.metrics.append(metric("count", 10, ">0", True))
            r.add_session(s)
            r.finalize()
            return r

        result1 = make_result()
        result2 = make_result()

        # Hashes should be the same for same content
        assert result1.metadata.run_hash == result2.metadata.run_hash

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        result1 = create_evaluation("pytest")
        s1 = create_session("tests")
        s1.metrics.append(metric("count", 10, ">0", True))
        result1.add_session(s1)
        result1.finalize()

        result2 = create_evaluation("pytest")
        s2 = create_session("tests")
        s2.metrics.append(metric("count", 20, ">0", True))  # different value
        result2.add_session(s2)
        result2.finalize()

        assert result1.metadata.run_hash != result2.metadata.run_hash

    def test_hash_excludes_timestamps(self):
        """Test that hash is not affected by timestamps."""
        import time

        result1 = create_evaluation("pytest")
        s1 = create_session("tests")
        s1.metrics.append(metric("count", 10, ">0", True))
        result1.add_session(s1)
        result1.finalize()

        time.sleep(0.01)  # small delay

        result2 = create_evaluation("pytest")
        s2 = create_session("tests")
        s2.metrics.append(metric("count", 10, ">0", True))
        result2.add_session(s2)
        result2.finalize()

        # Different timestamps but same hash
        assert result1.metadata.timestamp_utc != result2.metadata.timestamp_utc
        assert result1.metadata.run_hash == result2.metadata.run_hash


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
