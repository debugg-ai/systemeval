"""
Configuration loading and validation for systemeval.

Architecture Rationale:
----------------------
This module defines 9 Pydantic models to support complex multi-environment test orchestration:

1. TestCategory - Test categorization (unit, integration, api, browser, pipeline)
   - Supports pytest markers, path filters, dependency requirements
   - Used by adapters to filter and validate test execution

2. HealthCheckConfig - Docker health check configuration
   - Required for docker-compose environments to verify service readiness
   - Configurable endpoints, ports, timeouts, retries

3. EnvironmentConfig (base) - Shared environment fields
   - type: Literal union for environment type discrimination
   - test_command, working_dir, default flag
   - Base class for 3 concrete environment types

4-6. Environment Subclasses (StandaloneEnvConfig, DockerComposeEnvConfig, CompositeEnvConfig)
   - Each has distinct lifecycle requirements and configuration
   - StandaloneEnvConfig: Process-based (command, port, env vars, ready pattern)
   - DockerComposeEnvConfig: Docker orchestration (compose file, services, health checks)
   - CompositeEnvConfig: Multi-environment composition (dependency graph)
   - Cannot be merged - each type has unique validation and runtime behavior

7. PytestConfig - Pytest adapter configuration
   - config_file, base_path, default_category
   - Adapter-specific settings isolated from pipeline config

8. PipelineConfig - Pipeline adapter configuration
   - projects, timeout, poll_interval, sync_mode, skip_build
   - Full build→deploy→health→crawl→E2E evaluation settings

9. SystemEvalConfig - Root configuration
   - Aggregates all sub-configs with validation
   - Validates adapter names against registry
   - Validates composite environment dependency graphs
   - Converts YAML to strongly-typed config with defaults

Why Pydantic over TypedDict:
- Runtime validation of YAML input (catches config errors early)
- Discriminated unions for environment types (type-safe polymorphism)
- Field validators for paths, adapter names, dependency graphs
- Default values and optional fields with clear semantics
- Model inheritance for environment types (DRY principle)

This complexity is justified by production usage in sentinal/systemeval.yaml:
- 6 test categories (unit, integration, api, browser, pipeline, external)
- 3 environments (backend, browser, full-stack) with different Docker configs
- 2 adapters (pytest, pipeline) with distinct configuration needs
- Health checks with retries, timeouts, custom endpoints
- Composite environments with dependency resolution
"""
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Union

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator


class TestCategory(BaseModel):
    """Test category configuration."""
    description: Optional[str] = None
    markers: List[str] = Field(default_factory=list)
    test_match: List[str] = Field(default_factory=list)
    paths: List[str] = Field(default_factory=list)
    requires: List[str] = Field(default_factory=list)


class HealthCheckConfig(BaseModel):
    """Health check configuration for Docker environments."""
    service: str = Field(..., description="Service to health check")
    endpoint: str = Field(default="/api/v1/health/", description="Health endpoint path")
    port: int = Field(default=8000, description="Port to check")
    timeout: int = Field(default=120, description="Timeout in seconds")


class EnvironmentConfig(BaseModel):
    """Base environment configuration."""
    type: Literal["standalone", "docker-compose", "composite", "ngrok", "browser"] = "standalone"
    test_command: str = Field(default="", description="Command to run tests")
    working_dir: str = Field(default=".", description="Working directory")
    default: bool = Field(default=False, description="Is this the default environment")


class StandaloneEnvConfig(EnvironmentConfig):
    """Configuration for standalone (non-Docker) environments."""
    type: Literal["standalone"] = "standalone"
    command: str = Field(default="", description="Command to start the service")
    ready_pattern: str = Field(default="", description="Regex pattern indicating ready")
    port: int = Field(default=3000, description="Port the service runs on")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables")


class DockerComposeEnvConfig(EnvironmentConfig):
    """Configuration for Docker Compose environments."""
    type: Literal["docker-compose"] = "docker-compose"
    compose_file: str = Field(default="docker-compose.yml", description="Compose file path")
    services: List[str] = Field(default_factory=list, description="Services to start")
    test_service: str = Field(default="django", description="Service to run tests in")
    health_check: Optional[HealthCheckConfig] = None
    project_name: Optional[str] = None
    skip_build: bool = Field(default=False, description="Skip building images")


class CompositeEnvConfig(EnvironmentConfig):
    """Configuration for composite (multi-environment) setups."""
    type: Literal["composite"] = "composite"
    depends_on: List[str] = Field(default_factory=list, description="Required environments")


class NgrokConfig(BaseModel):
    """Configuration for ngrok tunnel."""
    auth_token: Optional[str] = Field(default=None, description="Ngrok auth token (or use NGROK_AUTHTOKEN env var)")
    port: int = Field(default=3000, description="Local port to expose")
    region: str = Field(default="us", description="Ngrok region (us, eu, ap, au, sa, jp, in)")


class NgrokEnvConfig(EnvironmentConfig):
    """Configuration for ngrok tunnel environment."""
    type: Literal["ngrok"] = "ngrok"
    port: int = Field(default=3000, description="Local port to tunnel")
    auth_token: Optional[str] = Field(default=None, description="Ngrok auth token")
    region: str = Field(default="us", description="Ngrok region")


class PlaywrightConfig(BaseModel):
    """Playwright adapter configuration."""
    config_file: str = Field(default="playwright.config.ts", description="Playwright config file")
    project: Optional[str] = Field(default=None, description="Playwright project (chromium, firefox, webkit)")
    headed: bool = Field(default=False, description="Run in headed mode")
    timeout: int = Field(default=30000, description="Test timeout in milliseconds")


class SurferConfig(BaseModel):
    """DebuggAI Surfer adapter configuration."""
    project_slug: str = Field(..., description="DebuggAI project slug")
    api_key: Optional[str] = Field(default=None, description="DebuggAI API key (or use DEBUGGAI_API_KEY env var)")
    api_base_url: str = Field(default="https://api.debugg.ai", description="DebuggAI API base URL")
    poll_interval: int = Field(default=5, description="Seconds between status checks")
    timeout: int = Field(default=600, description="Max time to wait for test completion")


class BrowserEnvConfig(EnvironmentConfig):
    """Configuration for browser testing environment (server + tunnel + tests)."""
    type: Literal["browser"] = "browser"
    server: Optional[Dict[str, Any]] = Field(default=None, description="Server configuration (StandaloneEnvConfig)")
    tunnel: Optional[NgrokConfig] = Field(default=None, description="Ngrok tunnel configuration")
    test_runner: Literal["playwright", "surfer"] = Field(default="playwright", description="Browser test runner to use")


# Union type for all environment configurations
# Used for discriminated union parsing based on 'type' field
AnyEnvironmentConfig = Union[
    StandaloneEnvConfig,
    DockerComposeEnvConfig,
    CompositeEnvConfig,
    NgrokEnvConfig,
    BrowserEnvConfig,
]


def parse_environment_config(name: str, config_dict: Dict[str, Any]) -> AnyEnvironmentConfig:
    """
    Parse a raw environment config dict into the appropriate typed model.

    Uses discriminated union based on the 'type' field.

    Args:
        name: Environment name (for error messages)
        config_dict: Raw config dictionary from YAML

    Returns:
        Typed environment config model

    Raises:
        ValueError: If environment type is unknown
    """
    env_type = config_dict.get("type", "standalone")

    if env_type == "standalone":
        return StandaloneEnvConfig(**config_dict)
    elif env_type == "docker-compose":
        return DockerComposeEnvConfig(**config_dict)
    elif env_type == "composite":
        return CompositeEnvConfig(**config_dict)
    elif env_type == "ngrok":
        return NgrokEnvConfig(**config_dict)
    elif env_type == "browser":
        return BrowserEnvConfig(**config_dict)
    else:
        raise ValueError(f"Unknown environment type '{env_type}' for environment '{name}'")


class PytestConfig(BaseModel):
    """Pytest adapter specific configuration."""
    config_file: Optional[str] = None
    base_path: str = "."
    default_category: str = "unit"


class PipelineConfig(BaseModel):
    """Pipeline adapter specific configuration."""
    projects: List[str] = Field(default_factory=lambda: ["crochet-patterns"])
    timeout: int = Field(default=600, description="Max time to wait per project (seconds)")
    poll_interval: int = Field(default=15, description="Seconds between status checks")
    sync_mode: bool = Field(default=False, description="Run webhooks synchronously")
    skip_build: bool = Field(default=False, description="Skip build, use existing containers")


class SystemEvalConfig(BaseModel):
    """Main configuration model."""
    adapter: str = Field(default="pytest", description="Test adapter to use (pytest, jest, pipeline, playwright, surfer)")
    project_root: Path = Field(default=Path("."), description="Project root directory")
    test_directory: Path = Field(default=Path("tests"), description="Test directory path")
    categories: Dict[str, TestCategory] = Field(default_factory=dict)
    adapter_config: Dict[str, Any] = Field(default_factory=dict, description="Adapter-specific config")
    pytest_config: Optional[PytestConfig] = None
    pipeline_config: Optional[PipelineConfig] = None
    playwright_config: Optional[PlaywrightConfig] = None
    surfer_config: Optional[SurferConfig] = None
    project_name: Optional[str] = None
    environments: Dict[str, AnyEnvironmentConfig] = Field(
        default_factory=dict,
        description="Environment configurations for multi-env testing"
    )

    @field_validator("adapter")
    @classmethod
    def validate_adapter(cls, v: str) -> str:
        """Validate adapter name."""
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
        result: Dict[str, AnyEnvironmentConfig] = {}
        for name, config in v.items():
            if isinstance(config, dict):
                result[name] = parse_environment_config(name, config)
            else:
                result[name] = config
        return result

    @model_validator(mode="after")
    def validate_composite_deps(self) -> "SystemEvalConfig":
        """Validate that composite environment dependencies exist."""
        for name, env_config in self.environments.items():
            if env_config.type == "composite":
                # CompositeEnvConfig has depends_on attribute
                if isinstance(env_config, CompositeEnvConfig):
                    deps = env_config.depends_on
                    for dep in deps:
                        if dep not in self.environments:
                            raise ValueError(
                                f"Environment '{name}' depends on '{dep}' which is not defined"
                            )
        return self


def find_config_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find systemeval.yaml in current or parent directories.

    Args:
        start_path: Starting directory (defaults to current working directory)

    Returns:
        Path to config file, or None if not found
    """
    current = start_path or Path.cwd()

    # Search up to 5 levels
    for _ in range(5):
        config_path = current / "systemeval.yaml"
        if config_path.exists():
            return config_path

        # Move to parent
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    return None


def load_config(config_path: Path) -> SystemEvalConfig:
    """
    Load and validate configuration from YAML file.

    Args:
        config_path: Path to systemeval.yaml

    Returns:
        Validated SystemEvalConfig instance

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
    """
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path, "r") as f:
        raw_config = yaml.safe_load(f)

    if not raw_config:
        raise ValueError(f"Empty or invalid config file: {config_path}")

    # Build normalized config from nested YAML structure
    normalized: Dict[str, Any] = {
        "adapter": raw_config.get("adapter", "pytest"),
        "project_root": config_path.parent,  # Use config file's directory as project root
    }

    # Extract project info
    if "project" in raw_config:
        project = raw_config["project"]
        if isinstance(project, dict):
            normalized["project_name"] = project.get("name")

    # Extract pytest-specific config
    if "pytest" in raw_config:
        pytest_conf = raw_config["pytest"]
        if isinstance(pytest_conf, dict):
            normalized["pytest_config"] = PytestConfig(**pytest_conf)
            # Set test_directory from base_path
            if "base_path" in pytest_conf:
                normalized["test_directory"] = pytest_conf["base_path"]

    # Extract pipeline-specific config
    if "pipeline" in raw_config:
        pipeline_conf = raw_config["pipeline"]
        if isinstance(pipeline_conf, dict):
            normalized["pipeline_config"] = PipelineConfig(**pipeline_conf)
            # Also store in adapter_config for adapter access
            normalized["adapter_config"] = {**normalized.get("adapter_config", {}), **pipeline_conf}

    # Extract playwright-specific config
    if "playwright" in raw_config:
        playwright_conf = raw_config["playwright"]
        if isinstance(playwright_conf, dict):
            normalized["playwright_config"] = PlaywrightConfig(**playwright_conf)
            normalized["adapter_config"] = {**normalized.get("adapter_config", {}), **playwright_conf}

    # Extract surfer-specific config
    if "surfer" in raw_config:
        surfer_conf = raw_config["surfer"]
        if isinstance(surfer_conf, dict):
            normalized["surfer_config"] = SurferConfig(**surfer_conf)
            normalized["adapter_config"] = {**normalized.get("adapter_config", {}), **surfer_conf}

    # Convert nested dicts to TestCategory objects
    if "categories" in raw_config:
        categories = {}
        for name, category_data in raw_config["categories"].items():
            if isinstance(category_data, dict):
                categories[name] = TestCategory(**category_data)
            else:
                categories[name] = TestCategory()
        normalized["categories"] = categories

    # Extract environments configuration and parse into typed models
    if "environments" in raw_config:
        environments_raw = raw_config["environments"]
        if isinstance(environments_raw, dict):
            parsed_environments: Dict[str, AnyEnvironmentConfig] = {}
            for name, env_config in environments_raw.items():
                if isinstance(env_config, dict):
                    # Inject working_dir relative to config file if not absolute
                    working_dir = env_config.get("working_dir", ".")
                    if not Path(working_dir).is_absolute():
                        env_config["working_dir"] = str(config_path.parent / working_dir)
                    # Parse into typed model
                    parsed_environments[name] = parse_environment_config(name, env_config)
                else:
                    # Default to standalone if env_config is None or empty
                    parsed_environments[name] = StandaloneEnvConfig(
                        working_dir=str(config_path.parent)
                    )
            normalized["environments"] = parsed_environments

    return SystemEvalConfig(**normalized)
