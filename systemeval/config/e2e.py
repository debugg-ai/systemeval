"""
E2E test generation configuration models for systemeval.

This module contains Pydantic models for E2E test generation configuration:
- E2EProviderConfig: Base configuration for E2E test generation providers
- DebuggAIConfig: DebuggAI-specific configuration for E2E test generation
- E2EOutputConfig: Configuration for E2E test output
- E2EGitConfig: Configuration for E2E git analysis
- E2EConfig: Complete E2E test generation configuration

Architectural Principles:
- No env var sniffing: api_key must be explicit or passed via CLI
- No magic values: all configuration is validated
- Provider-agnostic: works with any E2EProvider implementation
"""
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class E2EProviderConfig(BaseModel):
    """
    Base configuration for E2E test generation providers.

    This follows strict architectural principles:
    - No env var sniffing: api_key must be explicit or passed via CLI
    - No magic values: all configuration is validated
    - Provider-agnostic: works with any E2EProvider implementation
    """
    provider: Literal["debuggai", "local", "mock"] = Field(
        default="debuggai",
        description="E2E provider to use (debuggai, local, mock)"
    )
    api_key: Optional[str] = Field(
        default=None,
        description="API key for provider authentication (required for debuggai)"
    )
    api_base_url: str = Field(
        default="https://api.debugg.ai",
        description="Base URL for provider API"
    )
    project_slug: Optional[str] = Field(
        default=None,
        description="Project identifier in provider system"
    )
    timeout_seconds: int = Field(
        default=600,
        ge=1,
        le=3600,
        description="Max time to wait for test generation (1-3600 seconds)"
    )
    poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Seconds between status checks (1-60 seconds)"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: Optional[str], info) -> Optional[str]:
        """Validate API key is provided for debuggai provider."""
        # Note: We don't enforce api_key here because it can be passed via CLI
        # The E2E commands will validate this at runtime
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("api_key cannot be empty string")
        return v

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, v: str) -> str:
        """Validate and normalize API base URL."""
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("api_base_url must start with http:// or https://")
        return v


class DebuggAIConfig(BaseModel):
    """
    DebuggAI-specific configuration for E2E test generation.

    This model captures all configuration options specific to the DebuggAI
    provider, with proper validation and documented defaults.

    Architectural Principles:
    - No environment variable discovery: api_key must be explicit
    - All defaults are documented with clear rationale
    - Validation ensures values are within acceptable ranges

    Example YAML:
        debuggai:
          api_key: sk_live_xxx  # Required, or pass via CLI --api-key
          api_base_url: https://api.debugg.ai
          timeout_seconds: 30
          poll_interval_seconds: 5
          max_wait_seconds: 600
          project_url: https://myapp.example.com
          test_framework: playwright
          language: typescript

    Default Values Rationale:
    - api_base_url: Production DebuggAI API endpoint
    - timeout_seconds: 30s is reasonable for HTTP request timeout
    - poll_interval_seconds: 5s balances responsiveness vs API load
    - max_wait_seconds: 600s (10min) allows for complex test generation
    """

    api_key: str = Field(
        ...,
        min_length=1,
        description="API key for DebuggAI authentication. Required, no env var discovery."
    )

    api_base_url: str = Field(
        default="https://api.debugg.ai",
        description="Base URL for DebuggAI API. Default: https://api.debugg.ai"
    )

    timeout_seconds: int = Field(
        default=30,
        ge=1,
        le=300,
        description="HTTP request timeout in seconds. Range: 1-300. Default: 30"
    )

    poll_interval_seconds: int = Field(
        default=5,
        ge=1,
        le=60,
        description="Seconds between status poll requests. Range: 1-60. Default: 5"
    )

    max_wait_seconds: int = Field(
        default=600,
        ge=1,
        le=3600,
        description="Maximum seconds to wait for test completion. Range: 1-3600. Default: 600 (10 minutes)"
    )

    project_url: Optional[str] = Field(
        default=None,
        description="URL of the project under test (e.g., https://myapp.example.com)"
    )

    test_framework: Optional[str] = Field(
        default=None,
        description="Target test framework: playwright, cypress, or selenium"
    )

    language: Optional[str] = Field(
        default=None,
        description="Programming language for generated tests: typescript, javascript, or python"
    )

    @field_validator("api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        """Validate and normalize API key."""
        v = v.strip()
        if not v:
            raise ValueError("api_key is required and cannot be empty")
        return v

    @field_validator("api_base_url")
    @classmethod
    def validate_api_base_url(cls, v: str) -> str:
        """Validate and normalize API base URL."""
        v = v.strip().rstrip("/")
        if not v.startswith(("http://", "https://")):
            raise ValueError("api_base_url must start with http:// or https://")
        return v

    @field_validator("project_url")
    @classmethod
    def validate_project_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate project URL if provided."""
        if v is not None:
            v = v.strip().rstrip("/")
            if v and not v.startswith(("http://", "https://")):
                raise ValueError("project_url must start with http:// or https://")
        return v if v else None

    @field_validator("test_framework")
    @classmethod
    def validate_test_framework(cls, v: Optional[str]) -> Optional[str]:
        """Validate test framework if provided."""
        if v is not None:
            v = v.strip().lower()
            supported = {"playwright", "cypress", "selenium"}
            if v and v not in supported:
                raise ValueError(
                    f"test_framework '{v}' is not supported. "
                    f"Supported frameworks: {', '.join(sorted(supported))}"
                )
        return v if v else None

    @field_validator("language")
    @classmethod
    def validate_language(cls, v: Optional[str]) -> Optional[str]:
        """Validate programming language if provided."""
        if v is not None:
            v = v.strip().lower()
            supported = {"typescript", "javascript", "python"}
            if v and v not in supported:
                raise ValueError(
                    f"language '{v}' is not supported. "
                    f"Supported languages: {', '.join(sorted(supported))}"
                )
        return v if v else None

    @model_validator(mode="after")
    def validate_timing_consistency(self) -> "DebuggAIConfig":
        """Validate that timing values are consistent."""
        if self.poll_interval_seconds > self.max_wait_seconds:
            raise ValueError(
                f"poll_interval_seconds ({self.poll_interval_seconds}) cannot be "
                f"greater than max_wait_seconds ({self.max_wait_seconds})"
            )
        return self


class E2EOutputConfig(BaseModel):
    """Configuration for E2E test output."""
    directory: str = Field(
        default="tests/e2e_generated",
        description="Directory for generated E2E tests (relative to project_root)"
    )
    download_artifacts: bool = Field(
        default=True,
        description="Whether to download test artifacts (scripts, recordings)"
    )
    test_framework: Literal["playwright", "cypress", "selenium"] = Field(
        default="playwright",
        description="Target test framework for generated tests"
    )
    programming_language: Literal["typescript", "javascript", "python"] = Field(
        default="typescript",
        description="Programming language for generated tests"
    )


class E2EGitConfig(BaseModel):
    """Configuration for E2E git analysis."""
    base_ref: Optional[str] = Field(
        default=None,
        description="Base git reference for comparison (defaults to main/master)"
    )
    analyze_mode: Literal["working", "commit", "range", "pr"] = Field(
        default="working",
        description="How to analyze git changes"
    )


class E2EConfig(BaseModel):
    """
    Complete E2E test generation configuration.

    This is the top-level config section for E2E in systemeval.yaml:

    Example:
        e2e:
          provider:
            provider: debuggai
            api_key: sk_live_...  # Or pass via CLI: --api-key
            project_slug: my-project
          output:
            directory: tests/e2e
            test_framework: playwright
          git:
            analyze_mode: working

    Architecture Notes:
    - No env var discovery: api_key must be explicit in config or CLI
    - Provider-agnostic: works with debuggai, local dev servers, or mocks
    - Integrates with systemeval's existing environment system
    """
    provider: E2EProviderConfig = Field(
        default_factory=E2EProviderConfig,
        description="Provider configuration"
    )
    output: E2EOutputConfig = Field(
        default_factory=E2EOutputConfig,
        description="Output configuration"
    )
    git: E2EGitConfig = Field(
        default_factory=E2EGitConfig,
        description="Git analysis configuration"
    )
    enabled: bool = Field(
        default=True,
        description="Whether E2E generation is enabled"
    )

    def to_e2e_config(self, project_root: Path) -> "E2ETypesConfig":
        """
        Convert to E2E module config type.

        Args:
            project_root: Project root directory

        Returns:
            E2EConfig from systemeval.e2e.types
        """
        from systemeval.e2e.types import E2EConfig as E2ETypesConfig

        output_dir = project_root / self.output.directory
        return E2ETypesConfig(
            provider_name=self.provider.provider,
            project_root=project_root,
            api_key=self.provider.api_key,
            api_base_url=self.provider.api_base_url,
            project_slug=self.provider.project_slug,
            output_directory=output_dir,
            timeout_seconds=self.provider.timeout_seconds,
            test_framework=self.output.test_framework,
            programming_language=self.output.programming_language,
        )
