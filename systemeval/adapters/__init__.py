"""Test framework adapters for systemeval."""

from .base import BaseAdapter, TestFailure, TestItem, TestResult, Verdict
from .registry import get_adapter, is_registered, list_adapters, register_adapter

__all__ = [
    # Base classes and data structures
    "BaseAdapter",
    "TestItem",
    "TestResult",
    "TestFailure",
    "Verdict",
    # Registry functions
    "register_adapter",
    "get_adapter",
    "list_adapters",
    "is_registered",
]
