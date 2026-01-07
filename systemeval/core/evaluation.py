"""Unified EvaluationResult schema for SystemEval."""
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

# Import Verdict from shared types module
from systemeval.types import Verdict

# Schema version - bump on breaking changes
SCHEMA_VERSION = "1.0.0"


class Severity(str, Enum):
    """Severity level for metric failures."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class MetricResult:
    """Result of evaluating a single metric/criterion."""
    name: str
    value: Any
    expected: Any
    passed: bool
    message: Optional[str] = None
    severity: Union[str, Severity] = Severity.ERROR
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        """Validate severity field."""
        # Convert string to Severity enum if needed
        if isinstance(self.severity, str):
            try:
                self.severity = Severity(self.severity)
            except ValueError:
                valid_values = ", ".join([s.value for s in Severity])
                raise ValueError(
                    f"Invalid severity value '{self.severity}'. "
                    f"Must be one of: {valid_values}"
                )
        elif not isinstance(self.severity, Severity):
            raise TypeError(
                f"severity must be a string or Severity enum, got {type(self.severity).__name__}"
            )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "value": self.value,
            "expected": self.expected,
            "passed": self.passed,
            "message": self.message,
            "severity": self.severity.value,
            "metadata": self.metadata,
        }


@dataclass
class SessionResult:
    """Result for a single evaluation session."""
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
    """Non-fungible metadata for unique identification."""
    # Unique identifiers
    evaluation_id: str  # UUID4 - globally unique

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
    """Unified result schema for all evaluations."""
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
        """Compute verdict from sessions."""
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
        """Finalize the evaluation and compute duration."""
        if self._finalized:
            return

        # Compute duration
        if self._start_time:
            self.metadata.duration_seconds = time.time() - self._start_time

        self._finalized = True

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
    """Factory function to create an EvaluationResult with proper metadata."""
    # Capture environment context
    env_context = dict(environment or {})

    # Git context
    try:
        git_commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        env_context["git_commit"] = git_commit[:12]
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        # Git not available or not a git repo - skip git context
        pass

    try:
        git_branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        env_context["git_branch"] = git_branch
    except (subprocess.CalledProcessError, OSError, FileNotFoundError):
        # Git not available or not a git repo - skip git context
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
    """Factory function to create a SessionResult."""
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
    severity: Union[str, Severity] = Severity.ERROR,
    **metadata: Any,
) -> MetricResult:
    """Factory function to create a MetricResult."""
    return MetricResult(
        name=name,
        value=value,
        expected=expected,
        passed=condition,
        message=message,
        severity=severity,
        metadata=dict(metadata),
    )
