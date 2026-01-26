"""
Backward compatibility shim for systemeval.plugins.

DEPRECATED: This module is deprecated. Use systemeval.utils.docker instead.

The plugins directory has been renamed to utils/docker because the Docker
utilities are not a plugin system - they are core utilities for Docker
environment detection and container management.

Migration:
    # Old (deprecated)
    from systemeval.plugins.docker import is_docker_environment
    from systemeval.plugins.docker_manager import DockerResourceManager

    # New (recommended)
    from systemeval.utils.docker import is_docker_environment
    from systemeval.utils.docker import DockerResourceManager
"""

import warnings

# Re-export from new location for backward compatibility
from systemeval.utils.docker import (
    get_container_id,
    get_docker_compose_service,
    get_environment_type,
    is_docker_environment,
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


def __getattr__(name: str):
    """Emit deprecation warning when accessing this module."""
    if name in __all__:
        warnings.warn(
            f"systemeval.plugins is deprecated. Use systemeval.utils.docker instead.",
            DeprecationWarning,
            stacklevel=2,
        )
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
