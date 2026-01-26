"""
Configuration module - backward compatibility shim.

This module provides backward compatibility for code importing from systemeval.config.
All configuration functionality has been moved to the systemeval.config package.

Architecture Change:
-------------------
The monolithic config.py (400+ lines) has been split into focused modules:

- config/adapters.py      - Test adapter configuration models
- config/environments.py  - Environment configuration models
- config/e2e.py           - E2E test generation configuration
- config/multiproject.py  - Multi-project orchestration models
- config/core.py          - SystemEvalConfig main configuration class
- config/loaders.py       - Configuration loading and file discovery

This split improves:
- Maintainability: Each module has a single responsibility
- Testability: Easier to test individual components
- Readability: Related functionality grouped together
- Navigation: Faster to find specific configuration models

Migration Guide:
---------------
Old import (still works, but deprecated):
    from systemeval.config import SystemEvalConfig, load_config

New import (recommended):
    from systemeval.config import SystemEvalConfig, load_config

The import path is the same! The config package __init__.py re-exports everything.

Direct module imports (if needed for specificity):
    from systemeval.config.core import SystemEvalConfig
    from systemeval.config.loaders import load_config
    from systemeval.config.adapters import TestCategory, PytestConfig
    from systemeval.config.environments import DockerComposeEnvConfig
    from systemeval.config.e2e import E2EConfig, DebuggAIConfig
    from systemeval.config.multiproject import SubprojectConfig
"""

import warnings

# Re-export everything from the config package
from systemeval.config.core import SystemEvalConfig
from systemeval.config.loaders import (
    find_config_file,
    load_config,
    load_subproject_config,
    get_subproject_absolute_path,
)
from systemeval.config.adapters import (
    TestCategory,
    PytestConfig,
    PipelineConfig,
    PlaywrightConfig,
    SurferConfig,
)
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
from systemeval.config.e2e import (
    E2EProviderConfig,
    DebuggAIConfig,
    E2EOutputConfig,
    E2EGitConfig,
    E2EConfig,
)
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

# Note: No deprecation warning is needed since the import path is the same.
# Users importing from systemeval.config will continue to work without changes.
# This file simply ensures backward compatibility for any direct file references.
