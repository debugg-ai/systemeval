"""Test framework adapters for systemeval.

This module has been reorganized into logical subdirectories:
- js/: JavaScript test frameworks (Jest, Vitest)
- python/: Python test frameworks (pytest, pipeline)
- browser/: Browser E2E frameworks (Playwright, Surfer)

All imports remain backward compatible through this __init__.py.
"""

from .base import AdapterConfig, BaseAdapter, TestFailure, TestItem, TestResult, Verdict
from .registry import get_adapter, is_registered, list_adapters, register_adapter
from .repositories import (
    DjangoProjectRepository,
    MockProjectRepository,
    ProjectRepository,
)

# Import adapters from new locations for backward compatibility
from .js import JestAdapter, VitestAdapter
from .python import PytestAdapter
from .python.pipeline import PipelineAdapter
from .browser import PlaywrightAdapter, SurferAdapter

__all__ = [
    # Configuration
    "AdapterConfig",
    # Base classes and data structures
    "BaseAdapter",
    "TestItem",
    "TestResult",
    "TestFailure",
    "Verdict",
    # JavaScript adapters
    "JestAdapter",
    "VitestAdapter",
    # Python adapters
    "PytestAdapter",
    "PipelineAdapter",
    # Browser adapters
    "PlaywrightAdapter",
    "SurferAdapter",
    # Registry functions
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "is_registered",
    # Repository abstractions
    "ProjectRepository",
    "DjangoProjectRepository",
    "MockProjectRepository",
]
