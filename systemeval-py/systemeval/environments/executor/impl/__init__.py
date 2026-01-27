"""
Executor implementation strategies.

This module contains different execution strategies:
- DockerExecutor: Docker-based test execution
- LocalCommandExecutor: Local process execution
- ProcessStreamHandler: Stream handler for processes
- Result parsers: Parse test framework output
- JSON parsers: Parse JSON test results
"""

from .docker_executor import DockerExecutor
from .process_executor import LocalCommandExecutor, ProcessStreamHandler
from .test_result_parser import (
    PytestResultParser,
    JestResultParser,
    PlaywrightResultParser,
    MochaResultParser,
    GoTestResultParser,
    GenericResultParser,
    TestResultAggregator,
)
from .json_parser import JsonResultParser, EmbeddedJsonParser

__all__ = [
    "DockerExecutor",
    "LocalCommandExecutor",
    "ProcessStreamHandler",
    "PytestResultParser",
    "JestResultParser",
    "PlaywrightResultParser",
    "MochaResultParser",
    "GoTestResultParser",
    "GenericResultParser",
    "TestResultAggregator",
    "JsonResultParser",
    "EmbeddedJsonParser",
]
