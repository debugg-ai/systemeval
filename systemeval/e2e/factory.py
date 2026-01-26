"""
Factory for creating E2E test generation providers.

This module provides a factory pattern for creating E2E providers with
dependency injection support and lazy initialization.

Key principles:
- No side effects at import (lazy initialization)
- Explicit configuration (no env var sniffing)
- Dependency injection support (custom provider classes)
- Type safety (registry of provider classes)

Usage:
    from systemeval.e2e.factory import E2EProviderFactory
    from systemeval.e2e.types import E2EConfig

    # Create factory (lazy, no side effects)
    factory = E2EProviderFactory()

    # Create provider from config
    config = E2EConfig(
        provider_name="debuggai",
        project_root=Path("/my/project"),
        api_key="sk-...",
    )
    provider = factory.create_provider(config)

    # Register custom provider class
    factory.register_provider_class("custom", MyCustomProvider)
"""

from pathlib import Path
from typing import Callable, Dict, List, Optional, Type, Union

from .core.protocols import E2EProvider
from .core.types import E2EConfig


# Type alias for provider factory functions
ProviderFactory = Callable[[E2EConfig], E2EProvider]


class E2EProviderFactory:
    """
    Factory for creating E2E test generation providers.

    This factory supports:
    - Built-in providers (debuggai, mock, local)
    - Custom provider registration
    - Lazy initialization (no side effects at import)
    - Dependency injection via custom provider classes or factories

    The factory can create providers in two ways:
    1. From a registered provider class (instantiated with config)
    2. From a registered factory function (called with config)

    Example:
        # Using built-in providers
        factory = E2EProviderFactory()
        provider = factory.create_provider(config)

        # Registering a custom provider class
        factory.register_provider_class("custom", MyProvider)
        provider = factory.create_provider(custom_config)

        # Registering a factory function for more control
        def create_my_provider(config: E2EConfig) -> E2EProvider:
            return MyProvider(api_key=config.api_key, custom_option=True)
        factory.register_factory("my_provider", create_my_provider)
    """

    def __init__(self, auto_register_builtin: bool = True) -> None:
        """
        Initialize the provider factory.

        Args:
            auto_register_builtin: If True, register built-in providers.
                                   Set to False for testing or custom setups.
        """
        self._provider_classes: Dict[str, Type[E2EProvider]] = {}
        self._factories: Dict[str, ProviderFactory] = {}
        self._initialized = False

        if auto_register_builtin:
            self._register_builtin_providers()
            self._initialized = True

    def _register_builtin_providers(self) -> None:
        """
        Register built-in providers lazily.

        This method is called during initialization if auto_register_builtin
        is True. It registers the standard providers without importing them
        until they're actually needed.
        """
        # Register factory functions for built-in providers
        # This avoids importing provider classes at factory creation time

        def create_debuggai_provider(config: E2EConfig) -> E2EProvider:
            from .providers.debuggai import DebuggAIProvider

            if not config.api_key:
                raise ValueError(
                    "api_key is required for DebuggAI provider. "
                    "Set it in E2EConfig.api_key or pass via CLI."
                )

            return DebuggAIProvider(
                api_key=config.api_key,
                api_base_url=config.api_base_url or "https://api.debugg.ai",
                timeout_seconds=config.timeout_seconds,
            )

        def create_mock_provider(config: E2EConfig) -> E2EProvider:
            from .examples import MockE2EProvider

            return MockE2EProvider(
                api_key=config.api_key or "mock-key",
                api_base_url=config.api_base_url or "http://mock.local",
                simulate_delay=config.extra.get("simulate_delay", False),
            )

        def create_local_provider(config: E2EConfig) -> E2EProvider:
            # Local provider is an alias for mock with delay disabled
            # In a real implementation, this could be a local test server
            from .examples import MockE2EProvider

            return MockE2EProvider(
                api_key=config.api_key or "local-key",
                api_base_url=config.api_base_url or "http://localhost:8080",
                simulate_delay=False,
            )

        self._factories["debuggai"] = create_debuggai_provider
        self._factories["mock"] = create_mock_provider
        self._factories["local"] = create_local_provider

    def register_provider_class(
        self,
        name: str,
        provider_class: Type[E2EProvider],
        override: bool = False,
    ) -> None:
        """
        Register a provider class.

        The class will be instantiated when create_provider() is called.
        The class constructor must accept an E2EConfig or support the
        standard provider constructor signature.

        Args:
            name: Provider name (e.g., 'custom', 'enterprise')
            provider_class: Provider class implementing E2EProvider protocol
            override: If True, allow overriding existing registration

        Raises:
            ValueError: If provider is already registered (unless override=True)
            TypeError: If provider_class doesn't implement E2EProvider

        Example:
            class MyProvider:
                def __init__(self, api_key: str, api_base_url: str):
                    ...

                def generate_tests(self, changes, config):
                    ...
                # ... other E2EProvider methods

            factory.register_provider_class("my", MyProvider)
        """
        if not override and name in self._provider_classes:
            raise ValueError(
                f"Provider class '{name}' is already registered. "
                f"Use override=True to replace it."
            )

        if not override and name in self._factories:
            raise ValueError(
                f"A factory for '{name}' is already registered. "
                f"Use override=True to replace it."
            )

        # Runtime check that class has expected methods
        required_methods = [
            "generate_tests",
            "get_status",
            "download_artifacts",
            "validate_config",
        ]
        for method in required_methods:
            if not hasattr(provider_class, method) or not callable(
                getattr(provider_class, method, None)
            ):
                raise TypeError(
                    f"Provider class must implement {method}() method. "
                    f"Got: {provider_class.__name__}"
                )

        self._provider_classes[name] = provider_class

        # Remove any existing factory with same name if overriding
        if override and name in self._factories:
            del self._factories[name]

    def register_factory(
        self,
        name: str,
        factory: ProviderFactory,
        override: bool = False,
    ) -> None:
        """
        Register a factory function for creating providers.

        This gives full control over how providers are instantiated.
        The factory function receives the E2EConfig and returns a provider.

        Args:
            name: Provider name
            factory: Factory function that creates the provider
            override: If True, allow overriding existing registration

        Raises:
            ValueError: If provider is already registered (unless override=True)

        Example:
            def create_enterprise_provider(config: E2EConfig) -> E2EProvider:
                return EnterpriseProvider(
                    api_key=config.api_key,
                    custom_auth=get_custom_auth(),
                    retry_config=RetryConfig(max_retries=5),
                )

            factory.register_factory("enterprise", create_enterprise_provider)
        """
        if not override and name in self._factories:
            raise ValueError(
                f"Factory '{name}' is already registered. "
                f"Use override=True to replace it."
            )

        if not override and name in self._provider_classes:
            raise ValueError(
                f"A provider class for '{name}' is already registered. "
                f"Use override=True to replace it."
            )

        self._factories[name] = factory

        # Remove any existing provider class with same name if overriding
        if override and name in self._provider_classes:
            del self._provider_classes[name]

    def get_provider_class(self, name: str) -> Optional[Type[E2EProvider]]:
        """
        Get a registered provider class by name.

        Args:
            name: Provider name

        Returns:
            Provider class if registered as a class, None if registered as factory

        Raises:
            KeyError: If provider is not registered

        Example:
            provider_class = factory.get_provider_class("custom")
            if provider_class:
                # Create instance manually
                provider = provider_class(api_key="...", api_base_url="...")
        """
        if name in self._provider_classes:
            return self._provider_classes[name]

        if name in self._factories:
            # Provider is registered as a factory, not a class
            return None

        available = self.list_providers()
        raise KeyError(
            f"Provider '{name}' not found. Available providers: {available or 'none'}"
        )

    def create_provider(self, config: E2EConfig) -> E2EProvider:
        """
        Create a provider instance from configuration.

        This is the main method for creating providers. It:
        1. Looks up the provider by config.provider_name
        2. Creates the provider using the registered class or factory
        3. Returns the configured provider instance

        Args:
            config: E2E configuration with provider_name and settings

        Returns:
            Configured provider instance

        Raises:
            KeyError: If provider_name is not registered
            ValueError: If configuration is invalid for the provider

        Example:
            config = E2EConfig(
                provider_name="debuggai",
                project_root=Path("/my/project"),
                api_key="sk-...",
            )
            provider = factory.create_provider(config)
            result = provider.generate_tests(changes, config)
        """
        name = config.provider_name

        # Try factory first (for built-in providers)
        if name in self._factories:
            return self._factories[name](config)

        # Then try registered class
        if name in self._provider_classes:
            provider_class = self._provider_classes[name]
            return self._create_from_class(provider_class, config)

        available = self.list_providers()
        raise KeyError(
            f"Provider '{name}' not found. Available providers: {available or 'none'}"
        )

    def _create_from_class(
        self,
        provider_class: Type[E2EProvider],
        config: E2EConfig,
    ) -> E2EProvider:
        """
        Create a provider from a registered class.

        Attempts to instantiate the class with standard constructor signature.
        Falls back to just api_key and api_base_url if other params fail.

        Args:
            provider_class: The provider class to instantiate
            config: E2E configuration

        Returns:
            Provider instance
        """
        # Try standard constructor signature
        try:
            return provider_class(
                api_key=config.api_key or "",
                api_base_url=config.api_base_url or "",
            )
        except TypeError:
            # Class may have different constructor, try with just config
            try:
                return provider_class(config=config)  # type: ignore
            except TypeError:
                # Last resort: try with no arguments
                return provider_class()  # type: ignore

    def list_providers(self) -> List[str]:
        """
        List all registered provider names.

        Returns:
            Sorted list of provider names

        Example:
            providers = factory.list_providers()
            print(f"Available: {', '.join(providers)}")
        """
        all_names = set(self._factories.keys()) | set(self._provider_classes.keys())
        return sorted(all_names)

    def is_registered(self, name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            name: Provider name

        Returns:
            True if registered (as class or factory), False otherwise

        Example:
            if factory.is_registered("custom"):
                provider = factory.create_provider(config)
        """
        return name in self._factories or name in self._provider_classes

    def unregister(self, name: str) -> None:
        """
        Unregister a provider.

        Args:
            name: Provider name

        Raises:
            KeyError: If provider not found

        Example:
            factory.unregister("old_provider")
        """
        if name in self._factories:
            del self._factories[name]
        elif name in self._provider_classes:
            del self._provider_classes[name]
        else:
            raise KeyError(f"Provider '{name}' not found")

    def clear(self) -> None:
        """
        Clear all registered providers.

        Useful for testing or resetting state.

        Example:
            factory.clear()
            assert len(factory.list_providers()) == 0
        """
        self._factories.clear()
        self._provider_classes.clear()
        self._initialized = False


# ============================================================================
# Global Factory Instance
# ============================================================================

# Global factory instance (lazily created)
_global_factory: Optional[E2EProviderFactory] = None


def _get_global_factory() -> E2EProviderFactory:
    """Get or create the global provider factory."""
    global _global_factory
    if _global_factory is None:
        _global_factory = E2EProviderFactory()
    return _global_factory


def create_provider(config: E2EConfig) -> E2EProvider:
    """
    Create a provider using the global factory.

    Convenience function for the global factory.
    For more control, create your own factory instance.

    Args:
        config: E2E configuration

    Returns:
        Configured provider instance

    Example:
        from systemeval.e2e.factory import create_provider

        config = E2EConfig(provider_name="debuggai", ...)
        provider = create_provider(config)
    """
    return _get_global_factory().create_provider(config)


def register_provider_class(
    name: str,
    provider_class: Type[E2EProvider],
    override: bool = False,
) -> None:
    """
    Register a provider class in the global factory.

    Args:
        name: Provider name
        provider_class: Provider class implementing E2EProvider

    Example:
        register_provider_class("custom", MyCustomProvider)
    """
    _get_global_factory().register_provider_class(name, provider_class, override)


def register_factory(
    name: str,
    factory: ProviderFactory,
    override: bool = False,
) -> None:
    """
    Register a provider factory function in the global factory.

    Args:
        name: Provider name
        factory: Factory function

    Example:
        def my_factory(config):
            return MyProvider(api_key=config.api_key)

        register_factory("my", my_factory)
    """
    _get_global_factory().register_factory(name, factory, override)


def get_provider_class(name: str) -> Optional[Type[E2EProvider]]:
    """
    Get a provider class from the global factory.

    Args:
        name: Provider name

    Returns:
        Provider class or None if registered as factory
    """
    return _get_global_factory().get_provider_class(name)


def list_factory_providers() -> List[str]:
    """
    List all providers registered in the global factory.

    Returns:
        Sorted list of provider names
    """
    return _get_global_factory().list_providers()


def is_factory_registered(name: str) -> bool:
    """
    Check if a provider is registered in the global factory.

    Args:
        name: Provider name

    Returns:
        True if registered
    """
    return _get_global_factory().is_registered(name)


def reset_global_factory() -> None:
    """
    Reset the global factory to initial state.

    Primarily for testing purposes.
    """
    global _global_factory
    _global_factory = None
