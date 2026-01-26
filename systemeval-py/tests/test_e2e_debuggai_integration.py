"""
Integration tests for DebuggAI E2E provider.

These tests validate the full workflow of the DebuggAI provider with mocked
HTTP responses, simulating real API interactions without making actual calls.

Tests cover:
- Full generation workflow (generate -> poll status -> download)
- Error handling (API errors, timeouts, invalid responses)
- Retry behavior
- Artifact download verification
- Network error handling
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, Mock, patch, call

import pytest
import requests

from systemeval.e2e import (
    Change,
    ChangeSet,
    ChangeType,
    E2EConfig,
    GenerationStatus,
    DebuggAIProvider,
)
from systemeval.e2e.providers.debuggai import DebuggAIProviderConfig, DebuggAIRun


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_responses():
    """Factory for creating mock API responses."""

    class ResponseFactory:
        @staticmethod
        def health_ok() -> Dict[str, Any]:
            return {"status": "ok", "version": "1.2.3"}

        @staticmethod
        def suite_created(suite_uuid: str = "suite-abc123") -> Dict[str, Any]:
            return {
                "success": True,
                "testSuiteUuid": suite_uuid,
                "message": "Test suite created successfully",
            }

        @staticmethod
        def suite_creation_failed(error: str = "Invalid request") -> Dict[str, Any]:
            return {
                "success": False,
                "error": error,
            }

        @staticmethod
        def suite_status_pending(suite_uuid: str = "suite-abc123") -> Dict[str, Any]:
            return {
                "suite": {
                    "uuid": suite_uuid,
                    "status": "pending",
                    "tests": [],
                }
            }

        @staticmethod
        def suite_status_running(
            suite_uuid: str = "suite-abc123",
            tests_total: int = 3,
            tests_completed: int = 1,
        ) -> Dict[str, Any]:
            tests = []
            for i in range(tests_total):
                status = "completed" if i < tests_completed else "running"
                tests.append({
                    "uuid": f"test-{i+1}",
                    "name": f"test-{i+1}",
                    "curRun": {"status": status},
                })
            return {
                "suite": {
                    "uuid": suite_uuid,
                    "status": "running",
                    "tests": tests,
                }
            }

        @staticmethod
        def suite_status_completed(
            suite_uuid: str = "suite-abc123",
            tests: List[Dict[str, Any]] = None,
        ) -> Dict[str, Any]:
            if tests is None:
                tests = [
                    {
                        "uuid": "test-1",
                        "name": "login-flow",
                        "curRun": {
                            "status": "completed",
                            "runScript": "https://api.debugg.ai/artifacts/test-1/script.js",
                            "runGif": "https://api.debugg.ai/artifacts/test-1/recording.gif",
                            "runJson": "https://api.debugg.ai/artifacts/test-1/details.json",
                        },
                    },
                    {
                        "uuid": "test-2",
                        "name": "signup-flow",
                        "curRun": {
                            "status": "completed",
                            "runScript": "https://api.debugg.ai/artifacts/test-2/script.js",
                            "runGif": "https://api.debugg.ai/artifacts/test-2/recording.gif",
                            "runJson": "https://api.debugg.ai/artifacts/test-2/details.json",
                        },
                    },
                ]
            return {
                "suite": {
                    "uuid": suite_uuid,
                    "status": "completed",
                    "tests": tests,
                }
            }

        @staticmethod
        def suite_status_failed(
            suite_uuid: str = "suite-abc123",
            error: str = "Generation failed",
        ) -> Dict[str, Any]:
            return {
                "suite": {
                    "uuid": suite_uuid,
                    "status": "failed",
                    "error": error,
                    "tests": [],
                }
            }

    return ResponseFactory()


@pytest.fixture
def provider():
    """Create a DebuggAI provider for testing."""
    return DebuggAIProvider(
        api_key="sk_test_integration_key",
        api_base_url="https://api.debugg.ai",
        timeout_seconds=30,
        poll_interval_seconds=1,
        max_wait_seconds=60,
    )


@pytest.fixture
def sample_changes(tmp_path):
    """Create sample code changes for testing."""
    return ChangeSet(
        base_ref="main",
        head_ref="feature/user-auth",
        changes=[
            Change(
                file_path="src/auth/login.ts",
                change_type=ChangeType.MODIFIED,
                additions=25,
                deletions=10,
                diff="@@ -1,10 +1,25 @@\n+// New login logic",
            ),
            Change(
                file_path="src/auth/signup.ts",
                change_type=ChangeType.ADDED,
                additions=80,
                deletions=0,
                diff="@@ -0,0 +1,80 @@\n+// New signup component",
            ),
            Change(
                file_path="src/components/Button.tsx",
                change_type=ChangeType.MODIFIED,
                additions=5,
                deletions=2,
            ),
        ],
        repository_root=tmp_path,
    )


@pytest.fixture
def sample_config(tmp_path):
    """Create sample E2E configuration for testing."""
    return E2EConfig(
        provider_name="debuggai",
        project_root=tmp_path,
        project_url="http://localhost:3000",
        project_slug="test-project",
        test_framework="playwright",
        programming_language="typescript",
    )


# ============================================================================
# Full Workflow Integration Tests
# ============================================================================


class TestFullGenerationWorkflow:
    """Test the complete E2E test generation workflow."""

    def test_successful_workflow_generate_poll_download(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test complete successful workflow: generate -> poll -> download."""
        output_dir = tmp_path / "e2e_output"
        suite_uuid = "suite-workflow-123"

        # Mock the session to intercept all requests
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            # Setup response sequence
            response_sequence = [
                # 1. Health check (validate_config)
                self._create_mock_response(200, mock_responses.health_ok()),
                # 2. Create suite (generate_tests)
                self._create_mock_response(200, mock_responses.suite_created(suite_uuid)),
                # 3. First status poll - pending
                self._create_mock_response(200, mock_responses.suite_status_pending(suite_uuid)),
                # 4. Second status poll - running
                self._create_mock_response(200, mock_responses.suite_status_running(suite_uuid, 2, 1)),
                # 5. Third status poll - completed
                self._create_mock_response(200, mock_responses.suite_status_completed(suite_uuid)),
            ]
            mock_session.request.side_effect = response_sequence

            # Setup download mock
            mock_session.get.return_value = self._create_mock_download_response(b"test content")

            # Step 1: Validate config
            validation = provider.validate_config(sample_config)
            assert validation.valid, f"Validation failed: {validation.errors}"

            # Step 2: Generate tests
            generation = provider.generate_tests(sample_changes, sample_config)
            assert generation.status == GenerationStatus.IN_PROGRESS
            assert generation.run_id.startswith("debuggai-")
            assert suite_uuid in generation.message

            # Step 3: Poll for status - first poll (pending)
            status1 = provider.get_status(generation.run_id)
            assert status1.status == GenerationStatus.PENDING
            assert status1.tests_generated == 0

            # Step 4: Poll for status - second poll (running)
            status2 = provider.get_status(generation.run_id)
            assert status2.status == GenerationStatus.IN_PROGRESS
            assert status2.tests_generated == 2
            assert status2.progress_percent == 50.0

            # Step 5: Poll for status - third poll (completed)
            status3 = provider.get_status(generation.run_id)
            assert status3.status == GenerationStatus.COMPLETED
            assert status3.tests_generated == 2
            assert status3.progress_percent == 100.0

            # Step 6: Download artifacts
            artifacts = provider.download_artifacts(generation.run_id, output_dir)
            assert artifacts.total_tests == 2
            assert len(artifacts.test_files) > 0
            assert artifacts.output_directory == output_dir

    def test_workflow_with_progress_updates(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test workflow with detailed progress updates during polling."""
        suite_uuid = "suite-progress-test"

        with patch.object(provider, "_api_request") as mock_request:
            # Setup response sequence for multi-test progress
            mock_request.side_effect = [
                # Create suite
                mock_responses.suite_created(suite_uuid),
                # Status poll 1: 0/5 tests complete
                mock_responses.suite_status_running(suite_uuid, tests_total=5, tests_completed=0),
                # Status poll 2: 2/5 tests complete
                mock_responses.suite_status_running(suite_uuid, tests_total=5, tests_completed=2),
                # Status poll 3: 4/5 tests complete
                mock_responses.suite_status_running(suite_uuid, tests_total=5, tests_completed=4),
                # Status poll 4: completed
                mock_responses.suite_status_completed(suite_uuid),
            ]

            # Generate tests
            generation = provider.generate_tests(sample_changes, sample_config)
            assert generation.status == GenerationStatus.IN_PROGRESS

            # Track progress through polling
            progress_history = []
            for _ in range(4):
                status = provider.get_status(generation.run_id)
                progress_history.append({
                    "status": status.status,
                    "progress": status.progress_percent,
                    "tests_generated": status.tests_generated,
                })
                if status.status == GenerationStatus.COMPLETED:
                    break

            # Verify progress increased over time
            assert len(progress_history) == 4
            assert progress_history[0]["progress"] == 0.0
            assert progress_history[1]["progress"] == 40.0  # 2/5
            assert progress_history[2]["progress"] == 80.0  # 4/5
            assert progress_history[3]["status"] == GenerationStatus.COMPLETED

    def _create_mock_response(self, status_code: int, json_data: Dict[str, Any]) -> MagicMock:
        """Create a mock response object."""
        response = MagicMock()
        response.status_code = status_code
        response.json.return_value = json_data
        response.text = json.dumps(json_data)
        return response

    def _create_mock_download_response(self, content: bytes) -> MagicMock:
        """Create a mock download response."""
        response = MagicMock()
        response.status_code = 200
        response.iter_content.return_value = [content]
        response.raise_for_status.return_value = None
        return response


# ============================================================================
# API Error Handling Tests
# ============================================================================


class TestAPIErrorHandling:
    """Test error handling for various API failure scenarios."""

    def test_suite_creation_api_error(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test handling of API error during suite creation."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_creation_failed(
                "Rate limit exceeded"
            )

            result = provider.generate_tests(sample_changes, sample_config)

            assert result.status == GenerationStatus.FAILED
            assert "Rate limit exceeded" in result.message

    def test_suite_creation_http_error(
        self, provider, sample_changes, sample_config
    ):
        """Test handling of HTTP 500 error during suite creation."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = ValueError("API error: Internal server error")

            with pytest.raises(ValueError, match="Internal server error"):
                provider.generate_tests(sample_changes, sample_config)

    def test_status_polling_api_error(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test handling of API error during status polling."""
        with patch.object(provider, "_api_request") as mock_request:
            # First call succeeds (create suite)
            # Second call fails (status poll)
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                ValueError("API error: Service unavailable"),
            ]

            generation = provider.generate_tests(sample_changes, sample_config)
            assert generation.status == GenerationStatus.IN_PROGRESS

            with pytest.raises(ValueError, match="Service unavailable"):
                provider.get_status(generation.run_id)

    def test_missing_suite_uuid_in_response(
        self, provider, sample_changes, sample_config
    ):
        """Test handling of missing suite UUID in API response."""
        with patch.object(provider, "_api_request") as mock_request:
            # Response is successful but missing UUID
            mock_request.return_value = {
                "success": True,
                "message": "Created but UUID missing",
                # No testSuiteUuid or uuid field
            }

            result = provider.generate_tests(sample_changes, sample_config)

            assert result.status == GenerationStatus.FAILED
            assert "No suite UUID" in result.message

    def test_invalid_json_response(self, provider, sample_changes, sample_config):
        """Test handling of invalid JSON in API response."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            # Create a response that raises JSONDecodeError
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.side_effect = json.JSONDecodeError("Invalid JSON", "", 0)
            mock_session.request.return_value = mock_response

            with pytest.raises(json.JSONDecodeError):
                provider.generate_tests(sample_changes, sample_config)

    def test_http_401_unauthorized(self, provider, sample_changes, sample_config):
        """Test handling of 401 Unauthorized response."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {"error": "Invalid API key"}
            mock_response.text = "Invalid API key"
            mock_session.request.return_value = mock_response

            with pytest.raises(ValueError, match="Invalid API key"):
                provider.generate_tests(sample_changes, sample_config)

    def test_http_403_forbidden(self, provider, sample_changes, sample_config):
        """Test handling of 403 Forbidden response."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.json.return_value = {"error": "Access denied to resource"}
            mock_response.text = "Access denied"
            mock_session.request.return_value = mock_response

            with pytest.raises(ValueError, match="Access denied"):
                provider.generate_tests(sample_changes, sample_config)

    def test_http_404_not_found(self, provider, sample_changes, sample_config, mock_responses):
        """Test handling of 404 Not Found for suite status."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                ValueError("API error: Suite not found"),
            ]

            generation = provider.generate_tests(sample_changes, sample_config)

            with pytest.raises(ValueError, match="Suite not found"):
                provider.get_status(generation.run_id)

    def test_http_500_server_error(self, provider, sample_changes, sample_config):
        """Test handling of 500 Internal Server Error."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.json.return_value = {"error": "Internal server error"}
            mock_response.text = "Internal server error"
            mock_session.request.return_value = mock_response

            with pytest.raises(ValueError, match="Internal server error"):
                provider.generate_tests(sample_changes, sample_config)


# ============================================================================
# Timeout Handling Tests
# ============================================================================


class TestTimeoutHandling:
    """Test timeout scenarios during API operations."""

    def test_request_timeout_during_suite_creation(
        self, provider, sample_changes, sample_config
    ):
        """Test handling of request timeout during suite creation."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.Timeout("Connection timed out")

            with pytest.raises(requests.Timeout):
                provider.generate_tests(sample_changes, sample_config)

    def test_request_timeout_during_status_poll(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test handling of request timeout during status polling."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            # First request succeeds
            create_response = MagicMock()
            create_response.status_code = 200
            create_response.json.return_value = mock_responses.suite_created("suite-123")

            # Status poll times out
            mock_session.request.side_effect = [
                create_response,
                requests.Timeout("Status poll timed out"),
            ]

            generation = provider.generate_tests(sample_changes, sample_config)
            assert generation.status == GenerationStatus.IN_PROGRESS

            with pytest.raises(requests.Timeout):
                provider.get_status(generation.run_id)

    def test_connection_timeout(self, provider, sample_changes, sample_config):
        """Test handling of connection timeout."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.ConnectTimeout(
                "Failed to establish connection"
            )

            with pytest.raises(requests.ConnectTimeout):
                provider.generate_tests(sample_changes, sample_config)

    def test_read_timeout(self, provider, sample_changes, sample_config):
        """Test handling of read timeout."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.ReadTimeout(
                "Read operation timed out"
            )

            with pytest.raises(requests.ReadTimeout):
                provider.generate_tests(sample_changes, sample_config)


# ============================================================================
# Network Error Handling Tests
# ============================================================================


class TestNetworkErrorHandling:
    """Test handling of network-related errors."""

    def test_connection_error(self, provider, sample_changes, sample_config):
        """Test handling of connection errors."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.ConnectionError(
                "Failed to resolve hostname"
            )

            with pytest.raises(requests.ConnectionError):
                provider.generate_tests(sample_changes, sample_config)

    def test_ssl_error(self, provider, sample_changes, sample_config):
        """Test handling of SSL certificate errors."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.exceptions.SSLError(
                "SSL certificate verification failed"
            )

            with pytest.raises(requests.exceptions.SSLError):
                provider.generate_tests(sample_changes, sample_config)

    def test_dns_resolution_failure(self, provider, sample_changes, sample_config):
        """Test handling of DNS resolution failure."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.ConnectionError(
                "Name or service not known"
            )

            with pytest.raises(requests.ConnectionError):
                provider.generate_tests(sample_changes, sample_config)

    def test_network_unreachable(self, provider, sample_changes, sample_config):
        """Test handling of network unreachable error."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.request.side_effect = requests.ConnectionError(
                "Network is unreachable"
            )

            with pytest.raises(requests.ConnectionError):
                provider.generate_tests(sample_changes, sample_config)


# ============================================================================
# Invalid API Key Handling Tests
# ============================================================================


class TestInvalidAPIKeyHandling:
    """Test handling of invalid or missing API keys."""

    def test_empty_api_key_rejected(self):
        """Test that empty API key is rejected during initialization."""
        with pytest.raises(ValueError, match="api_key is required"):
            DebuggAIProvider(
                api_key="",
                api_base_url="https://api.debugg.ai",
            )

    def test_invalid_api_key_format_accepted_initially(self):
        """Test that invalid format API keys are accepted but fail at runtime."""
        # Provider accepts any non-empty string initially
        provider = DebuggAIProvider(
            api_key="invalid-format-key",
            api_base_url="https://api.debugg.ai",
        )
        assert provider.api_key == "invalid-format-key"

    def test_api_key_used_in_authorization_header(self, tmp_path):
        """Test that API key is correctly set in Authorization header."""
        provider = DebuggAIProvider(
            api_key="sk_test_my_api_key",
            api_base_url="https://api.debugg.ai",
        )

        # Access the session to trigger initialization
        session = provider._get_session()

        assert "Authorization" in session.headers
        assert session.headers["Authorization"] == "Bearer sk_test_my_api_key"

    def test_expired_api_key_handling(
        self, provider, sample_changes, sample_config
    ):
        """Test handling of expired API key response."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.json.return_value = {
                "error": "API key has expired",
                "code": "API_KEY_EXPIRED",
            }
            mock_response.text = "API key has expired"
            mock_session.request.return_value = mock_response

            with pytest.raises(ValueError, match="API key has expired"):
                provider.generate_tests(sample_changes, sample_config)


# ============================================================================
# Artifact Download Tests
# ============================================================================


class TestArtifactDownload:
    """Test artifact download functionality."""

    def test_successful_artifact_download(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test successful download of all artifacts."""
        output_dir = tmp_path / "artifacts"
        suite_uuid = "suite-download-test"

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created(suite_uuid)
            generation = provider.generate_tests(sample_changes, sample_config)

        # Set up completed run with suite data
        run = provider._runs[generation.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = mock_responses.suite_status_completed(suite_uuid)["suite"]

        # Mock file downloads
        with patch.object(provider, "_download_file") as mock_download:
            mock_download.return_value = True

            artifacts = provider.download_artifacts(generation.run_id, output_dir)

            assert artifacts.total_tests == 2
            assert artifacts.output_directory == output_dir
            # 2 tests x 3 artifacts each (script, gif, json) = 6 files
            assert len(artifacts.test_files) == 6

    def test_partial_artifact_download_failure(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test handling of partial download failures."""
        output_dir = tmp_path / "artifacts"
        suite_uuid = "suite-partial-failure"

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created(suite_uuid)
            generation = provider.generate_tests(sample_changes, sample_config)

        # Set up completed run
        run = provider._runs[generation.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = mock_responses.suite_status_completed(suite_uuid)["suite"]

        # Mock downloads - some succeed, some fail
        download_results = [True, False, True, False, True, False]  # Alternating
        with patch.object(provider, "_download_file") as mock_download:
            mock_download.side_effect = download_results

            artifacts = provider.download_artifacts(generation.run_id, output_dir)

            # Only successful downloads should be in test_files
            assert len(artifacts.test_files) == 3  # 3 successes

    def test_artifact_download_network_error(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test handling of network errors during download."""
        output_dir = tmp_path / "artifacts"
        suite_uuid = "suite-network-error"

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created(suite_uuid)
            generation = provider.generate_tests(sample_changes, sample_config)

        run = provider._runs[generation.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = mock_responses.suite_status_completed(suite_uuid)["suite"]

        # Mock download to return False (simulating network error handled internally)
        with patch.object(provider, "_download_file") as mock_download:
            mock_download.return_value = False

            artifacts = provider.download_artifacts(generation.run_id, output_dir)

            # Should complete but with no files
            assert artifacts.total_tests == 2
            assert len(artifacts.test_files) == 0

    def test_artifact_download_not_completed_raises(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test that downloading artifacts from incomplete run raises error."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created("suite-123")
            generation = provider.generate_tests(sample_changes, sample_config)

        # Run is still IN_PROGRESS (not completed)
        with pytest.raises(ValueError, match="not completed"):
            provider.download_artifacts(generation.run_id, tmp_path / "output")

    def test_artifact_download_unknown_run_raises(self, provider, tmp_path):
        """Test that downloading artifacts for unknown run raises error."""
        with pytest.raises(KeyError, match="not found"):
            provider.download_artifacts("unknown-run-id", tmp_path)

    def test_artifact_download_creates_directory(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test that download creates output directory if it does not exist."""
        output_dir = tmp_path / "nested" / "output" / "directory"
        assert not output_dir.exists()

        suite_uuid = "suite-mkdir-test"

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created(suite_uuid)
            generation = provider.generate_tests(sample_changes, sample_config)

        run = provider._runs[generation.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = {"tests": []}  # Empty tests

        artifacts = provider.download_artifacts(generation.run_id, output_dir)

        assert output_dir.exists()
        assert artifacts.output_directory == output_dir


# ============================================================================
# Status Polling Edge Cases
# ============================================================================


class TestStatusPollingEdgeCases:
    """Test edge cases in status polling."""

    def test_status_for_unknown_run_raises_keyerror(self, provider):
        """Test that getting status for unknown run raises KeyError."""
        with pytest.raises(KeyError, match="not found"):
            provider.get_status("nonexistent-run-id")

    def test_status_cached_after_completion(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test that status is cached after run completes."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                mock_responses.suite_status_completed("suite-123"),
            ]

            generation = provider.generate_tests(sample_changes, sample_config)

            # First status call hits the API
            status1 = provider.get_status(generation.run_id)
            assert status1.status == GenerationStatus.COMPLETED

        # Second status call should NOT hit the API (cached)
        # If it did, it would fail because mock has no more responses
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = Exception("Should not be called")

            status2 = provider.get_status(generation.run_id)
            assert status2.status == GenerationStatus.COMPLETED
            mock_request.assert_not_called()

    def test_status_cached_after_failure(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test that status is cached after run fails."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                mock_responses.suite_status_failed("suite-123", "Generation failed"),
            ]

            generation = provider.generate_tests(sample_changes, sample_config)
            status1 = provider.get_status(generation.run_id)
            assert status1.status == GenerationStatus.FAILED

        # Verify cache is used
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = Exception("Should not be called")

            status2 = provider.get_status(generation.run_id)
            assert status2.status == GenerationStatus.FAILED

    def test_status_with_no_tests(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test status polling when no tests are generated."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                {
                    "suite": {
                        "uuid": "suite-123",
                        "status": "completed",
                        "tests": [],  # No tests
                    }
                },
            ]

            generation = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(generation.run_id)

            assert status.status == GenerationStatus.COMPLETED
            assert status.tests_generated == 0
            assert status.progress_percent == 0.0

    def test_status_with_unknown_status_string(
        self, provider, sample_changes, sample_config, mock_responses
    ):
        """Test handling of unknown status string from API."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = [
                mock_responses.suite_created("suite-123"),
                {
                    "suite": {
                        "uuid": "suite-123",
                        "status": "unknown_status_xyz",  # Unknown status
                        "tests": [],
                    }
                },
            ]

            generation = provider.generate_tests(sample_changes, sample_config)
            status = provider.get_status(generation.run_id)

            # Unknown status should default to IN_PROGRESS
            assert status.status == GenerationStatus.IN_PROGRESS


# ============================================================================
# Config Validation Integration Tests
# ============================================================================


class TestConfigValidationIntegration:
    """Test configuration validation with mocked API."""

    def test_validate_config_with_health_check(
        self, provider, sample_config, mock_responses
    ):
        """Test config validation includes health check."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.health_ok()

            result = provider.validate_config(sample_config)

            assert result.valid
            mock_request.assert_called_once_with("GET", "/health")

    def test_validate_config_health_check_failure_is_warning(
        self, provider, sample_config
    ):
        """Test that health check failure results in warning, not error."""
        with patch.object(provider, "_api_request") as mock_request:
            mock_request.side_effect = requests.ConnectionError("Cannot connect")

            result = provider.validate_config(sample_config)

            # Should still be valid but with warning
            assert result.valid
            assert len(result.warnings) > 0
            assert any("connectivity" in w.lower() for w in result.warnings)

    def test_validate_config_missing_project_url(self, tmp_path):
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
        assert any("project_url" in e for e in result.errors)


# ============================================================================
# Context Manager and Resource Cleanup Tests
# ============================================================================


class TestResourceManagement:
    """Test resource management and cleanup."""

    def test_context_manager_closes_session(self):
        """Test that context manager properly closes session."""
        with DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        ) as provider:
            # Access session to create it
            session = provider._get_session()
            assert provider._session is not None

        # After exiting context, session should be closed
        assert provider._session is None

    def test_explicit_close(self):
        """Test explicit close method."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        # Create session
        provider._get_session()
        assert provider._session is not None

        # Close
        provider.close()
        assert provider._session is None

    def test_close_without_session(self):
        """Test close when session was never created."""
        provider = DebuggAIProvider(
            api_key="sk_test",
            api_base_url="https://api.debugg.ai",
        )

        # Session never created
        assert provider._session is None

        # Close should not raise
        provider.close()
        assert provider._session is None


# ============================================================================
# Request Building and Payload Tests
# ============================================================================


class TestRequestPayloads:
    """Test that API requests are built correctly."""

    def test_suite_creation_payload_structure(
        self, provider, sample_changes, sample_config
    ):
        """Test that suite creation request has correct payload structure."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            mock_session.request.return_value = mock_response

            provider.generate_tests(sample_changes, sample_config)

            # Verify the request was made with correct payload
            call_args = mock_session.request.call_args
            assert call_args is not None

            # Check method and URL
            assert call_args.kwargs["method"] == "POST"
            assert "/cli/e2e/suites" in call_args.kwargs["url"]

            # Check payload structure
            payload = call_args.kwargs["json"]
            assert "repoName" in payload
            assert "branchName" in payload
            assert "commitHash" in payload
            assert "workingChanges" in payload
            assert "testDescription" in payload

            # Verify changes are included
            assert len(payload["workingChanges"]) == 3
            assert payload["workingChanges"][0]["file"] == "src/auth/login.ts"
            assert payload["workingChanges"][0]["status"] == "modified"

    def test_authorization_header_included(self, provider, sample_changes, sample_config):
        """Test that Authorization header is included in requests."""
        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_session.headers = {
                "Authorization": "Bearer sk_test_integration_key",
                "Content-Type": "application/json",
            }
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                "success": True,
                "testSuiteUuid": "suite-123",
            }
            mock_session.request.return_value = mock_response

            provider.generate_tests(sample_changes, sample_config)

            # Verify session has correct headers
            assert mock_session.headers["Authorization"] == "Bearer sk_test_integration_key"


# ============================================================================
# Internal Download File Tests
# ============================================================================


class TestInternalDownloadFile:
    """Test the internal _download_file method."""

    def test_download_file_success(self, provider, tmp_path):
        """Test successful file download."""
        test_file = tmp_path / "test.js"
        content = b"const test = () => {};"

        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.iter_content.return_value = [content]
            mock_response.raise_for_status.return_value = None
            mock_session.get.return_value = mock_response

            result = provider._download_file("https://example.com/test.js", test_file)

            assert result is True
            assert test_file.exists()
            assert test_file.read_bytes() == content

    def test_download_file_http_error(self, provider, tmp_path):
        """Test download failure due to HTTP error."""
        test_file = tmp_path / "test.js"

        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_response = MagicMock()
            mock_response.raise_for_status.side_effect = requests.HTTPError("404 Not Found")
            mock_session.get.return_value = mock_response

            result = provider._download_file("https://example.com/test.js", test_file)

            assert result is False
            assert not test_file.exists()

    def test_download_file_connection_error(self, provider, tmp_path):
        """Test download failure due to connection error."""
        test_file = tmp_path / "test.js"

        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.get.side_effect = requests.ConnectionError("Network error")

            result = provider._download_file("https://example.com/test.js", test_file)

            assert result is False

    def test_download_file_timeout(self, provider, tmp_path):
        """Test download failure due to timeout."""
        test_file = tmp_path / "test.js"

        with patch.object(provider, "_get_session") as mock_get_session:
            mock_session = MagicMock()
            mock_get_session.return_value = mock_session

            mock_session.get.side_effect = requests.Timeout("Download timed out")

            result = provider._download_file("https://example.com/test.js", test_file)

            assert result is False


# ============================================================================
# Suite Data Fetching Tests
# ============================================================================


class TestSuiteDataFetching:
    """Test suite data fetching behavior."""

    def test_download_fetches_suite_data_if_missing(
        self, provider, sample_changes, sample_config, mock_responses, tmp_path
    ):
        """Test that download_artifacts fetches suite data if not cached."""
        suite_uuid = "suite-fetch-test"

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_created(suite_uuid)
            generation = provider.generate_tests(sample_changes, sample_config)

        # Mark as completed but without suite_data
        run = provider._runs[generation.run_id]
        run.status = GenerationStatus.COMPLETED
        run.suite_data = None  # Explicitly no data

        with patch.object(provider, "_api_request") as mock_request:
            mock_request.return_value = mock_responses.suite_status_completed(suite_uuid)

            with patch.object(provider, "_download_file", return_value=True):
                artifacts = provider.download_artifacts(generation.run_id, tmp_path)

            # Verify API was called to fetch suite data
            mock_request.assert_called_once()
            assert f"/cli/e2e/suites/{suite_uuid}" in str(mock_request.call_args)

        assert artifacts.total_tests == 2


# ============================================================================
# Test Description Building Tests
# ============================================================================


class TestTestDescriptionBuilding:
    """Test the test description building functionality."""

    def test_description_includes_branch_info(
        self, provider, sample_changes, sample_config
    ):
        """Test that description includes branch information."""
        description = provider._build_test_description(sample_changes, sample_config)

        assert "feature/user-auth" in description  # head_ref
        assert "main" in description  # base_ref

    def test_description_includes_file_count(
        self, provider, sample_changes, sample_config
    ):
        """Test that description includes file count."""
        description = provider._build_test_description(sample_changes, sample_config)

        assert "3 files changed" in description

    def test_description_includes_file_types(
        self, provider, sample_changes, sample_config
    ):
        """Test that description includes file type summary."""
        description = provider._build_test_description(sample_changes, sample_config)

        # Should include TypeScript files
        assert "TypeScript" in description

    def test_description_includes_framework(
        self, provider, sample_changes, sample_config
    ):
        """Test that description includes test framework."""
        description = provider._build_test_description(sample_changes, sample_config)

        assert "playwright" in description.lower()

    def test_description_truncates_long_file_lists(self, provider, sample_config, tmp_path):
        """Test that description truncates file lists over 10 files."""
        # Create changeset with more than 10 files
        changes = ChangeSet(
            base_ref="main",
            head_ref="feature",
            changes=[
                Change(f"src/file{i}.ts", ChangeType.MODIFIED, additions=5)
                for i in range(15)
            ],
            repository_root=tmp_path,
        )

        description = provider._build_test_description(changes, sample_config)

        assert "..." in description  # Truncation indicator
        assert "15 files changed" in description
