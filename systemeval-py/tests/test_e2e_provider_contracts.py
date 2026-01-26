"""
Contract tests for E2E Provider protocol.

These tests ensure that all E2EProvider implementations follow the interface
contract correctly. The same tests run against multiple implementations
(MockE2EProvider, DebuggAIProvider with mocked API) to verify consistent
behavior across providers.

Contract testing validates:
1. Required methods exist and have correct signatures
2. Return types match protocol specifications
3. Edge cases are handled consistently
4. Error conditions raise expected exceptions
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable, Type
from unittest.mock import patch, MagicMock

import pytest

from systemeval.e2e import (
    ArtifactResult,
    Change,
    ChangeSet,
    ChangeType,
    E2EConfig,
    GenerationResult,
    GenerationStatus,
    MockE2EProvider,
    StatusResult,
    ValidationResult,
)
from systemeval.e2e.providers.debuggai import DebuggAIProvider
from systemeval.e2e.protocols import E2EProvider


# ============================================================================
# Test Fixtures
# ============================================================================


@pytest.fixture
def sample_changes(tmp_path: Path) -> ChangeSet:
    """Create a sample ChangeSet for testing."""
    return ChangeSet(
        base_ref="main",
        head_ref="feature-branch",
        changes=[
            Change("src/api/users.py", ChangeType.MODIFIED, additions=10, deletions=5),
            Change("src/api/auth.py", ChangeType.ADDED, additions=50),
        ],
        repository_root=tmp_path,
    )


@pytest.fixture
def sample_config(tmp_path: Path) -> E2EConfig:
    """Create a sample E2EConfig for testing."""
    return E2EConfig(
        provider_name="test",
        project_root=tmp_path,
        project_url="http://localhost:3000",
        project_slug="test-project",
        test_framework="playwright",
        programming_language="typescript",
    )


@pytest.fixture
def invalid_config_missing_url(tmp_path: Path) -> E2EConfig:
    """Create an E2EConfig missing required project_url."""
    return E2EConfig(
        provider_name="test",
        project_root=tmp_path,
        # Missing project_url
    )


@pytest.fixture
def invalid_config_bad_framework(tmp_path: Path) -> E2EConfig:
    """Create an E2EConfig with unsupported test framework."""
    return E2EConfig(
        provider_name="test",
        project_root=tmp_path,
        project_url="http://localhost:3000",
        test_framework="unsupported_framework",
    )


# ============================================================================
# Provider Factory Fixtures
# ============================================================================


class ProviderFactory(ABC):
    """Abstract factory for creating E2EProvider instances for testing."""

    @abstractmethod
    def create_provider(self) -> E2EProvider:
        """Create a new provider instance."""
        ...

    @abstractmethod
    def setup_generation_success(self, provider: E2EProvider) -> None:
        """Configure provider to succeed on generate_tests call."""
        ...

    @abstractmethod
    def setup_status_completed(self, provider: E2EProvider, run_id: str) -> None:
        """Configure provider to return COMPLETED status for given run_id."""
        ...

    @abstractmethod
    def setup_download_success(self, provider: E2EProvider, run_id: str) -> None:
        """Configure provider to succeed on download_artifacts call."""
        ...


class MockProviderFactory(ProviderFactory):
    """Factory for MockE2EProvider."""

    def create_provider(self) -> MockE2EProvider:
        return MockE2EProvider(
            api_key="test-api-key",
            api_base_url="http://test.example.com",
            simulate_delay=False,  # Instant completion for tests
        )

    def setup_generation_success(self, provider: E2EProvider) -> None:
        # MockE2EProvider handles this internally
        pass

    def setup_status_completed(self, provider: E2EProvider, run_id: str) -> None:
        # MockE2EProvider with simulate_delay=False returns completed immediately
        pass

    def setup_download_success(self, provider: E2EProvider, run_id: str) -> None:
        # MockE2EProvider handles this internally
        pass


class DebuggAIProviderFactory(ProviderFactory):
    """Factory for DebuggAIProvider with mocked API calls."""

    def __init__(self):
        self._patches = []
        self._mock_request = None

    def create_provider(self) -> DebuggAIProvider:
        provider = DebuggAIProvider(
            api_key="sk_test_123",
            api_base_url="https://api.debugg.ai",
        )
        return provider

    def setup_generation_success(self, provider: E2EProvider) -> None:
        # Patching is done per-test via context manager
        pass

    def setup_status_completed(self, provider: E2EProvider, run_id: str) -> None:
        # Patching is done per-test via context manager
        pass

    def setup_download_success(self, provider: E2EProvider, run_id: str) -> None:
        # Patching is done per-test via context manager
        pass


@pytest.fixture(params=["mock", "debuggai"])
def provider_factory(request) -> ProviderFactory:
    """Parameterized fixture that provides factory for each provider type."""
    if request.param == "mock":
        return MockProviderFactory()
    elif request.param == "debuggai":
        return DebuggAIProviderFactory()
    else:
        raise ValueError(f"Unknown provider type: {request.param}")


@pytest.fixture
def provider(provider_factory: ProviderFactory) -> E2EProvider:
    """Create a provider instance using the parameterized factory."""
    return provider_factory.create_provider()


# ============================================================================
# Protocol Conformance Tests
# ============================================================================


class TestE2EProviderProtocolConformance:
    """Test that providers implement the E2EProvider protocol correctly."""

    def test_provider_is_e2e_provider_instance(self, provider: E2EProvider):
        """Test that provider is an instance of E2EProvider protocol."""
        assert isinstance(provider, E2EProvider)

    def test_has_generate_tests_method(self, provider: E2EProvider):
        """Test that provider has generate_tests method."""
        assert hasattr(provider, "generate_tests")
        assert callable(provider.generate_tests)

    def test_has_get_status_method(self, provider: E2EProvider):
        """Test that provider has get_status method."""
        assert hasattr(provider, "get_status")
        assert callable(provider.get_status)

    def test_has_download_artifacts_method(self, provider: E2EProvider):
        """Test that provider has download_artifacts method."""
        assert hasattr(provider, "download_artifacts")
        assert callable(provider.download_artifacts)

    def test_has_validate_config_method(self, provider: E2EProvider):
        """Test that provider has validate_config method."""
        assert hasattr(provider, "validate_config")
        assert callable(provider.validate_config)


# ============================================================================
# generate_tests Contract Tests
# ============================================================================


class TestGenerateTestsContract:
    """Contract tests for generate_tests method."""

    def test_generate_tests_returns_generation_result(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that generate_tests returns a GenerationResult."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(sample_changes, sample_config)
        else:
            result = provider.generate_tests(sample_changes, sample_config)

        assert isinstance(result, GenerationResult)

    def test_generate_tests_has_valid_run_id(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that GenerationResult has a non-empty run_id."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(sample_changes, sample_config)
        else:
            result = provider.generate_tests(sample_changes, sample_config)

        assert result.run_id is not None
        assert len(result.run_id) > 0
        assert isinstance(result.run_id, str)

    def test_generate_tests_has_valid_status(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that GenerationResult has a valid GenerationStatus."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(sample_changes, sample_config)
        else:
            result = provider.generate_tests(sample_changes, sample_config)

        assert isinstance(result.status, GenerationStatus)
        # Initial status should be IN_PROGRESS or PENDING (not COMPLETED yet)
        assert result.status in (
            GenerationStatus.PENDING,
            GenerationStatus.IN_PROGRESS,
            GenerationStatus.FAILED,  # Could fail immediately on API error
        )

    def test_generate_tests_has_started_at_timestamp(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that GenerationResult has a started_at timestamp."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(sample_changes, sample_config)
        else:
            result = provider.generate_tests(sample_changes, sample_config)

        assert result.started_at is not None
        assert isinstance(result.started_at, str)
        # Should be an ISO format timestamp
        assert "T" in result.started_at or "-" in result.started_at

    def test_generate_tests_result_serializable(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that GenerationResult can be serialized to dict."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(sample_changes, sample_config)
        else:
            result = provider.generate_tests(sample_changes, sample_config)

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "run_id" in result_dict
        assert "status" in result_dict


# ============================================================================
# get_status Contract Tests
# ============================================================================


class TestGetStatusContract:
    """Contract tests for get_status method."""

    def test_get_status_returns_status_result(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that get_status returns a StatusResult."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "suite": {
                        "status": "running",
                        "tests": [],
                    }
                }
                status = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(gen_result.run_id)

        assert isinstance(status, StatusResult)

    def test_get_status_has_run_id(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that StatusResult has the correct run_id."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "suite": {
                        "status": "running",
                        "tests": [],
                    }
                }
                status = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(gen_result.run_id)

        assert status.run_id == gen_result.run_id

    def test_get_status_has_valid_status(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that StatusResult has a valid GenerationStatus."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "suite": {
                        "status": "completed",
                        "tests": [{"curRun": {"status": "completed"}}],
                    }
                }
                status = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(gen_result.run_id)

        assert isinstance(status.status, GenerationStatus)

    def test_get_status_unknown_run_raises_key_error(self, provider: E2EProvider):
        """Test that get_status raises KeyError for unknown run_id."""
        with pytest.raises(KeyError, match="not found"):
            provider.get_status("unknown-run-id-12345")

    def test_get_status_tests_generated_is_non_negative(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that tests_generated is a non-negative integer."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "suite": {
                        "status": "running",
                        "tests": [{"curRun": {"status": "running"}}],
                    }
                }
                status = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(gen_result.run_id)

        assert isinstance(status.tests_generated, int)
        assert status.tests_generated >= 0

    def test_get_status_result_serializable(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that StatusResult can be serialized to dict."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "suite": {
                        "status": "running",
                        "tests": [],
                    }
                }
                status = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(gen_result.run_id)

        status_dict = status.to_dict()
        assert isinstance(status_dict, dict)
        assert "run_id" in status_dict
        assert "status" in status_dict


# ============================================================================
# download_artifacts Contract Tests
# ============================================================================


class TestDownloadArtifactsContract:
    """Contract tests for download_artifacts method."""

    def test_download_artifacts_returns_artifact_result(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test that download_artifacts returns an ArtifactResult."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            # Mark run as completed with suite data
            run = provider._runs[gen_result.run_id]
            run.status = GenerationStatus.COMPLETED
            run.suite_data = {
                "tests": [
                    {
                        "name": "test-1",
                        "uuid": "test-uuid-1",
                        "curRun": {
                            "status": "completed",
                            "runScript": "https://api.debugg.ai/artifacts/script.js",
                        },
                    }
                ]
            }

            with patch.object(provider, "_download_file") as mock_download:
                mock_download.return_value = True
                artifacts = provider.download_artifacts(gen_result.run_id, output_dir)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            # MockE2EProvider with simulate_delay=False completes immediately
            provider.get_status(gen_result.run_id)  # Trigger completion
            artifacts = provider.download_artifacts(gen_result.run_id, output_dir)

        assert isinstance(artifacts, ArtifactResult)

    def test_download_artifacts_has_run_id(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test that ArtifactResult has the correct run_id."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            run = provider._runs[gen_result.run_id]
            run.status = GenerationStatus.COMPLETED
            run.suite_data = {"tests": []}

            with patch.object(provider, "_download_file"):
                artifacts = provider.download_artifacts(gen_result.run_id, output_dir)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            provider.get_status(gen_result.run_id)
            artifacts = provider.download_artifacts(gen_result.run_id, output_dir)

        assert artifacts.run_id == gen_result.run_id

    def test_download_artifacts_requires_completed_run(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test that download_artifacts raises ValueError for non-completed run."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)
            # Run status is IN_PROGRESS by default

            with pytest.raises(ValueError, match="not completed"):
                provider.download_artifacts(gen_result.run_id, output_dir)
        else:
            # For MockE2EProvider with simulate_delay=True
            provider_delay = MockE2EProvider(
                api_key="test-api-key",
                api_base_url="http://test.example.com",
                simulate_delay=True,  # Will not complete immediately
            )
            gen_result = provider_delay.generate_tests(sample_changes, sample_config)

            with pytest.raises(ValueError, match="Cannot download artifacts"):
                provider_delay.download_artifacts(gen_result.run_id, output_dir)

    def test_download_artifacts_unknown_run_raises_key_error(
        self,
        provider: E2EProvider,
        tmp_path: Path,
    ):
        """Test that download_artifacts raises KeyError for unknown run_id."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        with pytest.raises(KeyError, match="not found"):
            provider.download_artifacts("unknown-run-id-12345", output_dir)

    def test_download_artifacts_has_output_directory(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test that ArtifactResult has the correct output_directory."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            run = provider._runs[gen_result.run_id]
            run.status = GenerationStatus.COMPLETED
            run.suite_data = {"tests": []}

            with patch.object(provider, "_download_file"):
                artifacts = provider.download_artifacts(gen_result.run_id, output_dir)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            provider.get_status(gen_result.run_id)
            artifacts = provider.download_artifacts(gen_result.run_id, output_dir)

        assert artifacts.output_directory == output_dir

    def test_download_artifacts_result_serializable(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test that ArtifactResult can be serialized to dict."""
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            run = provider._runs[gen_result.run_id]
            run.status = GenerationStatus.COMPLETED
            run.suite_data = {"tests": []}

            with patch.object(provider, "_download_file"):
                artifacts = provider.download_artifacts(gen_result.run_id, output_dir)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            provider.get_status(gen_result.run_id)
            artifacts = provider.download_artifacts(gen_result.run_id, output_dir)

        artifacts_dict = artifacts.to_dict()
        assert isinstance(artifacts_dict, dict)
        assert "run_id" in artifacts_dict
        assert "output_directory" in artifacts_dict


# ============================================================================
# validate_config Contract Tests
# ============================================================================


class TestValidateConfigContract:
    """Contract tests for validate_config method."""

    def test_validate_config_returns_validation_result(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that validate_config returns a ValidationResult."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(sample_config)
        else:
            result = provider.validate_config(sample_config)

        assert isinstance(result, ValidationResult)

    def test_validate_config_valid_has_true_valid_flag(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that valid config produces valid=True."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(sample_config)
        else:
            result = provider.validate_config(sample_config)

        assert result.valid is True
        assert isinstance(result.valid, bool)

    def test_validate_config_invalid_has_false_valid_flag(
        self,
        provider: E2EProvider,
        invalid_config_missing_url: E2EConfig,
    ):
        """Test that invalid config produces valid=False."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(invalid_config_missing_url)
        else:
            result = provider.validate_config(invalid_config_missing_url)

        assert result.valid is False
        assert isinstance(result.valid, bool)

    def test_validate_config_invalid_has_errors(
        self,
        provider: E2EProvider,
        invalid_config_missing_url: E2EConfig,
    ):
        """Test that invalid config produces non-empty errors list."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(invalid_config_missing_url)
        else:
            result = provider.validate_config(invalid_config_missing_url)

        assert len(result.errors) > 0
        assert all(isinstance(e, str) for e in result.errors)

    def test_validate_config_errors_is_list(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that errors is always a list."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(sample_config)
        else:
            result = provider.validate_config(sample_config)

        assert isinstance(result.errors, list)

    def test_validate_config_warnings_is_list(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that warnings is always a list."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(sample_config)
        else:
            result = provider.validate_config(sample_config)

        assert isinstance(result.warnings, list)

    def test_validate_config_unsupported_framework_produces_feedback(
        self,
        provider: E2EProvider,
        invalid_config_bad_framework: E2EConfig,
    ):
        """Test that unsupported framework produces error or warning."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(invalid_config_bad_framework)
        else:
            result = provider.validate_config(invalid_config_bad_framework)

        # Either an error or a warning should mention the framework
        has_framework_feedback = (
            any("unsupported" in e.lower() or "framework" in e.lower() for e in result.errors) or
            any("unsupported" in w.lower() or "framework" in w.lower() or "supported" in w.lower() for w in result.warnings)
        )
        assert has_framework_feedback

    def test_validate_config_result_serializable(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that ValidationResult can be serialized to dict."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result = provider.validate_config(sample_config)
        else:
            result = provider.validate_config(sample_config)

        result_dict = result.to_dict()
        assert isinstance(result_dict, dict)
        assert "valid" in result_dict
        assert "errors" in result_dict
        assert "warnings" in result_dict


# ============================================================================
# Edge Case Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases that should be handled consistently across providers."""

    def test_empty_changeset(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test handling of empty changeset."""
        empty_changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[],  # No changes
            repository_root=tmp_path,
        )

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(empty_changes, sample_config)
        else:
            result = provider.generate_tests(empty_changes, sample_config)

        # Should still return a valid result
        assert isinstance(result, GenerationResult)
        assert result.run_id is not None

    def test_large_changeset(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test handling of large changeset."""
        many_changes = [
            Change(f"src/file_{i}.py", ChangeType.MODIFIED, additions=10, deletions=5)
            for i in range(100)
        ]
        large_changeset = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=many_changes,
            repository_root=tmp_path,
        )

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(large_changeset, sample_config)
        else:
            result = provider.generate_tests(large_changeset, sample_config)

        # Should still return a valid result
        assert isinstance(result, GenerationResult)
        assert result.run_id is not None

    def test_special_characters_in_file_path(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
        tmp_path: Path,
    ):
        """Test handling of special characters in file paths."""
        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[
                Change("src/file with spaces.py", ChangeType.ADDED, additions=10),
                Change("src/file-with-dashes.py", ChangeType.MODIFIED, additions=5),
                Change("src/file_with_underscores.py", ChangeType.DELETED, additions=0, deletions=20),
            ],
            repository_root=tmp_path,
        )

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                result = provider.generate_tests(changes, sample_config)
        else:
            result = provider.generate_tests(changes, sample_config)

        # Should still return a valid result
        assert isinstance(result, GenerationResult)
        assert result.run_id is not None


# ============================================================================
# Idempotency Tests
# ============================================================================


class TestIdempotency:
    """Test that repeated calls behave consistently."""

    def test_multiple_validate_config_calls_consistent(
        self,
        provider: E2EProvider,
        sample_config: E2EConfig,
    ):
        """Test that multiple validate_config calls return consistent results."""
        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {"status": "ok"}
                result1 = provider.validate_config(sample_config)
                result2 = provider.validate_config(sample_config)
        else:
            result1 = provider.validate_config(sample_config)
            result2 = provider.validate_config(sample_config)

        assert result1.valid == result2.valid
        assert result1.errors == result2.errors

    def test_get_status_idempotent_for_completed_run(
        self,
        provider: E2EProvider,
        provider_factory: ProviderFactory,
        sample_changes: ChangeSet,
        sample_config: E2EConfig,
    ):
        """Test that get_status returns same status for completed run."""
        provider_factory.setup_generation_success(provider)

        if isinstance(provider, DebuggAIProvider):
            with patch.object(provider, "_api_request") as mock_request:
                mock_request.return_value = {
                    "success": True,
                    "testSuiteUuid": "suite-123",
                }
                gen_result = provider.generate_tests(sample_changes, sample_config)

            # Mark as completed
            run = provider._runs[gen_result.run_id]
            run.status = GenerationStatus.COMPLETED
            run.tests_generated = 5

            status1 = provider.get_status(gen_result.run_id)
            status2 = provider.get_status(gen_result.run_id)
        else:
            gen_result = provider.generate_tests(sample_changes, sample_config)
            # MockE2EProvider completes immediately with simulate_delay=False
            status1 = provider.get_status(gen_result.run_id)
            status2 = provider.get_status(gen_result.run_id)

        assert status1.status == status2.status
        assert status1.run_id == status2.run_id
