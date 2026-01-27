"""
Shared type definitions for SystemEval.

This module contains core types used across adapters, environments, and evaluation
to avoid circular dependencies.

The types are organized into domain-specific modules:
- common: Verdict enum and Result[T, E] generic type
- adapters: AdapterConfig
- results: TestItem, TestFailure, TestResult
- options: CLI option dataclasses

For backward compatibility, all types are re-exported at the package level.
"""

# Common types
from .common import Err, Ok, Result, Verdict

# Adapter configuration
from .adapters import AdapterConfig

# Test results
from .results import TestFailure, TestItem, TestResult

# CLI options
from .options import (
    BrowserOptions,
    EnvironmentOptions,
    ExecutionOptions,
    MultiProjectOptions,
    OutputOptions,
    PipelineOptions,
    TestCommandOptions,
    TestSelectionOptions,
)

__all__ = [
    # Common types
    "Verdict",
    "Result",
    "Ok",
    "Err",
    # Adapter configuration
    "AdapterConfig",
    # Test results
    "TestItem",
    "TestFailure",
    "TestResult",
    # CLI options
    "TestSelectionOptions",
    "ExecutionOptions",
    "OutputOptions",
    "EnvironmentOptions",
    "PipelineOptions",
    "BrowserOptions",
    "MultiProjectOptions",
    "TestCommandOptions",
]
