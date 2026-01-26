"""
Executor submodule - Modular test execution components.

This module provides a clean separation of concerns for test execution:
- process_executor: Local command execution with streaming
- docker_executor: Docker container execution
- test_result_parser: Framework-specific result parsing
- json_parser: JSON result parsing

All components are re-exported for backward compatibility.
"""

# Process execution
from systemeval.environments.executor_impl.process_executor import (
    LocalCommandExecutor,
    ProcessStreamHandler,
)

# Docker execution
from systemeval.environments.executor_impl.docker_executor import (
    DockerExecutor,
)

# Test result parsing
from systemeval.environments.executor_impl.test_result_parser import (
    PytestResultParser,
    JestResultParser,
    PlaywrightResultParser,
    MochaResultParser,
    GoTestResultParser,
    GenericResultParser,
    TestResultAggregator,
    DEFAULT_PARSERS,
)

# JSON parsing
from systemeval.environments.executor_impl.json_parser import (
    JsonResultParser,
    EmbeddedJsonParser,
)

__all__ = [
    # Process execution
    "LocalCommandExecutor",
    "ProcessStreamHandler",
    # Docker execution
    "DockerExecutor",
    # Test result parsing
    "PytestResultParser",
    "JestResultParser",
    "PlaywrightResultParser",
    "MochaResultParser",
    "GoTestResultParser",
    "GenericResultParser",
    "TestResultAggregator",
    "DEFAULT_PARSERS",
    # JSON parsing
    "JsonResultParser",
    "EmbeddedJsonParser",
]
