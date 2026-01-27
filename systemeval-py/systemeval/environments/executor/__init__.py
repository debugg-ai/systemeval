"""
Test execution orchestration.

This module contains the TestExecutor and related classes for running tests
in various environments (local, Docker, etc.).
"""

from .executor import TestExecutor, ExecutionConfig
from .impl.docker_executor import DockerExecutor
from .models import ExecutionResult

__all__ = [
    "TestExecutor",
    "ExecutionConfig",
    "DockerExecutor",
    "ExecutionResult",
]
