"""
Backward compatibility shim for e2e types.

After Phase 2 reorganization, types moved to e2e/core/types.py
This file provides backward compatibility for imports like:
    from systemeval.e2e.types import E2EConfig

Prefer importing from systemeval.e2e directly:
    from systemeval.e2e import E2EConfig
"""

from .core.types import (
    Change,
    ChangeSet,
    ChangeType,
    GenerationStatus,
    E2EConfig,
    GenerationResult,
    StatusResult,
    ArtifactResult,
    ValidationResult,
    CompletionResult,
    E2EResult,
)

__all__ = [
    "Change",
    "ChangeSet",
    "ChangeType",
    "GenerationStatus",
    "E2EConfig",
    "GenerationResult",
    "StatusResult",
    "ArtifactResult",
    "ValidationResult",
    "CompletionResult",
    "E2EResult",
]
