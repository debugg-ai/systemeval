"""Adapter registry for managing test framework adapters."""

from typing import Dict, List, Type

from .base import BaseAdapter


class AdapterRegistry:
    """Registry for test framework adapters."""

    def __init__(self) -> None:
        self._adapters: Dict[str, Type[BaseAdapter]] = {}

    def register(self, name: str, adapter_class: Type[BaseAdapter]) -> None:
        """Register a test framework adapter.

        Args:
            name: Adapter name (e.g., 'pytest', 'jest')
            adapter_class: Adapter class implementing BaseAdapter

        Raises:
            ValueError: If adapter is already registered or invalid
        """
        if not issubclass(adapter_class, BaseAdapter):
            raise ValueError(f"Adapter class must inherit from BaseAdapter: {adapter_class}")

        if name in self._adapters:
            raise ValueError(f"Adapter '{name}' is already registered")

        self._adapters[name] = adapter_class

    def get(self, name: str, project_root: str) -> BaseAdapter:
        """Get an adapter instance by name.

        Args:
            name: Adapter name
            project_root: Project root directory path

        Returns:
            Initialized adapter instance

        Raises:
            KeyError: If adapter not found
        """
        if name not in self._adapters:
            raise KeyError(
                f"Adapter '{name}' not found. Available adapters: {self.list_adapters()}"
            )

        adapter_class = self._adapters[name]
        return adapter_class(project_root)

    def list_adapters(self) -> List[str]:
        """List all registered adapter names.

        Returns:
            List of adapter names
        """
        return sorted(self._adapters.keys())

    def is_registered(self, name: str) -> bool:
        """Check if an adapter is registered.

        Args:
            name: Adapter name

        Returns:
            True if registered, False otherwise
        """
        return name in self._adapters


# Global registry instance
_registry = AdapterRegistry()


def register_adapter(name: str, adapter_class: Type[BaseAdapter]) -> None:
    """Register a test framework adapter in the global registry.

    Args:
        name: Adapter name (e.g., 'pytest', 'jest')
        adapter_class: Adapter class implementing BaseAdapter
    """
    _registry.register(name, adapter_class)


def get_adapter(name: str, project_root: str) -> BaseAdapter:
    """Get an adapter instance from the global registry.

    Args:
        name: Adapter name
        project_root: Project root directory path

    Returns:
        Initialized adapter instance
    """
    return _registry.get(name, project_root)


def list_adapters() -> List[str]:
    """List all registered adapter names in the global registry.

    Returns:
        List of adapter names
    """
    return _registry.list_adapters()


def is_registered(name: str) -> bool:
    """Check if an adapter is registered in the global registry.

    Args:
        name: Adapter name

    Returns:
        True if registered, False otherwise
    """
    return _registry.is_registered(name)


# Auto-register available adapters
def _register_builtin_adapters() -> None:
    """Register built-in adapters if their dependencies are available."""
    # Try to register pytest adapter
    try:
        from .pytest_adapter import PytestAdapter

        register_adapter("pytest", PytestAdapter)
    except ImportError:
        pass

    # Try to register pipeline adapter
    try:
        from .pipeline_adapter import PipelineAdapter

        register_adapter("pipeline", PipelineAdapter)
    except ImportError:
        pass

    # Try to register playwright adapter
    try:
        from .playwright_adapter import PlaywrightAdapter

        register_adapter("playwright", PlaywrightAdapter)
    except ImportError:
        pass

    # Try to register surfer adapter
    try:
        from .surfer_adapter import SurferAdapter

        register_adapter("surfer", SurferAdapter)
    except ImportError:
        pass

    # Try to register vitest adapter
    try:
        from .vitest_adapter import VitestAdapter

        register_adapter("vitest", VitestAdapter)
    except ImportError:
        pass

    # Try to register jest adapter
    try:
        from .jest_adapter import JestAdapter

        register_adapter("jest", JestAdapter)
    except ImportError:
        pass


# Auto-register on module import
_register_builtin_adapters()
