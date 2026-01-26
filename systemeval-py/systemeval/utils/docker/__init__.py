"""Docker utility modules for systemeval.

This module provides Docker-related utilities including:
- Environment detection (is_docker_environment, get_environment_type)
- Container management (get_container_id, get_docker_compose_service)
- Resource management (DockerResourceManager)

Note: This was previously located in systemeval.plugins.docker but moved here
because it's not a plugin system - these are core Docker utilities.
"""

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
    # Environment detection
    "get_environment_type",
    "is_docker_environment",
    "get_container_id",
    "get_docker_compose_service",
    # Resource management
    "BuildResult",
    "CommandResult",
    "DockerResourceManager",
    "HealthCheckConfig",
]
