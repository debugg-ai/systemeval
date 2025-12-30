"""
Unified EvaluationResult schema for SystemEval.

This is the singular contract that ALL evaluations MUST conform to.

Enforces:
1. Singular entrypoint - One schema for all evaluation types
2. Non-fungible - Unique IDs + content hashing
3. Objective - Binary verdict, deterministic
4. Repeatable - Same inputs = same run_hash
5. Structured output - JSON Schema compliant, AI-parseable

Usage:
    result = create_evaluation(
        adapter_type="pipeline",
        category="integration",
        project_name="debuggai"
    )

    result.add_session(SessionResult(...))
    result.finalize()  # Computes verdict, hash, duration

    # Output
    result.to_json()
    result.to_dict()
"""
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union


# Schema version - bump on breaking changes
SCHEMA_VERSION = "1.0.0"


class Verdict(str, Enum):
    """
    Binary verdict - deterministic, no subjective interpretation.

    CASCADE LOGIC:
    - ANY metric fails → session FAILS
    - ANY session fails → evaluation FAILS
    - System/config error → ERROR
    """
    PASS = "PASS"
    FAIL = "FAIL"
    ERROR = "ERROR"


@dataclass
class MetricResult:
    """
    Result of evaluating a single metric/criterion.

    A metric is a single measurable value with a pass/fail condition.
    Examples: build_status, test_count, error_rate, coverage_percent
    """
    name: str  # Metric identifier
    value: Any  # Actual value measured
    expected: Any  # Expected value or condition description
    passed: bool  # True if metric passed its condition

    # Enrichment
    message: Optional[str] = None  # Human-readable description
    severity: str = "error"  # error, warning, info
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "expected": self.expected,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity,
            "metadata": self.metadata,
        }


@dataclass
class SessionResult:
    """
    Result for a single evaluation session.

    A session is a logical unit of evaluation (e.g., one test file,
    one project, one E2E scenario).

    CASCADE RULE: If ANY metric fails, the session FAILS.
    """
    session_id: str  # Unique identifier
    session_name: str  # Human-readable name

    # Results
    metrics: List[MetricResult] = field(default_factory=list)

    # Timing
    started_at: Optional[str] = None  # ISO 8601
    completed_at: Optional[str] = None  # ISO 8601
    duration_seconds: float = 0.0

    # Raw output capture
    stdout: str = ""
    stderr: str = ""

    # Artifacts (links to logs, screenshots, etc.)
    artifacts: Dict[str, str] = field(default_factory=dict)

    # Adapter-specific metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def verdict(self) -> Verdict:
        """Compute verdict from metrics."""
        if not self.metrics:
            return Verdict.ERROR
        if all(m.passed for m in self.metrics):
            return Verdict.PASS
        return Verdict.FAIL

    @property
    def failed_metrics(self) -> List[MetricResult]:
        return [m for m in self.metrics if not m.passed]

    @property
    def passed_metrics(self) -> List[MetricResult]:
        return [m for m in self.metrics if m.passed]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "session_name": self.session_name,
            "verdict": self.verdict.value,
            "duration_seconds": self.duration_seconds,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "metrics": [m.to_dict() for m in self.metrics],
            "failed_metrics": [m.name for m in self.failed_metrics],
            "artifacts": self.artifacts,
            "metadata": self.metadata,
            "has_stdout": bool(self.stdout),
            "has_stderr": bool(self.stderr),
        }


@dataclass
class EvaluationMetadata:
    """
    Non-fungible metadata for unique identification.

    Every evaluation is uniquely identifiable via:
    - evaluation_id: UUID for this specific run
    - run_hash: Content-based hash for reproducibility verification
    - timestamp_utc: When the evaluation was performed
    - environment: Git commit, branch, host, etc.
    """
    # Unique identifiers
    evaluation_id: str  # UUID4 - globally unique
    run_hash: str = ""  # SHA256 content hash (computed after finalization)

    # Temporal
    timestamp_utc: str = ""  # ISO 8601 with microseconds
    duration_seconds: float = 0.0

    # Environment context
    environment: Dict[str, str] = field(default_factory=dict)

    # Schema versioning
    schema_version: str = SCHEMA_VERSION

    # Evaluation context
    adapter_type: str = ""
    category: Optional[str] = None
    project_name: Optional[str] = None

    # Command that was run
    command: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "evaluation_id": self.evaluation_id,
            "run_hash": self.run_hash,
            "timestamp_utc": self.timestamp_utc,
            "duration_seconds": self.duration_seconds,
            "environment": self.environment,
            "schema_version": self.schema_version,
            "adapter_type": self.adapter_type,
            "category": self.category,
            "project_name": self.project_name,
            "command": self.command,
        }


@dataclass
class EvaluationResult:
    """
    UNIFIED result schema for ALL evaluations.

    This is the singular contract that all adapters MUST conform to.

    Principles:
    1. Singular entrypoint - One schema for all evaluation types
    2. Non-fungible - Unique IDs + content hashing
    3. Objective - Binary verdict, deterministic
    4. Repeatable - Same inputs = same run_hash
    5. Structured output - JSON Schema compliant, AI-parseable

    CASCADE RULE: If ANY session fails, the evaluation FAILS.
    """
    metadata: EvaluationMetadata
    sessions: List[SessionResult] = field(default_factory=list)

    # Diagnostic data
    diagnostics: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Internal state
    _start_time: float = field(default=0.0, repr=False)
    _finalized: bool = field(default=False, repr=False)

    @property
    def verdict(self) -> Verdict:
        """
        Compute verdict from sessions.

        CASCADE LOGIC:
        - No sessions → ERROR
        - ANY session ERROR → ERROR
        - ANY session FAIL → FAIL
        - ALL sessions PASS → PASS
        """
        if not self.sessions:
            return Verdict.ERROR
        if any(s.verdict == Verdict.ERROR for s in self.sessions):
            return Verdict.ERROR
        if any(s.verdict == Verdict.FAIL for s in self.sessions):
            return Verdict.FAIL
        return Verdict.PASS

    @property
    def exit_code(self) -> int:
        """Map verdict to exit code."""
        return {
            Verdict.PASS: 0,
            Verdict.FAIL: 1,
            Verdict.ERROR: 2,
        }[self.verdict]

    @property
    def summary(self) -> Dict[str, Any]:
        """Compute summary statistics."""
        total_metrics = sum(len(s.metrics) for s in self.sessions)
        passed_metrics = sum(len(s.passed_metrics) for s in self.sessions)

        return {
            "total_sessions": len(self.sessions),
            "passed_sessions": sum(1 for s in self.sessions if s.verdict == Verdict.PASS),
            "failed_sessions": sum(1 for s in self.sessions if s.verdict == Verdict.FAIL),
            "error_sessions": sum(1 for s in self.sessions if s.verdict == Verdict.ERROR),
            "total_metrics": total_metrics,
            "passed_metrics": passed_metrics,
            "failed_metrics": total_metrics - passed_metrics,
            "total_duration_seconds": sum(s.duration_seconds for s in self.sessions),
        }

    @property
    def failed_sessions(self) -> List[SessionResult]:
        return [s for s in self.sessions if s.verdict != Verdict.PASS]

    def add_session(self, session: SessionResult) -> None:
        """Add a session to the evaluation."""
        if self._finalized:
            raise RuntimeError("Cannot add session to finalized evaluation")
        self.sessions.append(session)

    def add_diagnostic(self, message: str) -> None:
        """Add a diagnostic message."""
        self.diagnostics.append(message)

    def add_warning(self, message: str) -> None:
        """Add a warning message."""
        self.warnings.append(message)

    def finalize(self) -> None:
        """
        Finalize the evaluation.

        Computes:
        - Total duration
        - Content hash for reproducibility
        - Final timestamp
        """
        if self._finalized:
            return

        # Compute duration
        if self._start_time:
            self.metadata.duration_seconds = time.time() - self._start_time

        # Compute content hash
        self.metadata.run_hash = self._compute_hash()

        self._finalized = True

    def _compute_hash(self) -> str:
        """
        Compute deterministic content hash for reproducibility.

        Hash is computed from result content (excluding timestamps
        and non-deterministic metadata).
        """
        hash_content = {
            "adapter_type": self.metadata.adapter_type,
            "category": self.metadata.category,
            "project_name": self.metadata.project_name,
            "verdict": self.verdict.value,
            "sessions": [
                {
                    "session_name": s.session_name,
                    "verdict": s.verdict.value,
                    "metrics": [
                        {
                            "name": m.name,
                            "value": str(m.value),  # Stringify for consistency
                            "passed": m.passed,
                        }
                        for m in s.metrics
                    ],
                }
                for s in self.sessions
            ],
        }

        hash_str = json.dumps(hash_content, sort_keys=True)
        return hashlib.sha256(hash_str.encode()).hexdigest()[:16]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "metadata": self.metadata.to_dict(),
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "summary": self.summary,
            "sessions": [s.to_dict() for s in self.sessions],
            "diagnostics": self.diagnostics,
            "warnings": self.warnings,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    # Compatibility with existing TestResult interface
    @property
    def passed(self) -> int:
        return self.summary["passed_metrics"]

    @property
    def failed(self) -> int:
        return self.summary["failed_metrics"]

    @property
    def errors(self) -> int:
        return self.summary["error_sessions"]

    @property
    def skipped(self) -> int:
        return 0  # Not tracked at this level

    @property
    def total(self) -> int:
        return self.summary["total_metrics"]

    @property
    def duration(self) -> float:
        return self.metadata.duration_seconds


def create_evaluation(
    adapter_type: str,
    category: Optional[str] = None,
    project_name: Optional[str] = None,
    command: Optional[str] = None,
    environment: Optional[Dict[str, str]] = None,
) -> EvaluationResult:
    """
    Factory function to create an EvaluationResult with proper metadata.

    Automatically captures:
    - Unique evaluation_id (UUID4)
    - Timestamp with microseconds
    - Environment context (git commit, branch, host, Python version)

    Usage:
        result = create_evaluation(
            adapter_type="pipeline",
            category="integration",
            project_name="debuggai"
        )

        # Add sessions
        session = SessionResult(
            session_id=str(uuid.uuid4()),
            session_name="unit-tests",
        )
        session.metrics.append(MetricResult(
            name="tests_passed",
            value=150,
            expected=">0",
            passed=True,
        ))
        result.add_session(session)

        # Finalize and output
        result.finalize()
        print(result.to_json())
    """
    # Capture environment context
    env_context = dict(environment or {})

    # Git context
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        env_context["git_commit"] = git_commit[:12]
    except Exception:
        pass

    try:
        git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        env_context["git_branch"] = git_branch
    except Exception:
        pass

    # Host context
    env_context["hostname"] = socket.gethostname()
    env_context["python_version"] = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    env_context["platform"] = sys.platform

    # Create metadata
    metadata = EvaluationMetadata(
        evaluation_id=str(uuid.uuid4()),
        timestamp_utc=datetime.now(timezone.utc).isoformat(),
        environment=env_context,
        adapter_type=adapter_type,
        category=category,
        project_name=project_name,
        command=command,
    )

    result = EvaluationResult(metadata=metadata)
    result._start_time = time.time()

    return result


def create_session(
    name: str,
    session_id: Optional[str] = None,
) -> SessionResult:
    """
    Factory function to create a SessionResult.

    Usage:
        session = create_session("unit-tests")
        session.metrics.append(MetricResult(...))
        result.add_session(session)
    """
    return SessionResult(
        session_id=session_id or str(uuid.uuid4()),
        session_name=name,
        started_at=datetime.now(timezone.utc).isoformat(),
    )


def metric(
    name: str,
    value: Any,
    expected: Any,
    condition: bool,
    message: Optional[str] = None,
    severity: str = "error",
    **metadata: Any,
) -> MetricResult:
    """
    Factory function to create a MetricResult.

    Usage:
        m = metric(
            name="build_status",
            value="succeeded",
            expected="succeeded",
            condition=build_status == "succeeded",
            message="Build completed successfully"
        )
    """
    return MetricResult(
        name=name,
        value=value,
        expected=expected,
        passed=condition,
        message=message,
        severity=severity,
        metadata=dict(metadata),
    )
