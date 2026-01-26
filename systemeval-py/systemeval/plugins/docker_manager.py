"""
Backward compatibility shim for systemeval.plugins.docker_manager.

DEPRECATED: Use systemeval.utils.docker instead.
"""

import warnings

warnings.warn(
    "systemeval.plugins.docker_manager is deprecated. Use systemeval.utils.docker instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export everything from new location
from systemeval.utils.docker.docker_manager import (
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
]
