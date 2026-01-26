"""Plugin modules for systemeval."""

from .docker import (
    get_container_id,
    get_docker_compose_service,
    get_environment_type,
    is_docker_environment,
)
from .docker_manager import (
    BuildResult,
    CommandResult,
    DockerResourceManager,
    HealthCheckConfig,
)

__all__ = [
    "BuildResult",
    "CommandResult",
    "DockerResourceManager",
    "HealthCheckConfig",
    "get_container_id",
    "get_docker_compose_service",
    "get_environment_type",
    "is_docker_environment",
]
