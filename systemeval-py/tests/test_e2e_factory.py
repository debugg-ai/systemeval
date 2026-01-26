"""
Tests for E2E provider factory.

This test suite validates:
1. Factory creation and initialization
2. Built-in provider registration
3. Custom provider class registration
4. Custom factory function registration
5. Provider creation from config
6. Error handling for missing/invalid providers
7. Global factory functions
"""

import tempfile
from pathlib import Path
from typing import Dict

import pytest

from systemeval.e2e import (
    E2EConfig,
    E2EProviderFactory,
    factory_create_provider,
    register_provider_class,
    register_factory,
    get_provider_class,
    list_factory_providers,
    is_factory_registered,
    reset_global_factory,
)
from systemeval.e2e.protocols import E2EProvider
from systemeval.e2e.types import (
    ArtifactResult,
    ChangeSet,
    Change,
    ChangeType,
    GenerationResult,
    GenerationStatus,
    StatusResult,
    ValidationResult,
)


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def temp_project(tmp_path: Path) -> Path:
    """Create a temporary project directory."""
    project_dir = tmp_path / "test_project"
    project_dir.mkdir()
    return project_dir


@pytest.fixture
def basic_config(temp_project: Path) -> E2EConfig:
    """Create a basic E2E config for testing."""
    return E2EConfig(
        provider_name="mock",
        project_root=temp_project,
        api_key="test-key",
        api_base_url="http://test.local",
    )


@pytest.fixture
def debuggai_config(temp_project: Path) -> E2EConfig:
    """Create a DebuggAI config for testing."""
    return E2EConfig(
        provider_name="debuggai",
        project_root=temp_project,
        api_key="sk-test-key",
        api_base_url="https://api.debugg.ai",
    )


@pytest.fixture
def factory() -> E2EProviderFactory:
    """Create a fresh factory instance."""
    return E2EProviderFactory()


@pytest.fixture
def empty_factory() -> E2EProviderFactory:
    """Create an empty factory without built-in providers."""
    return E2EProviderFactory(auto_register_builtin=False)


class MockCustomProvider:
    """A custom provider for testing registration."""

    def __init__(self, api_key: str, api_base_url: str):
        self.api_key = api_key
        self.api_base_url = api_base_url
        self._runs: Dict[str, dict] = {}

    def generate_tests(self, changes: ChangeSet, config: E2EConfig) -> GenerationResult:
        run_id = "custom-123"
        self._runs[run_id] = {"status": "in_progress"}
        return GenerationResult(
            run_id=run_id,
            status=GenerationStatus.IN_PROGRESS,
            message="Custom provider started",
        )

    def get_status(self, run_id: str) -> StatusResult:
        return StatusResult(
            run_id=run_id,
            status=GenerationStatus.COMPLETED,
            tests_generated=5,
        )

    def download_artifacts(self, run_id: str, output_dir: Path) -> ArtifactResult:
        return ArtifactResult(
            run_id=run_id,
            output_directory=output_dir,
            test_files=[],
            total_tests=5,
        )

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        return ValidationResult(valid=True)


# ============================================================================
# Factory Initialization Tests
# ============================================================================


class TestFactoryInitialization:
    """Test factory initialization and built-in providers."""

    def test_factory_with_builtin_providers(self, factory: E2EProviderFactory):
        """Factory should have built-in providers registered."""
        providers = factory.list_providers()
        assert "debuggai" in providers
        assert "mock" in providers
        assert "local" in providers

    def test_factory_without_builtin_providers(self, empty_factory: E2EProviderFactory):
        """Factory without auto_register should be empty."""
        providers = empty_factory.list_providers()
        assert len(providers) == 0

    def test_factory_is_registered(self, factory: E2EProviderFactory):
        """is_registered should return True for built-in providers."""
        assert factory.is_registered("debuggai")
        assert factory.is_registered("mock")
        assert factory.is_registered("local")
        assert not factory.is_registered("nonexistent")


# ============================================================================
# Provider Class Registration Tests
# ============================================================================


class TestProviderClassRegistration:
    """Test registration of custom provider classes."""

    def test_register_provider_class(self, empty_factory: E2EProviderFactory):
        """Should register a provider class successfully."""
        empty_factory.register_provider_class("custom", MockCustomProvider)
        assert empty_factory.is_registered("custom")
        assert "custom" in empty_factory.list_providers()

    def test_register_duplicate_class_raises(self, empty_factory: E2EProviderFactory):
        """Should raise ValueError for duplicate registration."""
        empty_factory.register_provider_class("custom", MockCustomProvider)
        with pytest.raises(ValueError, match="already registered"):
            empty_factory.register_provider_class("custom", MockCustomProvider)

    def test_register_duplicate_with_override(self, empty_factory: E2EProviderFactory):
        """Should allow override with override=True."""
        empty_factory.register_provider_class("custom", MockCustomProvider)
        # This should not raise
        empty_factory.register_provider_class("custom", MockCustomProvider, override=True)
        assert empty_factory.is_registered("custom")

    def test_register_invalid_class_raises(self, empty_factory: E2EProviderFactory):
        """Should raise TypeError for class without required methods."""

        class InvalidProvider:
            pass

        with pytest.raises(TypeError, match="must implement"):
            empty_factory.register_provider_class("invalid", InvalidProvider)

    def test_get_provider_class(self, empty_factory: E2EProviderFactory):
        """Should return registered provider class."""
        empty_factory.register_provider_class("custom", MockCustomProvider)
        provider_class = empty_factory.get_provider_class("custom")
        assert provider_class is MockCustomProvider

    def test_get_provider_class_not_found(self, empty_factory: E2EProviderFactory):
        """Should raise KeyError for unregistered provider."""
        with pytest.raises(KeyError, match="not found"):
            empty_factory.get_provider_class("nonexistent")

    def test_get_provider_class_returns_none_for_factory(self, factory: E2EProviderFactory):
        """Should return None for providers registered as factories."""
        # Built-in providers are registered as factories, not classes
        provider_class = factory.get_provider_class("mock")
        assert provider_class is None


# ============================================================================
# Factory Function Registration Tests
# ============================================================================


class TestFactoryFunctionRegistration:
    """Test registration of factory functions."""

    def test_register_factory(self, empty_factory: E2EProviderFactory):
        """Should register a factory function successfully."""

        def create_provider(config: E2EConfig) -> E2EProvider:
            return MockCustomProvider(
                api_key=config.api_key or "",
                api_base_url=config.api_base_url or "",
            )

        empty_factory.register_factory("custom", create_provider)
        assert empty_factory.is_registered("custom")

    def test_register_duplicate_factory_raises(self, empty_factory: E2EProviderFactory):
        """Should raise ValueError for duplicate factory registration."""

        def create_provider(config: E2EConfig) -> E2EProvider:
            return MockCustomProvider("", "")

        empty_factory.register_factory("custom", create_provider)
        with pytest.raises(ValueError, match="already registered"):
            empty_factory.register_factory("custom", create_provider)

    def test_register_factory_overrides_class(self, empty_factory: E2EProviderFactory):
        """Factory registration with override should replace class registration."""
        empty_factory.register_provider_class("custom", MockCustomProvider)

        def create_provider(config: E2EConfig) -> E2EProvider:
            return MockCustomProvider("factory-key", "factory-url")

        empty_factory.register_factory("custom", create_provider, override=True)

        # Class should be removed, only factory should exist
        assert empty_factory.get_provider_class("custom") is None


# ============================================================================
# Provider Creation Tests
# ============================================================================


class TestProviderCreation:
    """Test creating providers from config."""

    def test_create_mock_provider(self, factory: E2EProviderFactory, basic_config: E2EConfig):
        """Should create mock provider from config."""
        provider = factory.create_provider(basic_config)
        assert provider is not None
        assert hasattr(provider, "generate_tests")
        assert hasattr(provider, "get_status")

    def test_create_debuggai_provider(self, factory: E2EProviderFactory, debuggai_config: E2EConfig):
        """Should create DebuggAI provider from config."""
        provider = factory.create_provider(debuggai_config)
        assert provider is not None
        assert hasattr(provider, "api_key")
        assert provider.api_key == "sk-test-key"

    def test_create_local_provider(self, factory: E2EProviderFactory, temp_project: Path):
        """Should create local provider from config."""
        config = E2EConfig(
            provider_name="local",
            project_root=temp_project,
        )
        provider = factory.create_provider(config)
        assert provider is not None

    def test_create_debuggai_without_api_key_raises(self, factory: E2EProviderFactory, temp_project: Path):
        """Should raise ValueError when DebuggAI provider has no API key."""
        config = E2EConfig(
            provider_name="debuggai",
            project_root=temp_project,
            # No api_key
        )
        with pytest.raises(ValueError, match="api_key is required"):
            factory.create_provider(config)

    def test_create_unknown_provider_raises(self, factory: E2EProviderFactory, temp_project: Path):
        """Should raise KeyError for unknown provider."""
        config = E2EConfig(
            provider_name="nonexistent",
            project_root=temp_project,
        )
        with pytest.raises(KeyError, match="not found"):
            factory.create_provider(config)

    def test_create_from_registered_class(self, empty_factory: E2EProviderFactory, temp_project: Path):
        """Should create provider from registered class."""
        empty_factory.register_provider_class("custom", MockCustomProvider)

        config = E2EConfig(
            provider_name="custom",
            project_root=temp_project,
            api_key="custom-key",
            api_base_url="http://custom.local",
        )

        provider = empty_factory.create_provider(config)
        assert provider is not None
        assert isinstance(provider, MockCustomProvider)
        assert provider.api_key == "custom-key"

    def test_create_from_registered_factory(self, empty_factory: E2EProviderFactory, temp_project: Path):
        """Should create provider from registered factory function."""
        captured_config = {}

        def create_provider(config: E2EConfig) -> E2EProvider:
            captured_config["api_key"] = config.api_key
            return MockCustomProvider(
                api_key=config.api_key or "",
                api_base_url=config.api_base_url or "",
            )

        empty_factory.register_factory("custom", create_provider)

        config = E2EConfig(
            provider_name="custom",
            project_root=temp_project,
            api_key="factory-key",
        )

        provider = empty_factory.create_provider(config)
        assert provider is not None
        assert captured_config["api_key"] == "factory-key"


# ============================================================================
# Factory Management Tests
# ============================================================================


class TestFactoryManagement:
    """Test factory management operations."""

    def test_unregister_provider(self, factory: E2EProviderFactory):
        """Should unregister a provider."""
        assert factory.is_registered("mock")
        factory.unregister("mock")
        assert not factory.is_registered("mock")

    def test_unregister_nonexistent_raises(self, factory: E2EProviderFactory):
        """Should raise KeyError for unregistering nonexistent provider."""
        with pytest.raises(KeyError, match="not found"):
            factory.unregister("nonexistent")

    def test_clear_factory(self, factory: E2EProviderFactory):
        """Should clear all providers."""
        assert len(factory.list_providers()) > 0
        factory.clear()
        assert len(factory.list_providers()) == 0

    def test_list_providers_sorted(self, factory: E2EProviderFactory):
        """list_providers should return sorted list."""
        providers = factory.list_providers()
        assert providers == sorted(providers)


# ============================================================================
# Global Factory Tests
# ============================================================================


class TestGlobalFactory:
    """Test global factory functions."""

    def setup_method(self):
        """Reset global factory before each test."""
        reset_global_factory()

    def teardown_method(self):
        """Reset global factory after each test."""
        reset_global_factory()

    def test_list_factory_providers(self):
        """list_factory_providers should return built-in providers."""
        providers = list_factory_providers()
        assert "debuggai" in providers
        assert "mock" in providers
        assert "local" in providers

    def test_is_factory_registered(self):
        """is_factory_registered should work for global factory."""
        assert is_factory_registered("mock")
        assert not is_factory_registered("nonexistent")

    def test_register_provider_class_global(self):
        """register_provider_class should add to global factory."""
        register_provider_class("custom", MockCustomProvider)
        assert is_factory_registered("custom")

    def test_register_factory_global(self, temp_project: Path):
        """register_factory should add to global factory."""

        def create_provider(config: E2EConfig) -> E2EProvider:
            return MockCustomProvider("", "")

        register_factory("custom_factory", create_provider)
        assert is_factory_registered("custom_factory")

    def test_factory_create_provider(self, temp_project: Path):
        """factory_create_provider should create provider from global factory."""
        config = E2EConfig(
            provider_name="mock",
            project_root=temp_project,
        )
        provider = factory_create_provider(config)
        assert provider is not None

    def test_get_provider_class_global(self):
        """get_provider_class should get from global factory."""
        register_provider_class("custom", MockCustomProvider)
        provider_class = get_provider_class("custom")
        assert provider_class is MockCustomProvider

    def test_reset_global_factory(self, temp_project: Path):
        """reset_global_factory should reset to fresh state."""
        # Register a custom provider
        register_provider_class("custom", MockCustomProvider)
        assert is_factory_registered("custom")

        # Reset
        reset_global_factory()

        # Custom provider should be gone, but built-ins should be back
        assert not is_factory_registered("custom")
        assert is_factory_registered("mock")


# ============================================================================
# Provider Protocol Compliance Tests
# ============================================================================


class TestProviderProtocolCompliance:
    """Test that created providers comply with E2EProvider protocol."""

    def test_mock_provider_methods(self, factory: E2EProviderFactory, basic_config: E2EConfig, temp_project: Path):
        """Mock provider should implement all required methods."""
        provider = factory.create_provider(basic_config)

        # Test validate_config
        validation = provider.validate_config(basic_config)
        assert isinstance(validation, ValidationResult)

        # Create test changeset
        changes = ChangeSet(
            base_ref="main",
            head_ref="HEAD",
            changes=[
                Change("src/test.py", ChangeType.MODIFIED, additions=10, deletions=5),
            ],
            repository_root=temp_project,
        )

        # Test generate_tests
        # Note: We need to set project_url for mock provider validation
        config_with_url = E2EConfig(
            provider_name="mock",
            project_root=temp_project,
            api_key="test-key",
            project_url="http://localhost:3000",
        )
        result = provider.generate_tests(changes, config_with_url)
        assert isinstance(result, GenerationResult)
        assert result.run_id is not None

        # Test get_status
        status = provider.get_status(result.run_id)
        assert isinstance(status, StatusResult)

        # Test download_artifacts (only if completed)
        if status.status == GenerationStatus.COMPLETED:
            output_dir = temp_project / "output"
            output_dir.mkdir()
            artifacts = provider.download_artifacts(result.run_id, output_dir)
            assert isinstance(artifacts, ArtifactResult)


# ============================================================================
# Edge Cases and Error Handling
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_create_provider_with_extra_config(self, factory: E2EProviderFactory, temp_project: Path):
        """Should pass extra config to factory function."""
        config = E2EConfig(
            provider_name="mock",
            project_root=temp_project,
            extra={"simulate_delay": True},
        )
        provider = factory.create_provider(config)
        # Mock provider should have simulate_delay=True
        assert hasattr(provider, "simulate_delay")
        assert provider.simulate_delay is True

    def test_conflicting_class_and_factory_registration(self, empty_factory: E2EProviderFactory):
        """Should raise when registering factory over class without override."""
        empty_factory.register_provider_class("custom", MockCustomProvider)

        def create_provider(config: E2EConfig) -> E2EProvider:
            return MockCustomProvider("", "")

        with pytest.raises(ValueError, match="already registered"):
            empty_factory.register_factory("custom", create_provider)

    def test_factory_prefers_factory_over_class(self, empty_factory: E2EProviderFactory, temp_project: Path):
        """When both factory and class are registered, factory should be used."""
        # This shouldn't happen normally due to validation, but test the priority

        # First register as factory
        called_factory = {"called": False}

        def create_provider(config: E2EConfig) -> E2EProvider:
            called_factory["called"] = True
            return MockCustomProvider("factory", "url")

        empty_factory.register_factory("custom", create_provider)

        # Create provider
        config = E2EConfig(provider_name="custom", project_root=temp_project)
        provider = empty_factory.create_provider(config)

        assert called_factory["called"]
        assert provider.api_key == "factory"
