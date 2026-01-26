"""
Configuration loading functions.

This module handles finding and loading systemeval.yaml configuration files,
with support for both v1.0 (single-project) and v2.0 (multi-project) formats.
"""
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .adapters import PipelineConfig, PlaywrightConfig, PytestConfig, SurferConfig, TestCategory
from .core import SystemEvalConfig
from .e2e import E2EConfig
from .environments import AnyEnvironmentConfig, StandaloneEnvConfig, parse_environment_config
from .multiproject import DefaultsConfig, SubprojectConfig


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

    Supports both v1.0 (single-project) and v2.0 (multi-project) configurations.

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

    # Detect config version
    version = raw_config.get("version", "1.0")

    # Build normalized config from nested YAML structure
    normalized: Dict[str, Any] = {
        "version": version,
        "adapter": raw_config.get("adapter", "pytest"),
        "project_root": config_path.parent,  # Use config file's directory as project root
    }

    # ========================================================================
    # V2.0 Multi-Project Configuration
    # ========================================================================
    if version == "2.0":
        # Parse defaults
        if "defaults" in raw_config:
            defaults_conf = raw_config["defaults"]
            if isinstance(defaults_conf, dict):
                normalized["defaults"] = DefaultsConfig(**defaults_conf)

        # Parse subprojects
        if "subprojects" in raw_config:
            subprojects_raw = raw_config["subprojects"]
            if isinstance(subprojects_raw, list):
                parsed_subprojects: List[SubprojectConfig] = []
                for sp_config in subprojects_raw:
                    if isinstance(sp_config, dict):
                        # Resolve path relative to config file
                        sp_path = sp_config.get("path", ".")
                        if not Path(sp_path).is_absolute():
                            # Store relative path - will be resolved at runtime
                            sp_config["path"] = sp_path

                        parsed_subprojects.append(SubprojectConfig(**sp_config))
                normalized["subprojects"] = parsed_subprojects

    # ========================================================================
    # V1.0 Legacy Configuration (also parsed for v2.0 for backward compat)
    # ========================================================================

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

    # Extract E2E test generation config
    if "e2e" in raw_config:
        e2e_conf = raw_config["e2e"]
        if isinstance(e2e_conf, dict):
            normalized["e2e"] = E2EConfig(**e2e_conf)

    # Convert nested dicts to TestCategory objects
    if "categories" in raw_config:
        categories = {}
        for name, category_data in raw_config["categories"].items():
            if isinstance(category_data, dict):
                categories[name] = TestCategory(**category_data)
            else:
                categories[name] = TestCategory()
        normalized["categories"] = categories

    # Handle legacy 'options' field (v1.0 style)
    if "options" in raw_config and version == "1.0":
        options = raw_config["options"]
        if isinstance(options, dict):
            normalized["adapter_config"] = {**normalized.get("adapter_config", {}), **options}

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


def load_subproject_config(
    root_config: SystemEvalConfig,
    subproject: SubprojectConfig,
) -> Optional[SystemEvalConfig]:
    """
    Load a subproject's own systemeval.yaml if it exists.

    Resolution order:
    1. Subproject's own systemeval.yaml (if exists)
    2. Root config's subprojects[name] settings (returned as-is if no local config)

    Args:
        root_config: The root SystemEvalConfig
        subproject: The SubprojectConfig to resolve

    Returns:
        SystemEvalConfig for the subproject, or None if subproject path doesn't exist
    """
    subproject_path = root_config.project_root / subproject.path
    subproject_config_path = subproject_path / "systemeval.yaml"

    if subproject_config_path.exists():
        # Load subproject's own config
        local_config = load_config(subproject_config_path)
        # Merge with root defaults (subproject config takes precedence)
        # Note: This is a simplified merge - full implementation would be more sophisticated
        return local_config

    # Return None to indicate using the subproject config from root
    return None


def get_subproject_absolute_path(
    root_config: SystemEvalConfig,
    subproject: SubprojectConfig,
) -> Path:
    """
    Get the absolute path to a subproject directory.

    Args:
        root_config: The root SystemEvalConfig
        subproject: The SubprojectConfig

    Returns:
        Absolute Path to the subproject directory
    """
    if Path(subproject.path).is_absolute():
        return Path(subproject.path)
    return root_config.project_root / subproject.path
