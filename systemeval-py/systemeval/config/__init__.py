"""
Configuration package for systemeval.

This package provides configuration models and utilities for systemeval,
supporting both v1.0 (single-project) and v2.0 (multi-project) configurations.

Module Organization:
- adapters: Test adapter configuration (TestCategory, PytestConfig, etc.)
- environments: Environment configuration (Docker, standalone, composite, etc.)
- e2e: E2E test generation configuration
- multiproject: Multi-project orchestration configuration (v2.0)
- core: SystemEvalConfig main configuration class
- loaders: Configuration loading functions

All configuration classes are re-exported from this package for backward compatibility.
"""

# Re-export core configuration class
from systemeval.config.core import SystemEvalConfig

# Re-export configuration loading functions
from systemeval.config.loaders import (
    find_config_file,
    load_config,
    load_subproject_config,
    get_subproject_absolute_path,
)

# Re-export adapter configs
from systemeval.config.adapters import (
    TestCategory,
    PytestConfig,
    PipelineConfig,
    PlaywrightConfig,
    SurferConfig,
)

# Re-export environment configs
from systemeval.config.environments import (
    HealthCheckConfig,
    EnvironmentConfig,
    StandaloneEnvConfig,
    DockerComposeEnvConfig,
    CompositeEnvConfig,
    NgrokConfig,
    NgrokEnvConfig,
    BrowserEnvConfig,
    AnyEnvironmentConfig,
    parse_environment_config,
)

# Re-export E2E configs
from systemeval.config.e2e import (
    E2EProviderConfig,
    DebuggAIConfig,
    E2EOutputConfig,
    E2EGitConfig,
    E2EConfig,
)

# Re-export multi-project configs
from systemeval.config.multiproject import (
    DefaultsConfig,
    SubprojectConfig,
    SubprojectResult,
    MultiProjectResult,
)

__all__ = [
    # Core configuration
    "SystemEvalConfig",
    # Configuration loading
    "find_config_file",
    "load_config",
    "load_subproject_config",
    "get_subproject_absolute_path",
    # Adapter configs
    "TestCategory",
    "PytestConfig",
    "PipelineConfig",
    "PlaywrightConfig",
    "SurferConfig",
    # Environment configs
    "HealthCheckConfig",
    "EnvironmentConfig",
    "StandaloneEnvConfig",
    "DockerComposeEnvConfig",
    "CompositeEnvConfig",
    "NgrokConfig",
    "NgrokEnvConfig",
    "BrowserEnvConfig",
    "AnyEnvironmentConfig",
    "parse_environment_config",
    # E2E configs
    "E2EProviderConfig",
    "DebuggAIConfig",
    "E2EOutputConfig",
    "E2EGitConfig",
    "E2EConfig",
    # Multi-project configs
    "DefaultsConfig",
    "SubprojectConfig",
    "SubprojectResult",
    "MultiProjectResult",
]
