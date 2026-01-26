"""
DebuggAI E2E test generation provider.

This module provides a Python implementation of the E2EProvider protocol
that integrates with the DebuggAI API for automated E2E test generation.

Follows systemeval's strict architectural principles:
- No environment variable discovery
- No magic values
- All configuration explicit
- No side effects on import
"""

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests

from ...core.protocols import E2EProvider
from ...core.types import (
    ArtifactResult,
    ChangeSet,
    E2EConfig,
    GenerationResult,
    GenerationStatus,
    StatusResult,
    ValidationResult,
)


@dataclass
class DebuggAIProviderConfig:
    """
    Configuration for DebuggAI provider.

    All parameters are explicit - no env var discovery.
    """

    api_key: str
    """API key for authentication (explicit, not from env)."""

    api_base_url: str = "https://api.debugg.ai"
    """Base URL for DebuggAI API."""

    timeout_seconds: int = 30
    """HTTP request timeout."""

    poll_interval_seconds: int = 5
    """Interval between status polls."""

    max_wait_seconds: int = 600
    """Maximum time to wait for test completion."""

    def __post_init__(self) -> None:
        """Validate configuration."""
        if not self.api_key:
            raise ValueError("api_key is required and cannot be empty")
        if not self.api_base_url:
            raise ValueError("api_base_url is required and cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if self.max_wait_seconds <= 0:
            raise ValueError("max_wait_seconds must be positive")

        # Strip trailing slash from base URL
        self.api_base_url = self.api_base_url.rstrip("/")


@dataclass
class DebuggAIRun:
    """Tracks a DebuggAI test run."""

    run_id: str
    suite_uuid: str
    status: GenerationStatus
    changes: ChangeSet
    config: E2EConfig
    created_at: float = field(default_factory=time.time)
    completed_at: Optional[float] = None
    tests_generated: int = 0
    suite_data: Optional[Dict[str, Any]] = None


class DebuggAIProvider(E2EProvider):
    """
    E2E provider implementation for DebuggAI.

    This provider integrates with the DebuggAI API to generate
    automated E2E tests based on code changes.

    Usage:
        provider = DebuggAIProvider(
            api_key="sk_live_...",
            api_base_url="https://api.debugg.ai",
        )

        # Validate config
        validation = provider.validate_config(config)
        if not validation.valid:
            raise ValueError(f"Invalid config: {validation.errors}")

        # Generate tests
        result = provider.generate_tests(changes, config)
        print(f"Run ID: {result.run_id}")

        # Poll for completion
        status = provider.get_status(result.run_id)
        while status.status == GenerationStatus.IN_PROGRESS:
            time.sleep(5)
            status = provider.get_status(result.run_id)

        # Download artifacts
        artifacts = provider.download_artifacts(result.run_id, output_dir)
    """

    def __init__(
        self,
        api_key: str,
        api_base_url: str = "https://api.debugg.ai",
        timeout_seconds: int = 30,
        poll_interval_seconds: int = 5,
        max_wait_seconds: int = 600,
    ) -> None:
        """
        Initialize DebuggAI provider with explicit configuration.

        Args:
            api_key: API key for authentication
            api_base_url: Base URL for DebuggAI API
            timeout_seconds: HTTP request timeout
            poll_interval_seconds: Interval between status polls
            max_wait_seconds: Maximum time to wait for completion

        Raises:
            ValueError: If configuration is invalid
        """
        self._config = DebuggAIProviderConfig(
            api_key=api_key,
            api_base_url=api_base_url,
            timeout_seconds=timeout_seconds,
            poll_interval_seconds=poll_interval_seconds,
            max_wait_seconds=max_wait_seconds,
        )

        # Track active runs
        self._runs: Dict[str, DebuggAIRun] = {}

        # Session for connection pooling
        self._session: Optional[requests.Session] = None

    @property
    def api_key(self) -> str:
        """API key (read-only)."""
        return self._config.api_key

    @property
    def api_base_url(self) -> str:
        """Base URL (read-only)."""
        return self._config.api_base_url

    def _get_session(self) -> requests.Session:
        """Get or create HTTP session."""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(
                {
                    "Authorization": f"Bearer {self._config.api_key}",
                    "Content-Type": "application/json",
                    "User-Agent": "systemeval/0.3.0",
                }
            )
        return self._session

    def _api_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Make an API request to DebuggAI.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (e.g., '/e2e/suites')
            data: Request body data
            params: Query parameters

        Returns:
            Response JSON as dict

        Raises:
            requests.RequestException: On network/HTTP errors
            ValueError: On API errors
        """
        url = urljoin(self._config.api_base_url, endpoint)
        session = self._get_session()

        response = session.request(
            method=method,
            url=url,
            json=data,
            params=params,
            timeout=self._config.timeout_seconds,
        )

        # Handle errors
        if response.status_code >= 400:
            try:
                error_data = response.json()
                error_msg = error_data.get("error", error_data.get("message", str(error_data)))
            except Exception:
                error_msg = response.text or f"HTTP {response.status_code}"

            raise ValueError(f"API error: {error_msg}")

        return response.json()

    def validate_config(self, config: E2EConfig) -> ValidationResult:
        """
        Validate E2E configuration for DebuggAI provider.

        Args:
            config: E2E configuration to validate

        Returns:
            ValidationResult with validation status and any errors/warnings
        """
        errors: List[str] = []
        warnings: List[str] = []

        # Required fields
        if not config.project_url:
            errors.append("project_url is required for DebuggAI provider")

        # Validate project_root exists
        if not config.project_root.exists():
            errors.append(f"project_root does not exist: {config.project_root}")

        # Validate output directory is writable
        if config.output_directory:
            if config.output_directory.exists() and not config.output_directory.is_dir():
                errors.append(f"output_directory is not a directory: {config.output_directory}")

        # Check test framework
        supported_frameworks = {"playwright", "cypress", "selenium"}
        if config.test_framework not in supported_frameworks:
            warnings.append(
                f"test_framework '{config.test_framework}' may not be fully supported. "
                f"Recommended: {', '.join(sorted(supported_frameworks))}"
            )

        # Check programming language
        supported_languages = {"typescript", "javascript", "python"}
        if config.programming_language not in supported_languages:
            warnings.append(
                f"programming_language '{config.programming_language}' may not be fully supported. "
                f"Recommended: {', '.join(sorted(supported_languages))}"
            )

        # Validate API connectivity (optional, non-blocking)
        try:
            self._api_request("GET", "/health")
        except Exception as e:
            warnings.append(f"Could not verify API connectivity: {e}")

        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
        )

    def generate_tests(self, changes: ChangeSet, config: E2EConfig) -> GenerationResult:
        """
        Generate E2E tests for the given changes.

        Args:
            changes: Set of code changes to generate tests for
            config: E2E configuration

        Returns:
            GenerationResult with run_id and initial status

        Raises:
            ValueError: On API errors
        """
        # Generate run ID
        run_id = f"debuggai-{uuid.uuid4().hex[:12]}"

        # Build request payload
        payload = {
            "repoName": config.project_slug or config.project_root.name,
            "repoPath": str(config.project_root),
            "branchName": changes.head_ref,
            "commitHash": changes.head_ref,
            "workingChanges": [
                {
                    "status": change.change_type.value,
                    "file": change.file_path,
                    "diff": change.diff,
                }
                for change in changes.changes
            ],
            "testDescription": self._build_test_description(changes, config),
        }

        # Add optional fields
        if config.project_url:
            payload["projectUrl"] = config.project_url

        # Create test suite
        response = self._api_request("POST", "/cli/e2e/suites", data=payload)

        if not response.get("success"):
            error = response.get("error", "Unknown error creating test suite")
            return GenerationResult(
                run_id=run_id,
                status=GenerationStatus.FAILED,
                message=error,
            )

        suite_uuid = response.get("testSuiteUuid", response.get("uuid"))
        if not suite_uuid:
            return GenerationResult(
                run_id=run_id,
                status=GenerationStatus.FAILED,
                message="No suite UUID returned from API",
            )

        # Track the run
        self._runs[run_id] = DebuggAIRun(
            run_id=run_id,
            suite_uuid=suite_uuid,
            status=GenerationStatus.IN_PROGRESS,
            changes=changes,
            config=config,
        )

        return GenerationResult(
            run_id=run_id,
            status=GenerationStatus.IN_PROGRESS,
            message=f"Test suite created: {suite_uuid}",
            metadata={"suite_uuid": suite_uuid},
        )

    def get_status(self, run_id: str) -> StatusResult:
        """
        Get the status of a test generation run.

        Args:
            run_id: The run ID returned from generate_tests

        Returns:
            StatusResult with current status and progress

        Raises:
            KeyError: If run_id not found
            ValueError: On API errors
        """
        if run_id not in self._runs:
            raise KeyError(f"Run '{run_id}' not found")

        run = self._runs[run_id]

        # If already completed/failed, return cached status
        if run.status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            return StatusResult(
                run_id=run_id,
                status=run.status,
                progress_percent=100.0 if run.status == GenerationStatus.COMPLETED else 0.0,
                tests_generated=run.tests_generated,
                message="Completed" if run.status == GenerationStatus.COMPLETED else "Failed",
            )

        # Poll API for status
        response = self._api_request("GET", f"/cli/e2e/suites/{run.suite_uuid}")

        suite = response.get("suite", response)
        status_str = suite.get("status", "pending")

        # Map API status to GenerationStatus
        status_map = {
            "pending": GenerationStatus.PENDING,
            "queued": GenerationStatus.PENDING,
            "running": GenerationStatus.IN_PROGRESS,
            "in_progress": GenerationStatus.IN_PROGRESS,
            "completed": GenerationStatus.COMPLETED,
            "failed": GenerationStatus.FAILED,
            "cancelled": GenerationStatus.CANCELLED,
        }
        status = status_map.get(status_str.lower(), GenerationStatus.IN_PROGRESS)

        # Count tests
        tests = suite.get("tests", [])
        tests_generated = len(tests)
        completed_tests = sum(
            1
            for t in tests
            if t.get("curRun", {}).get("status") in ("completed", "failed")
        )

        # Calculate progress
        progress = 0.0
        if tests_generated > 0:
            progress = (completed_tests / tests_generated) * 100.0

        # Update run state
        run.status = status
        run.tests_generated = tests_generated
        run.suite_data = suite

        if status in (GenerationStatus.COMPLETED, GenerationStatus.FAILED):
            run.completed_at = time.time()

        return StatusResult(
            run_id=run_id,
            status=status,
            progress_percent=progress,
            tests_generated=tests_generated,
            message=f"{completed_tests}/{tests_generated} tests completed",
            metadata={"suite_uuid": run.suite_uuid},
        )

    def download_artifacts(self, run_id: str, output_dir: Path) -> ArtifactResult:
        """
        Download test artifacts for a completed run.

        Args:
            run_id: The run ID
            output_dir: Directory to save artifacts

        Returns:
            ArtifactResult with downloaded file paths

        Raises:
            KeyError: If run_id not found
            ValueError: If run not completed or download fails
        """
        if run_id not in self._runs:
            raise KeyError(f"Run '{run_id}' not found")

        run = self._runs[run_id]

        # Ensure run is completed
        if run.status != GenerationStatus.COMPLETED:
            raise ValueError(
                f"Cannot download artifacts: run is {run.status.value}, not completed"
            )

        # Ensure we have suite data
        if not run.suite_data:
            # Fetch it
            response = self._api_request("GET", f"/cli/e2e/suites/{run.suite_uuid}")
            run.suite_data = response.get("suite", response)

        # Create output directory
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        test_files: List[Path] = []
        total_tests = 0

        tests = run.suite_data.get("tests", [])
        for test in tests:
            cur_run = test.get("curRun", {})
            if not cur_run:
                continue

            total_tests += 1
            test_name = test.get("name", f"test-{test.get('uuid', 'unknown')[:8]}")
            test_dir = output_dir / test_name
            test_dir.mkdir(parents=True, exist_ok=True)

            # Download script
            script_url = cur_run.get("runScript")
            if script_url:
                script_path = test_dir / f"{test_name}.spec.js"
                if self._download_file(script_url, script_path):
                    test_files.append(script_path)

            # Download recording (GIF)
            gif_url = cur_run.get("runGif")
            if gif_url:
                gif_path = test_dir / f"{test_name}-recording.gif"
                if self._download_file(gif_url, gif_path):
                    test_files.append(gif_path)

            # Download details (JSON)
            json_url = cur_run.get("runJson")
            if json_url:
                json_path = test_dir / f"{test_name}-details.json"
                if self._download_file(json_url, json_path):
                    test_files.append(json_path)

        return ArtifactResult(
            run_id=run_id,
            test_files=test_files,
            total_tests=total_tests,
            output_directory=output_dir,
        )

    def _download_file(self, url: str, path: Path) -> bool:
        """
        Download a file from URL to local path.

        Args:
            url: URL to download from
            path: Local path to save to

        Returns:
            True if successful, False otherwise
        """
        try:
            session = self._get_session()
            response = session.get(url, timeout=self._config.timeout_seconds, stream=True)
            response.raise_for_status()

            with open(path, "wb") as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return True
        except Exception:
            return False

    def _build_test_description(self, changes: ChangeSet, config: E2EConfig) -> str:
        """
        Build a test description for the API request.

        Args:
            changes: Set of code changes
            config: E2E configuration

        Returns:
            Test description string
        """
        file_count = len(changes.changes)

        # Analyze file types
        type_counts: Dict[str, int] = {}
        for change in changes.changes:
            ext = Path(change.file_path).suffix.lower()
            if ext in (".ts", ".tsx"):
                file_type = "TypeScript"
            elif ext in (".js", ".jsx"):
                file_type = "JavaScript"
            elif ext == ".py":
                file_type = "Python"
            elif ext in (".css", ".scss", ".sass"):
                file_type = "Styles"
            else:
                file_type = "Other"
            type_counts[file_type] = type_counts.get(file_type, 0) + 1

        type_summary = ", ".join(f"{count} {name}" for name, count in type_counts.items())

        description = f"""Generate E2E tests for changes on branch {changes.head_ref}.

Changes:
- {file_count} files changed ({type_summary})
- Base: {changes.base_ref}
- Head: {changes.head_ref}

Files:
{chr(10).join(f'- {c.file_path} ({c.change_type.value})' for c in changes.changes[:10])}
{'...' if file_count > 10 else ''}

Test framework: {config.test_framework}
Language: {config.programming_language}
"""
        return description

    def close(self) -> None:
        """Close the provider and release resources."""
        if self._session:
            self._session.close()
            self._session = None

    def __enter__(self) -> "DebuggAIProvider":
        """Context manager entry."""
        return self

    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()
