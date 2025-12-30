"""
Configuration dataclasses for systemeval.yaml

Defines the structure for loading and validating test configuration files.
Framework-agnostic configuration that can be adapted to pytest, jest, etc.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class CategoryConfig:
    """Configuration for a test category (e.g., unit, integration, e2e)."""

    markers: List[str] = field(default_factory=list)  # pytest markers
    pattern: Optional[str] = None  # jest pattern or glob
    description: str = ""
    requires: List[str] = field(default_factory=list)  # Dependencies (docker, database, etc.)
    timeout: Optional[int] = None  # Timeout in seconds
    coverage_threshold: Optional[float] = None  # Minimum coverage percentage
    pass_threshold: Optional[float] = None  # Minimum pass rate percentage

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CategoryConfig":
        """Create CategoryConfig from dictionary."""
        return cls(
            markers=data.get("markers", []),
            pattern=data.get("pattern"),
            description=data.get("description", ""),
            requires=data.get("requires", []),
            timeout=data.get("timeout"),
            coverage_threshold=data.get("coverage_threshold"),
            pass_threshold=data.get("pass_threshold"),
        )


@dataclass
class PytestConfig:
    """Pytest-specific configuration."""

    config_file: str = "pytest.ini"
    base_path: str = "."
    default_category: str = "unit"
    addopts: List[str] = field(default_factory=list)  # Additional pytest options

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PytestConfig":
        """Create PytestConfig from dictionary."""
        return cls(
            config_file=data.get("config_file", "pytest.ini"),
            base_path=data.get("base_path", "."),
            default_category=data.get("default_category", "unit"),
            addopts=data.get("addopts", []),
        )


@dataclass
class JestConfig:
    """Jest-specific configuration."""

    config_file: str = "jest.config.js"
    base_path: str = "."
    default_category: str = "unit"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "JestConfig":
        """Create JestConfig from dictionary."""
        return cls(
            config_file=data.get("config_file", "jest.config.js"),
            base_path=data.get("base_path", "."),
            default_category=data.get("default_category", "unit"),
        )


@dataclass
class EnvironmentConfig:
    """Environment-specific configuration (local, docker, ci)."""

    docker_detection: List[Dict[str, str]] = field(default_factory=list)
    database: str = "sqlite"
    redis: bool = False
    browser: bool = False  # For E2E tests requiring browser

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentConfig":
        """Create EnvironmentConfig from dictionary."""
        return cls(
            docker_detection=data.get("docker_detection", []),
            database=data.get("database", "sqlite"),
            redis=data.get("redis", False),
            browser=data.get("browser", False),
        )


@dataclass
class ReportingConfig:
    """Output and reporting configuration."""

    format: str = "table"  # table, json, junit, html
    verbose: bool = False
    colors: bool = True
    output_file: Optional[str] = None
    show_passed: bool = False  # Only show failures by default
    show_metrics: bool = True

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ReportingConfig":
        """Create ReportingConfig from dictionary."""
        return cls(
            format=data.get("format", "table"),
            verbose=data.get("verbose", False),
            colors=data.get("colors", True),
            output_file=data.get("output_file"),
            show_passed=data.get("show_passed", False),
            show_metrics=data.get("show_metrics", True),
        )


@dataclass
class SystemEvalConfig:
    """Root configuration for systemeval."""

    project_name: str = ""
    project_type: str = ""  # django, fastapi, nextjs, react, etc.
    adapter: str = "pytest"  # pytest, jest, playwright, etc.
    categories: Dict[str, CategoryConfig] = field(default_factory=dict)
    pytest: PytestConfig = field(default_factory=PytestConfig)
    jest: JestConfig = field(default_factory=JestConfig)
    environment: Dict[str, EnvironmentConfig] = field(default_factory=dict)
    reporting: ReportingConfig = field(default_factory=ReportingConfig)

    @classmethod
    def load(cls, path: Path) -> "SystemEvalConfig":
        """
        Load configuration from YAML file.

        Args:
            path: Path to systemeval.yaml

        Returns:
            Loaded SystemEvalConfig instance

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML is invalid
        """
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with open(path, "r") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Empty config file: {path}")

        # Parse categories
        categories = {}
        for name, cat_data in data.get("categories", {}).items():
            categories[name] = CategoryConfig.from_dict(cat_data)

        # Parse environments
        environments = {}
        for name, env_data in data.get("environment", {}).items():
            environments[name] = EnvironmentConfig.from_dict(env_data)

        return cls(
            project_name=data.get("project_name", ""),
            project_type=data.get("project_type", ""),
            adapter=data.get("adapter", "pytest"),
            categories=categories,
            pytest=PytestConfig.from_dict(data.get("pytest", {})),
            jest=JestConfig.from_dict(data.get("jest", {})),
            environment=environments,
            reporting=ReportingConfig.from_dict(data.get("reporting", {})),
        )

    @classmethod
    def find_config(cls, start_path: Optional[Path] = None) -> Optional[Path]:
        """
        Find systemeval.yaml in current directory or parents.

        Args:
            start_path: Directory to start searching from (defaults to cwd)

        Returns:
            Path to config file if found, None otherwise
        """
        search_path = start_path or Path.cwd()

        # Search up to root
        for parent in [search_path] + list(search_path.parents):
            config_path = parent / "systemeval.yaml"
            if config_path.exists():
                return config_path

        return None

    def get_category(self, name: str) -> Optional[CategoryConfig]:
        """Get category configuration by name."""
        return self.categories.get(name)

    def get_environment(self, name: str) -> Optional[EnvironmentConfig]:
        """Get environment configuration by name."""
        return self.environment.get(name)

    def validate(self) -> List[str]:
        """
        Validate configuration and return list of errors.

        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []

        if not self.project_name:
            errors.append("project_name is required")

        if self.adapter not in ["pytest", "jest", "playwright"]:
            errors.append(f"Unsupported adapter: {self.adapter}")

        if not self.categories:
            errors.append("At least one category is required")

        # Validate category dependencies
        for cat_name, category in self.categories.items():
            for req in category.requires:
                if req.startswith("env:"):
                    env_name = req[4:]
                    if env_name not in self.environment:
                        errors.append(
                            f"Category '{cat_name}' requires environment '{env_name}' which is not defined"
                        )

        return errors


# Backwards compatibility aliases
def find_config_file(start_path: Optional[Path] = None) -> Optional[Path]:
    """
    Find systemeval.yaml in current or parent directories.

    Alias for SystemEvalConfig.find_config() for backwards compatibility.
    """
    return SystemEvalConfig.find_config(start_path)


def load_config(config_path: Path) -> SystemEvalConfig:
    """
    Load and validate configuration from YAML file.

    Alias for SystemEvalConfig.load() for backwards compatibility.
    """
    return SystemEvalConfig.load(config_path)
