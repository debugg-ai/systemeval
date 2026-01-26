"""
E2E test generation provider interfaces.

This module defines the contracts for E2E test generation providers,
following strict architectural principles:
- No provider lock-in: True interface contracts
- No magic values: All configuration via explicit parameters
- No config discovery: No env var sniffing, no cwd searching
- No module side effects: Nothing runs at import
- No string dispatch: Registry returns instances, not strings

Usage:
    from systemeval.e2e import initialize, get_provider, E2EConfig

    # Must initialize before using providers
    config = E2EConfig(provider="debuggai", ...)
    initialize(config)

    # Now providers can be used
    provider = get_provider("debuggai")
    result = provider.generate_tests(changes, config)

    # Check initialization state
    if is_initialized():
        ...

    # Reset for testing
    reset()
"""

from typing import Optional

# Core types and protocols
from .core import (
    E2EProvider,
    E2EOrchestrator,
    ChangeSet,
    Change,
    ChangeType,
    E2EConfig,
    GenerationResult,
    StatusResult,
    ArtifactResult,
    ValidationResult,
    E2EResult,
    CompletionResult,
    GenerationStatus,
)

# Registry
from .registry import (
    E2EProviderRegistry,
    register_provider,
    get_provider as _registry_get_provider,
    list_providers,
    is_registered,
)

# Factory
from .factory import (
    E2EProviderFactory,
    create_provider as factory_create_provider,
    register_provider_class,
    register_factory,
    get_provider_class,
    list_factory_providers,
    is_factory_registered,
    reset_global_factory,
)

# Examples
from .examples import (
    MockE2EProvider,
    BasicE2EOrchestrator,
)

# Providers
from .providers import (
    DebuggAIProvider,
)

# Git Analysis
from .analysis import (
    GitAnalysisError,
    get_current_branch,
    get_default_branch,
    analyze_working_changes,
    analyze_commit,
    analyze_range,
    analyze_pr_changes,
)

# Reporting
from .reporting import (
    generation_status_to_verdict,
    e2e_result_to_test_result,
    status_result_to_test_result,
    e2e_to_evaluation_result,
    create_e2e_evaluation_context,
    render_e2e_result,
)

# Validation
from .validation import (
    E2EConfigValidator,
    validate_e2e_config,
    quick_validate,
    SUPPORTED_TEST_FRAMEWORKS,
    SUPPORTED_LANGUAGES,
    PROVIDERS_REQUIRING_API_KEY,
    MIN_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
)

# Storage
from .storage import (
    ArtifactStorage,
    StorageError,
    RunNotFoundError,
    ArtifactNotFoundError,
)


# ============================================================================
# Module Initialization State
# ============================================================================

# Module-level state (no side effects at import)
_initialized: bool = False
_config: Optional[E2EConfig] = None


class E2ENotInitializedError(RuntimeError):
    """Raised when E2E module is used before initialize() is called."""

    def __init__(self, operation: str = "use E2E providers"):
        super().__init__(
            f"Cannot {operation}: E2E module not initialized. "
            f"Call systemeval.e2e.initialize(config) first."
        )


def initialize(config: E2EConfig) -> None:
    """
    Initialize the E2E module with configuration.

    This MUST be called before using any E2E providers.
    The function validates the config and prepares the module for use.

    Args:
        config: E2E configuration specifying provider, output paths, etc.

    Raises:
        ValueError: If config is invalid
        TypeError: If config is not an E2EConfig instance

    Example:
        from systemeval.e2e import initialize, E2EConfig

        config = E2EConfig(
            provider="debuggai",
            provider_config={"api_key": "sk-...", "api_url": "https://..."},
            output_dir="/tmp/e2e",
        )
        initialize(config)
    """
    global _initialized, _config

    if not isinstance(config, E2EConfig):
        raise TypeError(
            f"config must be an E2EConfig instance, got {type(config).__name__}"
        )

    # Validate the config (will raise ValueError if invalid)
    if not config.provider_name:
        raise ValueError("config.provider_name cannot be empty")

    _config = config
    _initialized = True


def is_initialized() -> bool:
    """
    Check if the E2E module has been initialized.

    Returns:
        True if initialize() has been called, False otherwise

    Example:
        from systemeval.e2e import is_initialized, initialize

        if not is_initialized():
            initialize(config)
    """
    return _initialized


def require_initialized(operation: str = "use E2E providers") -> None:
    """
    Raise an error if the E2E module is not initialized.

    Args:
        operation: Description of the operation being attempted

    Raises:
        E2ENotInitializedError: If not initialized

    Example:
        from systemeval.e2e import require_initialized

        def my_function():
            require_initialized("call my_function")
            # ... rest of function
    """
    if not _initialized:
        raise E2ENotInitializedError(operation)


def get_config() -> E2EConfig:
    """
    Get the current E2E configuration.

    Returns:
        The E2EConfig passed to initialize()

    Raises:
        E2ENotInitializedError: If not initialized

    Example:
        from systemeval.e2e import get_config

        config = get_config()
        print(f"Using provider: {config.provider}")
    """
    require_initialized("get E2E config")
    assert _config is not None  # For type checker
    return _config


def get_provider(name: str) -> E2EProvider:
    """
    Get a provider instance from the global registry.

    This wraps the registry's get_provider to enforce initialization.

    Args:
        name: Provider name

    Returns:
        Provider instance

    Raises:
        E2ENotInitializedError: If not initialized
        KeyError: If provider not found

    Example:
        provider = get_provider("debuggai")
        result = provider.generate_tests(changes, config)
    """
    require_initialized(f"get provider '{name}'")
    return _registry_get_provider(name)


def reset() -> None:
    """
    Reset the E2E module to uninitialized state.

    This is primarily for testing purposes.
    Clears the configuration and resets initialization state.

    Example:
        from systemeval.e2e import reset, is_initialized

        reset()
        assert not is_initialized()
    """
    global _initialized, _config
    _initialized = False
    _config = None


__all__ = [
    # Initialization
    "initialize",
    "is_initialized",
    "require_initialized",
    "get_config",
    "reset",
    "E2ENotInitializedError",
    # Protocols
    "E2EProvider",
    "E2EOrchestrator",
    # Types
    "ChangeSet",
    "Change",
    "ChangeType",
    "E2EConfig",
    "GenerationResult",
    "StatusResult",
    "ArtifactResult",
    "ValidationResult",
    "E2EResult",
    "CompletionResult",
    "GenerationStatus",
    # Registry
    "E2EProviderRegistry",
    "register_provider",
    "get_provider",
    "list_providers",
    "is_registered",
    # Factory
    "E2EProviderFactory",
    "factory_create_provider",
    "register_provider_class",
    "register_factory",
    "get_provider_class",
    "list_factory_providers",
    "is_factory_registered",
    "reset_global_factory",
    # Examples
    "MockE2EProvider",
    "BasicE2EOrchestrator",
    # Providers
    "DebuggAIProvider",
    # Git Analysis
    "GitAnalysisError",
    "get_current_branch",
    "get_default_branch",
    "analyze_working_changes",
    "analyze_commit",
    "analyze_range",
    "analyze_pr_changes",
    # Reporting
    "generation_status_to_verdict",
    "e2e_result_to_test_result",
    "status_result_to_test_result",
    "e2e_to_evaluation_result",
    "create_e2e_evaluation_context",
    "render_e2e_result",
    # Validation
    "E2EConfigValidator",
    "validate_e2e_config",
    "quick_validate",
    "SUPPORTED_TEST_FRAMEWORKS",
    "SUPPORTED_LANGUAGES",
    "PROVIDERS_REQUIRING_API_KEY",
    "MIN_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    # Storage
    "ArtifactStorage",
    "StorageError",
    "RunNotFoundError",
    "ArtifactNotFoundError",
]
