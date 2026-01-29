"""
Auto-discovery for Docker test environments.

Finds compose files, infers test services, detects test commands,
and resolves health check configuration with minimal user input.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

from systemeval.utils.docker.compose_parser import ComposeFileInfo, parse_compose_file
from systemeval.utils.logging import get_logger

logger = get_logger(__name__)

# Compose file names to search, in priority order
COMPOSE_FILE_CANDIDATES = [
    "docker-compose.yml",
    "docker-compose.yaml",
    "compose.yml",
    "compose.yaml",
    "local.yml",
    "local.yaml",
    "docker-compose.local.yml",
    "docker-compose.local.yaml",
    "docker-compose.dev.yml",
    "docker-compose.dev.yaml",
]

# Common health check endpoints to probe, in order
COMMON_HEALTH_ENDPOINTS = [
    "/health/",
    "/healthz/",
    "/healthz",
    "/api/health/",
    "/api/v1/health/",
    "/api/healthcheck/",
    "/ready/",
    "/readyz",
    "/_health",
    "/status",
]

# Test command detection based on files present in project
_TEST_COMMAND_INDICATORS = [
    ("pytest.ini", "pytest"),
    ("setup.cfg", "pytest"),       # often has [tool:pytest]
    ("pyproject.toml", "pytest"),  # often has [tool.pytest]
    ("manage.py", "pytest"),       # Django projects
    ("package.json", "npm test"),
    ("Makefile", None),            # check inside for test target
]


def find_compose_file(project_dir: Path) -> Optional[Path]:
    """Find a docker-compose file in the project directory.

    Searches for common compose file names in priority order.

    Args:
        project_dir: Directory to search in

    Returns:
        Path to the compose file, or None if not found
    """
    for candidate in COMPOSE_FILE_CANDIDATES:
        path = project_dir / candidate
        if path.exists():
            logger.debug(f"Found compose file: {path}")
            return path

    return None


def discover_compose_file(project_dir: Path) -> Optional[ComposeFileInfo]:
    """Find and parse a docker-compose file.

    Args:
        project_dir: Directory to search in

    Returns:
        Parsed ComposeFileInfo, or None if no compose file found
    """
    path = find_compose_file(project_dir)
    if path is None:
        return None

    try:
        return parse_compose_file(path)
    except Exception as e:
        logger.warning(f"Failed to parse compose file {path}: {e}")
        return None


def infer_test_command(project_dir: Path) -> str:
    """Infer the test command based on project files.

    Args:
        project_dir: Project root directory

    Returns:
        Inferred test command string (defaults to 'pytest')
    """
    for filename, command in _TEST_COMMAND_INDICATORS:
        if (project_dir / filename).exists():
            if command:
                return command

    return "pytest"


def resolve_docker_config(
    user_config: Dict[str, Any],
    project_dir: Path,
) -> Dict[str, Any]:
    """Resolve a Docker environment config by filling in missing values.

    Takes the user's (possibly minimal) config and fills in everything
    that can be auto-detected from the compose file and project structure.

    Args:
        user_config: User-provided config dict (may have only 'type: docker-compose')
        project_dir: Project root directory for file discovery

    Returns:
        Fully resolved config dict with all fields populated
    """
    config = dict(user_config)

    # --- Compose file discovery ---
    compose_file = config.get("compose_file")
    compose_info: Optional[ComposeFileInfo] = None

    if compose_file:
        compose_path = project_dir / compose_file
        if compose_path.exists():
            try:
                compose_info = parse_compose_file(compose_path)
            except Exception as e:
                logger.warning(f"Failed to parse {compose_path}: {e}")
    else:
        compose_info = discover_compose_file(project_dir)
        if compose_info:
            config["compose_file"] = str(compose_info.path.relative_to(project_dir))

    if not compose_info:
        logger.debug("No compose file found or parsed; using user config as-is")
        return config

    # --- Service discovery ---
    if not config.get("services"):
        config["services"] = compose_info.service_names
        logger.debug(f"Auto-detected services: {config['services']}")

    # --- Test service discovery ---
    if not config.get("test_service"):
        inferred = compose_info.get_test_service()
        if inferred:
            config["test_service"] = inferred
            logger.debug(f"Auto-detected test service: {inferred}")

    test_service_name = config.get("test_service", "")

    # --- Working dir discovery ---
    if not config.get("working_dir") or config.get("working_dir") == ".":
        svc = compose_info.services.get(test_service_name)
        if svc and svc.working_dir:
            config["working_dir"] = svc.working_dir
            logger.debug(f"Auto-detected working_dir: {svc.working_dir}")

    # --- Test command discovery ---
    if not config.get("test_command"):
        config["test_command"] = infer_test_command(project_dir)
        logger.debug(f"Auto-detected test_command: {config['test_command']}")

    # --- Health check discovery ---
    if not config.get("health_check") and test_service_name:
        health_config: Dict[str, Any] = {"service": test_service_name}

        # Port from compose file
        port = compose_info.get_health_port(test_service_name)
        if port:
            health_config["port"] = port

        # Endpoint from compose healthcheck or env
        endpoint = compose_info.get_health_endpoint(test_service_name)
        if endpoint:
            health_config["endpoint"] = endpoint

        config["health_check"] = health_config
        logger.debug(f"Auto-detected health_check: {health_config}")

    # --- Environment variables ---
    if not config.get("env") and test_service_name:
        svc = compose_info.services.get(test_service_name)
        if svc and svc.environment:
            # Only include test-relevant env vars, not secrets
            test_env = {}
            for key, value in svc.environment.items():
                # Include settings modules, database URLs, and common test config
                if any(k in key.upper() for k in [
                    "SETTINGS", "DATABASE_URL", "REDIS_URL",
                    "CELERY", "TEST", "DEBUG",
                ]):
                    test_env[key] = value
            if test_env:
                config["env"] = test_env

    return config


def validate_docker_config(
    config: Dict[str, Any],
    project_dir: Path,
) -> List[str]:
    """Validate a Docker environment config and return warnings/errors.

    Args:
        config: Resolved config dict
        project_dir: Project root directory

    Returns:
        List of validation error/warning strings (empty = valid)
    """
    errors: List[str] = []

    # Check compose file exists
    compose_file = config.get("compose_file")
    if compose_file:
        compose_path = project_dir / compose_file
        if not compose_path.exists():
            errors.append(
                f"Compose file not found: {compose_path}\n"
                f"  Searched in: {project_dir}\n"
                f"  Available files: {', '.join(f.name for f in project_dir.iterdir() if f.is_file() and f.suffix in ('.yml', '.yaml'))}"
            )
    else:
        errors.append(
            f"No compose file specified or found in {project_dir}\n"
            f"  Searched for: {', '.join(COMPOSE_FILE_CANDIDATES[:4])}"
        )

    # Check services are valid
    services = config.get("services", [])
    test_service = config.get("test_service", "")
    if test_service and services and test_service not in services:
        errors.append(
            f"test_service '{test_service}' not in services list: {services}\n"
            f"  The test_service must be one of the services that will be started"
        )

    # Validate against compose file
    if compose_file:
        compose_path = project_dir / compose_file
        if compose_path.exists():
            try:
                compose_info = parse_compose_file(compose_path)
                available = compose_info.service_names

                for svc in services:
                    if svc not in available:
                        errors.append(
                            f"Service '{svc}' not found in {compose_file}\n"
                            f"  Available services: {', '.join(available)}"
                        )

                if test_service and test_service not in available:
                    errors.append(
                        f"test_service '{test_service}' not found in {compose_file}\n"
                        f"  Available services: {', '.join(available)}"
                    )
            except Exception:
                pass  # compose file parse errors handled above

    return errors
