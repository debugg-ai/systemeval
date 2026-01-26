"""
E2E Configuration for systemeval.

Architecture Principles:
------------------------
This module follows STRICT configuration principles:

1. **No config discovery**: Config passed explicitly at startup, no searching cwd, no env var magic
2. **No cascading fallbacks**: No "try this, then that" patterns
3. **No magic values**: All values explicit in config
4. **Fail fast**: Invalid config raises ValueError immediately
5. **Type safety**: Pydantic models enforce structure at runtime

Design Rationale:
-----------------
E2E testing requires coordination with external services (DebuggAI, etc).
Unlike unit tests, E2E configs must be explicit about:
- API credentials (never auto-discovered from env)
- Service URLs (no defaults - must be explicit)
- Timeouts and polling intervals (explicit, testable values)
- Output directories (no cwd assumptions)

Integration with systemeval:
-----------------------------
- Follows same Pydantic pattern as config.py
- Integrates with types.py result patterns
- Uses Field() for validation like SubprojectConfig
- No env var fallbacks (unlike legacy SurferConfig)

Provider Pattern:
-----------------
E2E tests can run against multiple providers (DebuggAI, local, etc).
Provider-specific config is stored in provider_config dict, validated
by provider-specific Pydantic models.
""" 
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, field_validator


# ============================================================================
# Provider-Specific Configuration Models
# ============================================================================


class DebuggAIProviderConfig(BaseModel):
    """
    Configuration for DebuggAI provider.

    CRITICAL: No environment variable fallbacks.
    All values must be passed explicitly by the caller.

    Example:
        config = DebuggAIProviderConfig(
            api_key="sk_live_...",
            api_url="https://api.debugg.ai",
            project_id="my-project",
        )

    Anti-pattern (DO NOT DO):
        # NO env var fallbacks
        api_key = os.getenv("DEBUGGAI_API_KEY", config.get("api_key"))

        # NO default URLs
        api_url = config.get("api_url", "https://api.debugg.ai")
    """

    api_key: str = Field(
        ...,
        description="DebuggAI API key (explicit, NOT from env var)",
        min_length=1,
    )

    api_url: str = Field(
        ...,
        description="DebuggAI API base URL (explicit, no defaults)",
        min_length=1,
    )

    project_id: Optional[str] = Field(
        default=None,
        description="DebuggAI project ID (optional, can be specified per test)",
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate API key format."""
        if not v or not v.strip():
            raise ValueError("api_key cannot be empty")
        return v.strip()

    @field_validator("api_url")
    @classmethod
    def validate_api_url(cls, v: str) -> str:
        """Validate API URL format."""
        if not v or not v.strip():
            raise ValueError("api_url cannot be empty")

        v = v.strip().rstrip("/")

        # Must be HTTP/HTTPS URL
        if not v.startswith(("http://", "https://")):
            raise ValueError(f"api_url must start with http:// or https://, got: {v}")

        return v

    @field_validator("project_id")
    @classmethod
    def validate_project_id(cls, v: Optional[str]) -> Optional[str]:
        """Validate project ID if provided."""
        if v is not None and not v.strip():
            raise ValueError("project_id cannot be empty string (use None instead)")
        return v.strip() if v else None


class LocalProviderConfig(BaseModel):
    """
    Configuration for local E2E test runner.

    Used when running E2E tests against local services without external APIs.

    Example:
        config = LocalProviderConfig(
            base_url="http://localhost:3000",
            timeout_seconds=60,
        )
    """

    base_url: str = Field(
        ...,
        description="Base URL for local service",
        min_length=1,
    )

    timeout_seconds: int = Field(
        default=60,
        description="Request timeout in seconds",
        ge=1,
        le=600,
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base URL format."""
        if not v or not v.strip():
            raise ValueError("base_url cannot be empty")

        v = v.strip().rstrip("/")

        if not v.startswith(("http://", "https://")):
            raise ValueError(f"base_url must start with http:// or https://, got: {v}")

        return v


# ============================================================================
# Top-Level E2E Configuration
# ============================================================================


class E2EConfig(BaseModel):
    """
    Top-level E2E test configuration.

    This is the root config object passed to E2E test runners.
    It specifies which provider to use and provider-specific settings.

    Design Principles:
    ------------------
    1. No config discovery - passed explicitly at startup
    2. No cascading fallbacks - single source of truth
    3. No magic values - all paths, URLs, timeouts are explicit
    4. Fail fast - invalid config raises ValueError

    Usage:
        # Construct explicitly
        config = E2EConfig(
            provider="debuggai",
            provider_config={
                "api_key": "sk_live_...",
                "api_url": "https://api.debugg.ai",
                "project_id": "my-project",
            },
            output_dir="/absolute/path/to/output",
            timeout_seconds=300,
            poll_interval_seconds=5,
        )

        # Validate provider config
        provider = config.get_provider_config()  # Returns DebuggAIProviderConfig

        # Use in E2E runner
        runner = E2ERunner(config)
        result = runner.run()

    Anti-patterns (DO NOT DO):
        # NO - config discovery
        config_path = find_e2e_config()  # NO

        # NO - env var magic
        output_dir = os.getenv("E2E_OUTPUT_DIR", ".")  # NO

        # NO - relative paths
        output_dir = "./output"  # NO - must be absolute
    """

    provider: Literal["debuggai", "local"] = Field(
        ...,
        description="E2E provider to use (debuggai, local)",
    )

    provider_config: Dict[str, Any] = Field(
        ...,
        description="Provider-specific configuration (validated against provider model)",
    )

    output_dir: Path = Field(
        ...,
        description="Absolute path to output directory (no defaults, no cwd assumptions)",
    )

    timeout_seconds: int = Field(
        default=300,
        description="Max time to wait for E2E test completion",
        ge=1,
        le=3600,
    )

    poll_interval_seconds: int = Field(
        default=5,
        description="Seconds between status checks",
        ge=1,
        le=60,
    )

    @field_validator("output_dir", mode="before")
    @classmethod
    def validate_output_dir(cls, v: Any) -> Path:
        """Validate output directory is an absolute path."""
        if isinstance(v, str):
            v = Path(v)
        elif not isinstance(v, Path):
            raise ValueError(f"output_dir must be Path or str, got: {type(v)}")

        # Must be absolute path
        if not v.is_absolute():
            raise ValueError(
                f"output_dir must be absolute path, got relative: {v}\n"
                "E2E config requires explicit paths - no cwd assumptions."
            )

        return v

    @field_validator("provider_config")
    @classmethod
    def validate_provider_config_dict(cls, v: Any) -> Dict[str, Any]:
        """Ensure provider_config is a dict."""
        if not isinstance(v, dict):
            raise ValueError(f"provider_config must be dict, got: {type(v)}")
        if not v:
            raise ValueError("provider_config cannot be empty")
        return v

    def get_provider_config(self) -> Union[DebuggAIProviderConfig, LocalProviderConfig]:
        """
        Get typed provider config based on provider type.

        Returns:
            Validated provider-specific config model

        Raises:
            ValueError: If provider_config is invalid for the selected provider
        """
        if self.provider == "debuggai":
            return DebuggAIProviderConfig(**self.provider_config)
        elif self.provider == "local":
            return LocalProviderConfig(**self.provider_config)
        else:
            # This should never happen due to Literal type, but handle it
            raise ValueError(f"Unknown provider: {self.provider}")

    @classmethod
    def for_debuggai(
        cls,
        api_key: str,
        api_url: str,
        output_dir: Path,
        project_id: Optional[str] = None,
        timeout_seconds: int = 300,
        poll_interval_seconds: int = 5,
    ) -> "E2EConfig":
        """
        Factory method for DebuggAI provider config.

        Example:
            config = E2EConfig.for_debuggai(
                api_key="sk_live_...",
                api_url="https://api.debugg.ai",
                output_dir=Path("/tmp/e2e-output"),
                project_id="my-project",
            )
        """
        return cls(
            provider="debuggai",
            provider_config={
                "api_key": api_key,
                "api_url": api_url,
                "project_id": project_id,
            },
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )

    @classmethod
    def for_local(
        cls,
        base_url: str,
        output_dir: Path,
        timeout_seconds: int = 60,
        poll_interval_seconds: int = 2,
    ) -> "E2EConfig":
        """
        Factory method for local provider config.

        Example:
            config = E2EConfig.for_local(
                base_url="http://localhost:3000",
                output_dir=Path("/tmp/e2e-output"),
            )
        """
        return cls(
            provider="local",
            provider_config={
                "base_url": base_url,
                "timeout_seconds": timeout_seconds,
            },
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
        )


# ============================================================================
# Configuration Validation Helpers
# ============================================================================


def validate_e2e_config(config_dict: Dict[str, Any]) -> E2EConfig:
    """
    Validate raw E2E config dictionary.

    Args:
        config_dict: Raw config from YAML, JSON, or dict

    Returns:
        Validated E2EConfig instance

    Raises:
        ValueError: If config is invalid
    """
    return E2EConfig(**config_dict)


def load_e2e_config_from_dict(config_dict: Dict[str, Any]) -> E2EConfig:
    """
    Load E2E config from dictionary.

    This is the primary entrypoint for E2E config creation.
    Unlike systemeval's load_config(), this does NOT search for files.

    Design:
    -------
    Config must be passed explicitly. No file discovery.
    Caller is responsible for reading config file and passing dict.

    Example:
        import yaml
        from pathlib import Path

        # Caller explicitly reads config file
        config_path = Path("/explicit/path/to/e2e_config.yaml")
        with open(config_path) as f:
            raw_config = yaml.safe_load(f)

        # Then passes to loader
        config = load_e2e_config_from_dict(raw_config)

    Anti-pattern (DO NOT DO):
        # NO - file discovery
        config = load_e2e_config()  # NO - where does it look?

        # NO - cwd assumptions
        config_path = Path("e2e_config.yaml")  # NO - which directory?
    """
    return validate_e2e_config(config_dict)
