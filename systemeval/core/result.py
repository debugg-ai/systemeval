"""
Unified Test Result Framework

Core data structures for deterministic pass/fail evaluation.
Framework-agnostic result types for test execution reporting.

CASCADE LOGIC:
- ANY metric fails → session FAILS
- ANY session fails → sequence FAILS
- Exit code: 0 = PASS, 1 = FAIL (binary, no other codes)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class Verdict(Enum):
    """Binary verdict - no middle ground."""

    PASS = "PASS"
    FAIL = "FAIL"


@dataclass
class MetricResult:
    """Result of evaluating a single metric."""

    name: str
    value: Any
    passed: bool
    failure_message: Optional[str] = None


@dataclass
class SessionResult:
    """
    Result for a single test session (e.g., one test category, one project).

    CASCADE RULE: If ANY metric fails, the session FAILS.
    """

    session_id: str
    session_name: str
    metrics: List[MetricResult] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)  # For renderer access
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def verdict(self) -> Verdict:
        """Session passes ONLY if ALL metrics pass."""
        if not self.metrics:
            return Verdict.FAIL  # No metrics = fail (can't verify success)
        return Verdict.PASS if all(m.passed for m in self.metrics) else Verdict.FAIL

    @property
    def failed_metrics(self) -> List[MetricResult]:
        """Get list of failed metrics for reporting."""
        return [m for m in self.metrics if not m.passed]

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate session duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None


@dataclass
class SequenceResult:
    """
    Result for an entire test sequence (multiple sessions).

    CASCADE RULE: If ANY session fails, the sequence FAILS.
    """

    sequence_id: str
    sequence_name: str
    sessions: List[SessionResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @property
    def verdict(self) -> Verdict:
        """Sequence passes ONLY if ALL sessions pass."""
        if not self.sessions:
            return Verdict.FAIL  # No sessions = fail
        return (
            Verdict.PASS
            if all(s.verdict == Verdict.PASS for s in self.sessions)
            else Verdict.FAIL
        )

    @property
    def failed_sessions(self) -> List[SessionResult]:
        """Get list of failed sessions for reporting."""
        return [s for s in self.sessions if s.verdict == Verdict.FAIL]

    @property
    def exit_code(self) -> int:
        """Exit code: 0 = PASS, 1 = FAIL. Binary, period."""
        return 0 if self.verdict == Verdict.PASS else 1

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate total sequence duration in seconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

    @property
    def pass_count(self) -> int:
        """Count of passed sessions."""
        return sum(1 for s in self.sessions if s.verdict == Verdict.PASS)

    @property
    def fail_count(self) -> int:
        """Count of failed sessions."""
        return sum(1 for s in self.sessions if s.verdict == Verdict.FAIL)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "sequence_id": self.sequence_id,
            "sequence_name": self.sequence_name,
            "verdict": self.verdict.value,
            "exit_code": self.exit_code,
            "duration_seconds": self.duration_seconds,
            "pass_count": self.pass_count,
            "fail_count": self.fail_count,
            "sessions": [
                {
                    "session_id": s.session_id,
                    "session_name": s.session_name,
                    "verdict": s.verdict.value,
                    "duration_seconds": s.duration_seconds,
                    "metrics": [
                        {
                            "name": m.name,
                            "value": m.value,
                            "passed": m.passed,
                            "failure_message": m.failure_message,
                        }
                        for m in s.metrics
                    ],
                }
                for s in self.sessions
            ],
        }
