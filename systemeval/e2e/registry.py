"""
Registry for E2E test generation providers.

This module provides a registry pattern for managing E2E providers,
following systemeval's adapter registry pattern but adapted for providers
that return instances rather than classes.

Key principle: Registry returns INSTANCES, not strings or classes.
This prevents string dispatch and provides type safety.
"""

from typing import Dict, List, Optional

from .core.protocols import E2EProvider


class E2EProviderRegistry:
    """
    Registry for E2E test generation providers.

    Unlike adapter registry which stores classes, this stores provider instances.
    This is because providers typically need initialization parameters (API keys,
    URLs, etc.) that shouldn't be discovered from environment.

    Usage:
        # Create provider instance with explicit config
        surfer = SurferProvider(api_key="sk-...", api_base_url="https://...")

        # Register instance
        registry = E2EProviderRegistry()
        registry.register("surfer", surfer)

        # Get registered instance
        provider = registry.get("surfer")
        result = provider.generate_tests(changes, config)
    """

    def __init__(self) -> None:
        """Initialize empty registry."""
        self._providers: Dict[str, E2EProvider] = {}

    def register(self, name: str, provider: E2EProvider) -> None:
        """
        Register an E2E provider instance.

        Args:
            name: Provider name (e.g., 'surfer', 'custom')
            provider: Provider instance implementing E2EProvider protocol

        Raises:
            ValueError: If provider is already registered or invalid
            TypeError: If provider doesn't implement E2EProvider protocol

        Example:
            surfer = SurferProvider(api_key="...", api_base_url="...")
            registry.register("surfer", surfer)
        """
        # Verify it implements the protocol (runtime check)
        if not isinstance(provider, E2EProvider):
            raise TypeError(
                f"Provider must implement E2EProvider protocol. "
                f"Got: {type(provider).__name__}"
            )

        if name in self._providers:
            raise ValueError(f"Provider '{name}' is already registered")

        self._providers[name] = provider

    def get(self, name: str) -> E2EProvider:
        """
        Get a registered provider instance by name.

        Args:
            name: Provider name

        Returns:
            Provider instance

        Raises:
            KeyError: If provider not found

        Example:
            provider = registry.get("surfer")
            result = provider.generate_tests(changes, config)
        """
        if name not in self._providers:
            available = self.list_providers()
            raise KeyError(
                f"Provider '{name}' not found. "
                f"Available providers: {available or 'none'}"
            )

        return self._providers[name]

    def list_providers(self) -> List[str]:
        """
        List all registered provider names.

        Returns:
            Sorted list of provider names

        Example:
            providers = registry.list_providers()
            print(f"Available providers: {', '.join(providers)}")
        """
        return sorted(self._providers.keys())

    def is_registered(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: Provider name

        Returns:
            True if registered, False otherwise

        Example:
            if registry.is_registered("surfer"):
                provider = registry.get("surfer")
        """
        return name in self._providers

    def unregister(self, name: str) -> None:
        """
        Unregister a provider.

        Args:
            name: Provider name

        Raises:
            KeyError: If provider not found

        Example:
            registry.unregister("surfer")
        """
        if name not in self._providers:
            raise KeyError(f"Provider '{name}' not found")

        del self._providers[name]

    def clear(self) -> None:
        """
        Clear all registered providers.

        Useful for testing or resetting state.

        Example:
            registry.clear()
            assert len(registry.list_providers()) == 0
        """
        self._providers.clear()


# ============================================================================
# Global Registry Instance
# ============================================================================

# Global registry instance (lazily created, not at module import)
_global_registry: Optional[E2EProviderRegistry] = None


def _get_global_registry() -> E2EProviderRegistry:
    """Get or create the global provider registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = E2EProviderRegistry()
    return _global_registry


def register_provider(name: str, provider: E2EProvider) -> None:
    """
    Register an E2E provider in the global registry.

    This is a convenience function for the global registry.
    For more control, create your own registry instance.

    Args:
        name: Provider name (e.g., 'surfer', 'custom')
        provider: Provider instance implementing E2EProvider protocol

    Example:
        surfer = SurferProvider(api_key="...", api_base_url="...")
        register_provider("surfer", surfer)
    """
    registry = _get_global_registry()
    registry.register(name, provider)


def get_provider(name: str) -> E2EProvider:
    """
    Get a provider instance from the global registry.

    Args:
        name: Provider name

    Returns:
        Provider instance

    Raises:
        KeyError: If provider not found

    Example:
        provider = get_provider("surfer")
        result = provider.generate_tests(changes, config)
    """
    registry = _get_global_registry()
    return registry.get(name)


def list_providers() -> List[str]:
    """
    List all registered provider names in the global registry.

    Returns:
        Sorted list of provider names

    Example:
        providers = list_providers()
        print(f"Available: {', '.join(providers)}")
    """
    registry = _get_global_registry()
    return registry.list_providers()


def is_registered(name: str) -> bool:
    """
    Check if a provider is registered in the global registry.

    Args:
        name: Provider name

    Returns:
        True if registered, False otherwise

    Example:
        if is_registered("surfer"):
            provider = get_provider("surfer")
    """
    registry = _get_global_registry()
    return registry.is_registered(name)


# Note: No auto-registration at module import.
# Providers must be explicitly registered by the application:
#
#   from systemeval.e2e import register_provider
#   from my_provider import SurferProvider
#
#   surfer = SurferProvider(api_key="...", api_base_url="...")
#   register_provider("surfer", surfer)
#
# This ensures:
# 1. No side effects at import time
# 2. Explicit configuration (no env var sniffing)
# 3. Clear dependency injection
# 4. Testable (can create isolated registries)
