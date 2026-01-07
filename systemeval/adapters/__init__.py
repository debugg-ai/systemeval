"""Test framework adapters for systemeval."""

from .base import AdapterConfig, BaseAdapter, TestFailure, TestItem, TestResult, Verdict
from .registry import get_adapter, is_registered, list_adapters, register_adapter
from .repositories import (
    DjangoProjectRepository,
    MockProjectRepository,
    ProjectRepository,
)
from .playwright_adapter import PlaywrightAdapter
from .surfer_adapter import SurferAdapter

__all__ = [
    # Configuration
    "AdapterConfig",
    # Base classes and data structures
    "BaseAdapter",
    "TestItem",
    "TestResult",
    "TestFailure",
    "Verdict",
    # Adapter implementations
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
