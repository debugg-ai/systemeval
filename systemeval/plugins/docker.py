"""
Docker environment detection plugin.
"""
import os
from pathlib import Path
from typing import Optional


def is_docker_environment() -> bool:
    """
    Detect if running inside Docker container.

    Checks multiple indicators:
    - Presence of /.dockerenv file
    - DOCKER_CONTAINER environment variable
    - Container-specific cgroup entries
    """
    # Check for /.dockerenv file (most reliable)
    if Path("/.dockerenv").exists():
        return True

    # Check for DOCKER_CONTAINER env var
    if os.environ.get("DOCKER_CONTAINER"):
        return True

    # Check cgroup for docker/containerd entries
    try:
        with open("/proc/1/cgroup", "r") as f:
            cgroup_content = f.read()
            if "docker" in cgroup_content or "containerd" in cgroup_content:
                return True
    except (FileNotFoundError, PermissionError):
        # /proc/1/cgroup might not exist on non-Linux systems
        pass

    return False


def get_environment_type() -> str:
    """
    Return 'docker' or 'local' based on environment detection.

    Returns:
        str: 'docker' if running in a container, 'local' otherwise
    """
    return "docker" if is_docker_environment() else "local"


def get_docker_compose_service() -> Optional[str]:
    """
    Get the Docker Compose service name if running in Docker Compose.

    Returns:
        Optional[str]: Service name from COMPOSE_SERVICE env var, or None
    """
    return os.environ.get("COMPOSE_SERVICE")


def get_container_id() -> Optional[str]:
    """
    Get the container ID if running in Docker.

    Returns:
        Optional[str]: Container ID from hostname, or None
    """
    if not is_docker_environment():
        return None

    # In Docker, hostname is typically the container ID
    return os.environ.get("HOSTNAME")
