"""
E2E Result Types for systemeval.

Architecture Rationale:
-----------------------
E2E tests have different execution models than unit tests:
- Async execution (trigger, poll, collect results)
- Multiple stages (generation, execution, artifact collection)
- External service dependencies (API failures, timeouts)

These types model the E2E execution lifecycle while maintaining
compatibility with systemeval's TestResult pattern.

Integration with types.py:
--------------------------
- E2EResult is the E2E equivalent of TestResult
- Both have verdict: Literal["PASS", "FAIL", "ERROR"]
- Both track passed/failed/errors/skipped counts
- Both have duration_seconds and timestamp
- E2EResult adds generation/status/artifact tracking

Design Principles:
------------------
1. Explicit stages: Generation -> Status Polling -> Artifact Collection
2. Fail fast: Each stage can fail independently with clear error messages
3. Type safety: All fields are explicitly typed, no Any except where needed
4. Traceable: test_run_id links all stages together
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Union

from systemeval.types import TestFailure, Verdict


# ============================================================================
# E2E Stage Results
# ============================================================================


@dataclass
class GenerationResult:
    """
    Result from E2E test generation stage.

    This represents the initial stage where test specifications are
    submitted to the E2E provider (e.g., DebuggAI Surfer).

    Success criteria:
    - status == "success"
    - test_run_id is not None

    Failure scenarios:
    - API authentication failure
    - Invalid test specification
    - Network timeout
    """

    status: Literal["success", "error"] = "error"
    """Generation status."""

    test_run_id: Optional[str] = None
    """Unique identifier for this test run (from provider)."""

    message: Optional[str] = None
    """Success or error message from generation."""

    error: Optional[str] = None
    """Detailed error message if status == "error"."""

    duration_seconds: float = 0.0
    """Time taken for generation request."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    """ISO 8601 timestamp of generation."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Provider-specific metadata (project_id, config, etc)."""

    @property
    def is_success(self) -> bool:
        """Check if generation succeeded."""
        return self.status == "success" and self.test_run_id is not None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "test_run_id": self.test_run_id,
            "message": self.message,
            "error": self.error,
            "duration_seconds": round(self.duration_seconds, 3),
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass
class StatusResult:
    """
    Result from E2E test status polling stage.

    This represents periodic status checks during test execution.
    Status polling continues until test reaches terminal state or timeout.

    Terminal states: "completed", "failed", "error"
    Non-terminal states: "pending", "running", "queued"

    Success criteria:
    - status in terminal states
    - No timeout before completion

    Failure scenarios:
    - Timeout waiting for completion
    - Provider API errors during polling
    - Network failures
    """

    status: Literal["pending", "running", "queued", "completed", "failed", "error"] = "pending"
    """Current test execution status."""

    poll_count: int = 0
    """Number of status polls performed."""

    duration_seconds: float = 0.0
    """Total time spent polling (wall clock time)."""

    last_poll_timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    """ISO 8601 timestamp of last poll."""

    error: Optional[str] = None
    """Error message if polling failed."""

    timeout_exceeded: bool = False
    """True if polling exceeded configured timeout."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Provider-specific status metadata."""

    @property
    def is_terminal(self) -> bool:
        """Check if status is terminal (no more polling needed)."""
        return self.status in ("completed", "failed", "error")

    @property
    def is_success(self) -> bool:
        """Check if test execution completed successfully."""
        return self.status == "completed"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "poll_count": self.poll_count,
            "duration_seconds": round(self.duration_seconds, 3),
            "last_poll_timestamp": self.last_poll_timestamp,
            "error": self.error,
            "timeout_exceeded": self.timeout_exceeded,
            "metadata": self.metadata,
        }


@dataclass
class ArtifactResult:
    """
    Result from E2E test artifact collection stage.

    After test execution completes, artifacts are collected:
    - Test results (passed/failed counts)
    - Screenshots, videos, traces
    - Logs and console output

    Success criteria:
    - status == "success"
    - artifacts collected successfully

    Failure scenarios:
    - Artifact download failures
    - Storage errors
    - Missing expected artifacts
    """

    status: Literal["success", "partial", "error"] = "error"
    """Artifact collection status."""

    artifacts_collected: List[str] = field(default_factory=list)
    """List of successfully collected artifact paths."""

    artifacts_failed: List[str] = field(default_factory=list)
    """List of artifacts that failed to collect."""

    total_size_bytes: int = 0
    """Total size of collected artifacts in bytes."""

    duration_seconds: float = 0.0
    """Time taken for artifact collection."""

    error: Optional[str] = None
    """Error message if collection failed."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Provider-specific artifact metadata."""

    @property
    def is_success(self) -> bool:
        """Check if artifact collection succeeded."""
        return self.status in ("success", "partial") and len(self.artifacts_collected) > 0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "status": self.status,
            "artifacts_collected": self.artifacts_collected,
            "artifacts_failed": self.artifacts_failed,
            "total_size_bytes": self.total_size_bytes,
            "duration_seconds": round(self.duration_seconds, 3),
            "error": self.error,
            "metadata": self.metadata,
        }


# ============================================================================
# E2E Test Result (equivalent to TestResult for E2E)
# ============================================================================


@dataclass
class E2EResult:
    """
    Complete E2E test execution result.

    This is the E2E equivalent of types.TestResult.
    It tracks the full lifecycle of E2E test execution:
    1. Generation (submit test to provider)
    2. Status Polling (wait for completion)
    3. Artifact Collection (download results)
    4. Result Aggregation (compute verdict)

    Integration with TestResult:
    -----------------------------
    Like TestResult, E2EResult has:
    - verdict: Literal["PASS", "FAIL", "ERROR"]
    - passed/failed/errors/skipped counts
    - duration_seconds, timestamp
    - failures: List[TestFailure]

    Unlike TestResult, E2EResult adds:
    - test_run_id: Links all stages
    - generation/status/artifacts: Stage-specific results
    - provider: Which E2E provider was used

    Usage:
        result = E2EResult(
            test_run_id="run_abc123",
            provider="debuggai",
            passed=5,
            failed=2,
            generation=generation_result,
            status=status_result,
            artifacts=artifact_result,
        )

        if result.verdict == Verdict.PASS:
            print("E2E tests passed")
        else:
            print(f"E2E tests failed: {result.failures}")
    """

    # Core test metrics (matches TestResult)
    passed: int = 0
    """Number of passed E2E tests."""

    failed: int = 0
    """Number of failed E2E tests."""

    errors: int = 0
    """Number of E2E test errors (setup/teardown failures)."""

    skipped: int = 0
    """Number of skipped E2E tests."""

    duration_seconds: float = 0.0
    """Total duration from generation to artifact collection."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    """ISO 8601 timestamp when result was finalized."""

    failures: List[TestFailure] = field(default_factory=list)
    """Detailed failure information for failed tests."""

    # E2E-specific fields
    test_run_id: Optional[str] = None
    """Unique identifier for this E2E test run."""

    provider: str = "unknown"
    """E2E provider used (debuggai, local, etc)."""

    generation: Optional[GenerationResult] = None
    """Result from test generation stage."""

    status: Optional[StatusResult] = None
    """Result from status polling stage."""

    artifacts: Optional[ArtifactResult] = None
    """Result from artifact collection stage."""

    exit_code: int = 0
    """Exit code (0 = success, non-zero = failure/error)."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    @property
    def total(self) -> int:
        """Total number of tests."""
        return self.passed + self.failed + self.errors + self.skipped

    @property
    def verdict(self) -> Verdict:
        """
        Determine verdict based on E2E execution.

        Verdict Logic:
        --------------
        ERROR: If any stage failed to complete
        - Generation failed (no test_run_id)
        - Status polling timed out or errored
        - Artifact collection failed
        - Exit code indicates error (exit_code == 2)

        FAIL: If tests ran but some failed
        - failed > 0 or errors > 0
        - All stages completed successfully

        PASS: All tests passed
        - passed > 0
        - failed == 0
        - errors == 0
        - All stages completed successfully

        Special case:
        - If total == 0 and generation succeeded, verdict is ERROR
          (no tests found/run)
        """
        # Check for stage failures
        if self.generation and not self.generation.is_success:
            return Verdict.ERROR

        if self.status:
            if self.status.timeout_exceeded:
                return Verdict.ERROR
            if not self.status.is_terminal:
                return Verdict.ERROR
            if self.status.status == "error":
                return Verdict.ERROR

        if self.artifacts and not self.artifacts.is_success:
            # Partial artifact collection is OK (verdict based on test results)
            if self.artifacts.status == "error":
                return Verdict.ERROR

        # Check exit code
        if self.exit_code == 2:
            return Verdict.ERROR

        # Check test results
        if self.total == 0:
            return Verdict.ERROR

        if self.failed > 0 or self.errors > 0:
            return Verdict.FAIL

        return Verdict.PASS

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for JSON serialization.

        Output format matches TestResult.to_dict() for consistency.
        """
        result = {
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "total": self.total,
            "passed": self.passed,
            "failed": self.failed,
            "errors": self.errors,
            "skipped": self.skipped,
            "duration_seconds": round(self.duration_seconds, 3),
            "timestamp": self.timestamp,
            "provider": self.provider,
            "test_run_id": self.test_run_id,
        }

        # Add failures if present
        if self.failures:
            result["failures"] = [
                {
                    "test_id": f.test_id,
                    "test_name": f.test_name,
                    "message": f.message,
                    "duration_seconds": f.duration,
                }
                for f in self.failures
            ]

        # Add stage results
        if self.generation:
            result["generation"] = self.generation.to_dict()

        if self.status:
            result["status"] = self.status.to_dict()

        if self.artifacts:
            result["artifacts"] = self.artifacts.to_dict()

        # Add metadata
        if self.metadata:
            result["metadata"] = self.metadata

        return result

    @classmethod
    def from_error(
        cls,
        error_message: str,
        provider: str = "unknown",
        test_run_id: Optional[str] = None,
    ) -> "E2EResult":
        """
        Create an E2EResult representing an error state.

        Use this factory for fatal errors that prevent test execution:
        - Configuration errors
        - Provider API failures
        - Network timeouts

        Example:
            result = E2EResult.from_error(
                error_message="DebuggAI API authentication failed",
                provider="debuggai",
            )
        """
        return cls(
            passed=0,
            failed=0,
            errors=1,
            skipped=0,
            exit_code=2,
            test_run_id=test_run_id,
            provider=provider,
            generation=GenerationResult(
                status="error",
                error=error_message,
            ),
            metadata={"error": error_message},
        )


# ============================================================================
# E2E Failure Types (extends TestFailure)
# ============================================================================


@dataclass
class E2EFailure(TestFailure):
    """
    E2E-specific test failure.

    Extends TestFailure with E2E-specific fields:
    - screenshot_path: Path to failure screenshot
    - video_path: Path to failure video
    - trace_path: Path to playwright trace
    - console_logs: Browser console output

    Usage:
        failure = E2EFailure(
            test_id="e2e_login_test",
            test_name="User can log in successfully",
            message="Timeout waiting for login button",
            screenshot_path="/tmp/e2e/screenshot_login_failed.png",
            video_path="/tmp/e2e/video_login_failed.webm",
        )
    """

    screenshot_path: Optional[str] = None
    """Path to screenshot taken at failure."""

    video_path: Optional[str] = None
    """Path to video recording of failure."""

    trace_path: Optional[str] = None
    """Path to Playwright trace file."""

    console_logs: List[str] = field(default_factory=list)
    """Browser console logs at time of failure."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result = {
            "test_id": self.test_id,
            "test_name": self.test_name,
            "message": self.message,
            "duration_seconds": self.duration,
        }

        if self.traceback:
            result["traceback"] = self.traceback

        if self.expected is not None:
            result["expected"] = self.expected

        if self.actual is not None:
            result["actual"] = self.actual

        # E2E-specific fields
        if self.screenshot_path:
            result["screenshot_path"] = self.screenshot_path

        if self.video_path:
            result["video_path"] = self.video_path

        if self.trace_path:
            result["trace_path"] = self.trace_path

        if self.console_logs:
            result["console_logs"] = self.console_logs

        if self.metadata:
            result["metadata"] = self.metadata

        return result


# ============================================================================
# Type Aliases
# ============================================================================

# Union type for all E2E result types
E2EStageResult = Union[GenerationResult, StatusResult, ArtifactResult]

# Type alias for E2E verdict (same as TestResult verdict)
E2EVerdict = Verdict
