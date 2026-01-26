"""Core E2E types and protocols."""

from .types import (
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

from .protocols import (
    E2EProvider,
    E2EOrchestrator,
)

__all__ = [
    # Types
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
    # Protocols
    "E2EProvider",
    "E2EOrchestrator",
]
