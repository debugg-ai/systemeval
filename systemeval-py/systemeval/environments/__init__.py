"""
Environment abstractions for multi-environment test orchestration.
"""
from systemeval.environments.base import (
    Environment,
    EnvironmentType,
    SetupResult,
)
from systemeval.environments.standalone import StandaloneEnvironment
from systemeval.environments.docker_compose import DockerComposeEnvironment
from systemeval.environments.composite import CompositeEnvironment
from systemeval.environments.ngrok import NgrokEnvironment
from systemeval.environments.browser import BrowserEnvironment
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
