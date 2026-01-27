"""
Environment abstractions for multi-environment test orchestration.
"""
from systemeval.environments.base import (
    Environment,
    EnvironmentType,
    SetupResult,
)
from systemeval.environments.implementations import (
    StandaloneEnvironment,
    DockerComposeEnvironment,
    CompositeEnvironment,
    NgrokEnvironment,
    BrowserEnvironment,
)
from systemeval.environments.resolver import EnvironmentResolver
from systemeval.environments.executor import (
    TestExecutor,
    DockerExecutor,
    ExecutionConfig,
    ExecutionResult,
)

__all__ = [
    "Environment",
    "EnvironmentType",
    "SetupResult",
    "StandaloneEnvironment",
    "DockerComposeEnvironment",
    "CompositeEnvironment",
    "NgrokEnvironment",
    "BrowserEnvironment",
    "EnvironmentResolver",
    "TestExecutor",
    "DockerExecutor",
    "ExecutionConfig",
    "ExecutionResult",
]
