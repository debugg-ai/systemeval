"""
DEPRECATED - DO NOT USE IN NEW CODE

This module contains legacy result classes that are being phased out.

USE INSTEAD:
- systemeval.core.evaluation.EvaluationResult (PRIMARY schema)
- systemeval.core.evaluation.SessionResult
- systemeval.core.evaluation.MetricResult

DEPRECATION PLAN:
- Phase 1: All internal code migrated to evaluation.py (DONE)
- Phase 2: Add deprecation warnings (CURRENT)
- Phase 3: Remove this file entirely (Future)

The classes in this file (SequenceResult, SessionResult, MetricResult)
have naming conflicts with the canonical classes in evaluation.py.

If you're seeing this file in new code, you're using the wrong schema.
See systemeval/core/__init__.py docstring for the correct flow.

CASCADE LOGIC (for legacy reference):
- ANY metric fails → session FAILS
- ANY session fails → sequence FAILS
- Exit code: 0 = PASS, 1 = FAIL (binary, no other codes)
"""

import warnings

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

# Import canonical Verdict from evaluation module
from .evaluation import Verdict


@dataclass
class MetricResult:
    """
    DEPRECATED: Use systemeval.core.evaluation.MetricResult instead.

    Result of evaluating a single metric.
    """

    name: str
    value: Any
    passed: bool
    failure_message: Optional[str] = None

    def __post_init__(self):
        warnings.warn(
            "MetricResult from result.py is deprecated. "
            "Use systemeval.core.evaluation.MetricResult instead.",
            DeprecationWarning,
            stacklevel=2
        )


@dataclass
class SessionResult:
    """
    DEPRECATED: Use systemeval.core.evaluation.SessionResult instead.

    Result for a single test session (e.g., one test category, one project).

    CASCADE RULE: If ANY metric fails, the session FAILS.
    """

    session_id: str
    session_name: str
    metrics: List[MetricResult] = field(default_factory=list)
    raw_data: Dict[str, Any] = field(default_factory=dict)  # For renderer access
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        warnings.warn(
            "SessionResult from result.py is deprecated. "
            "Use systemeval.core.evaluation.SessionResult instead.",
            DeprecationWarning,
            stacklevel=2
        )

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
    DEPRECATED: Use systemeval.core.evaluation.EvaluationResult instead.

    Result for an entire test sequence (multiple sessions).

    CASCADE RULE: If ANY session fails, the sequence FAILS.
    """

    sequence_id: str
    sequence_name: str
    sessions: List[SessionResult] = field(default_factory=list)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def __post_init__(self):
        warnings.warn(
            "SequenceResult from result.py is deprecated. "
            "Use systemeval.core.evaluation.EvaluationResult instead.",
            DeprecationWarning,
            stacklevel=2
        )

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
