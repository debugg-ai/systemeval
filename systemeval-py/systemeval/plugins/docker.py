"""
Backward compatibility shim for systemeval.plugins.docker.

DEPRECATED: Use systemeval.utils.docker instead.
"""

import warnings

warnings.warn(
    "systemeval.plugins.docker is deprecated. Use systemeval.utils.docker instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from new location
from systemeval.utils.docker.docker import (
    get_container_id,
    get_docker_compose_service,
    get_environment_type,
    is_docker_environment,
)

__all__ = [
    "get_container_id",
    "get_docker_compose_service",
    "get_environment_type",
    "is_docker_environment",
]
