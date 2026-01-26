"""
Environment configuration models for systemeval.

This module contains Pydantic models for various environment types:
- HealthCheckConfig: Docker health check configuration
- EnvironmentConfig: Base environment configuration
- StandaloneEnvConfig: Standalone (non-Docker) environments
- DockerComposeEnvConfig: Docker Compose environments
- CompositeEnvConfig: Composite (multi-environment) setups
- NgrokConfig: Ngrok tunnel configuration
- NgrokEnvConfig: Ngrok tunnel environment
- BrowserEnvConfig: Browser testing environment (server + tunnel + tests)
- parse_environment_config: Parser function for environment config dictionaries
"""
from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


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
