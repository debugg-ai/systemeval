"""
Tests for DebuggAI E2E provider.

These tests validate the DebuggAI provider implementation
without making actual API calls (uses mocking).
"""

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from systemeval.e2e import (
    Change,
    ChangeSet,
    ChangeType,
    E2EConfig,
    GenerationStatus,
    DebuggAIProvider,
)
from systemeval.e2e.providers.debuggai import DebuggAIProviderConfig


# ============================================================================
# Provider Config Tests
# ============================================================================


class TestDebuggAIProviderConfig:
    """Test DebuggAI provider configuration."""

    def test_valid_config(self):
        """Test valid config creation."""
        config = DebuggAIProviderConfig(
            api_key="sk_test_123",
            api_base_url="https://api.debugg.ai",
        )

        assert config.api_key == "sk_test_123"
        assert config.api_base_url == "https://api.debugg.ai"
        assert config.timeout_seconds == 30  # default
        assert config.poll_interval_seconds == 5  # default
        assert config.max_wait_seconds == 600  # default

    def test_api_key_required(self):
        """Test empty api_key raises ValueError."""
        with pytest.raises(ValueError, match="api_key is required"):
            DebuggAIProviderConfig(api_key="", api_base_url="https://api.debugg.ai")

    def test_api_base_url_required(self):
        """Test empty api_base_url raises ValueError."""
        with pytest.raises(ValueError, match="api_base_url is required"):
            DebuggAIProviderConfig(api_key="sk_test", api_base_url="")

    def test_trailing_slash_stripped(self):
        """Test trailing slash is stripped from base URL."""
        config = DebuggAIProviderConfig(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai/",
        )

        assert config.api_base_url == "https://api.debugg.ai"

    def test_timeout_must_be_positive(self):
        """Test timeout_seconds must be positive."""
        with pytest.raises(ValueError, match="timeout_seconds must be positive"):
            DebuggAIProviderConfig(
                api_key="sk_test",
                api_base_url="https://api.debugg.ai",
                timeout_seconds=0,
            )

    def test_poll_interval_must_be_positive(self):
        """Test poll_interval_seconds must be positive."""
        with pytest.raises(ValueError, match="poll_interval_seconds must be positive"):
            DebuggAIProviderConfig(
                api_key="sk_test",
                api_base_url="https://api.debugg.ai",
                poll_interval_seconds=-1,
            )


# ============================================================================
# Provider Initialization Tests
# ============================================================================


class TestDebuggAIProviderInit:
    """Test DebuggAI provider initialization."""

    def test_initialization(self):
        """Test provider initialization with valid config."""
        provider = DebuggAIProvider(
            api_key="sk_test_123",
            api_base_url="https://api.debugg.ai",
        )

        assert provider.api_key == "sk_test_123"
        assert provider.api_base_url == "https://api.debugg.ai"

    def test_initialization_with_custom_timeouts(self):
        """Test provider initialization with custom timeouts."""
        provider = DebuggAIProvider(
            api_key="sk_test_123",
            api_base_url="https://api.debugg.ai",
            timeout_seconds=60,
            poll_interval_seconds=10,
            max_wait_seconds=1200,
        )

        assert provider._config.timeout_seconds == 60
        assert provider._config.poll_interval_seconds == 10
        assert provider._config.max_wait_seconds == 1200

    def test_initialization_fails_without_api_key(self):
        """Test provider initialization fails without api_key."""
        with pytest.raises(ValueError, match="api_key is required"):
            DebuggAIProvider(api_key="", api_base_url="https://api.debugg.ai")

    def test_context_manager(self):
        """Test provider can be used as context manager."""
        with DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        ) as provider:
            assert provider.api_key == "sk_test"


# ============================================================================
# Config Validation Tests
# ============================================================================


class TestDebuggAIProviderValidateConfig:
    """Test DebuggAI provider config validation."""

    def test_valid_config(self, tmp_path):
        """Test validation passes with valid config."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        # Mock the health check
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {"status": "ok"}
            result = provider.validate_config(config)

        assert result.valid
        assert len(result.errors) == 0

    def test_validation_fails_without_project_url(self, tmp_path):
        """Test validation fails without project_url."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            # Missing project_url
        )

        with patch.object(provider, "_api_request"):
            result = provider.validate_config(config)

        assert not result.valid
        assert "project_url is required" in result.errors[0]

    def test_validation_fails_with_nonexistent_project_root(self, tmp_path):
        """Test validation fails with nonexistent project_root."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path / "nonexistent",
            project_url="http://localhost:3000",
        )

        with patch.object(provider, "_api_request"):
            result = provider.validate_config(config)

        assert not result.valid
        assert "does not exist" in result.errors[0]

    def test_validation_warns_on_unsupported_framework(self, tmp_path):
        """Test validation warns on unsupported test framework."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
            test_framework="custom_framework",
        )

        with patch.object(provider, "_api_request"):
            result = provider.validate_config(config)

        # Should still be valid but with warnings
        assert result.valid
        assert len(result.warnings) > 0
        assert "may not be fully supported" in result.warnings[0]


# ============================================================================
# Test Generation Tests
# ============================================================================


class TestDebuggAIProviderGenerateTests:
    """Test DebuggAI provider test generation."""

    @pytest.fixture
    def provider(self):
        """Create provider for testing."""
        return DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

    @pytest.fixture
    def changes(self, tmp_path):
        """Create test changes."""
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
    def config(self, tmp_path):
        """Create test config."""
        return E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

    def test_generate_tests_success(self, provider, changes, config):
        """Test successful test generation."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }

            result = provider.generate_tests(changes, config)

        assert result.run_id.startswith("debuggai-")
        assert result.status == GenerationStatus.IN_PROGRESS
        assert "suite-123" in result.message

    def test_generate_tests_failure(self, provider, changes, config):
        """Test test generation failure."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": False,
                "error": "API error",
            }

            result = provider.generate_tests(changes, config)

        assert result.status == GenerationStatus.FAILED
        assert "API error" in result.message

    def test_generate_tests_tracks_run(self, provider, changes, config):
        """Test that generate_tests tracks the run."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }

            result = provider.generate_tests(changes, config)

        assert result.run_id in provider._runs
        run = provider._runs[result.run_id]
        assert run.suite_uuid == "suite-123"
        assert run.status == GenerationStatus.IN_PROGRESS


# ============================================================================
# Status Polling Tests
# ============================================================================


class TestDebuggAIProviderGetStatus:
    """Test DebuggAI provider status polling."""

    @pytest.fixture
    def provider_with_run(self, tmp_path):
        """Create provider with an active run."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            result = provider.generate_tests(changes, config)

        return provider, result.run_id

    def test_get_status_in_progress(self, provider_with_run):
        """Test getting status for in-progress run."""
        provider, run_id = provider_with_run

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "suite": {
                    "status": "running",
                    "tests": [
                        {"curRun": {"status": "completed"}},
                        {"curRun": {"status": "running"}},
                    ],
                }
            }

            status = provider.get_status(run_id)

        assert status.status == GenerationStatus.IN_PROGRESS
        assert status.tests_generated == 2
        assert status.progress_percent == 50.0

    def test_get_status_completed(self, provider_with_run):
        """Test getting status for completed run."""
        provider, run_id = provider_with_run

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "suite": {
                    "status": "completed",
                    "tests": [
                        {"curRun": {"status": "completed"}},
                        {"curRun": {"status": "completed"}},
                    ],
                }
            }

            status = provider.get_status(run_id)

        assert status.status == GenerationStatus.COMPLETED
        assert status.tests_generated == 2
        assert status.progress_percent == 100.0

    def test_get_status_unknown_run_raises(self):
        """Test getting status for unknown run raises KeyError."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        with pytest.raises(KeyError, match="not found"):
            provider.get_status("unknown-run-id")


# ============================================================================
# Artifact Download Tests
# ============================================================================


class TestDebuggAIProviderDownloadArtifacts:
    """Test DebuggAI provider artifact downloads."""

    @pytest.fixture
    def provider_with_completed_run(self, tmp_path):
        """Create provider with a completed run."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            result = provider.generate_tests(changes, config)

        # Mark as completed with suite data
        run = provider._runs[result.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = {
            "tests": [
                {
                    "name": "test-1",
                    "uuid": "test-uuid-1",
                    "curRun": {
                        "status": "completed",
                        "runScript": "https://api.debugg.ai/artifacts/script.js",
                        "runGif": "https://api.debugg.ai/artifacts/recording.gif",
                        "runJson": "https://api.debugg.ai/artifacts/details.json",
                    },
                }
            ]
        }

        return provider, result.run_id

    def test_download_artifacts_success(self, provider_with_completed_run, tmp_path):
        """Test successful artifact download."""
        provider, run_id = provider_with_completed_run
        output_dir = tmp_path / "output"

        with patch.object(provider, "_download_file") as mock_download:
            mock_download.return_value = True

            artifacts = provider.download_artifacts(run_id, output_dir)

        assert artifacts.total_tests == 1
        assert len(artifacts.test_files) == 3  # script, gif, json
        assert output_dir in [f.parent.parent for f in artifacts.test_files]

    def test_download_artifacts_fails_if_not_completed(self, tmp_path):
        """Test download fails if run not completed."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[Change("file.py", ChangeType.ADDED, additions=10)],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
        )

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            result = provider.generate_tests(changes, config)

        output_dir = tmp_path / "output"

        with pytest.raises(ValueError, match="not completed"):
            provider.download_artifacts(result.run_id, output_dir)

    def test_download_artifacts_unknown_run_raises(self, tmp_path):
        """Test download fails for unknown run."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        with pytest.raises(KeyError, match="not found"):
            provider.download_artifacts("unknown-run", tmp_path)


# ============================================================================
# Integration Tests
# ============================================================================


class TestDebuggAIProviderIntegration:
    """Integration tests for DebuggAI provider."""

    def test_full_workflow_mocked(self, tmp_path):
        """Test complete workflow with mocked API."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[
                Change("src/api.py", ChangeType.MODIFIED, additions=20, deletions=5),
                Change("src/models.py", ChangeType.ADDED, additions=50),
            ],
            repository_root=tmp_path,
        )

        config = E2EConfig(
            provider_name="debuggai",
            project_root=tmp_path,
            project_url="http://localhost:3000",
            output_directory=tmp_path / "tests",
        )

        # Step 1: Validate config
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {"status": "ok"}
            validation = provider.validate_config(config)
        assert validation.valid

        # Step 2: Generate tests
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            generation = provider.generate_tests(changes, config)
        assert generation.status == GenerationStatus.IN_PROGRESS

        # Step 3: Poll for status
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = {
                "suite": {
                    "status": "completed",
                    "tests": [
                        {
                            "name": "test-api",
                            "curRun": {
                                "status": "completed",
                                "runScript": "https://example.com/script.js",
                            },
                        }
                    ],
                }
            }
            status = provider.get_status(generation.run_id)
        assert status.status == GenerationStatus.COMPLETED

        # Step 4: Download artifacts
        with patch.object(provider, "_download_file") as mock_download:
            mock_download.return_value = True
            artifacts = provider.download_artifacts(
                generation.run_id, tmp_path / "output"
            )
        assert artifacts.total_tests == 1
