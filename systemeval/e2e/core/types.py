"""
Type definitions for E2E test generation.

This module contains all data structures used in E2E test generation,
following systemeval's dataclass-based pattern.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class ChangeType(str, Enum):
    """Type of code change detected."""
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"


class GenerationStatus(str, Enum):
    """Status of E2E test generation."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ============================================================================
# Change Analysis
# ============================================================================


@dataclass
class Change:
    """
    Represents a single file change in a repository.

    This is a value object containing all information about a code change
    needed for E2E test generation.
    """

    file_path: str
    """Relative path from repository root (e.g., 'src/api/users.py')."""

    change_type: ChangeType
    """Type of change (added, modified, deleted, renamed)."""

    old_path: Optional[str] = None
    """Previous path if renamed, None otherwise."""

    additions: int = 0
    """Number of lines added."""

    deletions: int = 0
    """Number of lines deleted."""

    diff: Optional[str] = None
    """Full diff content (optional, may be large)."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    def __post_init__(self) -> None:
        """Validate change data."""
        if self.change_type == ChangeType.RENAMED and not self.old_path:
            raise ValueError("old_path is required for renamed files")

        if self.additions < 0 or self.deletions < 0:
            raise ValueError("additions and deletions must be non-negative")

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "file_path": self.file_path,
            "change_type": self.change_type.value,
            "old_path": self.old_path,
            "additions": self.additions,
            "deletions": self.deletions,
            "has_diff": self.diff is not None,
            "metadata": self.metadata,
        }


@dataclass
class ChangeSet:
    """
    Collection of changes from a git diff or similar comparison.

    This represents the complete set of changes that need E2E test coverage.
    """

    base_ref: str
    """Base git reference (commit SHA, branch, tag)."""

    head_ref: str
    """Head git reference (commit SHA, branch, tag)."""

    changes: List[Change]
    """List of individual file changes."""

    repository_root: Path
    """Absolute path to repository root."""

    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    """When this changeset was created."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional context (e.g., branch name, PR number, author)."""

    def __post_init__(self) -> None:
        """Validate changeset data."""
        # Ensure repository_root is absolute
        if not self.repository_root.is_absolute():
            raise ValueError(
                f"repository_root must be an absolute path, got: {self.repository_root}"
            )

        # Validate changes is a list
        if not isinstance(self.changes, list):
            raise TypeError("changes must be a list")

    @property
    def total_changes(self) -> int:
        """Total number of file changes."""
        return len(self.changes)

    @property
    def total_additions(self) -> int:
        """Total lines added across all changes."""
        return sum(c.additions for c in self.changes)

    @property
    def total_deletions(self) -> int:
        """Total lines deleted across all changes."""
        return sum(c.deletions for c in self.changes)

    def get_changes_by_type(self, change_type: ChangeType) -> List[Change]:
        """Filter changes by type."""
        return [c for c in self.changes if c.change_type == change_type]

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "base_ref": self.base_ref,
            "head_ref": self.head_ref,
            "repository_root": str(self.repository_root),
            "timestamp": self.timestamp,
            "total_changes": self.total_changes,
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
            "changes": [c.to_dict() for c in self.changes],
            "metadata": self.metadata,
        }


# ============================================================================
# E2E Configuration
# ============================================================================


@dataclass
class E2EConfig:
    """
    Configuration for E2E test generation.

    This is explicitly provided by the caller - no discovery, no magic.
    All parameters are explicit and validated.
    """

    provider_name: str
    """Name of the E2E provider (e.g., 'surfer', 'custom_provider')."""

    project_root: Path
    """Absolute path to project root directory."""

    # API Configuration
    api_key: Optional[str] = None
    """API key for provider authentication (explicit, not from env)."""

    api_base_url: Optional[str] = None
    """Base URL for provider API (explicit, not discovered)."""

    # Project Configuration
    project_slug: Optional[str] = None
    """Project identifier in provider system."""

    project_url: Optional[str] = None
    """Base URL of the application under test."""

    # Generation Options
    test_framework: str = "playwright"
    """Target test framework (playwright, cypress, selenium)."""

    programming_language: str = "typescript"
    """Programming language for generated tests."""

    output_directory: Optional[Path] = None
    """Where to write generated tests (defaults to project_root/e2e_generated)."""

    # Execution Options
    timeout_seconds: int = 300
    """Maximum time to wait for test generation."""

    max_tests: Optional[int] = None
    """Maximum number of tests to generate."""

    parallel: bool = False
    """Generate tests in parallel if supported."""

    # Provider-specific options
    extra: Dict[str, Any] = field(default_factory=dict)
    """
    Provider-specific configuration options.

    Examples:
        - SurferProvider: {"browser": "chromium", "viewport": "1920x1080"}
        - CustomProvider: {"model": "gpt-4", "temperature": 0.7}
    """

    def __post_init__(self) -> None:
        """Validate configuration."""
        # Validate project_root is absolute
        if not self.project_root.is_absolute():
            raise ValueError(
                f"project_root must be an absolute path, got: {self.project_root}"
            )

        # Validate timeout
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")

        # Validate max_tests if provided
        if self.max_tests is not None and self.max_tests <= 0:
            raise ValueError("max_tests must be positive")

        # Set default output directory
        if self.output_directory is None:
            self.output_directory = self.project_root / "e2e_generated"
        elif not self.output_directory.is_absolute():
            # Make relative paths absolute relative to project_root
            self.output_directory = self.project_root / self.output_directory

    def get(self, key: str, default: Any = None) -> Any:
        """Get an extra configuration value with a default."""
        return self.extra.get(key, default)

    def with_extra(self, **kwargs: Any) -> "E2EConfig":
        """Create a new config with additional extra settings."""
        new_extra = {**self.extra, **kwargs}
        return E2EConfig(
            provider_name=self.provider_name,
            project_root=self.project_root,
            api_key=self.api_key,
            api_base_url=self.api_base_url,
            project_slug=self.project_slug,
            project_url=self.project_url,
            test_framework=self.test_framework,
            programming_language=self.programming_language,
            output_directory=self.output_directory,
            timeout_seconds=self.timeout_seconds,
            max_tests=self.max_tests,
            parallel=self.parallel,
            extra=new_extra,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "provider_name": self.provider_name,
            "project_root": str(self.project_root),
            "api_key": "***" if self.api_key else None,  # Redact sensitive data
            "api_base_url": self.api_base_url,
            "project_slug": self.project_slug,
            "project_url": self.project_url,
            "test_framework": self.test_framework,
            "programming_language": self.programming_language,
            "output_directory": str(self.output_directory) if self.output_directory else None,
            "timeout_seconds": self.timeout_seconds,
            "max_tests": self.max_tests,
            "parallel": self.parallel,
            "extra": self.extra,
        }


# ============================================================================
# E2E Provider Results
# ============================================================================


@dataclass
class ValidationResult:
    """Result of validating E2E configuration."""

    valid: bool
    """Whether the configuration is valid."""

    errors: List[str] = field(default_factory=list)
    """List of validation error messages."""

    warnings: List[str] = field(default_factory=list)
    """List of validation warnings (non-blocking)."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional validation metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "valid": self.valid,
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


@dataclass
class GenerationResult:
    """Result of initiating E2E test generation."""

    run_id: str
    """Unique identifier for this generation run."""

    status: GenerationStatus
    """Current status of generation."""

    message: Optional[str] = None
    """Human-readable status message."""

    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    """When generation started."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "message": self.message,
            "started_at": self.started_at,
            "metadata": self.metadata,
        }


@dataclass
class StatusResult:
    """Result of checking E2E generation status."""

    run_id: str
    """Unique identifier for this generation run."""

    status: GenerationStatus
    """Current status of generation."""

    message: Optional[str] = None
    """Human-readable status message."""

    progress_percent: Optional[float] = None
    """Progress percentage (0-100) if available."""

    tests_generated: int = 0
    """Number of tests generated so far."""

    completed_at: Optional[str] = None
    """When generation completed (if status is COMPLETED or FAILED)."""

    error: Optional[str] = None
    """Error message if status is FAILED."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "message": self.message,
            "progress_percent": self.progress_percent,
            "tests_generated": self.tests_generated,
            "completed_at": self.completed_at,
            "error": self.error,
            "metadata": self.metadata,
        }


@dataclass
class ArtifactResult:
    """Result of downloading E2E test artifacts."""

    run_id: str
    """Unique identifier for this generation run."""

    output_directory: Path
    """Where artifacts were downloaded."""

    test_files: List[Path]
    """List of generated test file paths."""

    total_tests: int = 0
    """Total number of tests in generated files."""

    total_size_bytes: int = 0
    """Total size of downloaded artifacts in bytes."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "output_directory": str(self.output_directory),
            "test_files": [str(f) for f in self.test_files],
            "total_tests": self.total_tests,
            "total_size_bytes": self.total_size_bytes,
            "metadata": self.metadata,
        }


@dataclass
class CompletionResult:
    """Result of awaiting E2E generation completion."""

    run_id: str
    """Unique identifier for this generation run."""

    status: GenerationStatus
    """Final status of generation."""

    completed: bool
    """Whether generation completed (successfully or with failure)."""

    timed_out: bool
    """Whether the wait operation timed out."""

    duration_seconds: float = 0.0
    """How long we waited (may be less than timeout if completed early)."""

    final_message: Optional[str] = None
    """Final status message."""

    error: Optional[str] = None
    """Error message if status is FAILED."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional provider-specific metadata."""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "completed": self.completed,
            "timed_out": self.timed_out,
            "duration_seconds": self.duration_seconds,
            "final_message": self.final_message,
            "error": self.error,
            "metadata": self.metadata,
        }


# ============================================================================
# E2E Orchestrator Results
# ============================================================================


@dataclass
class E2EResult:
    """
    Complete result of E2E test generation orchestration.

    This is the final output of the orchestrator that combines all stages:
    change analysis, generation, status monitoring, and artifact download.
    """

    # Input context
    changeset: ChangeSet
    """The changes that were analyzed."""

    config: E2EConfig
    """Configuration used for generation."""

    # Generation results
    generation: GenerationResult
    """Initial generation result."""

    completion: CompletionResult
    """Result of waiting for completion."""

    artifacts: Optional[ArtifactResult] = None
    """Downloaded artifacts (None if generation failed)."""

    # Timing
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    completed_at: Optional[str] = None
    total_duration_seconds: float = 0.0

    # Overall status
    success: bool = False
    """Whether E2E generation succeeded end-to-end."""

    error: Optional[str] = None
    """Error message if generation failed."""

    warnings: List[str] = field(default_factory=list)
    """Non-blocking warnings from the process."""

    metadata: Dict[str, Any] = field(default_factory=dict)
    """Additional orchestrator metadata."""

    def finalize(self, success: bool = True, error: Optional[str] = None) -> None:
        """Finalize the E2E result with completion time."""
        self.completed_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self.success = success
        self.error = error

        # Calculate total duration from started_at to now
        try:
            started = datetime.fromisoformat(self.started_at.replace("Z", "+00:00"))
            completed = datetime.fromisoformat(self.completed_at.replace("Z", "+00:00"))
            self.total_duration_seconds = (completed - started).total_seconds()
        except (ValueError, AttributeError):
            # Fallback if timestamp parsing fails
            self.total_duration_seconds = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "changeset": self.changeset.to_dict(),
            "config": self.config.to_dict(),
            "generation": self.generation.to_dict(),
            "completion": self.completion.to_dict(),
            "artifacts": self.artifacts.to_dict() if self.artifacts else None,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "total_duration_seconds": self.total_duration_seconds,
            "success": self.success,
            "error": self.error,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }
