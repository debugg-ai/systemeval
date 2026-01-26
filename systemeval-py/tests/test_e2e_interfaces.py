"""
Tests for E2E provider interfaces.

This test suite validates:
1. Type definitions and validation
2. Protocol implementations
3. Registry functionality
4. Example implementations
5. Module initialization pattern
"""

import tempfile
from pathlib import Path

import pytest

from systemeval.e2e import (
    ArtifactResult,
    BasicE2EOrchestrator,
    Change,
    ChangeSet,
    ChangeType,
    CompletionResult,
    E2EConfig,
    E2ENotInitializedError,
    E2EProviderRegistry,
    E2EResult,
    GenerationResult,
    GenerationStatus,
    MockE2EProvider,
    StatusResult,
    ValidationResult,
    get_config,
    get_provider,
    initialize,
    is_initialized,
    is_registered,
    list_providers,
    register_provider,
    require_initialized,
    reset,
)


# ============================================================================
# Type Tests
# ============================================================================


class TestChange:
    """Test Change dataclass."""

    def test_basic_change(self):
        change = Change(
            file_path="src/api/users.py",
            change_type=ChangeType.MODIFIED,
            additions=10,
            deletions=5,
        )

        assert change.file_path == "src/api/users.py"
        assert change.change_type == ChangeType.MODIFIED
        assert change.additions == 10
        assert change.deletions == 5

    def test_renamed_change(self):
        change = Change(
            file_path="src/api/users_v2.py",
            change_type=ChangeType.RENAMED,
            old_path="src/api/users.py",
        )

        assert change.old_path == "src/api/users.py"
        assert change.change_type == ChangeType.RENAMED

    def test_renamed_requires_old_path(self):
        with pytest.raises(ValueError, match="old_path is required"):
            Change(
                file_path="src/api/users.py",
                change_type=ChangeType.RENAMED,
            )

    def test_negative_additions_rejected(self):
        with pytest.raises(ValueError, match="non-negative"):
            Change(
                file_path="src/api/users.py",
                change_type=ChangeType.MODIFIED,
                additions=-5,
            )

    def test_to_dict(self):
        change = Change(
            file_path="src/api/users.py",
            change_type=ChangeType.ADDED,
            additions=100,
        )

        d = change.to_dict()
        assert d["file_path"] == "src/api/users.py"
        assert d["change_type"] == "added"
        assert d["additions"] == 100


class TestChangeSet:
    """Test ChangeSet dataclass."""

    def test_basic_changeset(self, tmp_path):
        changes = [
            Change("file1.py", ChangeType.ADDED, additions=10),
            Change("file2.py", ChangeType.MODIFIED, additions=5, deletions=3),
        ]

        changeset = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=changes,
            repository_root=tmp_path,
        )

        assert changeset.base_ref == "main"
        assert changeset.head_ref == "feature"
        assert len(changeset.changes) == 2
        assert changeset.repository_root == tmp_path

    def test_requires_absolute_path(self):
        with pytest.raises(ValueError, match="absolute path"):
            ChangeSet(
                base_ref="main",
                head_ref="feature",
                changes=[],
                repository_root=Path("relative/path"),
            )

    def test_total_changes(self, tmp_path):
        changes = [
            Change("file1.py", ChangeType.ADDED, additions=10),
            Change("file2.py", ChangeType.MODIFIED, additions=5, deletions=3),
        ]

        changeset = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=changes,
            repository_root=tmp_path,
        )

        assert changeset.total_changes == 2
        assert changeset.total_additions == 15
        assert changeset.total_deletions == 3

    def test_get_changes_by_type(self, tmp_path):
        changes = [
            Change("file1.py", ChangeType.ADDED, additions=10),
            Change("file2.py", ChangeType.MODIFIED, additions=5),
            Change("file3.py", ChangeType.ADDED, additions=20),
        ]

        changeset = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=changes,
            repository_root=tmp_path,
        )

        added = changeset.get_changes_by_type(ChangeType.ADDED)
        assert len(added) == 2
        assert all(c.change_type == ChangeType.ADDED for c in added)


class TestE2EConfig:
    """Test E2EConfig dataclass."""

    def test_basic_config(self, tmp_path):
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        assert config.provider_name == "test"
        assert config.project_root == tmp_path
        assert config.project_url == "http://localhost:3000"

    def test_requires_absolute_path(self):
        with pytest.raises(ValueError, match="absolute path"):
            E2EConfig(
                provider_name="test",
                project_root=Path("relative/path"),
            )

    def test_default_output_directory(self, tmp_path):
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
        )

        assert config.output_directory == tmp_path / "e2e_generated"

    def test_relative_output_directory_resolved(self, tmp_path):
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            output_directory=Path("tests/e2e"),
        )

        assert config.output_directory == tmp_path / "tests/e2e"
        assert config.output_directory.is_absolute()

    def test_timeout_validation(self, tmp_path):
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            E2EConfig(
                provider_name="test",
                project_root=tmp_path,
                timeout_seconds=-1,
            )

    def test_max_tests_validation(self, tmp_path):
        with pytest.raises(ValueError, match="max_tests must be positive"):
            E2EConfig(
                provider_name="test",
                project_root=tmp_path,
                max_tests=0,
            )

    def test_with_extra(self, tmp_path):
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            extra={"key1": "value1"},
        )

        new_config = config.with_extra(key2="value2")

        assert new_config.extra["key1"] == "value1"
        assert new_config.extra["key2"] == "value2"
        assert config.extra == {"key1": "value1"}  # Original unchanged

    def test_to_dict_redacts_api_key(self, tmp_path):
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            api_key="sk-secret-key-12345",
        )

        d = config.to_dict()
        assert d["api_key"] == "***"


class TestResultTypes:
    """Test result dataclasses."""

    def test_validation_result(self):
        result = ValidationResult(
            valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"],
        )

        assert not result.valid
        assert len(result.errors) == 2
        assert len(result.warnings) == 1

    def test_generation_result(self):
        result = GenerationResult(
            run_id="run-123",
            status=GenerationStatus.IN_PROGRESS,
            message="Generation started",
        )

        assert result.run_id == "run-123"
        assert result.status == GenerationStatus.IN_PROGRESS

    def test_status_result(self):
        result = StatusResult(
            run_id="run-123",
            status=GenerationStatus.IN_PROGRESS,
            progress_percent=50.0,
            tests_generated=5,
        )

        assert result.progress_percent == 50.0
        assert result.tests_generated == 5

    def test_completion_result(self):
        result = CompletionResult(
            run_id="run-123",
            status=GenerationStatus.COMPLETED,
            completed=True,
            timed_out=False,
            duration_seconds=45.5,
        )

        assert result.completed
        assert not result.timed_out
        assert result.duration_seconds == 45.5


# ============================================================================
# Registry Tests
# ============================================================================


class TestE2EProviderRegistry:
    """Test provider registry."""

    def test_register_and_get(self):
        registry = E2EProviderRegistry()
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        registry.register("mock", provider)
        retrieved = registry.get("mock")

        assert retrieved is provider

    def test_register_duplicate_raises(self):
        registry = E2EProviderRegistry()
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        registry.register("mock", provider)

        with pytest.raises(ValueError, match="already registered"):
            registry.register("mock", provider)

    def test_get_nonexistent_raises(self):
        registry = E2EProviderRegistry()

        with pytest.raises(KeyError, match="Provider 'nonexistent' not found"):
            registry.get("nonexistent")

    def test_list_providers(self):
        registry = E2EProviderRegistry()
        provider1 = MockE2EProvider(api_key="test", api_base_url="http://test")
        provider2 = MockE2EProvider(api_key="test", api_base_url="http://test")

        registry.register("mock1", provider1)
        registry.register("mock2", provider2)

        providers = registry.list_providers()
        assert providers == ["mock1", "mock2"]  # Sorted

    def test_is_registered(self):
        registry = E2EProviderRegistry()
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        assert not registry.is_registered("mock")
        registry.register("mock", provider)
        assert registry.is_registered("mock")

    def test_unregister(self):
        registry = E2EProviderRegistry()
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        registry.register("mock", provider)
        assert registry.is_registered("mock")

        registry.unregister("mock")
        assert not registry.is_registered("mock")

    def test_clear(self):
        registry = E2EProviderRegistry()
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        registry.register("mock", provider)
        assert len(registry.list_providers()) == 1

        registry.clear()
        assert len(registry.list_providers()) == 0


class TestGlobalRegistry:
    """Test global registry functions."""

    def setup_method(self):
        """Clear global registry and reset initialization before each test."""
        # Access global registry and clear it
        from systemeval.e2e.registry import _get_global_registry
        registry = _get_global_registry()
        registry.clear()
        # Reset initialization state
        reset()

    def test_register_and_get_provider(self, tmp_path):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")
        register_provider("test", provider)

        # Initialize before getting provider
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )
        initialize(config)

        retrieved = get_provider("test")
        assert retrieved is provider

    def test_list_providers(self):
        provider1 = MockE2EProvider(api_key="test", api_base_url="http://test")
        provider2 = MockE2EProvider(api_key="test", api_base_url="http://test")

        register_provider("test1", provider1)
        register_provider("test2", provider2)

        providers = list_providers()
        assert "test1" in providers
        assert "test2" in providers

    def test_is_registered(self):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        assert not is_registered("test")
        register_provider("test", provider)
        assert is_registered("test")


# ============================================================================
# Module Initialization Tests
# ============================================================================


class TestModuleInitialization:
    """Test E2E module initialization pattern."""

    def setup_method(self):
        """Reset initialization state before each test."""
        reset()

    def teardown_method(self):
        """Reset initialization state after each test."""
        reset()

    def test_is_initialized_false_by_default(self):
        """Test module is not initialized by default."""
        assert not is_initialized()

    def test_initialize_with_valid_config(self, tmp_path):
        """Test initialize() with valid config."""
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        initialize(config)

        assert is_initialized()

    def test_initialize_raises_on_invalid_type(self):
        """Test initialize() raises TypeError for non-E2EConfig."""
        with pytest.raises(TypeError, match="must be an E2EConfig instance"):
            initialize({"provider": "test"})  # type: ignore

    def test_initialize_raises_on_empty_provider(self, tmp_path):
        """Test initialize() raises ValueError for empty provider."""
        # Create config with valid provider_name, then manually clear it
        # to test the initialize() validation (bypassing dataclass validation)
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
        )
        # Use object.__setattr__ to bypass frozen dataclass protection if any
        # Note: E2EConfig is not frozen, so direct assignment works
        object.__setattr__(config, "provider_name", "")

        with pytest.raises(ValueError, match="provider_name cannot be empty"):
            initialize(config)

    def test_get_config_returns_config_after_init(self, tmp_path):
        """Test get_config() returns config after initialization."""
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        initialize(config)

        retrieved = get_config()
        assert retrieved is config

    def test_get_config_raises_when_not_initialized(self):
        """Test get_config() raises E2ENotInitializedError when not initialized."""
        with pytest.raises(E2ENotInitializedError, match="not initialized"):
            get_config()

    def test_require_initialized_passes_when_initialized(self, tmp_path):
        """Test require_initialized() passes when initialized."""
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
        )
        initialize(config)

        # Should not raise
        require_initialized()

    def test_require_initialized_raises_when_not_initialized(self):
        """Test require_initialized() raises E2ENotInitializedError when not initialized."""
        with pytest.raises(E2ENotInitializedError, match="not initialized"):
            require_initialized()

    def test_require_initialized_includes_operation(self):
        """Test require_initialized() includes operation in error message."""
        with pytest.raises(E2ENotInitializedError, match="Cannot do something"):
            require_initialized("do something")

    def test_get_provider_requires_initialization(self):
        """Test get_provider() raises when not initialized."""
        # Register a provider first
        from systemeval.e2e.registry import _get_global_registry
        registry = _get_global_registry()
        registry.clear()

        provider = MockE2EProvider(api_key="test", api_base_url="http://test")
        register_provider("test", provider)

        # Try to get without initialization
        with pytest.raises(E2ENotInitializedError, match="not initialized"):
            get_provider("test")

    def test_get_provider_works_after_initialization(self, tmp_path):
        """Test get_provider() works after initialization."""
        # Register a provider first
        from systemeval.e2e.registry import _get_global_registry
        registry = _get_global_registry()
        registry.clear()

        provider = MockE2EProvider(api_key="test", api_base_url="http://test")
        register_provider("test", provider)

        # Initialize
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
        )
        initialize(config)

        # Should work now
        retrieved = get_provider("test")
        assert retrieved is provider

    def test_reset_clears_initialization_state(self, tmp_path):
        """Test reset() clears initialization state."""
        config = E2EConfig(
            provider_name="test",
            project_root=tmp_path,
        )
        initialize(config)
        assert is_initialized()

        reset()

        assert not is_initialized()

    def test_e2e_not_initialized_error_message(self):
        """Test E2ENotInitializedError has helpful message."""
        error = E2ENotInitializedError("get provider")
        assert "Cannot get provider" in str(error)
        assert "initialize(config)" in str(error)


# ============================================================================
# Provider Implementation Tests
# ============================================================================


class TestMockE2EProvider:
    """Test mock provider implementation."""

    def test_initialization(self):
        provider = MockE2EProvider(
            api_key="test-key",
            api_base_url="http://test.com",
        )

        assert provider.api_key == "test-key"
        assert provider.api_base_url == "http://test.com"

    def test_requires_api_key(self):
        with pytest.raises(ValueError, match="api_key is required"):
            MockE2EProvider(api_key="", api_base_url="http://test.com")

    def test_requires_api_base_url(self):
        with pytest.raises(ValueError, match="api_base_url is required"):
            MockE2EProvider(api_key="test", api_base_url="")

    def test_validate_config(self, tmp_path):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        result = provider.validate_config(config)
        assert result.valid

    def test_validate_config_missing_url(self, tmp_path):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            # Missing project_url
        )

        result = provider.validate_config(config)
        assert not result.valid
        assert "project_url is required" in result.errors

    def test_validate_config_unsupported_framework(self, tmp_path):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
            test_framework="unsupported",
        )

        result = provider.validate_config(config)
        assert not result.valid
        assert "Unsupported test_framework" in result.errors[0]

    def test_generate_tests(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        result = provider.generate_tests(changes, config)

        assert result.run_id.startswith("mock-")
        assert result.status == GenerationStatus.IN_PROGRESS

    def test_get_status(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        generation = provider.generate_tests(changes, config)
        status = provider.get_status(generation.run_id)

        # Should be completed immediately (simulate_delay=False)
        assert status.status == GenerationStatus.COMPLETED
        assert status.tests_generated > 0

    def test_get_status_unknown_run(self):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")

        with pytest.raises(KeyError, match="not found"):
            provider.get_status("unknown-run-id")

    def test_download_artifacts(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[
                Change("file1.py", ChangeType.ADDED, additions=10),
                Change("file2.py", ChangeType.MODIFIED, additions=5),
            ],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        generation = provider.generate_tests(changes, config)

        # Check status to trigger completion (simulate_delay=False means instant)
        status = provider.get_status(generation.run_id)
        assert status.status == GenerationStatus.COMPLETED

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        artifacts = provider.download_artifacts(generation.run_id, output_dir)

        assert len(artifacts.test_files) == 2
        assert all(f.exists() for f in artifacts.test_files)
        assert artifacts.total_tests > 0

    def test_download_artifacts_not_completed(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=True,  # Won't complete immediately
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        generation = provider.generate_tests(changes, config)

        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(ValueError, match="Cannot download artifacts"):
            provider.download_artifacts(generation.run_id, output_dir)


# ============================================================================
# Orchestrator Tests
# ============================================================================


class TestBasicE2EOrchestrator:
    """Test basic orchestrator implementation."""

    def test_initialization(self):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")
        orchestrator = BasicE2EOrchestrator(provider, poll_interval=2)

        assert orchestrator.provider is provider
        assert orchestrator.poll_interval == 2

    def test_run_e2e_flow_success(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )
        orchestrator = BasicE2EOrchestrator(provider)

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
            output_directory=tmp_path / "output",
        )
        config.output_directory.mkdir()

        result = orchestrator.run_e2e_flow(changes, config)

        assert result.success
        assert result.artifacts is not None
        assert len(result.artifacts.test_files) > 0
        assert result.error is None

    def test_run_e2e_flow_validation_failure(self, tmp_path):
        provider = MockE2EProvider(api_key="test", api_base_url="http://test")
        orchestrator = BasicE2EOrchestrator(provider)

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            # Missing project_url - will fail validation
        )

        result = orchestrator.run_e2e_flow(changes, config)

        assert not result.success
        assert result.error is not None
        assert "validation failed" in result.error.lower()

    def test_await_completion_success(self, tmp_path):
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )
        orchestrator = BasicE2EOrchestrator(provider)

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        generation = provider.generate_tests(changes, config)
        completion = orchestrator.await_completion(generation.run_id, timeout=10)

        assert completion.completed
        assert not completion.timed_out
        assert completion.status == GenerationStatus.COMPLETED


# ============================================================================
# Integration Tests
# ============================================================================


class TestE2EIntegration:
    """End-to-end integration tests."""

    def test_complete_workflow(self, tmp_path):
        """Test complete E2E workflow from provider to artifacts."""
        # 1. Create provider
        provider = MockE2EProvider(
            api_key="test-key",
            api_base_url="http://test.com",
            simulate_delay=False,
        )

        # 2. Create orchestrator
        orchestrator = BasicE2EOrchestrator(provider)

        # 3. Create changeset
        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[
                Change("src/api/users.py", ChangeType.MODIFIED, additions=20, deletions=5),
                Change("src/api/auth.py", ChangeType.ADDED, additions=50),
            ],
            repository_root=tmp_path,
        )

        # 4. Create config
        output_dir = tmp_path / "e2e_tests"
        output_dir.mkdir()

        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
            project_slug="test-project",
            test_framework="playwright",
            programming_language="typescript",
            output_directory=output_dir,
            timeout_seconds=60,
        )

        # 5. Run E2E flow
        result = orchestrator.run_e2e_flow(changes, config)

        # 6. Validate results
        assert result.success
        assert result.changeset == changes
        assert result.config == config
        assert result.generation.run_id
        assert result.completion.completed
        assert not result.completion.timed_out
        assert result.artifacts is not None
        assert len(result.artifacts.test_files) == 2
        assert all(f.exists() for f in result.artifacts.test_files)

        # 7. Validate generated test content
        for test_file in result.artifacts.test_files:
            content = test_file.read_text()
            assert "describe" in content
            assert "it(" in content
            assert "expect" in content

    def test_registry_integration(self, tmp_path):
        """Test using provider through registry."""
        # Clear registry and reset initialization
        from systemeval.e2e.registry import _get_global_registry
        registry = _get_global_registry()
        registry.clear()
        reset()

        # Register provider
        provider = MockE2EProvider(
            api_key="test",
            api_base_url="http://test",
            simulate_delay=False,
        )
        register_provider("mock", provider)

        # Create config
        config = E2EConfig(
            provider_name="mock",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        # Initialize before getting provider
        initialize(config)

        # Get from registry
        retrieved = get_provider("mock")

        # Use provider
        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        result = retrieved.generate_tests(changes, config)
        assert result.run_id
