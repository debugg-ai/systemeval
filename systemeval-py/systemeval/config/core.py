"""
Core SystemEvalConfig class.

This module contains the main configuration class that orchestrates
multi-project and single-project test configurations.
"""
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

if TYPE_CHECKING:
    from systemeval.e2e.types import E2EConfig as E2ETypesConfig

# Import from other config modules - use relative imports
from .adapters import (
    PipelineConfig,
    PlaywrightConfig,
    PytestConfig,
    SurferConfig,
    TestCategory,
)
from .e2e import E2EConfig
from .environments import AnyEnvironmentConfig, CompositeEnvConfig
from .multiproject import DefaultsConfig, SubprojectConfig


class SystemEvalConfig(BaseModel):
    """
    Main configuration model supporting both v1.0 (single-project) and v2.0 (multi-project).

    V2.0 Multi-Project Mode:
        When version="2.0" and subprojects is defined, the config operates in
        multi-project mode where each subproject can have its own adapter,
        test directory, environment variables, and pre-commands.

    V1.0 Legacy Mode (default):
        When version is missing or "1.0", the config operates in single-project
        mode for backward compatibility with existing configurations.

    Example v2.0 config:
        version: "2.0"
        project_root: .
        defaults:
          timeout: 300
        subprojects:
          - name: backend
            path: backend
            adapter: pytest
            env:
              DJANGO_SETTINGS_MODULE: config.settings.test
          - name: frontend
            path: app
            adapter: vitest
    """
    # V2.0 fields
    version: str = Field(default="1.0", description="Config version: '1.0' (legacy) or '2.0' (multi-project)")
    defaults: Optional[DefaultsConfig] = Field(default=None, description="Global defaults for all subprojects (v2.0)")
    subprojects: List[SubprojectConfig] = Field(default_factory=list, description="Subproject configurations (v2.0)")

    # Legacy v1.0 fields (maintained for backward compatibility)
    adapter: str = Field(default="pytest", description="Test adapter to use (pytest, jest, pipeline, playwright, surfer)")
    project_root: Path = Field(default=Path("."), description="Project root directory")
    test_directory: Path = Field(default=Path("tests"), description="Test directory path")
    categories: Dict[str, TestCategory] = Field(default_factory=dict)
    adapter_config: Dict[str, Any] = Field(default_factory=dict, description="Adapter-specific config")
    pytest_config: Optional[PytestConfig] = None
    pipeline_config: Optional[PipelineConfig] = None
    playwright_config: Optional[PlaywrightConfig] = None
    surfer_config: Optional[SurferConfig] = None
    e2e: Optional[E2EConfig] = Field(
        default=None,
        description="E2E test generation configuration"
    )
    project_name: Optional[str] = None
    environments: Dict[str, AnyEnvironmentConfig] = Field(
        default_factory=dict,
        description="Environment configurations for multi-env testing"
    )

    # Runtime fields (not from YAML)
    _is_multi_project: bool = False

    @property
    def is_multi_project(self) -> bool:
        """Check if config is in multi-project mode."""
        return self.version == "2.0" and len(self.subprojects) > 0

    def get_enabled_subprojects(self, tags: Optional[List[str]] = None, names: Optional[List[str]] = None) -> List[SubprojectConfig]:
        """
        Get enabled subprojects, optionally filtered by tags or names.

        Args:
            tags: If provided, only return subprojects that have at least one matching tag
            names: If provided, only return subprojects with matching names

        Returns:
            List of enabled SubprojectConfig objects
        """
        result = [sp for sp in self.subprojects if sp.enabled]

        if names:
            result = [sp for sp in result if sp.name in names]

        if tags:
            result = [sp for sp in result if any(tag in sp.tags for tag in tags)]

        return result

    def get_subproject(self, name: str) -> Optional[SubprojectConfig]:
        """Get a specific subproject by name."""
        for sp in self.subprojects:
            if sp.name == name:
                return sp
        return None

    def get_effective_timeout(self, subproject: Optional[SubprojectConfig] = None) -> int:
        """Get effective timeout, considering subproject override and defaults."""
        if subproject and subproject.timeout is not None:
            return subproject.timeout
        if self.defaults and self.defaults.timeout:
            return self.defaults.timeout
        return 300  # Default fallback

    def get_e2e_config(self, api_key_override: Optional[str] = None) -> Optional["E2ETypesConfig"]:
        """
        Get E2E configuration converted to the E2E module's config type.

        Args:
            api_key_override: Optional API key to override config value (from CLI)

        Returns:
            E2EConfig from systemeval.e2e.types, or None if E2E not configured

        Raises:
            ValueError: If E2E is configured but api_key is required and missing
        """
        if self.e2e is None or not self.e2e.enabled:
            return None

        # Lazy import to prevent circular dependencies
        from systemeval.e2e import E2EConfig as E2ETypesConfig

        # Resolve API key: CLI override > config > None
        api_key = api_key_override or self.e2e.provider.api_key

        # Validate API key for debuggai provider
        if self.e2e.provider.provider == "debuggai" and not api_key:
            raise ValueError(
                "API key is required for DebuggAI provider. "
                "Set e2e.provider.api_key in config or pass --api-key via CLI."
            )

        output_dir = self.project_root / self.e2e.output.directory
        return E2ETypesConfig(
            provider_name=self.e2e.provider.provider,
            project_root=self.project_root,
            api_key=api_key,
            api_base_url=self.e2e.provider.api_base_url,
            project_slug=self.e2e.provider.project_slug,
            output_directory=output_dir,
            timeout_seconds=self.e2e.provider.timeout_seconds,
            test_framework=self.e2e.output.test_framework,
            programming_language=self.e2e.output.programming_language,
        )

    def has_e2e_config(self) -> bool:
        """Check if E2E configuration is present and enabled."""
        return self.e2e is not None and self.e2e.enabled

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        """Validate config version."""
        valid_versions = {"1.0", "2.0"}
        if v not in valid_versions:
            raise ValueError(f"Invalid version '{v}'. Must be one of: {valid_versions}")
        return v

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, v: str) -> str:
        """Validate adapter name."""
        # Lazy import to prevent circular dependencies
        from systemeval.adapters import list_adapters

        allowed_adapters = list_adapters()
        if allowed_adapters and v not in allowed_adapters:
            raise ValueError(f"Adapter '{v}' not registered. Available: {allowed_adapters}")
        return v

    @field_validator("project_root", "test_directory", mode="before")
    @classmethod
    def validate_paths(cls, v: Any) -> Path:
        """Ensure paths are Path objects."""
        return Path(v) if not isinstance(v, Path) else v

    @field_validator("environments", mode="before")
    @classmethod
    def validate_environments(cls, v: Any) -> Dict[str, AnyEnvironmentConfig]:
        """Convert raw dicts to typed environment configs."""
        if not isinstance(v, dict):
            return v
        # Import here to avoid circular dependency
        from .environments import parse_environment_config

        result: Dict[str, AnyEnvironmentConfig] = {}
        for name, config in v.items():
            if isinstance(config, dict):
                result[name] = parse_environment_config(name, config)
            else:
                result[name] = config
        return result

    @field_validator("subprojects", mode="before")
    @classmethod
    def validate_subprojects(cls, v: Any) -> List[SubprojectConfig]:
        """Convert raw dicts to SubprojectConfig objects."""
        if not isinstance(v, list):
            return v
        result: List[SubprojectConfig] = []
        for item in v:
            if isinstance(item, dict):
                result.append(SubprojectConfig(**item))
            elif isinstance(item, SubprojectConfig):
                result.append(item)
            else:
                raise ValueError(f"Invalid subproject configuration: {item}")
        return result

    @model_validator(mode="after")
    def validate_config(self) -> "SystemEvalConfig":
        """Validate configuration consistency."""
        # Validate composite environment dependencies
        for name, env_config in self.environments.items():
            if env_config.type == "composite":
                if isinstance(env_config, CompositeEnvConfig):
                    deps = env_config.depends_on
                    for dep in deps:
                        if dep not in self.environments:
                            raise ValueError(
                                f"Environment '{name}' depends on '{dep}' which is not defined"
                            )

        # Validate subproject names are unique
        if self.subprojects:
            names = [sp.name for sp in self.subprojects]
            if len(names) != len(set(names)):
                duplicates = [n for n in names if names.count(n) > 1]
                raise ValueError(f"Duplicate subproject names: {set(duplicates)}")

        # Validate v2.0 config has subprojects or warn
        if self.version == "2.0" and not self.subprojects:
            import warnings
            warnings.warn(
                "Config version is 2.0 but no subprojects defined. "
                "Consider using version 1.0 or adding subprojects."
            )

        return self
