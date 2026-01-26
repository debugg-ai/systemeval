"""
Tests for E2E result types.

These tests validate the E2E execution lifecycle:
1. Generation stage
2. Status polling stage
3. Artifact collection stage
4. Result aggregation and verdict computation
"""
import pytest
from typing import List

from systemeval.e2e_types import (
    GenerationResult,
    StatusResult,
    ArtifactResult,
    E2EResult,
    E2EFailure,
    Verdict,
)


# ============================================================================
# GenerationResult Tests
# ============================================================================


class TestGenerationResult:
    """Test GenerationResult model."""

    def test_successful_generation(self):
        """Test successful generation result."""
        result = GenerationResult(
            status="success",
            test_run_id="run_abc123",
            message="Test run created",
            duration_seconds=0.5,
        )

        assert result.status == "success"
        assert result.test_run_id == "run_abc123"
        assert result.is_success is True

    def test_failed_generation(self):
        """Test failed generation result."""
        result = GenerationResult(
            status="error",
            error="API authentication failed",
            duration_seconds=0.1,
        )

        assert result.status == "error"
        assert result.test_run_id is None
        assert result.is_success is False

    def test_to_dict(self):
        """Test GenerationResult to_dict serialization."""
        result = GenerationResult(
            status="success",
            test_run_id="run_xyz",
            message="Success",
            metadata={"project_id": "test"},
        )

        data = result.to_dict()

        assert data["status"] == "success"
        assert data["test_run_id"] == "run_xyz"
        assert data["message"] == "Success"
        assert "timestamp" in data
        assert data["metadata"]["project_id"] == "test"


# ============================================================================
# StatusResult Tests
# ============================================================================


class TestStatusResult:
    """Test StatusResult model."""

    def test_completed_status(self):
        """Test completed status result."""
        result = StatusResult(
            status="completed",
            poll_count=5,
            duration_seconds=45.0,
        )

        assert result.status == "completed"
        assert result.is_terminal is True
        assert result.is_success is True
        assert result.timeout_exceeded is False

    def test_running_status(self):
        """Test running (non-terminal) status result."""
        result = StatusResult(
            status="running",
            poll_count=3,
            duration_seconds=15.0,
        )

        assert result.status == "running"
        assert result.is_terminal is False
        assert result.is_success is False

    def test_failed_status(self):
        """Test failed status result."""
        result = StatusResult(
            status="failed",
            poll_count=10,
            duration_seconds=60.0,
            error="Test execution failed",
        )

        assert result.status == "failed"
        assert result.is_terminal is True
        assert result.is_success is False

    def test_timeout_status(self):
        """Test timeout status result."""
        result = StatusResult(
            status="running",
            poll_count=60,
            duration_seconds=300.0,
            timeout_exceeded=True,
            error="Timeout after 300s",
        )

        assert result.timeout_exceeded is True
        assert result.is_terminal is False

    def test_to_dict(self):
        """Test StatusResult to_dict serialization."""
        result = StatusResult(
            status="completed",
            poll_count=5,
            duration_seconds=45.0,
            metadata={"execution_time": 43.2},
        )

        data = result.to_dict()

        assert data["status"] == "completed"
        assert data["poll_count"] == 5
        assert data["duration_seconds"] == 45.0
        assert data["timeout_exceeded"] is False


# ============================================================================
# ArtifactResult Tests
# ============================================================================


class TestArtifactResult:
    """Test ArtifactResult model."""

    def test_successful_collection(self):
        """Test successful artifact collection."""
        result = ArtifactResult(
            status="success",
            artifacts_collected=[
                "/tmp/screenshot.png",
                "/tmp/video.webm",
            ],
            total_size_bytes=1024 * 1024,
            duration_seconds=2.5,
        )

        assert result.status == "success"
        assert len(result.artifacts_collected) == 2
        assert result.is_success is True

    def test_partial_collection(self):
        """Test partial artifact collection."""
        result = ArtifactResult(
            status="partial",
            artifacts_collected=["/tmp/screenshot.png"],
            artifacts_failed=["/tmp/video.webm"],
            total_size_bytes=512 * 1024,
            duration_seconds=1.5,
        )

        assert result.status == "partial"
        assert len(result.artifacts_collected) == 1
        assert len(result.artifacts_failed) == 1
        assert result.is_success is True  # partial is still success

    def test_failed_collection(self):
        """Test failed artifact collection."""
        result = ArtifactResult(
            status="error",
            error="Failed to download artifacts",
            duration_seconds=0.5,
        )

        assert result.status == "error"
        assert result.is_success is False

    def test_to_dict(self):
        """Test ArtifactResult to_dict serialization."""
        result = ArtifactResult(
            status="success",
            artifacts_collected=["/tmp/test.png"],
            total_size_bytes=1024,
        )

        data = result.to_dict()

        assert data["status"] == "success"
        assert len(data["artifacts_collected"]) == 1
        assert data["total_size_bytes"] == 1024


# ============================================================================
# E2EFailure Tests
# ============================================================================


class TestE2EFailure:
    """Test E2EFailure model."""

    def test_basic_failure(self):
        """Test basic E2E failure without artifacts."""
        failure = E2EFailure(
            test_id="test_login",
            test_name="User can log in",
            message="Timeout waiting for login button",
            duration=30.0,
        )

        assert failure.test_id == "test_login"
        assert failure.test_name == "User can log in"
        assert failure.screenshot_path is None

    def test_failure_with_artifacts(self):
        """Test E2E failure with screenshot/video."""
        failure = E2EFailure(
            test_id="test_login",
            test_name="User can log in",
            message="Timeout",
            screenshot_path="/tmp/failure.png",
            video_path="/tmp/failure.webm",
            trace_path="/tmp/trace.json",
        )

        assert failure.screenshot_path == "/tmp/failure.png"
        assert failure.video_path == "/tmp/failure.webm"
        assert failure.trace_path == "/tmp/trace.json"

    def test_failure_with_console_logs(self):
        """Test E2E failure with console logs."""
        failure = E2EFailure(
            test_id="test_error",
            test_name="Test with console errors",
            message="JavaScript error",
            console_logs=[
                "ERROR: Uncaught TypeError",
                "WARNING: Deprecated API",
            ],
        )

        assert len(failure.console_logs) == 2
        assert "Uncaught TypeError" in failure.console_logs[0]

    def test_to_dict(self):
        """Test E2EFailure to_dict serialization."""
        failure = E2EFailure(
            test_id="test_1",
            test_name="Test 1",
            message="Failed",
            screenshot_path="/tmp/screenshot.png",
            console_logs=["ERROR: Test failed"],
        )

        data = failure.to_dict()

        assert data["test_id"] == "test_1"
        assert data["screenshot_path"] == "/tmp/screenshot.png"
        assert len(data["console_logs"]) == 1


# ============================================================================
# E2EResult Tests - Verdict Logic
# ============================================================================


class TestE2EResultVerdict:
    """Test E2EResult verdict computation."""

    def test_pass_verdict(self):
        """Test PASS verdict when all tests pass."""
        result = E2EResult(
            test_run_id="run_pass",
            provider="debuggai",
            passed=5,
            failed=0,
            errors=0,
            skipped=0,
            generation=GenerationResult(
                status="success",
                test_run_id="run_pass",
            ),
            status=StatusResult(status="completed"),
            artifacts=ArtifactResult(status="success"),
        )

        assert result.verdict == Verdict.PASS
        assert result.total == 5

    def test_fail_verdict(self):
        """Test FAIL verdict when tests fail."""
        result = E2EResult(
            test_run_id="run_fail",
            provider="debuggai",
            passed=3,
            failed=2,
            errors=0,
            skipped=0,
            generation=GenerationResult(
                status="success",
                test_run_id="run_fail",
            ),
            status=StatusResult(status="completed"),
        )

        assert result.verdict == Verdict.FAIL
        assert result.total == 5

    def test_error_verdict_generation_failed(self):
        """Test ERROR verdict when generation fails."""
        result = E2EResult(
            test_run_id=None,
            provider="debuggai",
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            generation=GenerationResult(
                status="error",
                error="API auth failed",
            ),
        )

        assert result.verdict == Verdict.ERROR

    def test_error_verdict_timeout(self):
        """Test ERROR verdict when status polling times out."""
        result = E2EResult(
            test_run_id="run_timeout",
            provider="debuggai",
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            generation=GenerationResult(
                status="success",
                test_run_id="run_timeout",
            ),
            status=StatusResult(
                status="running",
                timeout_exceeded=True,
            ),
        )

        assert result.verdict == Verdict.ERROR

    def test_error_verdict_no_tests_run(self):
        """Test ERROR verdict when no tests run."""
        result = E2EResult(
            test_run_id="run_empty",
            provider="debuggai",
            passed=0,
            failed=0,
            errors=0,
            skipped=0,
            generation=GenerationResult(
                status="success",
                test_run_id="run_empty",
            ),
            status=StatusResult(status="completed"),
        )

        assert result.verdict == Verdict.ERROR
        assert result.total == 0

    def test_error_verdict_exit_code(self):
        """Test ERROR verdict when exit_code == 2."""
        result = E2EResult(
            test_run_id="run_error",
            provider="debuggai",
            passed=5,
            failed=0,
            errors=0,
            skipped=0,
            exit_code=2,
        )

        assert result.verdict == Verdict.ERROR


# ============================================================================
# E2EResult Tests - Factory Methods
# ============================================================================


class TestE2EResultFactory:
    """Test E2EResult factory methods."""

    def test_from_error(self):
        """Test E2EResult.from_error factory."""
        result = E2EResult.from_error(
            error_message="API authentication failed",
            provider="debuggai",
        )

        assert result.verdict == Verdict.ERROR
        assert result.errors == 1
        assert result.exit_code == 2
        assert result.generation is not None
        assert result.generation.status == "error"
        assert result.metadata["error"] == "API authentication failed"


# ============================================================================
# E2EResult Tests - Serialization
# ============================================================================


class TestE2EResultSerialization:
    """Test E2EResult serialization."""

    def test_to_dict_pass(self):
        """Test to_dict for passing result."""
        result = E2EResult(
            test_run_id="run_123",
            provider="debuggai",
            passed=5,
            failed=0,
            errors=0,
            skipped=0,
            duration_seconds=45.0,
            generation=GenerationResult(
                status="success",
                test_run_id="run_123",
            ),
            status=StatusResult(
                status="completed",
                poll_count=5,
            ),
            artifacts=ArtifactResult(
                status="success",
                artifacts_collected=["/tmp/test.png"],
            ),
        )

        data = result.to_dict()

        assert data["verdict"] == "PASS"
        assert data["total"] == 5
        assert data["passed"] == 5
        assert data["failed"] == 0
        assert data["test_run_id"] == "run_123"
        assert data["provider"] == "debuggai"
        assert "generation" in data
        assert "status" in data
        assert "artifacts" in data

    def test_to_dict_fail_with_failures(self):
        """Test to_dict for failing result with failures."""
        failure = E2EFailure(
            test_id="test_1",
            test_name="Test 1",
            message="Failed",
            duration=10.0,
        )

        result = E2EResult(
            test_run_id="run_456",
            provider="local",
            passed=3,
            failed=2,
            errors=0,
            skipped=0,
            failures=[failure],
        )

        data = result.to_dict()

        assert data["verdict"] == "FAIL"
        assert data["failed"] == 2
        assert "failures" in data
        assert len(data["failures"]) == 1
        assert data["failures"][0]["test_id"] == "test_1"

    def test_to_dict_error(self):
        """Test to_dict for error result."""
        result = E2EResult.from_error(
            error_message="Network timeout",
            provider="debuggai",
            test_run_id="run_error",
        )

        data = result.to_dict()

        assert data["verdict"] == "ERROR"
        assert data["errors"] == 1
        assert data["exit_code"] == 2
        assert "metadata" in data


# ============================================================================
# E2EResult Tests - Integration
# ============================================================================


class TestE2EResultIntegration:
    """Integration tests for E2E result lifecycle."""

    def test_complete_successful_lifecycle(self):
        """Test complete E2E lifecycle: generate, poll, collect, succeed."""
        # Stage 1: Generation
        generation = GenerationResult(
            status="success",
            test_run_id="run_lifecycle_1",
            message="Test run created",
            duration_seconds=0.5,
        )

        # Stage 2: Status polling
        status = StatusResult(
            status="completed",
            poll_count=5,
            duration_seconds=45.0,
        )

        # Stage 3: Artifact collection
        artifacts = ArtifactResult(
            status="success",
            artifacts_collected=[
                "/tmp/screenshot1.png",
                "/tmp/video1.webm",
            ],
            total_size_bytes=1024 * 1024 * 2,
            duration_seconds=2.5,
        )

        # Stage 4: Aggregate result
        result = E2EResult(
            test_run_id="run_lifecycle_1",
            provider="debuggai",
            passed=8,
            failed=0,
            errors=0,
            skipped=0,
            duration_seconds=48.0,
            generation=generation,
            status=status,
            artifacts=artifacts,
        )

        # Verify
        assert result.verdict == Verdict.PASS
        assert result.total == 8
        assert result.generation.is_success
        assert result.status.is_success
        assert result.artifacts.is_success

    def test_complete_failed_lifecycle(self):
        """Test complete E2E lifecycle: generate, poll, collect, fail."""
        generation = GenerationResult(
            status="success",
            test_run_id="run_lifecycle_2",
        )

        status = StatusResult(
            status="completed",
            poll_count=10,
            duration_seconds=120.0,
        )

        artifacts = ArtifactResult(
            status="success",
            artifacts_collected=["/tmp/failure.png"],
            duration_seconds=1.0,
        )

        failure = E2EFailure(
            test_id="test_login",
            test_name="Login test",
            message="Timeout",
            screenshot_path="/tmp/failure.png",
        )

        result = E2EResult(
            test_run_id="run_lifecycle_2",
            provider="debuggai",
            passed=5,
            failed=2,
            errors=0,
            skipped=1,
            duration_seconds=123.5,
            failures=[failure],
            generation=generation,
            status=status,
            artifacts=artifacts,
        )

        # Verify
        assert result.verdict == Verdict.FAIL
        assert result.total == 8
        assert len(result.failures) == 1

    def test_complete_error_lifecycle(self):
        """Test E2E lifecycle: generation error."""
        generation = GenerationResult(
            status="error",
            error="API authentication failed: Invalid API key",
            duration_seconds=0.2,
        )

        result = E2EResult(
            test_run_id=None,
            provider="debuggai",
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            exit_code=2,
            generation=generation,
        )

        # Verify
        assert result.verdict == Verdict.ERROR
        assert not result.generation.is_success
