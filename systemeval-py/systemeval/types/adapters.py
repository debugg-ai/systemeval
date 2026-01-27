"""
Adapter configuration types.

This module contains the AdapterConfig dataclass used to configure
test framework adapters with consistent parameters.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


@dataclass
class AdapterConfig:
    """
    Standardized configuration for test framework adapters.

    This dataclass provides a consistent interface for configuring adapters,
    replacing the varied constructor signatures across different adapter types.

    Common fields are defined at the top level, while adapter-specific settings
    are stored in the `extra` dictionary.

    Usage:
        # Basic configuration
        config = AdapterConfig(project_root="/path/to/project")

        # With test directory and markers
        config = AdapterConfig(
            project_root="/path/to/project",
            test_directory="tests",
            markers=["unit", "integration"],
        )

        # With adapter-specific settings
        config = AdapterConfig(
            project_root="/path/to/project",
            extra={
                "config_file": "playwright.config.ts",
                "headed": True,
            }
        )
    """

    # Required: path to the project root directory
    project_root: Union[str, Path]
    """Absolute path to the project root directory."""

    # Test discovery and filtering
    test_directory: Optional[str] = None
    """Relative path to test directory from project_root (e.g., 'tests')."""

    markers: List[str] = field(default_factory=list)
    """List of test markers/categories to filter by (e.g., ['unit', 'integration'])."""

    # Execution options
    parallel: bool = False
    """Enable parallel test execution."""

    coverage: bool = False
    """Enable coverage collection."""

    timeout: Optional[int] = None
    """Default timeout in seconds for test execution."""

    verbose: bool = False
    """Enable verbose output."""

    # Adapter-specific configuration
    extra: Dict[str, Any] = field(default_factory=dict)
    """
    Adapter-specific configuration options.

    Examples:
        - PytestAdapter: {}  # Uses defaults
        - PlaywrightAdapter: {"config_file": "playwright.config.ts", "headed": True}
        - SurferAdapter: {"project_slug": "my-project", "api_key": "..."}
        - PipelineAdapter: {"retry_config": RetryConfig(...)}
    """

    def __post_init__(self) -> None:
        """Validate and normalize configuration."""
        # Ensure project_root is a string
        if isinstance(self.project_root, Path):
            self.project_root = str(self.project_root)

        # Validate project_root is absolute
        if not Path(self.project_root).is_absolute():
            raise ValueError(
                f"project_root must be an absolute path, got: {self.project_root}"
            )

    def get(self, key: str, default: Any = None) -> Any:
        """Get an extra configuration value with a default."""
        return self.extra.get(key, default)

    def with_extra(self, **kwargs: Any) -> "AdapterConfig":
        """Create a new config with additional extra settings."""
        new_extra = {**self.extra, **kwargs}
        return AdapterConfig(
            project_root=self.project_root,
            test_directory=self.test_directory,
            markers=self.markers.copy(),
            parallel=self.parallel,
            coverage=self.coverage,
            timeout=self.timeout,
            verbose=self.verbose,
            extra=new_extra,
        )

    @classmethod
    def from_project_root(cls, project_root: Union[str, Path]) -> "AdapterConfig":
        """Create a minimal config with just the project root."""
        return cls(project_root=project_root)


__all__ = ["AdapterConfig"]
