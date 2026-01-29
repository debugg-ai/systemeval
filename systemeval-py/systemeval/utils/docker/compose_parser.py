"""
Parse docker-compose.yml files to extract service definitions.

Reads compose files and extracts service names, port mappings,
health check endpoints, working directories, environment variables,
and volume mounts for auto-discovery.
"""
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from systemeval.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ServiceInfo:
    """Extracted information about a Docker Compose service."""
    name: str
    ports: List[Tuple[int, int]] = field(default_factory=list)  # (host, container)
    volumes: List[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    environment: Dict[str, str] = field(default_factory=dict)
    healthcheck: Optional[Dict[str, Any]] = None
    depends_on: List[str] = field(default_factory=list)
    has_source_mount: bool = False
    image: Optional[str] = None
    build_context: Optional[str] = None


@dataclass
class ComposeFileInfo:
    """Parsed information from a docker-compose.yml file."""
    path: Path
    services: Dict[str, ServiceInfo] = field(default_factory=dict)
    volumes: List[str] = field(default_factory=list)
    networks: List[str] = field(default_factory=list)

    @property
    def service_names(self) -> List[str]:
        return list(self.services.keys())

    def get_test_service(self) -> Optional[str]:
        """Infer which service is the test runner.

        Heuristics (in order):
        1. Service with a source code volume mount (./src:/app, ./backend:/app, etc.)
        2. Service with a working_dir set
        3. Service named 'django', 'web', 'app', 'api', 'backend'
        4. First service that has a build context (not just an image)
        """
        # 1. Source code mount
        for name, svc in self.services.items():
            if svc.has_source_mount:
                return name

        # 2. Has working_dir
        for name, svc in self.services.items():
            if svc.working_dir:
                return name

        # 3. Common names
        common_names = ["django", "web", "app", "api", "backend", "server"]
        for candidate in common_names:
            if candidate in self.services:
                return candidate

        # 4. First service with build context
        for name, svc in self.services.items():
            if svc.build_context:
                return name

        return None

    def get_health_port(self, service_name: str) -> Optional[int]:
        """Get the host-mapped port for a service."""
        svc = self.services.get(service_name)
        if not svc or not svc.ports:
            return None
        # Return the first host port
        return svc.ports[0][0]

    def get_health_endpoint(self, service_name: str) -> Optional[str]:
        """Try to infer health check endpoint from service config."""
        svc = self.services.get(service_name)
        if not svc:
            return None

        # Check Docker healthcheck command for URL patterns
        if svc.healthcheck:
            test_cmd = svc.healthcheck.get("test", [])
            if isinstance(test_cmd, list):
                test_cmd = " ".join(test_cmd)
            if isinstance(test_cmd, str):
                # Extract URL path from curl/wget commands
                url_match = re.search(r'https?://[^/\s]+(\/[^\s"\']*)', test_cmd)
                if url_match:
                    return url_match.group(1)

        # Check environment variables for health endpoint hints
        env = svc.environment
        for key in ["HEALTH_CHECK_PATH", "HEALTHCHECK_PATH", "HEALTH_ENDPOINT"]:
            if key in env:
                return env[key]

        return None


# Patterns that indicate a source code volume mount
_SOURCE_MOUNT_PATTERNS = [
    re.compile(r"^\./[^:]*:/app"),
    re.compile(r"^\./[^:]*:/workspace"),
    re.compile(r"^\./[^:]*:/code"),
    re.compile(r"^\./[^:]*:/src"),
    re.compile(r"^\.\s*:/app"),
    re.compile(r"^\.\s*:/workspace"),
]


def _is_source_mount(volume: str) -> bool:
    """Check if a volume string represents a source code mount."""
    return any(p.match(volume) for p in _SOURCE_MOUNT_PATTERNS)


def _parse_port(port_def: Any) -> Optional[Tuple[int, int]]:
    """Parse a port definition into (host_port, container_port)."""
    if isinstance(port_def, int):
        return (port_def, port_def)
    if isinstance(port_def, str):
        # Handle "8002:8002", "0.0.0.0:8002:8002", "8002"
        parts = port_def.split(":")
        try:
            if len(parts) == 1:
                p = int(parts[0].split("/")[0])
                return (p, p)
            elif len(parts) == 2:
                host = int(parts[0].split("/")[0])
                container = int(parts[1].split("/")[0])
                return (host, container)
            elif len(parts) == 3:
                host = int(parts[1].split("/")[0])
                container = int(parts[2].split("/")[0])
                return (host, container)
        except (ValueError, IndexError):
            pass
    if isinstance(port_def, dict):
        # Long syntax: {target: 8002, published: 8002}
        target = port_def.get("target")
        published = port_def.get("published", target)
        if target:
            return (int(published), int(target))
    return None


def _parse_environment(env_def: Any) -> Dict[str, str]:
    """Parse environment definition (list or dict format)."""
    if isinstance(env_def, dict):
        return {k: str(v) if v is not None else "" for k, v in env_def.items()}
    if isinstance(env_def, list):
        result = {}
        for item in env_def:
            if "=" in str(item):
                key, _, value = str(item).partition("=")
                result[key] = value
            else:
                result[str(item)] = ""
        return result
    return {}


def _parse_depends_on(depends: Any) -> List[str]:
    """Parse depends_on (list or dict with conditions)."""
    if isinstance(depends, list):
        return depends
    if isinstance(depends, dict):
        return list(depends.keys())
    return []


def parse_compose_file(path: Path) -> ComposeFileInfo:
    """Parse a docker-compose.yml file and extract service information.

    Args:
        path: Path to the docker-compose.yml file

    Returns:
        ComposeFileInfo with extracted service definitions

    Raises:
        FileNotFoundError: If the compose file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
    """
    if not path.exists():
        raise FileNotFoundError(f"Compose file not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if not data or not isinstance(data, dict):
        return ComposeFileInfo(path=path)

    info = ComposeFileInfo(
        path=path,
        volumes=list((data.get("volumes") or {}).keys()),
        networks=list((data.get("networks") or {}).keys()),
    )

    services = data.get("services", {})
    if not isinstance(services, dict):
        return info

    for name, svc_data in services.items():
        if not isinstance(svc_data, dict):
            continue

        # Parse volumes
        raw_volumes = svc_data.get("volumes", [])
        volumes = []
        has_source_mount = False
        for v in raw_volumes:
            vol_str = str(v) if not isinstance(v, dict) else v.get("source", "")
            volumes.append(vol_str)
            if _is_source_mount(vol_str):
                has_source_mount = True

        # Parse ports
        ports = []
        for p in svc_data.get("ports", []):
            parsed = _parse_port(p)
            if parsed:
                ports.append(parsed)

        # Parse build context
        build = svc_data.get("build")
        build_context = None
        if isinstance(build, str):
            build_context = build
        elif isinstance(build, dict):
            build_context = build.get("context", ".")

        svc = ServiceInfo(
            name=name,
            ports=ports,
            volumes=volumes,
            working_dir=svc_data.get("working_dir"),
            environment=_parse_environment(svc_data.get("environment", {})),
            healthcheck=svc_data.get("healthcheck"),
            depends_on=_parse_depends_on(svc_data.get("depends_on", [])),
            has_source_mount=has_source_mount,
            image=svc_data.get("image"),
            build_context=build_context,
        )
        info.services[name] = svc

    return info
